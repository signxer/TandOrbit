"""全局快捷键管理器（双平台）

- macOS：Quartz CGEventTap（需要「辅助功能」权限；未授权时通过 AXIsProcessTrusted 检测）
- Windows：RegisterHotKey + GetMessageW 消息循环线程

快捷键格式：修饰键用 ``+`` 连接，如 ``Ctrl+Alt+1``、``Cmd+Shift+F9``、``Ctrl+Option+3``。
支持配置热更新（reload 后重新注册）。
"""

from __future__ import annotations

import platform
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, Signal

# ---------- 快捷键解析（纯函数，便于测试） ----------

_MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "control",
    "control": "control",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "cmd": "meta",
    "command": "meta",
    "meta": "meta",
    "win": "meta",
    "super": "meta",
    "shift": "shift",
}

_NAMED_KEYS = {
    "SPACE", "TAB", "RETURN", "ENTER", "ESC", "ESCAPE", "BACKSPACE",
    "DELETE", "UP", "DOWN", "LEFT", "RIGHT",
}


def parse_hotkey(text: str) -> tuple[frozenset[str], str] | None:
    """解析 ``Ctrl+Alt+1`` → (frozenset({"control","alt"}), "1")

    返回 None 表示格式非法。
    """
    if not text:
        return None
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods: set[str] = set()
    key = ""
    for part in parts[:-1]:
        norm = _MODIFIER_ALIASES.get(part.lower())
        if norm is None:
            return None
        mods.add(norm)
    key_token = parts[-1].upper()
    if not key_token:
        return None
    if key_token in _NAMED_KEYS:
        pass
    elif len(key_token) == 1 and (key_token.isdigit() or key_token.isalpha()):
        pass
    elif len(key_token) >= 2 and key_token[0] == "F" and key_token[1:].isdigit():
        pass
    else:
        return None
    return frozenset(mods), key_token


# ---------- macOS 键码表 ----------

_MAC_KEYCODES: dict[str, int] = {
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22,
    "7": 26, "8": 28, "9": 25,
    "A": 0, "B": 11, "C": 8, "D": 2, "E": 14, "F": 3, "G": 5, "H": 4,
    "I": 34, "J": 38, "K": 40, "L": 37, "M": 46, "N": 45, "O": 31,
    "P": 35, "Q": 12, "R": 15, "S": 1, "T": 17, "U": 32, "V": 9,
    "W": 13, "X": 7, "Y": 16, "Z": 6,
    "SPACE": 49, "TAB": 48, "RETURN": 36, "ENTER": 76, "ESC": 53,
    "ESCAPE": 53, "BACKSPACE": 51, "DELETE": 117,
    "UP": 126, "DOWN": 125, "LEFT": 123, "RIGHT": 124,
}
for _i in range(1, 20):
    _MAC_KEYCODES[f"F{_i}"] = [122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111,
                               105, 107, 113, 106, 64, 79, 80][_i - 1]

# macOS 修饰键 flag bits（kCGEventFlagMask*）
_MAC_MOD_FLAGS: dict[str, int] = {
    "control": 1 << 18,
    "shift": 1 << 17,
    "alt": 1 << 19,
    "meta": 1 << 20,
}
_MAC_MOD_MASK = 0x1E0000  # shift|control|alt|command

# ---------- Windows 虚拟键码表 ----------

_WIN_VK: dict[str, int] = {
    **{str(n): 0x30 + n for n in range(10)},
    **{chr(c): ord(chr(c)) for c in range(ord("A"), ord("Z") + 1)},
    "SPACE": 0x20, "TAB": 0x09, "RETURN": 0x0D, "ENTER": 0x0D, "ESC": 0x1B,
    "ESCAPE": 0x1B, "BACKSPACE": 0x08, "DELETE": 0x2E,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
}
for _i in range(1, 25):
    _WIN_VK[f"F{_i}"] = 0x70 + (_i - 1)

_WIN_MODS: dict[str, int] = {
    "control": 0x2,  # MOD_CONTROL
    "alt": 0x1,      # MOD_ALT
    "shift": 0x4,    # MOD_SHIFT
    "meta": 0x8,     # MOD_WIN
}

# ---------- macOS 辅助功能权限 ----------

_mac_ax: Any = None


def _mac_permission_ok() -> bool:
    """macOS：检查是否已授予「辅助功能」权限"""
    global _mac_ax
    if platform.system() != "Darwin":
        return True
    try:
        import ctypes
        import ctypes.util

        if _mac_ax is None:
            lib = ctypes.util.find_library("ApplicationServices")
            if not lib:
                return False
            _mac_ax = ctypes.cdll.LoadLibrary(lib)
            _mac_ax.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(_mac_ax.AXIsProcessTrusted())
    except Exception:
        return False


# ---------- macOS CGEventTap 监听 ----------

class _MacHotkeyListener(QObject):
    """Quartz CGEventTap 监听（在独立线程跑 CFRunLoop）"""

    def __init__(self, manager: "GlobalHotkeyManager") -> None:
        super().__init__()
        self._manager = manager
        self._bindings: dict[int, tuple[int, str]] = {}  # keycode -> (flag_mask, action)
        self._thread: Any = None
        self._tap: Any = None
        self._callback: Any = None
        self._started = False

    def _load_cg(self) -> Any:
        import ctypes
        import ctypes.util

        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        return lib, ctypes

    def start(self, mapping: dict[str, str]) -> bool:
        import ctypes
        import threading

        if not _mac_permission_ok():
            logger.warning("全局快捷键需要「辅助功能」权限：系统设置 → 隐私与安全性 → 辅助功能")
            return False
        try:
            cg, ctypes = self._load_cg()
            self._cg = cg

            cg.CGEventTapCreate.argtypes = [
                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p,
            ]
            cg.CGEventTapCreate.restype = ctypes.c_void_p
            cg.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_int32]
            cg.CGEventGetIntegerValueField.restype = ctypes.c_int64
            cg.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            cg.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
            cg.CFRunLoopGetCurrent.restype = ctypes.c_void_p
            cg.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            cg.CFRunLoopRun.restype = None

            self._callback = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                ctypes.c_void_p, ctypes.c_void_p,
            )(self._on_event)

            k_cg_event_key_down = 10
            event_mask = 1 << k_cg_event_key_down
            tap = cg.CGEventTapCreate(1, 0, 0, event_mask, self._callback, None)
            if not tap:
                logger.error("CGEventTapCreate 失败（无法创建全局快捷键监听）")
                return False
            self._tap = tap

            source = cg.CFMachPortCreateRunLoopSource(None, tap, 0)
            if not source:
                logger.error("CFMachPortCreateRunLoopSource 失败")
                return False

            self.reload(mapping)

            self._thread = threading.Thread(target=self._run_loop, args=(source,), daemon=True)
            self._thread.start()
            self._started = True
            logger.info("macOS 全局快捷键监听已启动")
            return True
        except Exception as e:
            logger.error(f"启动 macOS 全局快捷键失败: {e}")
            return False

    def _run_loop(self, source: Any) -> None:
        import ctypes
        import ctypes.util

        try:
            cg = self._cg
            # 用 CFString 指定 kCFRunLoopDefaultMode，避免 NULL mode 的不确定行为
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            cf.CFStringCreateWithCString.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32,
            ]
            cf.CFStringCreateWithCString.restype = ctypes.c_void_p
            mode = cf.CFStringCreateWithCString(None, b"kCFRunLoopDefaultMode", 0x08000100)
            loop = cg.CFRunLoopGetCurrent()
            cg.CFRunLoopAddSource(loop, source, mode)
            cg.CFRunLoopRun()
        except Exception as e:
            logger.error(f"CGEventTap run loop 异常: {e}")

    def reload(self, mapping: dict[str, str]) -> None:
        """重新加载快捷键映射（配置热更新）"""
        self._bindings.clear()
        for action, hotkey in mapping.items():
            parsed = parse_hotkey(hotkey)
            if not parsed:
                logger.warning(f"快捷键格式无效，跳过 {action}: {hotkey!r}")
                continue
            mods, key = parsed
            keycode = _MAC_KEYCODES.get(key)
            if keycode is None:
                logger.warning(f"快捷键不支持的主键，跳过 {action}: {hotkey!r}")
                continue
            flag_mask = 0
            for mod in mods:
                flag_mask |= _MAC_MOD_FLAGS[mod]
            self._bindings[keycode] = (flag_mask, action)
        logger.debug(f"已注册 macOS 快捷键: {list(self._bindings.values())}")

    def _on_event(self, proxy: Any, event_type: int, event: Any, refcon: Any) -> Any:
        """CGEventTap 回调（运行在线程的 CFRunLoop 中）"""
        try:
            if event_type != 10:  # kCGEventKeyDown
                return event
            keycode = int(self._cg.CGEventGetIntegerValueField(event, 9))  # kCGKeyboardEventKeycode
            flags = int(self._cg.CGEventGetIntegerValueField(event, 1))    # kCGEventFlagsField
            binding = self._bindings.get(keycode)
            if binding is None:
                return event
            required, action = binding
            if (flags & _MAC_MOD_MASK) == required:
                self._manager.hotkey_pressed.emit(action)
        except Exception:
            pass
        return event

    def stop(self) -> None:
        self._started = False
        if self._tap and self._cg:
            try:
                self._cg.CGEventTapEnable(self._tap, False)
            except Exception:
                pass


# ---------- Windows RegisterHotKey 监听 ----------

class _WinHotkeyListener(QObject):
    """RegisterHotKey + GetMessageW 消息循环线程"""

    WM_HOTKEY = 0x0312

    def __init__(self, manager: "GlobalHotkeyManager") -> None:
        super().__init__()
        self._manager = manager
        self._thread: Any = None
        self._ids: dict[int, str] = {}  # hotkey id -> action
        self._next_id = 1
        self._registered: list[int] = []
        self._started = False

    def start(self, mapping: dict[str, str]) -> bool:
        import threading

        self.reload(mapping)
        if not self._ids:
            logger.error("Windows 快捷键全部注册失败，全局快捷键不可用")
            return False
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        self._started = True
        logger.info(f"Windows 全局快捷键监听已启动（{len(self._ids)} 个）")
        return True

    def reload(self, mapping: dict[str, str]) -> None:
        """重新注册（配置热更新；单个冲突不影响其余快捷键）"""
        import ctypes

        user32 = ctypes.windll.user32
        # 先注销旧的
        for hid in self._registered:
            try:
                user32.UnregisterHotKey(None, hid)
            except Exception:
                pass
        self._registered.clear()
        self._ids.clear()
        self._next_id = 1

        for action, hotkey in mapping.items():
            parsed = parse_hotkey(hotkey)
            if not parsed:
                logger.warning(f"快捷键格式无效，跳过 {action}: {hotkey!r}")
                continue
            mods, key = parsed
            vk = _WIN_VK.get(key)
            if vk is None:
                logger.warning(f"快捷键不支持的主键，跳过 {action}: {hotkey!r}")
                continue
            mod_flags = 0
            for mod in mods:
                mod_flags |= _WIN_MODS[mod]
            hid = self._next_id
            self._next_id += 1
            ok = user32.RegisterHotKey(None, hid, mod_flags, vk)
            if ok:
                self._ids[hid] = action
                self._registered.append(hid)
                logger.debug(f"已注册 Windows 快捷键: {hotkey} -> {action}")
            else:
                logger.warning(f"快捷键注册失败（可能被占用），跳过 {action}: {hotkey!r}")

    def _message_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        while True:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:
                break
            if msg.message == self.WM_HOTKEY:
                action = self._ids.get(int(msg.wParam))
                if action:
                    self._manager.hotkey_pressed.emit(action)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self) -> None:
        import ctypes

        self._started = False
        try:
            user32 = ctypes.windll.user32
            for hid in self._registered:
                user32.UnregisterHotKey(None, hid)
        except Exception:
            pass
        self._registered.clear()


# ---------- 管理器 ----------

class GlobalHotkeyManager(QObject):
    """全局快捷键管理器（双平台统一入口）"""

    hotkey_pressed = Signal(str)  # 动作名（如 switch_mac）

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: Any = None
        self._started = False
        self._mapping: dict[str, str] = {}

    def set_hotkeys(self, mapping: dict[str, str]) -> None:
        """设置 动作名 → 快捷键文本 映射；已启动时热更新注册"""
        self._mapping = dict(mapping)
        if self._started and self._listener is not None:
            self._listener.reload(self._mapping)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    @property
    def started(self) -> bool:
        return self._started

    @property
    def permission_ok(self) -> bool:
        if platform.system() == "Darwin":
            return _mac_permission_ok()
        return True

    def start(self) -> bool:
        """启动全局快捷键监听"""
        if self._started:
            return True
        system = platform.system()
        if system == "Darwin":
            self._listener = _MacHotkeyListener(self)
        elif system == "Windows":
            self._listener = _WinHotkeyListener(self)
        else:
            logger.warning(f"当前平台不支持全局快捷键: {system}")
            return False
        ok = self._listener.start(self._mapping)
        self._started = ok
        if not ok and system == "Darwin":
            logger.warning("全局快捷键未启动（macOS 需要辅助功能权限，且快捷键可能已被其他应用占用）")
        return ok

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
        self._started = False

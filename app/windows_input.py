"""Win32 low-level input hook and checked SendInput calls."""
from __future__ import annotations

import ctypes as C
import threading
from ctypes import wintypes as W

from app.native_input import EXTENDED_WINDOWS_KEYS, KEY_TO_WIN, WIN_TO_KEY, NativeInput

UPTR = C.c_size_t
PTR = C.c_ssize_t


class KeyboardHook(C.Structure):
    _fields_ = [("vk", W.DWORD), ("scan", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", UPTR)]


class MouseHook(C.Structure):
    _fields_ = [("pt", W.POINT), ("data", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", UPTR)]


class KeyboardInput(C.Structure):
    _fields_ = [("vk", W.WORD), ("scan", W.WORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", UPTR)]


class MouseInput(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("data", W.DWORD),
                ("flags", W.DWORD), ("time", W.DWORD), ("extra", UPTR)]


class InputValue(C.Union):
    _fields_ = [("key", KeyboardInput), ("mouse", MouseInput)]


class Input(C.Structure):
    _fields_ = [("kind", W.DWORD), ("value", InputValue)]


class WindowsInput(NativeInput):
    def __init__(self):
        super().__init__()
        self.win = C.WinDLL("user32")
        self.kernel = C.WinDLL("kernel32")
        self.thread_id = 0
        self.win.SendInput.argtypes = W.UINT, C.POINTER(Input), C.c_int
        self.win.SendInput.restype = W.UINT
        self.win.CallNextHookEx.argtypes = W.HANDLE, C.c_int, W.WPARAM, W.LPARAM
        self.win.CallNextHookEx.restype = PTR
        self.win.UnhookWindowsHookEx.argtypes = (W.HANDLE,)
        self.kernel.GetModuleHandleW.argtypes = (W.LPCWSTR,)
        self.kernel.GetModuleHandleW.restype = W.HMODULE
        self._stop = threading.Event()
        self._hardware_keys: set[int] = set()

    def start(self, callback):
        super().start(callback)
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self.thread_id:
            self.win.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
        if self._thread:
            self._thread.join(1)
        super().stop()

    def _run(self):
        win = self.win
        self.thread_id = self.kernel.GetCurrentThreadId()
        msg = W.MSG()
        win.PeekMessageW(C.byref(msg), None, 0, 0, 0)
        prototype = C.WINFUNCTYPE(PTR, C.c_int, W.WPARAM, W.LPARAM)
        keyboard, mouse = prototype(self._keyboard), prototype(self._mouse)
        win.SetWindowsHookExW.argtypes = C.c_int, prototype, W.HMODULE, W.DWORD
        win.SetWindowsHookExW.restype = W.HANDLE
        app = self.kernel.GetModuleHandleW(None)
        hooks = [win.SetWindowsHookExW(kind, callback, app, 0)
                 for kind, callback in ((13, keyboard), (14, mouse))]
        self.available = all(hooks)
        try:
            while self.available and not self._stop.is_set() and win.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                win.TranslateMessage(C.byref(msg))
                win.DispatchMessageW(C.byref(msg))
        finally:
            self.available = False
            self.thread_id = 0
            self._hardware_keys.clear()
            for hook in hooks:
                if hook:
                    win.UnhookWindowsHookEx(hook)

    def _keyboard(self, code, msg, arg):
        if code == 0 and self.available:
            data = KeyboardHook.from_address(arg)
            key = WIN_TO_KEY.get(data.vk)
            if key is not None and not (data.flags & 0x10):
                down = msg in (0x100, 0x104)
                self._hardware_keys.add(key) if down else self._hardware_keys.discard(key)
                escape = (self._capturing and key == 53 and bool(self._hardware_keys & {59, 62})
                          and bool(self._hardware_keys & {58, 61}))
                if self._key_event(key, down, escape):
                    return 1
        return self.win.CallNextHookEx(None, code, msg, arg)

    def _mouse(self, code, msg, arg):
        event = None
        if code == 0 and self.available:
            data = MouseHook.from_address(arg)
            if not (data.flags & 1):
                if msg == 0x200:
                    previous = self._pointer
                    if self._capturing:
                        previous = self.pointer()
                    self._pointer = (data.pt.x, data.pt.y)
                    event = {"kind": "move", "x": data.pt.x, "y": data.pt.y,
                             "dx": data.pt.x - previous[0], "dy": data.pt.y - previous[1]}
                elif msg in (0x20A, 0x20E):
                    delta = C.c_short(data.data >> 16).value / 120
                    event = {"kind": "scroll", "dx": delta if msg == 0x20E else 0,
                             "dy": delta if msg == 0x20A else 0}
                elif 0x201 <= msg <= 0x208 and msg not in (0x203, 0x206):
                    button = ("left" if msg <= 0x202 else "right" if msg <= 0x205 else "middle")
                    event = {"kind": "button", "code": button, "down": msg in (0x201, 0x204, 0x207)}
        if event and self._callback(event):
            return 1
        return self.win.CallNextHookEx(None, code, msg, arg)

    def pointer(self):
        pt = W.POINT()
        self.win.GetCursorPos(C.byref(pt))
        return pt.x, pt.y

    def move_cursor(self, x, y):
        self.win.SetCursorPos(x, y)

    def inject(self, event):
        kind = event["kind"]
        entries = []
        if kind == "key":
            vk = KEY_TO_WIN.get(event["code"])
            if vk is None:
                return True
            flags = (0 if event["down"] else 2) | (1 if vk in EXTENDED_WINDOWS_KEYS else 0)
            entries.append(Input(1, InputValue(key=KeyboardInput(vk, 0, flags, 0, 0))))
        elif kind == "move":
            entries.append(Input(0, InputValue(mouse=MouseInput(int(event["dx"]), int(event["dy"]), 0, 1, 0, 0))))
        elif kind == "button":
            flags = {"left": 2, "right": 8, "middle": 32}[event["code"]] << (not event["down"])
            entries.append(Input(0, InputValue(mouse=MouseInput(0, 0, 0, flags, 0, 0))))
        elif kind == "scroll":
            for axis, flags in (("dy", 0x800), ("dx", 0x1000)):
                if event[axis]:
                    data = int(event[axis] * 120) & 0xFFFFFFFF
                    entries.append(Input(0, InputValue(mouse=MouseInput(0, 0, data, flags, 0, 0))))
        if not entries:
            return True
        values = (Input * len(entries))(*entries)
        return self.win.SendInput(len(values), values, C.sizeof(Input)) == len(values)

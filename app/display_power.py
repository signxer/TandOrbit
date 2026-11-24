"""Display power commands and observations for the current interactive session."""
from __future__ import annotations

import asyncio
import ctypes as C
import sys
import uuid

from app.transition import TransitionError

DISPLAY_STATE = uuid.UUID("2b84c20e-ad23-4ddf-93db-05ffbd7efca5").bytes_le


class DisplayPower:
    def __init__(self) -> None:
        self.windows_awake: bool | None = None
        self._windows_registration = None
        self._filter = None
        self.session_active = True

    def install(self, app, window) -> None:
        if sys.platform != "win32":
            return
        from ctypes import wintypes as W
        from PySide6.QtCore import QAbstractNativeEventFilter

        owner = self

        class Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):
                msg = W.MSG.from_address(int(message))
                if msg.message == 0x0218:  # WM_POWERBROADCAST
                    if msg.wParam == 0x8013 and msg.lParam:
                        data = C.string_at(msg.lParam, 24)
                        if data[:16] == DISPLAY_STATE and int.from_bytes(data[16:20], "little") == 4:
                            owner.windows_awake = int.from_bytes(data[20:24], "little") != 0
                    elif msg.wParam == 4:
                        owner.session_active = False
                    elif msg.wParam in (7, 18):
                        owner.session_active = True
                elif msg.message == 0x02B1:  # WM_WTSSESSION_CHANGE
                    if msg.wParam in (2, 4, 6, 7):
                        owner.session_active = False
                    elif msg.wParam in (1, 3, 5, 8):
                        owner.session_active = True
                return False, 0

        hwnd = W.HWND(int(window.winId()))
        self._filter = Filter()
        app.installNativeEventFilter(self._filter)
        api = C.windll.user32
        api.RegisterPowerSettingNotification.restype = C.c_void_p
        api.RegisterPowerSettingNotification.argtypes = (W.HANDLE, C.c_void_p, W.DWORD)
        guid = C.create_string_buffer(DISPLAY_STATE)
        self._windows_registration = api.RegisterPowerSettingNotification(hwnd, guid, 0)
        C.windll.wtsapi32.WTSRegisterSessionNotification(hwnd, 0)
        self._hwnd = hwnd

    def close(self, app) -> None:
        if self._filter is not None:
            app.removeNativeEventFilter(self._filter)
            C.windll.wtsapi32.WTSUnRegisterSessionNotification(self._hwnd)
            if self._windows_registration:
                C.windll.user32.UnregisterPowerSettingNotification(C.c_void_p(self._windows_registration))
            self._filter = None

    async def read(self) -> bool | None:
        if sys.platform == "win32":
            return self.windows_awake
        if sys.platform == "darwin":
            from plugins.native_display.mac import enumerate_displays, quartz
            cg = quartz()
            current = enumerate_displays()
            return any(not cg.CGDisplayIsAsleep(item.id) for item in current) if current else None
        return None

    async def set(self, awake: bool) -> None:
        if await self.read() is awake:
            return
        if sys.platform == "darwin":
            args = ("/usr/bin/caffeinate", "-u", "-t", "1") if awake else (
                "/usr/bin/pmset", "displaysleepnow")
            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                status = await asyncio.wait_for(process.wait(), 5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                raise
            if status:
                raise TransitionError(f"系统显示器电源命令失败（{status}）")
        elif sys.platform == "win32":
            await asyncio.to_thread(self._windows_set, awake)
        else:
            raise TransitionError("本机系统未提供显示器电源控制")

    @staticmethod
    def _windows_set(awake: bool) -> None:
        from ctypes import wintypes as W

        api = C.windll.user32
        send = api.SendMessageTimeoutW
        send.argtypes = (W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.c_void_p)
        send.restype = C.c_ssize_t
        result = C.c_size_t()
        if not send(W.HWND(0xFFFF), 0x0112, 0xF170, -1 if awake else 2, 2, 500,
                    C.byref(result)):
            raise TransitionError("Windows 显示器电源命令超时")

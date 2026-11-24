"""Opt-in Windows monitor brightness controls using Dxva2."""
import ctypes as C
from ctypes import wintypes as W


class MonitorInfo(C.Structure):
    _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT),
                ("flags", W.DWORD), ("device", W.WCHAR * 32)]


class PhysicalMonitor(C.Structure):
    _fields_ = [("handle", W.HANDLE), ("description", W.WCHAR * 128)]


def brightness(display_id, value=None):
    """Return current brightness as a percentage, or None if the monitor cannot confirm it."""
    user = C.WinDLL("user32")
    dxva = C.WinDLL("dxva2")
    prototype = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
    matches = []

    def collect(handle, _dc, _rect, _data):
        info = MonitorInfo()
        info.size = C.sizeof(info)
        if user.GetMonitorInfoW(W.HANDLE(handle), C.byref(info)) and info.device.upper().endswith(
            f"\\DISPLAY{display_id}"
        ):
            matches.append(handle)
        return True

    callback = prototype(collect)
    user.EnumDisplayMonitors(None, None, callback, 0)
    if len(matches) != 1:
        return None
    logical = W.HANDLE(matches[0])
    count = W.DWORD()
    if not dxva.GetNumberOfPhysicalMonitorsFromHMONITOR(logical, C.byref(count)) or count.value != 1:
        return None
    monitors = (PhysicalMonitor * count.value)()
    if not dxva.GetPhysicalMonitorsFromHMONITOR(logical, count, monitors):
        return None
    try:
        handle = W.HANDLE(monitors[0].handle)
        low, current, high = W.DWORD(), W.DWORD(), W.DWORD()
        if not dxva.GetMonitorBrightness(handle, C.byref(low), C.byref(current), C.byref(high)):
            return None
        step = high.value - low.value
        if not step:
            return None
        if value is not None:
            level = low.value + round(step * value / 100)
            if not dxva.SetMonitorBrightness(handle, level) or not dxva.GetMonitorBrightness(
                handle, C.byref(low), C.byref(current), C.byref(high)
            ):
                return None
        return round((current.value - low.value) * 100 / step)
    finally:
        dxva.DestroyPhysicalMonitors(count, monitors)

"""Quartz inventory with optional BetterDisplay output disconnect support."""
from __future__ import annotations

import ctypes as C

from app.enums import PluginStatus
from app.models import DisplayInfo
from plugins.betterdisplay.plugin import BetterDisplayPlugin


def quartz():
    return C.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


def _identity(color, cf, display):
    uuid = color.CGDisplayCreateUUIDFromDisplayID(display)
    if not uuid:
        return ""
    try:
        text = cf.CFUUIDCreateString(None, uuid)
        if not text:
            return ""
        try:
            buffer = C.create_string_buffer(64)
            if cf.CFStringGetCString(text, buffer, len(buffer), 0x08000100):
                return buffer.value.decode().lower()
            return ""
        finally:
            cf.CFRelease(text)
    finally:
        cf.CFRelease(uuid)


def enumerate_displays():
    cg = quartz()
    cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    color = C.CDLL("/System/Library/Frameworks/ColorSync.framework/ColorSync")
    color.CGDisplayCreateUUIDFromDisplayID.argtypes = (C.c_uint32,)
    color.CGDisplayCreateUUIDFromDisplayID.restype = C.c_void_p
    cf.CFUUIDCreateString.argtypes = (C.c_void_p, C.c_void_p)
    cf.CFUUIDCreateString.restype = C.c_void_p
    cf.CFStringGetCString.argtypes = (C.c_void_p, C.c_void_p, C.c_long, C.c_uint32)
    cf.CFRelease.argtypes = (C.c_void_p,)
    values = (C.c_uint32 * 64)()
    count = C.c_uint32()
    if cg.CGGetOnlineDisplayList(len(values), values, C.byref(count)):
        raise OSError("CGGetOnlineDisplayList")
    cg.CGDisplayPixelsWide.restype = C.c_size_t
    cg.CGDisplayPixelsHigh.restype = C.c_size_t
    result = []
    for display in list(values)[:count.value]:
        vendor = cg.CGDisplayVendorNumber(display)
        model = cg.CGDisplayModelNumber(display)
        serial = cg.CGDisplaySerialNumber(display)
        identity = _identity(color, cf, display) or f"quartz:{vendor:04x}:{model:04x}:{serial & 0xffffffff:08x}"
        result.append(DisplayInfo(
            id=display, name=f"显示器 {vendor:04X}/{model:04X}",
            device_id=identity, width=cg.CGDisplayPixelsWide(display),
            height=cg.CGDisplayPixelsHigh(display), is_primary=bool(cg.CGDisplayIsMain(display)),
            is_enabled=True,
        ))
    return result


class MacDisplay(BetterDisplayPlugin):
    can_change_outputs = False

    async def initialize(self):
        self.can_change_outputs = await super().initialize() and await super().health_check()
        try:
            enumerate_displays()
        except OSError as exc:
            self._last_error = str(exc)
            self._set_status(PluginStatus.ERROR)
            return False
        self._set_status(PluginStatus.INITIALIZED)
        return True

    async def health_check(self):
        try:
            return bool(enumerate_displays())
        except OSError:
            return False

    async def list_displays(self):
        native = enumerate_displays()
        if self.can_change_outputs:
            compatible = await super().list_displays()
            # The compatibility provider knows disconnected targets and installation-specific tag IDs.
            # Prefer its identity and state where a matching Quartz identity is available.
            if compatible:
                by_id = {item.id: item for item in native}
                by_uuid = {item.device_id: item for item in native}
                for item in compatible:
                    try:
                        observed = by_id.get(int(item.monitor_id))
                    except ValueError:
                        observed = None
                    observed = observed or by_uuid.get(item.device_id.lower())
                    if observed:
                        item.device_id = observed.device_id
                        item.width, item.height = observed.width, observed.height
                        item.is_enabled = item.is_enabled and observed.is_enabled
                    elif not item.device_id:
                        item.device_id = f"betterdisplay:{item.id}"
                return compatible
            raise OSError("BetterDisplay 无法读取已绑定的输出")
        return native

    async def is_mirrored(self):
        cg = quartz()
        return any(cg.CGDisplayIsInMirrorSet(item.id) for item in enumerate_displays())

    async def set_extend(self):
        cg = quartz()
        config = C.c_void_p()
        if cg.CGBeginDisplayConfiguration(C.byref(config)):
            return False
        for item in enumerate_displays():
            if cg.CGDisplayMirrorsDisplay(item.id) and cg.CGConfigureDisplayMirrorOfDisplay(
                config, C.c_uint32(item.id), C.c_uint32(0)
            ):
                cg.CGCancelDisplayConfiguration(config)
                return False
        return cg.CGCompleteDisplayConfiguration(config, 0) == 0

    async def capture_arrangement(self):
        class Rect(C.Structure):
            _fields_ = [("x", C.c_double), ("y", C.c_double),
                        ("width", C.c_double), ("height", C.c_double)]

        cg = quartz()
        cg.CGDisplayBounds.argtypes = (C.c_uint32,)
        cg.CGDisplayBounds.restype = Rect
        cg.CGDisplayMirrorsDisplay.argtypes = (C.c_uint32,)
        cg.CGDisplayMirrorsDisplay.restype = C.c_uint32
        displays = {item.id: item.device_id for item in enumerate_displays()}
        snapshot = []
        for display, identity in displays.items():
            box = cg.CGDisplayBounds(display)
            snapshot.append({"id": identity, "x": int(box.x), "y": int(box.y),
                             "mirror": displays.get(cg.CGDisplayMirrorsDisplay(display))})
        return snapshot

    async def apply_arrangement(self, snapshot):
        from app.transition import TransitionError

        current = {display.device_id: display.id for display in enumerate_displays()}
        if any(item["id"] not in current for item in snapshot):
            raise TransitionError("macOS 布局内的显示器已更换或断开")
        cg = quartz()
        config = C.c_void_p()
        if cg.CGBeginDisplayConfiguration(C.byref(config)):
            raise TransitionError("无法开始恢复 macOS 布局")
        try:
            for item in snapshot:
                display = C.c_uint32(current[item["id"]])
                master = C.c_uint32(current[item["mirror"]] if item["mirror"] else 0)
                if cg.CGConfigureDisplayMirrorOfDisplay(config, display, master):
                    raise TransitionError("无法恢复镜像布局")
                if not master.value and cg.CGConfigureDisplayOrigin(config, display, item["x"], item["y"]):
                    raise TransitionError("无法恢复显示器位置")
        except Exception:
            cg.CGCancelDisplayConfiguration(config)
            raise
        if cg.CGCompleteDisplayConfiguration(config, 0):
            raise TransitionError("macOS 拒绝恢复显示布局")

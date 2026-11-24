"""Windows Connecting and Configuring Displays backend."""
from __future__ import annotations

import asyncio
import base64
import ctypes as C
import re
from ctypes import wintypes as W

from app.enums import PluginStatus
from app.models import DisplayInfo
from app.plugin_base import Plugin

U32 = C.c_uint32
I32 = C.c_int32
INVALID = 0xFFFFFFFF
ACTIVE = 1
VALIDATE = 0x40
APPLY = 0x80
SUPPLIED = 0x20
ALLOW_CHANGES = 0x400


class Luid(C.Structure):
    _fields_ = [("low", U32), ("high", I32)]


class Source(C.Structure):
    _fields_ = [("adapter", Luid), ("id", U32), ("mode", U32), ("status", U32)]


class Ratio(C.Structure):
    _fields_ = [("numerator", U32), ("denominator", U32)]


class Target(C.Structure):
    _fields_ = [
        ("adapter", Luid), ("id", U32), ("mode", U32), ("technology", I32),
        ("rotation", I32), ("scaling", I32), ("refresh", Ratio),
        ("scanline", I32), ("available", I32), ("status", U32),
    ]


class DisplayPath(C.Structure):
    _fields_ = [("source", Source), ("target", Target), ("flags", U32)]


class SourceMode(C.Structure):
    _fields_ = [("width", U32), ("height", U32), ("format", U32), ("x", I32), ("y", I32)]


class ModeData(C.Union):
    _fields_ = [("signal", C.c_uint64 * 6), ("source", SourceMode)]


class DisplayMode(C.Structure):
    _fields_ = [("kind", U32), ("id", U32), ("adapter", Luid), ("value", ModeData)]


class Header(C.Structure):
    _fields_ = [("kind", U32), ("size", U32), ("adapter", Luid), ("id", U32)]


class TargetName(C.Structure):
    _fields_ = [
        ("header", Header), ("flags", U32), ("technology", I32), ("vendor", C.c_uint16),
        ("product", C.c_uint16), ("connector", U32), ("name", W.WCHAR * 64),
        ("device_path", W.WCHAR * 128),
    ]


class SourceName(C.Structure):
    _fields_ = [("header", Header), ("name", W.WCHAR * 32)]


def _key(endpoint):
    return endpoint.adapter.high, endpoint.adapter.low, endpoint.id


class WindowsDisplay(Plugin):
    def __init__(self, event_bus):
        super().__init__("multimonitortool", event_bus)
        self._api = None
        self._last_error = ""

    @property
    def last_error(self):
        return self._last_error

    async def initialize(self):
        try:
            self._api = C.WinDLL("user32")
            self._api.GetDisplayConfigBufferSizes.argtypes = (U32, C.POINTER(U32), C.POINTER(U32))
            self._api.QueryDisplayConfig.argtypes = (
                U32, C.POINTER(U32), C.POINTER(DisplayPath), C.POINTER(U32),
                C.POINTER(DisplayMode), C.c_void_p,
            )
            self._api.SetDisplayConfig.argtypes = (
                U32, C.POINTER(DisplayPath), U32, C.POINTER(DisplayMode), U32,
            )
            self._api.DisplayConfigGetDeviceInfo.argtypes = (C.POINTER(Header),)
            await asyncio.to_thread(self._query, 2)
        except (OSError, AttributeError) as exc:
            self._last_error = str(exc)
            self._set_status(PluginStatus.ERROR)
            return False
        self._set_status(PluginStatus.INITIALIZED)
        return True

    async def enable(self):
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self):
        self._set_status(PluginStatus.DISABLED)
        return True

    async def shutdown(self):
        await self.disable()

    async def health_check(self):
        return self._api is not None and self.status != PluginStatus.ERROR

    def _query(self, flags):
        for _ in range(5):
            paths, modes = U32(), U32()
            result = self._api.GetDisplayConfigBufferSizes(flags, C.byref(paths), C.byref(modes))
            if result != 0:
                raise OSError(result, "GetDisplayConfigBufferSizes")
            path_buffer = (DisplayPath * paths.value)()
            mode_buffer = (DisplayMode * modes.value)()
            result = self._api.QueryDisplayConfig(
                flags, C.byref(paths), path_buffer, C.byref(modes), mode_buffer, None)
            if result == 0:
                return list(path_buffer)[:paths.value], list(mode_buffer)[:modes.value]
            if result != 122:
                raise OSError(result, "QueryDisplayConfig")
        raise OSError("显示拓扑正在变化")

    def _name(self, structure, kind, endpoint):
        value = structure()
        value.header = Header(kind, C.sizeof(value), endpoint.adapter, endpoint.id)
        self._api.DisplayConfigGetDeviceInfo(C.byref(value.header))
        return value

    def _inventory(self):
        paths, modes = self._query(1)
        targets = {}
        reserved = set()
        for path in paths:
            target_key = _key(path.target)
            if target_key in targets:
                continue
            name = self._name(TargetName, 2, path.target)
            if not name.device_path and not (path.flags & ACTIVE or path.target.available):
                continue
            source = self._name(SourceName, 1, path.source)
            match = re.search(r"DISPLAY(\d+)$", source.name) if path.flags & ACTIVE else None
            number = int(match[1]) if match and int(match[1]) not in reserved else None
            if number is not None:
                reserved.add(number)
            targets[target_key] = (path, name, number)
        result = []
        for key, (path, name, number) in targets.items():
            if number is None:
                inactive_names = {int(match[1]) for alternative in paths
                                  if _key(alternative.target) == key
                                  if (match := re.search(r"DISPLAY(\d+)$", self._name(
                                      SourceName, 1, alternative.source).name))}
                remaining = inactive_names - reserved
                number = remaining.pop() if len(remaining) == 1 else 1000 + len(result)
                while number in reserved:
                    number += 1
                reserved.add(number)
            source_mode = modes[path.source.mode].value.source if path.source.mode < len(modes) else None
            result.append((key, DisplayInfo(
                id=number, name=name.name or f"DISPLAY{number}", device_id=name.device_path,
                monitor_id=name.device_path,
                width=source_mode.width if source_mode else 0,
                height=source_mode.height if source_mode else 0,
                is_primary=bool(source_mode and source_mode.x == 0 and source_mode.y == 0),
                is_enabled=bool(path.flags & ACTIVE),
            )))
        return result, paths, modes

    async def list_displays(self):
        if not self._api:
            return []
        result, _, _ = await asyncio.to_thread(self._inventory)
        return [display for _, display in result]

    def _set(self, paths, modes, flags=SUPPLIED):
        path_buffer = (DisplayPath * len(paths))(*paths)
        mode_buffer = (DisplayMode * len(modes))(*modes)
        for action in (VALIDATE, APPLY):
            status = self._api.SetDisplayConfig(
                len(paths), path_buffer, len(modes), mode_buffer, flags | action)
            if status:
                raise OSError(status, "SetDisplayConfig")

    def _change(self, display_id, enabled):
        inventory, paths, modes = self._inventory()
        key = next((key for key, display in inventory if display.id == display_id), None)
        if key is None:
            return False
        active = [path for path in paths if path.flags & ACTIVE]
        selected = next((path for path in active if _key(path.target) == key), None)
        if bool(selected) == enabled:
            return True
        if enabled:
            sources = {_key(path.source) for path in active}
            selected = next((path for path in paths if _key(path.target) == key
                             and path.target.available and _key(path.source) not in sources), None)
            if not selected:
                return False
            selected.flags |= ACTIVE
            selected.source.mode = selected.target.mode = INVALID
            active.append(selected)
        else:
            active.remove(selected)
            if not active:
                return False
        self._set(active, modes, SUPPLIED | ALLOW_CHANGES)
        return True

    async def enable_display(self, display_id):
        return await asyncio.to_thread(self._change, display_id, True)

    async def disable_display(self, display_id):
        return await asyncio.to_thread(self._change, display_id, False)

    async def is_mirrored(self):
        paths, _ = await asyncio.to_thread(self._query, 2)
        return len({_key(path.source) for path in paths}) != len(paths)

    async def set_extend(self):
        def extend():
            status = self._api.SetDisplayConfig(0, None, 0, None, 4 | APPLY)
            if status:
                raise OSError(status, "SetDisplayConfig extend")
            return True
        return await asyncio.to_thread(extend)

    async def capture_topology(self):
        paths, modes = await asyncio.to_thread(self._query, 2)
        return {
            "paths": [base64.b64encode(bytes(path)).decode() for path in paths],
            "modes": [base64.b64encode(bytes(mode)).decode() for mode in modes],
        }

    async def apply_topology(self, snapshot):
        paths = [DisplayPath.from_buffer_copy(base64.b64decode(value)) for value in snapshot["paths"]]
        modes = [DisplayMode.from_buffer_copy(base64.b64decode(value)) for value in snapshot["modes"]]
        await asyncio.to_thread(self._set, paths, modes)

    async def brightness(self, display_id, amount=None):
        from plugins.native_display.brightness import brightness
        return await asyncio.to_thread(brightness, display_id, amount)

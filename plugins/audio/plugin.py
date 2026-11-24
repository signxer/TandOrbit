"""Core Audio and MMDevice output enumeration and verified default selection."""
from __future__ import annotations

import asyncio
import ctypes as C
import platform
import uuid
from contextlib import ExitStack, contextmanager

from loguru import logger

from app.enums import PluginStatus
from app.plugin_base import Plugin


class AudioPlugin(Plugin):
    def __init__(self, event_bus, config=None):
        super().__init__("audio", event_bus, config)
        self._backend = None

    async def initialize(self):
        try:
            self._backend = CoreAudio() if platform.system() == "Darwin" else WindowsAudio()
            await self.list_endpoints()
        except (AttributeError, OSError) as exc:
            self._init_error = str(exc)
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
        return bool(await self.list_endpoints())

    async def list_endpoints(self):
        if self._backend is None:
            return []
        try:
            return await asyncio.to_thread(self._backend.list)
        except OSError as exc:
            logger.warning(f"音频设备读取失败：{exc}")
            return []

    async def list_devices(self):
        return [device["name"] for device in await self.list_endpoints()]

    async def get_current_device(self):
        devices = await self.list_endpoints()
        return next((device["name"] for device in devices if device["default"]), "")

    async def set_device(self, name_or_id):
        devices = await self.list_endpoints()
        match = [device for device in devices if name_or_id == device["id"]]
        if not match:
            match = [device for device in devices if name_or_id == device["name"]]
        if len(match) != 1:
            return False
        if match[0]["default"]:
            return True
        try:
            await asyncio.to_thread(self._backend.select, match[0]["id"])
            return any(device["default"] and device["id"] == match[0]["id"]
                       for device in await self.list_endpoints())
        except (AttributeError, OSError) as exc:
            logger.warning(f"系统音频输出修改失败：{exc}")
            return False


def _fourcc(value):
    return int.from_bytes(value.encode("ascii"), "big")


class Address(C.Structure):
    _fields_ = [("selector", C.c_uint32), ("scope", C.c_uint32), ("element", C.c_uint32)]


class CoreAudio:
    def __init__(self):
        self.ca = C.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        data = (C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p)
        self.ca.AudioObjectGetPropertyDataSize.argtypes = (*data, C.POINTER(C.c_uint32))
        self.ca.AudioObjectGetPropertyData.argtypes = (*data, C.POINTER(C.c_uint32), C.c_void_p)
        self.ca.AudioObjectSetPropertyData.argtypes = (*data, C.c_uint32, C.c_void_p)
        self.cf.CFStringGetCString.argtypes = (C.c_void_p, C.c_void_p, C.c_long, C.c_uint32)
        self.cf.CFStringGetCString.restype = C.c_bool
        self.cf.CFRelease.argtypes = (C.c_void_p,)

    @staticmethod
    def _address(key, scope):
        return Address(_fourcc(key), _fourcc(scope), 0)

    def _size(self, device, key, scope="glob"):
        address = self._address(key, scope)
        size = C.c_uint32()
        if self.ca.AudioObjectGetPropertyDataSize(device, C.byref(address), 0, None, C.byref(size)):
            return 0
        return size.value

    def _read(self, device, key, value, scope="glob"):
        size = C.c_uint32(C.sizeof(value))
        address = self._address(key, scope)
        status = self.ca.AudioObjectGetPropertyData(
            device, C.byref(address), 0, None, C.byref(size), C.byref(value))
        if status:
            raise OSError(status, key)
        return value

    def _string(self, device, key):
        string = self._read(device, key, C.c_void_p())
        data = C.create_string_buffer(2048)
        if not string:
            return ""
        try:
            if self.cf.CFStringGetCString(string, data, len(data), 0x08000100):
                return data.value.decode()
            return ""
        finally:
            self.cf.CFRelease(string)

    def _outputs(self):
        size = self._size(1, "dev#")
        devices = self._read(1, "dev#", (C.c_uint32 * (size // 4))()) if size else []
        for device in devices:
            if self._size(device, "stm#", "outp"):
                yield device, self._string(device, "uid ")

    def list(self):
        default = self._read(1, "dOut", C.c_uint32()).value
        return [{"id": uid, "name": self._string(device, "lnam"), "default": device == default}
                for device, uid in self._outputs()]

    def select(self, uid):
        device = next((device for device, identifier in self._outputs() if identifier == uid), None)
        if device is None:
            raise OSError("所选音频输出已离线")
        address = self._address("dOut", "glob")
        result = self.ca.AudioObjectSetPropertyData(
            1, C.byref(address), 0, None, 4, C.byref(C.c_uint32(device)))
        if result:
            raise OSError(result, "AudioObjectSetPropertyData")


class PropertyKey(C.Structure):
    _fields_ = [("format_id", C.c_ubyte * 16), ("id", C.c_uint32)]


class PropertyData(C.Union):
    _fields_ = [("size", C.c_void_p * 2), ("text", C.c_wchar_p)]


class Variant(C.Structure):
    _fields_ = [("type", C.c_ushort), ("reserved", C.c_ushort * 3), ("data", PropertyData)]


class WindowsAudio:
    ENUMERATOR = ("bcde0395-e52f-467c-8e3d-c4579291692e", "a95664d2-9614-4f35-a746-de8db63617e6")
    POLICY = ("870af99c-171d-4f9e-af0d-e63df40c2bc9", "f8679f50-850a-41cf-9c72-430f290290c8")

    def __init__(self):
        self.ole = C.WinDLL("ole32")
        self.ole.CoTaskMemFree.argtypes = (C.c_void_p,)
        self.ole.CoInitializeEx.argtypes = (C.c_void_p, C.c_uint32)
        self.ole.CoCreateInstance.argtypes = (
            C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p, C.POINTER(C.c_void_p))

    @staticmethod
    def _check(status):
        if status < 0:
            raise OSError(hex(status & 0xffffffff))

    @staticmethod
    def _method(obj, index, *args, result=C.c_int32):
        methods = C.cast(obj, C.POINTER(C.POINTER(C.c_void_p))).contents
        return C.WINFUNCTYPE(result, C.c_void_p, *args)(methods[index])

    @contextmanager
    def _com(self):
        self._check(self.ole.CoInitializeEx(None, 0))
        try:
            yield
        finally:
            self.ole.CoUninitialize()

    def _create(self, ids):
        obj = C.c_void_p()
        cls, interface = (C.create_string_buffer(uuid.UUID(value).bytes_le) for value in ids)
        self._check(self.ole.CoCreateInstance(cls, None, 1, interface, C.byref(obj)))
        return obj

    def _release(self, obj):
        if obj:
            self._method(obj, 2, result=C.c_uint32)(obj)

    def _device_id(self, device):
        value = C.c_void_p()
        self._check(self._method(device, 5, C.POINTER(C.c_void_p))(device, C.byref(value)))
        try:
            return C.wstring_at(value)
        finally:
            self.ole.CoTaskMemFree(value)

    def _device_name(self, device):
        store, value = C.c_void_p(), Variant()
        self._check(self._method(device, 4, C.c_uint32, C.POINTER(C.c_void_p))(device, 0, C.byref(store)))
        try:
            key = PropertyKey((C.c_ubyte * 16).from_buffer_copy(
                uuid.UUID("a45c254e-df1c-4efd-8020-67d146a850e0").bytes_le), 14)
            self._check(self._method(store, 5, C.POINTER(PropertyKey), C.POINTER(Variant))(
                store, C.byref(key), C.byref(value)))
            return value.data.text if value.type == 31 else ""
        finally:
            self.ole.PropVariantClear(C.byref(value))
            self._release(store)

    def list(self):
        with self._com(), ExitStack() as stack:
            enum = self._create(self.ENUMERATOR)
            stack.callback(self._release, enum)
            default, collection = C.c_void_p(), C.c_void_p()
            get_default = self._method(enum, 4, C.c_int32, C.c_int32, C.POINTER(C.c_void_p))
            default_id = ""
            if get_default(enum, 0, 0, C.byref(default)) >= 0:
                stack.callback(self._release, default)
                default_id = self._device_id(default)
            enumerate_devices = self._method(enum, 3, C.c_int32, C.c_uint32, C.POINTER(C.c_void_p))
            self._check(enumerate_devices(enum, 0, 1, C.byref(collection)))
            stack.callback(self._release, collection)
            count = C.c_uint32()
            self._check(self._method(collection, 3, C.POINTER(C.c_uint32))(collection, C.byref(count)))
            get_device = self._method(collection, 4, C.c_uint32, C.POINTER(C.c_void_p))
            items = []
            for index in range(count.value):
                device = C.c_void_p()
                self._check(get_device(collection, index, C.byref(device)))
                try:
                    identifier = self._device_id(device)
                    items.append({"id": identifier, "name": self._device_name(device) or identifier,
                                  "default": identifier == default_id})
                finally:
                    self._release(device)
            return items

    def select(self, uid):
        with self._com():
            policy = self._create(self.POLICY)
            try:
                set_default = self._method(policy, 13, C.c_wchar_p, C.c_int32)
                self._check(set_default(policy, uid, 0))
            finally:
                self._release(policy)

"""Physical desktop input for the paired sharing session."""
from __future__ import annotations

import ctypes as C
import sys
import threading

# Canonical physical key positions use the Quartz ANSI virtual key codes.
KEYS = {
    **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", (0, 11, 8, 2, 14, 3, 5, 4, 34, 38, 40, 37, 46,
                                               45, 31, 35, 12, 15, 1, 17, 32, 9, 13, 7, 16, 6))),
    **dict(zip("0123456789", (29, 18, 19, 20, 21, 23, 22, 26, 28, 25))),
    0x1B: 53, 0x0D: 36, 0x09: 48, 0x20: 49, 0x08: 51, 0x2E: 117, 0x2D: 114,
    0x25: 123, 0x26: 126, 0x27: 124, 0x28: 125, 0x24: 115, 0x23: 119, 0x21: 116, 0x22: 121,
    0xA0: 56, 0xA1: 60, 0xA2: 59, 0xA3: 62, 0xA4: 58, 0xA5: 61, 0x5B: 55, 0x5C: 54,
    0x14: 57, 0xBA: 41, 0xBB: 24, 0xBC: 43, 0xBD: 27, 0xBE: 47, 0xBF: 44, 0xC0: 50,
    0xDB: 33, 0xDC: 42, 0xDD: 30, 0xDE: 39,
    **dict(zip(range(0x70, 0x7C), (122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111))),
}
WIN_TO_KEY = {ord(key) if isinstance(key, str) else key: value for key, value in KEYS.items()}
KEY_TO_WIN = {value: key for key, value in WIN_TO_KEY.items()}
EXTENDED_WINDOWS_KEYS = {0x2D, 0x2E, 0xA3, 0xA5, 0x5B, 0x5C, *range(0x21, 0x29)}


class NativeInput:
    available = False

    def __init__(self):
        self._thread = None
        self._focus = True
        self._callback = None
        self._held = set()
        self._pointer = (0, 0)
        self._capturing = False
        self._swallow_escape_up = False
        self._desktop_size = (0, 0, 1, 1)

    def geometry(self, bounds):
        self._desktop_size = bounds

    def session_active(self):
        return self._focus

    def at_edge(self, event, edge):
        x, y = event["x"], event["y"]
        left, top, width, height = self._desktop_size
        if edge == "left" and x <= left + 1 and event["dx"] < 0:
            return min(1, max(0, (y - top) / height))
        if edge == "right" and x >= left + width - 2 and event["dx"] > 0:
            return min(1, max(0, (y - top) / height))
        if edge == "top" and y <= top + 1 and event["dy"] < 0:
            return min(1, max(0, (x - left) / width))
        if edge == "bottom" and y >= top + height - 2 and event["dy"] > 0:
            return min(1, max(0, (x - left) / width))
        return None

    def enter(self, edge, fraction):
        left, top, width, height = self._desktop_size
        x = {"left": left + 4, "right": left + width - 5}.get(edge, left + fraction * (width - 1))
        y = {"top": top + 4, "bottom": top + height - 5}.get(edge, top + fraction * (height - 1))
        self.move_cursor(int(x), int(y))

    def return_edge(self, event, edge):
        x, y = self.pointer()
        return self.at_edge({**event, "x": x, "y": y}, edge) is not None

    def capture(self, enabled):
        self._capturing = enabled
        if enabled:
            self._pointer = self.pointer()

    def _key_event(self, code, down, escape):
        if code == 53 and ((escape and down) or self._swallow_escape_up):
            if not down:
                self._swallow_escape_up = False
            elif escape:
                self._swallow_escape_up = True
                self._callback({"kind": "escape"})
            return True
        return self._callback({"kind": "key", "code": code, "down": down})

    def start(self, callback):
        self._callback = callback

    def stop(self):
        self.available = False

    def inject(self, event):
        return False


class Point(C.Structure):
    _fields_ = [("x", C.c_double), ("y", C.c_double)]


QUARTZ_MODIFIERS = {54: 1 << 20, 55: 1 << 20, 56: 1 << 17, 60: 1 << 17, 57: 1 << 16,
                    58: 1 << 19, 61: 1 << 19, 59: 1 << 18, 62: 1 << 18}


class MacInput(NativeInput):
    def __init__(self):
        super().__init__()
        from plugins.native_display.mac import quartz
        self.cg = quartz()
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        p = C.c_void_p
        self._functions(self.cg, {
            "CGEventCreate": (p, (p,)), "CGEventGetLocation": (Point, (p,)),
            "CGEventGetFlags": (C.c_uint64, (p,)),
            "CGEventSetFlags": (None, (p, C.c_uint64)),
            "CGEventGetIntegerValueField": (C.c_int64, (p, C.c_uint32)),
            "CGEventSetIntegerValueField": (None, (p, C.c_uint32, C.c_int64)),
            "CGEventCreateKeyboardEvent": (p, (p, C.c_uint16, C.c_bool)),
            "CGEventCreateMouseEvent": (p, (p, C.c_uint32, Point, C.c_uint32)),
            "CGEventCreateScrollWheelEvent": (p, (p, C.c_uint32, C.c_uint32)),
            "CGEventPost": (None, (C.c_uint32, p)),
            "CGWarpMouseCursorPosition": (C.c_int32, (Point,)),
            "CGEventTapEnable": (None, (p, C.c_bool)),
            "CGSessionCopyCurrentDictionary": (p, ()),
        })
        self._functions(self.cf, {
            "CFRelease": (None, (p,)), "CFRunLoopGetCurrent": (p, ()),
            "CFRunLoopStop": (None, (p,)), "CFRunLoopRunInMode": (C.c_int32, (p, C.c_double, C.c_bool)),
            "CFMachPortCreateRunLoopSource": (p, (p, p, C.c_long)),
            "CFMachPortInvalidate": (None, (p,)), "CFRunLoopAddSource": (None, (p, p, p)),
            "CFStringCreateWithCString": (p, (p, C.c_char_p, C.c_uint32)),
            "CFDictionaryGetValue": (p, (p, p)), "CFBooleanGetValue": (C.c_bool, (p,)),
        })
        self._locked_key = self.cf.CFStringCreateWithCString(None, b"CGSSessionScreenIsLocked", 0x08000100)
        self._loopref = None
        self._quit = threading.Event()
        self._last_focus = 0.0
        self._modifiers = set()
        self._marker = 0x544F5242

    @staticmethod
    def _functions(lib, definitions):
        for name, (result, params) in definitions.items():
            function = getattr(lib, name)
            function.restype, function.argtypes = result, params

    def session_active(self):
        import time
        now = time.monotonic()
        if now - self._last_focus > 0.25:
            self._last_focus = now
            session = self.cg.CGSessionCopyCurrentDictionary()
            if session:
                locked = self.cf.CFDictionaryGetValue(session, self._locked_key)
                self._focus = not (locked and self.cf.CFBooleanGetValue(locked))
                self.cf.CFRelease(session)
            else:
                self._focus = False
        return self._focus

    def start(self, callback):
        super().start(callback)
        if self._thread and self._thread.is_alive():
            return
        self._quit.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._quit.set()
        if self._loopref:
            self.cf.CFRunLoopStop(self._loopref)
        if self._thread:
            self._thread.join(1)
        super().stop()

    def _run(self):
        cg, cf = self.cg, self.cf
        cb_type = C.CFUNCTYPE(C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p, C.c_void_p)
        cb = cb_type(self._event)
        create = cg.CGEventTapCreate
        create.restype = C.c_void_p
        create.argtypes = (C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint64, cb_type, C.c_void_p)
        types = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 22, 25, 26, 27)
        self._tap = create(1, 0, 0, sum(1 << event for event in types), cb, None)
        if not self._tap:
            return
        run_mode = C.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
        source = cf.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        if not source:
            cf.CFRelease(self._tap)
            return
        self._loopref = cf.CFRunLoopGetCurrent()
        cf.CFRunLoopAddSource(self._loopref, source, run_mode)
        self.available = bool(cg.CGPreflightPostEventAccess())
        try:
            while not self._quit.is_set():
                cf.CFRunLoopRunInMode(run_mode, 0.25, False)
        finally:
            self.available = False
            self._loopref = None
            cf.CFMachPortInvalidate(self._tap)
            cf.CFRelease(source)
            cf.CFRelease(self._tap)

    def _event(self, _proxy, kind, event, _info):
        cg = self.cg
        if kind in (0xFFFFFFFF, 0xFFFFFFFE):
            self._callback({"kind": "escape"})
            cg.CGEventTapEnable(self._tap, True)
            return event
        field = cg.CGEventGetIntegerValueField
        if field(event, 42) == self._marker or not self.available:
            return event
        if kind in (10, 11, 12):
            code = field(event, 9)
            flags = cg.CGEventGetFlags(event)
            down = kind == 10 or (kind == 12 and code not in self._modifiers and
                                  bool(flags & QUARTZ_MODIFIERS.get(code, 0)))
            if kind == 12:
                self._modifiers.add(code) if down else self._modifiers.discard(code)
            has_control = bool(flags & (1 << 18) or self._modifiers & {59, 62})
            has_option = bool(flags & (1 << 19) or self._modifiers & {58, 61})
            escape = has_control and has_option and self._capturing
            consumed = self._key_event(code, down, escape)
        elif kind in (5, 6, 7, 27):
            pt = cg.CGEventGetLocation(event)
            consumed = self._callback({"kind": "move", "x": pt.x, "y": pt.y,
                                       "dx": field(event, 4), "dy": field(event, 5)})
        elif kind == 22:
            consumed = self._callback({"kind": "scroll", "dx": field(event, 12),
                                       "dy": field(event, 11)})
        else:
            code = "left" if kind <= 2 else ("right" if kind <= 4 else "middle")
            consumed = self._callback({"kind": "button", "code": code, "down": kind in (1, 3, 25)})
        return None if consumed else event

    def pointer(self):
        event = self.cg.CGEventCreate(None)
        if not event:
            return self._pointer
        pt = self.cg.CGEventGetLocation(event)
        self.cf.CFRelease(event)
        return pt.x, pt.y

    def move_cursor(self, x, y):
        self.cg.CGWarpMouseCursorPosition(Point(x, y))

    def inject(self, event):
        cg = self.cg
        kind = event["kind"]
        code = event.get("code")
        down = event.get("down")
        if kind == "key":
            ref = cg.CGEventCreateKeyboardEvent(None, code, down)
            if code in QUARTZ_MODIFIERS:
                self._held.add(code) if down else self._held.discard(code)
            if ref:
                flags = 0
                for key in self._held:
                    if type(key) is int:
                        flags |= QUARTZ_MODIFIERS.get(key, 0)
                cg.CGEventSetFlags(ref, flags)
        elif kind == "scroll":
            ref = cg.CGEventCreateScrollWheelEvent(None, 1, 2, C.c_int(event["dy"]), C.c_int(event["dx"]))
        else:
            x, y = self.pointer()
            if kind == "move":
                left, top, width, height = self._desktop_size
                x = min(max(left, x + event["dx"]), left + width - 1)
                y = min(max(top, y + event["dy"]), top + height - 1)
                button, event_type = next(
                    ((idx, drag) for key, idx, drag in (("left", 0, 6), ("right", 1, 7),
                                                        ("middle", 2, 27)) if key in self._held),
                    (0, 5))
            else:
                button, event_type = {"left": (0, 1), "right": (1, 3), "middle": (2, 25)}[code]
                event_type += int(not down)
                self._held.add(code) if down else self._held.discard(code)
            ref = cg.CGEventCreateMouseEvent(None, event_type, Point(x, y), button)
        if not ref:
            return False
        cg.CGEventSetIntegerValueField(ref, 42, self._marker)
        cg.CGEventPost(0, ref)
        self.cf.CFRelease(ref)
        return True


def create_native_input(role):
    if role == "mac" and sys.platform == "darwin":
        return MacInput()
    if role == "windows" and sys.platform == "win32":
        from app.windows_input import WindowsInput
        return WindowsInput()
    return NativeInput()

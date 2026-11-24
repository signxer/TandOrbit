"""Exclusive, paired input and text clipboard sessions."""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from uuid import uuid4

from loguru import logger

from app.enums import Mode

TEXT_LIMIT = 64 * 1024
FRAME_LIMIT = 400 * 1024
VALID_EDGES = {"left", "right", "top", "bottom"}
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


class ShareSession:
    def __init__(self, role, config, native, qt_clipboard, notify):
        self.role = role
        self.config = config
        self.native = native
        self.qt_clipboard = qt_clipboard
        self.notify = notify
        self.runtime = None
        self.mode = Mode.UNKNOWN
        self._loop = None
        self._connector = None
        self._connection = None
        self._queue = None
        self._session = uuid4().hex
        self._seq = 0
        self._last_peer_state = {}
        self._peer_seen = 0.0
        self._owned = False
        self._requested = False
        self._capturing = False
        self._receiving = False
        self._pressed: set[tuple[str, str]] = set()
        self._seen = deque(maxlen=64)
        self._avoid_clip = None
        self._last_status = None
        self._clipboard_armed = False
        self._switching = False
        self._last_enter = 0.0

    def mode_changed(self, mode):
        self.mode = mode
        self._switching = False
        if mode != Mode.SHARE:
            self.release()
            self.native.stop()
            if self._connection is not None:
                asyncio.create_task(self._connection())
        elif self._loop is not None and self.config.config.sharing.input_enabled:
            self.native.start(self._native_event)

    def start(self):
        self._loop = asyncio.get_running_loop()
        if self.mode == Mode.SHARE and self.config.config.sharing.input_enabled:
            self.native.start(self._native_event)
        if self.role == "mac" and self._connector is None:
            self._connector = asyncio.create_task(self._connect())

    def suspend(self):
        self._switching = True
        self.release()

    async def close(self):
        self.release(send=False)
        if self._connection is not None:
            await self._connection()
        if self._connector is not None:
            self._connector.cancel()
            await asyncio.gather(self._connector, return_exceptions=True)
            self._connector = None
        self.native.stop()

    def _local_state(self):
        cfg = self.config.config.sharing
        active = self.mode == Mode.SHARE and not self._switching
        session_ok = self.runtime is not None and self.runtime.power.session_active
        awake = self.runtime is not None and self.runtime.power.windows_awake is not False
        usable = active and session_ok and awake and self.native.session_active()
        return {"active": usable, "input": usable and cfg.input_enabled and self.native.available,
                "clipboard": usable and cfg.clipboard_enabled,
                "controller": cfg.controller}

    def _ready(self, key):
        local = self._local_state()
        return bool(local[key] and self._last_peer_state.get(key) and
                    (key != "input" or local["controller"] == self._last_peer_state.get("controller")) and
                    time.monotonic() - self._peer_seen < 2)

    def _native_event(self, event):
        # The OS hook must return promptly. The event loop owns all network state.
        kind = event["kind"]
        was_capturing = self._capturing
        if kind == "escape":
            self._capturing = False
            self.native.capture(False)
        elif self.mode != Mode.SHARE or self._switching:
            return was_capturing
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._input, event)
        return was_capturing or kind == "escape"

    def _input(self, event):
        kind = event["kind"]
        if kind == "escape":
            self.release()
        elif self.config.config.sharing.controller != self.role or not self._ready("input"):
            return
        elif self._owned:
            self._send("input", event=event)
        elif kind == "move" and not self._requested and time.monotonic() >= self._last_enter + 0.65:
            edge = self.config.config.sharing.edge
            fraction = self.native.at_edge(event, edge)
            if fraction is not None:
                self._requested = True
                self._last_enter = time.monotonic()
                self._send("enter", edge=edge, fraction=fraction)

    def release(self, *, send=True):
        if send and (self._owned or self._requested or self._receiving):
            self._send("release")
        self._owned = self._requested = self._capturing = self._receiving = False
        self._last_enter = time.monotonic()
        for kind, code in self._pressed:
            self.native.inject({"kind": kind, "code": code, "down": False})
        self._pressed.clear()
        self.native.capture(False)

    def clipboard_changed(self, text):
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._clipboard, text)

    def _clipboard(self, text):
        if text == self._avoid_clip:
            self._avoid_clip = None
            return
        self._avoid_clip = None
        if self._clipboard_armed and self._ready("clipboard") and len(text.encode("utf-8")) <= TEXT_LIMIT:
            self._send("clipboard", id=uuid4().hex, text=text)

    def _send(self, kind, **data):
        if self._queue is not None:
            try:
                self._queue.put_nowait({"type": kind, **data})
            except asyncio.QueueFull:
                self._owned = self._requested = self._capturing = False
                self.native.capture(False)
                if self._connection is not None:
                    asyncio.create_task(self._connection())

    async def _connect(self):
        from websockets.asyncio.client import connect

        while True:
            client = self.runtime.client
            if client is not None and self.mode == Mode.SHARE:
                host = f"[{client.host}]" if ":" in client.host else client.host
                url = f"wss://{host}:{client.port}/api/share"
                try:
                    async with connect(url, ssl=client.tls, proxy=None, max_size=FRAME_LIMIT,
                                       open_timeout=3, close_timeout=1) as socket:
                        await self._run(socket.recv, socket.send, socket.close)
                except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                    logger.debug(f"共享通道等待重连：{exc.__class__.__name__}")
                except Exception as exc:
                    logger.debug(f"共享通道关闭：{exc.__class__.__name__}")
            await asyncio.sleep(1)

    async def accept(self, socket):
        if self.role != "windows" or self._connection is not None:
            await socket.close(code=1008)
            return
        await socket.accept()
        await self._run(socket.receive_text, socket.send_text, socket.close)

    async def _run(self, receive, send, close):
        if self._connection is not None:
            return
        self._connection = close
        self._queue = asyncio.Queue(256)
        self._session = uuid4().hex
        self._seq = 0

        async def write():
            while True:
                try:
                    frame = await asyncio.wait_for(self._queue.get(), 0.20)
                except TimeoutError:
                    frame = {"type": "state", **self._local_state()}
                self._seq += 1
                await send(json.dumps({"v": 1, "session": self._session, "seq": self._seq, **frame},
                                      ensure_ascii=False, separators=(",", ":")))

        async def read():
            prior_seq = 0
            session = None
            while True:
                raw = await asyncio.wait_for(receive(), 2)
                if not isinstance(raw, str) or len(raw.encode("utf-8")) > FRAME_LIMIT:
                    raise ValueError("共享消息过大")
                frame = json.loads(raw)
                if (frame["v"] != 1 or type(frame["seq"]) is not int or frame["seq"] != prior_seq + 1 or
                        (session is not None and session != frame["session"])):
                    raise ValueError("共享协议版本、会话或序号错误")
                session = frame["session"]
                prior_seq = frame["seq"]
                self._peer_seen = time.monotonic()
                self._handle(frame)

        tasks = [asyncio.create_task(write()), asyncio.create_task(read()), asyncio.create_task(self._monitor())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.release(send=False)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._queue = self._connection = None
            self._last_peer_state = {}
            self._clipboard_armed = False
            self._report()
            try:
                await close()
            except (RuntimeError, OSError):
                pass

    async def _monitor(self):
        while True:
            if self.mode == Mode.SHARE and not self._switching and (
                self.config.config.sharing.input_enabled and not self.native.available
            ):
                self.native.start(self._native_event)
            self._send("state", **self._local_state())
            if not self._ready("input") and (self._owned or self._receiving):
                self.release()
            if self._requested and time.monotonic() - self._last_enter > 1:
                self.release()
            self._clipboard_armed = self._ready("clipboard")
            self._report()
            await asyncio.sleep(0.25)

    def _report(self):
        state = self._ready("input")
        status = (state, self._clipboard_armed)
        if status != self._last_status:
            self._last_status = status
            self.notify({"phase": "sharing", "input": state, "clipboard": self._clipboard_armed})

    def _handle(self, frame):
        kind = frame["type"]
        cfg = self.config.config.sharing
        if kind == "state":
            self._last_peer_state = {
                "input": frame.get("input") is True, "clipboard": frame.get("clipboard") is True,
                "controller": frame.get("controller"),
            }
        elif kind == "release":
            self.release(send=False)
        elif kind == "enter" and self._ready("input") and cfg.controller != self.role:
            edge, fraction = frame.get("edge"), frame.get("fraction")
            if edge in VALID_EDGES and type(fraction) in (int, float) and 0 <= fraction <= 1:
                self._receive_edge = OPPOSITE[edge]
                self.native.enter(self._receive_edge, fraction)
                self._receiving = True
                self._last_enter = time.monotonic()
                self._send("accepted")
        elif kind == "accepted" and self._ready("input") and self._requested:
            self._requested = False
            self._owned = self._capturing = True
            self.native.capture(True)
        elif kind == "input" and self._receiving and self._ready("input"):
            event = self._valid_input(frame.get("event"))
            token = event["kind"], event.get("code")
            if token[0] in ("key", "button"):
                self._pressed.add(token) if event["down"] else self._pressed.discard(token)
            if not self.native.inject(event):
                self.release()
            elif (token[0] == "move" and time.monotonic() >= self._last_enter + 0.45
                  and not self._pressed and self.native.return_edge(event, self._receive_edge)):
                self.release()
        elif kind == "clipboard" and self._ready("clipboard"):
            text, message_id = frame.get("text"), frame.get("id")
            if (isinstance(message_id, str) and len(message_id) == 32 and
                    message_id not in self._seen and isinstance(text, str) and
                    len(text.encode("utf-8")) <= TEXT_LIMIT):
                self._seen.append(message_id)
                self._avoid_clip = text
                self.qt_clipboard(text)

    @staticmethod
    def _valid_input(event):
        kind = event["kind"]
        if kind == "key" and type(event.get("code")) is int and 0 <= event["code"] < 256:
            if type(event.get("down")) is bool:
                return event
        if kind == "button" and event.get("code") in ("left", "right", "middle"):
            if type(event.get("down")) is bool:
                return event
        if kind in ("move", "scroll"):
            if all(type(event.get(axis)) in (int, float) and abs(event[axis]) <= 8192
                   for axis in ("dx", "dy")):
                return event
        raise ValueError("无效的键鼠事件")

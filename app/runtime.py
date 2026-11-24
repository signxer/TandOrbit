"""Authenticated desktop-to-desktop control service."""
from __future__ import annotations

import asyncio
import time
from uuid import UUID, uuid4

import httpx
import uvicorn
from loguru import logger
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from app.communication.mac_client import MacClient
from app.display_modes import DisplayModes
from app.enums import Mode
from app.transition import DONE, LocalParticipant, ModeCoordinator, TransitionError, TransitionJournal


class Runtime:
    def __init__(self, controller, role, pairing, power, notify, sharing=None):
        self.controller = controller
        controller.runtime = self
        self.role = role
        self.pairing = pairing
        self.power = power
        self.notify = notify
        self.sharing = sharing
        self.config = controller._config
        self.display = controller._get_plugin("betterdisplay" if role == "mac" else "multimonitortool")
        self.output = DisplayModes(role, self.config, self.display, power)
        self.journal = TransitionJournal(self.config.data_dir / "state.db")
        self.participant = LocalParticipant(self.journal, self.output, controller._state,
                                            self.config, self._on_commit)
        self.coordinator = ModeCoordinator(self.journal, self.participant, self._peer_step,
                                           self._notify_transition, self._history,
                                           lambda: self._fingerprint)
        self.client: MacClient | None = None
        self.server = None
        self._fingerprint = ""
        self._server_task = None
        self._transport_lock = asyncio.Lock()
        self._observation_lock = asyncio.Lock()
        self._deadline = 180
        if self.sharing is not None:
            self.sharing.runtime = self

    def _notify_transition(self, record):
        if self.sharing and record["phase"] == "prepare":
            self.sharing.suspend()
        elif self.sharing and record["phase"] == "restored":
            self.sharing.mode_changed(self.controller.current_mode)
        self.notify(record)

    def _history(self, record):
        phase = record["phase"]
        error = record.get("error") or record.get("warning", "")
        self.controller._history_store.record({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "from": record.get("from", "UNKNOWN"),
            "to": record["target"], "success": phase == "committed",
            "duration_ms": round((time.time() - record["started"]) * 1000),
            "error": error, "operation_id": record["id"], "phase": phase,
        })

    async def _on_commit(self, mode):
        if self.sharing is not None:
            self.sharing.mode_changed(mode)
        if mode not in (Mode.SHARE, Mode.MAC if self.role == "mac" else Mode.WINDOWS):
            return
        audio = self.controller._get_plugin("audio")
        cfg = self.config.config.audio
        device = (cfg.mac_device_uid or cfg.mac_output) if self.role == "mac" else (
            cfg.windows_device_id or cfg.windows_output)
        if audio and device:
            try:
                if await asyncio.wait_for(audio.set_device(device), timeout=5):
                    return
            except Exception as exc:
                logger.warning(f"音频设置失败：{exc}")
            return "音频输出未切换，可在设置中检查设备或打开系统声音设置"

    async def start(self):
        async with self._transport_lock:
            await self._stop_transport()
            peer = self.pairing.peer
            if peer is None:
                self.notify({"phase": "unpaired"})
                return
            context = self.pairing.context(peer=peer)
            server_context = self.pairing.context(server=True, peer=peer)
            if context is None or server_context is None:
                return
            self._fingerprint = peer["fingerprint"]
            self.client = MacClient(peer["host"], peer["port"], 30, tls=context)
            local = self.config.config.mac if self.role == "mac" else self.config.config.windows
            server_config = uvicorn.Config(
                self.create_app(), host="0.0.0.0", port=local.port, log_config=None,
                log_level="warning", access_log=False, ws="websockets-sansio",
                ws_max_size=400 * 1024, ws_per_message_deflate=False, timeout_graceful_shutdown=2,
            )
            server_config.load()
            server_config.ssl = server_context
            self.server = uvicorn.Server(server_config)

            async def serve():
                server = self.server
                try:
                    # The Qt process owns process signals.
                    await server.serve()
                except (SystemExit, OSError) as exc:
                    self.notify({"phase": "connection_error", "error": f"监听端口失败：{local.port} ({exc})"})
            self._server_task = asyncio.create_task(serve())
            if self.sharing is not None:
                self.sharing.start()
        await self.recover()

    async def _stop_transport(self):
        if self.sharing is not None:
            await self.sharing.close()
        if self.server is not None:
            self.server.should_exit = True
        if self._server_task is not None:
            await self._server_task
        self.server, self._server_task = None, None
        if self.client is not None:
            await self.client.close()
            self.client = None
        self._fingerprint = ""

    async def close(self):
        if self.coordinator._task is not None:
            task = self.coordinator._task
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with self._transport_lock:
            await self._stop_transport()

    async def probe_candidate(self, candidate):
        if self.client is None or (self.client.host, self.client.port) == (
            candidate["host"], candidate["port"]
        ):
            return False
        async with self._transport_lock:
            if self.client is None:
                return False
            peer = self.pairing.peer
            if not peer or peer["fingerprint"] != self._fingerprint:
                return False
            trial = MacClient(candidate["host"], candidate["port"], 3, tls=self.client.tls)
            try:
                report = await trial.request("GET", "/api/health")
                if report.get("role") != peer["role"] or report.get("protocol") != 1:
                    return False
                if (await self._online(self.client)):
                    return False
                if not self.pairing.update_address(self._fingerprint, trial.host, trial.port):
                    return False
                previous, self.client = self.client, MacClient(trial.host, trial.port, 30, tls=trial.tls)
                await previous.close()
                return True
            except (httpx.HTTPError, OSError, ValueError):
                return False
            finally:
                if trial is not None:
                    await trial.close()

    @staticmethod
    async def _online(client):
        if client is None:
            return False
        try:
            return (await asyncio.wait_for(client.request("GET", "/api/health"), timeout=3)).get("protocol") == 1
        except (OSError, httpx.HTTPError, ValueError, TimeoutError):
            return False

    async def online(self):
        return await self._online(self.client)

    async def recover(self):
        if self.role == "mac":
            await self.coordinator.recover()

    async def observe_startup(self):
        if (self.client is None or self.controller.current_mode != Mode.UNKNOWN or
                self._observation_lock.locked() or self.journal.pending("local")):
            return
        async with self._observation_lock:
            record = self.journal.last_commit("local")
            if record is None or not await self.online():
                return
            try:
                await self.client.request("GET", f"/api/observe/{record['id']}")
                await self.participant.step(record["id"], record["target"], "observe")
            except (TransitionError, httpx.HTTPError, OSError):
                return
            mode = Mode[record["target"]]
            self.controller._state.force_set(mode)
            if self.sharing:
                self.sharing.mode_changed(mode)

    async def recover_local(self):
        if self.coordinator._active is not None or self.participant._lock.locked():
            raise TransitionError("切换正在执行")
        async with self.participant._lock:
            await self.power.set(True)
            cfg = self.config.config.display
            monitors = await self.display.list_displays()
            bound = [
                DisplayModes._resolve(monitors, getattr(cfg, f"{self.role}_{name}_monitor_id"),
                                      getattr(cfg, f"{name}_id"))
                for name in ("primary", "secondary")
            ]
            for display in bound:
                if not display.is_enabled and not await self.display.enable_display(display.id):
                    raise TransitionError(f"无法恢复本机输出：{display.name}")
            for _ in range(16):
                if await self.power.read() is True:
                    current = await self.display.list_displays()
                    try:
                        if all(DisplayModes._resolve(current, monitor.device_id or monitor.monitor_id,
                                                     monitor.id).is_enabled for monitor in bound):
                            break
                    except TransitionError:
                        pass
                await asyncio.sleep(0.25)
            else:
                raise TransitionError("系统尚未确认本机输出已恢复")
        await self.recover()

    async def wake_windows(self, timeout=60):
        from plugins.wol.plugin import WoLPlugin

        peer = self.pairing.peer
        if self.role != "mac" or not peer or not peer["mac_address"]:
            raise TransitionError("请在配对时选择 Windows 的 WoL 网卡")
        plugin = self.controller._get_plugin("wol") or WoLPlugin(self.controller._event_bus)
        if not await plugin.wake(peer["mac_address"]):
            raise TransitionError("无法发送网络唤醒包")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.online():
                return
            await asyncio.sleep(1)
        raise TransitionError(f"Windows Agent 未在 {timeout} 秒内上线")

    async def _peer_step(self, record, phase):
        if self.client is None:
            raise TransitionError("尚未与 Windows 配对")
        if record.get("peer") and record["peer"] != self._fingerprint:
            raise TransitionError("原切换的对端已变更，请连接原配对设备恢复")
        path = f"/api/participant/{record['id']}"
        body = {"target": record["target"], "phase": phase, "share_role": record["share_role"]}
        try:
            return await self.client.request("POST", path, json=body)
        except httpx.HTTPStatusError as exc:
            raise TransitionError(exc.response.json().get("error", str(exc))) from exc
        except httpx.TransportError:
            observed = await self.client.request("POST", path, json={**body, "phase": "status"})
            if observed.get("phase") not in (phase, {"commit": "committed", "restore": "restored"}.get(phase)):
                raise
            return observed

    async def switch(self, mode: Mode):
        if (mode == self.controller.current_mode and not self.controller.is_transitioning
                and not self.journal.pending("coordinator") and not self.journal.pending("local")):
            return True
        if self.client is None:
            raise TransitionError("请先在连接设置中完成双机配对")
        if self.role == "mac":
            record = self.coordinator.submit(mode.name)
        else:
            operation_id = uuid4().hex
            request = {"target": mode.name, "id": operation_id}
            try:
                record = await self.client.request("POST", "/api/switch", json=request)
            except httpx.TransportError:
                record = await self.client.request("POST", "/api/switch", json=request)
            except httpx.HTTPStatusError as exc:
                raise TransitionError(exc.response.json().get("error", str(exc))) from exc
        deadline = time.monotonic() + self._deadline
        while time.monotonic() < deadline:
            self.notify(record)
            phase = record["phase"]
            if phase in DONE:
                return phase == "committed"
            if phase in ("recovering", "decision_commit") and record.get("error"):
                return False
            await asyncio.sleep(0.25)
            if self.role == "mac":
                record = self.coordinator.status(record["id"])
            else:
                try:
                    record = await self.client.request("GET", f"/api/switch/{record['id']}")
                except httpx.TransportError:
                    continue
        raise TransitionError("等待切换结果超时，可在切换记录中查看操作 ID")

    def create_app(self):
        app = Starlette(routes=[
            Route("/api/health", self._health),
            Route("/api/capabilities", self._capabilities),
            Route("/api/switch", self._submit, methods=["POST"]),
            Route("/api/switch/{id}", self._status),
            Route("/api/observe/{id}", self._observe),
            Route("/api/participant/{id}", self._participate, methods=["POST"]),
            WebSocketRoute("/api/share", self._share),
        ])
        fingerprint = self._fingerprint

        async def authorization(request, call_next):
            peer = self.pairing.peer
            if not peer or peer["fingerprint"] != fingerprint:
                return JSONResponse({"error": "配对身份已变更"}, status_code=403)
            return await call_next(request)

        app.add_middleware(BaseHTTPMiddleware, dispatch=authorization)
        return app

    async def _health(self, request):
        return JSONResponse({"protocol": 1, "role": self.role,
                             "mode": self.controller.current_mode.name})

    async def _capabilities(self, request):
        audio = self.controller._get_plugin("audio")
        return JSONResponse({
            "display": [item.model_dump(mode="json") for item in await self.display.list_displays()],
            "audio": await audio.list_endpoints() if audio else [],
            "single_display": getattr(self.display, "can_change_outputs", True),
            "mode": self.controller.current_mode.name,
        })

    async def _submit(self, request):
        if self.role != "mac":
            return JSONResponse({"error": "Mac 负责协调切换"}, status_code=409)
        try:
            body = await request.json()
            operation_id = UUID(body["id"]).hex
            return JSONResponse(self.coordinator.submit(body["target"], operation_id))
        except (KeyError, TypeError, ValueError, TransitionError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

    async def _status(self, request):
        record = self.coordinator.status(request.path_params["id"])
        return JSONResponse(record or {"error": "找不到切换记录"}, status_code=200 if record else 404)

    async def _observe(self, request):
        record = self.journal.last_commit("local")
        if (not record or record["id"] != request.path_params["id"] or
                self.journal.pending("local")):
            return JSONResponse({"error": "两端没有同一份已提交状态"}, status_code=409)
        try:
            return JSONResponse(await self.participant.step(record["id"], record["target"], "observe"))
        except (TransitionError, OSError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

    async def _participate(self, request: Request):
        if self.role != "windows":
            return JSONResponse({"error": "只有 Windows 接收协调器指令"}, status_code=409)
        try:
            operation_id = UUID(request.path_params["id"]).hex
            body = await request.json()
            if self.sharing and body["phase"] == "prepare":
                self.sharing.suspend()
            record = await self.participant.step(operation_id, body["target"], body["phase"],
                                                 body.get("share_role", ""))
            if body["phase"] != "status":
                self.notify(record)
            if body["phase"] in ("commit", "restore") and "started" in record:
                self._history(record)
            if self.sharing and record["phase"] == "restored":
                self.sharing.mode_changed(self.controller.current_mode)
            return JSONResponse(record)
        except (KeyError, TypeError, ValueError, TransitionError, OSError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

    async def _share(self, websocket):
        peer = self.pairing.peer
        if self.sharing is not None and peer and peer["fingerprint"] == self._fingerprint:
            await self.sharing.accept(websocket)
        else:
            await websocket.close(code=1008)

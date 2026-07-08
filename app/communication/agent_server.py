"""Windows Agent HTTP Server

运行在 Windows 端，接收 Mac 端的控制指令。
使用 Starlette + Uvicorn 实现轻量级 HTTP 服务。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.models import AgentHealthStatus, AgentResponse, DisplayInfo


class AgentServer:
    """Windows Agent HTTP Server

    常驻运行在 Windows 端，提供 HTTP API 供 Mac 端调用。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5000) -> None:
        self._host = host
        self._port = port
        self._start_time = time.monotonic()
        self._app: Starlette | None = None
        self._display_plugin: Any = None
        self._deskflow_plugin: Any = None
        self._audio_plugin: Any = None

    def set_plugins(
        self,
        display: Any = None,
        deskflow: Any = None,
        audio: Any = None,
    ) -> None:
        """注入插件实例"""
        self._display_plugin = display
        self._deskflow_plugin = deskflow
        self._audio_plugin = audio

    def create_app(self) -> Starlette:
        """创建 Starlette 应用"""
        routes = [
            Route("/api/health", self._health_check, methods=["GET"]),
            Route("/api/status", self._get_status, methods=["GET"]),
            Route("/api/display/list", self._list_displays, methods=["GET"]),
            Route("/api/display/enable", self._enable_display, methods=["POST"]),
            Route("/api/display/disable", self._disable_display, methods=["POST"]),
            Route("/api/display/duplicate", self._set_duplicate, methods=["POST"]),
            Route("/api/display/extend", self._set_extend, methods=["POST"]),
            Route("/api/deskflow/start", self._start_deskflow, methods=["POST"]),
            Route("/api/deskflow/stop", self._stop_deskflow, methods=["POST"]),
            Route("/api/deskflow/restart", self._restart_deskflow, methods=["POST"]),
            Route("/api/deskflow/status", self._deskflow_status, methods=["GET"]),
            Route("/api/audio/devices", self._list_audio_devices, methods=["GET"]),
            Route("/api/audio/set", self._set_audio_device, methods=["POST"]),
        ]
        self._app = Starlette(routes=routes)
        return self._app

    async def start(self) -> None:
        """启动服务器"""
        import uvicorn

        if self._app is None:
            self.create_app()
        logger.info(f"Agent server starting on {self._host}:{self._port}")
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        await server.serve()

    # --- API Handlers ---

    async def _health_check(self, request: Request) -> JSONResponse:
        """健康检查"""
        displays = []
        if self._display_plugin:
            try:
                display_list = await self._display_plugin.list_displays()
                displays = [d.model_dump() for d in display_list]
            except Exception:
                pass

        deskflow_running = False
        deskflow_connected = False
        if self._deskflow_plugin:
            try:
                deskflow_running = await self._deskflow_plugin.health_check()
                deskflow_connected = self._deskflow_plugin.connected
            except Exception:
                pass

        status = AgentHealthStatus(
            status="ok",
            uptime_seconds=time.monotonic() - self._start_time,
            displays=[DisplayInfo(**d) for d in displays] if displays else [],
            deskflow_running=deskflow_running,
            deskflow_connected=deskflow_connected,
        )
        return JSONResponse(status.model_dump())

    async def _get_status(self, request: Request) -> JSONResponse:
        """获取状态"""
        return JSONResponse({"status": "running", "agent": "TandOrbit Agent"})

    async def _list_displays(self, request: Request) -> JSONResponse:
        """列出显示器"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(),
                status_code=503,
            )
        try:
            displays = await self._display_plugin.list_displays()
            return JSONResponse(
                AgentResponse(
                    success=True, data={"displays": [d.model_dump() for d in displays]}
                ).model_dump()
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _enable_display(self, request: Request) -> JSONResponse:
        """启用显示器"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(),
                status_code=503,
            )
        try:
            body = await request.json()
            display_id = body.get("display_id", 1)
            ok = await self._display_plugin.enable_display(display_id)
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _disable_display(self, request: Request) -> JSONResponse:
        """禁用显示器"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(),
                status_code=503,
            )
        try:
            body = await request.json()
            display_id = body.get("display_id", 2)
            ok = await self._display_plugin.disable_display(display_id)
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _set_duplicate(self, request: Request) -> JSONResponse:
        """设置复制模式"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(),
                status_code=503,
            )
        try:
            body = await request.json()
            source_id = body.get("source_id", 1)
            target_id = body.get("target_id", 2)
            ok = await self._display_plugin.set_duplicate(source_id, target_id)
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _set_extend(self, request: Request) -> JSONResponse:
        """设置扩展模式"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(),
                status_code=503,
            )
        try:
            ok = await self._display_plugin.set_extend()
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _start_deskflow(self, request: Request) -> JSONResponse:
        """启动 Deskflow"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(),
                status_code=503,
            )
        try:
            ok = await self._deskflow_plugin.start()
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _stop_deskflow(self, request: Request) -> JSONResponse:
        """停止 Deskflow"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(),
                status_code=503,
            )
        try:
            ok = await self._deskflow_plugin.stop()
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _restart_deskflow(self, request: Request) -> JSONResponse:
        """重启 Deskflow"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(),
                status_code=503,
            )
        try:
            ok = await self._deskflow_plugin.restart()
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _deskflow_status(self, request: Request) -> JSONResponse:
        """获取 Deskflow 状态"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(),
                status_code=503,
            )
        try:
            running = await self._deskflow_plugin.health_check()
            connected = self._deskflow_plugin.connected
            return JSONResponse(
                AgentResponse(
                    success=True,
                    data={"running": running, "connected": connected},
                ).model_dump()
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _list_audio_devices(self, request: Request) -> JSONResponse:
        """列出音频设备"""
        if not self._audio_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Audio plugin not available").model_dump(),
                status_code=503,
            )
        try:
            devices = await self._audio_plugin.list_devices()
            return JSONResponse(
                AgentResponse(success=True, data={"devices": devices}).model_dump()
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

    async def _set_audio_device(self, request: Request) -> JSONResponse:
        """设置音频设备"""
        if not self._audio_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Audio plugin not available").model_dump(),
                status_code=503,
            )
        try:
            body = await request.json()
            device_name = body.get("device", "")
            ok = await self._audio_plugin.set_device(device_name)
            return JSONResponse(AgentResponse(success=ok).model_dump())
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(),
                status_code=500,
            )

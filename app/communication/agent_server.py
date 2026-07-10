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

from app.enums import Mode
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

    def set_state_manager(self, state_manager: Any) -> None:
        """注入状态管理器（用于模式同步）"""
        self._state_manager = state_manager

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
            Route("/api/power/sleep", self._sleep, methods=["POST"]),
            Route("/api/power/shutdown", self._shutdown, methods=["POST"]),
            Route("/api/mode/set", self._set_mode, methods=["POST"]),
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
                displays = [d.model_dump(mode="json") for d in display_list]
            except Exception:
                pass

        deskflow_running = False
        deskflow_connected = False
        if self._deskflow_plugin:
            try:
                deskflow_running = await self._deskflow_plugin.health_check()
                deskflow_connected = await self._deskflow_plugin.check_connection()
            except Exception:
                pass

        status = AgentHealthStatus(
            status="ok",
            uptime_seconds=time.monotonic() - self._start_time,
            displays=[DisplayInfo(**d) for d in displays] if displays else [],
            deskflow_running=deskflow_running,
            deskflow_connected=deskflow_connected,
        )
        return JSONResponse(status.model_dump(mode="json"))

    async def _get_status(self, request: Request) -> JSONResponse:
        """获取状态"""
        return JSONResponse({"status": "running", "agent": "TandOrbit Agent"})

    async def _list_displays(self, request: Request) -> JSONResponse:
        """列出显示器"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            displays = await self._display_plugin.list_displays()
            return JSONResponse(
                AgentResponse(
                    success=True, data={"displays": [d.model_dump(mode="json") for d in displays]}
                ).model_dump(mode="json")
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _enable_display(self, request: Request) -> JSONResponse:
        """启用显示器"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            body = await request.json()
            display_id = body.get("display_id", 1)
            ok = await self._display_plugin.enable_display(display_id)
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _disable_display(self, request: Request) -> JSONResponse:
        """禁用显示器"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            body = await request.json()
            display_id = body.get("display_id", 2)
            ok = await self._display_plugin.disable_display(display_id)
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _set_duplicate(self, request: Request) -> JSONResponse:
        """设置复制模式"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            body = await request.json()
            source_id = body.get("source_id", 1)
            target_id = body.get("target_id", 2)
            ok = await self._display_plugin.set_duplicate(source_id, target_id)
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _set_extend(self, request: Request) -> JSONResponse:
        """设置扩展模式"""
        if not self._display_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Display plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            ok = await self._display_plugin.set_extend()
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _start_deskflow(self, request: Request) -> JSONResponse:
        """启动 Deskflow"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            ok = await self._deskflow_plugin.start()
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _stop_deskflow(self, request: Request) -> JSONResponse:
        """停止 Deskflow"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            ok = await self._deskflow_plugin.stop()
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _restart_deskflow(self, request: Request) -> JSONResponse:
        """重启 Deskflow"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            ok = await self._deskflow_plugin.restart()
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _deskflow_status(self, request: Request) -> JSONResponse:
        """获取 Deskflow 状态"""
        if not self._deskflow_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Deskflow plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            running = await self._deskflow_plugin.health_check()
            connected = self._deskflow_plugin.connected
            return JSONResponse(
                AgentResponse(
                    success=True,
                    data={"running": running, "connected": connected},
                ).model_dump(mode="json")
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _list_audio_devices(self, request: Request) -> JSONResponse:
        """列出音频设备"""
        if not self._audio_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Audio plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            devices = await self._audio_plugin.list_devices()
            return JSONResponse(
                AgentResponse(success=True, data={"devices": devices}).model_dump(mode="json")
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _set_audio_device(self, request: Request) -> JSONResponse:
        """设置音频设备"""
        if not self._audio_plugin:
            return JSONResponse(
                AgentResponse(success=False, error="Audio plugin not available").model_dump(mode="json"),
                status_code=503,
            )
        try:
            body = await request.json()
            device_name = body.get("device", "")
            ok = await self._audio_plugin.set_device(device_name)
            return JSONResponse(AgentResponse(success=ok).model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _sleep(self, request: Request) -> JSONResponse:
        """让 Windows 休眠"""
        import subprocess
        try:
            subprocess.Popen(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                shell=True,
            )
            return JSONResponse(AgentResponse(success=True, message="Sleep command sent").model_dump(mode="json"))
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _shutdown(self, request: Request) -> JSONResponse:
        """关闭 Windows"""
        import subprocess
        try:
            subprocess.Popen(["shutdown", "/s", "/t", "5"], shell=True)
            return JSONResponse(
                AgentResponse(success=True, message="Shutdown command sent").model_dump(mode="json")
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _set_mode(self, request: Request) -> JSONResponse:
        """接收远端模式变更通知（Mac 端收到后会同步到 Windows）"""
        import platform
        try:
            body = await request.json()
            mode_name = body.get("mode", "")
            if mode_name not in Mode.__members__:
                return JSONResponse(
                    AgentResponse(success=False, error=f"Invalid mode: {mode_name}").model_dump(mode="json"),
                    status_code=400,
                )
            mode = Mode[mode_name]
            if hasattr(self, "_state_manager") and self._state_manager:
                self._state_manager.force_set(mode)
                logger.info(f"Mode synced from remote: {mode_name}")
            # 只在本机需要显示时才唤醒显示器
            if platform.system() == "Windows" and mode != Mode.MAC:
                await self._wake_displays()
            elif platform.system() == "Darwin" and mode != Mode.WINDOWS:
                await self._wake_mac_displays()
            # 如果是 Mac 端收到，转发到 Windows Agent
            await self._forward_mode_to_windows(mode_name)
            return JSONResponse(
                AgentResponse(success=True, message=f"Mode set to {mode_name}").model_dump(mode="json")
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    async def _wake_displays(self) -> None:
        """唤醒 Windows 显示器"""
        import ctypes
        try:
            ctypes.windll.user32.mouse_event(0x0001, 0, 0, 0, 0)
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
            logger.info("Windows displays woken up")
        except Exception as e:
            logger.warning(f"Wake displays failed: {e}")

    async def _wake_mac_displays(self) -> None:
        """唤醒 Mac 显示器"""
        import asyncio
        try:
            proc = await asyncio.create_subprocess_shell(
                "caffeinate -u -t 1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            logger.info("Mac displays woken up")
        except Exception as e:
            logger.warning(f"Wake Mac displays failed: {e}")

    async def _forward_mode_to_windows(self, mode_name: str) -> None:
        """Mac 端收到模式变更后转发到 Windows Agent"""
        import platform
        if platform.system() != "Darwin":
            return
        try:
            import httpx
            from app.config import ConfigManager
            cfg = ConfigManager().load()
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"http://{cfg.windows.host}:{cfg.windows.port}/api/mode/set",
                    json={"mode": mode_name},
                )
        except Exception as e:
            logger.warning(f"Forward mode to Windows failed: {e}")

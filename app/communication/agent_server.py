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
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.enums import Mode
from app.models import AgentHealthStatus, AgentResponse


class _AuthMiddleware(BaseHTTPMiddleware):
    """Agent 访问令牌鉴权（/api/health 放行，供在线探测；其余端点需 Bearer token）"""

    def __init__(self, app: Any, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not self._token or request.url.path == "/api/health":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth == f"Bearer {self._token}":
            return await call_next(request)
        return JSONResponse(
            {"success": False, "error": "Unauthorized"}, status_code=401
        )


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
        self._token: str = ""
        self._last_claim_time: float = 0.0  # 最近一次收到切换声明的时刻（缩小同时发起竞态）

    def set_auth_token(self, token: str) -> None:
        """设置 Agent 访问令牌（两端需一致；空 = 不鉴权）"""
        self._token = token

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
            Route("/api/mode/claim", self._claim_mode, methods=["POST"]),
        ]
        self._app = Starlette(
            routes=routes,
            middleware=[Middleware(_AuthMiddleware, token=self._token)],
        )
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
        """健康检查（轻量实现：不枚举显示器，避免频繁触发 PowerShell 子进程）"""
        deskflow_running = False
        if self._deskflow_plugin:
            try:
                deskflow_running = await self._deskflow_plugin.health_check()
            except Exception:
                pass

        status = AgentHealthStatus(
            status="ok",
            uptime_seconds=time.monotonic() - self._start_time,
            displays=[],
            deskflow_running=deskflow_running,
            deskflow_connected=deskflow_running,
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

    async def _claim_mode(self, request: Request) -> JSONResponse:
        """对端切换意图声明（冲突裁决）

        - 本机正在切换中 → 409（对端应等待重试）
        - 1 秒内收到过重复声明 → 409（缩小两端同时发起的竞态窗口）
        - 否则 → 200（可切换）
        """
        try:
            body = await request.json()
            mode_name = body.get("mode", "")
        except Exception:
            mode_name = ""
        if hasattr(self, "_state_manager") and self._state_manager and self._state_manager.is_transitioning:
            target = self._state_manager.target_mode
            return JSONResponse(
                {
                    "success": False,
                    "error": "conflict",
                    "target_mode": target.name if target else None,
                    "message": f"本机正在切换（目标 {target.name if target else '未知'}），请稍后再试",
                },
                status_code=409,
            )
        now = time.monotonic()
        if self._last_claim_time and now - self._last_claim_time < 1.0:
            return JSONResponse(
                {"success": False, "error": "busy", "message": "正在处理切换声明，请稍后再试"},
                status_code=409,
            )
        self._last_claim_time = now
        logger.info(f"Mode claim accepted: {mode_name or '?'}")
        return JSONResponse(
            {"success": True, "message": f"claimed {mode_name or '?'}"}
        )

    async def _set_mode(self, request: Request) -> JSONResponse:
        """接收远端模式变更通知，并执行本机对应的显示器配置

        语义（对称化，修复"切换成功率不高"）：
        - WINDOWS 模式：启用全部显示器 + 扩展拓扑 + 上电
        - SHARE 模式：保留副屏（禁用主屏），扩展拓扑
        - MAC 模式：关闭本机显示器（让显示器切到对端输入源）
        """
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
            from_mode = None
            if hasattr(self, "_state_manager") and self._state_manager:
                if self._state_manager.is_transitioning:
                    # 本机正在切换中，只应用显示器配置，不覆盖状态
                    logger.warning("Local transition in progress; applying display mode without state change")
                else:
                    from_mode = self._state_manager.current_mode
                    if from_mode != mode:
                        self._state_manager.force_set(mode)
                        logger.info(f"Mode synced from remote: {mode_name}")
                        # 远端同步也持久化 last_mode，保持两端共识一致，
                        # 否则重启会恢复到"本端上次成功切换"的旧状态（如 Windows 端错显 Mac 模式）
                        self._persist_last_mode(mode)
                    # 即使已经是目标模式也重新应用显示器配置（幂等），
                    # 修复从 Share 切出时远端显示器被关闭后无人重新启用的问题
            if platform.system() == "Windows":
                await self._apply_display_mode(mode, from_mode)
            elif platform.system() == "Darwin":
                await self._apply_mac_display_mode(mode)
            return JSONResponse(
                AgentResponse(success=True, message=f"Mode set to {mode_name}").model_dump(mode="json")
            )
        except Exception as e:
            return JSONResponse(
                AgentResponse(success=False, error=str(e)).model_dump(mode="json"),
                status_code=500,
            )

    @staticmethod
    def _persist_last_mode(mode: Mode) -> None:
        """持久化 last_mode（远端同步触发时），与本地切换成功的保存保持一致"""
        try:
            from app.config import ConfigManager

            cm = ConfigManager()
            cm.config.last_mode = mode.name
            cm.save()
        except Exception as e:
            logger.warning(f"Failed to persist last_mode (remote sync {mode.name}): {e}")

    async def _apply_display_mode(self, mode: Mode, from_mode: Mode | None = None) -> None:
        """Windows 端：根据模式切换显示器拓扑与电源

        - WINDOWS：启用所有显示器 + 扩展拓扑 + 上电（显示器切回 Windows）
        - SHARE：确保副屏启用 + 扩展拓扑 + 禁用主屏（主屏留给 Mac）
        - MAC：关闭本机显示器（信号消失后显示器自动切到 Mac 输入）
        """
        logger.debug(f"Applying display mode {mode.name} (from {from_mode.name if from_mode else 'unknown'})")
        if not self._display_plugin:
            if mode == Mode.MAC:
                await self._turn_off_displays()
            else:
                await self._wake_displays()
            return

        try:
            if mode == Mode.WINDOWS:
                await self._enable_all_displays()
                await self._display_plugin.set_extend_mode()
                await self._power_on_displays()
            elif mode == Mode.SHARE:
                await self._ensure_display_enabled(self._secondary_display_id())
                await self._display_plugin.set_extend_mode()
                await self._disable_display(self._primary_display_id())
            else:  # MAC
                await self._turn_off_displays()
        except Exception as e:
            logger.warning(f"Failed to apply display mode {mode.name}: {e}")

    async def _apply_mac_display_mode(self, mode: Mode) -> None:
        """Mac 端：收到远端模式变更后执行完整重配置（与本地管线语义一致）

        - WINDOWS：休眠 Mac 显示器（显示器切到 Windows 输入源）
        - SHARE：保留主屏，断开副屏（Windows 独占副屏）
        - MAC：唤醒显示器并确保副屏已连接
        """
        try:
            if mode == Mode.WINDOWS:
                await self._sleep_mac_displays()
            elif mode == Mode.SHARE:
                await self._disconnect_mac_secondary()
                await self._wake_mac_displays()
            else:  # MAC
                await self._reconnect_mac_secondary()
                await self._wake_mac_displays()
        except Exception as e:
            logger.warning(f"Mac display reconfig failed: {e}")

    # --- Windows 显示器拓扑/电源辅助 ---

    def _primary_display_id(self) -> int:
        """主显示器 DISPLAY 编号（来自配置，默认 1）"""
        try:
            from app.config import ConfigManager
            return int(ConfigManager().load().display.primary_id)
        except Exception:
            return 1

    def _secondary_display_id(self) -> int:
        """副显示器 DISPLAY 编号（来自配置，默认 2）"""
        try:
            from app.config import ConfigManager
            return int(ConfigManager().load().display.secondary_id)
        except Exception:
            return 2

    async def _enable_all_displays(self) -> None:
        """启用所有被禁用的显示器"""
        if not self._display_plugin:
            return
        try:
            displays = await self._display_plugin.list_displays()
            for d in displays:
                if not d.is_enabled:
                    logger.info(f"Enabling display {d.id}: {d.name}")
                    await self._display_plugin.enable_display(d.id)
                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"Enable all displays error: {e}")

    async def _ensure_display_enabled(self, display_id: int) -> None:
        """确保指定显示器已启用"""
        if not self._display_plugin:
            return
        try:
            displays = await self._display_plugin.list_displays()
            for d in displays:
                if d.id == display_id:
                    if d.is_enabled:
                        return
                    break
            logger.info(f"Enabling display {display_id}")
            await self._display_plugin.enable_display(display_id)
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"Ensure display enabled error: {e}")

    async def _disable_display(self, display_id: int) -> None:
        """禁用指定显示器"""
        if not self._display_plugin:
            return
        try:
            logger.info(f"Disabling display {display_id} (releasing for Mac)")
            await self._display_plugin.disable_display(display_id)
        except Exception as e:
            logger.warning(f"Disable display error: {e}")

    async def _turn_off_displays(self) -> None:
        """关闭 Windows 显示器（SC_MONITORPOWER，仅断电不断开）"""
        import ctypes
        try:
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            logger.info("Windows displays turned off (releasing for Mac)")
        except Exception as e:
            logger.warning(f"Windows display off error: {e}")

    async def _power_on_displays(self) -> None:
        """唤醒 Windows 显示器"""
        await self._wake_displays()

    async def _wake_displays(self) -> None:
        """唤醒 Windows 显示器"""
        import ctypes
        try:
            ctypes.windll.user32.mouse_event(0x0001, 0, 0, 0, 0)
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
            logger.info("Windows displays woken up")
        except Exception as e:
            logger.warning(f"Wake displays failed: {e}")

    # --- Mac 显示器辅助 ---

    async def _resolve_mac_secondary_id(self) -> int | None:
        """从 BetterDisplay 枚举结果解析副显示器 tagID"""
        plugin = self._display_plugin
        if plugin is None:
            return None
        try:
            displays = await plugin.list_displays()
            if len(displays) >= 2:
                non_primary = [d for d in displays if not d.is_primary]
                if non_primary:
                    return non_primary[0].id
                return displays[-1].id
        except Exception:
            pass
        return None

    async def _disconnect_mac_secondary(self) -> None:
        """断开 Mac 副屏（Share 模式）"""
        plugin = self._display_plugin
        if plugin is None:
            return
        display_id = await self._resolve_mac_secondary_id()
        if display_id is None:
            logger.warning("Cannot resolve Mac secondary display, skipping disconnect")
            return
        try:
            ok = await plugin.disable_display(display_id)
            if ok:
                logger.info(f"Mac secondary display (tagID={display_id}) disconnected")
            else:
                logger.warning(f"Mac secondary display (tagID={display_id}) disconnect failed")
        except Exception as e:
            logger.warning(f"Mac secondary display disconnect error: {e}")

    async def _reconnect_mac_secondary(self) -> None:
        """重新连接 Mac 副屏（离开 Share 模式）"""
        plugin = self._display_plugin
        if plugin is None:
            return
        display_id = await self._resolve_mac_secondary_id()
        if display_id is None:
            # 枚举中只有主屏时无法解析副屏 tagID，尝试用配置值（用户可能已配置真实 tagID）
            try:
                from app.config import ConfigManager
                display_id = int(ConfigManager().load().display.secondary_id)
            except Exception:
                logger.warning("Cannot resolve Mac secondary display, skipping reconnect")
                return
        try:
            ok = await plugin.enable_display(display_id)
            if ok:
                logger.info(f"Mac secondary display (tagID={display_id}) reconnected")
            else:
                logger.warning(f"Mac secondary display (tagID={display_id}) reconnect failed")
        except Exception as e:
            logger.warning(f"Mac secondary display reconnect error: {e}")

    async def _wake_mac_displays(self) -> None:
        """唤醒 Mac 显示器"""
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

    async def _sleep_mac_displays(self) -> None:
        """休眠 Mac 显示器（让显示器切到 Windows 输入源）"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "pmset displaysleepnow",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            logger.info("Mac displays put to sleep")
        except Exception as e:
            logger.warning(f"Sleep Mac displays failed: {e}")

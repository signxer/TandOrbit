"""Mac 端 HTTP Client

运行在 Mac 端，向 Windows Agent 发送控制指令。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.models import AgentHealthStatus, AgentResponse, DisplayInfo


class MacClient:
    """Mac 端 HTTP Client

    向 Windows Agent 发送 HTTP 请求。
    """

    def __init__(self, host: str = "192.168.1.100", port: int = 5000, timeout: float = 10.0) -> None:
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # --- API 调用 ---

    async def health_check(self) -> AgentHealthStatus | None:
        """健康检查"""
        try:
            client = await self._get_client()
            resp = await client.get("/api/health")
            resp.raise_for_status()
            return AgentHealthStatus(**resp.json())
        except Exception as e:
            logger.error(f"Agent health check failed: {e}")
            return None

    async def get_status(self) -> dict[str, Any] | None:
        """获取状态"""
        try:
            client = await self._get_client()
            resp = await client.get("/api/status")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Agent status failed: {e}")
            return None

    async def list_displays(self) -> list[DisplayInfo]:
        """列出显示器"""
        try:
            client = await self._get_client()
            resp = await client.get("/api/display/list")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            if data.success and data.data:
                return [DisplayInfo(**d) for d in data.data.get("displays", [])]
            return []
        except Exception as e:
            logger.error(f"List displays failed: {e}")
            return []

    async def enable_display(self, display_id: int) -> bool:
        """启用显示器"""
        try:
            client = await self._get_client()
            resp = await client.post(
                "/api/display/enable", json={"display_id": display_id}
            )
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Enable display failed: {e}")
            return False

    async def disable_display(self, display_id: int) -> bool:
        """禁用显示器"""
        try:
            client = await self._get_client()
            resp = await client.post(
                "/api/display/disable", json={"display_id": display_id}
            )
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Disable display failed: {e}")
            return False

    async def set_duplicate(self, source_id: int, target_id: int) -> bool:
        """设置复制模式"""
        try:
            client = await self._get_client()
            resp = await client.post(
                "/api/display/duplicate",
                json={"source_id": source_id, "target_id": target_id},
            )
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Set duplicate failed: {e}")
            return False

    async def set_extend(self) -> bool:
        """设置扩展模式"""
        try:
            client = await self._get_client()
            resp = await client.post("/api/display/extend")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Set extend failed: {e}")
            return False

    async def start_deskflow(self) -> bool:
        """启动 Deskflow"""
        try:
            client = await self._get_client()
            resp = await client.post("/api/deskflow/start")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Start deskflow failed: {e}")
            return False

    async def stop_deskflow(self) -> bool:
        """停止 Deskflow"""
        try:
            client = await self._get_client()
            resp = await client.post("/api/deskflow/stop")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Stop deskflow failed: {e}")
            return False

    async def restart_deskflow(self) -> bool:
        """重启 Deskflow"""
        try:
            client = await self._get_client()
            resp = await client.post("/api/deskflow/restart")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Restart deskflow failed: {e}")
            return False

    async def get_deskflow_status(self) -> dict[str, Any] | None:
        """获取 Deskflow 状态"""
        try:
            client = await self._get_client()
            resp = await client.get("/api/deskflow/status")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            if data.success:
                return data.data
            return None
        except Exception as e:
            logger.error(f"Deskflow status failed: {e}")
            return None

    async def list_audio_devices(self) -> list[str]:
        """列出音频设备"""
        try:
            client = await self._get_client()
            resp = await client.get("/api/audio/devices")
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            if data.success and data.data:
                return data.data.get("devices", [])
            return []
        except Exception as e:
            logger.error(f"List audio devices failed: {e}")
            return []

    async def set_audio_device(self, device_name: str) -> bool:
        """设置音频设备"""
        try:
            client = await self._get_client()
            resp = await client.post("/api/audio/set", json={"device": device_name})
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Set audio device failed: {e}")
            return False

    async def set_mode(self, mode_name: str) -> bool:
        """通知远端切换模式"""
        try:
            client = await self._get_client()
            resp = await client.post("/api/mode/set", json={"mode": mode_name})
            resp.raise_for_status()
            data = AgentResponse(**resp.json())
            return data.success
        except Exception as e:
            logger.error(f"Set mode failed: {e}")
            return False

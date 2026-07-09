"""TandOrbit 模式切换动作

所有模式切换的具体动作实现。
"""

from __future__ import annotations

import asyncio
import platform
import time
from typing import Any

import httpx
from loguru import logger

from app.scheduler.action_pipeline import Action


class WakeWindowsAction(Action):
    """唤醒 Windows 并等待 Agent 上线"""

    def __init__(
        self,
        mac_address: str = "",
        agent_host: str = "192.168.1.100",
        agent_port: int = 5000,
        timeout: float = 60.0,
        poll_interval: float = 2.0,
    ) -> None:
        super().__init__("Wake Windows")
        self._mac_address = mac_address
        self._agent_host = agent_host
        self._agent_port = agent_port
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._was_online = False

    async def execute(self) -> bool:
        # 先检查 Agent 是否已经在线
        if await self._check_agent():
            logger.info("Windows Agent already online")
            self._was_online = True
            return True

        # 发送 WoL
        if not self._mac_address:
            self.error = "No MAC address configured for WoL"
            logger.error(self.error)
            return False

        logger.info(f"Sending WoL to {self._mac_address}")
        try:
            from plugins.wol.plugin import WoLPlugin
            wol = WoLPlugin(None)  # type: ignore
            await wol.wake(self._mac_address)
        except Exception as e:
            self.error = f"Failed to send WoL: {e}"
            logger.error(self.error)
            return False

        # 等待 Agent 上线
        logger.info(f"Waiting for Windows Agent at {self._agent_host}:{self._agent_port}")
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            if await self._check_agent():
                logger.info("Windows Agent is online!")
                return True
            await asyncio.sleep(self._poll_interval)

        self.error = f"Windows Agent did not come online within {self._timeout}s"
        logger.error(self.error)
        return False

    async def rollback(self) -> bool:
        # 如果之前不在线，唤醒后不需要回滚（保持原状）
        return True

    async def _check_agent(self) -> bool:
        """检查 Agent 是否在线"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"http://{self._agent_host}:{self._agent_port}/api/health"
                )
                return resp.status_code == 200
        except Exception:
            return False


class SleepWindowsAction(Action):
    """让 Windows 休眠"""

    def __init__(self, agent_host: str = "192.168.1.100", agent_port: int = 5000) -> None:
        super().__init__("Sleep Windows")
        self._agent_host = agent_host
        self._agent_port = agent_port

    async def execute(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"http://{self._agent_host}:{self._agent_port}/api/power/sleep"
                )
                if resp.status_code == 200:
                    logger.info("Windows sleep command sent")
                    return True
                # Agent 可能没有这个 endpoint，静默成功
                logger.warning("Windows Agent does not support sleep command")
                return True
        except Exception as e:
            # Windows 可能已经关机了，视为成功
            logger.info(f"Windows already offline or sleep failed: {e}")
            return True

    async def rollback(self) -> bool:
        return True


class SleepMacAction(Action):
    """让 Mac 休眠"""

    def __init__(self) -> None:
        super().__init__("Sleep Mac")

    async def execute(self) -> bool:
        if platform.system() != "Darwin":
            logger.info("Not on macOS, skipping Mac sleep")
            return True
        try:
            proc = await asyncio.create_subprocess_shell(
                "pmset sleepnow",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            success = proc.returncode == 0
            if success:
                logger.info("Mac sleep command sent")
            return success
        except Exception as e:
            self.error = f"Failed to sleep Mac: {e}"
            logger.error(self.error)
            return False

    async def rollback(self) -> bool:
        return True


class WakeMacAction(Action):
    """唤醒 Mac（通过 pmset）"""

    def __init__(self) -> None:
        super().__init__("Wake Mac")

    async def execute(self) -> bool:
        if platform.system() != "Darwin":
            return True
        # Mac 通常不需要特殊唤醒，它已经在运行
        logger.info("Mac is already running (it's the controller)")
        return True

    async def rollback(self) -> bool:
        return True


class ConfigureDisplaysForMac(Action):
    """配置显示器：双屏给 Mac"""

    def __init__(self, mac_display_plugin: Any = None, win_client: Any = None) -> None:
        super().__init__("Configure displays for Mac mode")
        self._mac_display = mac_display_plugin
        self._win_client = win_client

    async def execute(self) -> bool:
        logger.info("Configuring displays for Mac mode")
        # Mac 端：启用所有显示器
        if self._mac_display:
            try:
                await self._mac_display.set_extend()
            except Exception as e:
                logger.warning(f"Mac display config error: {e}")

        # Windows 端：禁用副屏（如果在线）
        if self._win_client:
            try:
                health = await self._win_client.health_check()
                if health:
                    await self._win_client.disable_display(2)
            except Exception:
                pass  # Windows 可能不在线

        return True

    async def rollback(self) -> bool:
        return True


class ConfigureDisplaysForWindows(Action):
    """配置显示器：双屏给 Windows"""

    def __init__(self, mac_display_plugin: Any = None, win_client: Any = None) -> None:
        super().__init__("Configure displays for Windows mode")
        self._mac_display = mac_display_plugin
        self._win_client = win_client

    async def execute(self) -> bool:
        logger.info("Configuring displays for Windows mode")
        # Mac 端：关闭副屏
        if self._mac_display:
            try:
                await self._mac_display.disable_display(2)
            except Exception as e:
                logger.warning(f"Mac display disable error: {e}")

        # Windows 端：启用所有显示器
        if self._win_client:
            try:
                await self._win_client.set_extend()
            except Exception as e:
                logger.warning(f"Windows display config error: {e}")

        return True

    async def rollback(self) -> bool:
        return True


class ConfigureDisplaysForShare(Action):
    """配置显示器：一屏 Mac，一屏 Windows"""

    def __init__(self, mac_display_plugin: Any = None, win_client: Any = None) -> None:
        super().__init__("Configure displays for Share mode")
        self._mac_display = mac_display_plugin
        self._win_client = win_client

    async def execute(self) -> bool:
        logger.info("Configuring displays for Share mode")
        # Mac：主屏留给自己，副屏禁用
        if self._mac_display:
            try:
                await self._mac_display.disable_display(2)
            except Exception as e:
                logger.warning(f"Mac display error: {e}")

        # Windows：启用主屏
        if self._win_client:
            try:
                await self._win_client.enable_display(1)
            except Exception as e:
                logger.warning(f"Windows display error: {e}")

        return True

    async def rollback(self) -> bool:
        return True


class RestartDeskflowAction(Action):
    """重启 Deskflow 键鼠共享"""

    def __init__(self, deskflow_plugin: Any = None) -> None:
        super().__init__("Restart Deskflow")
        self._deskflow = deskflow_plugin

    async def execute(self) -> bool:
        if not self._deskflow:
            logger.warning("Deskflow plugin not available")
            return True
        logger.info("Restarting Deskflow")
        return await self._deskflow.restart()

    async def rollback(self) -> bool:
        return True


class StopDeskflowAction(Action):
    """停止 Deskflow"""

    def __init__(self, deskflow_plugin: Any = None) -> None:
        super().__init__("Stop Deskflow")
        self._deskflow = deskflow_plugin

    async def execute(self) -> bool:
        if not self._deskflow:
            return True
        logger.info("Stopping Deskflow")
        return await self._deskflow.stop()

    async def rollback(self) -> bool:
        return True


class SetAudioMacAction(Action):
    """切换音频到 Mac 输出"""

    def __init__(self, audio_plugin: Any = None, device: str = "") -> None:
        super().__init__("Set audio to Mac")
        self._audio = audio_plugin
        self._device = device

    async def execute(self) -> bool:
        if not self._audio or not self._device:
            return True
        logger.info(f"Setting Mac audio to: {self._device}")
        return await self._audio.set_device(self._device)

    async def rollback(self) -> bool:
        return True


class SetAudioWindowsAction(Action):
    """切换音频到 Windows 输出"""

    def __init__(self, win_client: Any = None, device: str = "") -> None:
        super().__init__("Set audio to Windows")
        self._win_client = win_client
        self._device = device

    async def execute(self) -> bool:
        if not self._win_client or not self._device:
            return True
        logger.info(f"Setting Windows audio to: {self._device}")
        return await self._win_client.set_audio_device(self._device)

    async def rollback(self) -> bool:
        return True


class LocalDisplayOffAction(Action):
    """本地关闭所有显示器（Windows 端切到 Mac 模式时使用）"""

    def __init__(self, display_plugin: Any = None) -> None:
        super().__init__("Local display off")
        self._display = display_plugin

    async def execute(self) -> bool:
        if not self._display:
            logger.warning("No local display plugin")
            return True
        try:
            displays = await self._display.list_displays()
            for d in displays:
                logger.info(f"Disabling local display {d.id}: {d.name}")
                await self._display.disable_display(d.id)
            return True
        except Exception as e:
            logger.warning(f"Local display off error: {e}")
            return False

    async def rollback(self) -> bool:
        return True


class LocalDisplayOnAction(Action):
    """本地启用所有显示器（Windows 端切回 Windows 模式时使用）"""

    def __init__(self, display_plugin: Any = None) -> None:
        super().__init__("Local display on")
        self._display = display_plugin

    async def execute(self) -> bool:
        if not self._display:
            logger.warning("No local display plugin")
            return True
        logger.info("Enabling all local displays")
        try:
            # 启用所有显示器
            displays = await self._display.list_displays()
            for d in displays:
                if not d.is_enabled:
                    await self._display.enable_display(d.id)
            return True
        except Exception as e:
            logger.warning(f"Local display on error: {e}")
            return False

    async def rollback(self) -> bool:
        return True


class DisplaySleepAction(Action):
    """仅关闭显示器（不休眠电脑），让显示器自动识别其他信号源"""

    def __init__(self) -> None:
        super().__init__("Display Sleep")

    async def execute(self) -> bool:
        system = platform.system()
        try:
            if system == "Darwin":
                proc = await asyncio.create_subprocess_shell(
                    "pmset displaysleepnow",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                success = proc.returncode == 0
            elif system == "Windows":
                import ctypes
                # SC_MONITORPOWER = 0xF170, HWND_BROADCAST = 0xFFFF, WM_SYSCOMMAND = 0x0112
                # 2 = MONITOR_OFF
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                success = True
            else:
                logger.warning(f"Display sleep not supported on {system}")
                return False

            if success:
                logger.info("Display sleep command sent")
            return success
        except Exception as e:
            self.error = f"Failed to sleep display: {e}"
            logger.error(self.error)
            return False

    async def rollback(self) -> bool:
        return True

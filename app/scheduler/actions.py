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


class DelayAction(Action):
    """延迟执行（等待显示器切换信号源等）"""

    def __init__(self, seconds: float = 2.0, reason: str = "") -> None:
        super().__init__(f"Delay {seconds}s" + (f" ({reason})" if reason else ""))
        self._seconds = seconds
        self._reason = reason

    async def execute(self) -> bool:
        if self._reason:
            logger.info(f"Waiting {self._seconds}s: {self._reason}")
        await asyncio.sleep(self._seconds)
        return True

    async def rollback(self) -> bool:
        return True


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
        logger.info(f"Checking if Windows Agent is online at {self._agent_host}:{self._agent_port}")
        if await self._check_agent():
            logger.info("Windows Agent already online")
            self._was_online = True
            return True
        logger.info("Windows Agent not online, will send WoL")

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
    """配置显示器：唤醒全部 Mac 显示器（显示器自动识别信号源）"""

    def __init__(self, mac_display_plugin: Any = None) -> None:
        super().__init__("Configure displays for Mac mode")
        self._mac_display = mac_display_plugin

    async def execute(self) -> bool:
        logger.info("Configuring displays for Mac mode")
        # 唤醒 Mac 显示器，显示器会自动识别信号源
        if platform.system() == "Darwin":
            try:
                proc = await asyncio.create_subprocess_shell(
                    "caffeinate -u -t 1",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                logger.info("Mac displays woken up")
            except Exception as e:
                logger.warning(f"Mac display wake error: {e}")

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
        # Mac 端：断开副屏 + 休眠所有显示器
        if self._mac_display:
            try:
                await self._mac_display.disable_display(2)
            except Exception as e:
                logger.warning(f"Mac display disable error: {e}")

        if platform.system() == "Darwin":
            try:
                proc = await asyncio.create_subprocess_shell(
                    "pmset displaysleepnow",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                logger.info("Mac displays put to sleep")
            except Exception as e:
                logger.warning(f"Mac display sleep error: {e}")

        # 等待显示器切换输入源
        await asyncio.sleep(2.0)

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
    """配置显示器：Mac 保留主屏，关闭副屏（让 Windows 接管）"""

    def __init__(self, mac_display_plugin: Any = None) -> None:
        super().__init__("Configure displays for Share mode")
        self._mac_display = mac_display_plugin

    async def execute(self) -> bool:
        logger.info("Configuring displays for Share mode")
        # 唤醒 Mac 主屏
        if platform.system() == "Darwin":
            try:
                proc = await asyncio.create_subprocess_shell(
                    "caffeinate -u -t 1",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                logger.info("Mac displays woken up")
            except Exception as e:
                logger.warning(f"Mac display wake error: {e}")

        # 关闭 Mac 副屏（screen_off 而非 disable，不断开连接）
        if self._mac_display:
            try:
                await self._mac_display.screen_off(2)
                logger.info("Mac secondary display screen off")
            except Exception as e:
                logger.warning(f"Mac secondary display off error: {e}")

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

    def __init__(self) -> None:
        super().__init__("Local display off")

    async def execute(self) -> bool:
        if platform.system() != "Windows":
            return True
        try:
            import ctypes
            # 多次发送关闭命令，防止 Windows 唤醒主显示器
            for _ in range(5):
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                await asyncio.sleep(0.5)
            logger.info("All local displays off")
            return True
        except Exception as e:
            logger.warning(f"Local display off error: {e}")
            return False

    async def rollback(self) -> bool:
        return True


class LocalDisplayShareAction(Action):
    """本地共享模式：保留指定显示器，关闭其他（留给 Mac）"""

    def __init__(self, display_plugin: Any = None, keep_display_id: int = 2) -> None:
        super().__init__("Local display share")
        self._display = display_plugin
        self._keep_id = keep_display_id

    async def execute(self) -> bool:
        if not self._display:
            logger.warning("No local display plugin")
            return True
        try:
            displays = await self._display.list_displays()
            for d in displays:
                if d.id != self._keep_id:
                    logger.info(f"Disabling display {d.id} for Mac: {d.name}")
                    await self._display.disable_display(d.id)
            logger.info(f"Keeping display {self._keep_id} for Windows")
            return True
        except Exception as e:
            logger.warning(f"Local display share error: {e}")
            return False

    async def rollback(self) -> bool:
        return True


class SetWindowsDuplicateAction(Action):
    """Windows 端切换到复制模式（双屏显示相同内容）"""

    def __init__(self, display_plugin: Any = None) -> None:
        super().__init__("Set Windows duplicate mode")
        self._display = display_plugin

    async def execute(self) -> bool:
        if not self._display:
            logger.warning("No display plugin available")
            return True
        try:
            ok = await self._display.set_duplicate(1, 2)
            if ok:
                logger.info("Windows switched to duplicate mode")
            else:
                logger.warning("Failed to set Windows duplicate mode")
            return ok
        except Exception as e:
            logger.warning(f"Set Windows duplicate error: {e}")
            return False

    async def rollback(self) -> bool:
        return True


class LocalDisplaySleepPrimaryAction(Action):
    """Windows 端让主屏休眠（保留副屏给 Windows，主屏触发硬件信号切换给 Mac）

    DP 连接无法真正断开，只能通过 Win32 API 让显示器休眠，
    触发显示器自动切换到另一个信号源。
    """

    def __init__(self) -> None:
        super().__init__("Local display sleep primary")

    async def execute(self) -> bool:
        if platform.system() != "Windows":
            return True
        try:
            import ctypes
            # SC_MONITORPOWER = 0xF170, HWND_BROADCAST = 0xFFFF, WM_SYSCOMMAND = 0x0112
            # 2 = MONITOR_OFF
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            logger.info("Windows primary display put to sleep")
            return True
        except Exception as e:
            logger.warning(f"Local display sleep error: {e}")
            return False

    async def rollback(self) -> bool:
        return True


class LocalDisplayOnAction(Action):
    """本地启用所有显示器（Windows 端切回 Windows 模式时使用）"""

    def __init__(self, display_plugin: Any = None) -> None:
        super().__init__("Local display on")
        self._display = display_plugin

    async def execute(self) -> bool:
        if platform.system() != "Windows":
            return True
        try:
            # 先用 MultiMonitorTool 启用所有显示器
            if self._display:
                displays = await self._display.list_displays()
                for d in displays:
                    if not d.is_enabled:
                        logger.info(f"Enabling display {d.id}: {d.name}")
                        await self._display.enable_display(d.id)
            # 再用 Windows API 唤醒
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
            logger.info("All local displays on")
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

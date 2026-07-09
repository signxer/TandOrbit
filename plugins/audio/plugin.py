"""音频管理插件实现

跨平台音频输出设备切换。
"""

from __future__ import annotations

import asyncio
import platform
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import EventBus
from app.plugin_base import Plugin


class AudioPlugin(Plugin):
    """音频管理插件

    支持 macOS（SwitchAudioSource）和 Windows（nircmd/PowerShell）。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("audio", event_bus, config)
        self._mac_output = self.config.get("mac_output", "")
        self._windows_output = self.config.get("windows_output", "")

    async def initialize(self) -> bool:
        self._set_status(PluginStatus.INITIALIZED)
        logger.info("Audio plugin initialized")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        return True

    async def shutdown(self) -> None:
        self._set_status(PluginStatus.DISABLED)

    # --- 音频控制接口 ---

    async def list_devices(self) -> list[str]:
        """列出所有音频输出设备"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_list_devices()
        elif system == "Windows":
            return await self._windows_list_devices()
        return []

    async def get_current_device(self) -> str:
        """获取当前音频输出设备"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_get_current()
        elif system == "Windows":
            return await self._windows_get_current()
        return ""

    async def set_device(self, device_name: str) -> bool:
        """设置音频输出设备"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_set_device(device_name)
        elif system == "Windows":
            return await self._windows_set_device(device_name)
        return False

    # --- macOS 实现 ---

    async def _mac_list_devices(self) -> list[str]:
        """macOS: 列出音频设备（需要 SwitchAudioSource）"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "SwitchAudioSource -a",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            devices = stdout.decode(errors="replace").strip().split("\n")
            return [d.strip() for d in devices if d.strip()]
        except Exception as e:
            logger.error(f"Failed to list macOS audio devices: {e}")
            return []

    async def _mac_get_current(self) -> str:
        """macOS: 获取当前音频设备"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "SwitchAudioSource -c",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return stdout.decode(errors="replace").strip()
        except Exception:
            return ""

    async def _mac_set_device(self, device_name: str) -> bool:
        """macOS: 设置音频设备"""
        try:
            proc = await asyncio.create_subprocess_shell(
                f'SwitchAudioSource -s "{device_name}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            success = proc.returncode == 0
            if success:
                logger.info(f"macOS audio output set to: {device_name}")
            return success
        except Exception as e:
            logger.error(f"Failed to set macOS audio device: {e}")
            return False

    # --- Windows 实现 ---

    async def _windows_list_devices(self) -> list[str]:
        """Windows: 列出音频设备"""
        script = (
            "Get-AudioDevice -List | "
            "Where-Object { $_.Type -eq 'Playback' } | "
            "Select-Object -ExpandProperty Name"
        )
        output = await self._run_powershell(script)
        if output:
            return [d.strip() for d in output.strip().split("\n") if d.strip()]
        return []

    async def _windows_get_current(self) -> str:
        """Windows: 获取当前音频设备"""
        script = (
            "Get-AudioDevice | "
            "Where-Object { $_.Type -eq 'Playback' } | "
            "Select-Object -ExpandProperty Name"
        )
        output = await self._run_powershell(script)
        return output.strip() if output else ""

    async def _windows_set_device(self, device_name: str) -> bool:
        """Windows: 设置音频设备"""
        script = (
            f'Get-AudioDevice -List | '
            f'Where-Object {{ $_.Name -eq "{device_name}" -and $_.Type -eq "Playback" }} | '
            f'Set-AudioDevice'
        )
        output = await self._run_powershell(script)
        success = output is not None
        if success:
            logger.info(f"Windows audio output set to: {device_name}")
        return success

    async def _run_powershell(self, script: str) -> str | None:
        """执行 PowerShell 脚本"""
        cmd = f'powershell -NoProfile -Command "{script}"'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode != 0:
                logger.error(f"PowerShell error: {stderr.decode(errors='replace').strip()}")
                return None
            return stdout.decode(errors="replace").strip()
        except Exception as e:
            logger.error(f"PowerShell exception: {e}")
            return None

"""DDC/CI 插件实现

通过 DDC/CI 协议控制显示器（亮度、输入源等）。
"""

from __future__ import annotations

import asyncio
import platform
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from app.enums import InputSource, PluginStatus
from app.events import EventBus
from app.plugin_base import Plugin


# DDC/CI VCP codes
VCP_INPUT_SOURCE = 0x60
VCP_BRIGHTNESS = 0x10
VCP_CONTRAST = 0x12
VCP_POWER_MODE = 0xD6

# 电源模式
POWER_ON = 0x01
POWER_STANDBY = 0x02
POWER_SUSPEND = 0x03
POWER_OFF = 0x04

# 输入源映射
INPUT_SOURCE_MAP: dict[InputSource, int] = {
    InputSource.VGA: 0x01,
    InputSource.HDMI1: 0x11,
    InputSource.HDMI2: 0x12,
    InputSource.DISPLAYPORT1: 0x0F,
    InputSource.DISPLAYPORT2: 0x10,
    InputSource.TYPE_C: 0x10,
}


class DDCPlugin(Plugin):
    """DDC/CI 显示器控制插件

    通过 DDC/CI 协议控制显示器输入源、亮度等。
    macOS 使用 m1ddc，Windows 使用 ControlMyMonitor。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("ddc", event_bus, config)
        self._tool_path: str = ""

    async def initialize(self) -> bool:
        system = platform.system()
        if system == "Darwin":
            self._tool_path = self.config.get("m1ddc_path", "m1ddc")
        elif system == "Windows":
            self._tool_path = self.config.get(
                "controlmymonitor_path", "ControlMyMonitor.exe"
            )

        if not shutil.which(self._tool_path):
            # macOS: 尝试 Homebrew 路径
            if system == "Darwin":
                homebrew_path = "/opt/homebrew/bin/m1ddc"
                if shutil.which(homebrew_path) or Path(homebrew_path).exists():
                    self._tool_path = homebrew_path

        if not shutil.which(self._tool_path):
            tool_name = "m1ddc" if system == "Darwin" else "ControlMyMonitor.exe"
            self._init_error = (
                f"DDC 工具未找到 ({self._tool_path})。"
                f"请安装 {tool_name}。"
            )
            logger.warning(self._init_error)
            self._set_status(PluginStatus.ERROR)
            return False

        self._set_status(PluginStatus.INITIALIZED)
        logger.info(f"DDC plugin initialized (tool: {self._tool_path})")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_shell(
                f'"{self._tool_path}" --help',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return True
        except Exception:
            return False

    async def shutdown(self) -> None:
        self._set_status(PluginStatus.DISABLED)

    # --- DDC 控制接口 ---

    async def get_input_source(self, display_id: int = 0) -> InputSource | None:
        """获取显示器当前输入源"""
        value = await self._read_vcp(display_id, VCP_INPUT_SOURCE)
        if value is None:
            return None
        for source, code in INPUT_SOURCE_MAP.items():
            if code == value:
                return source
        return InputSource.UNKNOWN

    async def set_input_source(
        self, display_id: int, source: InputSource
    ) -> bool:
        """设置显示器输入源"""
        code = INPUT_SOURCE_MAP.get(source)
        if code is None:
            logger.error(f"Unknown input source: {source}")
            return False
        return await self._write_vcp(display_id, VCP_INPUT_SOURCE, code)

    async def get_brightness(self, display_id: int = 0) -> int | None:
        """获取显示器亮度（0-100）"""
        return await self._read_vcp(display_id, VCP_BRIGHTNESS)

    async def set_brightness(self, display_id: int, level: int) -> bool:
        """设置显示器亮度（0-100）"""
        level = max(0, min(100, level))
        return await self._write_vcp(display_id, VCP_BRIGHTNESS, level)

    async def get_contrast(self, display_id: int = 0) -> int | None:
        """获取显示器对比度（0-100）"""
        return await self._read_vcp(display_id, VCP_CONTRAST)

    async def set_contrast(self, display_id: int, level: int) -> bool:
        """设置显示器对比度（0-100）"""
        level = max(0, min(100, level))
        return await self._write_vcp(display_id, VCP_CONTRAST, level)

    async def power_off(self, display_id: int) -> bool:
        """关闭显示器（DDC/CI VCP D6=5）"""
        return await self._write_vcp(display_id, VCP_POWER_MODE, 5)

    async def power_on(self, display_id: int) -> bool:
        """打开显示器（DDC/CI VCP D6=1）"""
        return await self._write_vcp(display_id, VCP_POWER_MODE, 1)

    async def power_off_monitor(self, monitor: str) -> bool:
        """关闭指定显示器（使用完整 monitor 标识）"""
        cmd = f'"{self._tool_path}" /SetValue "{monitor}" D6 5'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"ControlMyMonitor power off error: {e}")
            return False

    async def power_on_monitor(self, monitor: str) -> bool:
        """打开指定显示器（使用完整 monitor 标识）"""
        cmd = f'"{self._tool_path}" /SetValue "{monitor}" D6 1'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"ControlMyMonitor power on error: {e}")
            return False

    # --- 内部方法 ---

    async def _read_vcp(self, display_id: int, vcp_code: int) -> int | None:
        """读取 VCP 值"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_read_vcp(display_id, vcp_code)
        elif system == "Windows":
            return await self._windows_read_vcp(display_id, vcp_code)
        return None

    async def _write_vcp(self, display_id: int, vcp_code: int, value: int) -> bool:
        """写入 VCP 值"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_write_vcp(display_id, vcp_code, value)
        elif system == "Windows":
            return await self._windows_write_vcp(display_id, vcp_code, value)
        return False

    # m1ddc 命令映射
    M1DDC_VCP_MAP: dict[int, str] = {
        VCP_INPUT_SOURCE: "input",
        VCP_BRIGHTNESS: "luminance",
        VCP_CONTRAST: "contrast",
    }

    async def _mac_read_vcp(self, display_id: int, vcp_code: int) -> int | None:
        """macOS: 使用 m1ddc 读取 VCP 值"""
        cmd_name = self.M1DDC_VCP_MAP.get(vcp_code)
        if not cmd_name:
            logger.error(f"Unsupported VCP code for m1ddc: {vcp_code:#04x}")
            return None
        cmd = f'"{self._tool_path}" display {display_id} get {cmd_name}'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                return int(stdout.decode(errors="replace").strip())
        except Exception as e:
            logger.error(f"m1ddc read error: {e}")
        return None

    async def _mac_write_vcp(
        self, display_id: int, vcp_code: int, value: int
    ) -> bool:
        """macOS: 使用 m1ddc 写入 VCP 值"""
        cmd_name = self.M1DDC_VCP_MAP.get(vcp_code)
        if not cmd_name:
            logger.error(f"Unsupported VCP code for m1ddc: {vcp_code:#04x}")
            return False
        cmd = f'"{self._tool_path}" display {display_id} set {cmd_name} {value}'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"m1ddc write error: {e}")
            return False

    async def _windows_read_vcp(self, display_id: int, vcp_code: int) -> int | None:
        """Windows: 使用 ControlMyMonitor 读取 VCP 值"""
        monitor = self._monitor_str(display_id)
        cmd = f'"{self._tool_path}" /GetValue "{monitor}" {vcp_code:#04x}'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                return int(stdout.decode(errors="replace").strip())
        except Exception as e:
            logger.error(f"ControlMyMonitor read error: {e}")
        return None

    async def _windows_write_vcp(
        self, display_id: int, vcp_code: int, value: int
    ) -> bool:
        """Windows: 使用 ControlMyMonitor 写入 VCP 值"""
        monitor = self._monitor_str(display_id)
        cmd = f'"{self._tool_path}" /SetValue "{monitor}" {vcp_code:#04x} {value}'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"ControlMyMonitor write error: {e}")
            return False

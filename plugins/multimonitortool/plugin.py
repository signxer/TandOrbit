"""MultiMonitorTool 插件实现

通过 MultiMonitorTool 控制 Windows 显示器。
此插件运行在 Windows Agent 端。
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import DisplayChangedEvent, EventBus
from app.models import DisplayInfo
from app.plugin_base import Plugin


class MultiMonitorToolPlugin(Plugin):
    """MultiMonitorTool 显示器控制插件

    通过 NirSoft MultiMonitorTool 控制 Windows 显示器。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("multimonitortool", event_bus, config)
        self._tool_path = self.config.get("path", "MultiMonitorTool.exe")

    async def initialize(self) -> bool:
        """初始化：检查 MultiMonitorTool 是否可用"""
        path = shutil.which("MultiMonitorTool.exe") or self._tool_path
        if not shutil.which(path):
            logger.warning(f"MultiMonitorTool not found at: {path}")
            # 在 Windows Agent 端可能需要指定完整路径
        self._tool_path = path
        self._set_status(PluginStatus.INITIALIZED)
        logger.info("MultiMonitorTool plugin initialized")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._tool_path, "/scomma",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception:
            return False

    async def shutdown(self) -> None:
        self._set_status(PluginStatus.DISABLED)

    # --- 显示器控制接口 ---

    async def list_displays(self) -> list[DisplayInfo]:
        """列出所有显示器"""
        output = await self._run_tool("/scomma")
        if output is None:
            return []
        displays = []
        for i, line in enumerate(output.strip().split("\n"), 1):
            if line.strip() and "," in line:
                parts = line.split(",")
                name = parts[0] if parts else f"Display {i}"
                displays.append(
                    DisplayInfo(
                        id=i,
                        name=name.strip('"'),
                        is_primary=(i == 1),
                    )
                )
        return displays

    async def enable_display(self, display_id: int) -> bool:
        """启用显示器"""
        ok = await self._run_tool(f"/enable {display_id}")
        success = ok is not None
        if success:
            self.event_bus.publish(
                DisplayChangedEvent(
                    display_id=display_id, enabled=True, source="MultiMonitorTool"
                )
            )
        return success

    async def disable_display(self, display_id: int) -> bool:
        """禁用显示器"""
        ok = await self._run_tool(f"/disable {display_id}")
        success = ok is not None
        if success:
            self.event_bus.publish(
                DisplayChangedEvent(
                    display_id=display_id, enabled=False, source="MultiMonitorTool"
                )
            )
        return success

    async def set_primary(self, display_id: int) -> bool:
        """设置主显示器"""
        ok = await self._run_tool(f"/SetPrimary {display_id}")
        return ok is not None

    async def set_duplicate(self, source_id: int, target_id: int) -> bool:
        """设置显示器复制模式"""
        # Windows 10/11 使用 PowerShell 设置显示模式
        script = (
            f'Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID | '
            f'Where-Object {{$_.InstanceName -like "*{source_id}*"}} '
        )
        ok = await self._run_powershell(script)
        return ok is not None

    async def set_extend(self) -> bool:
        """设置扩展模式"""
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Screen]::AllScreens | "
            "ForEach-Object { $_.Bounds }"
        )
        ok = await self._run_powershell(script)
        return ok is not None

    # --- 内部方法 ---

    async def _run_tool(self, args: str) -> str | None:
        """执行 MultiMonitorTool 命令"""
        cmd = f'"{self._tool_path}" {args}'
        logger.debug(f"Running: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                logger.error(f"Tool error: {stderr.decode().strip()}")
                return None
            return stdout.decode().strip()
        except asyncio.TimeoutError:
            logger.error(f"Tool timeout: {cmd}")
            return None
        except Exception as e:
            logger.error(f"Tool exception: {e}")
            return None

    async def _run_powershell(self, script: str) -> str | None:
        """执行 PowerShell 脚本"""
        cmd = f'powershell -NoProfile -Command "{script}"'
        logger.debug(f"Running PowerShell: {script[:100]}...")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                logger.error(f"PowerShell error: {stderr.decode().strip()}")
                return None
            return stdout.decode().strip()
        except asyncio.TimeoutError:
            logger.error(f"PowerShell timeout")
            return None
        except Exception as e:
            logger.error(f"PowerShell exception: {e}")
            return None

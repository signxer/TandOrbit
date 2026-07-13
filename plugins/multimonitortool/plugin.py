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
        self._tool_path = self.config.get("multimonitortool_path", "MultiMonitorTool.exe")

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
        import csv
        import io
        import re

        output = await self._run_tool("/scomma")
        if output is None:
            return []
        displays = []
        reader = csv.reader(io.StringIO(output))
        header = next(reader, None)  # 跳过表头
        if not header:
            return []
        for row in reader:
            if len(row) < 13:
                continue
            # Name 列 (index 12): \\.\DISPLAY1
            name_col = row[12].strip()
            match = re.search(r"DISPLAY(\d+)", name_col)
            display_id = int(match.group(1)) if match else len(displays) + 1
            # Short Monitor ID (index 17) 作为可读名称
            short_id = row[17].strip() if len(row) > 17 else ""
            # Resolution (index 0)
            resolution = row[0].strip()
            # Primary (index 5): Yes/No
            is_primary = row[5].strip().lower() == "yes" if len(row) > 5 else False
            # 构建显示名称: "SDX32AC (3840x2160) PRIMARY" 或 "ICD3208 (3840x2160)"
            label = f"{short_id} ({resolution})" if short_id else f"Display {display_id} ({resolution})"
            displays.append(
                DisplayInfo(
                    id=display_id,
                    name=label,
                    is_primary=is_primary,
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

    async def set_extend_mode(self) -> bool:
        """设置扩展模式（通过 Windows API SetDisplayConfig）"""
        script = (
            "Add-Type @'\n"
            "using System.Runtime.InteropServices;\n"
            "public class Display {\n"
            "  [DllImport(\"user32.dll\")] public static extern int SetDisplayConfig(uint numPathArrayElements, IntPtr pathArray, uint numModeInfoArrayElements, IntPtr modeInfoArray, uint flags);\n"
            "}\n"
            "'@\n"
            "[Display]::SetDisplayConfig(0, [IntPtr]::Zero, 0, [IntPtr]::Zero, 0x00000002 -bor 0x00000040)"
        )
        ok = await self._run_powershell(script)
        success = ok is not None
        if success:
            logger.info("Display mode set to extend")
        return success

    async def set_clone_mode(self) -> bool:
        """设置复制模式（通过 Windows API SetDisplayConfig）"""
        script = (
            "Add-Type @'\n"
            "using System.Runtime.InteropServices;\n"
            "public class Display {\n"
            "  [DllImport(\"user32.dll\")] public static extern int SetDisplayConfig(uint numPathArrayElements, IntPtr pathArray, uint numModeInfoArrayElements, IntPtr modeInfoArray, uint flags);\n"
            "}\n"
            "'@\n"
            "[Display]::SetDisplayConfig(0, [IntPtr]::Zero, 0, [IntPtr]::Zero, 0x00000001 -bor 0x00000040)"
        )
        ok = await self._run_powershell(script)
        success = ok is not None
        if success:
            logger.info("Display mode set to clone")
        return success

    # --- 内部方法 ---

    async def _run_tool(self, args: str) -> str | None:
        """执行 MultiMonitorTool 命令（通过 PowerShell 包装，避免 GUI 程序阻塞）"""
        import os
        import tempfile

        # 读取类命令（/scomma, /sxml 等）需要输出文件；操作类命令（/enable, /disable 等）不需要
        is_read = args.strip().lower().startswith("/s")
        if is_read:
            output_file = os.path.join(tempfile.gettempdir(), "tandorbit_mmt_out.csv")
            mmt_args = f"{args} '{output_file}'"
        else:
            output_file = None
            mmt_args = args

        cmd = f"powershell -NoProfile -Command \"& '{self._tool_path}' {mmt_args}\""
        logger.debug(f"Running: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                logger.error(f"Tool error: {stderr.decode(errors='replace').strip()}")
                return None
            if output_file and os.path.exists(output_file):
                with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                    result = f.read().strip()
                os.remove(output_file)
                return result
            return stdout.decode(errors="replace").strip()
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
                logger.error(f"PowerShell error: {stderr.decode(errors='replace').strip()}")
                return None
            return stdout.decode(errors="replace").strip()
        except asyncio.TimeoutError:
            logger.error(f"PowerShell timeout")
            return None
        except Exception as e:
            logger.error(f"PowerShell exception: {e}")
            return None

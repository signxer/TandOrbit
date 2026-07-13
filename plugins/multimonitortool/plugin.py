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

# SetDisplayConfig flags
SDC_TOPOLOGY_SUPPRESS = 0x00000001
SDC_TOPOLOGY_EXTEND = 0x00000002
SDC_TOPOLOGY_CLONE = 0x00000004
SDC_APPLY = 0x00000040

# SetDisplayConfig return codes
ERROR_SUCCESS = 0

# PowerShell script to define SetDisplayConfig (written to temp file to avoid escaping issues)
_SETDISPLAYCONFIG_SCRIPT = """\
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class DisplayConfig {{
    [DllImport("user32.dll", SetLastError = true)]
    public static extern int SetDisplayConfig(
        uint numPathArrayElements,
        IntPtr pathArray,
        uint numModeInfoArrayElements,
        IntPtr modeInfoArray,
        uint flags
    );
}}
"@
"""


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
            # Active (index 4): Yes/No — 显示器是否启用
            is_enabled = row[4].strip().lower() == "yes" if len(row) > 4 else True
            # 构建显示名称
            label = f"{short_id} ({resolution})" if short_id else f"Display {display_id} ({resolution})"
            displays.append(
                DisplayInfo(
                    id=display_id,
                    name=label,
                    is_primary=is_primary,
                    is_enabled=is_enabled,
                )
            )
        return displays

    async def enable_display(self, display_id: int, retries: int = 2) -> bool:
        """启用显示器（带重试）"""
        for attempt in range(retries + 1):
            ok = await self._run_tool(f"/enable {display_id}")
            if ok is not None:
                self.event_bus.publish(
                    DisplayChangedEvent(
                        display_id=display_id, enabled=True, source="MultiMonitorTool"
                    )
                )
                return True
            if attempt < retries:
                logger.warning(f"enable_display({display_id}) attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(2.0)
        return False

    async def disable_display(self, display_id: int, retries: int = 2) -> bool:
        """禁用显示器（带重试）"""
        for attempt in range(retries + 1):
            ok = await self._run_tool(f"/disable {display_id}")
            if ok is not None:
                self.event_bus.publish(
                    DisplayChangedEvent(
                        display_id=display_id, enabled=False, source="MultiMonitorTool"
                    )
                )
                return True
            if attempt < retries:
                logger.warning(f"disable_display({display_id}) attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(2.0)
        return False

    async def set_primary(self, display_id: int) -> bool:
        """设置主显示器"""
        ok = await self._run_tool(f"/SetPrimary {display_id}")
        return ok is not None

    async def set_extend_mode(self, retries: int = 2) -> bool:
        """设置扩展模式（通过 Windows API SetDisplayConfig）"""
        return await self._set_display_config(SDC_TOPOLOGY_EXTEND | SDC_APPLY, "extend", retries)

    async def set_clone_mode(self, retries: int = 2) -> bool:
        """设置复制模式（通过 Windows API SetDisplayConfig）"""
        return await self._set_display_config(SDC_TOPOLOGY_CLONE | SDC_APPLY, "clone", retries)

    async def verify_display_mode(self, expected: str, timeout: float = 5.0) -> bool:
        """验证当前显示器拓扑是否匹配预期

        通过 list_displays 检查显示器数量和状态来推断模式。
        clone 模式下所有显示器分辨率相同且数量>=2，extend 下可能不同。
        这是一个 best-effort 验证。
        """
        try:
            displays = await self.list_displays()
            enabled = [d for d in displays if d.is_enabled]
            if expected == "clone":
                # clone 模式至少需要 2 个启用的显示器
                return len(enabled) >= 2
            elif expected == "extend":
                # extend 模式至少需要 1 个启用的显示器
                return len(enabled) >= 1
        except Exception as e:
            logger.warning(f"Display mode verification failed: {e}")
        return False

    # --- 内部方法 ---

    async def _set_display_config(self, flags: int, mode_name: str, retries: int = 2) -> bool:
        """调用 SetDisplayConfig API（带重试和返回值检查）"""
        # 用临时 .ps1 文件避免引号转义问题
        script = (
            _SETDISPLAYCONFIG_SCRIPT
            + f"$result = [DisplayConfig]::SetDisplayConfig(0, [IntPtr]::Zero, 0, [IntPtr]::Zero, 0x{flags:08X})\n"
            + "if ($result -ne 0) { Write-Error \"SetDisplayConfig failed with code $result\"; exit 1 }\n"
            + "Write-Output \"OK\"\n"
        )

        for attempt in range(retries + 1):
            ok = await self._run_powershell_script(script)
            if ok is not None:
                logger.info(f"Display mode set to {mode_name}")
                return True
            if attempt < retries:
                logger.warning(f"set_{mode_name}_mode attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(2.0)
        logger.error(f"Failed to set display mode to {mode_name} after {retries + 1} attempts")
        return False

    async def _run_tool(self, args: str) -> str | None:
        """执行 MultiMonitorTool 命令（通过 PowerShell 包装，避免 GUI 程序阻塞）"""
        import os
        import tempfile

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

    async def _run_powershell_script(self, script: str) -> str | None:
        """执行 PowerShell 脚本（通过临时 .ps1 文件，避免转义问题）"""
        import os
        import tempfile

        # 写入临时 .ps1 文件，彻底避免命令行转义问题
        ps1_path = os.path.join(tempfile.gettempdir(), "tandorbit_mmt_script.ps1")
        try:
            with open(ps1_path, "w", encoding="utf-8") as f:
                f.write(script)

            cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}"'
            logger.debug(f"Running PowerShell script: {ps1_path}")
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20.0)
            if proc.returncode != 0:
                logger.error(f"PowerShell error: {stderr.decode(errors='replace').strip()}")
                return None
            return stdout.decode(errors="replace").strip()
        except asyncio.TimeoutError:
            logger.error("PowerShell timeout")
            return None
        except Exception as e:
            logger.error(f"PowerShell exception: {e}")
            return None
        finally:
            try:
                os.remove(ps1_path)
            except OSError:
                pass

"""MultiMonitorTool 插件实现

通过 MultiMonitorTool + Windows API 控制 Windows 显示器。
此插件运行在 Windows Agent 端。

- 显示器枚举：PowerShell P/Invoke EnumDisplayDevices（不再依赖 MultiMonitorTool 的
  /scomma —— 该工具官方命令行选项中没有 /scomma，旧实现无法可靠读取显示器列表）
- 拓扑切换：Windows API SetDisplayConfig（extend / clone）
- 禁用/启用：MultiMonitorTool /disable /enable（按 DISPLAY 编号）
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
# 注意：此脚本通过字符串拼接使用（不调用 .format()），花括号必须为单括号
_SETDISPLAYCONFIG_SCRIPT = r"""\
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class DisplayConfig {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern int SetDisplayConfig(
        uint numPathArrayElements,
        IntPtr pathArray,
        uint numModeInfoArrayElements,
        IntPtr modeInfoArray,
        uint flags
    );
}
"@
"""

# PowerShell script to enumerate displays via EnumDisplayDevices.
# 输出：JSON 数组 [{id, name, is_primary, is_enabled, width, height}]
# 使用 System.Windows.Forms.Screen.AllScreens（.NET 原生，稳定返回活动显示器），
# 避免 P/Invoke EnumDisplayDevices 在某些系统枚举不到 DISPLAYn 的情况。
_ENUM_DISPLAYS_SCRIPT = r"""\
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct DISPLAY_DEVICE_EDID {
    public int cb;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string DeviceName;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceString;
    public int StateFlags;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceID;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceKey;
}
public class EnumDisplay {
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern bool EnumDisplayDevices(
        string lpDevice, uint iDevNum, ref DISPLAY_DEVICE_EDID lpDisplayDevice, uint dwFlags);
}
"@
$results = @()
foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
    if ($s.DeviceName -match 'DISPLAY(\d+)') {
        $id = [int]$Matches[1]
        $name = $s.DeviceName
        $monitor_id = ''
        $device_id = ''
        # 补充查询：用 EnumDisplayDevices 获得显示器型号名（DeviceString）和 DeviceID
        $dd = New-Object DISPLAY_DEVICE_EDID
        $dd.cb = [System.Runtime.InteropServices.Marshal]::SizeOf([DISPLAY_DEVICE_EDID])
        if ([EnumDisplay]::EnumDisplayDevices($s.DeviceName, 0, [ref]$dd, 0)) {
            if ($dd.DeviceString -match '\S+') {
                $name = $dd.DeviceString
            }
            $monitor_id = [string]$dd.DeviceID
            $device_id = [string]$dd.DeviceKey
        }
        $results += [pscustomobject]@{
            id         = $id
            name       = $name
            is_primary = $s.Primary
            is_enabled = $true
            width      = $s.Bounds.Width
            height     = $s.Bounds.Height
            monitor_id = $monitor_id
            device_id  = $device_id
        }
    }
}
$results | ConvertTo-Json -Compress
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
        path = self._tool_path
        # 先查 PATH，再查配置的绝对路径，不存在的绝对路径直接跳过
        if shutil.which("MultiMonitorTool.exe"):
            path = shutil.which("MultiMonitorTool.exe")
        elif path and not shutil.which(path) and not Path(path).exists():
            logger.warning(f"MultiMonitorTool not found at: {path}（配置路径不存在或不在 PATH 中）")
        self._tool_path = path
        self._set_status(PluginStatus.INITIALIZED)
        logger.info(f"MultiMonitorTool plugin initialized (tool: {path})")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        """健康检查：执行一次显示器枚举验证 PowerShell 可用"""
        try:
            output = await self._run_powershell_script(_ENUM_DISPLAYS_SCRIPT, timeout=8.0)
            return output is not None
        except Exception:
            return False

    async def shutdown(self) -> None:
        self._set_status(PluginStatus.DISABLED)

    # --- 显示器控制接口 ---

    async def list_displays(self) -> list[DisplayInfo]:
        """列出所有显示器（EnumDisplayDevices，含已禁用/未连接的显示器）"""
        output = await self._run_powershell_script(_ENUM_DISPLAYS_SCRIPT)
        if output is None:
            logger.warning("显示器枚举脚本执行失败（返回 None），无法获取显示器列表")
            return []
        displays = self._parse_displays(output)
        if not displays:
            logger.warning(
                f"显示器枚举脚本执行成功但返回空列表，输出内容: {output[:200] if output else '(空)'}"
            )
        return displays

    @staticmethod
    def _parse_displays(output: str) -> list[DisplayInfo]:
        """解析 EnumDisplayDevices JSON 输出（纯函数，便于测试）"""
        import json

        output = (output or "").strip()
        if not output:
            return []
        try:
            items = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse display list JSON: {e}")
            return []
        displays: list[DisplayInfo] = []
        for item in items:
            try:
                display_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            displays.append(
                DisplayInfo(
                    id=display_id,
                    name=str(item.get("name") or f"Display {display_id}"),
                    is_primary=bool(item.get("is_primary", False)),
                    is_enabled=bool(item.get("is_enabled", False)),
                    width=int(item.get("width", 0) or 0),
                    height=int(item.get("height", 0) or 0),
                    monitor_id=str(item.get("monitor_id", "") or ""),
                    device_id=str(item.get("device_id", "") or ""),
                )
            )
        return displays

    @staticmethod
    def find_display_by_identity(
        displays: list[DisplayInfo],
        monitor_id: str,
    ) -> DisplayInfo | None:
        """按 Monitor ID / Device ID 查找显示器（身份优先，不受 DISPLAY 编号漂移影响）

        匹配规则：
        - 精确匹配 monitor_id；
        - 若 monitor_id 是短标识（如 DEL41A6），则模糊匹配包含关系；
        - 否则尝试 device_id 匹配。
        """
        if not monitor_id:
            return None
        monitor_id = monitor_id.strip()
        # 精确
        for d in displays:
            if d.monitor_id and d.monitor_id == monitor_id:
                return d
        # 短标识包含
        short = monitor_id.upper()
        for d in displays:
            mid = (d.monitor_id or "").upper()
            if mid and short in mid:
                return d
        # device_id
        for d in displays:
            if d.device_id and d.device_id == monitor_id:
                return d
        return None

    async def resolve_identity_id(self, monitor_id: str, fallback_id: int) -> int:
        """按身份解析当前 DISPLAY 编号；找不到时回退配置数字并警告"""
        if not monitor_id:
            return fallback_id
        displays = await self.list_displays()
        found = self.find_display_by_identity(displays, monitor_id)
        if found is not None:
            logger.info(
                f"身份解析: {monitor_id} -> DISPLAY{found.id} "
                f"(当前枚举 {[d.id for d in displays]})"
            )
            return found.id
        logger.warning(
            f"未找到显示器身份 {monitor_id!r}，回退 DISPLAY{fallback_id}；"
            f"当前枚举: {[d.id for d in displays]}"
        )
        return fallback_id

    async def enable_display(self, display_id: int, retries: int = 2) -> bool:
        """启用显示器（带重试）"""
        for attempt in range(retries + 1):
            ok = await self._run_tool(f"/enable {display_id}")
            if ok:
                await asyncio.sleep(1.0)  # 等待 Windows 应用拓扑
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
            if ok:
                await asyncio.sleep(1.0)  # 等待 Windows 应用拓扑
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
        return await self._run_tool(f"/SetPrimary {display_id}")

    async def set_extend_mode(self, retries: int = 2) -> bool:
        """设置扩展模式（通过 Windows API SetDisplayConfig）"""
        return await self._set_display_config(SDC_TOPOLOGY_EXTEND | SDC_APPLY, "extend", retries)

    async def set_clone_mode(self, retries: int = 2) -> bool:
        """设置复制模式（通过 Windows API SetDisplayConfig）"""
        return await self._set_display_config(SDC_TOPOLOGY_CLONE | SDC_APPLY, "clone", retries)

    async def set_extend(self, retries: int = 2) -> bool:
        """设置扩展模式（兼容 /api/display/extend 端点调用）"""
        return await self.set_extend_mode(retries)

    async def set_duplicate(self, source_id: int, target_id: int, retries: int = 2) -> bool:
        """设置复制模式（兼容 /api/display/duplicate 端点调用）"""
        return await self.set_clone_mode(retries)

    async def save_topology(self, path: str) -> bool:
        """保存当前显示器完整拓扑（MultiMonitorTool /SaveConfig）"""
        if not path:
            return False
        return await self._run_tool(f'/SaveConfig "{path}"')

    async def restore_topology(self, path: str) -> bool:
        """恢复之前保存的显示器拓扑（MultiMonitorTool /LoadConfig）"""
        if not path:
            return False
        return await self._run_tool(f'/LoadConfig "{path}"')

    async def verify_display_mode(
        self,
        expected: str,
        primary_id: int = 1,
        secondary_id: int = 2,
        primary_monitor_id: str = "",
        secondary_monitor_id: str = "",
    ) -> bool:
        """验证显示器拓扑是否符合预期（基于真实枚举结果）

        Args:
            expected: "extend"（Windows 模式：主/副屏均启用）
                      或 "share"（共享模式：主屏禁用、副屏启用）
            primary_id: 主显示器 DISPLAY 编号（来自配置）
            secondary_id: 副显示器 DISPLAY 编号（来自配置）
            primary_monitor_id: 主显示器 Monitor ID（优先于数字编号）
            secondary_monitor_id: 副显示器 Monitor ID
        """
        try:
            displays = await self.list_displays()
        except Exception as e:
            logger.warning(f"Display mode verification failed: {e}")
            return False

        # 失败时输出完整枚举详情，方便诊断 DISPLAY 编号与配置不符的问题
        def _enumerate_summary() -> str:
            return ", ".join(
                f"DISPLAY{d.id}({'on' if d.is_enabled else 'off'}{',primary' if d.is_primary else ''})"
                for d in displays
            )

        # 身份优先：用 Monitor ID 解析出当前 DISPLAY 编号，避免编号漂移
        if primary_monitor_id:
            resolved = self.find_display_by_identity(displays, primary_monitor_id)
            if resolved is not None:
                primary_id = resolved.id
        if secondary_monitor_id:
            resolved = self.find_display_by_identity(displays, secondary_monitor_id)
            if resolved is not None:
                secondary_id = resolved.id

        by_id = {d.id: d for d in displays}
        if expected == "extend":
            primary = by_id.get(primary_id)
            if primary is None or not primary.is_enabled:
                logger.warning(
                    f"extend verify failed: primary DISPLAY{primary_id} "
                    f"{'missing' if primary is None else 'not enabled'} | "
                    f"当前枚举: [{_enumerate_summary()}]"
                )
                return False
            secondary = by_id.get(secondary_id)
            if secondary is not None and not secondary.is_enabled:
                logger.warning(
                    f"extend verify failed: secondary DISPLAY{secondary_id} not enabled | "
                    f"当前枚举: [{_enumerate_summary()}]"
                )
                return False
            return True
        elif expected == "share":
            primary = by_id.get(primary_id)
            secondary = by_id.get(secondary_id)
            if primary is None or secondary is None:
                logger.warning(
                    f"share verify failed: primary DISPLAY{primary_id}={primary is not None}, "
                    f"secondary DISPLAY{secondary_id}={secondary is not None} | "
                    f"当前枚举: [{_enumerate_summary()}]"
                )
                return False
            if primary.is_enabled:
                logger.warning(f"share verify failed: primary DISPLAY{primary_id} still enabled")
                return False
            if not secondary.is_enabled:
                logger.warning(f"share verify failed: secondary DISPLAY{secondary_id} not enabled")
                return False
            return True
        logger.warning(f"Unknown expected display mode: {expected}")
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

    async def _run_tool(self, args: str, timeout: float = 15.0) -> bool:
        """执行 MultiMonitorTool 命令（写操作，通过 PowerShell 包装避免 GUI 阻塞）"""
        cmd = (
            "powershell -NoProfile -NonInteractive -Command "
            f"\"& '{self._tool_path}' {args}\""
        )
        logger.debug(f"Running: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode != 0:
                logger.error(f"Tool error: {stderr.decode(errors='replace').strip()}")
                return False
            return True
        except asyncio.TimeoutError:
            logger.error(f"Tool timeout: {cmd}")
            return False
        except Exception as e:
            logger.error(f"Tool exception: {e}")
            return False

    async def _run_powershell_script(self, script: str, timeout: float = 20.0) -> str | None:
        """执行 PowerShell 脚本（通过临时 .ps1 文件，避免转义问题）"""
        import os
        import tempfile
        import uuid

        # 唯一临时文件名，避免并发调用互相覆盖
        ps1_path = os.path.join(
            tempfile.gettempdir(), f"tandorbit_mmt_{uuid.uuid4().hex}.ps1"
        )
        try:
            with open(ps1_path, "w", encoding="utf-8") as f:
                f.write(script)

            cmd = f'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{ps1_path}"'
            logger.debug(f"Running PowerShell script: {ps1_path}")
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
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

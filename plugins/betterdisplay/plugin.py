"""BetterDisplay 插件实现

通过 BetterDisplay CLI 控制 macOS 显示器。
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import DisplayChangedEvent, EventBus
from app.models import DisplayInfo, DisplayProfile
from app.plugin_base import Plugin


class BetterDisplayPlugin(Plugin):
    """BetterDisplay 显示器控制插件

    通过 BetterDisplay CLI 控制 macOS 显示器的启用/禁用/布局。
    """

    DEFAULT_CLI_PATH = (
        "/Applications/BetterDisplay.app/Contents/MacOS/betterdisplaycli"
    )
    HOMEBREW_CLI_PATH = "/opt/homebrew/bin/betterdisplaycli"

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("betterdisplay", event_bus, config)
        self._cli_path = self.config.get("cli_path", self.DEFAULT_CLI_PATH)
        self._profiles: dict[str, DisplayProfile] = {}

    async def initialize(self) -> bool:
        """初始化：检查 BetterDisplay CLI 是否可用"""
        cli = shutil.which("betterdisplaycli") or self._cli_path
        # 如果 PATH 中找不到，尝试 Homebrew 路径
        if not shutil.which(cli) and not await self._file_exists(cli):
            cli = self.HOMEBREW_CLI_PATH
        if not shutil.which(cli) and not await self._file_exists(cli):
            self._init_error = (
                f"BetterDisplay CLI 未找到 ({cli})。"
                "请安装 BetterDisplay 并确保 betterdisplaycli 可用。"
            )
            logger.error(self._init_error)
            self._set_status(PluginStatus.ERROR)
            return False
        self._cli_path = cli
        self._set_status(PluginStatus.INITIALIZED)
        logger.info(f"BetterDisplay plugin initialized (cli: {self._cli_path})")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        """检查 BetterDisplay CLI 是否可执行"""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli_path, "get", "--identifiers",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    async def shutdown(self) -> None:
        self._set_status(PluginStatus.DISABLED)

    # --- 显示器控制接口 ---

    async def list_displays(self) -> list[DisplayInfo]:
        """列出所有显示器"""
        import json
        output = await self._run_cli("get --identifiers")
        if output is None:
            return []
        displays = []
        try:
            # 输出是多个 JSON 对象，用逗号分隔
            # 需要包装成数组
            json_str = f"[{output}]"
            items = json.loads(json_str)
            for item in items:
                if item.get("deviceType") != "Display":
                    continue
                tag_id = item.get("tagID", 0)
                name = item.get("name", item.get("originalName", "Unknown"))
                displays.append(
                    DisplayInfo(
                        id=int(tag_id),
                        name=name,
                        is_primary=(len(displays) == 0),
                    )
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse display list: {e}")
        return displays

    async def enable_display(self, display_id: int) -> bool:
        """启用显示器"""
        ok = await self._run_cli(f"set --tagID={display_id} --connected=on")
        success = ok is not None
        if success:
            self.event_bus.publish(
                DisplayChangedEvent(display_id=display_id, enabled=True, source="BetterDisplay")
            )
        return success

    async def disable_display(self, display_id: int) -> bool:
        """禁用显示器"""
        ok = await self._run_cli(f"set --tagID={display_id} --connected=off")
        success = ok is not None
        if success:
            self.event_bus.publish(
                DisplayChangedEvent(display_id=display_id, enabled=False, source="BetterDisplay")
            )
        return success

    async def set_primary(self, display_id: int) -> bool:
        """设置主显示器"""
        ok = await self._run_cli(f"set --tagID={display_id} --main=on")
        return ok is not None

    async def set_mirror(self, source_id: int, target_id: int) -> bool:
        """设置显示器镜像"""
        ok = await self._run_cli(
            f"set --tagID={source_id} --mirror=on --targetTagID={target_id}"
        )
        return ok is not None

    async def set_extend(self) -> bool:
        """设置扩展模式（取消所有镜像）"""
        ok = await self._run_cli("set --mirror=off")
        return ok is not None

    async def screen_off(self, display_id: int) -> bool:
        """关闭显示器屏幕（不断开连接，需要 DDC 支持）"""
        ok = await self._run_cli(f"set --tagID={display_id} --hardwareBacklight=off")
        return ok is not None

    async def screen_on(self, display_id: int) -> bool:
        """打开显示器屏幕"""
        ok = await self._run_cli(f"set --tagID={display_id} --hardwareBacklight=on")
        return ok is not None

    async def save_profile(self, name: str) -> bool:
        """保存当前显示配置（BetterDisplay CLI 不支持此操作）"""
        logger.warning("BetterDisplay CLI does not support profile save")
        return False

    async def load_profile(self, name: str) -> bool:
        """加载显示配置（BetterDisplay CLI 不支持此操作）"""
        logger.warning("BetterDisplay CLI does not support profile load")
        return False

    # --- 内部方法 ---

    async def _run_cli(self, args: str) -> str | None:
        """执行 BetterDisplay CLI 命令"""
        cmd = f"{self._cli_path} {args}"
        logger.debug(f"Running: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                logger.error(f"CLI error: {stderr.decode(errors='replace').strip()}")
                return None
            return stdout.decode(errors="replace").strip()
        except asyncio.TimeoutError:
            logger.error(f"CLI timeout: {cmd}")
            return None
        except Exception as e:
            logger.error(f"CLI exception: {e}")
            return None

    async def _file_exists(self, path: str) -> bool:
        """检查文件是否存在"""
        try:
            proc = await asyncio.create_subprocess_shell(
                f"test -f {path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

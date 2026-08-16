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
        """列出所有显示器（tagID 为 BetterDisplay 安装专属 ID，不是 Windows DISPLAY 编号）"""
        output = await self._run_cli("get --identifiers")
        if output is None:
            return []
        return self._parse_identifiers(output)

    @staticmethod
    def _parse_identifiers(output: str) -> list[DisplayInfo]:
        """解析 betterdisplaycli get --identifiers 输出（纯函数，便于测试）

        输出可能是 JSON 数组，也可能是多行/逗号分隔的独立 JSON 对象，
        这里做防御性解析。
        """
        import json

        text = (output or "").strip()
        if not text:
            return []
        items: list[dict[str, Any]] = []
        if text.startswith("["):
            try:
                items = json.loads(text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse display list JSON: {e}")
                return []
        else:
            decoder = json.JSONDecoder()
            idx = 0
            while idx < len(text):
                while idx < len(text) and text[idx] in " \t\r\n,":
                    idx += 1
                if idx >= len(text):
                    break
                try:
                    obj, end = decoder.raw_decode(text, idx)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse display list JSON: {e}")
                    break
                items.append(obj)
                idx = end

        displays: list[DisplayInfo] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("deviceType") not in (None, "Display"):
                continue
            try:
                tag_id = int(item.get("tagID", 0))
            except (TypeError, ValueError):
                continue
            if tag_id == 0:
                continue
            name = str(item.get("name") or item.get("originalName") or f"Display {tag_id}")
            # BetterDisplay identifiers 中主显示器通过 "main" 标记（值可能为 on/off/1/0/true/false）
            main_flag = item.get("main", 0)
            is_primary = False
            if main_flag is not None:
                if isinstance(main_flag, str):
                    is_primary = main_flag.strip().lower() not in ("off", "0", "false")
                else:
                    is_primary = bool(main_flag)
            # "connected" 标记显示器是否连接（值可能为 on/off/1/0/true/false）
            conn = item.get("connected")
            is_enabled = True
            if conn is not None:
                if isinstance(conn, str):
                    is_enabled = conn.strip().lower() not in ("off", "0", "false")
                else:
                    is_enabled = bool(conn)
            displays.append(
                DisplayInfo(
                    id=tag_id,
                    name=name,
                    is_primary=is_primary,
                    is_enabled=is_enabled,
                )
            )
        # 没有任何显示器标记为主屏时，回退：第一个显示器视为主屏
        if displays and not any(d.is_primary for d in displays):
            displays[0].is_primary = True
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

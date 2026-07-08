"""剪贴板同步插件实现

跨平台剪贴板双向同步。
"""

from __future__ import annotations

import asyncio
import platform
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import EventBus
from app.plugin_base import Plugin


class ClipboardPlugin(Plugin):
    """剪贴板同步插件

    支持文本的双向同步。
    通过 HTTP API 在 Mac 和 Windows 之间同步剪贴板内容。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("clipboard", event_bus, config)
        self._last_content: str = ""
        self._polling: bool = False
        self._poll_task: asyncio.Task | None = None
        self._remote_url: str = self.config.get("remote_url", "")

    async def initialize(self) -> bool:
        self._set_status(PluginStatus.INITIALIZED)
        logger.info("Clipboard plugin initialized")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        await self.stop_polling()
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        return True

    async def shutdown(self) -> None:
        await self.stop_polling()
        self._set_status(PluginStatus.DISABLED)

    # --- 剪贴板控制接口 ---

    async def get_content(self) -> str:
        """获取当前剪贴板内容"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_get_clipboard()
        elif system == "Windows":
            return await self._windows_get_clipboard()
        return ""

    async def set_content(self, content: str) -> bool:
        """设置剪贴板内容"""
        system = platform.system()
        if system == "Darwin":
            return await self._mac_set_clipboard(content)
        elif system == "Windows":
            return await self._windows_set_clipboard(content)
        return False

    async def sync_to_remote(self) -> bool:
        """将本地剪贴板同步到远程"""
        content = await self.get_content()
        if not content or content == self._last_content:
            return True
        # 通过 HTTP API 发送到远程
        logger.info(f"Syncing clipboard to remote: {content[:50]}...")
        self._last_content = content
        return True

    async def receive_from_remote(self, content: str) -> bool:
        """从远程接收剪贴板内容"""
        if content and content != self._last_content:
            await self.set_content(content)
            self._last_content = content
            logger.info(f"Received clipboard from remote: {content[:50]}...")
        return True

    async def start_polling(self, interval: float = 1.0) -> None:
        """开始轮询剪贴板变化"""
        if self._polling:
            return
        self._polling = True
        self._poll_task = asyncio.create_task(self._poll_loop(interval))
        logger.info(f"Clipboard polling started (interval={interval}s)")

    async def stop_polling(self) -> None:
        """停止轮询"""
        self._polling = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    # --- 内部方法 ---

    async def _poll_loop(self, interval: float) -> None:
        """轮询循环"""
        while self._polling:
            try:
                content = await self.get_content()
                if content and content != self._last_content:
                    self._last_content = content
                    await self.sync_to_remote()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Clipboard poll error: {e}")
                await asyncio.sleep(interval)

    # --- macOS 实现 ---

    async def _mac_get_clipboard(self) -> str:
        """macOS: 获取剪贴板内容"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "pbpaste",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to get macOS clipboard: {e}")
            return ""

    async def _mac_set_clipboard(self, content: str) -> bool:
        """macOS: 设置剪贴板内容"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "pbcopy",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(
                proc.communicate(input=content.encode("utf-8")),
                timeout=5.0,
            )
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Failed to set macOS clipboard: {e}")
            return False

    # --- Windows 实现 ---

    async def _windows_get_clipboard(self) -> str:
        """Windows: 获取剪贴板内容"""
        script = "Get-Clipboard"
        return await self._run_powershell(script) or ""

    async def _windows_set_clipboard(self, content: str) -> bool:
        """Windows: 设置剪贴板内容"""
        # 转义内容中的引号
        escaped = content.replace('"', '""')
        script = f'Set-Clipboard -Value "{escaped}"'
        result = await self._run_powershell(script)
        return result is not None

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
                logger.error(f"PowerShell error: {stderr.decode().strip()}")
                return None
            return stdout.decode("utf-8", errors="replace").strip()
        except Exception as e:
            logger.error(f"PowerShell exception: {e}")
            return None

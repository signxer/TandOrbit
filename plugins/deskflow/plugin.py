"""Deskflow 插件实现

控制 Deskflow（原 Barrier/Synergy）的启动、停止、重连。
"""

from __future__ import annotations

import asyncio
import platform
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import DeskflowStatusChangedEvent, EventBus
from app.plugin_base import Plugin


class DeskflowPlugin(Plugin):
    """Deskflow 键鼠共享控制插件

    支持 macOS 和 Windows 双平台。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("deskflow", event_bus, config)
        self._is_server = self.config.get("is_server", False)
        self._server_host = self.config.get("server_host", "192.168.1.100")
        self._server_port = self.config.get("server_port", 24800)
        self._auto_restart = self.config.get("auto_restart", True)
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def initialize(self) -> bool:
        system = platform.system()
        if system == "Darwin":
            cli_path = self.config.get("deskflow_path", "")
            if cli_path:
                self._exe_path = cli_path
            elif Path("/Applications/Deskflow.app").exists():
                self._exe_path = "Deskflow"
            else:
                self._init_error = (
                    "Deskflow 未安装。"
                    "请从 https://github.com/deskflow/deskflow/releases 下载安装。"
                )
                logger.warning(self._init_error)
                self._set_status(PluginStatus.ERROR)
                return False
        elif system == "Windows":
            cli_path = self.config.get("deskflow_path", "deskflow.exe")
            if shutil.which(cli_path) or Path(cli_path).exists():
                self._exe_path = cli_path
            else:
                self._init_error = (
                    "Deskflow 未安装。"
                    "请从 https://github.com/deskflow/deskflow/releases 下载安装。"
                )
                logger.warning(self._init_error)
                self._set_status(PluginStatus.ERROR)
                return False

        self._set_status(PluginStatus.INITIALIZED)
        logger.info("Deskflow plugin initialized")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        await self.stop()
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        """检查 Deskflow 是否运行"""
        if self._process is not None:
            return self._process.returncode is None
        return await self._is_running()

    async def shutdown(self) -> None:
        await self.stop()
        self._set_status(PluginStatus.DISABLED)

    # --- Deskflow 控制接口 ---

    async def start(self) -> bool:
        """启动 Deskflow"""
        if await self._is_running():
            logger.info("Deskflow already running")
            return True

        cmd = self._get_start_command()
        logger.info(f"Starting Deskflow: {cmd}")
        try:
            self._process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 等待一下检查是否启动成功
            await asyncio.sleep(2.0)
            if self._process.returncode is not None:
                logger.error("Deskflow failed to start")
                return False
            self._connected = True
            self.event_bus.publish(
                DeskflowStatusChangedEvent(connected=True, source="Deskflow")
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start Deskflow: {e}")
            return False

    async def stop(self) -> bool:
        """停止 Deskflow"""
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            except Exception as e:
                logger.error(f"Error stopping Deskflow: {e}")
            finally:
                self._process = None

        # 也尝试通过系统命令停止
        cmd = self._get_stop_command()
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except Exception:
            pass

        self._connected = False
        self.event_bus.publish(
            DeskflowStatusChangedEvent(connected=False, source="Deskflow")
        )
        return True

    async def restart(self) -> bool:
        """重启 Deskflow"""
        logger.info("Restarting Deskflow")
        await self.stop()
        await asyncio.sleep(1.0)
        return await self.start()

    async def check_connection(self) -> bool:
        """检查连接状态"""
        # 尝试连接到 Deskflow 服务器端口
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._server_host, self._server_port),
                timeout=3.0,
            )
            writer.close()
            await writer.wait_closed()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    # --- 内部方法 ---

    def _get_start_command(self) -> str:
        """获取启动命令"""
        system = platform.system()
        exe = getattr(self, "_exe_path", "deskflow.exe")
        if system == "Darwin":
            if self._is_server:
                return f'open -a "{exe}"'
            else:
                return f'open -a "{exe}" --args --client {self._server_host}'
        elif system == "Windows":
            if self._is_server:
                return f'start "" "{exe}"'
            else:
                return f'start "" "{exe}" --client {self._server_host}'
        return "deskflow"

    def _get_stop_command(self) -> str:
        """获取停止命令"""
        system = platform.system()
        if system == "Darwin":
            return "osascript -e 'quit app \"Deskflow\"'"
        elif system == "Windows":
            return "taskkill /IM Deskflow.exe /F"
        return "pkill deskflow"

    async def _is_running(self) -> bool:
        """检查 Deskflow 是否在运行"""
        system = platform.system()
        exe = getattr(self, "_exe_path", "deskflow.exe")
        exe_name = Path(exe).name
        if system == "Darwin":
            cmd = f'pgrep -f "{exe_name}"'
        elif system == "Windows":
            cmd = f'tasklist /FI "IMAGENAME eq {exe_name}" /NH'
        else:
            cmd = f"pgrep -f {exe_name}"

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return bool(stdout.decode(errors="replace").strip())
        except Exception:
            return False

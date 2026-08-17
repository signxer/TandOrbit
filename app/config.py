"""TandOrbit 配置管理

YAML 配置加载与热更新。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger
from pydantic import BaseModel, Field


class DisplayConfig(BaseModel):
    """显示器配置"""

    primary_id: int = 1
    secondary_id: int = 2
    share_display_id: int = 2  # 共享模式下留给 Windows 的显示器 ID
    ddc_primary_monitor: str = r"\\.\DISPLAY1\Monitor0"  # DDC/CI 主屏标识（ControlMyMonitor 用）
    ddc_secondary_monitor: str = r"\\.\DISPLAY2\Monitor0"  # DDC/CI 副屏标识（ControlMyMonitor 用）
    auto_repair: bool = False  # 启动时按上次模式自愈显示器状态（默认关闭，避免意外改动）
    # Windows 显示器身份（Monitor ID / DeviceID），用于避免 DISPLAY 编号漂移。
    # 为空时回退 primary_id/secondary_id 数字编号。
    windows_primary_monitor_id: str = ""
    windows_secondary_monitor_id: str = ""


class WindowsConfig(BaseModel):
    """Windows Agent 配置"""

    host: str = "192.168.1.100"
    mac_address: str = ""
    port: int = 5000  # Windows Agent 监听端口
    timeout: float = 10.0


class MacConfig(BaseModel):
    """Mac 端配置（供 Windows 连接和唤醒）"""

    host: str = "192.168.1.100"
    mac_address: str = ""  # Mac 的 MAC 地址，用于 WoL 唤醒
    port: int = 5001  # Mac Agent 监听端口


class DeskflowConfig(BaseModel):
    """Deskflow 配置"""

    auto_restart: bool = True
    server_host: str = "192.168.1.100"
    server_port: int = 24800
    client_name: str = "mac"
    is_server: Optional[bool] = None  # None = 按平台自动判断（Windows 为服务端，Mac 为客户端）


class BetterDisplayConfig(BaseModel):
    """BetterDisplay 配置"""

    cli_path: str = "/Applications/BetterDisplay.app/Contents/MacOS/betterdisplaycli"


class AudioConfig(BaseModel):
    """音频配置"""

    mac_output: str = "AirPods"
    windows_output: str = "USB DAC"


class ToolsConfig(BaseModel):
    """外部工具路径配置"""

    multimonitortool_path: str = "MultiMonitorTool.exe"
    controlmymonitor_path: str = "ControlMyMonitor.exe"
    deskflow_path: str = "deskflow.exe"


import platform


def _default_hotkeys() -> dict[str, str]:
    if platform.system() == "Darwin":
        return {
            "switch_mac": "Ctrl+Option+1",
            "switch_windows": "Ctrl+Option+2",
            "switch_share": "Ctrl+Option+3",
        }
    return {
        "switch_mac": "Ctrl+Alt+1",
        "switch_windows": "Ctrl+Alt+2",
        "switch_share": "Ctrl+Alt+3",
    }


class AppConfig(BaseModel):
    """应用总配置"""

    display: DisplayConfig = Field(default_factory=DisplayConfig)
    windows: WindowsConfig = Field(default_factory=WindowsConfig)
    mac: MacConfig = Field(default_factory=MacConfig)
    deskflow: DeskflowConfig = Field(default_factory=DeskflowConfig)
    betterdisplay: BetterDisplayConfig = Field(default_factory=BetterDisplayConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    hotkeys: dict[str, str] = Field(default_factory=_default_hotkeys)
    wol_nic: str = ""  # 本机 WoL 网卡名，如 en0 / Ethernet
    last_mode: Optional[str] = None  # 上次成功切换的模式（启动恢复用）
    agent_token: str = ""  # Agent 访问令牌（两端需一致；空 = 不鉴权，兼容旧配置）
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_retention_days: int = 30


DEFAULT_CONFIG_PATH = Path.home() / ".tandorbit" / "config.yaml"


class ConfigManager:
    """配置管理器

    支持 YAML 配置文件加载和热更新。
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        self._path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._config = AppConfig()
        self._callbacks: list[Any] = []

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def data_dir(self) -> Path:
        """配置所在目录（状态数据如 state.db 也放这里）"""
        return self._path.parent

    def load(self) -> AppConfig:
        """加载配置文件"""
        if not self._path.exists():
            logger.info(f"Config file not found at {self._path}, using defaults")
            self.save()
            return self._config

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._config = AppConfig(**data)
            logger.info(f"Config loaded from {self._path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}, using defaults")
            self._config = AppConfig()

        return self._config

    def save(self) -> None:
        """保存配置到文件（原子写入：先写临时文件再替换，避免崩溃损坏配置）"""
        import os
        import tempfile

        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".tandorbit_config_", suffix=".tmp", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._config.model_dump(),
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            os.replace(tmp_path, str(self._path))
            logger.info(f"Config saved to {self._path}")
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def update(self, updates: dict[str, Any]) -> None:
        """更新配置（部分更新）"""
        current = self._config.model_dump()
        self._deep_merge(current, updates)
        self._config = AppConfig(**current)
        self.save()

    def export_to(self, path: Path | str) -> bool:
        """导出当前配置到指定路径"""
        import shutil

        try:
            if not self._path.exists():
                self.save()
            shutil.copy2(self._path, str(path))
            logger.info(f"Config exported to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export config: {e}")
            return False

    def import_from(self, path: Path | str) -> bool:
        """从指定路径导入配置并重载"""
        import shutil

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(path), str(self._path))
            self.load()
            logger.info(f"Config imported from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to import config: {e}")
            return False

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> None:
        """深度合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（点分路径）"""
        keys = key.split(".")
        value = self._config.model_dump()
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

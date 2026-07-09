"""TandOrbit 配置管理

YAML 配置加载与热更新。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, Field


class DisplayConfig(BaseModel):
    """显示器配置"""

    primary_id: int = 1
    secondary_id: int = 2
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)


class WindowsConfig(BaseModel):
    """Windows Agent 配置"""

    host: str = "192.168.1.100"
    mac_address: str = ""
    port: int = 5000
    timeout: float = 10.0


class DeskflowConfig(BaseModel):
    """Deskflow 配置"""

    auto_restart: bool = True
    server_host: str = "192.168.1.100"
    server_port: int = 24800
    client_name: str = "mac"


class BetterDisplayConfig(BaseModel):
    """BetterDisplay 配置"""

    cli_path: str = "/Applications/BetterDisplay.app/Contents/MacOS/betterdisplaycli"


class AudioConfig(BaseModel):
    """音频配置"""

    mac_output: str = "AirPods"
    windows_output: str = "USB DAC"


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
    deskflow: DeskflowConfig = Field(default_factory=DeskflowConfig)
    betterdisplay: BetterDisplayConfig = Field(default_factory=BetterDisplayConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    hotkeys: dict[str, str] = Field(default_factory=_default_hotkeys)
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
        """保存配置到文件"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._config.model_dump(),
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            logger.info(f"Config saved to {self._path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def update(self, updates: dict[str, Any]) -> None:
        """更新配置（部分更新）"""
        current = self._config.model_dump()
        self._deep_merge(current, updates)
        self._config = AppConfig(**current)
        self.save()

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

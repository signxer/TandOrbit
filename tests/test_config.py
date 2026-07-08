"""配置管理单元测试"""

import tempfile
from pathlib import Path

import pytest

from app.config import AppConfig, ConfigManager


class TestConfigManager:
    """ConfigManager 测试"""

    def test_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            mgr = ConfigManager(path)
            config = mgr.load()
            assert config.windows.port == 5000
            assert config.display.primary_id == 1

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            mgr = ConfigManager(path)
            mgr.load()
            mgr.update({"windows": {"port": 8080}})
            assert mgr.config.windows.port == 8080

            # 重新加载验证持久化
            mgr2 = ConfigManager(path)
            mgr2.load()
            assert mgr2.config.windows.port == 8080

    def test_get_nested_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            mgr = ConfigManager(path)
            mgr.load()
            assert mgr.get("windows.port") == 5000
            assert mgr.get("nonexistent.key", "default") == "default"

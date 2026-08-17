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


class TestV2ConfigFields:
    """v2.0 新增配置字段"""

    def test_new_display_fields_defaults(self) -> None:
        config = AppConfig()
        assert config.display.auto_repair is False
        assert config.display.ddc_primary_monitor.startswith(r"\\.\DISPLAY1")

    def test_last_mode_default_none(self) -> None:
        config = AppConfig()
        assert config.last_mode is None

    def test_export_import_roundtrip(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.yaml"
            dst = Path(tmpdir) / "dst.yaml"
            mgr = ConfigManager(src)
            mgr.load()
            mgr.update({"windows": {"port": 8080}, "last_mode": "SHARE"})

            assert mgr.export_to(dst)
            assert dst.exists()

            mgr2 = ConfigManager(Path(tmpdir) / "other.yaml")
            mgr2.load()
            assert mgr2.import_from(dst)
            assert mgr2.config.windows.port == 8080
            assert mgr2.config.last_mode == "SHARE"


    def test_windows_monitor_identity_defaults(self) -> None:
        config = AppConfig()
        assert config.display.windows_primary_monitor_id == ""
        assert config.display.windows_secondary_monitor_id == ""

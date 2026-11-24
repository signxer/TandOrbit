"""设置对话框回归测试（真实实例化，验证异步刷新不抛异常）"""

import asyncio
import platform
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import ConfigManager
from app.models import DisplayInfo


class _FakeDisplay:
    """假显示器插件：list_displays 返回固定列表"""

    status = "ENABLED"

    async def list_displays(self):
        return [DisplayInfo(id=1, name="Primary"), DisplayInfo(id=2, name="Secondary")]


class _FakeAudio:
    """假音频插件"""

    status = "ENABLED"

    async def list_devices(self):
        return ["AirPods", "USB DAC"]


@pytest.fixture
def make_dialog(tmp_path, qapp):
    from PySide6.QtCore import QCoreApplication, QEvent

    from app.gui.settings_dialog import SettingsDialog

    dialogs = []
    work = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        def submit(coroutine):
            future = executor.submit(asyncio.run, coroutine)
            work.append(future)
            return future

        def create(plugins=None):
            provider = (lambda: plugins) if plugins is not None else None
            dialog = SettingsDialog(
                ConfigManager(tmp_path / "config.yaml"),
                plugin_provider=provider,
                submit=submit,
            )
            dialogs.append(dialog)
            return dialog

        yield create

    for future in work:
        future.result()
    qapp.processEvents()
    for dialog in dialogs:
        dialog.close()
        dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class TestSettingsDialogRefresh:
    """异步刷新显示器/音频列表：不应抛 NameError，且应回填下拉框"""

    def test_refresh_displays_with_plugin(self, qapp, make_dialog) -> None:
        dialog = make_dialog({"betterdisplay": _FakeDisplay()})
        try:
            dialog._refresh_displays()  # 后台线程 + 信号回填
            # 等待异步完成
            for _ in range(50):
                qapp.processEvents()
                if dialog._primary_id.count() >= 2:
                    break
                time.sleep(0.02)
            assert dialog._primary_id.count() == 2
            assert dialog._secondary_id.count() == 2
        finally:
            dialog.close()

    def test_refresh_audio_with_plugin(self, qapp, make_dialog) -> None:
        dialog = make_dialog({"audio": _FakeAudio()})
        try:
            dialog._refresh_audio()
            combo = dialog._mac_audio if platform.system() == "Darwin" else dialog._win_audio
            for _ in range(50):
                qapp.processEvents()
                if combo.count() >= 2:
                    break
                time.sleep(0.02)
            assert combo.count() == 2
        finally:
            dialog.close()

    def test_refresh_without_plugin_provider(self, qapp, make_dialog) -> None:
        dialog = make_dialog()
        try:
            dialog._refresh_displays()  # 走占位分支，不应抛异常
            dialog._refresh_audio()
            qapp.processEvents()
        finally:
            dialog.close()

    def test_dialog_constructs_with_real_plugins(self, qapp, make_dialog) -> None:
        """构造即触发 _load_values → _refresh_displays/audio（真实插件为 None 时也不崩）"""
        dialog = make_dialog({"betterdisplay": _FakeDisplay(), "audio": _FakeAudio()})
        try:
            for _ in range(50):
                qapp.processEvents()
                time.sleep(0.02)
        finally:
            dialog.close()

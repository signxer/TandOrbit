"""设置对话框回归测试（真实实例化，验证异步刷新不抛异常）"""

import asyncio
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

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

        def create(plugins=None, pairing=None, remote_provider=None):
            provider = (lambda: plugins) if plugins is not None else None
            dialog = SettingsDialog(
                ConfigManager(tmp_path / "config.yaml"),
                plugin_provider=provider,
                submit=submit,
                pairing=pairing,
                remote_provider=remote_provider,
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


def test_navigation_keeps_fields_reachable_in_compact_window(qapp, make_dialog):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    dialog = make_dialog({"betterdisplay": _FakeDisplay()})
    dialog.resize(640, 450)
    dialog.show()
    tabs = dialog._navigation
    display = next(index for index in range(tabs.count()) if tabs.tabText(index) == "显示器")
    tabs.setCurrentIndex(display)
    tabs.setFocus()
    QTest.keyClick(tabs, Qt.Key.Key_Right)
    qapp.processEvents()
    assert tabs.tabText(tabs.currentIndex()) == "键鼠与剪贴板"
    assert dialog._shared_keys.isVisible()
    assert dialog._shared_edge.isVisible()
    dialog._shared_keys.click()
    assert not dialog._shared_edge.isEnabled()
    assert dialog._shared_clipboard.isEnabled()


def test_paired_fingerprint_wraps_without_clipping_controls(qapp, make_dialog):
    from PySide6.QtWidgets import QPushButton

    dialog = make_dialog()
    dialog._pairing = SimpleNamespace(peer={
        "host": "192.168.1.20", "port": 5000, "fingerprint": ":".join(["AB"] * 32),
    })
    dialog.refresh_remote_info()
    dialog.resize(640, 450)
    dialog.show()
    dialog._show_page("computers")
    details = next(button for button in dialog.findChildren(QPushButton)
                   if button.text() == "网络与配对详情")
    assert not dialog._fingerprint.isVisible()
    details.click()
    qapp.processEvents()
    page = dialog._pages.currentWidget()
    assert page.widget().width() == page.viewport().width()
    assert dialog._revoke_button.isEnabled()
    assert dialog._fingerprint.isVisible()


def test_setup_guides_pairing_before_read_only_connection_check(qapp, make_dialog):
    pairing = SimpleNamespace(peer=None)

    async def capabilities():
        return {"display": [{}, {}], "single_display": False}

    dialog = make_dialog({"betterdisplay": _FakeDisplay()}, pairing, capabilities)
    assert dialog._navigation.tabText(dialog._navigation.currentIndex()) == "开始使用"
    assert not dialog._check_button.isEnabled()
    dialog._setup_pair_button.click()
    assert dialog._navigation.tabText(dialog._navigation.currentIndex()) == "两台电脑"

    pairing.peer = {"host": "192.168.1.20", "port": 5000, "fingerprint": "AB:CD"}
    dialog.refresh_remote_info()
    assert "本机已保存" in dialog._setup_pair_status.text()
    assert dialog._check_button.isEnabled()
    dialog._next_displays.click()
    assert dialog._navigation.tabText(dialog._navigation.currentIndex()) == "显示器"

    dialog._show_page("setup")
    dialog._check_button.click()
    for _ in range(50):
        qapp.processEvents()
        if "已连上" in dialog._setup_check_status.text():
            break
        time.sleep(0.02)
    assert "识别到 2 台显示器" in dialog._setup_check_status.text()
    assert "另一台电脑暂时无法独立控制" in dialog._connection_result.text()

    pairing.peer = None
    dialog.refresh_remote_info()
    dialog._show_connection_result("AB:CD", "旧结果", "旧详情")
    assert not dialog._check_button.isEnabled()
    assert "完成配对" in dialog._setup_check_status.text()


def test_device_appearance_persists_without_available_displays(qapp, make_dialog):
    other = "windows" if platform.system() == "Darwin" else "mac"
    peer = {"role": other, "host": "192.168.1.20", "port": 5000, "fingerprint": "AA:BB"}
    dialog = make_dialog(pairing=SimpleNamespace(peer=peer))
    manager = dialog._config_manager
    prefix = "mac" if platform.system() == "Darwin" else "windows"
    manager.update({"display": {f"{prefix}_primary_monitor_id": "disconnected-monitor"}})
    dialog._populate_displays([])
    dialog._local_device.name.setText("工作电脑")
    dialog._local_device.glyph.setCurrentIndex(dialog._local_device.glyph.findData("mini"))
    dialog._peer_device.name.setText("家庭电脑")
    dialog._peer_device.glyph.setCurrentIndex(dialog._peer_device.glyph.findData("desktop"))
    peer["host"] = "192.168.1.21"
    dialog.refresh_remote_info()
    assert dialog._peer_device._preview_icon.accessibleName() == "家庭电脑"

    dialog._save()
    assert dialog.result() == dialog.DialogCode.Accepted
    config = ConfigManager(manager.data_dir / "config.yaml").load()
    assert config.device_appearance["local"].model_dump() == {"name": "工作电脑", "glyph": "mini"}
    assert config.device_appearance["AA:BB"].model_dump() == {"name": "家庭电脑", "glyph": "desktop"}
    assert getattr(config.display, f"{prefix}_primary_monitor_id") == "disconnected-monitor"
    reopened = make_dialog(pairing=dialog._pairing)
    reopened._config_manager.load()
    reopened.refresh_remote_info(reload_appearance=True)
    assert reopened._peer_device.name.text() == "家庭电脑"
    reopened._pairing.peer = {**peer, "fingerprint": "CC:DD"}
    reopened.refresh_remote_info()
    assert reopened._peer_device.name.text() == ""
    assert reopened._peer_device.glyph.currentData() == "auto"

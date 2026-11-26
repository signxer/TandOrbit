"""Layout and mode-state regression tests for the desktop panel."""

import pytest

from app.enums import Mode


@pytest.mark.parametrize("width", [448, 517, 624])
def test_mode_cards_keep_titles_and_shortcuts_separate(qapp, width):
    from app.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window.resize(width, window.minimumSizeHint().height())
        window.show()
        qapp.processEvents()
        left, right = window._preview.screens
        assert left.size() == right.size()
        assert left.screen_rect() == right.screen_rect()
        assert left.y() == right.y()
        screen = left.screen_rect()
        assert screen.width() / screen.height() == pytest.approx(16 / 9)
        for control in window._mode_buttons.values():
            title = control._label.geometry()
            shortcut = control._shortcut.geometry()
            assert title.height() >= control._label.fontMetrics().height()
            assert shortcut.height() >= control._shortcut.fontMetrics().height()
            assert title.bottom() < shortcut.top()
            assert control.rect().contains(title)
            assert control.rect().contains(shortcut)
    finally:
        window.close()


def test_mode_request_only_highlights_after_commit(qapp):
    from app.gui.main_window import MainWindow

    window = MainWindow()
    try:
        requested = []
        window.mode_switch_requested.connect(requested.append)
        window.update_mode(Mode.MAC)
        window._mode_buttons[Mode.SHARE].click()
        assert requested == [Mode.SHARE]
        assert window._mode_buttons[Mode.MAC].isChecked()
        assert not window._mode_buttons[Mode.SHARE].isChecked()
        window.show_operation({"phase": "verify", "target": "SHARE"})
        assert not any(button.isEnabled() for button in window._mode_buttons.values())
        assert "正在验证" in window._operation.text()
        window.show_operation({"phase": "committed", "target": "SHARE"})
        assert window._mode_buttons[Mode.SHARE].isChecked()
        assert all(button.isEnabled() for button in window._mode_buttons.values())
    finally:
        window.close()


def test_screen_owners_follow_confirmation_and_keep_device_appearance(qapp):
    from app.config import DeviceAppearance
    from app.gui.devices import devices_for
    from app.gui.main_window import MainWindow

    window = MainWindow()
    try:
        peer = {"role": "windows", "fingerprint": "pc"}
        appearances = {
            "local": DeviceAppearance(name="工作站", glyph="mini"),
            "pc": DeviceAppearance(name="游戏机", glyph="tower"),
        }
        mac, windows = devices_for(appearances, "mac", peer)
        window.set_devices(mac, windows)
        window.update_mode(Mode.MAC)
        left, right = window._preview.screens
        window.show_operation({"phase": "verify", "target": "SHARE", "share_role": "primary"})
        assert (left.owner, right.owner) == (mac, mac)
        window.show_operation({"phase": "committed", "target": "SHARE", "share_role": "primary"})
        assert (left.owner, right.owner) == (windows, mac)

        appearances["pc"] = DeviceAppearance(name="家庭电脑", glyph="desktop")
        mac, windows = devices_for(appearances, "mac", peer)
        window.set_devices(mac, windows)
        window.show_operation({"phase": "committed", "target": "SHARE"})
        assert left.accessibleName() == "主屏 · 家庭电脑"
        assert (left.owner, right.owner) == (windows, mac)
        assert window._mode_buttons[Mode.WINDOWS].accessibleName().startswith("家庭电脑")
    finally:
        window.close()

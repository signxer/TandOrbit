"""Native tray menu for TandOrbit."""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from app.enums import Mode
from app.gui.devices import DeviceView
from app.gui.main_window import BUSY_PHASES, MODE_INFO, MODE_PLATFORM, mode_name
from app.gui.theme import icon as menu_icon


class TrayIcon(QSystemTrayIcon):
    mode_switch_requested = Signal(Mode)
    show_window_requested = Signal()
    settings_requested = Signal()
    check_update_requested = Signal()
    view_log_requested = Signal()
    switch_history_requested = Signal()
    quit_requested = Signal()
    recover_requested = Signal()

    def __init__(self, icon: QIcon | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if icon and not icon.isNull():
            self.setIcon(icon)
        self._current_mode = Mode.UNKNOWN
        self._busy = False
        self._devices = {}
        self._setup_menu()
        self.update_mode(self._current_mode)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window_requested.emit()

    def _setup_menu(self) -> None:
        menu = QMenu()
        self._menu = menu

        def add(text, glyph, signal):
            action = menu.addAction(menu_icon(glyph), text)
            action.triggered.connect(signal.emit)

        add("显示主窗口", "monitor", self.show_window_requested)
        add("设置…", "settings", self.settings_requested)
        menu.addSeparator()

        self._mode_actions: dict[Mode, QAction] = {}
        for mode, (_, glyph, _) in MODE_INFO.items():
            action = menu.addAction(menu_icon(glyph), mode_name(mode))
            action.setCheckable(True)
            action.triggered.connect(lambda _checked, target=mode: self._request_mode(target))
            self._mode_actions[mode] = action

        menu.addSeparator()
        add("恢复本机显示", "restore", self.recover_requested)
        add("切换记录…", "history", self.switch_history_requested)
        add("查看日志", "logs", self.view_log_requested)
        add("检查更新…", "refresh", self.check_update_requested)
        menu.addSeparator()
        add("退出 TandOrbit", "logout", self.quit_requested)
        self.setContextMenu(menu)

    def _request_mode(self, mode: Mode) -> None:
        self._mode_actions[mode].setChecked(mode == self._current_mode)
        self.mode_switch_requested.emit(mode)

    def set_devices(self, local: DeviceView, peer: DeviceView) -> None:
        self._devices = {device.platform: device for device in (local, peer)}
        for mode, platform in MODE_PLATFORM.items():
            action = self._mode_actions[mode]
            action.setIcon(menu_icon(self._devices[platform].glyph))
            action.setText(mode_name(mode, self._devices).replace("&", "&&"))
        self.update_mode(self._current_mode)

    @Slot(object)
    def update_mode(self, mode: Mode) -> None:
        self._current_mode = mode
        self.setToolTip(f"TandOrbit · {mode_name(mode, self._devices)}")
        for value, action in self._mode_actions.items():
            action.setChecked(value == mode)
            action.setEnabled(not self._busy and value != mode)

    def show_operation(self, record: dict) -> None:
        phase = record["phase"]
        if phase in ("sharing", "audio_warning"):
            return
        self._busy = phase in BUSY_PHASES
        mode = Mode.__members__.get(record.get("target", "")) if phase == "committed" else None
        self.update_mode(mode or self._current_mode)

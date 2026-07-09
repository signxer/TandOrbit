"""TandOrbit 系统托盘

提供系统托盘图标和菜单。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from app.enums import Mode


class TrayIcon(QSystemTrayIcon):
    """系统托盘图标"""

    mode_switch_requested = Signal(Mode)
    show_window_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if icon and not icon.isNull():
            self.setIcon(icon)
        self._setup_menu()
        self._current_mode = Mode.UNKNOWN
        # 点击 tray 图标显示主窗口
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window_requested.emit()

    def _setup_menu(self) -> None:
        """构建托盘菜单"""
        menu = QMenu()

        # 显示主窗口
        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(self.show_window_requested.emit)
        menu.addAction(show_action)

        # 设置
        settings_action = QAction("设置...", menu)
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 模式切换
        mac_action = QAction("Mac 模式", menu)
        mac_action.triggered.connect(lambda: self.mode_switch_requested.emit(Mode.MAC))
        menu.addAction(mac_action)

        win_action = QAction("Windows 模式", menu)
        win_action.triggered.connect(lambda: self.mode_switch_requested.emit(Mode.WINDOWS))
        menu.addAction(win_action)

        share_action = QAction("共享模式", menu)
        share_action.triggered.connect(lambda: self.mode_switch_requested.emit(Mode.SHARE))
        menu.addAction(share_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def update_mode(self, mode: Mode) -> None:
        """更新托盘图标提示"""
        self._current_mode = mode
        mode_names = {
            Mode.MAC: "Mac 模式",
            Mode.WINDOWS: "Windows 模式",
            Mode.SHARE: "共享模式",
            Mode.PRESENTATION: "演示模式",
            Mode.UNKNOWN: "未知",
        }
        name = mode_names.get(mode, "未知")
        self.setToolTip(f"TandOrbit - {name}")

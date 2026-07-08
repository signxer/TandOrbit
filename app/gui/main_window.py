"""TandOrbit 主窗口

极简风格的主界面，显示设备状态和模式切换。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.enums import Mode


class StatusIndicator(QLabel):
    """状态指示器（绿色圆点 + 文字）"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._online = False
        self.update_status(False)

    def update_status(self, online: bool) -> None:
        self._online = online
        color = "#4CAF50" if online else "#9E9E9E"
        self.setText(f'<span style="color:{color};">●</span> {self._text}')


class ModeButton(QPushButton):
    """模式切换按钮"""

    def __init__(self, text: str, mode: Mode, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.mode = mode
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setFont(QFont(".AppleSystemUIFont", 13))


class MainWindow(QMainWindow):
    """TandOrbit 主窗口"""

    mode_switch_requested = Signal(Mode)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TandOrbit")
        self.setFixedSize(320, 480)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建界面"""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # --- 标题 ---
        title = QLabel("TandOrbit")
        title.setFont(QFont(".AppleSystemUIFont", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("双机双屏协同管理")
        subtitle.setFont(QFont(".AppleSystemUIFont", 11))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # --- 设备状态 ---
        self._mac_status = StatusIndicator("Mac")
        self._win_status = StatusIndicator("Windows")
        self._deskflow_status = StatusIndicator("Deskflow")

        for indicator in [self._mac_status, self._win_status, self._deskflow_status]:
            indicator.setFont(QFont(".AppleSystemUIFont", 12))
            layout.addWidget(indicator)

        layout.addSpacing(20)

        # --- 模式切换按钮 ---
        self._mode_buttons: dict[Mode, ModeButton] = {}
        modes = [
            ("Mac 模式", Mode.MAC),
            ("Windows 模式", Mode.WINDOWS),
            ("共享模式", Mode.SHARE),
        ]
        for text, mode in modes:
            btn = ModeButton(text, mode)
            btn.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(m))
            self._mode_buttons[mode] = btn
            layout.addWidget(btn)

        layout.addSpacing(16)

        # --- 快捷键提示 ---
        hotkeys = QLabel("Ctrl+Alt+1 / 2 / 3")
        hotkeys.setFont(QFont(".AppleSystemUIFont", 10))
        hotkeys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hotkeys.setStyleSheet("color: #666;")
        layout.addWidget(hotkeys)

        layout.addStretch()

    def _on_mode_clicked(self, mode: Mode) -> None:
        """模式按钮点击"""
        self.mode_switch_requested.emit(mode)

    def update_mode(self, mode: Mode) -> None:
        """更新当前模式显示"""
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)

    def update_device_status(self, mac_online: bool, win_online: bool, deskflow_connected: bool) -> None:
        """更新设备状态"""
        self._mac_status.update_status(mac_online)
        self._win_status.update_status(win_online)
        self._deskflow_status.update_status(deskflow_connected)

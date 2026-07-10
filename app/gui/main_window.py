"""TandOrbit 主窗口

极简风格的主界面，显示设备状态和模式切换。
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.enums import Mode

# 平台字体
_FONT = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"


def _detect_dark_mode() -> bool:
    """检测系统是否为深色模式"""
    try:
        if platform.system() == "Windows":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        elif platform.system() == "Darwin":
            import subprocess

            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3,
            )
            return result.stdout.strip().lower() == "dark"
    except Exception:
        pass
    return False


# 配色方案
_LIGHT = {
    "bg": "#FFFFFF",
    "border": "#D0D0D0",
    "hover": "#F5F5F5",
    "checked_bg": "#E8F0FE",
    "checked_border": "#4A90D9",
    "text": "#333333",
    "text_secondary": "#666666",
    "settings_hover": "#F0F0F0",
    "window_bg": "#FFFFFF",
}

_DARK = {
    "bg": "#2B2B2B",
    "border": "#555555",
    "hover": "#3A3A3A",
    "checked_bg": "#1A3A5C",
    "checked_border": "#4A90D9",
    "text": "#E0E0E0",
    "text_secondary": "#AAAAAA",
    "settings_hover": "#3A3A3A",
    "window_bg": "#1E1E1E",
}

_COLORS = _DARK if _detect_dark_mode() else _LIGHT


def _resource_path(relative: str) -> Path:
    """获取资源文件路径（兼容 PyInstaller 打包和开发模式）"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent.parent / relative

# 各模式对应的 SVG 资源和文字
_MODE_CONFIG: dict[Mode, tuple[str, str]] = {
    Mode.MAC: ("resources/apple.svg", "Mac"),
    Mode.WINDOWS: ("resources/windows.svg", "Windows"),
    Mode.SHARE: ("resources/mix.svg", "共享"),
}

_ICON_SIZE = QSize(32, 32)


class StatusIndicator(QLabel):
    """状态指示器（绿色圆点 + 文字，居中）"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._online = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_status(False)

    def update_status(self, online: bool) -> None:
        self._online = online
        dot = "#4CAF50" if online else "#9E9E9E"
        self.setText(
            f'<span style="color:{dot};">●</span> '
            f'<span style="color:{_COLORS["text"]};">{self._text}</span>'
        )


class ModeButton(QPushButton):
    """模式按钮（图标 + 文字的方块按钮，可作为状态指示器或切换按钮）"""

    _STYLE = """
        ModeButton {{
            border: 2px solid {border};
            border-radius: 10px;
            background: {bg};
            padding: 12px 4px;
            color: {text};
        }}
        ModeButton:hover {{
            background: {hover};
        }}
        ModeButton:checked {{
            border-color: {checked_border};
            background: {checked_bg};
        }}
    """.format(**_COLORS)

    _STATUS_STYLE = """
        ModeButton {{
            border: 2px solid {checked_border};
            border-radius: 10px;
            background: {checked_bg};
            padding: 12px 4px;
            color: {text};
        }}
    """.format(**_COLORS)

    def __init__(
        self,
        text: str,
        mode: Mode,
        svg_path: str,
        base_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setCheckable(True)
        self.setFixedSize(88, 80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._STYLE)

        # 内部布局：图标居上，文字居下
        inner = QVBoxLayout(self)
        inner.setContentsMargins(0, 6, 0, 4)
        inner.setSpacing(4)
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QSvgWidget(str(base_dir / svg_path))
        icon.setFixedSize(_ICON_SIZE)
        icon.setStyleSheet("background: transparent;")
        inner.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        label = QLabel(text)
        label.setFont(QFont(_FONT, 11))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: transparent; border: none;")
        inner.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_status_only(self) -> None:
        """设为纯状态指示器（保留 checkable 以配合 update_mode，但禁止点击切换）"""
        self._status_only = True
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(self._STATUS_STYLE)

    def mousePressEvent(self, event) -> None:
        if getattr(self, "_status_only", False):
            return  # 阻止点击切换 checked 状态
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """TandOrbit 主窗口"""

    mode_switch_requested = Signal(Mode)
    sleep_display_requested = Signal()
    settings_requested = Signal()

    _SETTINGS_STYLE = f"""
        QPushButton {{
            border: none;
            background: transparent;
            padding: 4px;
            border-radius: 6px;
        }}
        QPushButton:hover {{
            background: {_COLORS['settings_hover']};
        }}
    """

    def __init__(self, base_dir: Path | None = None, hotkeys: dict[str, str] | None = None) -> None:
        super().__init__()
        self._base_dir = base_dir or _resource_path(".")
        self._hotkeys = hotkeys or {
            "switch_mac": "Ctrl+Option+1" if platform.system() == "Darwin" else "Ctrl+Alt+1",
            "switch_windows": "Ctrl+Option+2" if platform.system() == "Darwin" else "Ctrl+Alt+2",
            "switch_share": "Ctrl+Option+3" if platform.system() == "Darwin" else "Ctrl+Alt+3",
        }
        self.setWindowTitle("TandOrbit")
        self.setFixedSize(320, 320)
        self.setStyleSheet(f"background-color: {_COLORS['window_bg']};")
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建界面"""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 16)

        # --- 图标 + 标题 ---
        icon_label = QLabel()
        pixmap = QPixmap(str(self._base_dir / "icon.png"))
        # Retina: 用 2 倍物理像素渲染，避免模糊
        dpr = self.devicePixelRatio()
        size = int(48 * dpr)
        scaled = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        icon_label.setPixmap(scaled)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel("TandOrbit")
        title.setFont(QFont(_FONT, 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {_COLORS['text']};")
        layout.addWidget(title)

        layout.addSpacing(12)

        # --- 设备状态（横向，与按钮列对齐） ---
        self._mac_status = StatusIndicator("Mac")
        self._win_status = StatusIndicator("Windows")
        self._deskflow_status = StatusIndicator("Deskflow")

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        for indicator in [self._mac_status, self._win_status, self._deskflow_status]:
            indicator.setFont(QFont(_FONT, 11))
            status_row.addWidget(indicator)
        layout.addLayout(status_row)

        layout.addSpacing(6)

        # --- 模式指示器 / 切换按钮（横向排列） ---
        local_mode = Mode.MAC if sys.platform == "darwin" else Mode.WINDOWS
        self._mode_buttons: dict[Mode, ModeButton] = {}
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        for mode, (svg, text) in _MODE_CONFIG.items():
            btn = ModeButton(text, mode, svg, self._base_dir)
            if mode == local_mode:
                btn.set_status_only()
            else:
                btn.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(m))
            self._mode_buttons[mode] = btn
            self._mode_group.addButton(btn)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        layout.addSpacing(8)

        # --- 快捷键提示（与按钮列对齐） ---
        self._hk_labels: list[QLabel] = []
        hk_row = QHBoxLayout()
        hk_row.setSpacing(12)
        for key in ("switch_mac", "switch_windows", "switch_share"):
            lbl = QLabel(self._hotkeys.get(key, ""))
            lbl.setFont(QFont(_FONT, 10))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {_COLORS['text_secondary']};")
            self._hk_labels.append(lbl)
            hk_row.addWidget(lbl)
        layout.addLayout(hk_row)

        layout.addSpacing(6)

        # --- 底部工具按钮（关闭显示器 + 设置） ---
        tool_row = QHBoxLayout()
        tool_row.setSpacing(24)
        tool_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sleep_btn = self._make_icon_button("resources/sleep.svg")
        sleep_btn.clicked.connect(self._confirm_sleep)
        tool_row.addWidget(sleep_btn)

        settings_btn = self._make_icon_button("resources/setting.svg")
        settings_btn.clicked.connect(self.settings_requested.emit)
        tool_row.addWidget(settings_btn)

        layout.addLayout(tool_row)

    def _make_icon_button(self, svg_path: str) -> QPushButton:
        """创建无边框图标按钮"""
        btn = QPushButton()
        btn.setFixedSize(32, 32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._SETTINGS_STYLE)

        icon = QSvgWidget(str(self._base_dir / svg_path))
        icon.setFixedSize(20, 20)
        icon.setStyleSheet("background: transparent;")
        inner = QVBoxLayout(btn)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        return btn

    def _on_mode_clicked(self, mode: Mode) -> None:
        """模式按钮点击"""
        self.mode_switch_requested.emit(mode)

    def update_mode(self, mode: Mode) -> None:
        """更新当前模式显示"""
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)

    def update_hotkeys(self, hotkeys: dict[str, str]) -> None:
        """更新快捷键提示"""
        self._hotkeys = hotkeys
        keys = ("switch_mac", "switch_windows", "switch_share")
        for lbl, key in zip(self._hk_labels, keys):
            lbl.setText(hotkeys.get(key, ""))

    def update_device_status(self, mac_online: bool, win_online: bool, deskflow_connected: bool) -> None:
        """更新设备状态"""
        self._mac_status.update_status(mac_online)
        self._win_status.update_status(win_online)
        self._deskflow_status.update_status(deskflow_connected)

    def _confirm_sleep(self) -> None:
        """确认关闭显示器（带 3 秒倒计时）"""
        msg = QMessageBox(self)
        msg.setWindowTitle("关闭显示器")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)

        countdown = [3]

        def _update_text():
            if countdown[0] > 0:
                msg.setText(f"将在 {countdown[0]} 秒后关闭显示器...")
                countdown[0] -= 1
            else:
                timer.stop()
                msg.done(QMessageBox.StandardButton.Ok)

        timer = QTimer(self)
        timer.timeout.connect(_update_text)

        _update_text()
        timer.start(1000)

        result = msg.exec()
        timer.stop()

        if result == QMessageBox.StandardButton.Ok:
            self.sleep_display_requested.emit()

"""Desktop control panel for switching work modes."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from app.enums import Mode
from app.gui.devices import DeviceView, devices_for
from app.gui.display_diagram import DisplayDiagram
from app.gui.theme import ElidedLabel, button, card, colors, icon, label, stylesheet

MODE_INFO = {
    Mode.MAC: ("Mac", "laptop", "switch_mac"),
    Mode.WINDOWS: ("Windows", "tower", "switch_windows"),
    Mode.SHARE: ("共享", "share", "switch_share"),
}
MODE_PLATFORM = {Mode.MAC: "mac", Mode.WINDOWS: "windows"}
BUSY_PHASES = frozenset((
    "queued", "waking", "prepare", "activate", "release", "verify", "commit",
    "decision_commit", "recovering",
))
PHASE_LABELS = {
    "queued": "排队中", "waking": "正在等待 Windows 上线", "prepare": "正在检查设备和保存布局",
    "activate": "正在启用目标输出", "release": "正在释放原输出", "verify": "正在验证两端显示",
    "decision_commit": "正在确认提交", "commit": "正在提交", "committed": "切换完成",
    "recovering": "待恢复", "restored": "已恢复原输出", "unpaired": "打开设置 → 开始使用，连接两台电脑",
    "local_restored": "已恢复本机显示", "connection_error": "连接异常", "failed": "操作失败",
}


def _resource_path(relative: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    root = Path(__file__).resolve().parent.parent.parent
    if (root / "resources").is_dir():
        return root / relative
    return Path(sys.prefix) / "share" / "tandorbit" / relative


def mode_name(mode: Mode, devices: dict[str, DeviceView] | None = None) -> str:
    if mode == Mode.SHARE:
        return "双机共享"
    if mode in MODE_PLATFORM:
        name = devices[MODE_PLATFORM[mode]].name if devices else MODE_INFO[mode][0]
        return f"{name} · 双屏"
    return "待确认"


class StatusIndicator(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._online = False
        self._local = False
        self._paired = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        self._dot = QLabel()
        self._dot.setFixedSize(5, 5)
        row.addWidget(self._dot)
        self._label = ElidedLabel("caption")
        row.addWidget(self._label, 1)
        self._state = label("", "caption")
        row.addWidget(self._state)
        row.addStretch(1)

    def set_identity(self, device: DeviceView) -> None:
        self._local = device.is_local
        self._paired = device.key is not None
        self._label.set_name(device.name)
        self._label.setMaximumWidth(self._label.fontMetrics().horizontalAdvance(device.name) + 3)
        self.update_status(self._online)

    def update_status(self, online: bool) -> None:
        self._online = online
        c = colors()
        self._dot.setStyleSheet(f"background: {c['green' if online else 'trace']};")
        if self._local:
            status = "本机"
        elif not self._paired:
            status = "未配对"
        else:
            status = "在线" if online else "离线"
        self._state.setText(f"· {status}")
        self.setAccessibleName(f"{self._label.accessibleName()} · {status}")


class ModeButton(QPushButton):
    def __init__(self, text: str, shortcut: str) -> None:
        super().__init__()
        self.setProperty("mode-card", True)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content = QVBoxLayout(self)
        content.setContentsMargins(8, 5, 8, 6)
        content.setSpacing(2)
        self._label = ElidedLabel("section")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self._label)
        self._shortcut = ElidedLabel("caption")
        self._shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._shortcut.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        content.addWidget(self._shortcut)
        for child in (self._label, self._shortcut):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._shortcut_text = ""
        self.set_identity(text)
        self.set_shortcut(shortcut)

    def nextCheckState(self) -> None:
        # The coordinator is the source of truth for the checked state.
        pass

    def set_identity(self, name: str) -> None:
        self._label.set_name(name)
        self._update_accessibility()

    def set_shortcut(self, shortcut: str) -> None:
        self._shortcut_text = shortcut.replace("+", " + ")
        if sys.platform == "darwin":
            marks = {"ctrl": "⌃", "option": "⌥", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
            display = "".join(marks.get(key.lower(), key) for key in shortcut.split("+"))
        else:
            display = shortcut.replace("+", " + ")
        self._shortcut.set_name(display)
        self._shortcut.setVisible(bool(shortcut))
        self._update_accessibility()

    def _update_accessibility(self) -> None:
        text = " · ".join(filter(None, (self._label.accessibleName(), self._shortcut_text)))
        self.setAccessibleName(text)
        self.setToolTip(text)


class MainWindow(QMainWindow):
    mode_switch_requested = Signal(Mode)
    sleep_display_requested = Signal()
    settings_requested = Signal()
    recover_requested = Signal()
    history_requested = Signal()
    logs_requested = Signal()

    def __init__(self, base_dir: Path | None = None, hotkeys: dict[str, str] | None = None) -> None:
        super().__init__()
        self._hotkeys = hotkeys if hotkeys is not None else {
            key: f"Ctrl+{'Option' if sys.platform == 'darwin' else 'Alt'}+{number}"
            for number, (*_, key) in enumerate(MODE_INFO.values(), 1)
        }
        self._mode = Mode.UNKNOWN
        self._share_role = None
        self._devices: dict[str, DeviceView] = {}
        self.setWindowTitle("TandOrbit")
        self.setWindowIcon(QIcon(str((base_dir or _resource_path(".")) / "resources/icon.png")))
        self.setStyleSheet(stylesheet() + self._panel_styles())
        self._setup_ui()
        self.setMinimumWidth(448)
        self.set_devices(*devices_for({}, "mac" if sys.platform == "darwin" else "windows"))
        self.resize(624, 520)

    @staticmethod
    def _panel_styles() -> str:
        c = colors()
        return f"""
            QFrame[role="command-bar"] {{
                background: {c['subtle']}; border-bottom: 1px solid {c['stroke']};
            }}
            QFrame[role="mode-strip"] {{
                border-top: 1px solid {c['stroke']}; border-bottom: 1px solid {c['stroke']};
            }}
            QPushButton[mode-card="true"] {{
                background: transparent; border: 1px solid transparent;
                border-bottom-width: 2px; border-radius: 0; padding: 0;
                min-height: 48px;
            }}
            QPushButton[mode-card="true"]:hover {{ background: {c['subtle']}; }}
            QPushButton[mode-card="true"]:checked {{
                border-bottom-color: {c['accent']}; background: {c['accent_soft']};
            }}
            QPushButton[mode-card="true"]:focus {{ border-color: {c['selected_stroke']}; }}
        """

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCentralWidget(central)
        central.setFocus()
        body = QVBoxLayout(central)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        command_bar = card("command-bar")
        command = QHBoxLayout(command_bar)
        command.setContentsMargins(15, 2, 11, 2)
        command.setSpacing(5)
        brand = QLabel()
        brand.setPixmap(icon("share", colors()["text"]).pixmap(22, 22))
        command.addWidget(brand)
        command.addWidget(label("TandOrbit", "section"))
        command.addStretch()
        for caption, glyph, signal in (
            ("日志", "logs", self.logs_requested),
            ("切换记录", "history", self.history_requested),
            ("设置", "settings", self.settings_requested),
        ):
            action = button(caption, glyph, icon_only=True)
            action.clicked.connect(signal.emit)
            command.addWidget(action)
        body.addWidget(command_bar)

        panel = QVBoxLayout()
        panel.setContentsMargins(16, 10, 16, 13)
        panel.setSpacing(9)
        body.addLayout(panel, 1)
        header = QHBoxLayout()
        header.addWidget(label("屏幕分配", "title"))
        header.addStretch()
        self._mode_dot = QLabel()
        self._mode_dot.setFixedSize(6, 6)
        header.addWidget(self._mode_dot)
        self._mode_title = label("")
        header.addWidget(self._mode_title)
        panel.addLayout(header)

        self._preview = DisplayDiagram()
        panel.addWidget(self._preview, 1)

        state_layout = QHBoxLayout()
        state_layout.setContentsMargins(1, 0, 1, 0)
        state_layout.setSpacing(12)
        self._mac_status = StatusIndicator()
        self._win_status = StatusIndicator()
        self._input_status = label("键鼠未就绪", "caption")
        for index, indicator in enumerate((self._mac_status, self._win_status, self._input_status)):
            if index:
                divider = card("separator")
                divider.setFixedSize(1, 12)
                state_layout.addWidget(divider)
            state_layout.addWidget(indicator, 1 if index < 2 else 0)
        panel.addLayout(state_layout)

        mode_strip = card("mode-strip")
        modes = QHBoxLayout(mode_strip)
        modes.setContentsMargins(0, 1, 0, 1)
        modes.setSpacing(0)
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict[Mode, ModeButton] = {}
        for mode, (text, _, key) in MODE_INFO.items():
            if modes.count():
                rule = card("separator")
                rule.setFixedSize(1, 24)
                modes.addWidget(rule)
            control = ModeButton(text, self._hotkeys.get(key, ""))
            control.clicked.connect(lambda _checked, m=mode: self.mode_switch_requested.emit(m))
            self._mode_group.addButton(control)
            self._mode_buttons[mode] = control
            modes.addWidget(control, 1)
        panel.addWidget(mode_strip)

        divider = card("separator")
        divider.setFixedHeight(1)
        panel.addWidget(divider)
        footer = QHBoxLayout()
        footer.setSpacing(7)
        self._notice = card("notice")
        message_layout = QHBoxLayout(self._notice)
        message_layout.setContentsMargins(5, 3, 5, 3)
        message_layout.setSpacing(6)
        self._notice_icon = QLabel()
        message_layout.addWidget(self._notice_icon, alignment=Qt.AlignmentFlag.AlignTop)
        self._operation = label("等待设备状态", "caption", wrap=True)
        message_layout.addWidget(self._operation, 1)
        footer.addWidget(self._notice, 1)
        sleep = button("关闭显示器", kind="ghost")
        sleep.clicked.connect(self._confirm_sleep)
        recover = button("恢复本机显示", kind="ghost")
        recover.clicked.connect(self.recover_requested.emit)
        footer.addWidget(sleep)
        footer.addWidget(recover)
        panel.addLayout(footer)
        self._show_notice("等待设备状态", "", "info")

    def set_devices(self, local: DeviceView, peer: DeviceView) -> None:
        self._devices = {device.platform: device for device in (local, peer)}
        for platform, status in (("mac", self._mac_status), ("windows", self._win_status)):
            device = self._devices[platform]
            status.set_identity(device)
        for mode, platform in MODE_PLATFORM.items():
            device = self._devices[platform]
            self._mode_buttons[mode].set_identity(device.name)
        self._render_mode()

    def update_mode(self, mode: Mode, share_role: str | None = None) -> None:
        changed = mode != self._mode
        if changed or share_role:
            self._share_role = share_role
        self._mode = mode
        self._render_mode()
        if changed and mode == Mode.UNKNOWN:
            self._show_notice("等待设备状态", "", "info")
        elif mode != Mode.UNKNOWN and self._operation.text() == "等待设备状态":
            self._show_notice("已确认当前模式", "success", "check")

    def _render_mode(self) -> None:
        mode = self._mode
        if mode == Mode.SHARE:
            title = "共享中" if self._share_role in ("primary", "secondary") else "等待确认归属"
        else:
            title = "单机双屏" if mode in MODE_PLATFORM else "待确认"
        self._mode_title.setText(title)
        ink = colors()["accent" if mode != Mode.UNKNOWN else "muted"]
        self._mode_dot.setStyleSheet(f"background: {ink};")
        self._mode_title.setStyleSheet(f"color: {ink};")
        owners = (None, None)
        if mode in MODE_PLATFORM:
            owner = self._devices[MODE_PLATFORM[mode]]
            owners = (owner, owner)
        elif mode == Mode.SHARE and self._share_role in ("primary", "secondary"):
            mac, windows = self._devices["mac"], self._devices["windows"]
            owners = (windows, mac) if self._share_role == "primary" else (mac, windows)
        self._preview.update_owners(*owners)
        self._mode_group.setExclusive(False)
        for value, control in self._mode_buttons.items():
            control.setChecked(value == mode)
        self._mode_group.setExclusive(True)

    def _show_notice(self, text: str, tone: str, glyph: str) -> None:
        color = colors()[{"success": "green", "warning": "amber", "error": "red"}.get(tone, "accent")]
        self._notice.setProperty("tone", tone)
        self._notice.style().unpolish(self._notice)
        self._notice.style().polish(self._notice)
        self._notice_icon.setPixmap(icon(glyph, color).pixmap(16, 16))
        self._operation.setText(text)

    def show_operation(self, record: dict) -> None:
        phase = record["phase"]
        if phase == "sharing":
            self._input_status.setText("键鼠就绪" if record["input"] else "键鼠未就绪")
            self._input_status.setToolTip(
                f"剪贴板{'已就绪' if record['clipboard'] else '未启用或未就绪'}"
            )
            return
        if phase == "audio_warning":
            self._show_notice(record.get("error", "音频输出无法切换"), "warning", "alert")
            return
        target = Mode.__members__.get(record.get("target", ""))
        if phase == "committed" and target is not None:
            self.update_mode(target, record.get("share_role"))
        for control in self._mode_buttons.values():
            control.setEnabled(phase not in BUSY_PHASES)
        tone, glyph = ("progress", "refresh") if phase in BUSY_PHASES else ("", "info")
        if phase in ("committed", "local_restored"):
            tone, glyph = "success", "check"
        if phase in ("recovering", "restored"):
            tone, glyph = "warning", "alert"
        if phase in ("failed", "connection_error"):
            tone, glyph = "error", "alert"
        detail = record.get("error") or record.get("warning")
        self._show_notice(" · ".join(filter(None, (
            mode_name(target, self._devices) if target is not None and phase != "committed" else None,
            PHASE_LABELS.get(phase, "操作失败"),
            detail,
        ))), tone, glyph)

    def update_hotkeys(self, hotkeys: dict[str, str]) -> None:
        for mode, (*_, key) in MODE_INFO.items():
            self._mode_buttons[mode].set_shortcut(hotkeys.get(key, ""))

    def update_connection_status(self, mac_online: bool, windows_online: bool) -> None:
        self._mac_status.update_status(mac_online)
        self._win_status.update_status(windows_online)

    def _confirm_sleep(self) -> None:
        message = QMessageBox(self)
        message.setWindowTitle("关闭显示器")
        message.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        message.setDefaultButton(QMessageBox.StandardButton.Cancel)
        message.button(QMessageBox.StandardButton.Ok).setText("立即关闭")
        message.button(QMessageBox.StandardButton.Cancel).setText("取消")
        countdown = 3
        message.setText(f"将在 {countdown} 秒后关闭本机显示器。")
        timer = QTimer(message)

        def tick() -> None:
            nonlocal countdown
            countdown -= 1
            if countdown == 0:
                message.done(QMessageBox.StandardButton.Ok)
            else:
                message.setText(f"将在 {countdown} 秒后关闭本机显示器。")

        timer.timeout.connect(tick)
        timer.start(1000)
        if message.exec() == QMessageBox.StandardButton.Ok:
            self.sleep_display_requested.emit()
        timer.stop()

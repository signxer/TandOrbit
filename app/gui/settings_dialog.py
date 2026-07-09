"""TandOrbit 设置对话框

配置管理界面。
"""

from __future__ import annotations

import platform

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from typing import Any, Callable

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, ConfigManager

_MODIFIER_MAP = {
    Qt.Key.Key_Control: "Ctrl",
    Qt.Key.Key_Shift: "Shift",
    Qt.Key.Key_Alt: "Option" if platform.system() == "Darwin" else "Alt",
    Qt.Key.Key_Meta: "Cmd" if platform.system() == "Darwin" else "Win",
}


class HotkeyEdit(QLineEdit):
    """点击后录制快捷键的输入框"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击录制...")
        self._recording = False

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self._recording = True
        self.setText("")
        self.setPlaceholderText("请按下快捷键...")

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._recording = False
        if not self.text():
            self.setPlaceholderText("点击录制...")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            return super().keyPressEvent(event)

        # 纯修饰键不记录，等待下一个非修饰键
        if event.key() in _MODIFIER_MAP:
            mods = self._format_mods(event.modifiers())
            self.setText(mods + "+")
            return

        parts: list[str] = []
        mods = event.modifiers()
        for mod_key, label in _MODIFIER_MAP.items():
            attr = mod_key.name.replace("Key_", "") + "Modifier"
            if mods & getattr(Qt.KeyboardModifier, attr):
                parts.append(label)

        key_name = self._key_to_name(event.key())
        parts.append(key_name)
        self.setText("+".join(parts))
        self._recording = False
        self.clearFocus()

    def _format_mods(self, mods: Qt.KeyboardModifier) -> str:
        parts: list[str] = []
        for mod_key, label in _MODIFIER_MAP.items():
            attr = mod_key.name.replace("Key_", "") + "Modifier"
            if mods & getattr(Qt.KeyboardModifier, attr):
                parts.append(label)
        return "+".join(parts)

    def _key_to_name(self, key: int) -> str:
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(key)
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key)
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
            return f"F{key - Qt.Key.Key_F1 + 1}"
        names = {
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Return: "Return",
            Qt.Key.Key_Enter: "Enter",
            Qt.Key.Key_Escape: "Esc",
            Qt.Key.Key_Backspace: "Backspace",
            Qt.Key.Key_Delete: "Delete",
            Qt.Key.Key_Up: "↑",
            Qt.Key.Key_Down: "↓",
            Qt.Key.Key_Left: "←",
            Qt.Key.Key_Right: "→",
        }
        return names.get(key, event_key_name(key))


def event_key_name(key: int) -> str:
    """兜底：用 QKeySequence 取名字"""
    from PySide6.QtGui import QKeySequence
    return QKeySequence(key).toString()


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(
        self,
        config_manager: ConfigManager,
        plugin_provider: Callable[[], dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_manager = config_manager
        self._plugin_provider = plugin_provider
        self.setWindowTitle("TandOrbit 设置")
        self.setMinimumWidth(480)
        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_connection_tab(), "连接")
        tabs.addTab(self._create_display_tab(), "显示器")
        tabs.addTab(self._create_deskflow_tab(), "Deskflow")
        tabs.addTab(self._create_audio_tab(), "音频")
        tabs.addTab(self._create_hotkeys_tab(), "快捷键")
        layout.addWidget(tabs)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _create_connection_tab(self) -> QWidget:
        """连接配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("Windows Agent")
        form = QFormLayout(group)
        self._win_host = QLineEdit()
        self._win_port = QSpinBox()
        self._win_port.setRange(1, 65535)
        form.addRow("主机地址:", self._win_host)
        form.addRow("端口:", self._win_port)
        layout.addRow(group)
        return widget

    def _create_display_tab(self) -> QWidget:
        """显示器配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("显示器设置")
        form = QFormLayout(group)
        self._primary_id = QComboBox()
        self._secondary_id = QComboBox()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedWidth(60)
        refresh_btn.clicked.connect(self._refresh_displays)
        hint = QLabel("选择显示器后对应 ID 会自动填入配置")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("主显示器:", self._primary_id)
        form.addRow("副显示器:", self._secondary_id)
        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addStretch()
        form.addRow("", row)
        form.addRow("", hint)
        layout.addRow(group)
        return widget

    def _create_deskflow_tab(self) -> QWidget:
        """Deskflow 配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("Deskflow 设置")
        form = QFormLayout(group)
        self._df_host = QLineEdit()
        self._df_port = QSpinBox()
        self._df_port.setRange(1, 65535)
        self._df_client = QLineEdit()
        form.addRow("服务器地址:", self._df_host)
        form.addRow("端口:", self._df_port)
        form.addRow("客户端名称:", self._df_client)
        layout.addRow(group)
        return widget

    def _create_audio_tab(self) -> QWidget:
        """音频配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("音频设置")
        form = QFormLayout(group)
        self._mac_audio = QComboBox()
        self._mac_audio.setEditable(True)
        self._win_audio = QComboBox()
        self._win_audio.setEditable(True)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedWidth(60)
        refresh_btn.clicked.connect(self._refresh_audio)
        form.addRow("Mac 音频输出:", self._mac_audio)
        form.addRow("Windows 音频输出:", self._win_audio)
        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addStretch()
        form.addRow("", row)
        layout.addRow(group)
        return widget

    def _create_hotkeys_tab(self) -> QWidget:
        """快捷键配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("模式切换快捷键")
        form = QFormLayout(group)
        self._hk_mac = HotkeyEdit()
        self._hk_win = HotkeyEdit()
        self._hk_share = HotkeyEdit()
        hint = QLabel("点击输入框后按下快捷键组合")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("Mac 模式:", self._hk_mac)
        form.addRow("Windows 模式:", self._hk_win)
        form.addRow("共享模式:", self._hk_share)
        form.addRow("", hint)
        layout.addRow(group)
        return widget

    def _load_values(self) -> None:
        """加载当前配置值"""
        cfg = self._config_manager.config
        self._win_host.setText(cfg.windows.host)
        self._win_port.setValue(cfg.windows.port)
        self._df_host.setText(cfg.deskflow.server_host)
        self._df_port.setValue(cfg.deskflow.server_port)
        self._df_client.setText(cfg.deskflow.client_name)

        # 显示器 — 尝试从插件获取列表
        self._refresh_displays()
        self._set_combo_value(self._primary_id, str(cfg.display.primary_id))
        self._set_combo_value(self._secondary_id, str(cfg.display.secondary_id))

        # 音频 — 尝试从插件获取列表
        self._refresh_audio()
        self._set_combo_value(self._mac_audio, cfg.audio.mac_output)
        self._set_combo_value(self._win_audio, cfg.audio.windows_output)

        # 快捷键
        default_mod = "Ctrl+Option" if platform.system() == "Darwin" else "Ctrl+Alt"
        self._hk_mac.setText(cfg.hotkeys.get("switch_mac", f"{default_mod}+1"))
        self._hk_win.setText(cfg.hotkeys.get("switch_windows", f"{default_mod}+2"))
        self._hk_share.setText(cfg.hotkeys.get("switch_share", f"{default_mod}+3"))

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """设置 ComboBox 的值，如果不在列表中则插入"""
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(value)

    def _refresh_displays(self) -> None:
        """从插件刷新显示器列表"""
        if not self._plugin_provider:
            return
        plugins = self._plugin_provider()
        display_plugin = plugins.get("betterdisplay")
        if not display_plugin:
            return
        try:
            displays = display_plugin.list_displays()
            # list_displays 是异步的，需要在同步上下文中处理
            import asyncio
            if asyncio.iscoroutine(displays):
                loop = asyncio.new_event_loop()
                displays = loop.run_until_complete(displays)
                loop.close()
        except Exception:
            displays = []

        self._primary_id.clear()
        self._secondary_id.clear()
        for d in displays:
            label = f"{d.id} - {d.name}"
            self._primary_id.addItem(label, str(d.id))
            self._secondary_id.addItem(label, str(d.id))

    def _refresh_audio(self) -> None:
        """从插件刷新音频设备列表"""
        if not self._plugin_provider:
            return
        plugins = self._plugin_provider()
        audio_plugin = plugins.get("audio")
        if not audio_plugin:
            return
        try:
            devices = audio_plugin.list_devices()
            import asyncio
            if asyncio.iscoroutine(devices):
                loop = asyncio.new_event_loop()
                devices = loop.run_until_complete(devices)
                loop.close()
        except Exception:
            devices = []

        for combo in (self._mac_audio, self._win_audio):
            current = combo.currentText()
            combo.clear()
            for name in devices:
                combo.addItem(name)
            if current:
                self._set_combo_value(combo, current)

    def _save(self) -> None:
        """保存配置"""
        primary_id = int(self._primary_id.currentData() or self._primary_id.currentText() or 1)
        secondary_id = int(self._secondary_id.currentData() or self._secondary_id.currentText() or 2)
        updates = {
            "windows": {
                "host": self._win_host.text(),
                "port": self._win_port.value(),
            },
            "display": {
                "primary_id": primary_id,
                "secondary_id": secondary_id,
            },
            "deskflow": {
                "server_host": self._df_host.text(),
                "server_port": self._df_port.value(),
                "client_name": self._df_client.text(),
            },
            "audio": {
                "mac_output": self._mac_audio.currentText(),
                "windows_output": self._win_audio.currentText(),
            },
            "hotkeys": {
                "switch_mac": self._hk_mac.text(),
                "switch_windows": self._hk_win.text(),
                "switch_share": self._hk_share.text(),
            },
        }
        self._config_manager.update(updates)
        self.accept()

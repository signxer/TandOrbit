"""TandOrbit 设置对话框

配置管理界面。
"""

from __future__ import annotations

import platform
from pathlib import Path

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
from app.communication.discovery import DiscoveryService
from app.gui.main_window import _COLORS, _FONT

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
        self.setMinimumWidth(540)
        self.setStyleSheet(self._build_stylesheet())
        self._setup_ui()
        self._load_values()

    @staticmethod
    def _build_stylesheet() -> str:
        c = _COLORS
        f = _FONT
        return f"""
            * {{
                font-family: "{f}";
                font-size: 13px;
            }}
            QDialog {{
                background: {c['window_bg']};
                color: {c['text']};
            }}
            QTabWidget::pane {{
                border: 1px solid {c['border']};
                border-radius: 6px;
                background: {c['window_bg']};
                margin-top: -1px;
            }}
            QTabBar::tab {{
                background: {c['bg']};
                color: {c['text_secondary']};
                border: 1px solid {c['border']};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 6px 16px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {c['window_bg']};
                color: {c['text']};
                border-bottom: 1px solid {c['window_bg']};
            }}
            QGroupBox {{
                font-weight: bold;
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px 12px 8px 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }}
            QLabel {{
                color: {c['text']};
            }}
            QLineEdit, QSpinBox {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 5px 8px;
                selection-background-color: {c['checked_bg']};
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border-color: {c['checked_border']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 16px;
                border: none;
                background: {c['hover']};
                border-radius: 2px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {c['checked_bg']};
            }}
            QComboBox {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 5px 8px;
                min-height: 20px;
            }}
            QComboBox:focus {{
                border-color: {c['checked_border']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                border-left: 1px solid {c['border']};
                border-radius: 0 6px 6px 0;
            }}
            QComboBox QAbstractItemView {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                selection-background-color: {c['checked_bg']};
                selection-color: {c['text']};
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 4px 8px;
                min-height: 24px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {c['checked_bg']};
            }}
            QPushButton {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 18px;
            }}
            QPushButton:hover {{
                background: {c['hover']};
            }}
            QPushButton:pressed {{
                background: {c['checked_bg']};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c['border']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c['text_secondary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

    def _setup_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_connection_tab(), "连接")
        tabs.addTab(self._create_display_tab(), "显示器")
        tabs.addTab(self._create_deskflow_tab(), "Deskflow")
        tabs.addTab(self._create_audio_tab(), "音频")
        tabs.addTab(self._create_hotkeys_tab(), "快捷键")
        if platform.system() != "Darwin":
            tabs.addTab(self._create_tools_tab(), "工具")
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

        is_mac = platform.system() == "Darwin"

        # --- 本机配置（可编辑） ---
        local_group = QGroupBox("本机")
        local_form = QFormLayout(local_group)
        self._local_port = QSpinBox()
        self._local_port.setRange(1, 65535)
        local_form.addRow("监听端口:", self._local_port)

        # WoL 网卡下拉
        self._wol_nic = QComboBox()
        self._wol_nic.setMinimumWidth(220)
        self._refresh_nics()
        local_form.addRow("WoL 网卡:", self._wol_nic)
        nic_hint = QLabel("选择支持网络唤醒的网卡，用于被对端 WoL 唤醒")
        nic_hint.setStyleSheet("color: #888; font-size: 11px;")
        local_form.addRow("", nic_hint)
        layout.addRow(local_group)

        # --- 对端信息（自动发现，只读） ---
        remote_label = "Windows" if is_mac else "Mac"
        remote_group = QGroupBox(f"对端（{remote_label} · 自动发现）")
        remote_form = QFormLayout(remote_group)

        self._remote_status = QLabel("●  等待发现...")
        self._remote_status.setStyleSheet("color: #9E9E9E; font-size: 12px;")
        remote_form.addRow("状态:", self._remote_status)

        self._remote_host = QLabel("—")
        self._remote_host.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        remote_form.addRow("主机地址:", self._remote_host)

        self._remote_port = QLabel("—")
        remote_form.addRow("端口:", self._remote_port)

        self._remote_mac = QLabel("—")
        self._remote_mac.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        remote_form.addRow("MAC 地址:", self._remote_mac)

        layout.addRow(remote_group)

        # 兼容字段（_save 中需要，但不在 UI 显示）
        self._win_host = QLineEdit()
        self._win_mac = QLineEdit()
        self._win_port = QSpinBox()
        self._mac_host = QLineEdit()
        self._mac_mac = QLineEdit()
        self._mac_port = QSpinBox()

        return widget

    def _refresh_nics(self) -> None:
        """刷新网卡列表"""
        self._wol_nic.clear()
        nics = DiscoveryService.list_nics()
        for nic in nics:
            self._wol_nic.addItem(f"{nic['name']}  ({nic['mac']})", nic["name"])

    def refresh_remote_info(self) -> None:
        """刷新对端信息（由 discovery 回调触发）"""
        cfg = self._config_manager.config
        is_mac = platform.system() == "Darwin"
        if is_mac:
            host = cfg.windows.host
            port = cfg.windows.port
            mac = cfg.windows.mac_address
        else:
            host = cfg.mac.host
            port = cfg.mac.port
            mac = cfg.mac.mac_address

        if host and host != "192.168.1.100":
            self._remote_status.setText("●  已发现")
            self._remote_status.setStyleSheet("color: #4CAF50; font-size: 12px;")
            self._remote_host.setText(host)
            self._remote_port.setText(str(port))
            self._remote_mac.setText(mac or "（未广播）")
        else:
            self._remote_status.setText("●  等待发现...")
            self._remote_status.setStyleSheet("color: #9E9E9E; font-size: 12px;")
            self._remote_host.setText("—")
            self._remote_port.setText("—")
            self._remote_mac.setText("—")

    def _create_display_tab(self) -> QWidget:
        """显示器配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("显示器设置")
        form = QFormLayout(group)
        self._primary_id = QComboBox()
        self._primary_id.setMinimumWidth(320)
        self._secondary_id = QComboBox()
        self._secondary_id.setMinimumWidth(320)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedWidth(60)
        refresh_btn.clicked.connect(self._refresh_displays)
        self._share_display = QComboBox()
        self._share_display.setMinimumWidth(320)
        hint = QLabel("选择显示器后对应 ID 会自动填入配置")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("主显示器:", self._primary_id)
        form.addRow("副显示器:", self._secondary_id)
        form.addRow("共享模式留 Windows:", self._share_display)
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
        self._mac_audio.setMinimumWidth(320)
        self._win_audio = QComboBox()
        self._win_audio.setEditable(True)
        self._win_audio.setMinimumWidth(320)
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

    def _create_tools_tab(self) -> QWidget:
        """外部工具路径配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("外部工具路径")
        form = QFormLayout(group)

        # MultiMonitorTool
        self._mmt_path = QLineEdit()
        mmt_btn = QPushButton("浏览...")
        mmt_btn.setFixedWidth(70)
        mmt_btn.clicked.connect(lambda: self._browse_file(self._mmt_path))
        mmt_row = QHBoxLayout()
        mmt_row.addWidget(self._mmt_path)
        mmt_row.addWidget(mmt_btn)
        form.addRow("MultiMonitorTool:", mmt_row)

        # ControlMyMonitor
        self._cmm_path = QLineEdit()
        cmm_btn = QPushButton("浏览...")
        cmm_btn.setFixedWidth(70)
        cmm_btn.clicked.connect(lambda: self._browse_file(self._cmm_path))
        cmm_row = QHBoxLayout()
        cmm_row.addWidget(self._cmm_path)
        cmm_row.addWidget(cmm_btn)
        form.addRow("ControlMyMonitor:", cmm_row)

        # Deskflow
        self._df_path = QLineEdit()
        df_btn = QPushButton("浏览...")
        df_btn.setFixedWidth(70)
        df_btn.clicked.connect(lambda: self._browse_file(self._df_path))
        df_row = QHBoxLayout()
        df_row.addWidget(self._df_path)
        df_row.addWidget(df_btn)
        form.addRow("Deskflow:", df_row)

        hint = QLabel("填写完整路径或确保工具所在目录已加入 PATH 环境变量")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        layout.addRow(group)
        return widget

    def _browse_file(self, target: QLineEdit) -> None:
        """打开文件选择对话框"""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "选择可执行文件", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if path:
            target.setText(path)

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
        is_mac = platform.system() == "Darwin"
        if is_mac:
            self._local_port.setValue(cfg.mac.port)
        else:
            self._local_port.setValue(cfg.windows.port)

        # WoL 网卡
        if cfg.wol_nic:
            idx = self._wol_nic.findData(cfg.wol_nic)
            if idx >= 0:
                self._wol_nic.setCurrentIndex(idx)

        # 对端信息（自动发现）
        self.refresh_remote_info()
        self._df_host.setText(cfg.deskflow.server_host)
        self._df_port.setValue(cfg.deskflow.server_port)
        self._df_client.setText(cfg.deskflow.client_name)

        # 显示器 — 尝试从插件获取列表
        self._refresh_displays()
        self._set_combo_value(self._primary_id, str(cfg.display.primary_id))
        self._set_combo_value(self._secondary_id, str(cfg.display.secondary_id))
        self._set_combo_value(self._share_display, str(cfg.display.share_display_id))

        # 音频 — 尝试从插件获取列表
        self._refresh_audio()
        self._set_combo_value(self._mac_audio, cfg.audio.mac_output)
        self._set_combo_value(self._win_audio, cfg.audio.windows_output)

        # 快捷键
        default_mod = "Ctrl+Option" if platform.system() == "Darwin" else "Ctrl+Alt"
        self._hk_mac.setText(cfg.hotkeys.get("switch_mac", f"{default_mod}+1"))
        self._hk_win.setText(cfg.hotkeys.get("switch_windows", f"{default_mod}+2"))
        self._hk_share.setText(cfg.hotkeys.get("switch_share", f"{default_mod}+3"))

        # 工具路径（仅 Windows）
        if platform.system() != "Darwin":
            self._mmt_path.setText(cfg.tools.multimonitortool_path)
            self._cmm_path.setText(cfg.tools.controlmymonitor_path)
            self._df_path.setText(cfg.tools.deskflow_path)

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """设置 ComboBox 的值，按 data 匹配（data 是 ID 字符串）"""
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(value)

    def _refresh_displays(self) -> None:
        """从插件刷新显示器列表"""
        cfg = self._config_manager.config
        displays = []

        if self._plugin_provider:
            plugins = self._plugin_provider()
            display_plugin = plugins.get("betterdisplay") or plugins.get("multimonitortool")
            if display_plugin:
                try:
                    result = display_plugin.list_displays()
                    import asyncio
                    if asyncio.iscoroutine(result):
                        loop = asyncio.new_event_loop()
                        result = loop.run_until_complete(result)
                        loop.close()
                    displays = result or []
                except Exception:
                    displays = []

        self._primary_id.clear()
        self._secondary_id.clear()
        self._share_display.clear()

        if displays:
            for d in displays:
                label = f"{d.id} - {d.name}"
                self._primary_id.addItem(label, str(d.id))
                self._secondary_id.addItem(label, str(d.id))
                self._share_display.addItem(label, str(d.id))
        else:
            # 插件不可用时，用配置里的 ID 作为占位项
            for did in (cfg.display.primary_id, cfg.display.secondary_id, cfg.display.share_display_id):
                label = f"Display {did}"
                self._primary_id.addItem(label, str(did))
                self._secondary_id.addItem(label, str(did))
                self._share_display.addItem(label, str(did))

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
        share_display_id = int(self._share_display.currentData() or self._share_display.currentText() or 2)
        is_mac = platform.system() == "Darwin"

        # 本机端口
        if is_mac:
            local_config: dict[str, Any] = {"mac": {"port": self._local_port.value()}}
        else:
            local_config = {"windows": {"port": self._local_port.value()}}

        updates = {
            **local_config,
            "wol_nic": self._wol_nic.currentData() or "",
            "display": {
                "primary_id": primary_id,
                "secondary_id": secondary_id,
                "share_display_id": share_display_id,
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

        if platform.system() != "Darwin":
            updates["tools"] = {
                "multimonitortool_path": self._mmt_path.text(),
                "controlmymonitor_path": self._cmm_path.text(),
                "deskflow_path": self._df_path.text(),
            }
        self._config_manager.update(updates)
        self.accept()

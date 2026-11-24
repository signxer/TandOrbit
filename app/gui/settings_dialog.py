"""TandOrbit 设置对话框

配置管理界面。
"""

from __future__ import annotations

import asyncio
import platform
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from typing import Any, Callable

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager
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

    _displays_loaded = Signal(list)
    _audio_loaded = Signal(object)
    pairing_changed = Signal()
    _brightness_loaded = Signal(object)
    _connection_checked = Signal(str)

    def __init__(
        self,
        config_manager: ConfigManager,
        plugin_provider: Callable[[], dict[str, Any]] | None = None,
        parent: QWidget | None = None,
        *, submit=None, remote_provider=None, pairing=None, discovery=None,
    ) -> None:
        super().__init__(parent)
        self._submit = submit
        self._remote_provider = remote_provider
        self._pairing = pairing
        self._discovery = discovery
        self._display_objects = {}
        self._display_loading = False
        self._audio_loading = False
        self._config_manager = config_manager
        self._plugin_provider = plugin_provider
        self.setWindowTitle("TandOrbit 设置")
        self.setMinimumWidth(540)
        self.setStyleSheet(self._build_stylesheet())
        self._displays_loaded.connect(self._populate_displays)
        self._audio_loaded.connect(self._populate_audio)
        self._brightness_loaded.connect(self._show_brightness)
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
        tabs.addTab(self._create_sharing_tab(), "共享")
        tabs.addTab(self._create_audio_tab(), "音频")
        tabs.addTab(self._create_hotkeys_tab(), "快捷键")
        if platform.system() != "Darwin":
            tabs.addTab(self._create_tools_tab(), "工具")
        layout.addWidget(tabs)

        # 按钮
        btn_layout = QHBoxLayout()
        export_btn = QPushButton("导出配置…")
        export_btn.clicked.connect(self._export_config)
        import_btn = QPushButton("导入配置…")
        import_btn.clicked.connect(self._import_config)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(import_btn)
        btn_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _export_config(self) -> None:
        """导出配置到用户指定路径"""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "tandorbit-config.yaml", "YAML 配置 (*.yaml)"
        )
        if path and self._config_manager.export_to(path):
            QMessageBox.information(self, "导出配置", f"配置已导出到：\n{path}")
        elif path:
            QMessageBox.warning(self, "导出配置", "导出失败，请检查目标路径。")

    def _import_config(self) -> None:
        """从用户指定路径导入配置"""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "导入配置", "", "YAML 配置 (*.yaml);;所有文件 (*)"
        )
        if not path:
            return
        if QMessageBox.question(
            self, "导入配置", "导入将覆盖当前配置并重新加载，确定继续？"
        ) != QMessageBox.StandardButton.Yes:
            return
        if self._config_manager.import_from(path):
            self._load_values()  # 刷新界面
            QMessageBox.information(
                self,
                "导入配置",
                "配置已导入并重新加载。\n\n部分运行中的组件（Agent 端口、Deskflow、显示器工具）需要重启 TandOrbit 后完全生效。",
            )
        else:
            QMessageBox.warning(self, "导入配置", "导入失败，请检查文件格式。")

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

        group = QGroupBox("双机配对")
        form = QFormLayout(group)
        self._remote_status = QLabel()
        self._remote_status.setWordWrap(True)
        form.addRow(self._remote_status)
        self._connection_result = QLabel()
        self._connection_result.setWordWrap(True)
        self._connection_checked.connect(self._connection_result.setText)
        form.addRow(self._connection_result)
        self._offer_host = QLineEdit()
        if self._discovery:
            self._offer_host.setText(self._discovery._get_local_ip())
        form.addRow("本机局域网地址", self._offer_host)
        copy = QPushButton("复制本机配对信息")
        copy.clicked.connect(self._copy_offer)
        pair = QPushButton("粘贴对端配对信息…")
        pair.clicked.connect(self._pair)
        revoke = QPushButton("解除配对")
        revoke.clicked.connect(self._revoke)
        for button in (copy, pair, revoke):
            form.addRow(button)
            button.setEnabled(self._pairing is not None)
        check = QPushButton("验证两端能力")
        check.setEnabled(self._remote_provider is not None)
        check.clicked.connect(self._check_connection)
        form.addRow(check)
        layout.addRow(group)
        return widget

    def _copy_offer(self):
        import json

        nic = self._wol_nic.currentData() or ""
        mac = DiscoveryService._get_local_mac(nic) if self._pairing.role == "windows" else ""
        try:
            offer = self._pairing.offer(self._offer_host.text(), self._local_port.value(), mac)
            QApplication.clipboard().setText(json.dumps(offer))
            QMessageBox.information(self, "已复制", f"本机指纹\n{offer['fingerprint']}")
        except Exception as exc:
            QMessageBox.warning(self, "无法生成配对信息", str(exc))

    def _check_connection(self):
        async def check():
            try:
                result = await self._remote_provider()
                if not result:
                    raise ValueError("尚未建立配对连接")
                shared = "具备单屏控制" if result["single_display"] else "需要单屏控制兼容后端"
                message = f"认证通过 · 对端显示器 {len(result['display'])} 台 · {shared}"
            except Exception as exc:
                message = f"对端验证失败 · {exc}"
            self._connection_checked.emit(message)
        self._run_refresh(check())

    def _pair(self):
        import json

        text, ok = QInputDialog.getMultiLineText(self, "粘贴对端配对信息", "配对信息")
        if not ok:
            return
        try:
            if len(text) > 16 * 1024:
                raise ValueError("配对信息超过长度限制")
            offer = self._pairing.validate(json.loads(text))
            if QMessageBox.question(
                self, "核对对端设备指纹",
                f"{offer['host']}:{offer['port']}\n{offer['fingerprint']}\n\n指纹与对端显示的一致？",
            ) == QMessageBox.StandardButton.Yes:
                self._pairing.trust(offer)
                self.refresh_remote_info()
                self.pairing_changed.emit()
        except Exception as exc:
            QMessageBox.warning(self, "配对失败", str(exc))

    def _revoke(self):
        if self._pairing.peer and QMessageBox.question(
            self, "解除配对", "立即断开对端的控制和共享会话？",
        ) == QMessageBox.StandardButton.Yes:
            self._pairing.revoke()
            self.refresh_remote_info()
            self.pairing_changed.emit()

    def _refresh_nics(self) -> None:
        """刷新网卡列表"""
        self._wol_nic.clear()
        nics = DiscoveryService.list_nics()
        for nic in nics:
            self._wol_nic.addItem(f"{nic['name']}  ({nic['mac']})", nic["name"])

    def refresh_remote_info(self) -> None:
        peer = self._pairing.peer if self._pairing else None
        if peer:
            self._remote_status.setText(f"已配对 · {peer['host']}:{peer['port']}\n{peer['fingerprint']}")
        elif self._discovery and self._discovery.peer:
            self._remote_status.setText(f"发现候选 · {self._discovery.peer['host']} · 等待配对")
        else:
            self._remote_status.setText("在两台电脑上交换配对信息，并核对双方指纹。")

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
        self._share_display = QComboBox(widget)
        self._share_display.setMinimumWidth(320)
        hint = QLabel("选择显示器后对应 ID 会自动填入配置")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("主显示器:", self._primary_id)
        form.addRow("副显示器:", self._secondary_id)
        if platform.system() == "Darwin":
            form.addRow("共享模式留 Windows:", self._share_display)
        else:
            self._share_display.hide()
            form.addRow(QLabel("共享时 Windows 使用主屏还是副屏，由 Mac 端设置。"))
        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addStretch()
        form.addRow("", row)
        form.addRow("", hint)
        # 列表读取失败/插件异常时的原因提示（有数据时自动隐藏）
        self._display_status = QLabel("")
        self._display_status.setStyleSheet("color: #C0392B; font-size: 11px;")
        self._display_status.setWordWrap(True)
        self._display_status.hide()
        form.addRow("", self._display_status)
        if platform.system() == "Windows":
            self._brightness = QSpinBox()
            self._brightness.setRange(0, 100)
            self._brightness.setSuffix("%")
            self._brightness_result = QLabel()
            read = QPushButton("读取")
            read.clicked.connect(lambda: self._change_brightness(None))
            apply = QPushButton("应用")
            apply.clicked.connect(lambda: self._change_brightness(self._brightness.value()))
            controls = QHBoxLayout()
            controls.addWidget(self._brightness)
            controls.addWidget(read)
            controls.addWidget(apply)
            form.addRow("主屏亮度", controls)
            form.addRow(self._brightness_result)
        else:
            self._betterdisplay_path = QLineEdit()
            form.addRow("BetterDisplay CLI（重启后生效）", self._betterdisplay_path)
        layout.addRow(group)

        return widget

    def _change_brightness(self, amount):
        display = getattr(self, "_display_plugin", None)
        target = self._primary_id.currentData()
        if not hasattr(display, "brightness") or not target or not target.isdigit():
            self._show_brightness(None)
            return
        async def change():
            try:
                value = await display.brightness(int(target), amount)
            except OSError:
                value = None
            self._brightness_loaded.emit(value)
        self._run_refresh(change())

    def _show_brightness(self, value):
        if not hasattr(self, "_brightness_result"):
            return
        self._brightness_result.setText("显示器未报告可用的 DDC/CI 亮度控制" if value is None else "")
        if value is not None:
            self._brightness.setValue(value)

    def _create_sharing_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self._shared_keys = QCheckBox("启用键鼠共享")
        self._shared_clipboard = QCheckBox("同步新复制的纯文本")
        self._shared_host = QComboBox()
        self._shared_host.addItem("Windows", "windows")
        self._shared_host.addItem("Mac", "mac")
        self._shared_edge = QComboBox()
        for label, value in (("右侧", "right"), ("左侧", "left"), ("上方", "top"), ("下方", "bottom")):
            self._shared_edge.addItem(label, value)
        form.addRow(self._shared_keys)
        form.addRow("连接实体键鼠的电脑", self._shared_host)
        form.addRow("对端屏幕方向", self._shared_edge)
        form.addRow(self._shared_clipboard)
        hint = QLabel("两端选择同一台主控机。Ctrl + Alt（Option）+ Esc 可立即收回键鼠。")
        hint.setWordWrap(True)
        form.addRow(hint)
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
        system_audio = QPushButton("打开本机声音设置")
        system_audio.clicked.connect(self._open_audio_settings)
        form.addRow(system_audio)
        return widget

    def _open_audio_settings(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        scheme = "x-apple.systempreferences:com.apple.Sound-Settings.extension" if (
            platform.system() == "Darwin") else "ms-settings:sound"
        QDesktopServices.openUrl(QUrl(scheme))

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

        self._windows_backend = QComboBox()
        self._windows_backend.addItem("Windows 原生（默认）", "native")
        self._windows_backend.addItem("MultiMonitorTool 兼容", "multimonitortool")
        form.addRow("显示器后端（重启后生效）", self._windows_backend)

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
            self._betterdisplay_path.setText(cfg.betterdisplay.cli_path)
        else:
            self._local_port.setValue(cfg.windows.port)

        # WoL 网卡
        if cfg.wol_nic:
            idx = self._wol_nic.findData(cfg.wol_nic)
            if idx >= 0:
                self._wol_nic.setCurrentIndex(idx)

        # 对端信息（自动发现）
        self.refresh_remote_info()
        self._shared_keys.setChecked(cfg.sharing.input_enabled)
        self._shared_clipboard.setChecked(cfg.sharing.clipboard_enabled)
        self._set_combo_data(self._shared_host, cfg.sharing.controller)
        self._set_combo_data(self._shared_edge, cfg.sharing.edge)
        self._set_combo_value(self._mac_audio, cfg.audio.mac_output)
        self._set_combo_value(self._win_audio, cfg.audio.windows_output)

        # 显示器 — 异步从插件获取列表（选择恢复在 _populate_displays 中完成）
        self._refresh_displays()

        # 音频 — 异步从插件获取列表（选择恢复在 _populate_audio 中完成）
        self._refresh_audio()

        # 快捷键
        default_mod = "Ctrl+Option" if platform.system() == "Darwin" else "Ctrl+Alt"
        self._hk_mac.setText(cfg.hotkeys.get("switch_mac", f"{default_mod}+1"))
        self._hk_win.setText(cfg.hotkeys.get("switch_windows", f"{default_mod}+2"))
        self._hk_share.setText(cfg.hotkeys.get("switch_share", f"{default_mod}+3"))

        # 工具路径（仅 Windows）
        if platform.system() != "Darwin":
            self._mmt_path.setText(cfg.tools.multimonitortool_path)
            self._cmm_path.setText(cfg.tools.controlmymonitor_path)
            self._set_combo_data(self._windows_backend, cfg.display.windows_backend)

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """设置 ComboBox 的值，按 data 匹配（data 是 ID 字符串）"""
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(value)

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        """按 data 值选中下拉项（无匹配时选中第一项：不切换）"""
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _run_refresh(self, coroutine):
        if self._submit is not None:
            return self._submit(coroutine)
        # Standalone dialog displays mock or local data when no app worker is provided.
        threading.Thread(target=asyncio.run, args=(coroutine,), daemon=True).start()
        return True

    def _refresh_displays(self) -> None:
        if self._display_loading:
            return
        plugins = self._plugin_provider() if self._plugin_provider else {}
        self._display_plugin = plugins.get("betterdisplay") or plugins.get("multimonitortool")
        if not self._display_plugin:
            self._populate_displays([])
            return
        self._display_loading = True

        async def read():
            try:
                displays = await self._display_plugin.list_displays()
            except Exception:
                displays = []
            self._displays_loaded.emit(displays)
        if not self._run_refresh(read()):
            self._display_loading = False

    def _populate_displays(self, displays: list) -> None:
        self._display_loading = False
        cfg = self._config_manager.config.display
        prefix = "mac" if platform.system() == "Darwin" else "windows"
        fields = ((self._primary_id, cfg.primary_id, getattr(cfg, f"{prefix}_primary_monitor_id")),
                  (self._secondary_id, cfg.secondary_id, getattr(cfg, f"{prefix}_secondary_monitor_id")),
                  (self._share_display, cfg.share_display_id, ""))
        if self._display_status:
            self._display_status.setText(self._display_failure_reason())
            self._display_status.setVisible(not displays)
        old = self._display_objects
        self._display_objects = {str(display.id): display for display in displays}
        for combo, initial, stable_id in fields:
            previous = combo.currentData()
            previous_display = old.get(previous)
            identity = (previous_display.device_id or previous_display.monitor_id) if previous_display else stable_id
            chosen = previous or str(initial)
            combo.clear()
            for item in displays:
                label = f"{item.name} · {item.id}" + (" · 已断开" if not item.is_enabled else "")
                combo.addItem(label, str(item.id))
            if identity:
                matches = [str(item.id) for item in displays if identity in (item.device_id, item.monitor_id)]
                if len(matches) == 1:
                    chosen = matches[0]
                else:
                    chosen = f"missing:{chosen}"
            if combo.findData(chosen) < 0:
                combo.addItem(f"需重新确认 · {initial}", chosen)
            combo.setCurrentIndex(combo.findData(chosen))

    def _display_failure_reason(self) -> str:
        """分析显示器列表读取失败的原因（插件状态/错误信息）"""
        plugin = getattr(self, "_display_plugin", None)
        if plugin is None:
            return "显示器插件不可用（未注册）"
        status = getattr(plugin, "status", None)
        status_name = getattr(status, "name", "")
        init_error = getattr(plugin, "_init_error", "") or ""
        if status_name == "ERROR":
            return f"显示器插件初始化失败：{init_error or '未知原因'}"
        last_error = getattr(plugin, "last_error", "") or ""
        if last_error:
            return f"显示器工具返回错误：{last_error}"
        return "未能读取显示器列表（插件未返回数据，请确认工具已安装并运行，或查看日志）"

    def _refresh_audio(self) -> None:
        if self._audio_loading or not self._plugin_provider:
            return
        plugin = self._plugin_provider().get("audio")
        if plugin is None:
            return
        self._audio_loading = True

        async def read():
            role = "mac" if platform.system() == "Darwin" else "windows"
            local, remote = [], []
            try:
                local = await plugin.list_endpoints() if hasattr(plugin, "list_endpoints") else await plugin.list_devices()
            except Exception:
                pass
            if self._remote_provider:
                try:
                    remote = (await self._remote_provider()).get("audio", [])
                except Exception:
                    pass
            self._audio_loaded.emit({"mac": local if role == "mac" else remote,
                                     "windows": local if role == "windows" else remote})
        if not self._run_refresh(read()):
            self._audio_loading = False

    def _populate_audio(self, devices: dict) -> None:
        cfg = self._config_manager.config.audio
        self._audio_loading = False
        for combo, role in ((self._mac_audio, "mac"), (self._win_audio, "windows")):
            target = combo.currentText() or getattr(cfg, f"{role}_output")
            device_key = "mac_device_uid" if role == "mac" else "windows_device_id"
            stable = combo.currentData() or getattr(cfg, device_key)
            combo.clear()
            for item in devices[role]:
                if isinstance(item, dict):
                    combo.addItem(item["name"], item["id"])
                else:
                    combo.addItem(item)
            index = combo.findData(stable) if stable else -1
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                self._set_combo_value(combo, target)

    @staticmethod
    def _audio_id(combo):
        return (combo.currentData() or "") if combo.currentText() == combo.itemText(combo.currentIndex()) else ""

    def _save(self) -> None:
        """保存配置"""
        is_mac = platform.system() == "Darwin"
        try:
            primary_id, secondary_id = (
                int(combo.currentData()) for combo in (self._primary_id, self._secondary_id))
            share_display_id = int(self._share_display.currentData()) if is_mac else secondary_id
        except (ValueError, TypeError):
            QMessageBox.warning(self, "显示器绑定", "请重新选择缺失的屏幕，再保存设置。")
            return
        if primary_id == secondary_id or share_display_id not in (primary_id, secondary_id):
            QMessageBox.warning(self, "显示器绑定", "主屏与副屏必须不同，共享时从两者中选择 Windows 使用的屏幕。")
            return
        # 校验快捷键：不能为空、不能互相冲突
        hotkeys = {
            "switch_mac": self._hk_mac.text().strip(),
            "switch_windows": self._hk_win.text().strip(),
            "switch_share": self._hk_share.text().strip(),
        }
        for name, hk in hotkeys.items():
            if not hk:
                QMessageBox.warning(self, "快捷键未设置", f"请为 {name} 录制快捷键。")
                return
        from app.hotkeys import parse_hotkey
        parsed = [parse_hotkey(value) for value in hotkeys.values()]
        if any(value is None for value in parsed) or len(set(parsed)) != 3:
            QMessageBox.warning(self, "快捷键冲突", "三个模式快捷键不能重复，请重新录制。")
            return

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
            "sharing": {
                "input_enabled": self._shared_keys.isChecked(),
                "clipboard_enabled": self._shared_clipboard.isChecked(),
                "controller": self._shared_host.currentData(),
                "edge": self._shared_edge.currentData(),
            },
            "audio": {
                "mac_output": self._mac_audio.currentText(),
                "windows_output": self._win_audio.currentText(),
                "mac_device_uid": self._audio_id(self._mac_audio),
                "windows_device_id": self._audio_id(self._win_audio),
            },
            "hotkeys": {
                "switch_mac": hotkeys["switch_mac"],
                "switch_windows": hotkeys["switch_windows"],
                "switch_share": hotkeys["switch_share"],
            },
        }

        prefix = "mac" if is_mac else "windows"
        selected = []
        for role, number in (("primary", primary_id), ("secondary", secondary_id)):
            monitor = self._display_objects.get(str(number))
            if monitor:
                identity = monitor.device_id or monitor.monitor_id
                updates["display"][f"{prefix}_{role}_monitor_id"] = identity
                if identity:
                    selected.append(identity.casefold())
        if len(selected) != len(set(selected)):
            QMessageBox.warning(self, "显示器绑定", "系统为两块显示器报告了相同的身份，请检查连接。")
            return
        if not is_mac:
            updates["display"]["windows_backend"] = self._windows_backend.currentData()
            updates["tools"] = {
                "multimonitortool_path": self._mmt_path.text(),
                "controlmymonitor_path": self._cmm_path.text(),
            }
        else:
            updates["betterdisplay"] = {"cli_path": self._betterdisplay_path.text().strip()}
        try:
            self._config_manager.update(updates)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法保存设置", str(exc))
            return
        self.accept()

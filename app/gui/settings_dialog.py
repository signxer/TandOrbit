"""TandOrbit 设置对话框

配置管理界面。
"""

from __future__ import annotations

import asyncio
import platform
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent
from typing import Any, Callable

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QLineEdit,
    QSpinBox,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager
from app.communication.discovery import DiscoveryService
from app.gui.device_editor import DeviceEditor
from app.gui.devices import devices_for
from app.gui.theme import ComboBox, Toggle, button, card, colors, icon, label, stylesheet

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
        self.setPlaceholderText("点击或按 Enter 录制")
        self._recording = False
        self._previous = ""

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self._start_recording()

    def _start_recording(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._previous = self.text()
        self.setText("")
        self.setPlaceholderText("请按下快捷键")

    def _stop_recording(self) -> None:
        self._recording = False
        self.setPlaceholderText("点击或按 Enter 录制")

    def focusOutEvent(self, event) -> None:
        if self._recording:
            self.setText(self._previous)
            self._stop_recording()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._start_recording()
                return
            return super().keyPressEvent(event)

        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self.setText(self._previous)
            self._stop_recording()
            return
        if event.key() in _MODIFIER_MAP:
            mods = self._format_mods(event.modifiers())
            self.setPlaceholderText(mods + " + …")
            return

        modifiers = self._format_mods(event.modifiers())
        key_name = self._key_to_name(event.key())
        self.setText(f"{modifiers}+{key_name}" if modifiers else key_name)
        self._stop_recording()

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
    _connection_checked = Signal(str, str, str)

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
        self._display_edited = False
        self._audio_loading = False
        self._peer_fingerprint = ""
        self._checking_connection = False
        self._config_manager = config_manager
        self._plugin_provider = plugin_provider
        self.setWindowTitle("TandOrbit 设置")
        self.setMinimumSize(640, 450)
        self.resize(762, 491)
        self.setStyleSheet(stylesheet())
        self._displays_loaded.connect(self._populate_displays)
        self._audio_loaded.connect(self._populate_audio)
        self._brightness_loaded.connect(self._show_brightness)
        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        nav_frame = card("navigation-bar")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(15, 4, 15, 4)
        self._navigation = QTabBar()
        self._navigation.setProperty("role", "navigation")
        self._navigation.setAccessibleName("设置分类")
        self._navigation.setIconSize(QSize(16, 16))
        self._navigation.setDrawBase(False)
        self._navigation.setExpanding(False)
        self._navigation.setElideMode(Qt.TextElideMode.ElideNone)
        self._navigation.setUsesScrollButtons(True)
        nav_layout.addWidget(self._navigation)
        layout.addWidget(nav_frame)

        self._pages = QStackedWidget()
        layout.addWidget(self._pages, 1)
        pages = [
            ("setup", "开始使用", "check",
             "让两台电脑连上同一个局域网。每台电脑都用视频线接到这两块显示器，并在显示器菜单开启自动选择输入源。",
             self._create_setup_tab),
            ("computers", "两台电脑", "link", "在同一个局域网内查找另一台电脑并配对。", self._create_connection_tab),
            ("displays", "显示器", "monitor",
             "在两台电脑上把同一块物理显示器设为主屏，例如都选桌面左边那块。", self._create_display_tab),
            ("sharing", "键鼠与剪贴板", "share",
             "在两台电脑各用一块屏幕时，可以用同一套键鼠，也可以同步复制的文字。", self._create_sharing_tab),
            ("audio", "音频", "audio", "切换后，有画面的电脑会尝试使用这里选定的声音输出。", self._create_audio_tab),
            ("hotkeys", "快捷键", "keyboard", "给三种用屏方式设定不同的全局快捷键。", self._create_hotkeys_tab),
        ]
        self._page_indexes = {}
        for key, name, glyph, description, build in pages:
            self._page_indexes[key] = self._navigation.addTab(icon(glyph, colors()["text"]), name)
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(21, 15, 21, 16)
            page_layout.setSpacing(13)
            titles = QVBoxLayout()
            titles.setSpacing(3)
            titles.addWidget(label(name, "page-title"))
            titles.addWidget(label(description, "muted", wrap=True))
            page_layout.addLayout(titles)
            page_layout.addWidget(build())
            page_layout.addStretch()
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroller.setWidget(page)
            self._pages.addWidget(scroller)
        footer = card("toolbar")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(16, 10, 18, 10)
        actions.setSpacing(7)
        backup = button("配置备份", "folder", kind="ghost")
        backup_menu = QMenu(backup)
        backup_menu.addAction("导入配置…", self._import_config)
        backup_menu.addAction("导出配置…", self._export_config)
        backup.setMenu(backup_menu)
        actions.addWidget(backup)
        actions.addStretch()
        cancel_btn = button("取消")
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(cancel_btn)
        self._save_button = button("保存设置")
        self._save_button.clicked.connect(self._save)
        actions.addWidget(self._save_button)
        layout.addWidget(footer)
        self._navigation.currentChanged.connect(self._change_page)

    def _change_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        self._emphasize(self._save_button, index != self._page_indexes["setup"])

    def _show_page(self, key: str) -> None:
        self._navigation.setCurrentIndex(self._page_indexes[key])

    @staticmethod
    def _emphasize(action, primary: bool) -> None:
        kind = "primary" if primary else "secondary"
        if action.property("kind") != kind:
            action.setProperty("kind", kind)
            action.style().unpolish(action)
            action.style().polish(action)

    @staticmethod
    def _details(layout: QVBoxLayout, title: str, content: QWidget) -> None:
        disclosure = button(title, "chevron", kind="ghost")
        disclosure.setCheckable(True)
        disclosure.toggled.connect(content.setVisible)
        content.hide()
        layout.addWidget(disclosure, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(content)

    @staticmethod
    def _setup_step(layout: QVBoxLayout, title: str, action) -> QLabel:
        row = card()
        content = QHBoxLayout(row)
        content.setContentsMargins(13, 9, 13, 9)
        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(label(title, "section"))
        description = label("", "muted", wrap=True)
        text.addWidget(description)
        content.addLayout(text, 1)
        content.addWidget(action)
        layout.addWidget(row)
        return description

    def _create_setup_tab(self) -> QWidget:
        widget, layout = self._page_body()
        pairing = button("去配对")
        pairing.clicked.connect(lambda: self._show_page("computers"))
        self._setup_pair_button = pairing
        self._setup_pair_status = self._setup_step(layout, "1. 配对两台电脑", pairing)

        displays = button("选显示器", "arrow")
        displays.clicked.connect(lambda: self._show_page("displays"))
        self._setup_display_status = self._setup_step(layout, "2. 绑定主屏和副屏", displays)

        self._check_button = button("开始检查", "check")
        self._check_button.clicked.connect(self._check_connection)
        self._setup_check_status = self._setup_step(layout, "3. 检查连接和共享条件", self._check_button)
        self._connection_result = label("", "muted", wrap=True)
        self._connection_result.hide()
        self._connection_checked.connect(self._show_connection_result)
        layout.addWidget(self._connection_result)
        return widget

    @staticmethod
    def _page_body() -> tuple[QWidget, QVBoxLayout]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        return widget, layout

    @staticmethod
    def _form(layout: QVBoxLayout, title: str) -> QFormLayout:
        section = card()
        frame_layout = QVBoxLayout(section)
        frame_layout.setContentsMargins(14, 13, 14, 14)
        frame_layout.setSpacing(11)
        frame_layout.addWidget(label(title, "section"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(11)
        frame_layout.addLayout(form)
        layout.addWidget(section)
        return form

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
            for combo in (self._primary_id, self._secondary_id, self._share_display):
                combo.setCurrentIndex(-1)
            self._load_values()  # 刷新界面
            QMessageBox.information(
                self,
                "导入配置",
                "配置已导入并重新加载。\n\n显示器兼容工具的修改在重启后生效。",
            )
        else:
            QMessageBox.warning(self, "导入配置", "导入失败，请检查文件格式。")

    def _create_connection_tab(self) -> QWidget:
        widget, layout = self._page_body()
        pair = self._form(layout, "附近电脑配对")
        self._remote_status = label("", "muted", wrap=True)
        self._remote_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pair.addRow(self._remote_status)
        pair.addRow(label(
            "两台电脑都打开搜索窗口。在其中一台选中另一台电脑，然后在两边核对并确认同一个六位数字。",
            "muted", wrap=True,
        ))
        nearby = button("查找附近电脑", "link", kind="primary")
        nearby.setEnabled(self._pairing is not None and self._discovery is not None and self._submit is not None)
        nearby.clicked.connect(self._pair_nearby)
        pair.addRow(nearby)
        self._next_displays = button("下一步：选显示器", "arrow", kind="ghost")
        self._next_displays.clicked.connect(lambda: self._show_page("displays"))
        pair.addRow(self._next_displays)

        manual, manual_layout = self._page_body()
        pair = self._form(manual_layout, "交换配对信息")
        pair.addRow(label(
            "把本机配对信息粘贴到另一台电脑，再把另一台的信息粘贴到这里。"
            "每次确认前，对照两台电脑上显示的设备指纹。", "muted", wrap=True,
        ))
        copy = button("复制本机配对信息", "copy")
        copy.clicked.connect(self._copy_offer)
        paste = button("粘贴另一台的配对信息…", "paste")
        paste.clicked.connect(self._pair)
        actions = QHBoxLayout()
        actions.setSpacing(7)
        for control in (copy, paste):
            actions.addWidget(control)
            control.setEnabled(self._pairing is not None)
        actions.addStretch()
        pair.addRow(actions)
        self._details(layout, "手动配对", manual)
        self._details(layout, "设备名称和图标", self._create_device_appearance())

        details, detail_layout = self._page_body()
        local = self._form(detail_layout, "网络与配对详情")
        self._offer_host = QLineEdit()
        if self._discovery:
            self._offer_host.setText(self._discovery._get_local_ip())
        local.addRow("手动配对时使用的本机 IP", self._offer_host)
        local.addRow(label(
            "如果自动填入的地址有误，可改成本机在当前局域网的 IP，再复制配对信息。",
            "muted", wrap=True,
        ))
        self._local_port = QSpinBox()
        self._local_port.setRange(1, 65535)
        local.addRow("连接端口", self._local_port)
        self._wol_nic = ComboBox()
        self._refresh_nics()
        if platform.system() == "Windows":
            local.addRow("用于远程唤醒的网卡", self._wol_nic)
            local.addRow(label(
                "要从 Mac 唤醒 Windows，请选择支持网络唤醒的网卡，"
                "再与 Mac 重新配对。", "muted", wrap=True,
            ))
        else:
            self._wol_nic.setParent(widget)
            self._wol_nic.hide()
        self._fingerprint = label("", "caption", wrap=True)
        self._fingerprint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        local.addRow(self._fingerprint)
        self._revoke_button = button("解除配对", kind="ghost")
        self._revoke_button.clicked.connect(self._revoke)
        local.addRow(self._revoke_button)
        self._details(layout, "网络与配对详情", details)
        return widget

    def _pair_nearby(self) -> None:
        from app.gui.nearby_pairing_dialog import NearbyPairingDialog

        cfg = self._config_manager.config
        local = cfg.mac if self._pairing.role == "mac" else cfg.windows
        nic = self._wol_nic.currentData() or ""
        address = DiscoveryService._get_local_mac(nic) if self._pairing.role == "windows" else ""
        dialog = NearbyPairingDialog(self._pairing, self._discovery, local.port, address, self._submit, self)
        dialog.start()
        try:
            if dialog.exec():
                self.refresh_remote_info()
                self.pairing_changed.emit()
        finally:
            dialog.stop()
            dialog.deleteLater()

    def _show_connection_result(self, fingerprint: str, summary: str, detail: str) -> None:
        if fingerprint != self._peer_fingerprint:
            return
        self._checking_connection = False
        self._check_button.setEnabled(True)
        self._setup_check_status.setText(summary)
        self._connection_result.setText(detail)
        self._connection_result.show()

    def _copy_offer(self):
        import json

        nic = self._wol_nic.currentData() or ""
        mac = DiscoveryService._get_local_mac(nic) if self._pairing.role == "windows" else ""
        try:
            offer = self._pairing.offer(self._offer_host.text(), self._local_port.value(), mac)
            QApplication.clipboard().setText(json.dumps(offer))
            QMessageBox.information(
                self, "已复制本机配对信息",
                f"在另一台电脑上粘贴刚复制的信息，并核对下面的设备指纹。\n\n{offer['fingerprint']}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "无法生成配对信息", str(exc))

    def _check_connection(self):
        fingerprint = self._peer_fingerprint
        if not fingerprint or self._remote_provider is None or self._checking_connection:
            return
        self._checking_connection = True
        self._check_button.setEnabled(False)
        self._connection_result.hide()
        self._setup_check_status.setText("正在连接另一台电脑并读取显示器信息…")
        local_display = getattr(self, "_display_plugin", None)

        async def check():
            try:
                result = await self._remote_provider()
                count = len(result["display"])
                summary = f"已连上另一台电脑。它识别到 {count} 台显示器。"
                detail = []
                if count < 2:
                    detail.append("在另一台电脑上检查视频线，并重新检测显示器。")
                if local_display is None:
                    detail.append("本机暂时无法读取显示器，请在「显示器」重新检测。")
                elif not getattr(local_display, "can_change_outputs", True):
                    detail.append("本机缺少独立控制一块屏幕的能力。请在 Mac 的「显示器」里检查 BetterDisplay。")
                if not result["single_display"]:
                    detail.append("另一台电脑暂时无法独立控制一块屏幕，请在那台电脑上检查显示器工具。")
                if not detail:
                    detail.append("在两台电脑上核对并保存主、副屏，随后回到主窗口试切一次。")
            except Exception:
                summary = "暂时连不上另一台电脑。"
                detail = ["确认两台电脑都打开了 TandOrbit 并完成配对，而且连接了同一个局域网。"]
            self._connection_checked.emit(fingerprint, summary, "\n".join(detail))
        if not self._run_refresh(check()):
            self._show_connection_result(fingerprint, "连接服务正在启动。", "等几秒后，再点一次「开始检查」。")

    def _pair(self):
        import json

        text, ok = QInputDialog.getMultiLineText(
            self, "粘贴另一台电脑的配对信息", "粘贴从另一台电脑上复制的完整配对信息。",
        )
        if not ok:
            return
        try:
            if len(text) > 16 * 1024:
                raise ValueError("配对信息太长。请回到另一台电脑重新复制。")
            offer = self._pairing.validate(json.loads(text))
            if QMessageBox.question(
                self, "核对设备指纹",
                f"{offer['fingerprint']}\n\n这串字符是否和另一台电脑上显示的指纹完全一致？",
            ) == QMessageBox.StandardButton.Yes:
                self._pairing.trust(offer)
                self.refresh_remote_info()
                self.pairing_changed.emit()
        except (json.JSONDecodeError, KeyError, TypeError):
            QMessageBox.warning(self, "配对信息不完整", "请从另一台电脑重新复制配对信息，然后粘贴到这里。")
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

    def refresh_remote_info(self, *, reload_appearance: bool = False) -> None:
        peer = self._pairing.peer if self._pairing else None
        local, remote = devices_for(
            self._config_manager.config.device_appearance,
            "mac" if platform.system() == "Darwin" else "windows",
            peer,
        )
        if reload_appearance or self._local_device.device is None:
            self._local_device.load(local)
        if remote.key is None:
            self._peer_device.device = None
        elif reload_appearance or self._peer_device.device is None or self._peer_device.device.key != remote.key:
            self._peer_device.load(remote)
        self._peer_device.setVisible(remote.key is not None)
        self._unpaired_device.setVisible(remote.key is None)
        for device in (local, remote):
            index = self._shared_host.findData(device.platform)
            self._shared_host.setItemText(index, device.name)
            self._shared_host.setItemIcon(index, icon(device.glyph))

        self._revoke_button.setEnabled(peer is not None)
        self._next_displays.setVisible(peer is not None)
        self._fingerprint.setVisible(peer is not None)
        if peer:
            self._remote_status.setText(f"本机已保存 {remote.name} 的配对信息。")
            octets = peer["fingerprint"].split(":")
            groups = [":".join(octets[start:start + 4]) for start in range(0, len(octets), 4)]
            self._fingerprint.setText(f"另一台电脑的地址　{peer['host']}:{peer['port']}\n设备指纹　{'  '.join(groups)}")
            self._fingerprint.setToolTip(peer["fingerprint"])
        elif self._discovery and self._discovery.peer:
            self._remote_status.setText("局域网里发现了另一台电脑，可以打开搜索窗口开始配对。")
        else:
            self._remote_status.setText("还没有配对。先在两台电脑上打开 TandOrbit。")

        fingerprint = remote.key or ""
        if fingerprint != self._peer_fingerprint:
            self._peer_fingerprint = fingerprint
            self._checking_connection = False
            self._connection_result.clear()
            self._connection_result.hide()
        self._check_button.setEnabled(bool(peer and self._remote_provider and not self._checking_connection))
        self._setup_pair_button.setText("查看配对" if peer else "去配对")
        self._emphasize(self._setup_pair_button, not peer)
        self._setup_pair_status.setText(
            f"本机已保存 {remote.name} 的配对信息。可在第三步检查双方能否连通。"
            if peer else "查找附近电脑，在两台屏幕上核对同一个六位数字。"
        )
        if not self._checking_connection and not self._connection_result.text():
            self._setup_check_status.setText(
                "检查另一台电脑能否连接，以及两端能否独立控制一块屏幕。"
                if peer else "完成配对后，就可以检查连接。"
            )

    def _create_device_appearance(self) -> QWidget:
        widget, layout = self._page_body()
        section = card()
        devices = QVBoxLayout(section)
        devices.setContentsMargins(0, 0, 0, 0)
        devices.setSpacing(0)
        self._local_device = DeviceEditor("本机")
        self._peer_device = DeviceEditor("已配对的电脑")
        devices.addWidget(self._local_device)
        line = card("separator")
        line.setFixedHeight(1)
        devices.addWidget(line)
        devices.addWidget(self._peer_device)

        self._unpaired_device = QWidget()
        empty = QVBoxLayout(self._unpaired_device)
        empty.setContentsMargins(15, 13, 15, 14)
        empty.setSpacing(7)
        empty.addWidget(label("配对后可为另一台电脑设置名称和图标。", "muted", wrap=True))
        devices.addWidget(self._unpaired_device)
        layout.addWidget(section)
        layout.addWidget(label("名称和图标只用于本机显示。留空名称会使用默认名称。", "muted", wrap=True))
        return widget

    def _create_display_tab(self) -> QWidget:
        widget, layout = self._page_body()
        form = self._form(layout, "选择这台电脑连接的两块屏幕")
        self._primary_id = ComboBox()
        self._secondary_id = ComboBox()
        self._share_display = ComboBox(widget)
        for combo in (self._primary_id, self._secondary_id, self._share_display):
            combo.setMinimumContentsLength(14)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.activated.connect(self._mark_display_edited)
        form.addRow("哪块是主屏", self._primary_id)
        form.addRow("哪块是副屏", self._secondary_id)
        if platform.system() == "Darwin":
            form.addRow("共享时 Windows 用哪块", self._share_display)
            form.addRow(label("共享时另一块屏幕由 Mac 使用。", "muted", wrap=True))
        else:
            self._share_display.hide()
            form.addRow(label("哪块屏幕在共享时分给 Windows，可在 Mac 上选择。", "muted", wrap=True))
        refresh = button("重新检测显示器", "refresh")
        refresh.clicked.connect(self._refresh_displays)
        self._display_status = label("", "warning", wrap=True)
        self._display_status.hide()
        form.addRow(self._display_status)
        check = button("下一步：检查连接", "arrow", kind="ghost")
        check.clicked.connect(lambda: self._show_page("setup"))
        actions = QHBoxLayout()
        actions.setSpacing(7)
        actions.addWidget(refresh)
        actions.addStretch(1)
        actions.addWidget(check)
        form.addRow(actions)

        advanced, advanced_layout = self._page_body()
        if platform.system() == "Windows":
            extra = self._form(advanced_layout, "主屏亮度")
            self._brightness = QSpinBox()
            self._brightness.setRange(0, 100)
            self._brightness.setSuffix("%")
            self._brightness_result = label("", "muted", wrap=True)
            read = button("读取")
            read.clicked.connect(lambda: self._change_brightness(None))
            apply = button("应用")
            apply.clicked.connect(lambda: self._change_brightness(self._brightness.value()))
            controls = QHBoxLayout()
            controls.addWidget(self._brightness, 1)
            controls.addWidget(read)
            controls.addWidget(apply)
            extra.addRow("亮度", controls)
            extra.addRow(self._brightness_result)
            advanced_layout.addWidget(self._create_windows_display_tools())
        else:
            extra = self._form(advanced_layout, "BetterDisplay")
            self._betterdisplay_path = QLineEdit()
            extra.addRow("命令行程序路径", self._betterdisplay_path)
            extra.addRow(label(
                "Mac 在共享模式中使用 BetterDisplay 单独断开或接回一块屏幕。修改路径后请重启 TandOrbit。",
                "muted", wrap=True,
            ))
            inspect = button("检查 BetterDisplay", "tools", kind="ghost")
            inspect.clicked.connect(self._show_requirements)
            extra.addRow(inspect)
        self._details(layout, "兼容工具与高级选项", advanced)
        return widget

    def _show_requirements(self):
        from app.gui.requirements_dialog import RequirementsDialog

        dialog = RequirementsDialog(self, config_manager=self._config_manager)
        dialog.exec()
        dialog.deleteLater()

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
        widget, layout = self._page_body()
        form = self._form(layout, "让鼠标跨到另一台电脑")
        self._shared_keys = Toggle("启用键鼠共享")
        self._shared_host = ComboBox()
        self._shared_host.addItem("Windows", "windows")
        self._shared_host.addItem("Mac", "mac")
        self._shared_host.setMinimumContentsLength(12)
        self._shared_host.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._shared_edge = ComboBox()
        for text, value, glyph in (
            ("右侧", "right", "arrow"), ("左侧", "left", "arrow-left"),
            ("上方", "top", "arrow-up"), ("下方", "bottom", "arrow-down"),
        ):
            self._shared_edge.addItem(icon(glyph), text, value)
        form.addRow(self._shared_keys)
        form.addRow("键鼠接在哪台电脑", self._shared_host)
        form.addRow("从哪条边跨到另一台", self._shared_edge)
        modifier = "Option" if platform.system() == "Darwin" else "Alt"
        form.addRow(label(
            "两台电脑都开启键鼠共享，并选择键鼠实际连接的那台。"
            f"把鼠标推到指定的屏幕边缘即可切过去，按 Ctrl + {modifier} + Esc 收回控制。",
            "muted", wrap=True,
        ))
        self._shared_keys.toggled.connect(self._shared_host.setEnabled)
        self._shared_keys.toggled.connect(self._shared_edge.setEnabled)

        text = self._form(layout, "剪贴板")
        self._shared_clipboard = Toggle("在两台电脑间同步复制的文字")
        text.addRow(self._shared_clipboard)
        text.addRow(label(
            "两台电脑都打开此项后，共享模式中刚复制的纯文本会发到另一台。每次最多 64 KiB。",
            "muted", wrap=True,
        ))
        return widget

    def _create_audio_tab(self) -> QWidget:
        widget, layout = self._page_body()
        form = self._form(layout, "切换后的声音输出")
        self._mac_audio = ComboBox()
        self._mac_audio.setEditable(True)
        self._win_audio = ComboBox()
        self._win_audio.setEditable(True)
        form.addRow("Mac", self._mac_audio)
        form.addRow("Windows", self._win_audio)
        refresh = button("重新检测声音设备", "refresh")
        refresh.clicked.connect(self._refresh_audio)
        system = button("打开本机声音设置", "external", kind="ghost")
        system.clicked.connect(self._open_audio_settings)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addWidget(system)
        row.addStretch()
        form.addRow(row)
        form.addRow(label("先连接耳机或扬声器，再检测设备。另一台电脑在线时会列出它的选项。", "muted", wrap=True))
        return widget

    def _open_audio_settings(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        scheme = "x-apple.systempreferences:com.apple.Sound-Settings.extension" if (
            platform.system() == "Darwin") else "ms-settings:sound"
        QDesktopServices.openUrl(QUrl(scheme))

    def _create_windows_display_tools(self) -> QWidget:
        widget, layout = self._page_body()
        form = self._form(layout, "Windows 显示器控制方式")
        self._windows_backend = ComboBox()
        self._windows_backend.addItem("Windows 系统接口（默认）", "native")
        self._windows_backend.addItem("使用 MultiMonitorTool", "multimonitortool")
        form.addRow("控制方式", self._windows_backend)
        form.addRow(label("系统接口无法控制显示器时可尝试 MultiMonitorTool。保存后请重启 TandOrbit。", "muted", wrap=True))

        paths = self._form(layout, "工具路径")
        self._mmt_path = QLineEdit()
        self._cmm_path = QLineEdit()
        for title, field in (("MultiMonitorTool", self._mmt_path), ("ControlMyMonitor", self._cmm_path)):
            browse = button("浏览", "folder")
            browse.clicked.connect(lambda _checked, target=field: self._browse_file(target))
            row = QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(browse)
            paths.addRow(title, row)
        inspect = button("检查兼容工具", "tools", kind="ghost")
        inspect.clicked.connect(self._show_requirements)
        paths.addRow(inspect)
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
        widget, layout = self._page_body()
        form = self._form(layout, "模式切换")
        self._hk_mac = HotkeyEdit()
        self._hk_win = HotkeyEdit()
        self._hk_share = HotkeyEdit()
        form.addRow("两块屏幕都给 Mac", self._hk_mac)
        form.addRow("两块屏幕都给 Windows", self._hk_win)
        form.addRow("每台电脑各用一块", self._hk_share)
        form.addRow(label("点击输入框，按下想用的组合键。也可用 Tab 选中输入框，再按 Enter 开始录制。", "muted", wrap=True))
        if platform.system() == "Darwin":
            layout.addWidget(label("全局快捷键需启用 macOS 的辅助功能权限。", "muted", wrap=True))
        return widget

    def _load_values(self) -> None:
        """加载当前配置值"""
        cfg = self._config_manager.config
        is_mac = platform.system() == "Darwin"
        if is_mac:
            self._local_port.setValue(cfg.mac.port)
            self._betterdisplay_path.setText(cfg.betterdisplay.cli_path)
            self._betterdisplay_path.setCursorPosition(0)
            self._betterdisplay_path.setToolTip(cfg.betterdisplay.cli_path)
        else:
            self._local_port.setValue(cfg.windows.port)

        # WoL 网卡
        if cfg.wol_nic:
            idx = self._wol_nic.findData(cfg.wol_nic)
            if idx >= 0:
                self._wol_nic.setCurrentIndex(idx)

        # 对端信息（自动发现）
        self.refresh_remote_info(reload_appearance=True)
        self._display_edited = False
        self._shared_keys.setChecked(cfg.sharing.input_enabled)
        self._shared_host.setEnabled(cfg.sharing.input_enabled)
        self._shared_edge.setEnabled(cfg.sharing.input_enabled)
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
        self._setup_display_status.setText("正在检测本机连接的显示器…")

        async def read():
            try:
                displays = await self._display_plugin.list_displays()
            except Exception:
                displays = []
            self._displays_loaded.emit(displays)
        if not self._run_refresh(read()):
            self._populate_displays([])

    def _mark_display_edited(self) -> None:
        self._display_edited = True

    def _populate_displays(self, displays: list) -> None:
        self._display_loading = False
        if len(displays) >= 2:
            setup_status = f"本机找到 {len(displays)} 台。请在两端核对主屏和副屏，并保存设置。"
        elif displays:
            setup_status = "本机只找到 1 台。接好第二块屏幕后，在「显示器」重新检测。"
        else:
            setup_status = "暂未找到本机的显示器。检查视频线后，在「显示器」重新检测。"
        self._setup_display_status.setText(setup_status)
        cfg = self._config_manager.config.display
        prefix = "mac" if platform.system() == "Darwin" else "windows"
        fields = ((self._primary_id, cfg.primary_id, getattr(cfg, f"{prefix}_primary_monitor_id")),
                  (self._secondary_id, cfg.secondary_id, getattr(cfg, f"{prefix}_secondary_monitor_id")),
                  (self._share_display, cfg.share_display_id, ""))
        if self._display_status:
            self._display_status.setText(
                "本机只识别到一块屏幕。请接好第二块，再重新检测。"
                if displays else self._display_failure_reason()
            )
            self._display_status.setVisible(len(displays) < 2)
        old = self._display_objects
        self._display_objects = {str(display.id): display for display in displays}
        for combo, initial, stable_id in fields:
            previous = combo.currentData()
            previous_display = old.get(previous)
            identity = (previous_display.device_id or previous_display.monitor_id) if previous_display else stable_id
            chosen = (previous or str(initial)).removeprefix("missing:")
            combo.clear()
            for item in displays:
                size = f" · {item.width} × {item.height}" if item.width and item.height else ""
                state = " · 暂未启用" if not item.is_enabled else ""
                combo.addItem(f"{item.name} · {item.id}{size}{state}", str(item.id))
            if identity:
                matches = [str(item.id) for item in displays if identity in (item.device_id, item.monitor_id)]
                if len(matches) == 1:
                    chosen = matches[0]
                else:
                    chosen = f"missing:{chosen}"
            if combo.findData(chosen) < 0:
                chosen = f"missing:{chosen.removeprefix('missing:')}"
                combo.addItem("请选择显示器", chosen)
            combo.setCurrentIndex(combo.findData(chosen))

    def _display_failure_reason(self) -> str:
        """分析显示器列表读取失败的原因（插件状态/错误信息）"""
        plugin = getattr(self, "_display_plugin", None)
        if plugin is None:
            return "尚未检测到显示器。请重新检测，或重启 TandOrbit 后再试。"
        status = getattr(plugin, "status", None)
        status_name = getattr(status, "name", "")
        init_error = getattr(plugin, "_init_error", "") or ""
        if status_name == "ERROR":
            message = "无法开始检测显示器。请查看下方的兼容工具设置。"
            return f"{message}\n{init_error}" if init_error else message
        last_error = getattr(plugin, "last_error", "") or ""
        if last_error:
            return f"显示器工具未能读取列表。请检查视频线或兼容工具设置。\n{last_error}"
        return "没有读到显示器。请检查两台屏幕的视频线和电源，然后重新检测。"

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

    def _display_updates(self) -> dict | None:
        """Keep unresolved bindings intact when saving unrelated settings."""
        if not self._display_objects and not self._display_edited:
            return {}
        is_mac = platform.system() == "Darwin"
        try:
            primary_id, secondary_id = (
                int(combo.currentData()) for combo in (self._primary_id, self._secondary_id))
            share_display_id = int(self._share_display.currentData()) if is_mac else secondary_id
        except (ValueError, TypeError):
            if not self._display_edited:
                return {}
            QMessageBox.warning(self, "显示器绑定", "请重新选择缺失的屏幕，再保存设置。")
            return None
        if primary_id == secondary_id or share_display_id not in (primary_id, secondary_id):
            if not self._display_edited:
                return {}
            QMessageBox.warning(self, "显示器绑定", "主屏与副屏必须不同，共享时从两者中选择 Windows 使用的屏幕。")
            return None
        updates = {"primary_id": primary_id, "secondary_id": secondary_id, "share_display_id": share_display_id}
        prefix = "mac" if is_mac else "windows"
        identities = []
        for role, number in (("primary", primary_id), ("secondary", secondary_id)):
            monitor = self._display_objects.get(str(number))
            if monitor:
                identity = monitor.device_id or monitor.monitor_id
                updates[f"{prefix}_{role}_monitor_id"] = identity
                if identity:
                    identities.append(identity.casefold())
        if len(identities) != len(set(identities)):
            if not self._display_edited:
                return {}
            QMessageBox.warning(self, "显示器绑定", "系统为两块显示器报告了相同的身份，请检查连接。")
            return None
        return updates

    def _save(self) -> None:
        """保存配置"""
        is_mac = platform.system() == "Darwin"
        display = self._display_updates()
        if display is None:
            self._show_page("displays")
            return
        # 校验快捷键：不能为空、不能互相冲突
        hotkeys = {
            "switch_mac": self._hk_mac.text().strip(),
            "switch_windows": self._hk_win.text().strip(),
            "switch_share": self._hk_share.text().strip(),
        }
        titles = {"switch_mac": "Mac 双屏", "switch_windows": "Windows 双屏", "switch_share": "每台电脑各用一块"}
        for name, hk in hotkeys.items():
            if not hk:
                self._show_page("hotkeys")
                QMessageBox.warning(self, "快捷键未设置", f"请为「{titles[name]}」录制快捷键。")
                return
        from app.hotkeys import parse_hotkey
        parsed = [parse_hotkey(value) for value in hotkeys.values()]
        if any(value is None for value in parsed) or len(set(parsed)) != 3:
            self._show_page("hotkeys")
            QMessageBox.warning(self, "检查快捷键", "请为三种用屏方式分别录制可用且互不重复的快捷键。")
            return

        # 本机端口
        if is_mac:
            local_config: dict[str, Any] = {"mac": {"port": self._local_port.value()}}
        else:
            local_config = {"windows": {"port": self._local_port.value()}}

        updates = {
            **local_config,
            "wol_nic": self._wol_nic.currentData() or "",
            "display": display,
            "device_appearance": {
                editor.device.key: editor.appearance().model_dump()
                for editor in (self._local_device, self._peer_device)
                if editor.device is not None and editor.device.key is not None
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

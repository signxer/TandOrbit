"""Discover an available computer and confirm the same number on both screens."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout

from app.communication.nearby_pairing import NearbyPairing
from app.gui.theme import button, label, stylesheet


class NearbyPairingDialog(QDialog):
    _event = Signal(str, object)

    def __init__(self, pairing, discovery, control_port, mac_address, submit, parent=None):
        super().__init__(parent)
        self._submit = submit
        self._discovery = discovery
        self._candidates = []
        self._stopping = False
        self._service = NearbyPairing(pairing, discovery, control_port, mac_address, self._notify)
        self._event.connect(self._show_event)
        self.setWindowTitle("附近电脑配对")
        self.setStyleSheet(stylesheet())
        self.setMinimumWidth(465)
        self.resize(485, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(21, 17, 21, 15)
        layout.setSpacing(11)
        layout.addWidget(label("附近电脑配对", "page-title"))
        self._description = label("正在打开配对窗口…", "muted", wrap=True)
        self._description.setMinimumHeight(42)
        layout.addWidget(self._description)
        self._devices = QListWidget()
        self._devices.setProperty("role", "pairing-list")
        self._devices.setAccessibleName("可配对的电脑")
        self._devices.setMinimumHeight(98)
        self._devices.currentItemChanged.connect(self._update_action)
        layout.addWidget(self._devices)
        self._number = label("", "pair-number")
        self._number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._number.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._number.hide()
        layout.addWidget(self._number)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._cancel = button("取消")
        self._cancel.setDefault(True)
        self._cancel.clicked.connect(self.reject)
        actions.addWidget(self._cancel)
        self._select = button("配对选中的电脑", kind="primary")
        self._select.setAutoDefault(False)
        self._select.setEnabled(False)
        self._select.clicked.connect(self._connect)
        actions.addWidget(self._select)
        self._matched = button("数字一致，确认配对", kind="primary")
        self._matched.setAutoDefault(False)
        self._matched.clicked.connect(self._confirm)
        self._matched.hide()
        actions.addWidget(self._matched)
        layout.addLayout(actions)

        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._refresh_candidates)

    def start(self) -> None:
        if not self._submit(self._service.start()):
            self._show_event("error", "连接服务正在启动，稍等几秒后重试。")

    def stop(self) -> None:
        self._stopping = True
        self._timer.stop()
        self._submit(self._service.close())

    def _notify(self, state: str, payload) -> None:
        if not self._stopping:
            self._event.emit(state, payload)

    def _update_action(self) -> None:
        self._select.setEnabled(self._devices.currentItem() is not None)

    def _refresh_candidates(self) -> None:
        candidates = sorted(self._discovery.pairing_candidates(),
                            key=lambda candidate: (candidate["name"], candidate["host"], candidate["pairing_port"]))
        if candidates == self._candidates:
            return
        selected = self._selected_device()
        self._candidates = candidates
        self._devices.clear()
        for candidate in candidates:
            platform = "Mac" if candidate["role"] == "mac" else "Windows"
            name = candidate["name"]
            title = f"{name} · {platform}" if name and name != platform else platform
            item = QListWidgetItem(f"{title} · {candidate['host']}")
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self._devices.addItem(item)
            if candidate == selected:
                self._devices.setCurrentItem(item)
        if len(candidates) == 1:
            self._devices.setCurrentRow(0)

    def _selected_device(self):
        current = self._devices.currentItem()
        return current.data(Qt.ItemDataRole.UserRole) if current is not None else None

    def _connect(self) -> None:
        candidate = self._selected_device()
        if candidate is None:
            return
        self._show_event("connecting", "")
        if not self._submit(self._service.connect(candidate["host"], candidate["pairing_port"])):
            self._show_event("error", "连接服务正在启动，稍等几秒后重试。")

    def _confirm(self) -> None:
        self._matched.setEnabled(False)
        self._description.setText("已在本机确认，等另一台电脑也确认。")
        self._submit(self._service.decide(True))

    def _show_event(self, state: str, payload) -> None:
        if state == "discovery":
            self._description.setText(
                "两台电脑都打开这个窗口。找到另一台后，在任意一台点击配对。"
            )
            self._refresh_candidates()
            self._timer.start()
            return

        self._timer.stop()
        self._select.hide()
        self._devices.hide()
        if state == "connecting":
            self._description.setText("正在连接另一台电脑…")
        elif state == "compare":
            self._description.setText(f"核对 {payload['name']} 屏幕上的六位数字。两台一致时，分别点击确认。")
            self._number.setText(payload["number"])
            self._number.show()
            self._cancel.setText("数字不同 / 取消")
            self._matched.show()
        elif state == "paired":
            self.accept()
        else:
            self._description.setText(payload)
            self._number.hide()
            self._matched.hide()
            self._cancel.setText("关闭")

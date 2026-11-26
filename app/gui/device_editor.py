"""Live editing of a device's presentation attributes."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.config import DeviceAppearance
from app.gui.devices import DeviceView, GLYPH_OPTIONS, PLATFORM_GLYPH
from app.gui.theme import ComboBox, card, colors, icon, label


class DeviceEditor(QWidget):
    def __init__(self, caption: str) -> None:
        super().__init__()
        self.device: DeviceView | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(13)

        identity_box = QWidget()
        identity_box.setFixedWidth(146)
        identity = QHBoxLayout(identity_box)
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(9)
        self._preview_icon = QLabel()
        self._preview_icon.setFixedSize(31, 31)
        identity.addWidget(self._preview_icon)
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(label(caption, "section"))
        self._platform = label("", "caption")
        title.addWidget(self._platform)
        identity.addLayout(title)
        identity.addStretch()
        layout.addWidget(identity_box)
        rule = card("separator")
        rule.setFixedSize(1, 30)
        layout.addWidget(rule, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.name = QLineEdit()
        self.name.setMaxLength(40)
        self.name.setMinimumWidth(98)
        self.glyph = ComboBox()
        for field, text in ((self.name, "显示名称"), (self.glyph, "设备图标")):
            column = QVBoxLayout()
            column.setSpacing(4)
            caption_label = label(text, "caption")
            caption_label.setBuddy(field)
            field.setAccessibleName(f"{caption}{text}")
            column.addWidget(caption_label)
            column.addWidget(field)
            layout.addLayout(column, 1)
        self.name.textChanged.connect(self._preview)
        self.glyph.currentIndexChanged.connect(self._preview)

    def load(self, device: DeviceView) -> None:
        self.device = device
        self._platform.setText("macOS" if device.platform == "mac" else "Windows")
        self.glyph.clear()
        for value, title in GLYPH_OPTIONS:
            mark = PLATFORM_GLYPH[device.platform] if value == "auto" else value
            self.glyph.addItem(icon(mark, colors()["text"]), title, value)
        default_name = replace(device, appearance=DeviceAppearance()).name
        self.name.setPlaceholderText(default_name)
        self.name.setText(device.appearance.name)
        self.glyph.setCurrentIndex(self.glyph.findData(device.appearance.glyph))
        self._preview()

    def appearance(self) -> DeviceAppearance:
        return DeviceAppearance(name=self.name.text().strip(), glyph=self.glyph.currentData() or "auto")

    def _preview(self) -> None:
        if self.device is not None:
            view = replace(self.device, appearance=self.appearance())
            self._preview_icon.setAccessibleName(view.name)
            self._preview_icon.setToolTip(view.name)
            self._preview_icon.setPixmap(self.glyph.itemIcon(self.glyph.currentIndex()).pixmap(31, 31))

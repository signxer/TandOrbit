"""Shared desktop palette, typography and controls."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFrame, QLabel, QPushButton, QSizePolicy

_LIGHT = {
    "page": "#EFF0F1", "surface": "#F8F8F8", "subtle": "#E6E7E9",
    "stroke": "#ADB1B5", "text": "#1A1B1E", "muted": "#52575D",
    "accent": "#A93421", "accent_hover": "#902D1D", "accent_soft": "#F1DFDB",
    "selected_stroke": "#AE4B3A", "inverse": "#FFFFFF",
    "green": "#267459", "amber": "#8C5318", "amber_soft": "#F4E9D9",
    "red": "#A23339", "red_soft": "#F5E0E1",
    "diagram": "#E8EAEC", "grid": "#DDE0E3", "grid_major": "#D1D5D8",
    "trace": "#747B82", "console": "#15171A", "console_text": "#EBECEE",
}
_DARK = {
    "page": "#121315", "surface": "#1B1D20", "subtle": "#17191C",
    "stroke": "#45494D", "text": "#EEEFF1", "muted": "#ADB1B7",
    "accent": "#FF765E", "accent_hover": "#FF927D", "accent_soft": "#342320",
    "selected_stroke": "#DA6C58", "inverse": "#1F1411",
    "green": "#7BD6AE", "amber": "#F8C285", "amber_soft": "#382D25",
    "red": "#FFA9AD", "red_soft": "#412A32",
    "diagram": "#101113", "grid": "#1D1F22", "grid_major": "#2B2E32",
    "trace": "#7C848C", "console": "#0D0E10", "console_text": "#E0E2E6",
}


def colors() -> dict[str, str]:
    app = QApplication.instance()
    if app is not None:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark or (
            scheme == Qt.ColorScheme.Unknown
            and app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        ):
            return _DARK
    return _LIGHT


# The glyphs share a 24px grid so menus, buttons, and navigation line up optically.
_GLYPHS = {
    "monitor": "M3 4h18v12H3zM8 21h8m-4-5v5",
    "desktop": "M3 4h18v12H3zM8 21h8m-4-5v5",
    "laptop": "M5 6h14v10H5zM3 16h18l1 2c0 1-1 2-2 2H4c-1 0-2-1-2-2z",
    "mini": "M5 8h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2zm11 5h1m1 0h1M7 13h4",
    "tower": "M7 3h10a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm3 4h4m-4 3h4m-2 6h.01",
    "windows": "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
    "share": "M2.5 6h8v9h-8zM13.5 9h8v9h-8zM6.5 15v4m11-1v4m-13-3h4m7 3h4",
    "link": "M10 14l4-4m-6 6-1 1a3.5 3.5 0 0 1-5-5l4-4a3.5 3.5 0 0 1 5 0m5 0 1-1a3.5 3.5 0 0 1 5 5l-4 4a3.5 3.5 0 0 1-5 0",
    "audio": "M4 9h4l5-4v14l-5-4H4zm12 0a4 4 0 0 1 0 6m2-9a8 8 0 0 1 0 12",
    "keyboard": "M3 6h18v12H3zm4 4h1m3 0h1m3 0h1m-9 4h1m3 0h5",
    "tools": "M14 7a4 4 0 0 0 5 5l-8 8a2 2 0 0 1-3-3l8-8m2-6-3 3 3 3 3-3",
    "settings": "M4 6h16M4 12h16M4 18h16M8 4v4m8 2v4m-6 2v4",
    "history": "M4 11a8 8 0 1 1 2 6M4 5v6h6m2-3v4l3 2",
    "logs": "M6 3h8l4 4v14H6zM14 3v4h4M9 11h6m-6 4h6m-6 3h4",
    "sleep": "M19.5 15.6A8 8 0 0 1 8.4 4.5a8 8 0 1 0 11.1 11.1z",
    "restore": "M3 4h18v12H3zM8 21h8m-4-5v5m-3-10 3-3 3 3m-3-3v5",
    "refresh": "M19 8a8 8 0 0 0-14-1m14-3v4h-4M5 16a8 8 0 0 0 14 1m-14 3v-4h4",
    "folder": "M3 6h7l2 2h9v11H3z",
    "export": "M3 15v5h18v-5M12 15V4m-4 4 4-4 4 4",
    "import": "M3 15v5h18v-5M12 4v10m-4-4 4 4 4-4",
    "check": "M5 12l4 4L19 6",
    "alert": "M12 3l10 18H2zM12 9v4m0 4h.01",
    "info": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zm0-10v5m0-10h.01",
    "chevron": "m6 9 6 6 6-6",
    "copy": "M8 8h12v12H8zM16 8V4H4v12h4",
    "paste": "M8 5H5v15h14V5h-3M9 3h6v4H9zm0 9h6m-6 4h6",
    "trash": "M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15m-8 4v7m4-7v7",
    "arrow": "M4 12h15m-5-5 5 5-5 5",
    "arrow-left": "M20 12H5m5-5-5 5 5 5",
    "arrow-up": "M12 20V5m-5 5 5-5 5 5",
    "arrow-down": "M12 4v15m-5-5 5 5 5-5",
    "logout": "M10 4H4v16h6m3-13 5 5-5 5m-4-5h9",
    "external": "M13 4h7v7m0-7-9 9m-1-6H4v13h13v-6",
}


def icon(name: str, color: str | None = None) -> QIcon:
    ink = color or colors()["accent"]
    source = QByteArray(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{ink}" stroke-width="1.65" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="{_GLYPHS[name]}"/></svg>'
        ).encode()
    )
    renderer = QSvgRenderer(source)
    glyph = QIcon()
    for size in (16, 20, 24):
        for scale in (1, 2):
            pixmap = QPixmap(size * scale, size * scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(scale)
            glyph.addPixmap(pixmap)
    return glyph


def label(text: str = "", role: str = "", *, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


class ElidedLabel(QLabel):
    """Keep a long device name from setting the width of its container."""

    def __init__(self, role: str) -> None:
        super().__init__()
        self._full_text = ""
        self.setProperty("role", role)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_name(self, text: str) -> None:
        self._full_text = text
        self.setAccessibleName(text)
        self._fit_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_text()

    def _fit_text(self) -> None:
        shown = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        self.setText(shown)
        self.setToolTip(self._full_text if shown != self._full_text else "")


def button(text: str, glyph: str | None = None, *, kind: str = "secondary",
           icon_only: bool = False) -> QPushButton:
    widget = QPushButton("" if icon_only else text)
    widget.setProperty("kind", "icon" if icon_only else kind)
    widget.setAccessibleName(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if glyph:
        ink = colors()["inverse" if kind == "primary" else "text"]
        widget.setIcon(icon(glyph, ink))
        widget.setIconSize(QSize(17, 17))
    if icon_only:
        widget.setToolTip(text)
        widget.setFixedSize(32, 32)
    return widget


def card(role: str = "card") -> QFrame:
    frame = QFrame()
    frame.setProperty("role", role)
    return frame


class ComboBox(QComboBox):
    """Keep the disclosure mark visible on both Qt platform styles."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._caret = icon("chevron", colors()["muted"])

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        self._caret.paint(painter, self.width() - 27, (self.height() - 16) // 2, 16, 16)
        painter.end()


class Toggle(QCheckBox):
    """A themed indicator with the native checkbox's focus and keyboard behavior."""

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        return QSize(43 + metrics.horizontalAdvance(self.text()), max(26, metrics.height() + 4))

    def hitButton(self, position) -> bool:
        return self.rect().contains(position)

    def paintEvent(self, event) -> None:
        c = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - 19) // 2
        if self.hasFocus():
            painter.setPen(QPen(QColor(c["selected_stroke"]), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(0, top - 2, 36, 23, 11, 11)
        painter.setPen(QPen(QColor(c["accent"] if self.isChecked() else c["stroke"])))
        painter.setBrush(QColor(c["accent"] if self.isChecked() else c["subtle"]))
        painter.drawRoundedRect(2, top, 32, 19, 9, 9)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["inverse"] if self.isChecked() else c["muted"]))
        painter.drawEllipse(19 if self.isChecked() else 6, top + 4, 11, 11)
        painter.setPen(QColor(c["text"] if self.isEnabled() else c["muted"]))
        painter.drawText(43, 0, self.width() - 43, self.height(),
                         Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.end()


def stylesheet() -> str:
    c = colors()
    return f"""
        QMainWindow, QDialog, QWidget[role="window"] {{
            background: {c['page']}; color: {c['text']};
        }}
        QLabel {{ color: {c['text']}; background: transparent; font-size: 13px; }}
        QLabel:disabled {{ color: {c['muted']}; }}
        QLabel[role="title"] {{ font-size: 21px; font-weight: 700; }}
        QLabel[role="page-title"] {{ font-size: 24px; font-weight: 700; }}
        QLabel[role="pair-number"] {{ color: {c['accent']}; font-size: 42px; font-weight: 700; }}
        QLabel[role="section"] {{ font-size: 14px; font-weight: 650; }}
        QLabel[role="muted"] {{ color: {c['muted']}; }}
        QLabel[role="caption"] {{ color: {c['muted']}; font-size: 11px; }}
        QLabel[role="secondary-title"] {{ color: {c['muted']}; font-size: 12px; font-weight: 600; }}
        QLabel[role="error"] {{ color: {c['red']}; }}
        QLabel[role="success"] {{ color: {c['green']}; }}
        QLabel[role="warning"] {{ color: {c['amber']}; }}
        QFrame[role="card"], QFrame[role="toolbar"] {{
            background: {c['surface']}; border: 1px solid {c['stroke']}; border-radius: 3px;
        }}
        QFrame[role="toolbar"] {{ border-radius: 0; border-width: 1px 0 0; }}
        QFrame[role="navigation-bar"] {{
            background: {c['subtle']}; border-bottom: 1px solid {c['stroke']};
        }}
        QFrame[role="separator"] {{ background: {c['stroke']}; border: none; }}
        QFrame[tone="warning"] {{ background: {c['amber_soft']}; }}
        QFrame[tone="error"] {{ background: {c['red_soft']}; }}
        QFrame[tone="progress"] {{ background: {c['accent_soft']}; }}
        QPushButton {{
            color: {c['text']}; background: {c['surface']}; border: 1px solid {c['stroke']};
            border-radius: 3px; padding: 0 11px; min-height: 30px; font-size: 13px;
        }}
        QPushButton:hover {{ background: {c['subtle']}; }}
        QPushButton:pressed {{ background: {c['accent_soft']}; }}
        QPushButton:focus {{ border: 1px solid {c['selected_stroke']}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['page']}; }}
        QPushButton[kind="ghost"], QPushButton[kind="icon"] {{ background: transparent; }}
        QPushButton[kind="ghost"] {{ border-color: transparent; }}
        QPushButton[kind="ghost"]:hover, QPushButton[kind="icon"]:hover {{ background: {c['subtle']}; }}
        QPushButton[kind="ghost"]:pressed, QPushButton[kind="icon"]:pressed {{ background: {c['accent_soft']}; }}
        QPushButton[kind="ghost"]:focus, QPushButton[kind="icon"]:focus {{
            border-color: {c['selected_stroke']};
        }}
        QPushButton[kind="icon"] {{ padding: 0; border-color: transparent; min-height: 0; }}
        QPushButton[kind="primary"] {{
            color: {c['inverse']}; background: {c['accent']}; border-color: {c['accent']}; font-weight: 600;
        }}
        QPushButton[kind="primary"]:hover {{ background: {c['accent_hover']}; }}
        QPushButton[kind="primary"]:pressed {{ background: {c['accent_hover']}; }}
        QPushButton[kind="primary"]:focus {{ border: 2px solid {c['text']}; }}
        QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
            color: {c['text']}; background: {c['surface']}; border: 1px solid {c['stroke']};
            border-radius: 3px; min-height: 31px; font-size: 13px; padding: 0 9px;
            selection-background-color: {c['accent_soft']}; selection-color: {c['text']};
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
            border: 1px solid {c['selected_stroke']};
        }}
        QComboBox {{ padding-right: 32px; }}
        QComboBox::drop-down {{ width: 28px; border: 0; background: transparent; }}
        QComboBox::down-arrow {{ image: none; }}
        QComboBox QLineEdit {{ border: 0; padding: 0; min-height: 0; background: transparent; }}
        QComboBox QAbstractItemView {{
            color: {c['text']}; background: {c['surface']}; border: 1px solid {c['stroke']};
            selection-background-color: {c['accent_soft']}; selection-color: {c['accent']};
            padding: 4px;
        }}
        QCheckBox {{ color: {c['text']}; font-size: 13px; spacing: 8px; }}
        QCheckBox:disabled {{ color: {c['muted']}; }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: {c['page']}; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 3px; }}
        QScrollBar::handle {{ background: {c['stroke']}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
        QScrollBar::handle:hover {{ background: {c['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QTabBar[role="navigation"]::tab {{
            background: transparent; color: {c['text']}; font-size: 13px;
            border-right: 1px solid {c['stroke']}; border-bottom: 2px solid transparent;
            min-height: 34px; padding: 0 9px;
        }}
        QTabBar[role="navigation"]::tab:hover {{ background: {c['surface']}; }}
        QTabBar[role="navigation"]::tab:selected {{
            background: {c['accent_soft']}; color: {c['accent']}; border-bottom-color: {c['accent']};
        }}
        QTabBar[role="navigation"]::tab:selected:focus {{
            border-top: 1px solid {c['selected_stroke']}; min-height: 33px;
        }}
        QListWidget[role="pairing-list"] {{
            background: {c['surface']}; color: {c['text']}; border: 1px solid {c['stroke']};
        }}
        QListWidget[role="pairing-list"]::item {{ padding: 7px 9px; }}
        QListWidget[role="pairing-list"]::item:selected {{
            background: {c['accent_soft']}; color: {c['text']}; border-left: 2px solid {c['accent']};
        }}
        QToolTip {{
            background: {c['surface']}; color: {c['text']}; border: 1px solid {c['stroke']};
            padding: 4px 7px;
        }}
    """

"""Live display ownership as an engineering diagram, scaled by Qt."""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QWidget

from app.gui.devices import DeviceView
from app.gui.theme import colors, icon


def _linework(painter: QPainter, *points: tuple[float, float]) -> None:
    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))


class ScreenTile(QWidget):
    """Use identical monitor geometry for both roles."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self.owner: DeviceView | None = None
        self.setFixedHeight(224)
        self._glyph = icon("monitor", colors()["muted"])

    def set_owner(self, owner: DeviceView | None) -> None:
        if owner != self.owner:
            self.owner = owner
            self._glyph = icon(owner.glyph if owner else "monitor", colors()["text" if owner else "muted"])
        name = owner.name if owner else "待确认"
        self.setAccessibleName(f"{self.title} · {name}")
        self.setToolTip(self.accessibleName())
        self.update()

    def screen_rect(self) -> QRectF:
        width = self.width() - 28
        height = width * 9 / 16
        return QRectF(14, 122 - height / 2, width, height)

    def signal_port(self) -> QPointF:
        screen = self.screen_rect()
        return QPointF(screen.center().x(), screen.bottom() + 29)

    def paintEvent(self, event) -> None:
        c = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ink = c["text"] if self.owner else c["muted"]
        self._draw_monitor(painter, c, ink)
        screen = self.screen_rect()
        anchor = screen.left() + 29
        top = screen.top() - 4
        painter.setPen(QPen(QColor(c["trace"]), 0.8))
        _linework(painter, (31, 53), (anchor - 7, 53), (anchor, 60), (anchor, top))
        painter.fillRect(QRectF(anchor - 1.5, top - 1.5, 3, 3), QColor(ink))

        painter.setPen(QPen(QColor(ink), 1))
        _linework(painter, (18, 10), (13, 10), (13, 53), (31, 53))
        font = QFont(self.font())
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        name = self.owner.name if self.owner else "待确认"
        space = self.width() - 58
        name = QFontMetrics(font).elidedText(name, Qt.TextElideMode.ElideRight, space)
        mark_x = min(self.width() - 32, max(102, 32 + QFontMetrics(font).horizontalAdvance(name)))
        self._glyph.paint(painter, mark_x, 14, 24, 24)
        painter.drawText(QRectF(22, 10, space, 19), Qt.AlignmentFlag.AlignVCenter, name)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        painter.setPen(QColor(c["muted"]))
        painter.setFont(font)
        painter.drawText(QRectF(22, 31, space, 16), Qt.AlignmentFlag.AlignVCenter, self.title)
        painter.end()

    def _draw_monitor(self, painter: QPainter, c: dict[str, str], ink: str) -> None:
        screen = self.screen_rect()
        bezel = screen.adjusted(-5, -4, 5, 7)
        l, t, r, b = bezel.left(), bezel.top(), bezel.right(), bezel.bottom()
        painter.setPen(QPen(QColor(ink), 1))
        _linework(painter, (l + 4, t), (r - 4, t), (r, t + 4), (r, b - 4),
                  (r - 4, b), (l + 4, b), (l, b - 4), (l, t + 4), (l + 4, t))
        glass = QColor(c["surface"])
        glass.setAlpha(102)
        painter.fillRect(screen, glass)
        painter.setPen(QPen(QColor(c["trace"]), 0.8))
        painter.drawRect(screen)

        center = screen.center()
        for x, direction in ((screen.left() + 7, 1), (screen.right() - 7, -1)):
            for y, vertical in ((screen.top() + 7, 1), (screen.bottom() - 7, -1)):
                _linework(painter, (x, y + 7 * vertical), (x, y), (x + 9 * direction, y))
        painter.drawLine(QLineF(center.x() - 5, center.y(), center.x() + 5, center.y()))
        painter.drawLine(QLineF(center.x(), center.y() - 5, center.x(), center.y() + 5))
        if self.owner is not None:
            painter.fillRect(QRectF(r - 15, b - 3.5, 6, 1.5), QColor(c["accent"]))

        port = self.signal_port()
        x, y = port.x(), port.y()
        painter.setPen(QPen(QColor(ink), 0.9))
        _linework(painter, (x - 7, b), (x - 7, y - 7), (x + 7, y - 7), (x + 7, b))
        _linework(painter, (x - 29, y), (x - 29, y - 3), (x - 24, y - 7),
                  (x + 24, y - 7), (x + 29, y - 3), (x + 29, y), (x - 29, y))


class DisplayDiagram(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(289)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 20)
        layout.setSpacing(0)
        self.screens = (ScreenTile("主屏"), ScreenTile("副屏"))
        layout.addStretch(1)
        layout.addWidget(self.screens[0])
        layout.addSpacing(43)
        layout.addWidget(self.screens[1])
        layout.addStretch(1)
        self.update_owners(None, None)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = min(231, max(117, (self.width() - 106) // 2))
        for tile in self.screens:
            tile.setFixedWidth(width)

    def update_owners(self, primary: DeviceView | None, secondary: DeviceView | None) -> None:
        for screen, owner in zip(self.screens, (primary, secondary)):
            screen.set_owner(owner)
        self.update()

    def paintEvent(self, event) -> None:
        c = colors()
        painter = QPainter(self)
        border = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.fillRect(border, QColor(c["diagram"]))
        painter.setPen(QPen(QColor(c["stroke"]), 1))
        painter.drawRect(border)
        self._draw_grid(painter, c)
        self._draw_route(painter, c)
        painter.end()

    def _draw_grid(self, painter: QPainter, c: dict[str, str]) -> None:
        width, height = self.width(), self.height()
        for spacing, ink in ((8, "grid"), (40, "grid_major")):
            painter.setPen(QPen(QColor(c[ink]), 1))
            for x in range(12, width - 4, spacing):
                painter.drawLine(x, 10, x, height - 3)
            for y in range(10, height - 3, spacing):
                painter.drawLine(12, y, width - 3, y)
        painter.setPen(QPen(QColor(c["trace"]), 1))
        painter.drawLine(12, 10, width - 6, 10)
        painter.drawLine(12, 10, 12, height - 6)
        for x in range(12, width - 6, 8):
            painter.drawLine(x, 10, x, 4 if (x - 12) % 40 == 0 else 7)
        for y in range(10, height - 6, 8):
            painter.drawLine(12, y, 6 if (y - 10) % 40 == 0 else 9, y)

    def _draw_route(self, painter: QPainter, c: dict[str, str]) -> None:
        left, right = self.screens
        if left.owner is None or right.owner is None:
            return
        left_port = QPointF(left.pos()) + left.signal_port()
        right_port = QPointF(right.pos()) + right.signal_port()
        x1, y1 = left_port.x(), left_port.y()
        x2 = right_port.x()
        y2 = left.geometry().bottom() + 11
        center = (x1 + x2) / 2
        shared = left.owner.key != right.owner.key
        ink = QColor(c["accent" if shared else "trace"])
        painter.setPen(QPen(ink, 1.25))
        _linework(painter, (x1, y1), (x1, y2), (x2, y2), (x2, y1))
        painter.setBrush(QColor(c["diagram"]))
        for x in (x1, x2):
            painter.drawRect(QRectF(x - 3, y2 - 3, 6, 6))
        painter.fillRect(QRectF(center - 3, y2 - 3, 6, 6), ink)

"""Switch history and details for the selected operation."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from app.enums import Mode
from app.gui.main_window import PHASE_LABELS, mode_name
from app.gui.theme import button, card, colors, label, stylesheet

_HEADERS = ("时间", "模式切换", "结果", "耗时", "详情")


class SwitchHistoryDialog(QDialog):
    def __init__(self, history_provider: Callable, rate_provider: Callable, parent=None) -> None:
        super().__init__(parent)
        self._history_provider = history_provider
        self._rate_provider = rate_provider
        self._records: list[dict] = []
        self.setWindowTitle("切换记录")
        self.setMinimumSize(620, 380)
        self.resize(806, 505)
        self.setStyleSheet(stylesheet() + self._table_styles())
        self._setup_ui()
        self._refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    @staticmethod
    def _table_styles() -> str:
        c = colors()
        return f"""
            QTableWidget {{
                background: {c['surface']}; alternate-background-color: {c['page']};
                color: {c['text']}; border: 1px solid {c['stroke']}; border-radius: 10px;
                gridline-color: {c['stroke']}; selection-background-color: {c['accent_soft']};
                selection-color: {c['text']}; outline: 0;
            }}
            QTableWidget::item {{ padding: 5px 8px; }}
            QHeaderView::section {{
                background: {c['subtle']}; color: {c['muted']}; border: none;
                border-bottom: 1px solid {c['stroke']}; padding: 9px 8px; font-weight: 600;
            }}
        """

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(21, 18, 21, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(label("切换记录", "title"))
        top.addStretch()
        refresh = button("刷新", "refresh")
        refresh.clicked.connect(self._refresh)
        top.addWidget(refresh)
        layout.addLayout(top)

        summary = card()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(13, 11, 13, 11)
        self._summary = label("暂无切换记录")
        self._rate = label("", "section")
        summary_layout.addWidget(self._summary, 1)
        summary_layout.addWidget(self._rate)
        layout.addWidget(summary)

        self._results = QStackedWidget()
        empty = card()
        empty_layout = QVBoxLayout(empty)
        self._empty_label = label("暂无切换记录", "muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._empty_label)
        self._results.addWidget(empty)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        columns = self._table.horizontalHeader()
        columns.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        columns.setSectionResizeMode(len(_HEADERS) - 1, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._show_detail)
        self._results.addWidget(self._table)
        layout.addWidget(self._results, 1)

        self._detail = card()
        detail_layout = QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(13, 10, 13, 11)
        detail_layout.setSpacing(5)
        self._detail_title = label("", "section")
        self._detail_text = label("", "muted", wrap=True)
        self._detail_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self._detail_title)
        detail_layout.addWidget(self._detail_text)
        self._detail.hide()
        layout.addWidget(self._detail)

    @staticmethod
    def _result(record: dict) -> tuple[str, str]:
        phase = record.get("phase")
        if record.get("success"):
            return "成功", "green"
        if phase == "restored":
            return "已恢复", "amber"
        if phase in ("recovering", "decision_commit"):
            return "待确认", "amber"
        return "失败", "red"

    @staticmethod
    def _route(record: dict) -> str:
        names = [mode_name(Mode.__members__.get(str(record.get(key)), Mode.UNKNOWN)) for key in ("from", "to")]
        return " → ".join(names)

    def _show_detail(self) -> None:
        row = self._table.currentRow()
        valid = 0 <= row < len(self._records) and bool(self._table.selectedItems())
        self._detail.setVisible(valid)
        if not valid:
            return
        record = self._records[row]
        result, _ = self._result(record)
        parts = []
        if phase := record.get("phase"):
            parts.append(f"阶段　{PHASE_LABELS.get(phase, phase)}")
        if key := record.get("operation_id"):
            parts.append(f"操作 ID　{key}")
        if error := record.get("error"):
            parts.append(str(error))
        self._detail_text.setVisible(bool(parts))
        self._detail_title.setText(f"{self._route(record)}　·　{result}")
        self._detail_text.setText("\n".join(parts))

    def _refresh(self) -> None:
        ok, total, rate = self._rate_provider(20)
        self._summary.setText(f"最近 {total} 次切换 · {ok} 次成功" if total else "切换概况")
        self._rate.setText(f"成功率 {rate:.0%}" if total else "")
        history = self._history_provider()
        if history == self._records:
            return
        row = self._table.currentRow()
        selected = self._records[row].get("operation_id") if 0 <= row < len(self._records) else None
        self._records = history
        self._table.setRowCount(len(history))
        self._results.setCurrentIndex(int(bool(history)))
        for row, record in enumerate(history):
            status, tone = self._result(record)
            stage = record.get("phase", "")
            values = [
                record.get("time", ""), self._route(record), status,
                f"{record['duration_ms']} ms" if "duration_ms" in record else "—",
                record.get("error") or PHASE_LABELS.get(stage, stage),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 2:
                    item.setForeground(QColor(colors()[tone]))
                self._table.setItem(row, column, item)
            if selected and record.get("operation_id") == selected:
                self._table.selectRow(row)
        self._show_detail()

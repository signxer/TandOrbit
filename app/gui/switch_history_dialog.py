"""切换记录看板

显示最近切换历史与成功率，帮助定位"切换成功率不高"的问题。
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.gui.main_window import _COLORS, _FONT

_HEADERS = ["时间", "从", "到", "结果", "耗时(ms)", "失败原因"]


class SwitchHistoryDialog(QDialog):
    """切换历史看板（打开后每 2 秒自动刷新）"""

    def __init__(
        self,
        history_provider: Callable[[], list[dict[str, Any]]],
        rate_provider: Callable[[int], tuple[int, int, float]],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("切换记录")
        self.resize(700, 420)
        self._history_provider = history_provider
        self._rate_provider = rate_provider
        self.setStyleSheet(self._build_stylesheet())
        self._setup_ui()
        self._refresh()

        # 打开期间自动刷新（切换事件来自工作线程）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)

    @staticmethod
    def _build_stylesheet() -> str:
        c = _COLORS
        return f"""
            * {{
                font-family: "{_FONT}";
                font-size: 13px;
            }}
            QDialog {{
                background: {c['window_bg']};
                color: {c['text']};
            }}
            QLabel {{ color: {c['text']}; }}
            QTableWidget {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                gridline-color: {c['border']};
            }}
            QHeaderView::section {{
                background: {c['hover']};
                color: {c['text']};
                border: none;
                border-bottom: 1px solid {c['border']};
                padding: 4px 8px;
            }}
            QPushButton {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 18px;
            }}
            QPushButton:hover {{ background: {c['hover']}; }}
        """

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._summary = QLabel("—")
        self._summary.setStyleSheet(f"color: {_COLORS['text']}; font-weight: bold;")
        layout.addWidget(self._summary)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _refresh(self) -> None:
        ok, total, rate = self._rate_provider(20)
        if total == 0:
            self._summary.setText("暂无切换记录")
        else:
            pct = rate * 100
            color = "#4CAF50" if rate >= 0.9 else ("#ffa500" if rate >= 0.7 else "#ff4444")
            self._summary.setText(
                f"最近 {total} 次切换 · 成功 {ok} 次 · 成功率 "
                f'<span style="color:{color}; font-size:16px;">{pct:.0f}%</span>'
            )

        history = self._history_provider()
        self._table.setRowCount(len(history))
        for row, rec in enumerate(history):
            values = [
                str(rec.get("time", "")),
                str(rec.get("from", "")),
                str(rec.get("to", "")),
                "✓ 成功" if rec.get("success") else "✗ 失败",
                str(rec.get("duration_ms", "")),
                str(rec.get("error", "")),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 3:
                    item.setForeground(Qt.GlobalColor.darkGreen if rec.get("success") else Qt.GlobalColor.red)
                self._table.setItem(row, col, item)

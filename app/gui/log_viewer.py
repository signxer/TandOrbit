"""TandOrbit 日志查看器

实时显示应用日志。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogViewer(QWidget):
    """日志查看器"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._log_buffer: list[str] = []
        self._max_lines = 1000

    def _setup_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear)
        toolbar.addStretch()
        toolbar.addWidget(clear_btn)
        layout.addLayout(toolbar)

        # 日志文本区域
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("SF Mono", 11))
        self._text_edit.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        layout.addWidget(self._text_edit)

    def append_log(self, message: str, level: str = "INFO") -> None:
        """添加日志"""
        color_map = {
            "DEBUG": "#888888",
            "INFO": "#d4d4d4",
            "WARNING": "#ffa500",
            "ERROR": "#ff4444",
            "CRITICAL": "#ff0000",
        }
        color = color_map.get(level, "#d4d4d4")
        html = f'<span style="color:{color};">{message}</span>'
        self._text_edit.append(html)

        # 限制行数
        doc = self._text_edit.document()
        if doc.blockCount() > self._max_lines:
            cursor = self._text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()

        # 滚动到底部
        scrollbar = self._text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear(self) -> None:
        """清空日志"""
        self._text_edit.clear()

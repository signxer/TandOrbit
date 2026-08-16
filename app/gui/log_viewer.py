"""TandOrbit 日志查看器

实时显示应用日志（通过 loguru sink + Qt 信号桥接，跨线程安全）。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_LEVEL_COLORS = {
    "DEBUG": "#888888",
    "INFO": "#d4d4d4",
    "WARNING": "#ffa500",
    "ERROR": "#ff4444",
    "CRITICAL": "#ff0000",
}


class LogViewer(QWidget):
    """日志查看器（应用内）"""

    # 跨线程安全：loguru sink 在任意线程 emit，Qt 自动排队到 GUI 线程
    log_message = Signal(str, str)  # (message, level)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TandOrbit 日志")
        self.resize(640, 420)
        self._setup_ui()
        self._log_buffer: list[str] = []
        self._max_lines = 2000
        self.log_message.connect(self._on_log_message)

    def _setup_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 工具栏
        toolbar = QHBoxLayout()
        open_file_btn = QPushButton("打开日志文件")
        open_file_btn.clicked.connect(self._open_log_file)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(open_file_btn)
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

    def _on_log_message(self, message: str, level: str) -> None:
        """收到日志消息（GUI 线程）"""
        self.append_log(message, level)

    def append_log(self, message: str, level: str = "INFO") -> None:
        """添加日志"""
        color = _LEVEL_COLORS.get(level, "#d4d4d4")
        # 转义 HTML 特殊字符，防止日志内容破坏渲染
        safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f'<span style="color:{color};">{safe}</span>'
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

    def _open_log_file(self) -> None:
        """用系统默认程序打开最新日志文件"""
        from pathlib import Path

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        log_dir = Path.home() / ".tandorbit" / "logs"
        try:
            files = sorted(
                log_dir.glob("tandorbit_*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            files = []
        if files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(files[0])))

    def _clear(self) -> None:
        """清空日志"""
        self._text_edit.clear()

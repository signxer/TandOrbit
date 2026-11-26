"""Application log viewer with a bounded, selectable console."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from app.gui.theme import button, colors, label, stylesheet

_LEVEL_COLORS = {
    "DEBUG": "#A9BAD0",
    "INFO": "#DAE5F4",
    "WARNING": "#FFD08B",
    "ERROR": "#FFAAB5",
    "CRITICAL": "#FFAAB5",
}


class LogViewer(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent: QWidget | None = None, log_dir=None) -> None:
        super().__init__(parent)
        self._log_dir = Path(log_dir) if log_dir else Path.home() / ".tandorbit/logs"
        self.setWindowTitle("TandOrbit 日志")
        self.setProperty("role", "window")
        self.setMinimumSize(565, 350)
        self.resize(784, 450)
        palette = colors()
        self.setStyleSheet(stylesheet() + f"""
            QPlainTextEdit[role="console"] {{
                background: {palette['console']}; color: {palette['console_text']};
                border-radius: 10px; padding: 12px; selection-background-color: #355781;
                selection-color: #FFFFFF;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(21, 18, 21, 16)
        layout.setSpacing(11)
        top = QHBoxLayout()
        top.addWidget(label("运行日志", "title"))
        top.addStretch()
        open_file = button("打开日志文件", "folder")
        open_file.clicked.connect(self._open_log_file)
        top.addWidget(open_file)
        clear = button("清空视图", "trash", kind="ghost")
        clear.clicked.connect(self._text_clear)
        top.addWidget(clear)
        layout.addLayout(top)
        self._text_edit = QPlainTextEdit()
        self._text_edit.setProperty("role", "console")
        self._text_edit.setAccessibleName("运行日志内容")
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._text_edit.setMaximumBlockCount(2000)
        self._text_edit.setPlaceholderText("等待日志…")
        layout.addWidget(self._text_edit, 1)
        self.log_message.connect(self.append_log)

    def append_log(self, message: str, level: str = "INFO") -> None:
        scroll = self._text_edit.verticalScrollBar()
        follow = scroll.value() == scroll.maximum()
        cursor = QTextCursor(self._text_edit.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self._text_edit.document().isEmpty():
            cursor.insertBlock()
        format = QTextCharFormat()
        format.setForeground(QColor(_LEVEL_COLORS.get(level, _LEVEL_COLORS["INFO"])))
        cursor.insertText(message, format)
        if follow:
            scroll.setValue(scroll.maximum())

    def _open_log_file(self) -> None:
        try:
            latest = max(self._log_dir.glob("tandorbit_*.log"), key=lambda path: path.stat().st_mtime, default=None)
        except OSError:
            latest = None
        if latest:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(latest)))

    def _text_clear(self) -> None:
        self._text_edit.clear()

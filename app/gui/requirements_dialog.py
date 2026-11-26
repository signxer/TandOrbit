"""Availability of optional display compatibility tools."""
from __future__ import annotations

import platform
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from app.gui.theme import button, card, colors, icon, label, stylesheet


class RequirementsDialog(QDialog):
    def __init__(self, parent=None, config_manager=None) -> None:
        super().__init__(parent)
        self._config_manager = config_manager
        self.setWindowTitle("显示器兼容工具")
        self.setMinimumWidth(448)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setStyleSheet(stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(label("显示器兼容工具", "title"))
        self._tool_list = QVBoxLayout()
        self._tool_list.setSpacing(9)
        layout.addLayout(self._tool_list)
        actions = QHBoxLayout()
        refresh = button("重新检查", "refresh", kind="ghost")
        refresh.clicked.connect(self._refresh)
        close = button("关闭", kind="primary")
        close.clicked.connect(self.accept)
        actions.addWidget(refresh)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        self._refresh()

    def _tools(self):
        config = self._config_manager.config if self._config_manager else None
        if platform.system() == "Darwin":
            path = config.betterdisplay.cli_path if config else (
                "/Applications/BetterDisplay.app/Contents/MacOS/betterdisplaycli")
            found = Path(path).is_file() or bool(shutil.which("betterdisplaycli"))
            return [("BetterDisplay", found, "共享模式中的逐屏断开与重连",
                     "https://github.com/waydabber/BetterDisplay/releases")]
        path = config.tools.multimonitortool_path if config else "MultiMonitorTool.exe"
        found = Path(path).is_file() or bool(shutil.which(path))
        return [("MultiMonitorTool", found, "Windows 显示器后端的可选兼容工具",
                 "https://www.nirsoft.net/utils/multi_monitor_tool.html")]

    def _refresh(self):
        while self._tool_list.count():
            self._tool_list.takeAt(0).widget().deleteLater()
        for name, available, detail, url in self._tools():
            row = card()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(13, 12, 13, 12)
            mark = QLabel()
            glyph = "check" if available else "info"
            ink = colors()["green" if available else "muted"]
            mark.setPixmap(icon(glyph, ink).pixmap(19, 19))
            layout.addWidget(mark)
            text = QVBoxLayout()
            text.addWidget(label(name, "section"))
            text.addWidget(label(detail, "muted", wrap=True))
            layout.addLayout(text, 1)
            if available:
                layout.addWidget(label("已安装", "success"))
            else:
                open_page = button("下载", "external")
                open_page.setToolTip("未检测到兼容工具")
                open_page.clicked.connect(lambda _checked, target=url: QDesktopServices.openUrl(QUrl(target)))
                layout.addWidget(open_page)
            self._tool_list.addWidget(row)

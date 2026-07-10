"""TandOrbit 依赖检查对话框

启动时检查必需的外部工具是否已安装，未安装的给出下载链接。
"""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.main_window import _COLORS, _FONT


def _check_betterdisplay() -> bool:
    cli = shutil.which("betterdisplaycli")
    if cli:
        return True
    paths = [
        "/Applications/BetterDisplay.app/Contents/MacOS/betterdisplaycli",
        "/opt/homebrew/bin/betterdisplaycli",
    ]
    return any(Path(p).exists() for p in paths)


def _check_multimonitortool() -> bool:
    return shutil.which("MultiMonitorTool.exe") is not None


def _check_deskflow() -> bool:
    system = platform.system()
    if system == "Darwin":
        return Path("/Applications/Deskflow.app").exists()
    elif system == "Windows":
        if shutil.which("deskflow.exe"):
            return True
        return Path("deskflow.exe").exists()
    return False


# (名称, 检查函数, 下载链接, 平台)
REQUIREMENTS: list[tuple[str, callable, str, str]] = [
    (
        "BetterDisplay",
        _check_betterdisplay,
        "https://github.com/waydabber/BetterDisplay/releases",
        "Darwin",
    ),
    (
        "MultiMonitorTool",
        _check_multimonitortool,
        "https://www.nirsoft.net/utils/multi_monitor_tool.html",
        "Windows",
    ),
    (
        "Deskflow",
        _check_deskflow,
        "https://github.com/deskflow/deskflow/releases",
        "all",
    ),
]


class RequirementsDialog(QDialog):
    """依赖检查对话框"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TandOrbit — 环境检查")
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(self._build_stylesheet())
        self._items: list[dict] = []
        self._setup_ui()
        self._run_check()

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
            QLabel {{
                color: {c['text']};
            }}
            QPushButton {{
                background: {c['bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 18px;
            }}
            QPushButton:hover {{
                background: {c['hover']};
            }}
            QPushButton:pressed {{
                background: {c['checked_bg']};
            }}
        """

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel("以下工具是 TandOrbit 正常运行所必需的：")
        title.setFont(QFont(_FONT, 13))
        layout.addWidget(title)

        # 检查项容器
        self._check_container = QVBoxLayout()
        self._check_container.setSpacing(8)
        layout.addLayout(self._check_container)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        recheck_btn = QPushButton("重新检查")
        recheck_btn.clicked.connect(self._run_check)
        btn_row.addWidget(recheck_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _run_check(self) -> None:
        """执行检查并刷新 UI"""
        # 清空旧项
        while self._check_container.count():
            item = self._check_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()

        system = platform.system()
        all_ok = True

        for name, check_fn, url, plat in REQUIREMENTS:
            if plat != "all" and plat != system:
                continue

            ok = check_fn()
            if not ok:
                all_ok = False

            row = self._create_check_row(name, ok, url)
            self._check_container.addWidget(row)

        if all_ok:
            status = QLabel("✅  所有依赖已就绪")
            status.setStyleSheet(f"color: #4CAF50; font-size: 14px; font-weight: bold;")
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._check_container.addWidget(status)

    def _create_check_row(self, name: str, ok: bool, url: str) -> QWidget:
        """创建单个检查项行"""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(10)

        # 状态图标
        icon = QLabel("✅" if ok else "❌")
        icon.setFixedWidth(24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(icon)

        # 工具名
        name_label = QLabel(name)
        name_label.setFont(QFont(_FONT, 13, QFont.Weight.Bold if not ok else QFont.Weight.Normal))
        h.addWidget(name_label)

        h.addStretch()

        if ok:
            status_label = QLabel("已安装")
            status_label.setStyleSheet(f"color: #4CAF50;")
            h.addWidget(status_label)
        else:
            status_label = QLabel("未安装")
            status_label.setStyleSheet(f"color: #FF5252;")
            h.addWidget(status_label)

            # 下载链接按钮
            link_btn = QPushButton("下载 ↗")
            link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            link_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {_COLORS['checked_border']};
                    border: 1px solid {_COLORS['checked_border']};
                    border-radius: 4px;
                    padding: 3px 12px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {_COLORS['checked_bg']};
                }}
            """)
            link_btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(u))
            h.addWidget(link_btn)

        return row

    @staticmethod
    def has_missing() -> bool:
        """快速检查是否有缺失的依赖"""
        system = platform.system()
        for name, check_fn, url, plat in REQUIREMENTS:
            if plat != "all" and plat != system:
                continue
            if not check_fn():
                return True
        return False

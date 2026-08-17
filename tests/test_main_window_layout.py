"""主窗口布局回归测试（offscreen Qt）"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class TestMainWindowLayout:
    def test_mode_button_content_fits(self, qapp, tmp_path) -> None:
        """模式按钮内部内容（图标+文字）必须能放入固定尺寸内，避免 Windows 字体下裁剪"""
        from pathlib import Path

        from app.gui.main_window import MainWindow, ModeButton
        from app.enums import Mode

        # 主窗口需要 base_dir 指向项目根（含 resources/）
        from app.main import _resource_path
        base_dir = _resource_path(".") if hasattr(_resource_path, "__call__") else None

        # 直接构造 ModeButton 验证内部布局
        root = Path(__file__).resolve().parent.parent
        btn = ModeButton("Windows", Mode.WINDOWS, "resources/windows.svg", root)
        # 激活布局后，sizeHint 高度应能容纳图标+间距+文字
        btn.layout().activate()
        # 需求 = 图标(32) + 间距(4) + 文字行高(11pt，用实际字体度量)
        font_metrics = btn._label.fontMetrics()
        text_height = font_metrics.height()
        need = 32 + 4 + text_height + 6  # 图标+间距+文字+上下内容边距
        assert btn.height() >= need, (
            f"按钮高度不足以容纳内容: height={btn.height()} need={need}"
        )

    def test_main_window_constructs(self, qapp, tmp_path) -> None:
        """主窗口能正常构造，不抛异常"""
        from pathlib import Path

        from app.gui.main_window import MainWindow
        root = Path(__file__).resolve().parent.parent
        window = MainWindow(base_dir=root, hotkeys={
            "switch_mac": "Ctrl+Alt+1",
            "switch_windows": "Ctrl+Alt+2",
            "switch_share": "Ctrl+Alt+3",
        })
        try:
            assert window._mode_buttons, "应有模式按钮"
            assert len(window._mode_buttons) == 3
            assert window._hk_labels, "应有快捷键提示"
        finally:
            window.close()

"""PyInstaller runtime hook: 确保 Qt 能找到平台插件"""
import os
import sys

if sys.platform == "darwin":
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    qt_plugin_path = os.path.join(base, "PySide6", "Qt", "plugins")
    if os.path.isdir(qt_plugin_path):
        os.environ["QT_PLUGIN_PATH"] = qt_plugin_path

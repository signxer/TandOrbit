"""TandOrbit 设置对话框

配置管理界面。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, ConfigManager


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, config_manager: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config_manager = config_manager
        self.setWindowTitle("TandOrbit 设置")
        self.setMinimumWidth(480)
        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_connection_tab(), "连接")
        tabs.addTab(self._create_display_tab(), "显示器")
        tabs.addTab(self._create_deskflow_tab(), "Deskflow")
        tabs.addTab(self._create_audio_tab(), "音频")
        layout.addWidget(tabs)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _create_connection_tab(self) -> QWidget:
        """连接配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("Windows Agent")
        form = QFormLayout(group)
        self._win_host = QLineEdit()
        self._win_port = QSpinBox()
        self._win_port.setRange(1, 65535)
        form.addRow("主机地址:", self._win_host)
        form.addRow("端口:", self._win_port)
        layout.addRow(group)
        return widget

    def _create_display_tab(self) -> QWidget:
        """显示器配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("显示器设置")
        form = QFormLayout(group)
        self._primary_id = QSpinBox()
        self._primary_id.setRange(1, 10)
        self._secondary_id = QSpinBox()
        self._secondary_id.setRange(1, 10)
        form.addRow("主显示器 ID:", self._primary_id)
        form.addRow("副显示器 ID:", self._secondary_id)
        layout.addRow(group)
        return widget

    def _create_deskflow_tab(self) -> QWidget:
        """Deskflow 配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("Deskflow 设置")
        form = QFormLayout(group)
        self._df_host = QLineEdit()
        self._df_port = QSpinBox()
        self._df_port.setRange(1, 65535)
        self._df_client = QLineEdit()
        form.addRow("服务器地址:", self._df_host)
        form.addRow("端口:", self._df_port)
        form.addRow("客户端名称:", self._df_client)
        layout.addRow(group)
        return widget

    def _create_audio_tab(self) -> QWidget:
        """音频配置标签页"""
        widget = QWidget()
        layout = QFormLayout(widget)

        group = QGroupBox("音频设置")
        form = QFormLayout(group)
        self._mac_audio = QLineEdit()
        self._win_audio = QLineEdit()
        form.addRow("Mac 音频输出:", self._mac_audio)
        form.addRow("Windows 音频输出:", self._win_audio)
        layout.addRow(group)
        return widget

    def _load_values(self) -> None:
        """加载当前配置值"""
        cfg = self._config_manager.config
        self._win_host.setText(cfg.windows.host)
        self._win_port.setValue(cfg.windows.port)
        self._primary_id.setValue(cfg.display.primary_id)
        self._secondary_id.setValue(cfg.display.secondary_id)
        self._df_host.setText(cfg.deskflow.server_host)
        self._df_port.setValue(cfg.deskflow.server_port)
        self._df_client.setText(cfg.deskflow.client_name)
        self._mac_audio.setText(cfg.audio.mac_output)
        self._win_audio.setText(cfg.audio.windows_output)

    def _save(self) -> None:
        """保存配置"""
        updates = {
            "windows": {
                "host": self._win_host.text(),
                "port": self._win_port.value(),
            },
            "display": {
                "primary_id": self._primary_id.value(),
                "secondary_id": self._secondary_id.value(),
            },
            "deskflow": {
                "server_host": self._df_host.text(),
                "server_port": self._df_port.value(),
                "client_name": self._df_client.text(),
            },
            "audio": {
                "mac_output": self._mac_audio.text(),
                "windows_output": self._win_audio.text(),
            },
        }
        self._config_manager.update(updates)
        self.accept()

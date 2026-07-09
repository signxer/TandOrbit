"""TandOrbit Mac 端主入口

启动 Mac 端 GUI 和控制系统。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import ConfigManager
from app.controller.controller import Controller
from app.enums import Mode
from app.events import EventBus, ModeChangedEvent
from app.gui.main_window import MainWindow
from app.gui.settings_dialog import SettingsDialog
from app.gui.tray import TrayIcon
from app.plugin_base import PluginRegistry
from app.scheduler.scheduler import Scheduler
from app.state.state_machine import StateManager

# 插件导入
from plugins.betterdisplay.plugin import BetterDisplayPlugin
from plugins.clipboard.plugin import ClipboardPlugin
from plugins.ddc.plugin import DDCPlugin
from plugins.deskflow.plugin import DeskflowPlugin
from plugins.wol.plugin import WoLPlugin


class AsyncWorker(QThread):
    """异步工作线程"""

    status_updated = Signal(bool, bool, bool)  # mac, win, deskflow
    mode_changed = Signal(str)
    init_report = Signal(list)  # [(name, success, reason)]

    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self._controller = controller
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._controller.initialize())
            self.init_report.emit(self._controller.init_results)
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Initialization error: {e}")

    def run_async(self, coro):  # type: ignore
        """在工作线程中执行异步任务"""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self) -> None:
        """停止事件循环"""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


def _resource_path(relative: str) -> Path:
    """获取资源文件路径（兼容 PyInstaller 打包和开发模式）"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """配置日志"""
    log_path = Path(log_dir)
    if not log_path.is_absolute():
        log_path = Path.home() / ".tandorbit" / log_dir
    log_path.mkdir(parents=True, exist_ok=True)
    logger.remove()
    if sys.stderr is not None:
        logger.add(sys.stderr, level=level)
    logger.add(
        str(log_path / "tandorbit_{time:YYYY-MM-DD}.log"),
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
    )


def main() -> None:
    """Mac 端主入口"""
    # 加载配置
    config_manager = ConfigManager()
    config = config_manager.load()

    # 配置日志
    setup_logging(config.log_dir, config.log_level)

    logger.info("TandOrbit Mac client starting...")

    # 创建核心组件
    event_bus = EventBus()
    state_manager = StateManager(event_bus)
    scheduler = Scheduler(event_bus)
    plugin_registry = PluginRegistry(event_bus)

    # 注册插件
    plugin_registry.register(BetterDisplayPlugin(event_bus, config.betterdisplay.model_dump()))
    plugin_registry.register(DeskflowPlugin(event_bus, config.deskflow.model_dump()))
    plugin_registry.register(WoLPlugin(event_bus))
    plugin_registry.register(DDCPlugin(event_bus))
    plugin_registry.register(ClipboardPlugin(event_bus))

    # 创建控制器
    controller = Controller(
        event_bus=event_bus,
        state_manager=state_manager,
        scheduler=scheduler,
        plugin_registry=plugin_registry,
        config_manager=config_manager,
    )

    # 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # macOS: 开发模式下隐藏 Dock 图标（打包后由 LSUIElement 处理）
    if sys.platform == "darwin":
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except ImportError:
            # PyObjC 不可用时（如打包环境），LSUIElement 已处理
            pass

    # 创建主窗口
    window = MainWindow(hotkeys=config.hotkeys)
    window.setWindowIcon(QIcon(str(_resource_path("resources/tray_icon.png"))))
    window.show()

    # 创建系统托盘
    tray_icon = QIcon(str(_resource_path("resources/tray_icon.png")))
    tray = TrayIcon(tray_icon)
    tray.show()

    # 创建设置对话框
    settings_dialog = SettingsDialog(
        config_manager,
        plugin_provider=lambda: plugin_registry.get_all(),
        parent=window,
    )

    # 创建异步工作线程
    worker = AsyncWorker(controller)
    worker.start()

    # 连接信号
    def on_mode_switch(mode: Mode) -> None:
        worker.run_async(controller.switch_mode(mode))

    def on_mode_changed(event: ModeChangedEvent) -> None:
        mode = Mode[event.new_mode] if event.new_mode in Mode.__members__ else Mode.UNKNOWN
        window.update_mode(mode)
        tray.update_mode(mode)

    def open_settings() -> None:
        settings_dialog._load_values()  # 刷新当前配置
        if settings_dialog.exec():  # 用户点了保存
            window.update_hotkeys(config_manager.config.hotkeys)

    window.mode_switch_requested.connect(on_mode_switch)
    window.sleep_display_requested.connect(lambda: worker.run_async(controller.sleep_display()))
    window.settings_requested.connect(open_settings)
    tray.mode_switch_requested.connect(on_mode_switch)
    def show_and_activate():
        window.show()
        window.raise_()
        window.activateWindow()

    tray.show_window_requested.connect(show_and_activate)
    tray.settings_requested.connect(open_settings)
    tray.quit_requested.connect(app.quit)

    # 订阅事件
    event_bus.subscribe(ModeChangedEvent, on_mode_changed)

    # 异步状态更新 → UI
    worker.status_updated.connect(window.update_device_status)

    # 插件初始化报告 → 提示缺失依赖
    def on_init_report(results: list) -> None:
        failed = [(name, reason) for name, ok, reason in results if not ok]
        if not failed:
            return
        lines = "\n".join(f"• {name}: {reason}" for name, reason in failed)
        QMessageBox.warning(
            window,
            "初始化提示",
            f"以下插件未能正常初始化，部分功能可能不可用：\n\n{lines}",
        )

    worker.init_report.connect(on_init_report)

    # 初始化完成后更新 UI
    def on_init_done() -> None:
        window.update_mode(state_manager.current_mode)
        tray.update_mode(state_manager.current_mode)
        # Mac 本机已启动，标记为在线
        window.update_device_status(
            mac_online=True,
            win_online=False,
            deskflow_connected=False,
        )

    worker.finished.connect(on_init_done)

    logger.info("TandOrbit Mac client started")
    app.exec()

    # 清理
    worker.run_async(controller.shutdown())
    worker.wait(1000)
    worker.stop()
    worker.wait(3000)
    logger.info("TandOrbit Mac client stopped")


if __name__ == "__main__":
    main()

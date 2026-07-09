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
    init_done = Signal()

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
            self.init_done.emit()
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


def _start_agent_server(config, event_bus: EventBus, state_manager: StateManager) -> None:
    """启动 Mac Agent Server（权威模式状态源）"""
    import threading

    import uvicorn

    from app.communication.agent_server import AgentServer

    port = config.mac.port
    server = AgentServer(host="0.0.0.0", port=port)
    server.set_state_manager(state_manager)

    app = server.create_app()

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        uv_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
        loop.run_until_complete(uvicorn.Server(uv_config).serve())

    threading.Thread(target=_run, daemon=True).start()
    logger.info(f"Mac Agent Server starting on port {port}")


def main() -> None:
    """Mac 端主入口"""
    # 加载配置
    config_manager = ConfigManager()
    config = config_manager.load()

    # 配置日志
    setup_logging(config.log_dir, config.log_level)

    logger.info("TandOrbit Mac client starting...")

    # 防止 macOS 锁屏后挂起服务
    import subprocess
    _caffeinate = subprocess.Popen(
        ["caffeinate", "-i", "-s"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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

    # 启动 Mac Agent Server（权威模式状态源）
    _start_agent_server(config, event_bus, state_manager)

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
    if sys.platform == "win32":
        window.setWindowIcon(QIcon(str(_resource_path("resources/icon.ico"))))
    else:
        window.setWindowIcon(QIcon(str(_resource_path("icon.png"))))
    window.show()

    # 创建系统托盘
    if sys.platform == "win32":
        tray_icon = QIcon(str(_resource_path("resources/icon.ico")))
    else:
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

    # --- 启动发现服务（window 创建后） ---
    from PySide6.QtCore import QTimer, QObject, Signal

    class DiscoverySignals(QObject):
        peer_discovered = Signal(dict)

    discovery_signals = DiscoverySignals()

    from app.communication.discovery import DiscoveryService
    discovery = DiscoveryService(local_port=config.mac.port)

    def _on_peer_discovered(peer):
        """发现对端后在主线程更新 UI"""
        logger.info(f"[UI] Peer discovered: {peer['role']} at {peer['host']}")
        if peer["role"] == "windows":
            win_host = peer["host"]
            cfg = config_manager.config
            if cfg.windows.host != win_host:
                config_manager.update({"windows": {"host": win_host}})
                logger.info(f"Auto-discovered Windows at {win_host}, config updated")
            # 更新状态灯
            window.update_device_status(
                mac_online=True,
                win_online=True,
                deskflow_connected=False,
            )

    discovery_signals.peer_discovered.connect(_on_peer_discovered)

    def _on_peer_found(peer):
        """发现对端（后台线程）→ 通过信号转发到主线程"""
        discovery_signals.peer_discovered.emit(peer)

    discovery.on_peer_discovered(_on_peer_found)
    # 延迟启动发现服务，确保 Qt 事件循环已运行
    QTimer.singleShot(500, discovery.start)

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
        # 不覆盖已有的状态（发现服务可能已经更新了）
        # 只设置初始状态，如果发现服务还没更新的话
        if not window._win_status._online:
            window.update_device_status(
                mac_online=True,
                win_online=False,
                deskflow_connected=False,
            )
        # 定时 ping Windows 检测在线状态
        from PySide6.QtCore import QTimer
        import subprocess

        def _check_win_online():
            win_host = config_manager.config.windows.host
            if not win_host:
                return
            try:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", win_host],
                    capture_output=True, timeout=3,
                )
                online = result.returncode == 0
            except Exception:
                online = False
            cur_win = window._win_status._online
            if online != cur_win:
                window.update_device_status(
                    mac_online=True,
                    win_online=online,
                    deskflow_connected=window._deskflow_status._online,
                )

        win_timer = QTimer()
        win_timer.timeout.connect(_check_win_online)
        win_timer.start(5000)
        _check_win_online()

    worker.init_done.connect(on_init_done)

    # 模式切换：检查 Windows 是否在线，离线时询问是否 WoL
    def on_mode_switch(mode: Mode) -> None:
        if mode == Mode.WINDOWS or mode == Mode.SHARE:
            win_online = window._win_status._online
            if not win_online:
                reply = QMessageBox.question(
                    window,
                    "Windows 离线",
                    "Windows 未开机或不在网络中，是否发送 WoL 唤醒？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    cfg = config_manager.config
                    if cfg.windows.mac_address:
                        worker.run_async(_wake_and_switch(mode))
                    else:
                        QMessageBox.warning(
                            window, "缺少配置",
                            "请先在设置中填写 Windows 的 MAC 地址。",
                        )
                    return
        worker.run_async(controller.switch_mode(mode))

    async def _wake_and_switch(mode: Mode):
        """发送 WoL 后等待 Windows 上线再切换"""
        cfg = config_manager.config
        wol = plugin_registry.get("wol")
        if wol:
            await wol.wake(cfg.windows.mac_address)
            logger.info(f"WoL sent to {cfg.windows.mac_address}")
        # 等待 Windows 上线
        import asyncio
        for _ in range(30):  # 最多等 60 秒
            if await controller.check_windows_agent():
                logger.info("Windows is online, switching mode")
                await controller.switch_mode(mode)
                return
            await asyncio.sleep(2)
        logger.error("Windows did not come online after WoL")
        from PySide6.QtWidgets import QApplication
        QMessageBox.warning(None, "唤醒超时", "Windows 未在 60 秒内上线，请检查网络。")

    window.mode_switch_requested.connect(on_mode_switch)

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

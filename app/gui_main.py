"""TandOrbit 跨平台 GUI 入口

在 macOS 和 Windows 上启动相同的 GUI 界面。
Windows 上同时启动 HTTP Agent Server，接收 Mac 端的控制指令。
"""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

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
            # 保持事件循环运行，以便后续 run_async 提交的任务能被执行
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
    # Windows GUI 模式下 sys.stderr 可能为 None（console=False）
    if sys.stderr is not None:
        logger.add(sys.stderr, level=level)
    logger.add(
        str(log_path / "tandorbit_{time:YYYY-MM-DD}.log"),
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
    )


def _start_agent_server(config, event_bus: EventBus, state_manager) -> None:
    """在后台线程启动 Windows Agent HTTP Server"""
    import uvicorn

    from app.communication.agent_server import AgentServer
    from plugins.audio.plugin import AudioPlugin
    from plugins.deskflow.plugin import DeskflowPlugin
    from plugins.multimonitortool.plugin import MultiMonitorToolPlugin

    display_plugin = MultiMonitorToolPlugin(event_bus, config.tools.model_dump())
    deskflow_cfg = {**config.deskflow.model_dump(), **config.tools.model_dump()}
    deskflow_plugin = DeskflowPlugin(event_bus, deskflow_cfg)
    audio_plugin = AudioPlugin(event_bus, config.audio.model_dump())

    server = AgentServer(host="0.0.0.0", port=config.windows.port)
    server.set_plugins(
        display=display_plugin,
        deskflow=deskflow_plugin,
        audio=audio_plugin,
    )
    server.set_state_manager(state_manager)

    app = server.create_app()

    def _run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _init_and_serve():
            await display_plugin.initialize()
            await display_plugin.enable()
            await deskflow_plugin.initialize()
            await deskflow_plugin.enable()
            await audio_plugin.initialize()
            await audio_plugin.enable()
            logger.info(f"Agent server starting on port {config.windows.port}")
            uv_config = uvicorn.Config(
                app, host="0.0.0.0", port=config.windows.port, log_level="warning"
            )
            uv_server = uvicorn.Server(uv_config)
            await uv_server.serve()

        loop.run_until_complete(_init_and_serve())

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    logger.info("Agent server thread started")


def main() -> None:
    """跨平台 GUI 主入口"""
    try:
        _main()
    except Exception:
        # 打包后 stderr 可能为 None，写到文件兜底
        import traceback
        log_dir = Path.home() / ".tandorbit" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "crash.log", "w") as f:
            traceback.print_exc(file=f)
        raise


def _main() -> None:
    """实际主逻辑"""
    config_manager = ConfigManager()
    config = config_manager.load()

    setup_logging(config.log_dir, config.log_level)

    is_mac = sys.platform == "darwin"
    logger.info(f"TandOrbit starting on {'macOS' if is_mac else 'Windows'}...")

    # --- 创建核心组件 ---
    event_bus = EventBus()
    state_manager = StateManager(event_bus)
    scheduler = Scheduler(event_bus)
    plugin_registry = PluginRegistry(event_bus)

    # --- 注册平台相关插件 ---
    if is_mac:
        from plugins.betterdisplay.plugin import BetterDisplayPlugin
        from plugins.clipboard.plugin import ClipboardPlugin
        from plugins.ddc.plugin import DDCPlugin
        from plugins.deskflow.plugin import DeskflowPlugin
        from plugins.wol.plugin import WoLPlugin

        plugin_registry.register(BetterDisplayPlugin(event_bus, config.betterdisplay.model_dump()))
        plugin_registry.register(DeskflowPlugin(event_bus, config.deskflow.model_dump()))
        plugin_registry.register(WoLPlugin(event_bus))
        plugin_registry.register(DDCPlugin(event_bus))
        plugin_registry.register(ClipboardPlugin(event_bus))
    else:
        from plugins.audio.plugin import AudioPlugin
        from plugins.ddc.plugin import DDCPlugin
        from plugins.deskflow.plugin import DeskflowPlugin
        from plugins.multimonitortool.plugin import MultiMonitorToolPlugin

        plugin_registry.register(MultiMonitorToolPlugin(event_bus, config.tools.model_dump()))
        deskflow_cfg = {**config.deskflow.model_dump(), **config.tools.model_dump()}
        plugin_registry.register(DeskflowPlugin(event_bus, deskflow_cfg))
        plugin_registry.register(AudioPlugin(event_bus, config.audio.model_dump()))
        plugin_registry.register(DDCPlugin(event_bus, config.tools.model_dump()))

    # --- 创建控制器 ---
    controller = Controller(
        event_bus=event_bus,
        state_manager=state_manager,
        scheduler=scheduler,
        plugin_registry=plugin_registry,
        config_manager=config_manager,
    )

    # --- 启动 Agent Server ---
    if not is_mac:
        _start_agent_server(config, event_bus, state_manager)

    # --- 启动网络自动发现 ---
    from app.communication.discovery import DiscoveryService
    local_port = config.mac.port if is_mac else config.windows.port
    discovery = DiscoveryService(local_port=local_port)
    discovery.start()

    def _on_peer_found(peer):
        """发现对端后自动更新配置和状态"""
        if peer["role"] == "mac":
            # Windows 端发现 Mac
            mac_host = peer["host"]
            cfg = config_manager.config
            if cfg.deskflow.server_host != mac_host:
                config_manager.update({"deskflow": {"server_host": mac_host}})
                logger.info(f"Auto-discovered Mac at {mac_host}, config updated")
        elif peer["role"] == "windows":
            # Mac 端发现 Windows，更新状态灯
            logger.info(f"Windows discovered at {peer['host']}, updating status")
            window.update_device_status(
                mac_online=True,
                win_online=True,
                deskflow_connected=False,
            )

    discovery.on_peer_discovered(_on_peer_found)

    # --- 创建 Qt 应用 ---
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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

    # --- 连接信号 ---
    def on_mode_switch(mode: Mode) -> None:
        if mode == Mode.MAC:
            mac_online = window._mac_status._online
            if not mac_online:
                cfg = config_manager.config
                if cfg.mac.mac_address:
                    reply = QMessageBox.question(
                        window,
                        "Mac 离线",
                        "Mac 未响应，是否发送 WoL 唤醒？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        worker.run_async(_wake_mac_and_switch(mode))
                    return
                else:
                    QMessageBox.warning(
                        window, "缺少配置",
                        "请先在设置中填写 Mac 的 MAC 地址。",
                    )
                    return
        worker.run_async(controller.switch_mode(mode))

    async def _wake_mac_and_switch(mode: Mode):
        """发送 WoL 唤醒 Mac 后切换模式"""
        cfg = config_manager.config
        wol = plugin_registry.get("wol")
        if wol:
            await wol.wake(cfg.mac.mac_address)
            logger.info(f"WoL sent to Mac at {cfg.mac.mac_address}")
        # 等待 Mac 上线
        import asyncio
        import socket
        for _ in range(30):
            try:
                s = socket.create_connection((cfg.deskflow.server_host, cfg.mac.port), timeout=2)
                s.close()
                logger.info("Mac is online, switching mode")
                await controller.switch_mode(mode)
                return
            except OSError:
                pass
            await asyncio.sleep(2)
        logger.error("Mac did not come online after WoL")
        QMessageBox.warning(None, "唤醒超时", "Mac 未在 60 秒内上线，请检查网络。")

    def on_mode_changed(event: ModeChangedEvent) -> None:
        mode = Mode[event.new_mode] if event.new_mode in Mode.__members__ else Mode.UNKNOWN
        window.update_mode(mode)
        tray.update_mode(mode)

    def open_settings() -> None:
        settings_dialog._load_values()
        if settings_dialog.exec():
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
        window.update_device_status(
            mac_online=is_mac,
            win_online=not is_mac,
            deskflow_connected=False,
        )
        # Windows 端：定时 ping Mac 检测是否在线
        if not is_mac:
            from PySide6.QtCore import QTimer
            import subprocess

            mac_host = config.deskflow.server_host

            def _check_mac_online():
                try:
                    result = subprocess.run(
                        ["ping", "-n", "1", "-w", "2000", mac_host],
                        capture_output=True, timeout=3,
                    )
                    online = result.returncode == 0
                except Exception:
                    online = False
                cur_mac = window._mac_status._online
                cur_deskflow = window._deskflow_status._online
                if online != cur_mac:
                    window.update_device_status(
                        mac_online=online,
                        win_online=True,
                        deskflow_connected=cur_deskflow,
                    )

            mac_timer = QTimer()
            mac_timer.timeout.connect(_check_mac_online)
            mac_timer.start(5000)
            # 首次立即检测
            _check_mac_online()
        else:
            # Mac 端：定时 ping Windows 检测是否在线
            from PySide6.QtCore import QTimer
            import subprocess

            win_host = config.windows.host

            def _check_win_online():
                try:
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "2000", win_host],
                        capture_output=True, timeout=3,
                    )
                    online = result.returncode == 0
                except Exception:
                    online = False
                cur_win = window._win_status._online
                cur_deskflow = window._deskflow_status._online
                if online != cur_win:
                    window.update_device_status(
                        mac_online=True,
                        win_online=online,
                        deskflow_connected=cur_deskflow,
                    )

            win_timer = QTimer()
            win_timer.timeout.connect(_check_win_online)
            win_timer.start(5000)
            # 首次立即检测
            _check_win_online()

    worker.init_done.connect(on_init_done)

    logger.info(f"TandOrbit GUI started on {'macOS' if is_mac else 'Windows'}")
    app.exec()

    # 清理
    worker.run_async(controller.shutdown())
    worker.wait(1000)
    worker.stop()
    worker.wait(3000)
    logger.info("TandOrbit stopped")


if __name__ == "__main__":
    main()

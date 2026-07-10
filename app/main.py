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
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

_MSGBOX_STYLE = """
    QPushButton {
        border: 1px solid #D0D0D0;
        border-radius: 6px;
        padding: 5px 18px;
        font-size: 13px;
        min-width: 60px;
    }
    QPushButton:hover { background: #F5F5F5; }
    QPushButton:pressed { background: #E8F0FE; }
"""


def _msgbox(icon: QMessageBox.Icon, title: str, text: str, parent=None) -> int:
    """统一样式的消息框"""
    msg = QMessageBox(parent)
    msg.setIcon(icon)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setStyleSheet(_MSGBOX_STYLE)
    msg.exec()
    return msg.result()

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


def _start_agent_server(config, event_bus: EventBus, state_manager: StateManager, plugin_registry: PluginRegistry) -> None:
    """启动 Agent Server（Mac: 权威模式状态源; Windows: 接收指令）"""
    import threading

    import uvicorn

    from app.communication.agent_server import AgentServer

    is_mac = sys.platform == "darwin"
    port = config.mac.port if is_mac else config.windows.port
    server = AgentServer(host="0.0.0.0", port=port)
    server.set_state_manager(state_manager)

    # 注入插件，使 API 端点可用
    display = plugin_registry.get("betterdisplay") if is_mac else plugin_registry.get("multimonitortool")
    deskflow = plugin_registry.get("deskflow")
    audio = plugin_registry.get("audio")
    server.set_plugins(display=display, deskflow=deskflow, audio=audio)

    app = server.create_app()

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        uv_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
        loop.run_until_complete(uvicorn.Server(uv_config).serve())

    threading.Thread(target=_run, daemon=True).start()
    logger.info(f"Agent Server starting on port {port}")


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
    if sys.platform == "darwin":
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

    # 注册插件（按平台区分）
    deskflow_cfg = {**config.deskflow.model_dump(), **config.tools.model_dump()}
    plugin_registry.register(DeskflowPlugin(event_bus, deskflow_cfg))
    plugin_registry.register(DDCPlugin(event_bus, config.tools.model_dump()))

    if sys.platform == "darwin":
        plugin_registry.register(BetterDisplayPlugin(event_bus, config.betterdisplay.model_dump()))
        plugin_registry.register(WoLPlugin(event_bus))
        plugin_registry.register(ClipboardPlugin(event_bus))
    else:
        from plugins.audio.plugin import AudioPlugin
        from plugins.multimonitortool.plugin import MultiMonitorToolPlugin
        plugin_registry.register(MultiMonitorToolPlugin(event_bus, config.tools.model_dump()))
        plugin_registry.register(AudioPlugin(event_bus, config.audio.model_dump()))

    # 创建控制器
    controller = Controller(
        event_bus=event_bus,
        state_manager=state_manager,
        scheduler=scheduler,
        plugin_registry=plugin_registry,
        config_manager=config_manager,
    )

    # 启动 Agent Server（注入插件）
    _start_agent_server(config, event_bus, state_manager, plugin_registry)

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
        tray_icon.setIsMask(True)  # macOS 模板图标，自动适配深色/浅色菜单栏
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
    discovery = DiscoveryService(
        local_port=config.mac.port if sys.platform == "darwin" else config.windows.port,
        wol_nic=config.wol_nic,
        config_manager=config_manager,
    )

    def _on_peer_discovered(peer):
        """发现对端后在主线程更新 UI（config 已由 DiscoveryService 自动更新）"""
        logger.info(f"[UI] Peer discovered: {peer['role']} at {peer['host']}")
        if peer["role"] == "windows":
            window.update_device_status(
                mac_online=True,
                win_online=True,
                deskflow_connected=False,
            )
        # 通知设置对话框刷新对端信息（如果打开的话）
        settings_dialog.refresh_remote_info()

    discovery_signals.peer_discovered.connect(_on_peer_discovered)

    def _on_peer_found(peer):
        """发现对端（后台线程）→ 通过信号转发到主线程"""
        discovery_signals.peer_discovered.emit(peer)

    discovery.on_peer_discovered(_on_peer_found)
    discovery.start()

    # 连接信号
    def on_mode_changed(event: ModeChangedEvent) -> None:
        mode = Mode[event.new_mode] if event.new_mode in Mode.__members__ else Mode.UNKNOWN
        window.update_mode(mode)
        tray.update_mode(mode)

    def open_settings() -> None:
        settings_dialog._load_values()  # 刷新当前配置
        if settings_dialog.exec():  # 用户点了保存
            window.update_hotkeys(config_manager.config.hotkeys)

    window.sleep_display_requested.connect(lambda: worker.run_async(controller.sleep_display()))
    window.settings_requested.connect(open_settings)
    def show_and_activate():
        window.show()
        window.raise_()
        window.activateWindow()

    tray.show_window_requested.connect(show_and_activate)
    tray.settings_requested.connect(open_settings)
    tray.quit_requested.connect(app.quit)

    # --- 检查更新 ---
    from app.updater import check_update, get_download_assets, __version__

    def _show_update_dialog(release: dict) -> None:
        """显示更新对话框"""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        tag = release.get("tag_name", "")
        url = release.get("html_url", "")
        body = release.get("body", "")

        # 截取更新日志前 500 字
        changelog = body[:500] + "..." if len(body) > 500 else body

        msg = QMessageBox(window)
        msg.setWindowTitle("发现新版本")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(f"新版本 <b>{tag}</b> 已发布（当前 {__version__}）")
        msg.setInformativeText(f"<b>更新日志：</b><br><pre style='font-size:11px;'>{changelog}</pre>")
        msg.setStandardButtons(QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ignore)
        msg.button(QMessageBox.StandardButton.Open).setText("前往下载")
        msg.button(QMessageBox.StandardButton.Ignore).setText("稍后再说")
        msg.setStyleSheet(_MSGBOX_STYLE)

        if msg.exec() == QMessageBox.StandardButton.Open:
            QDesktopServices.openUrl(QUrl(url))

    # 用信号桥接异步回调到主线程
    from PySide6.QtCore import QObject, Signal as QSignal

    class _UpdateSignals(QObject):
        result = QSignal(object, bool)  # (release_or_None, silent)

    _update_signals = _UpdateSignals()

    def _on_update_result(release, silent):
        if release:
            _show_update_dialog(release)
        elif not silent:
            _msgbox(QMessageBox.Icon.Information, "检查更新", f"当前已是最新版本 {__version__}", window)

    _update_signals.result.connect(_on_update_result)

    def _do_check_update(silent: bool = False) -> None:
        """执行更新检查（异步）"""
        async def _check():
            release = await check_update()
            _update_signals.result.emit(release, silent)
        worker.run_async(_check())

    tray.check_update_requested.connect(lambda: _do_check_update(silent=False))

    # 启动后静默检查一次更新
    from PySide6.QtCore import QTimer
    QTimer.singleShot(3000, lambda: _do_check_update(silent=True))

    # 订阅事件
    event_bus.subscribe(ModeChangedEvent, on_mode_changed)

    # 异步状态更新 → UI
    worker.status_updated.connect(window.update_device_status)

    # 插件初始化报告 → 缺失依赖时弹出检查清单
    def on_init_report(results: list) -> None:
        failed = [ok for _, ok, _ in results if not ok]
        if not failed:
            return
        from app.gui.requirements_dialog import RequirementsDialog
        dlg = RequirementsDialog(window)
        dlg.exec()

    worker.init_report.connect(on_init_report)

    # 初始化完成后更新 UI
    def on_init_done() -> None:
        window.update_mode(state_manager.current_mode)
        tray.update_mode(state_manager.current_mode)
        # 不覆盖已有的状态（发现服务可能已经更新了）
        # 只设置初始状态，如果发现服务还没更新的话
        logger.info(f"[DEBUG] on_init_done: win_online={window._win_status._online}")
        if not window._win_status._online:
            logger.info("[DEBUG] Setting win_online=False (not overwritten by discovery)")
            window.update_device_status(
                mac_online=True,
                win_online=False,
                deskflow_connected=False,
            )
        # 定时 ping Windows 检测在线状态
        from PySide6.QtCore import QTimer
        import subprocess

        def _check_win_online():
            # 如果发现服务已经标记为在线，不覆盖
            if window._win_status._online:
                return
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
            if online:
                window.update_device_status(
                    mac_online=True,
                    win_online=True,
                    deskflow_connected=window._deskflow_status._online,
                )

        win_timer = QTimer()
        win_timer.timeout.connect(_check_win_online)
        win_timer.start(5000)

        # 定时检查 Deskflow SSL 连接状态
        from PySide6.QtCore import Signal as QSignal, QObject

        class _DeskflowChecker(QObject):
            result = QSignal(bool)

        deskflow_checker = _DeskflowChecker()
        deskflow_plugin = plugin_registry.get("deskflow")

        def _on_deskflow_result(connected: bool) -> None:
            if connected != window._deskflow_status._online:
                window.update_device_status(
                    mac_online=True,
                    win_online=window._win_status._online,
                    deskflow_connected=connected,
                )

        deskflow_checker.result.connect(_on_deskflow_result)

        def _check_deskflow():
            if not deskflow_plugin:
                return
            async def _do_check():
                connected = await deskflow_plugin.check_connection()
                deskflow_checker.result.emit(connected)
            worker.run_async(_do_check())

        deskflow_timer = QTimer()
        deskflow_timer.timeout.connect(_check_deskflow)
        deskflow_timer.start(5000)

    worker.init_done.connect(on_init_done)

    # 切换完成后刷新 UI 按钮状态（确保与实际模式一致）
    class _ModeSyncSignals(QObject):
        sync = QSignal()

    _mode_sync = _ModeSyncSignals()

    def _sync_mode_ui() -> None:
        window.update_mode(controller.current_mode)
        tray.update_mode(controller.current_mode)

    _mode_sync.sync.connect(_sync_mode_ui)

    # 模式切换：检查 Windows 是否在线，离线时询问是否 WoL
    def on_mode_switch(mode: Mode) -> None:
        if mode == Mode.WINDOWS or mode == Mode.SHARE:
            win_online = window._win_status._online
            if not win_online:
                msg = QMessageBox(window)
                msg.setWindowTitle("Windows 离线")
                msg.setIcon(QMessageBox.Icon.Question)
                msg.setText("Windows 未开机或不在网络中，是否发送 WoL 唤醒？")
                yes_btn = msg.addButton("唤醒", QMessageBox.ButtonRole.AcceptRole)
                no_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(yes_btn)
                msg.setStyleSheet(_MSGBOX_STYLE)
                msg.exec()
                if msg.clickedButton() == yes_btn:
                    cfg = config_manager.config
                    if cfg.windows.mac_address:
                        worker.run_async(_wake_and_switch(mode))
                    else:
                        _msgbox(QMessageBox.Icon.Warning, "缺少配置", "请先在设置中填写 Windows 的 MAC 地址。", window)
                        _sync_mode_ui()
                else:
                    _sync_mode_ui()
                return
        async def _switch_and_sync():
            await controller.switch_mode(mode)
            _mode_sync.sync.emit()
        worker.run_async(_switch_and_sync())

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
                _mode_sync.sync.emit()
                return
            await asyncio.sleep(2)
        logger.error("Windows did not come online after WoL")
        _mode_sync.sync.emit()
        from PySide6.QtWidgets import QApplication
        _msgbox(QMessageBox.Icon.Warning, "唤醒超时", "Windows 未在 60 秒内上线，请检查网络。")

    window.mode_switch_requested.connect(on_mode_switch)
    tray.mode_switch_requested.connect(on_mode_switch)

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

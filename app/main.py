"""Start the TandOrbit desktop UI and its single service event loop."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from app.communication.discovery import DiscoveryService
from app.communication.pairing import Pairing
from app.config import ConfigManager
from app.controller.controller import Controller
from app.display_power import DisplayPower
from app.enums import Mode
from app.events import EventBus, ModeChangedEvent
from app.gui.log_viewer import LogViewer
from app.gui.main_window import MainWindow, _resource_path
from app.gui.settings_dialog import SettingsDialog
from app.gui.switch_history_dialog import SwitchHistoryDialog
from app.gui.tray import TrayIcon
from app.hotkeys import GlobalHotkeyManager
from app.native_input import create_native_input
from app.plugin_base import PluginRegistry
from app.runtime import Runtime
from app.scheduler.scheduler import Scheduler
from app.sharing import ShareSession
from app.state.state_machine import StateManager
from app.updater import __version__, check_update
from plugins.audio.plugin import AudioPlugin
from plugins.wol.plugin import WoLPlugin


class Worker(QThread):
    ready = Signal()

    def __init__(self, initialize, shutdown) -> None:
        super().__init__()
        self.loop = None
        self._start = initialize
        self._close = shutdown

    def run(self) -> None:
        async def services():
            self.loop = asyncio.get_running_loop()
            self.finished_work = asyncio.Event()
            try:
                await self._start()
            except Exception:
                logger.exception("初始化失败")
            self.ready.emit()
            await self.finished_work.wait()
            try:
                await self._close()
            finally:
                self.loop = None

        asyncio.run(services())

    def submit(self, coroutine):
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)

            def report(result):
                if not result.cancelled() and result.exception():
                    logger.warning(f"后台操作失败：{result.exception()}")
            future.add_done_callback(report)
            return future
        coroutine.close()
        return None

    def stop(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self.finished_work.set)


class Bridge(QObject):
    mode = Signal(object)
    status = Signal(dict)
    candidate = Signal(dict)
    clipboard = Signal(str)
    online = Signal(bool)
    update = Signal(object)


def setup_logging(config):
    path = Path(config.log_dir)
    if not path.is_absolute():
        path = Path.home() / ".tandorbit" / path
    path.mkdir(parents=True, exist_ok=True)
    logger.remove()
    if sys.stderr is not None:
        logger.add(sys.stderr, level=config.log_level)
    logger.add(path / "tandorbit_{time:YYYY-MM-DD}.log", rotation="1 day",
               retention=f"{config.log_retention_days} days", level=config.log_level)
    return path


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(_resource_path("resources/icon.png"))))
    if "--smoke-test" in sys.argv:
        from starlette.applications import Starlette
        from uvicorn import Config

        Config(Starlette(), log_config=None, ws="websockets-sansio").load()
        window = MainWindow()
        window.show()
        app.processEvents()
        window.close()
        return

    role = {"darwin": "mac", "win32": "windows"}.get(sys.platform)
    if role is None:
        QMessageBox.critical(None, "TandOrbit", "TandOrbit 支持 macOS 和 Windows。")
        return
    config = ConfigManager()
    saved = config.load()
    logs = setup_logging(saved)
    bridge = Bridge()
    bus = EventBus()
    state = StateManager(bus)
    registry = PluginRegistry(bus)

    if role == "mac":
        from plugins.native_display.mac import MacDisplay
        registry.register(MacDisplay(bus, saved.betterdisplay.model_dump()))
        registry.register(WoLPlugin(bus))
    elif saved.display.windows_backend == "native":
        from plugins.native_display.windows import WindowsDisplay
        registry.register(WindowsDisplay(bus))
    else:
        from plugins.multimonitortool.plugin import MultiMonitorToolPlugin
        registry.register(MultiMonitorToolPlugin(bus, saved.tools.model_dump()))
    registry.register(AudioPlugin(bus, saved.audio.model_dump()))

    window = MainWindow(hotkeys=saved.hotkeys)
    power = DisplayPower()
    power.install(app, window)
    native = create_native_input(role)
    pairing = Pairing(config.data_dir, role)
    sharing = ShareSession(role, config, native, bridge.clipboard.emit, bridge.status.emit)
    controller = Controller(bus, state, Scheduler(bus), registry, config)
    runtime = Runtime(controller, role, pairing, power, bridge.status.emit, sharing)
    local = saved.mac if role == "mac" else saved.windows
    discovery = DiscoveryService(local_port=local.port, wol_nic=saved.wol_nic)
    prevent_idle = None

    async def initialize():
        nonlocal prevent_idle
        if role == "mac":
            try:
                prevent_idle = await asyncio.create_subprocess_exec(
                    "/usr/bin/caffeinate", "-i", "-w", str(os.getpid()),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                )
            except OSError as exc:
                logger.warning(f"无法维持 Mac Agent 的后台唤醒：{exc}")
        await registry.initialize_all()
        await registry.enable_all()
        try:
            await runtime.start()
        except Exception as exc:
            bridge.status.emit({"phase": "connection_error", "error": str(exc)})
            raise

    async def shutdown():
        try:
            await runtime.close()
            await registry.shutdown_all()
        finally:
            if prevent_idle and prevent_idle.returncode is None:
                prevent_idle.terminate()
                await prevent_idle.wait()

    worker = Worker(initialize, shutdown)
    bus.subscribe(ModeChangedEvent, lambda event: bridge.mode.emit(Mode[event.new_mode]))
    bridge.mode.connect(window.update_mode)
    bridge.status.connect(window.show_operation)

    clipboard = app.clipboard()
    bridge.clipboard.connect(clipboard.setText)

    def clipboard_changed():
        if sharing._clipboard_armed and clipboard.mimeData() and clipboard.mimeData().hasText():
            sharing.clipboard_changed(clipboard.text())
    clipboard.dataChanged.connect(clipboard_changed)

    connected = False

    def online_changed(online):
        nonlocal connected
        connected = online
        window.update_device_status(role == "mac" or online, role == "windows" or online,
                                    window._deskflow_status._online)
    bridge.online.connect(online_changed)

    def desktop_changed(*_args):
        screen = app.primaryScreen()
        if screen:
            rect = screen.geometry()
            scale = screen.devicePixelRatio() if role == "windows" else 1
            native.geometry((int(rect.x() * scale), int(rect.y() * scale),
                             int(rect.width() * scale), int(rect.height() * scale)))
    desktop_changed()
    app.primaryScreenChanged.connect(desktop_changed)
    for screen in app.screens():
        screen.geometryChanged.connect(desktop_changed)
    app.screenAdded.connect(lambda screen: screen.geometryChanged.connect(desktop_changed))

    tray_icon = QIcon(str(_resource_path(
        "resources/tray_icon.png" if role == "mac" else "resources/icon.ico")))
    if role == "mac":
        tray_icon.setIsMask(True)
    tray = TrayIcon(tray_icon)
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    app.setQuitOnLastWindowClosed(not tray_available)
    if tray_available:
        tray.show()
    bridge.mode.connect(tray.update_mode)
    bridge.status.connect(tray.show_operation)

    def notice(message):
        window.show_operation({"phase": "failed", "error": str(message)})

    async def perform(mode, wake):
        try:
            if wake:
                bridge.status.emit({"phase": "waking", "target": mode.name})
                await runtime.wake_windows()
            await controller.switch_mode(mode)
        except Exception as exc:
            bridge.status.emit({"phase": "failed", "error": str(exc)})

    def switch(mode):
        wake = (role == "mac" and mode in (Mode.WINDOWS, Mode.SHARE)
                and pairing.peer is not None and not connected)
        if wake and QMessageBox.question(window, "唤醒 Windows", "Windows Agent 当前离线。发送唤醒包？") != (
            QMessageBox.StandardButton.Yes):
            return
        if not worker.submit(perform(mode, wake)):
            notice("服务正在启动，请稍后再试")

    window.mode_switch_requested.connect(switch)
    tray.mode_switch_requested.connect(switch)
    hotkeys = GlobalHotkeyManager()
    hotkeys.set_hotkeys(saved.hotkeys)
    actions = {"switch_mac": Mode.MAC, "switch_windows": Mode.WINDOWS, "switch_share": Mode.SHARE}
    hotkeys.hotkey_pressed.connect(lambda action: switch(actions[action]) if action in actions else None)
    hotkeys.start()

    async def sleep():
        try:
            if runtime.coordinator._active or runtime.participant._lock.locked():
                raise RuntimeError("切换进行中，请稍后休眠显示器")
            sharing.release()
            await power.set(False)
        except Exception as exc:
            bridge.status.emit({"phase": "failed", "error": str(exc)})
    window.sleep_display_requested.connect(lambda: worker.submit(sleep()))

    async def recover():
        try:
            await runtime.recover_local()
            bridge.status.emit({"phase": "local_restored"})
        except Exception as exc:
            bridge.status.emit({"phase": "failed", "error": str(exc)})
    tray.recover_requested.connect(lambda: worker.submit(recover()))
    window.recover_requested.connect(lambda: worker.submit(recover()))

    def show_settings():
        async def remote():
            return await runtime.client.request("GET", "/api/capabilities") if runtime.client else {}

        dialog = SettingsDialog(
            config, plugin_provider=registry.get_all, parent=window, submit=worker.submit,
            remote_provider=remote, pairing=pairing, discovery=discovery,
        )
        dialog.pairing_changed.connect(lambda: worker.submit(runtime.start()))
        previous_port = (config.config.mac if role == "mac" else config.config.windows).port
        if dialog.exec():
            window.update_hotkeys(config.config.hotkeys)
            hotkeys.set_hotkeys(config.config.hotkeys)
        current_port = (config.config.mac if role == "mac" else config.config.windows).port
        if current_port != previous_port:
            worker.submit(runtime.start())
        dialog.deleteLater()

    window.settings_requested.connect(show_settings)
    tray.settings_requested.connect(show_settings)
    tray.show_window_requested.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
    tray.quit_requested.connect(app.quit)

    history = SwitchHistoryDialog(controller.get_switch_history, controller.get_success_rate)
    viewer = LogViewer(log_dir=logs)
    sink = logger.add(lambda message: viewer.log_message.emit(
        str(message).rstrip(), message.record["level"].name))
    tray.switch_history_requested.connect(lambda: (history._refresh(), history.show(), history.raise_()))
    tray.view_log_requested.connect(lambda: (viewer.show(), viewer.raise_()))

    async def update():
        bridge.update.emit(await check_update())

    def show_update(release):
        if not release:
            QMessageBox.information(window, "检查更新", f"未发现可下载的更新。当前版本 {__version__}。")
        elif QMessageBox.question(window, "发现新版本", f"打开 {release['tag_name']} 下载页面？") == (
            QMessageBox.StandardButton.Yes):
            url = QUrl(release.get("html_url", ""))
            if url.scheme() == "https" and url.host() == "github.com":
                QDesktopServices.openUrl(url)
    tray.check_update_requested.connect(lambda: worker.submit(update()))
    bridge.update.connect(show_update)

    probe = None
    async def check_peer():
        online = await runtime.online()
        bridge.online.emit(online)
        if online:
            await runtime.recover()
            await runtime.observe_startup()

    def poll():
        nonlocal probe
        if probe is None or probe.done():
            probe = worker.submit(check_peer())

    async def candidate(peer):
        if await runtime.probe_candidate(peer):
            bridge.online.emit(True)
            await runtime.recover()
    bridge.candidate.connect(lambda peer: worker.submit(candidate(peer)))
    discovery.on_peer_discovered(bridge.candidate.emit)
    timer = QTimer(window)
    timer.timeout.connect(poll)
    timer.start(2500)
    worker.ready.connect(poll)
    worker.start()
    discovery.start()
    online_changed(False)
    window.show()
    app.exec()
    timer.stop()
    discovery.stop()
    hotkeys.stop()
    worker.stop()
    worker.wait()
    power.close(app)
    logger.remove(sink)


if __name__ == "__main__":
    main()

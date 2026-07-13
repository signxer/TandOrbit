"""TandOrbit 控制器

唯一入口，负责参数检查、状态检查、构建动作管道。
不负责业务逻辑。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.config import ConfigManager
from app.communication.mac_client import MacClient
from app.enums import Mode
from app.events import EventBus
from app.plugin_base import PluginRegistry
from app.scheduler.action_pipeline import ActionPipeline
from app.scheduler.actions import (
    ConfigureDisplaysForMac,
    ConfigureDisplaysForShare,
    ConfigureDisplaysForWindows,
    DelayAction,
    DisplaySleepAction,
    SetDisplayModeAction,
    LocalDisplayOffAction,
    LocalDisplayOnAction,
    LocalDisplaySleepPrimaryAction,
    ReconnectSecondaryDisplay,
    RestartDeskflowAction,
    SetAudioMacAction,
    SetWindowsDuplicateAction,
    StopDeskflowAction,
    WakeWindowsAction,
)
from app.scheduler.scheduler import Scheduler
from app.state.state_machine import StateManager


class Controller:
    """控制器

    所有操作的唯一入口。
    GUI → Controller → ActionPipeline → Actions → Plugins
    """

    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        scheduler: Scheduler,
        plugin_registry: PluginRegistry,
        config_manager: ConfigManager,
    ) -> None:
        self._event_bus = event_bus
        self._state = state_manager
        self._scheduler = scheduler
        self._plugins = plugin_registry
        self._config = config_manager
        self._win_client: MacClient | None = None  # Mac → Windows
        self._mac_client: MacClient | None = None  # Windows → Mac

    @property
    def current_mode(self) -> Mode:
        return self._state.current_mode

    @property
    def is_transitioning(self) -> bool:
        return self._state.is_transitioning

    @property
    def init_results(self) -> list[tuple[str, bool, str]]:
        """插件初始化结果 [(name, success, reason)]"""
        return getattr(self, "_init_results", [])

    def _get_win_client(self) -> MacClient:
        """获取或创建 Windows Agent 客户端（Mac → Windows）"""
        if self._win_client is None:
            cfg = self._config.config.windows
            self._win_client = MacClient(
                host=cfg.host, port=cfg.port, timeout=cfg.timeout
            )
        return self._win_client

    def _get_mac_client(self) -> MacClient:
        """获取或创建 Mac Agent 客户端（Windows → Mac）"""
        if self._mac_client is None:
            cfg = self._config.config
            self._mac_client = MacClient(
                host=cfg.mac.host, port=cfg.mac.port, timeout=cfg.windows.timeout
            )
        return self._mac_client

    def _get_plugin(self, name: str) -> Any:
        """获取插件实例"""
        return self._plugins.get(name)

    def _build_pipeline(self, from_mode: Mode, to_mode: Mode) -> ActionPipeline:
        """根据目标模式构建动作管道"""
        import platform
        is_mac = platform.system() == "Darwin"

        pipeline = ActionPipeline(
            name=f"{from_mode.name}_to_{to_mode.name}",
            event_bus=self._event_bus,
        )

        cfg = self._config.config
        # Mac 端用 win_client 调 Windows，Windows 端用 mac_client 调 Mac
        remote_client = self._get_win_client() if is_mac else self._get_mac_client()
        deskflow = self._get_plugin("deskflow")
        display = self._get_plugin("betterdisplay") if is_mac else self._get_plugin("multimonitortool")
        ddc = self._get_plugin("ddc")
        audio = self._get_plugin("audio")

        # === 切换到 Mac 模式 ===
        if to_mode == Mode.MAC:
            if is_mac:
                # 从 Share 模式切回时，等 Windows 先关屏再接回副屏
                if from_mode == Mode.SHARE:
                    pipeline.add_action(DelayAction(2.0, "等待 Windows 释放副屏"))
                    pipeline.add_action(ReconnectSecondaryDisplay(
                        mac_display_plugin=display,
                        secondary_display_id=cfg.display.secondary_id,
                    ))
                # Mac 端：唤醒全部显示器 + 停止 Deskflow + 切音频
                pipeline.add_action(
                    ConfigureDisplaysForMac(mac_display_plugin=display)
                )
                pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))
                if audio:
                    pipeline.add_action(SetAudioMacAction(
                        audio_plugin=audio,
                        device=cfg.audio.mac_output,
                    ))
            else:
                if from_mode == Mode.SHARE:
                    # Windows 端：先关屏释放副屏，再停 Deskflow
                    pipeline.add_action(LocalDisplayOffAction())
                    pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))
                else:
                    # Windows 端：等待 Mac 准备好 → 停 Deskflow → 关屏
                    pipeline.add_action(DelayAction(1.0, "等待 Mac 唤醒"))
                    pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))
                    pipeline.add_action(LocalDisplayOffAction())

        # === 切换到 Windows 模式 ===
        elif to_mode == Mode.WINDOWS:
            if is_mac:
                # 从 Share 模式切回时，等 Windows 先关屏再接回副屏
                if from_mode == Mode.SHARE:
                    pipeline.add_action(DelayAction(2.0, "等待 Windows 释放副屏"))
                    pipeline.add_action(ReconnectSecondaryDisplay(
                        mac_display_plugin=display,
                        secondary_display_id=cfg.display.secondary_id,
                    ))
                # Mac 端：唤醒 Windows + 配置显示器
                pipeline.add_action(WakeWindowsAction(
                    mac_address=cfg.windows.mac_address,
                    agent_host=cfg.windows.host,
                    agent_port=cfg.windows.port,
                    timeout=60.0,
                ))
                pipeline.add_action(
                    ConfigureDisplaysForWindows(
                        mac_display_plugin=display, win_client=remote_client
                    )
                )
                pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))
            else:
                if from_mode == Mode.SHARE:
                    # Windows 端：先关屏释放副屏，再启用扩展模式
                    pipeline.add_action(LocalDisplayOffAction())
                # Windows 端：扩展模式 + 停止 Deskflow
                pipeline.add_action(SetDisplayModeAction("extend", display_plugin=display))
                pipeline.add_action(LocalDisplayOnAction(display_plugin=display))
                pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))

        # === 切换到共享模式 ===
        elif to_mode == Mode.SHARE:
            if is_mac:
                # Mac 端：唤醒 Windows + 唤醒全部显示器
                if from_mode == Mode.MAC:
                    pipeline.add_action(WakeWindowsAction(
                        mac_address=cfg.windows.mac_address,
                        agent_host=cfg.windows.host,
                        agent_port=cfg.windows.port,
                        timeout=60.0,
                    ))
                pipeline.add_action(
                    ConfigureDisplaysForShare(
                        mac_display_plugin=display,
                        secondary_display_id=cfg.display.secondary_id,
                    )
                )
            else:
                # Windows 端：加载复制配置 → 等待 → 禁用主屏（主屏切到 Mac）
                pipeline.add_action(SetDisplayModeAction("clone", display_plugin=display))
                pipeline.add_action(DelayAction(10.0, "等待显示器配置生效"))
                pipeline.add_action(LocalDisplaySleepPrimaryAction(
                    display_plugin=display,
                    ddc_plugin=ddc,
                    primary_id=cfg.display.primary_id,
                    ddc_monitor=cfg.display.ddc_primary_monitor,
                ))
            pipeline.add_action(RestartDeskflowAction(deskflow_plugin=deskflow))

        return pipeline

    async def switch_mode(self, target: Mode) -> bool:
        """切换工作模式

        Args:
            target: 目标模式

        Returns:
            bool: 是否切换成功
        """
        logger.info(f"Controller: switch_mode({target.name})")

        # 1. 检查是否可以转换
        if not self._state.can_transition(target):
            logger.error(
                f"Cannot transition: {self._state.current_mode.name} -> {target.name}"
            )
            return False

        # 2. 设置目标状态
        if not self._state.set_target(target):
            return False

        # 3. 先通知远端开始切换（让远端先释放资源）
        if self._state.current_mode == Mode.SHARE:
            await self._sync_mode_to_remote(target)

        # 4. 构建管道（动态构建，不依赖预注册）
        pipeline = self._build_pipeline(self._state.current_mode, target)

        # 5. 开始转换
        if not self._state.begin_transition():
            self._state.rollback_transition()
            return False

        # 6. 执行管道
        success = await pipeline.execute()

        # 7. 提交或回滚
        if success:
            self._state.commit_transition()
            logger.info(f"Mode switched to {target.name}")
            # 再次通知远端确认模式（防止第3步的通知丢失）
            if self._state.current_mode != Mode.SHARE:
                await self._sync_mode_to_remote(target)
        else:
            self._state.rollback_transition()
            logger.error(f"Failed to switch to {target.name}, rolled back")

        return success

    async def _sync_mode_to_remote(self, mode: Mode) -> None:
        """同步模式到远端（带重试）"""
        import asyncio
        import platform

        for attempt in range(3):
            try:
                if platform.system() == "Darwin":
                    await self._get_win_client().set_mode(mode.name)
                else:
                    await self._get_mac_client().set_mode(mode.name)
                return  # 成功则退出
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Mode sync attempt {attempt + 1} failed: {e}, retrying...")
                    await asyncio.sleep(2.0)
                else:
                    logger.error(f"Mode sync to remote failed after 3 attempts: {e}")

    async def check_windows_agent(self) -> bool:
        """检查 Windows Agent 是否在线"""
        try:
            health = await self._get_win_client().health_check()
            return health is not None
        except Exception:
            return False

    async def wake_windows(self) -> bool:
        """手动唤醒 Windows"""
        cfg = self._config.config
        action = WakeWindowsAction(
            mac_address=cfg.windows.mac_address,
            agent_host=cfg.windows.host,
            agent_port=cfg.windows.port,
            timeout=60.0,
        )
        return await action.execute()

    async def sleep_display(self) -> bool:
        """仅关闭显示器（不休眠电脑）"""
        logger.info("Controller: sleeping display")
        action = DisplaySleepAction()
        return await action.execute()

    async def get_system_status(self) -> dict[str, object]:
        """获取系统状态"""
        health = await self._plugins.health_check_all()
        windows_online = await self.check_windows_agent()
        return {
            "current_mode": self._state.current_mode.name,
            "is_transitioning": self._state.is_transitioning,
            "windows_online": windows_online,
            "plugins_health": health,
            "config_display_primary": self._config.config.display.primary_id,
            "config_display_secondary": self._config.config.display.secondary_id,
        }

    async def initialize(self) -> bool:
        """初始化系统"""
        logger.info("Controller: initializing system")
        self._config.load()

        # 检查 Windows Agent 是否在线
        windows_online = await self.check_windows_agent()
        logger.info(f"Windows Agent online: {windows_online}")

        ok, init_results = await self._plugins.initialize_all()
        if ok:
            await self._plugins.enable_all()
        self._init_results = init_results

        # 根据平台设置初始模式
        import platform
        if platform.system() == "Windows":
            self._state.force_set(Mode.WINDOWS)
        else:
            self._state.force_set(Mode.MAC)

        return ok

    async def shutdown(self) -> None:
        """关闭系统"""
        logger.info("Controller: shutting down system")
        if self._win_client:
            await self._win_client.close()
        if self._mac_client:
            await self._mac_client.close()
        await self._plugins.shutdown_all()

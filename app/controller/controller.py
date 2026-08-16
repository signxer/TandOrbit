"""TandOrbit 控制器

唯一入口，负责参数检查、状态检查、构建动作管道。
不负责业务逻辑。
"""

from __future__ import annotations

import time
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
    VerifyDisplayModeAction,
    LocalDisplayOffAction,
    LocalDisplayOnAction,
    LocalDisplaySleepPrimaryAction,
    ReconnectSecondaryDisplay,
    RestartDeskflowAction,
    SetAudioMacAction,
    StopDeskflowAction,
    SwitchDisplayInputsAction,
    VerifyDisplayInputsAction,
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
        self.last_error: str = ""  # 最近一次切换失败原因（供 GUI 展示）
        # 切换历史（SQLite 持久化，重启不丢）
        from app.history import SwitchHistoryStore
        self._history_store = SwitchHistoryStore(
            self._config.data_dir / "state.db"
        )

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
        """获取或创建 Windows Agent 客户端（Mac → Windows）

        自动发现服务可能更新对端 host/port，配置变化时重建客户端，
        避免一直连接旧地址。
        """
        cfg = self._config.config.windows
        if (
            self._win_client is None
            or self._win_client.host != cfg.host
            or self._win_client.port != cfg.port
            or self._win_client.token != self._config.config.agent_token
        ):
            self._win_client = MacClient(
                host=cfg.host, port=cfg.port, timeout=cfg.timeout,
                token=self._config.config.agent_token,
            )
        return self._win_client

    def _get_mac_client(self) -> MacClient:
        """获取或创建 Mac Agent 客户端（Windows → Mac）"""
        cfg = self._config.config
        if (
            self._mac_client is None
            or self._mac_client.host != cfg.mac.host
            or self._mac_client.port != cfg.mac.port
            or self._mac_client.token != cfg.agent_token
        ):
            self._mac_client = MacClient(
                host=cfg.mac.host, port=cfg.mac.port, timeout=cfg.windows.timeout,
                token=cfg.agent_token,
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
        deskflow = self._get_plugin("deskflow")
        display = self._get_plugin("betterdisplay") if is_mac else self._get_plugin("multimonitortool")
        audio = self._get_plugin("audio")
        # DDC/CI 输入源切换（配置驱动，默认关闭）
        ddc = self._get_plugin("ddc")
        input_map: dict[str, dict[str, str]] = (
            cfg.display.input_map if cfg.display.ddc_switch_enabled else {}
        )

        # 显示器拓扑的目标状态（供验证动作使用）
        primary_id = cfg.display.primary_id
        secondary_id = cfg.display.secondary_id

        # === 切换到 Mac 模式 ===
        if to_mode == Mode.MAC:
            if is_mac:
                # 从 Share 模式切回时，等 Windows 先关屏再接回副屏
                if from_mode == Mode.SHARE:
                    pipeline.add_action(DelayAction(2.0, "等待 Windows 释放副屏"))
                    pipeline.add_action(ReconnectSecondaryDisplay(
                        mac_display_plugin=display,
                        secondary_display_id=secondary_id,
                    ))
                # 可选：DDC/CI 主动把显示器输入源切到 Mac（并读回验证）
                if input_map:
                    pipeline.add_action(SwitchDisplayInputsAction(ddc, input_map, "mac"))
                    pipeline.add_action(VerifyDisplayInputsAction(ddc, input_map, "mac"))
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
                # 可选：DDC/CI 主动把显示器输入源切到 Mac（并读回验证）
                if input_map:
                    pipeline.add_action(SwitchDisplayInputsAction(ddc, input_map, "mac"))
                    pipeline.add_action(VerifyDisplayInputsAction(ddc, input_map, "mac"))
                # Windows 端：停 Deskflow → 关屏（电源关，信号消失后显示器切到 Mac）
                pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))
                pipeline.add_action(LocalDisplayOffAction())

        # === 切换到 Windows 模式 ===
        elif to_mode == Mode.WINDOWS:
            if is_mac:
                # 从 Share 模式切回时，等 Windows 先配置好再处理副屏
                if from_mode == Mode.SHARE:
                    pipeline.add_action(DelayAction(2.0, "等待 Windows 释放副屏"))
                    pipeline.add_action(ReconnectSecondaryDisplay(
                        mac_display_plugin=display,
                        secondary_display_id=secondary_id,
                    ))
                # Mac 端：唤醒 Windows + 休眠 Mac 显示器（远端拓扑由模式同步负责）
                pipeline.add_action(WakeWindowsAction(
                    mac_address=cfg.windows.mac_address,
                    agent_host=cfg.windows.host,
                    agent_port=cfg.windows.port,
                    timeout=60.0,
                ))
                # 可选：DDC/CI 主动把显示器输入源切到 Windows（并读回验证）
                if input_map:
                    pipeline.add_action(SwitchDisplayInputsAction(ddc, input_map, "windows"))
                    pipeline.add_action(VerifyDisplayInputsAction(ddc, input_map, "windows"))
                pipeline.add_action(
                    ConfigureDisplaysForWindows(mac_display_plugin=display)
                )
                pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))
            else:
                # 可选：DDC/CI 主动把显示器输入源切到 Windows（并读回验证）
                if input_map:
                    pipeline.add_action(SwitchDisplayInputsAction(ddc, input_map, "windows"))
                    pipeline.add_action(VerifyDisplayInputsAction(ddc, input_map, "windows"))
                # Windows 端：启用所有显示器 → 扩展拓扑 → 验证
                pipeline.add_action(LocalDisplayOnAction(display_plugin=display))
                pipeline.add_action(SetDisplayModeAction("extend", display_plugin=display))
                pipeline.add_action(DelayAction(2.0, "等待扩展模式生效"))
                pipeline.add_action(VerifyDisplayModeAction(
                    "extend", display_plugin=display,
                    primary_id=primary_id, secondary_id=secondary_id,
                ))
                pipeline.add_action(StopDeskflowAction(deskflow_plugin=deskflow))

        # === 切换到共享模式 ===
        elif to_mode == Mode.SHARE:
            if is_mac:
                # Mac 端：唤醒 Windows（如从 Mac 模式）+ 断开 Mac 副屏
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
                        secondary_display_id=secondary_id,
                    )
                )
            else:
                # Windows 端：扩展拓扑 → 禁用主屏（主屏留给 Mac）→ 验证
                pipeline.add_action(SetDisplayModeAction("extend", display_plugin=display))
                pipeline.add_action(DelayAction(2.0, "等待扩展模式生效"))
                pipeline.add_action(LocalDisplaySleepPrimaryAction(
                    display_plugin=display,
                    primary_id=primary_id,
                ))
                pipeline.add_action(VerifyDisplayModeAction(
                    "share", display_plugin=display,
                    primary_id=primary_id, secondary_id=secondary_id,
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
        self.last_error = ""
        start_time = time.monotonic()
        from_mode = self._state.current_mode

        # 1. 检查是否可以转换
        if not self._state.can_transition(target):
            logger.error(
                f"Cannot transition: {self._state.current_mode.name} -> {target.name}"
            )
            self.last_error = f"非法状态转换: {self._state.current_mode.name} -> {target.name}"
            return False

        # 2. 设置目标状态
        if not self._state.set_target(target):
            self.last_error = f"无法设置目标状态: {target.name}"
            return False

        # 3. 切换前仲裁：向对端声明意图，对端切换中则等待其完成（最多 30s）
        if not await self._claim_remote(target):
            self._state.rollback_transition()
            logger.error(f"Mode claim failed for {target.name}: {self.last_error}")
            return False

        # 4. 切换前预检（对端在线、本机显示器插件可用）
        if not await self._precheck(target):
            self._state.rollback_transition()
            logger.error(f"Precheck failed for {target.name}: {self.last_error}")
            return False

        # 5. 预同步远端（先让远端完成配置，再操作本机，避免两端互相干扰）
        await self._sync_mode_to_remote(target)

        # 6. 构建管道（动态构建，不依赖预注册）
        pipeline = self._build_pipeline(self._state.current_mode, target)

        # 7. 开始转换
        if not self._state.begin_transition():
            self._state.rollback_transition()
            self.last_error = "系统正在切换中，请稍后再试"
            return False

        # 8. 执行管道
        success = await pipeline.execute()
        if not success:
            self._state.rollback_transition()
            action_name, action_error = pipeline.last_failure or ("Pipeline", "未知错误")
            self.last_error = f"动作 {action_name} 失败: {action_error}"
            logger.error(f"Failed to switch to {target.name}: {self.last_error}")
            self._record_switch(from_mode, target, False, start_time, self.last_error)
            return False

        # 9. 提交状态
        self._state.commit_transition()

        # 10. 后同步确认 + 端到端验证（带重试）
        if not await self._post_sync_and_verify(target):
            self._state.rollback_transition()
            logger.error(f"Remote display verification failed for {target.name}: {self.last_error}")
            self._record_switch(from_mode, target, False, start_time, self.last_error)
            return False

        # 11. 持久化上次模式（启动恢复用）
        try:
            self._config.config.last_mode = target.name
            self._config.save()
        except Exception as e:
            logger.warning(f"Failed to persist last_mode: {e}")

        self._record_switch(from_mode, target, True, start_time, "")
        logger.info(f"Mode switched to {target.name}")
        return True

    async def _claim_remote(
        self, target: Mode, timeout: float = 30.0, interval: float = 2.0
    ) -> bool:
        """向对端声明切换意图；对端切换中则等待其完成（默认最多 30 秒）

        冲突裁决：两端同时发起切换时，后声明的一方等待先声明的一方完成，
        避免双端动作并发执行互相干扰。
        """
        import asyncio
        import platform

        if platform.system() == "Darwin":
            claim = self._get_win_client().claim_mode
        else:
            claim = self._get_mac_client().claim_mode

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await claim(target.name):
                return True
            logger.info(f"Remote busy, waiting to claim {target.name}...")
            await asyncio.sleep(interval)
        self.last_error = f"对端正在切换中（{timeout:.0f} 秒内未完成），请稍后再试"
        return False

    async def _precheck(self, target: Mode) -> bool:
        """切换前预检：目标模式依赖的对端 Agent 与本机显示器插件可用性"""
        import platform

        is_mac = platform.system() == "Darwin"
        if target in (Mode.WINDOWS, Mode.SHARE) and is_mac:
            if not await self.check_windows_agent():
                self.last_error = "预检失败：Windows Agent 不在线，无法切换到目标模式"
                return False
        elif target == Mode.MAC and not is_mac:
            if not await self.check_mac_agent():
                self.last_error = "预检失败：Mac Agent 不在线，无法切换到 Mac 模式"
                return False

        display = self._get_plugin("betterdisplay") if is_mac else self._get_plugin("multimonitortool")
        status = getattr(display, "status", None) if display else None
        if display is None or status is None or getattr(status, "name", "") == "ERROR":
            self.last_error = "预检失败：显示器控制插件不可用"
            return False
        return True

    # ---------- 切换历史 ----------

    def _record_switch(
        self,
        from_mode: Mode,
        to_mode: Mode,
        success: bool,
        start_time: float,
        error: str,
    ) -> None:
        """记录一次切换（SQLite 持久化 + 内存缓存）"""
        import datetime

        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "from": from_mode.name,
            "to": to_mode.name,
            "success": success,
            "duration_ms": round((time.monotonic() - start_time) * 1000),
            "error": error,
        }
        try:
            self._history_store.record(record)
        except Exception as e:
            logger.warning(f"Failed to persist switch history: {e}")

    def get_switch_history(self) -> list[dict[str, object]]:
        """获取切换历史（最新在前）"""
        try:
            return self._history_store.recent(100)
        except Exception as e:
            logger.warning(f"Failed to read switch history: {e}")
            return []

    def get_success_rate(self, window: int = 20) -> tuple[int, int, float]:
        """近 window 次切换的成功率：返回 (成功数, 总数, 成功率)"""
        try:
            return self._history_store.success_rate(window)
        except Exception:
            return 0, 0, 0.0

    async def _post_sync_and_verify(
        self, target: Mode, max_attempts: int = 3, interval: float = 2.0
    ) -> bool:
        """后同步 + 验证远端显示器状态，失败时重试"""
        import asyncio

        for attempt in range(max_attempts):
            await self._sync_mode_to_remote(target)
            if await self._verify_remote_state(target):
                return True
            if attempt < max_attempts - 1:
                logger.warning(f"Remote state verification attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(interval)
        self.last_error = f"远端显示器状态验证失败（{target.name}）"
        return False

    async def _verify_remote_state(self, target: Mode) -> bool:
        """验证远端 Windows 显示器拓扑是否符合目标模式（端到端）"""
        import platform

        if platform.system() != "Darwin":
            # 本机即 Windows：本地管线已做验证
            return True
        if target == Mode.MAC:
            # MAC 模式无法读取显示器电源状态，跳过验证
            return True
        try:
            displays = await self._get_win_client().list_displays()
        except Exception as e:
            logger.warning(f"Remote state verification failed: {e}")
            return False
        by_id = {d.id: d for d in displays}
        cfg = self._config.config
        primary = by_id.get(cfg.display.primary_id)
        secondary = by_id.get(cfg.display.secondary_id)
        if target == Mode.WINDOWS:
            if primary is None or not primary.is_enabled:
                logger.warning(f"Remote verify: primary DISPLAY{cfg.display.primary_id} not enabled")
                return False
            if secondary is not None and not secondary.is_enabled:
                logger.warning(f"Remote verify: secondary DISPLAY{cfg.display.secondary_id} not enabled")
                return False
            return True
        if target == Mode.SHARE:
            if primary is None or secondary is None:
                logger.warning("Remote verify: primary/secondary display missing")
                return False
            if primary.is_enabled:
                logger.warning(f"Remote verify: primary DISPLAY{cfg.display.primary_id} still enabled in SHARE")
                return False
            if not secondary.is_enabled:
                logger.warning(f"Remote verify: secondary DISPLAY{cfg.display.secondary_id} not enabled in SHARE")
                return False
            return True
        return True

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

    async def check_mac_agent(self) -> bool:
        """检查 Mac Agent 是否在线（Windows 端使用）"""
        try:
            health = await self._get_mac_client().health_check()
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

        # 初始模式：优先恢复上次成功切换的模式，否则按平台默认
        import platform
        initial_mode: Mode | None = None
        last_mode = getattr(self._config.config, "last_mode", None)
        if last_mode in Mode.__members__:
            initial_mode = Mode[last_mode]
        if initial_mode is None:
            initial_mode = Mode.WINDOWS if platform.system() == "Windows" else Mode.MAC
        self._state.force_set(initial_mode)
        logger.info(f"Initial mode: {initial_mode.name} (last_mode={last_mode!r})")

        # 启动自检：本地显示器状态与模式是否一致（仅诊断日志）
        await self._self_check(initial_mode)

        # 自愈（默认关闭）：按上次模式重新应用本地显示器配置
        if self._config.config.display.auto_repair:
            logger.info("auto_repair 已开启，正在按上次模式自愈显示器状态…")
            await self._reconcile_local_displays(initial_mode)

        return ok

    async def _self_check(self, mode: Mode) -> None:
        """启动自检：验证本地显示器状态与当前模式是否一致（仅诊断日志）"""
        import platform

        is_mac = platform.system() == "Darwin"
        display = self._get_plugin("betterdisplay") if is_mac else self._get_plugin("multimonitortool")
        if display is None or not hasattr(display, "list_displays"):
            return
        try:
            displays = await display.list_displays()
        except Exception as e:
            logger.warning(f"启动自检：无法枚举显示器: {e}")
            return
        by_id = {d.id: d for d in displays}
        cfg = self._config.config
        if is_mac:
            if mode == Mode.SHARE:
                secondary = by_id.get(cfg.display.secondary_id)
                if secondary is not None and secondary.is_enabled:
                    logger.warning(
                        f"启动自检：Share 模式下 Mac 副屏 (tagID={secondary.id}) 仍处于连接状态"
                    )
        else:
            primary = by_id.get(cfg.display.primary_id)
            secondary = by_id.get(cfg.display.secondary_id)
            if mode == Mode.SHARE:
                if primary is not None and primary.is_enabled:
                    logger.warning("启动自检：Share 模式下 Windows 主屏仍启用")
                if secondary is not None and not secondary.is_enabled:
                    logger.warning("启动自检：Share 模式下 Windows 副屏未启用")
            elif mode == Mode.WINDOWS:
                if primary is not None and not primary.is_enabled:
                    logger.warning("启动自检：Windows 模式下主屏未启用")

    async def _reconcile_local_displays(self, mode: Mode) -> None:
        """按上次模式自愈本地显示器状态（auto_repair 开启时在启动时调用）"""
        import asyncio
        import platform

        is_mac = platform.system() == "Darwin"
        display = self._get_plugin("betterdisplay") if is_mac else self._get_plugin("multimonitortool")
        if display is None:
            logger.warning("自愈跳过：显示器控制插件不可用")
            return
        cfg = self._config.config
        try:
            if is_mac:
                if mode == Mode.WINDOWS:
                    await self._sleep_local_displays()
                elif mode == Mode.SHARE:
                    await self._disconnect_secondary(display, cfg.display.secondary_id)
                    await self._wake_local_displays()
                else:  # MAC
                    await self._reconnect_secondary(display, cfg.display.secondary_id)
                    await self._wake_local_displays()
            else:
                if mode == Mode.MAC:
                    await self._power_off_local_displays()
                elif mode == Mode.SHARE:
                    await self._ensure_enabled(display, cfg.display.secondary_id)
                    await display.set_extend_mode()
                    await display.disable_display(cfg.display.primary_id)
                else:  # WINDOWS
                    await self._enable_all_local_displays(display)
                    await display.set_extend_mode()
                    await self._power_on_local_displays()
        except Exception as e:
            logger.warning(f"启动自愈失败: {e}")

    # --- 自愈用本地显示器辅助 ---

    @staticmethod
    async def _wake_local_displays() -> None:
        import asyncio
        import platform
        if platform.system() == "Darwin":
            try:
                proc = await asyncio.create_subprocess_shell(
                    "caffeinate -u -t 1",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            except Exception:
                pass

    @staticmethod
    async def _sleep_local_displays() -> None:
        import asyncio
        import platform
        if platform.system() == "Darwin":
            try:
                proc = await asyncio.create_subprocess_shell(
                    "pmset displaysleepnow",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            except Exception:
                pass

    @staticmethod
    async def _disconnect_secondary(display: Any, fallback_id: int) -> None:
        from app.scheduler.actions import _resolve_secondary_display_id

        display_id = await _resolve_secondary_display_id(display, fallback_id)
        try:
            ok = await display.disable_display(display_id)
            if not ok:
                logger.warning(f"自愈：Mac 副屏 (tagID={display_id}) 断开失败")
        except Exception as e:
            logger.warning(f"自愈：Mac 副屏断开异常: {e}")

    @staticmethod
    async def _reconnect_secondary(display: Any, fallback_id: int) -> None:
        from app.scheduler.actions import _resolve_secondary_display_id

        display_id = await _resolve_secondary_display_id(display, fallback_id)
        try:
            await display.enable_display(display_id)
        except Exception as e:
            logger.warning(f"自愈：Mac 副屏重连异常: {e}")

    @staticmethod
    async def _power_off_local_displays() -> None:
        import ctypes
        import platform
        if platform.system() == "Windows":
            try:
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            except Exception:
                pass

    @staticmethod
    async def _power_on_local_displays() -> None:
        import ctypes
        import platform
        if platform.system() == "Windows":
            try:
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
            except Exception:
                pass

    @staticmethod
    async def _ensure_enabled(display: Any, display_id: int) -> None:
        try:
            displays = await display.list_displays()
            for d in displays:
                if d.id == display_id:
                    if d.is_enabled:
                        return
                    break
            await display.enable_display(display_id)
        except Exception as e:
            logger.warning(f"自愈：确保显示器 {display_id} 启用失败: {e}")

    @staticmethod
    async def _enable_all_local_displays(display: Any) -> None:
        import asyncio
        try:
            displays = await display.list_displays()
            for d in displays:
                if not d.is_enabled:
                    await display.enable_display(d.id)
                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"自愈：启用全部显示器失败: {e}")

    async def shutdown(self) -> None:
        """关闭系统"""
        logger.info("Controller: shutting down system")
        if self._win_client:
            await self._win_client.close()
        if self._mac_client:
            await self._mac_client.close()
        await self._plugins.shutdown_all()

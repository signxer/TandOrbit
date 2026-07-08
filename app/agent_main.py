"""TandOrbit Windows Agent 主入口

启动 Windows 端 HTTP Agent 服务。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

from app.communication.agent_server import AgentServer
from app.config import ConfigManager
from app.events import EventBus
from app.plugin_base import PluginRegistry

# 插件导入
from plugins.audio.plugin import AudioPlugin
from plugins.ddc.plugin import DDCPlugin
from plugins.deskflow.plugin import DeskflowPlugin
from plugins.multimonitortool.plugin import MultiMonitorToolPlugin


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """配置日志"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level)
    logger.add(
        str(log_path / "tandorbit_agent_{time:YYYY-MM-DD}.log"),
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
    )


async def async_main() -> None:
    """异步主函数"""
    # 加载配置
    config_manager = ConfigManager()
    config = config_manager.load()

    # 配置日志
    setup_logging(config.log_dir, config.log_level)

    logger.info("TandOrbit Windows Agent starting...")

    # 创建核心组件
    event_bus = EventBus()
    plugin_registry = PluginRegistry(event_bus)

    # 注册插件
    display_plugin = MultiMonitorToolPlugin(event_bus)
    deskflow_plugin = DeskflowPlugin(event_bus, config.deskflow.model_dump())
    audio_plugin = AudioPlugin(event_bus, config.audio.model_dump())
    ddc_plugin = DDCPlugin(event_bus)

    plugin_registry.register(display_plugin)
    plugin_registry.register(deskflow_plugin)
    plugin_registry.register(audio_plugin)
    plugin_registry.register(ddc_plugin)

    # 初始化插件
    await plugin_registry.initialize_all()
    await plugin_registry.enable_all()

    # 创建 Agent 服务器
    server = AgentServer(
        host="0.0.0.0",
        port=config.windows.port,
    )
    server.set_plugins(
        display=display_plugin,
        deskflow=deskflow_plugin,
        audio=audio_plugin,
    )

    logger.info(f"TandOrbit Windows Agent ready on port {config.windows.port}")

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Agent shutting down...")
    finally:
        await plugin_registry.shutdown_all()
        logger.info("TandOrbit Windows Agent stopped")


def main() -> None:
    """Windows Agent 主入口"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

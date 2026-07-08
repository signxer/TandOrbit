"""Wake on LAN 插件实现

通过 WOL 协议远程唤醒计算机。
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import DeviceStatusChangedEvent, EventBus
from app.plugin_base import Plugin


class WoLPlugin(Plugin):
    """Wake on LAN 插件

    通过发送魔术包唤醒远程计算机。
    """

    def __init__(self, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        super().__init__("wol", event_bus, config)
        self._mac_address = self.config.get("mac_address", "")
        self._broadcast_ip = self.config.get("broadcast_ip", "255.255.255.255")
        self._port = self.config.get("port", 9)

    async def initialize(self) -> bool:
        self._set_status(PluginStatus.INITIALIZED)
        logger.info("WoL plugin initialized")
        return True

    async def enable(self) -> bool:
        self._set_status(PluginStatus.ENABLED)
        return True

    async def disable(self) -> bool:
        self._set_status(PluginStatus.DISABLED)
        return True

    async def health_check(self) -> bool:
        return bool(self._mac_address)

    async def shutdown(self) -> None:
        self._set_status(PluginStatus.DISABLED)

    # --- WOL 控制接口 ---

    async def wake(self, mac_address: str | None = None, broadcast_ip: str | None = None) -> bool:
        """发送 WOL 魔术包唤醒远程计算机

        Args:
            mac_address: MAC 地址（如 AA:BB:CC:DD:EE:FF）
            broadcast_ip: 广播地址

        Returns:
            bool: 是否发送成功
        """
        mac = mac_address or self._mac_address
        broadcast = broadcast_ip or self._broadcast_ip

        if not mac:
            logger.error("No MAC address specified")
            return False

        try:
            magic_packet = self._create_magic_packet(mac)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic_packet, (broadcast, self._port))
            sock.close()
            logger.info(f"WOL packet sent to {mac} via {broadcast}")
            self._event_bus.publish(
                DeviceStatusChangedEvent(
                    device="windows", status="waking", source="WoL"
                )
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send WOL packet: {e}")
            return False

    async def check_host_alive(self, host: str, timeout: float = 3.0) -> bool:
        """检查主机是否在线（通过 TCP 连接测试）"""
        try:
            # 尝试连接常见端口
            for port in [22, 80, 445, 3389]:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port),
                        timeout=timeout,
                    )
                    writer.close()
                    await writer.wait_closed()
                    return True
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                    continue
            return False
        except Exception:
            return False

    # --- 内部方法 ---

    @staticmethod
    def _create_magic_packet(mac_address: str) -> bytes:
        """创建 WOL 魔术包

        魔术包格式：6 字节 0xFF + 16 次重复的 MAC 地址
        """
        # 清理 MAC 地址格式
        mac = mac_address.replace(":", "").replace("-", "").replace(".", "").upper()
        if len(mac) != 12:
            raise ValueError(f"Invalid MAC address: {mac_address}")

        mac_bytes = bytes.fromhex(mac)
        magic = b"\xff" * 6 + mac_bytes * 16
        return magic

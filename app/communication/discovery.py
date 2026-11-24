"""TandOrbit 网络自动发现

通过 UDP 广播在同一局域网内发现对方。
"""

from __future__ import annotations

import json
import platform
import socket
import threading
from typing import Any, Callable

from loguru import logger

BROADCAST_PORT = 5002  # UDP 广播端口（与 agent 端口分开）
BROADCAST_INTERVAL = 3  # 秒
BROADCAST_MAGIC = "TandOrbit"


class DiscoveryService:
    """局域网自动发现服务"""

    def __init__(self, local_port: int = 5000, wol_nic: str = "", config_manager: Any = None) -> None:
        self._local_port = local_port
        self._local_host = self._get_local_ip()
        self._local_name = platform.node()
        self._local_role = "mac" if platform.system() == "Darwin" else "windows"
        self._peer: dict[str, Any] | None = None
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._running = False

    @property
    def peer(self) -> dict[str, Any] | None:
        return self._peer

    def on_peer_discovered(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """注册发现对端的回调"""
        self._callbacks.append(callback)

    def start(self) -> None:
        """启动发现服务"""
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run_broadcast, daemon=True).start()
        threading.Thread(target=self._run_listen, daemon=True).start()
        logger.info(f"Discovery service started (role={self._local_role}, ip={self._local_host})")

    def stop(self) -> None:
        self._running = False

    def _get_local_ip(self) -> str:
        """获取本机局域网 IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def _get_local_mac(nic_name: str = "") -> str:
        """获取指定网卡的 MAC 地址，nic_name 为空时自动选择活跃网卡"""
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            if nic_name and nic_name in addrs:
                for snic in addrs[nic_name]:
                    if snic.family.name == "AF_LINK" and snic.address:
                        return snic.address.upper()
            # 未指定或未找到，取当前活跃网卡（与本机 IP 同网卡）
            for name, snics in addrs.items():
                if name.startswith(("lo", "utun", "awdl", "llw", "bridge", "vmenet")):
                    continue
                for snic in snics:
                    if snic.family.name == "AF_LINK" and snic.address:
                        return snic.address.upper()
        except Exception:
            pass
        return ""

    @staticmethod
    def list_nics() -> list[dict[str, str]]:
        """列出所有网卡（名称 + MAC 地址），供 UI 下拉选择"""
        nics = []
        try:
            import psutil
            for name, snics in psutil.net_if_addrs().items():
                if name.startswith(("lo", "utun", "awdl", "llw", "vmenet")):
                    continue
                mac = ""
                for snic in snics:
                    if snic.family.name == "AF_LINK" and snic.address:
                        mac = snic.address.upper()
                        break
                if mac:
                    nics.append({"name": name, "mac": mac})
        except Exception:
            pass
        return nics

    def _make_announcement(self) -> bytes:
        """构建广播消息"""
        msg: dict[str, Any] = {
            "magic": BROADCAST_MAGIC,
            "role": self._local_role,
            "host": self._local_host,
            "port": self._local_port,
            "name": self._local_name,
        }
        return json.dumps(msg).encode()

    def _run_broadcast(self) -> None:
        """定时广播本机信息"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1)
        msg = self._make_announcement()
        while self._running:
            try:
                sock.sendto(msg, ("255.255.255.255", BROADCAST_PORT))
            except Exception:
                pass
            import time
            time.sleep(BROADCAST_INTERVAL)
        sock.close()

    def _run_listen(self) -> None:
        """监听广播消息"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass  # Windows 没有 SO_REUSEPORT
        sock.bind(("0.0.0.0", BROADCAST_PORT))
        sock.settimeout(1)
        while self._running:
            try:
                data, addr = sock.recvfrom(1024)
                self._handle_broadcast(data, addr)
            except socket.timeout:
                continue
            except Exception:
                continue
        sock.close()

    def _handle_broadcast(self, data: bytes, addr: tuple[str, int]) -> None:
        """处理收到的广播"""
        try:
            msg = json.loads(data.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(msg, dict) or msg.get("magic") != BROADCAST_MAGIC:
            return
        role = msg.get("role")
        if role not in ("mac", "windows") or role == self._local_role:
            return
        port = msg.get("port")
        if type(port) is not int or not 1 <= port <= 65535:
            return
        peer = {
            "role": role, "host": addr[0], "port": port,
            "name": str(msg.get("name", ""))[:128],
        }
        if self._peer == peer:
            return
        self._peer = peer
        for callback in self._callbacks:
            try:
                callback(peer)
            except Exception as exc:
                logger.error(f"Discovery callback error: {exc}")

"""Short authentication string for pairing on the local network.

The temporary listener handles only pairing. Controls and sharing still require
the certificates pinned by Pairing and their existing mutually authenticated TLS.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import secrets

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app.communication.discovery import DiscoveryService
from app.communication.pairing import Pairing

_PROTOCOL = 1
_MAX_FRAME = 16 * 1024
_HANDSHAKE_TIMEOUT = 8
_CONFIRM_TIMEOUT = 60
_DOMAIN = b"TandOrbit nearby pairing v1\0"


class PairingError(ValueError):
    pass


def _encode(frame: dict) -> bytes:
    return json.dumps(frame, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _commitment(reveal: dict) -> str:
    return hashlib.sha256(_DOMAIN + b"commit\0" + _encode(reveal)).hexdigest()


async def _send(writer: asyncio.StreamWriter, kind: str, **data) -> None:
    writer.write(_encode({"type": kind, "version": _PROTOCOL, **data}) + b"\n")
    await writer.drain()


async def _read(reader: asyncio.StreamReader, kind: str) -> dict:
    try:
        message = json.loads(await reader.readuntil(b"\n"))
    except asyncio.IncompleteReadError as exc:
        raise PairingError("另一台电脑结束了配对。") from exc
    if not isinstance(message, dict) or message.get("type") != kind or message.get("version") != _PROTOCOL:
        raise PairingError("配对流程不一致。请确认两台电脑使用同一版本。")
    return message


def _signed_message(transcript: bytes, role: str) -> bytes:
    return _DOMAIN + b"accepted\0" + transcript + role.encode("ascii")


class NearbyPairing:
    """One explicitly opened pairing window, with at most one attempt."""

    def __init__(self, pairing: Pairing, discovery: DiscoveryService, control_port: int,
                 mac_address: str, notify) -> None:
        self.pairing = pairing
        self.discovery = discovery
        self.control_port = control_port
        self.mac_address = mac_address
        self.notify = notify
        self._server: asyncio.Server | None = None
        self._task: asyncio.Task | None = None
        self._decision: asyncio.Future | None = None
        self._closed = False
        self._attempted = False

    async def start(self, host: str = "0.0.0.0") -> None:
        if self._closed:
            return
        try:
            server = await asyncio.start_server(self._incoming, host, 0, limit=_MAX_FRAME)
        except OSError:
            self.notify("error", "无法打开局域网配对。可以在设置中手动导入配对信息。")
            return
        if self._closed:
            server.close()
            await server.wait_closed()
            return
        self._server = server
        self.notify("discovery", "")
        self.discovery.advertise_pairing(server.sockets[0].getsockname()[1])

    def _incoming(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._closed or self._attempted:
            writer.close()
            return
        self._attempted = True
        self._task = asyncio.create_task(self._run(reader, writer))

    async def connect(self, host: str, port: int) -> None:
        if self._closed or self._attempted or self._server is None:
            return
        self._attempted = True
        self._task = asyncio.current_task()
        try:
            async with asyncio.timeout(_HANDSHAKE_TIMEOUT):
                reader, writer = await asyncio.open_connection(host, port, limit=_MAX_FRAME)
        except (OSError, TimeoutError):
            self.discovery.advertise_pairing(0)
            self.notify("error", "连不上选中的电脑。请让双方保持配对窗口打开，再试一次。")
        else:
            await self._run(reader, writer)

    async def close(self) -> None:
        self._closed = True
        self.discovery.advertise_pairing(0)
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def decide(self, accepted: bool) -> None:
        if self._decision is not None and not self._decision.done():
            self._decision.set_result(accepted)

    async def _run(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.discovery.advertise_pairing(0)
        self.notify("connecting", "")
        try:
            async with asyncio.timeout(_HANDSHAKE_TIMEOUT):
                offer, name, transcript = await self._exchange(reader, writer)
            code = int.from_bytes(hashlib.sha256(_DOMAIN + b"number\0" + transcript).digest()[:8], "big")
            async with asyncio.timeout(_CONFIRM_TIMEOUT):
                await self._confirm(reader, writer, offer, name, f"{code % 1_000_000:06d}", transcript)
            if not self._closed:
                self.pairing.trust_nearby(offer)
                self.notify("paired", name)
        except PairingError as exc:
            self.notify("error", str(exc))
        except TimeoutError:
            self.notify("error", "配对已超时。请重新打开两台电脑的配对窗口。")
        except (OSError, ValueError, KeyError, TypeError, AttributeError,
                asyncio.LimitOverrunError, InvalidSignature, UnsupportedAlgorithm):
            self.notify("error", "配对未完成。请取消后重新搜索设备。")
        finally:
            writer.close()
            await asyncio.gather(writer.wait_closed(), return_exceptions=True)

    async def _exchange(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        local_address = writer.get_extra_info("sockname")[0]
        remote_address = writer.get_extra_info("peername")[0]
        local = {
            "offer": self.pairing.offer(local_address, self.control_port, self.mac_address),
            "nonce": secrets.token_hex(32),
            "name": platform.node()[:80],
        }
        ours = _commitment(local)
        await _send(writer, "commit", digest=ours)
        theirs = (await _read(reader, "commit"))["digest"]
        if not isinstance(theirs, str) or len(bytes.fromhex(theirs)) != 32 or len(theirs) != 64:
            raise PairingError("收到的配对请求无效。")
        # Neither side discloses its random contribution until both commitments are fixed.
        await _send(writer, "reveal", payload=local)
        remote = (await _read(reader, "reveal"))["payload"]
        if not secrets.compare_digest(_commitment(remote), theirs):
            raise PairingError("设备身份比对失败。请重新选择另一台电脑。")
        if len(bytes.fromhex(remote["nonce"])) != 32:
            raise PairingError("收到的配对请求无效。")
        offer = self.pairing.validate(remote["offer"])
        if offer["host"] != remote_address:
            raise PairingError("发现的设备地址与连接地址不一致。请检查局域网或使用手动配对。")
        current = self.pairing.peer
        if current and current["fingerprint"] != offer["fingerprint"]:
            raise PairingError("本机已配对其他电脑。请先在配对详情中解除配对。")
        # Derive the number from the revealed nonces, which are still secret when
        # each side fixes its commitment. Public commitments alone are insufficient.
        transcript = hashlib.sha256(
            _DOMAIN + b"transcript\0" + _encode({self.pairing.role: local, offer["role"]: remote}),
        ).digest()
        name = str(remote["name"])[:80].strip() or ("Mac" if offer["role"] == "mac" else "Windows")
        return offer, name, transcript

    async def _confirm(self, reader, writer, offer, name, code, transcript) -> None:
        self._decision = asyncio.get_running_loop().create_future()
        self.notify("compare", {"name": name, "number": code})
        remote = asyncio.create_task(_read(reader, "accepted"))
        try:
            done, _ = await asyncio.wait((remote, self._decision), return_when=asyncio.FIRST_COMPLETED)
            if remote in done:
                remote.result()
            if not await self._decision:
                raise PairingError("已取消配对。")
            message = _signed_message(transcript, self.pairing.role)
            await _send(writer, "accepted", signature=self.pairing.sign_confirmation(message).hex())
            signature = bytes.fromhex((await remote)["signature"])
            cert = x509.load_pem_x509_certificate(offer["cert"].encode())
            cert.public_key().verify(signature, _signed_message(transcript, offer["role"]), ec.ECDSA(hashes.SHA256()))
        finally:
            remote.cancel()
            await asyncio.gather(remote, return_exceptions=True)
            self._decision = None

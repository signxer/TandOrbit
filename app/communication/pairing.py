"""Local device identity and peer trust for HTTPS and input sharing."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def _save(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


class Pairing:
    def __init__(self, directory: Path, role: str) -> None:
        self.identity = directory / "identity.pem"
        self.peer_path = directory / "paired-peer.json"
        self.role = role
        self._lock = RLock()

    def _local_cert(self) -> x509.Certificate:
        if self.identity.exists():
            cert_pem = self.identity.read_bytes().split(b"-----END CERTIFICATE-----")[0]
            return x509.load_pem_x509_certificate(cert_pem + b"-----END CERTIFICATE-----\n")
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"TandOrbit {self.role}")])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        _save(self.identity, cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        return cert

    @property
    def peer(self) -> dict | None:
        with self._lock:
            try:
                return json.loads(self.peer_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None

    def offer(self, host: str, port: int, mac_address: str = "") -> dict:
        cert = self._local_cert()
        return {"version": 1, "role": self.role, "host": host, "port": port,
                "mac_address": mac_address, "cert": cert.public_bytes(serialization.Encoding.PEM).decode(),
                "fingerprint": self.fingerprint(cert)}

    @staticmethod
    def fingerprint(cert) -> str:
        return cert.fingerprint(hashes.SHA256()).hex(":").upper()

    def validate(self, data: dict) -> dict:
        if data["version"] != 1 or data["role"] != {"mac": "windows", "windows": "mac"}[self.role]:
            raise ValueError("配对信息必须来自另一台电脑")
        host = str(data["host"]).strip()
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}", host):
            raise ValueError("主机地址无效")
        if ":" in host:
            ipaddress.IPv6Address(host)
        port = int(data["port"])
        if not 1 <= port <= 65535:
            raise ValueError("监听端口无效")
        cert = x509.load_pem_x509_certificate(data["cert"].encode())
        cert.verify_directly_issued_by(cert)
        now = datetime.now(timezone.utc)
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError("对端证书已过期或尚未生效")
        fingerprint = self.fingerprint(cert)
        if data["fingerprint"] != fingerprint or fingerprint == self.fingerprint(self._local_cert()):
            raise ValueError("配对指纹无效")
        mac = str(data.get("mac_address", ""))
        if mac and not re.fullmatch(r"[a-fA-F0-9]{2}([:-][a-fA-F0-9]{2}){5}", mac):
            raise ValueError("MAC 地址无效")
        return {"version": 1, "role": data["role"], "host": host, "port": port,
                "mac_address": mac, "cert": cert.public_bytes(serialization.Encoding.PEM).decode(),
                "fingerprint": fingerprint}

    def trust(self, offer: dict) -> None:
        with self._lock:
            _save(self.peer_path, json.dumps(self.validate(offer)).encode())

    def revoke(self) -> None:
        with self._lock:
            self.peer_path.unlink(missing_ok=True)

    def update_address(self, fingerprint: str, host: str, port: int) -> bool:
        with self._lock:
            peer = self.peer
            if not peer or peer["fingerprint"] != fingerprint:
                return False
            _save(self.peer_path, json.dumps({**peer, "host": host, "port": port}).encode())
            return True

    def context(self, *, server: bool = False, peer: dict | None = None) -> ssl.SSLContext | None:
        peer = peer or self.peer
        if not peer:
            return None
        self._local_cert()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # A single pinned, self-signed peer leaf is the only trust anchor.
        # The LAN address can change independently of the peer's identity.
        if not server:
            context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cadata=peer["cert"])
        context.load_cert_chain(self.identity)
        return context

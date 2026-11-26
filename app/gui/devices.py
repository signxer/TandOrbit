"""Presentation identity for the local device and its paired peer."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import DeviceAppearance

PLATFORM_NAME = {"mac": "Mac", "windows": "Windows"}
PLATFORM_GLYPH = {"mac": "laptop", "windows": "tower"}
LOCAL_DEVICE_KEY = "local"
GLYPH_OPTIONS = (
    ("auto", "自动"),
    ("laptop", "笔记本"),
    ("desktop", "显示器"),
    ("mini", "迷你主机"),
    ("tower", "塔式主机"),
)


@dataclass(frozen=True)
class DeviceView:
    key: str | None
    platform: str
    appearance: DeviceAppearance

    @property
    def is_local(self) -> bool:
        return self.key == LOCAL_DEVICE_KEY

    @property
    def name(self) -> str:
        return self.appearance.name.strip() or PLATFORM_NAME[self.platform]

    @property
    def glyph(self) -> str:
        return PLATFORM_GLYPH[self.platform] if self.appearance.glyph == "auto" else self.appearance.glyph


def devices_for(appearances: dict[str, DeviceAppearance], local_platform: str,
                peer: dict | None = None) -> tuple[DeviceView, DeviceView]:
    other_platform = "windows" if local_platform == "mac" else "mac"
    fingerprint = peer["fingerprint"] if peer else None
    return (
        DeviceView(LOCAL_DEVICE_KEY, local_platform, appearances.get(LOCAL_DEVICE_KEY, DeviceAppearance())),
        DeviceView(fingerprint, peer.get("role", other_platform) if peer else other_platform,
                   appearances.get(fingerprint, DeviceAppearance()) if fingerprint else DeviceAppearance()),
    )

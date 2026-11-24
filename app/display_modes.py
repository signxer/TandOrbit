"""One local display executor for both initiators and both desktop platforms."""
from __future__ import annotations

import asyncio
import re
from typing import Any

from app.enums import Mode
from app.transition import TransitionError


class DisplayModes:
    def __init__(self, role, config, display, power) -> None:
        self.role = role
        self.config = config
        self.display = display
        self.power = power

    @staticmethod
    def _resolve(displays, identity, fallback):
        if identity:
            key = identity.casefold()
            exact = [item for item in displays if key in
                     {item.device_id.casefold(), item.monitor_id.casefold()}]
            matches = exact or [item for item in displays if
                                key in item.monitor_id.casefold()]
            if not matches:
                legacy = re.match(r"^monitor\\([^\\]+)", key)
                if legacy:
                    model = legacy[1]
                    matches = [item for item in displays if f"display#{model}#" in item.device_id.casefold()]
        else:
            matches = [item for item in displays if item.id == fallback]
        if len(matches) != 1:
            raise TransitionError(f"显示器绑定缺失或重复，请在设置中重新确认：{identity or fallback}")
        return matches[0]

    async def snapshot(self, mode: Mode, share_role: str) -> dict:
        config = self.config.config.display
        if not self.display:
            raise TransitionError("本机显示器后端不可用")
        displays = await self.display.list_displays()
        prefix = "mac" if self.role == "mac" else "windows"
        primary = self._resolve(displays, getattr(config, f"{prefix}_primary_monitor_id"),
                                config.primary_id)
        secondary = self._resolve(displays, getattr(config, f"{prefix}_secondary_monitor_id"),
                                  config.secondary_id)
        if primary.id == secondary.id:
            raise TransitionError("主屏和副屏绑定到了同一个输出")
        if not share_role:
            share_role = "primary" if config.share_display_id == config.primary_id else "secondary"
        if share_role not in ("primary", "secondary"):
            raise TransitionError("共享屏角色无效")
        targets = dict(primary=primary.model_dump(mode="json"),
                       secondary=secondary.model_dump(mode="json"))
        desired = self.desired(mode, share_role)
        if any(targets[key]["is_enabled"] != enabled for key, enabled in desired.items()):
            if not getattr(self.display, "can_change_outputs", True):
                raise TransitionError("单屏断开与重连需要可用的 BetterDisplay 兼容后端")
        power = await self.power.read()
        if power is None:
            raise TransitionError("系统尚未报告显示器电源状态")
        native = await self.display.capture_topology() if hasattr(self.display, "capture_topology") else None
        arrangement = await self.display.capture_arrangement() if hasattr(self.display, "capture_arrangement") else None
        mirrored = await self.display.is_mirrored() if hasattr(self.display, "is_mirrored") else False
        return {"targets": targets, "power": power, "native": native, "arrangement": arrangement,
                "mirrored": mirrored, "share_role": share_role}

    def desired(self, mode, share_role) -> dict[str, bool]:
        if mode == Mode.SHARE:
            return {role: (role == share_role) == (self.role == "windows")
                    for role in ("primary", "secondary")}
        owner = "mac" if mode == Mode.MAC else "windows"
        return {"primary": True, "secondary": True} if self.role == owner else {}

    async def _set_outputs(self, snapshot, desired) -> None:
        if not desired:
            return
        displays = await self.display.list_displays()
        for key, enabled in desired.items():
            target = snapshot["targets"][key]
            identity = target["device_id"] or target["monitor_id"]
            monitor = self._resolve(displays, identity, target["id"])
            if monitor.is_enabled != enabled:
                change = self.display.enable_display if enabled else self.display.disable_display
                if not await change(monitor.id):
                    raise TransitionError(f"无法{'启用' if enabled else '释放'}显示器：{monitor.name}")
                displays = await self.display.list_displays()

    async def _verify(self, snapshot, desired, power, *, mirrored=False) -> None:
        for _ in range(16):
            try:
                displays = await self.display.list_displays() if desired else []
                observed = {}
                for key in desired:
                    item = snapshot["targets"][key]
                    identity = item["device_id"] or item["monitor_id"]
                    observed[key] = self._resolve(displays, identity, item["id"]).is_enabled
                matches = observed == desired and await self.power.read() == power
                if matches and all(desired.values()) and len(desired) == 2:
                    matches = (await self.display.is_mirrored()) == mirrored if (
                        hasattr(self.display, "is_mirrored")) else True
                if matches:
                    return
            except TransitionError:
                pass
            await asyncio.sleep(0.25)
        raise TransitionError(f"{self.role} 显示输出或电源状态未达到目标")

    async def apply(self, mode, phase, snapshot) -> None:
        desired = self.desired(mode, snapshot["share_role"])
        if phase == "activate" and desired:
            targets = {key: True for key, enabled in desired.items() if enabled}
            await self._set_outputs(snapshot, targets)
            if len(targets) == 2 and hasattr(self.display, "is_mirrored"):
                if await self.display.is_mirrored() and not await self.display.set_extend():
                    raise TransitionError("无法设置双屏扩展")
            await self.power.set(True)
            await self._verify(snapshot, targets, True)
        if phase == "release":
            if desired:
                await self._set_outputs(snapshot, {key: False for key, enabled in desired.items() if not enabled})
            else:
                await self.power.set(False)
        if phase == "verify":
            await self._verify(snapshot, desired, bool(desired))

    async def restore(self, snapshot: dict[str, Any]) -> None:
        if snapshot["native"] is not None:
            await self.display.apply_topology(snapshot["native"])
        else:
            desired = {key: item["is_enabled"] for key, item in snapshot["targets"].items()}
            await self._set_outputs(snapshot, {key: value for key, value in desired.items() if value})
            await self._set_outputs(snapshot, {key: value for key, value in desired.items() if not value})
            if snapshot.get("arrangement") is not None:
                await self.display.apply_arrangement(snapshot["arrangement"])
        await self.power.set(snapshot["power"])
        await self._verify(snapshot, {key: item["is_enabled"] for key, item in snapshot["targets"].items()},
                           snapshot["power"], mirrored=snapshot.get("mirrored", False))

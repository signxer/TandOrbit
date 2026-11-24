"""Durable coordinator and participant for the two-computer display switch."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from app.enums import Mode

MODES = frozenset(("MAC", "WINDOWS", "SHARE"))
DONE = frozenset(("committed", "restored", "failed"))
STAGES = ("prepare", "activate", "release", "verify", "commit")


class TransitionError(RuntimeError):
    pass


class TransitionJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS transitions (
                role TEXT NOT NULL, id TEXT NOT NULL, value TEXT NOT NULL,
                changed REAL NOT NULL, PRIMARY KEY(role, id))"""
        )
        return conn

    def put(self, role: str, operation: dict[str, Any]) -> None:
        from contextlib import closing
        with closing(self._open()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO transitions VALUES (?, ?, ?, ?)",
                (role, operation["id"], json.dumps(operation), time.time()),
            )

    def get(self, role: str, operation_id: str) -> dict | None:
        from contextlib import closing
        with closing(self._open()) as conn:
            row = conn.execute(
                "SELECT value FROM transitions WHERE role=? AND id=?", (role, operation_id)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def pending(self, role: str) -> list[dict]:
        from contextlib import closing
        with closing(self._open()) as conn:
            rows = conn.execute(
                "SELECT value FROM transitions WHERE role=? ORDER BY changed", (role,)
            ).fetchall()
        return [record for (value,) in rows if (record := json.loads(value))["phase"] not in DONE]

    def last_commit(self, role: str) -> dict | None:
        from contextlib import closing
        with closing(self._open()) as conn, conn:
            row = conn.execute(
                """SELECT value FROM transitions WHERE role=?
                   AND json_extract(value, '$.phase') = 'committed' ORDER BY changed DESC LIMIT 1""",
                (role,),
            ).fetchone()
        return json.loads(row[0]) if row else None


def public_status(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "snapshot"}


class LocalParticipant:
    def __init__(self, journal, output, state, config, on_commit=None) -> None:
        self.journal = journal
        self.output = output
        self.state = state
        self.config = config
        self.on_commit = on_commit
        self._lock = asyncio.Lock()

    async def step(self, operation_id: str, mode: str, phase: str, share_role: str = "") -> dict:
        if mode not in MODES or phase not in (*STAGES, "restore", "status", "observe"):
            raise TransitionError("无效的模式或切换阶段")
        async with self._lock:
            return await self._step(operation_id, mode, phase, share_role)

    async def _step(self, operation_id: str, mode: str, phase: str, share_role: str) -> dict:
        record = self.journal.get("local", operation_id)
        if phase == "status":
            if record is None:
                return {"id": operation_id, "phase": "missing"}
            return public_status(record)
        if record is None:
            if phase == "restore":
                # Tombstone prevents a delayed prepare starting an already aborted operation.
                record = {"id": operation_id, "target": mode, "phase": "restored"}
                self.journal.put("local", record)
                return record
            if phase != "prepare" or self.journal.pending("local"):
                raise TransitionError("本机有尚未处理完的切换")
            snapshot = await self.output.snapshot(Mode[mode], share_role)
            record = {
                "id": operation_id, "target": mode, "phase": "prepare", "snapshot": snapshot,
                "from": self.state.current_mode.name, "share_role": snapshot.get("share_role", share_role),
                "started": time.time(),
            }
            self.journal.put("local", record)
            return public_status(record)

        current = record["phase"]
        if record["target"] != mode:
            raise TransitionError("操作 ID 已绑定其他模式")
        if current == "committed":
            if phase == "restore":
                raise TransitionError("此操作已有提交决定")
            if phase == "observe":
                await self.output.apply(Mode[mode], "verify", record["snapshot"])
            return public_status(record)
        if current == "restored":
            if phase != "restore":
                raise TransitionError("此操作已撤销")
            return public_status(record)
        if phase == "restore":
            await self.output.restore(record["snapshot"])
            record["phase"] = "restored"
        elif phase == "observe":
            raise TransitionError("切换尚未提交")
        elif STAGES.index(phase) <= STAGES.index(current):
            return public_status(record)
        elif STAGES.index(phase) != STAGES.index(current) + 1:
            raise TransitionError("切换阶段不连续")
        elif phase == "commit":
            self.config.update({"last_mode": mode})
            record["phase"] = "committed"
        else:
            await self.output.apply(Mode[mode], phase, record["snapshot"])
            record["phase"] = phase
        self.journal.put("local", record)
        if record["phase"] == "committed":
            self.state.force_set(Mode[mode])
            if self.on_commit:
                warning = await self.on_commit(Mode[mode])
                if warning:
                    record["warning"] = warning
                    self.journal.put("local", record)
        return public_status(record)


class ModeCoordinator:
    def __init__(self, journal, participant, peer, notify, history, identity=None) -> None:
        self.journal = journal
        self.participant = participant
        self.peer = peer
        self.notify = notify
        self.history = history
        self.identity = identity
        self._active: dict | None = None
        self._queued: dict | None = None
        self._task: asyncio.Task | None = None
        self._recovery_lock = asyncio.Lock()

    def status(self, operation_id: str) -> dict | None:
        alias = self.journal.get("coalesced", operation_id)
        return self.journal.get("coordinator", alias["operation"] if alias else operation_id)

    def submit(self, mode: str, operation_id: str | None = None) -> dict:
        if mode not in MODES:
            raise TransitionError("无效的目标模式")
        if operation_id and (record := self.status(operation_id)):
            if record["target"] != mode:
                raise TransitionError("操作 ID 已绑定其他模式")
            return record
        if self._recovery_lock.locked():
            raise TransitionError("正在恢复显示器，请稍后再试")
        if self._active is None and self.journal.pending("coordinator"):
            raise TransitionError("上次切换待恢复")
        for record in (self._active, self._queued):
            if record and record["target"] == mode:
                if operation_id and operation_id != record["id"]:
                    self.journal.put("coalesced", {"id": operation_id, "operation": record["id"]})
                return record.copy()
        if self._queued:
            raise TransitionError("已有一个切换排队")
        record = {
            "id": operation_id or uuid4().hex, "target": mode, "phase": "queued",
            "started": time.time(), "share_role": "",
        }
        if self.identity is not None:
            record["peer"] = self.identity()
        if self._active is None and self.participant.state.current_mode.name == mode:
            record["phase"] = "committed"
            self.journal.put("coordinator", record)
            return record.copy()
        self.journal.put("coordinator", record)
        if self._active is None:
            self._active = record
            self._task = asyncio.create_task(self._drain())
        else:
            self._queued = record
        return record.copy()

    def _set(self, record: dict, phase: str, **updates) -> None:
        next_record = {**record, **updates, "phase": phase}
        self.journal.put("coordinator", next_record)
        record.update(next_record)
        self.notify(record.copy())

    async def _drain(self) -> None:
        while self._active:
            record = self._active
            try:
                await self._execute(record)
            except Exception:
                logger.exception("切换协调器异常")
            finally:
                if record["phase"] not in DONE and self._queued:
                    self._set(self._queued, "failed", error="前一请求待恢复")
                    self._queued = None
                self._active, self._queued = self._queued, None

    async def _execute(self, record: dict) -> None:
        record["from"] = self.participant.state.current_mode.name
        try:
            self._set(record, "prepare")
            local = await self.participant.step(record["id"], record["target"], "prepare")
            record["share_role"] = local.get("share_role", "")
            await self.peer(record, "prepare")
            for phase in ("activate", "release", "verify"):
                self._set(record, phase)
                await self.participant.step(record["id"], record["target"], phase)
                await self.peer(record, phase)
            self._set(record, "decision_commit")
        except Exception as exc:
            record["failed_phase"] = record["phase"]
            await self._recover_record(record, str(exc))
        else:
            await self._complete_commit(record)
        self.history(record)

    async def _complete_commit(self, record: dict) -> None:
        try:
            remote = await self.peer(record, "commit")
            local = await self.participant.step(record["id"], record["target"], "commit")
        except Exception as exc:
            self._set(record, "decision_commit", error=f"等待确认提交：{exc}")
        else:
            warnings = [f"{name}：{result['warning']}"
                        for name, result in (("Mac", local), ("Windows", remote))
                        if result.get("warning")]
            self._set(record, "committed", error="", warning=" · ".join(warnings))

    async def _recover_record(self, record: dict, error: str) -> None:
        local_changed = record.get("failed_phase", record["phase"]) != "prepare"
        self._set(record, "recovering", error=error)
        # Before release, restoring either side is safe. Afterwards wake the old owner first.
        prior = self.journal.get("local", record["id"])
        local_power = (prior or {}).get("snapshot", {}).get("power")
        peer_first = record.get("from") == "WINDOWS" or local_power is False
        calls = (self.peer, self._restore_local) if peer_first else (self._restore_local, self.peer)
        failures = []
        for call in calls:
            try:
                await call(record, "restore")
            except Exception as exc:
                failures.append(str(exc))
                if local_changed:
                    break
        if failures:
            self._set(record, "recovering", error=f"{error} · {' / '.join(failures)}")
        else:
            self._set(record, "restored", error=error)

    async def _restore_local(self, record: dict, phase: str) -> dict:
        return await self.participant.step(record["id"], record["target"], phase)

    async def recover(self) -> None:
        if self._active or self._recovery_lock.locked():
            return
        async with self._recovery_lock:
            for record in self.journal.pending("coordinator"):
                if record["phase"] == "decision_commit":
                    await self._complete_commit(record)
                elif record["phase"] == "queued":
                    self._set(record, "failed", error="应用重启，排队请求已结束")
                else:
                    await self._recover_record(record, record.get("error", "切换中断"))
                if record["phase"] in DONE:
                    self.history(record)

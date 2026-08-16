"""切换历史持久化（SQLite，重启不丢）"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class SwitchHistoryStore:
    """切换历史存储：SQLite 持久化 + 内存缓存（最近 cache_limit 条，最新在前）"""

    def __init__(self, db_path: str | Path, cache_limit: int = 100) -> None:
        self._db_path = Path(db_path)
        self._cache_limit = cache_limit
        self._cache: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._init_db()
        self._load_cache()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS switch_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT NOT NULL,
                    from_mode TEXT NOT NULL,
                    to_mode TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT ''
                )"""
            )

    def record(self, entry: dict[str, Any]) -> None:
        """记录一次切换（写库 + 更新内存缓存）"""
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO switch_history (time, from_mode, to_mode, success, duration_ms, error)"
                    " VALUES (?,?,?,?,?,?)",
                    (
                        entry.get("time", ""),
                        entry.get("from", ""),
                        entry.get("to", ""),
                        1 if entry.get("success") else 0,
                        int(entry.get("duration_ms", 0)),
                        entry.get("error", ""),
                    ),
                )
            self._cache.insert(0, dict(entry))
            if len(self._cache) > self._cache_limit:
                self._cache.pop()

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """最近 limit 条切换记录（最新在前）"""
        if limit <= self._cache_limit:
            with self._lock:
                return [dict(e) for e in self._cache[:limit]]
        return self._query_recent(limit)

    def success_rate(self, window: int = 20) -> tuple[int, int, float]:
        """近 window 次切换的成功率：返回 (成功数, 总数, 成功率)"""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT success FROM switch_history ORDER BY id DESC LIMIT ?",
                (window,),
            )
            rows = [int(r[0]) for r in cur.fetchall()]
        total = len(rows)
        if total == 0:
            return 0, 0, 0.0
        ok = sum(rows)
        return ok, total, ok / total

    def clear(self) -> None:
        """清空历史（测试/管理用）"""
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM switch_history")
            self._cache.clear()

    def _query_recent(self, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT time, from_mode, to_mode, success, duration_ms, error"
                " FROM switch_history ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            for r in cur.fetchall():
                rows.append(
                    {
                        "time": r[0],
                        "from": r[1],
                        "to": r[2],
                        "success": bool(r[3]),
                        "duration_ms": r[4],
                        "error": r[5],
                    }
                )
        return rows

    def _load_cache(self) -> None:
        try:
            with self._lock:
                self._cache = self._query_recent(self._cache_limit)
        except Exception:
            self._cache = []

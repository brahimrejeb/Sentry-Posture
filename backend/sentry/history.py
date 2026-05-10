"""SQLite-backed posture history.

We persist a few things:

* **sessions** — when monitoring is on
* **breaks** — periods the user is away from the desk (tracker PAUSED)
* **alerts** — slouch and stand-up notifications fired
* **posture_minutes** — one aggregate row per minute of LOCKED time

Per-second resolution would be ~31M rows/year and isn't useful for
charts. The minute aggregate is built in memory and flushed at most once
per minute, so the SQLite write rate is negligible.

The store is a thin functional layer; ``HistoryStore`` is the entry
point. Tests use ``:memory:`` to get an isolated DB.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import SENTRY_HOME

DEFAULT_DB_PATH = SENTRY_HOME / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    started_at  REAL NOT NULL,
    ended_at    REAL
);

CREATE TABLE IF NOT EXISTS breaks (
    id          INTEGER PRIMARY KEY,
    started_at  REAL NOT NULL,
    ended_at    REAL,
    seconds     REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY,
    fired_at    REAL NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'slouch'
);

CREATE TABLE IF NOT EXISTS posture_minutes (
    minute_ts        INTEGER PRIMARY KEY,
    locked_seconds   REAL NOT NULL,
    slouch_seconds   REAL NOT NULL,
    avg_cva          REAL,
    avg_deviation    REAL
);

CREATE INDEX IF NOT EXISTS idx_breaks_started ON breaks(started_at);
CREATE INDEX IF NOT EXISTS idx_alerts_fired ON alerts(fired_at);
"""


def _minute_floor(ts: float) -> int:
    return int(ts // 60) * 60


@dataclass
class _MinuteBucket:
    """In-memory accumulator for the current minute of LOCKED time."""

    minute_ts: int
    locked_seconds: float = 0.0
    slouch_seconds: float = 0.0
    cva_sum: float = 0.0
    cva_n: int = 0
    deviation_sum: float = 0.0
    deviation_n: int = 0

    def avg_cva(self) -> float | None:
        return self.cva_sum / self.cva_n if self.cva_n else None

    def avg_deviation(self) -> float | None:
        return self.deviation_sum / self.deviation_n if self.deviation_n else None


@dataclass
class HistoryStore:
    """Thin wrapper around a single SQLite connection.

    Designed for a single writer (the monitor loop) plus occasional API
    readers; ``check_same_thread=False`` and an internal lock keep us
    safe.
    """

    db_path: Path | str = DEFAULT_DB_PATH
    _conn: sqlite3.Connection = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _bucket: _MinuteBucket | None = field(default=None, init=False)
    _open_session_id: int | None = field(default=None, init=False)
    _open_break_id: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        # Recover dangling sessions/breaks from a previous crash by closing
        # them at the recorded timestamp. We don't try to be clever here.
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = started_at WHERE ended_at IS NULL"
            )
            self._conn.execute(
                "UPDATE breaks SET ended_at = started_at, seconds = 0 WHERE ended_at IS NULL"
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Recording
    def start_session(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions(started_at) VALUES (?)", (now,)
            )
            self._conn.commit()
            self._open_session_id = cur.lastrowid
            return self._open_session_id  # type: ignore[return-value]

    def end_session(self, now: float | None = None) -> None:
        if self._open_session_id is None:
            return
        now = time.time() if now is None else now
        self.flush()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (now, self._open_session_id),
            )
            self._conn.commit()
            self._open_session_id = None

    def start_break(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO breaks(started_at) VALUES (?)", (now,)
            )
            self._conn.commit()
            self._open_break_id = cur.lastrowid
            return self._open_break_id  # type: ignore[return-value]

    def end_break(self, now: float | None = None) -> None:
        if self._open_break_id is None:
            return
        now = time.time() if now is None else now
        with self._lock:
            row = self._conn.execute(
                "SELECT started_at FROM breaks WHERE id = ?", (self._open_break_id,)
            ).fetchone()
            if row is None:
                self._open_break_id = None
                return
            seconds = max(0.0, now - row["started_at"])
            self._conn.execute(
                "UPDATE breaks SET ended_at = ?, seconds = ? WHERE id = ?",
                (now, seconds, self._open_break_id),
            )
            self._conn.commit()
            self._open_break_id = None

    def record_alert(self, kind: str = "slouch", now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._conn.execute(
                "INSERT INTO alerts(fired_at, kind) VALUES (?, ?)", (now, kind)
            )
            self._conn.commit()

    def record_sample(
        self,
        *,
        is_locked: bool,
        is_slouching: bool,
        cva: float | None,
        deviation: float | None,
        dt_seconds: float,
        now: float | None = None,
    ) -> None:
        """Add one observation to the current minute bucket."""
        if not is_locked or dt_seconds <= 0:
            return
        now = time.time() if now is None else now
        minute = _minute_floor(now)
        if self._bucket is None or self._bucket.minute_ts != minute:
            if self._bucket is not None:
                self._flush_bucket(self._bucket)
            self._bucket = _MinuteBucket(minute_ts=minute)
        self._bucket.locked_seconds += dt_seconds
        if is_slouching:
            self._bucket.slouch_seconds += dt_seconds
        if cva is not None:
            self._bucket.cva_sum += cva
            self._bucket.cva_n += 1
        if deviation is not None:
            self._bucket.deviation_sum += deviation
            self._bucket.deviation_n += 1

    def flush(self) -> None:
        if self._bucket is None:
            return
        self._flush_bucket(self._bucket)
        self._bucket = None

    def _flush_bucket(self, bucket: _MinuteBucket) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO posture_minutes(
                    minute_ts, locked_seconds, slouch_seconds, avg_cva, avg_deviation
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(minute_ts) DO UPDATE SET
                    locked_seconds = locked_seconds + excluded.locked_seconds,
                    slouch_seconds = slouch_seconds + excluded.slouch_seconds,
                    avg_cva =
                        CASE
                            WHEN excluded.avg_cva IS NULL THEN avg_cva
                            WHEN avg_cva IS NULL THEN excluded.avg_cva
                            ELSE (avg_cva + excluded.avg_cva) / 2
                        END,
                    avg_deviation =
                        CASE
                            WHEN excluded.avg_deviation IS NULL THEN avg_deviation
                            WHEN avg_deviation IS NULL THEN excluded.avg_deviation
                            ELSE (avg_deviation + excluded.avg_deviation) / 2
                        END
                """,
                (
                    bucket.minute_ts,
                    bucket.locked_seconds,
                    bucket.slouch_seconds,
                    bucket.avg_cva(),
                    bucket.avg_deviation(),
                ),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Maintenance
    def clear(self) -> None:
        with self._lock:
            self._conn.executescript(
                "DELETE FROM sessions; DELETE FROM breaks; DELETE FROM alerts; DELETE FROM posture_minutes;"
            )
            self._conn.commit()
        self._bucket = None
        self._open_session_id = None
        self._open_break_id = None

    def close(self) -> None:
        self.flush()
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Queries — all return plain dicts so the API layer can wrap them.
    def day(self, target: date) -> dict:
        start = _start_of_day(target)
        end = start + 86400
        return self._range_buckets_by_hour(start, end, target.isoformat())

    def week(self, end_day: date) -> dict:
        days = [end_day - timedelta(days=i) for i in range(6, -1, -1)]
        return {"days": [self._day_summary(d) for d in days]}

    def month(self, end_day: date, days: int = 30) -> dict:
        seq = [end_day - timedelta(days=i) for i in range(days - 1, -1, -1)]
        return {"days": [self._day_summary(d) for d in seq]}

    def year(self, end_day: date) -> dict:
        seq = [end_day - timedelta(days=i) for i in range(364, -1, -1)]
        return {"days": [self._day_summary(d) for d in seq]}

    def streaks(self, today: date, slouch_goal_pct: float, breaks_goal: int) -> dict:
        return {
            "good_posture_days": self._streak(
                today, lambda s: s["slouch_pct"] <= slouch_goal_pct
            ),
            "break_goal_days": self._streak(
                today, lambda s: s["breaks"] >= breaks_goal
            ),
        }

    def _streak(self, today: date, ok: Callable[[dict], bool]) -> int:
        """Walk backwards from ``today`` counting consecutive days where ``ok`` holds.

        Days with no recorded data don't break the streak when they fall on
        ``today`` (the user just hasn't been at their desk yet) but do
        break it any earlier — we don't reward absence.
        """
        count = 0
        cur = today
        for _ in range(365):
            summary = self._day_summary(cur)
            if summary["locked_seconds"] <= 0:
                if cur == today:
                    cur -= timedelta(days=1)
                    continue
                break
            if not ok(summary):
                break
            count += 1
            cur -= timedelta(days=1)
        return count

    # ------------------------------------------------------------------
    def _range_buckets_by_hour(self, start_ts: float, end_ts: float, day_iso: str) -> dict:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT minute_ts, locked_seconds, slouch_seconds
                FROM posture_minutes
                WHERE minute_ts >= ? AND minute_ts < ?
                """,
                (int(start_ts), int(end_ts)),
            ).fetchall()
            break_rows = self._conn.execute(
                "SELECT started_at, ended_at FROM breaks WHERE started_at < ? AND COALESCE(ended_at, started_at) >= ?",
                (end_ts, start_ts),
            ).fetchall()
            alert_count = self._conn.execute(
                "SELECT COUNT(*) AS n FROM alerts WHERE fired_at >= ? AND fired_at < ?",
                (start_ts, end_ts),
            ).fetchone()["n"]

        hours = [
            {"hour": h, "locked_seconds": 0.0, "slouch_seconds": 0.0, "breaks": 0}
            for h in range(24)
        ]
        locked_total = 0.0
        slouch_total = 0.0
        for r in rows:
            h = (int(r["minute_ts"]) - int(start_ts)) // 3600
            if 0 <= h < 24:
                hours[h]["locked_seconds"] += r["locked_seconds"]
                hours[h]["slouch_seconds"] += r["slouch_seconds"]
                locked_total += r["locked_seconds"]
                slouch_total += r["slouch_seconds"]

        breaks_count = 0
        for b in break_rows:
            ended = b["ended_at"] if b["ended_at"] is not None else end_ts
            mid = (max(b["started_at"], start_ts) + min(ended, end_ts)) / 2
            h = int((mid - start_ts) // 3600)
            if 0 <= h < 24:
                hours[h]["breaks"] += 1
                breaks_count += 1

        longest = self._longest_uninterrupted(start_ts, end_ts)
        slouch_pct = (slouch_total / locked_total) if locked_total > 0 else 0.0
        return {
            "date": day_iso,
            "buckets": hours,
            "totals": {
                "locked_seconds": locked_total,
                "slouch_seconds": slouch_total,
                "breaks": breaks_count,
                "alerts": int(alert_count),
                "longest_uninterrupted_seconds": longest,
                "slouch_pct": slouch_pct,
            },
        }

    def _day_summary(self, target: date) -> dict:
        start = _start_of_day(target)
        end = start + 86400
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COALESCE(SUM(locked_seconds), 0) AS locked,
                    COALESCE(SUM(slouch_seconds), 0) AS slouch
                FROM posture_minutes
                WHERE minute_ts >= ? AND minute_ts < ?
                """,
                (int(start), int(end)),
            ).fetchone()
            breaks = self._conn.execute(
                "SELECT COUNT(*) AS n FROM breaks WHERE started_at >= ? AND started_at < ?",
                (start, end),
            ).fetchone()["n"]
            alerts = self._conn.execute(
                "SELECT COUNT(*) AS n FROM alerts WHERE fired_at >= ? AND fired_at < ?",
                (start, end),
            ).fetchone()["n"]
        locked = float(row["locked"]) if row else 0.0
        slouch = float(row["slouch"]) if row else 0.0
        return {
            "date": target.isoformat(),
            "locked_seconds": locked,
            "slouch_seconds": slouch,
            "breaks": int(breaks),
            "alerts": int(alerts),
            "slouch_pct": (slouch / locked) if locked > 0 else 0.0,
        }

    def _longest_uninterrupted(self, start_ts: float, end_ts: float) -> float:
        """Longest consecutive run of LOCKED minutes within the range."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT minute_ts, locked_seconds
                FROM posture_minutes
                WHERE minute_ts >= ? AND minute_ts < ? AND locked_seconds > 0
                ORDER BY minute_ts
                """,
                (int(start_ts), int(end_ts)),
            ).fetchall()
        if not rows:
            return 0.0
        best = 0.0
        run = 0.0
        prev_minute: int | None = None
        for r in rows:
            m = int(r["minute_ts"])
            if prev_minute is not None and m - prev_minute <= 60:
                run += r["locked_seconds"]
            else:
                run = r["locked_seconds"]
            best = max(best, run)
            prev_minute = m
        return best


def _start_of_day(target: date) -> float:
    """Local-midnight as a unix timestamp."""
    dt = datetime(target.year, target.month, target.day)
    return dt.timestamp()


__all__ = ["DEFAULT_DB_PATH", "HistoryStore"]

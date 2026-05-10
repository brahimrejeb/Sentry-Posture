"""Unit tests for the history store. Uses :memory: SQLite for isolation."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sentry.history import HistoryStore


@pytest.fixture
def store() -> HistoryStore:
    s = HistoryStore(db_path=":memory:")
    yield s
    s.close()


def _midnight(d: date) -> float:
    return datetime(d.year, d.month, d.day).timestamp()


def test_session_lifecycle(store: HistoryStore) -> None:
    store.start_session(now=1000.0)
    store.end_session(now=1500.0)
    rows = store._conn.execute("SELECT started_at, ended_at FROM sessions").fetchall()
    assert len(rows) == 1
    assert rows[0]["started_at"] == 1000.0
    assert rows[0]["ended_at"] == 1500.0


def test_break_lifecycle_records_seconds(store: HistoryStore) -> None:
    store.start_break(now=2000.0)
    store.end_break(now=2090.0)
    row = store._conn.execute(
        "SELECT seconds, ended_at FROM breaks WHERE id = ?", (1,)
    ).fetchone()
    assert row["seconds"] == 90.0
    assert row["ended_at"] == 2090.0


def test_minute_bucket_aggregates_until_flush(store: HistoryStore) -> None:
    today = date.today()
    base = _midnight(today) + 9 * 3600  # 9 AM today
    # 30 seconds locked, 10 of which slouching
    for i in range(30):
        store.record_sample(
            is_locked=True,
            is_slouching=i < 10,
            cva=60.0,
            deviation=5.0,
            dt_seconds=1.0,
            now=base + i,
        )
    store.flush()
    row = store._conn.execute(
        "SELECT locked_seconds, slouch_seconds FROM posture_minutes"
    ).fetchone()
    assert row["locked_seconds"] == pytest.approx(30.0)
    assert row["slouch_seconds"] == pytest.approx(10.0)


def test_day_aggregation_and_kpis(store: HistoryStore) -> None:
    today = date.today()
    base = _midnight(today) + 9 * 3600  # 9 AM
    # Two minutes of locked time at 9:00, with half slouching
    for i in range(120):
        store.record_sample(
            is_locked=True,
            is_slouching=i % 2 == 0,
            cva=55.0,
            deviation=10.0,
            dt_seconds=1.0,
            now=base + i,
        )
    # One break
    store.start_break(now=base + 200)
    store.end_break(now=base + 260)
    store.record_alert(kind="slouch", now=base + 300)
    store.flush()

    day = store.day(today)
    assert day["date"] == today.isoformat()
    nine = day["buckets"][9]
    assert nine["locked_seconds"] == pytest.approx(120.0)
    assert nine["slouch_seconds"] == pytest.approx(60.0)
    assert nine["breaks"] == 1
    totals = day["totals"]
    assert totals["alerts"] == 1
    assert totals["breaks"] == 1
    assert totals["slouch_pct"] == pytest.approx(0.5)


def test_week_returns_seven_days(store: HistoryStore) -> None:
    today = date.today()
    week = store.week(today)
    assert len(week["days"]) == 7
    assert week["days"][-1]["date"] == today.isoformat()
    assert week["days"][0]["date"] == (today - timedelta(days=6)).isoformat()


def test_year_returns_365_days(store: HistoryStore) -> None:
    today = date.today()
    year = store.year(today)
    assert len(year["days"]) == 365


def test_streaks_count_consecutive_good_days(store: HistoryStore) -> None:
    today = date.today()

    def seed(d: date, slouch_pct: float, breaks: int) -> None:
        base = _midnight(d) + 10 * 3600
        store.record_sample(
            is_locked=True,
            is_slouching=False,
            cva=60.0,
            deviation=0.0,
            dt_seconds=600 * (1 - slouch_pct),
            now=base,
        )
        if slouch_pct > 0:
            store.record_sample(
                is_locked=True,
                is_slouching=True,
                cva=40.0,
                deviation=20.0,
                dt_seconds=600 * slouch_pct,
                now=base + 60,
            )
        store.flush()
        for k in range(breaks):
            store.start_break(now=base + 1000 + k * 60)
            store.end_break(now=base + 1030 + k * 60)

    # Today + yesterday: good. 2 days ago: bad slouch. Reset.
    seed(today, 0.10, 6)
    seed(today - timedelta(days=1), 0.15, 6)
    seed(today - timedelta(days=2), 0.40, 6)

    streaks = store.streaks(today, slouch_goal_pct=0.20, breaks_goal=5)
    assert streaks["good_posture_days"] == 2
    assert streaks["break_goal_days"] == 3


def test_clear_wipes_everything(store: HistoryStore) -> None:
    store.start_session(now=1000.0)
    store.end_session(now=1100.0)
    store.record_alert(now=1050.0)
    store.record_sample(
        is_locked=True, is_slouching=False, cva=60.0, deviation=0.0,
        dt_seconds=10.0, now=1010.0,
    )
    store.flush()
    store.clear()
    for table in ("sessions", "breaks", "alerts", "posture_minutes"):
        n = store._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        assert n == 0

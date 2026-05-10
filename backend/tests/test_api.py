"""End-to-end tests over the FastAPI surface using a fake detector + camera.

We swap out :class:`PostureDetector` with a stub so we don't need MediaPipe
weights in CI.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sentry.api import create_app
from sentry.config import RuntimeConfig, UserSettings
from sentry.posture import PoseObservation


class FakeDetector:
    def __init__(self, *_args, **_kwargs) -> None:
        self.current_model = "full"

    def set_model(self, level: str) -> None:
        self.current_model = level

    def detect(self, _frame):
        return [
            PoseObservation(
                cva=70.0,
                shoulder_width=0.4,
                torso_length=0.55,
                image_landmarks=[],
                world_landmarks=[],
            )
        ]


class FakeCamera:
    def __init__(self) -> None:
        self.is_running = False
        self._frame = np.zeros((10, 10, 3), dtype=np.uint8)

    def start(self, source) -> bool:
        self.is_running = True
        return True

    def stop(self) -> None:
        self.is_running = False

    def read_frame(self, timeout=None):
        return self._frame.copy()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("sentry.config.CONFIG_FILE", tmp_path / "config.json")
    with (
        patch("sentry.api.PostureDetector", FakeDetector),
        patch("sentry.api.CameraStream", FakeCamera),
    ):
        config = RuntimeConfig(
            settings=UserSettings(), history_db_path=tmp_path / "history.db"
        )
        app = create_app(config)
        with TestClient(app) as c:
            yield c


def test_devices_endpoint(client) -> None:
    response = client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert data["devices"][-1]["id"] == "ip"


def test_status_when_idle(client) -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "idle"
    assert data["monitoring"] is False


def test_calibrate_requires_monitoring(client) -> None:
    response = client.post("/api/calibrate")
    assert response.status_code == 400


def test_start_stop_cycle(client) -> None:
    started = client.post("/api/start", json={"source": "0"})
    assert started.status_code == 200
    assert started.json()["status"] == "started"

    status = client.get("/api/status").json()
    assert status["monitoring"] is True

    stopped = client.post("/api/stop")
    assert stopped.json()["status"] == "stopped"


def test_config_updates_persist_to_status(client) -> None:
    response = client.post(
        "/api/config",
        json={"sensitivity_threshold": 12.0, "slouch_time_threshold": 30.0, "alert_cooldown": 45.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sensitivity_threshold"] == 12.0
    assert body["slouch_time_threshold"] == 30.0
    assert body["alert_cooldown"] == 45.0


def test_config_rejects_unavailable_model(client) -> None:
    response = client.post("/api/config", json={"model_level": "heavy"})
    # Heavy model isn't downloaded in tests → 409.
    assert response.status_code == 409


def test_history_today_endpoint_shape(client) -> None:
    response = client.get("/api/history/today")
    assert response.status_code == 200
    data = response.json()
    assert "buckets" in data
    assert len(data["buckets"]) == 24
    assert "totals" in data
    assert {"locked_seconds", "slouch_seconds", "breaks", "alerts", "slouch_pct"} <= set(
        data["totals"].keys()
    )


def test_history_week_returns_seven_days(client) -> None:
    response = client.get("/api/history/week")
    assert response.status_code == 200
    assert len(response.json()["days"]) == 7


def test_history_year_returns_365_days(client) -> None:
    response = client.get("/api/history/year")
    assert response.status_code == 200
    assert len(response.json()["days"]) == 365


def test_history_streaks_endpoint(client) -> None:
    response = client.get("/api/history/streaks")
    assert response.status_code == 200
    data = response.json()
    assert "good_posture_days" in data
    assert "break_goal_days" in data


def test_history_clear(client) -> None:
    response = client.post("/api/history/clear")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_status_includes_stand_up_fields(client) -> None:
    data = client.get("/api/status").json()
    assert "stand_up_after_seconds" in data
    assert "locked_streak_seconds" in data
    assert "daily_slouch_goal_pct" in data
    assert "daily_break_goal" in data


def test_config_updates_goals_and_stand_up(client) -> None:
    response = client.post(
        "/api/config",
        json={
            "stand_up_after_minutes": 30.0,
            "daily_slouch_goal_pct": 0.15,
            "daily_break_goal": 6,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stand_up_after_seconds"] == 1800.0
    assert data["daily_slouch_goal_pct"] == 0.15
    assert data["daily_break_goal"] == 6

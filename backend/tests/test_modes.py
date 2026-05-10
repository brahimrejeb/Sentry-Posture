"""Mode gating: history recording and stand-up nudges only happen in advanced mode."""

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
                cva=70.0, shoulder_width=0.4, torso_length=0.55,
                image_landmarks=[], world_landmarks=[],
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
    # Isolate config.json so persisted settings don't leak between tests.
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


def test_default_mode_is_simple(client) -> None:
    data = client.get("/api/status").json()
    assert data["mode"] == "simple"


def test_switch_to_advanced(client) -> None:
    response = client.post("/api/config", json={"mode": "advanced"})
    assert response.status_code == 200
    assert response.json()["mode"] == "advanced"


def test_simple_mode_does_not_open_history_session(client, tmp_path) -> None:
    # Mode is simple by default. Start monitoring → no session row should appear.
    client.post("/api/start", json={"source": "0"})
    client.post("/api/stop")
    # Read the DB directly.
    import sqlite3

    db = sqlite3.connect(tmp_path / "history.db")
    rows = db.execute("SELECT COUNT(*) FROM sessions").fetchone()
    db.close()
    assert rows[0] == 0


def test_advanced_mode_opens_history_session(client, tmp_path) -> None:
    client.post("/api/config", json={"mode": "advanced"})
    client.post("/api/start", json={"source": "0"})
    client.post("/api/stop")
    import sqlite3

    db = sqlite3.connect(tmp_path / "history.db")
    rows = db.execute("SELECT COUNT(*) FROM sessions").fetchone()
    db.close()
    assert rows[0] >= 1

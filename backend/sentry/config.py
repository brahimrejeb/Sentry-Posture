"""Runtime paths, model registry, and persisted user settings."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Mode = Literal["simple", "advanced"]

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = REPO_ROOT / "assets"
UI_DIST_DIR = REPO_ROOT / "ui" / "dist"

SENTRY_HOME = Path(os.environ.get("SENTRY_HOME", Path.home() / ".sentry"))
MODEL_DIR = SENTRY_HOME / "models"
CONFIG_FILE = SENTRY_HOME / "config.json"

# MediaPipe pose landmarker model registry. URLs from Google's CDN; sha256
# hashes are pinned so a corrupted download will be re-fetched.
MODEL_REGISTRY: dict[str, dict[str, str | int]] = {
    "lite": {
        "filename": "pose_landmarker_lite.task",
        "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
        "size_mb": 6,
    },
    "full": {
        "filename": "pose_landmarker_full.task",
        "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
        "size_mb": 9,
    },
    "heavy": {
        "filename": "pose_landmarker_heavy.task",
        "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
        "size_mb": 30,
    },
}

DEFAULT_MODEL = "full"


def model_path(level: str) -> Path:
    return MODEL_DIR / str(MODEL_REGISTRY[level]["filename"])


def has_model(level: str) -> bool:
    return model_path(level).exists()


@dataclass
class UserSettings:
    """Persisted user preferences. Mirrored to ~/.sentry/config.json."""

    model_level: str = DEFAULT_MODEL
    sensitivity_threshold: float = 12.0
    slouch_time_threshold: float = 10.0
    alert_cooldown: float = 30.0
    settling_window: float = 5.0
    away_recalibrate_seconds: float = 60.0

    # History + goals
    stand_up_after_minutes: float = 50.0
    daily_slouch_goal_pct: float = 0.20      # at most 20% of locked time slouching
    daily_break_goal: int = 5

    # UI mode. Simple = core slouch detection only. Advanced = history,
    # goals, stand-up nudges, debug overlay.
    mode: Mode = "simple"

    @classmethod
    def load(cls) -> UserSettings:
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def save(self) -> None:
        SENTRY_HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


HISTORY_DB_PATH = SENTRY_HOME / "history.db"


DEFAULT_PORT = 47821  # uncommon, in IANA user range, no well-known service


@dataclass
class RuntimeConfig:
    """Process-wide configuration that the launcher passes to the API."""

    dev_mode: bool = False
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    settings: UserSettings = field(default_factory=UserSettings.load)
    history_db_path: Path = field(default_factory=lambda: HISTORY_DB_PATH)

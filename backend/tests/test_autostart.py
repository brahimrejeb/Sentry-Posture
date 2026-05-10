"""Auto-start tests. Each platform branch is exercised with patched IO."""

from __future__ import annotations

import platform
from unittest.mock import patch

from sentry import autostart


def test_describe_returns_supported_for_current_platform() -> None:
    info = autostart.describe()
    expected_supported = platform.system() in {"Windows", "Darwin", "Linux"}
    assert info.supported == expected_supported
    assert info.platform == platform.system()


def test_linux_autostart_writes_desktop_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTRY_AUTOSTART_DIR", str(tmp_path))
    with patch("sentry.autostart.platform.system", return_value="Linux"):
        autostart.enable()
        assert autostart.is_enabled() is True
        info = autostart.describe()
        assert info.target == str(tmp_path / "sentry.desktop")
        body = (tmp_path / "sentry.desktop").read_text(encoding="utf-8")
        assert "Sentry" in body
        assert "Exec=" in body
        # The registered command should include our entry flags.
        assert "--no-browser" in body
        assert "--autostarted" in body
        autostart.disable()
        assert autostart.is_enabled() is False
        assert not (tmp_path / "sentry.desktop").exists()


def test_command_uses_entry_point_when_installed() -> None:
    """When ``sentry-gui.exe`` / ``sentry`` is installed, the registered
    command should target it directly (no fragile python-subprocess chain)."""
    with patch("sentry.autostart.platform.system", return_value="Linux"):
        info = autostart.describe()
        assert info.command is not None
        # Either the entry-point binary, or the python-module fallback.
        assert ("sentry" in info.command and "-m" not in info.command) or (
            "-m sentry" in info.command
        )


def test_macos_autostart_writes_plist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTRY_LAUNCH_AGENT_DIR", str(tmp_path))
    with patch("sentry.autostart.platform.system", return_value="Darwin"):
        autostart.enable()
        assert autostart.is_enabled() is True
        plist = tmp_path / "com.sentry.posture.plist"
        body = plist.read_text(encoding="utf-8")
        assert "<?xml" in body
        assert "ProgramArguments" in body
        autostart.disable()
        assert autostart.is_enabled() is False


def test_disable_when_not_enabled_is_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTRY_AUTOSTART_DIR", str(tmp_path))
    with patch("sentry.autostart.platform.system", return_value="Linux"):
        autostart.disable()  # Should not raise.
        assert autostart.is_enabled() is False


def test_unsupported_platform_describes_no_support() -> None:
    with patch("sentry.autostart.platform.system", return_value="Plan9"):
        info = autostart.describe()
        assert info.supported is False
        assert info.command is None
        assert info.target is None


def test_enable_on_unsupported_platform_raises() -> None:
    with patch("sentry.autostart.platform.system", return_value="Plan9"):
        try:
            autostart.enable()
        except RuntimeError as exc:
            assert "not supported" in str(exc).lower()
        else:
            raise AssertionError("enable() should have raised RuntimeError")


def test_autostart_api_routes(tmp_path, monkeypatch) -> None:
    """End-to-end through the FastAPI client."""
    from unittest.mock import patch as _patch

    import numpy as np
    from fastapi.testclient import TestClient
    from sentry.api import create_app
    from sentry.config import RuntimeConfig
    from sentry.posture import PoseObservation

    class FakeDetector:
        def __init__(self, *_a, **_k) -> None:
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
            self._f = np.zeros((10, 10, 3), dtype=np.uint8)

        def start(self, source):
            self.is_running = True
            return True

        def stop(self) -> None:
            self.is_running = False

        def read_frame(self, timeout=None):
            return self._f.copy()

    monkeypatch.setenv("SENTRY_AUTOSTART_DIR", str(tmp_path))
    monkeypatch.setenv("SENTRY_LAUNCH_AGENT_DIR", str(tmp_path))
    monkeypatch.setattr("sentry.config.CONFIG_FILE", tmp_path / "config.json")

    from sentry.config import UserSettings

    with (
        _patch("sentry.api.PostureDetector", FakeDetector),
        _patch("sentry.api.CameraStream", FakeCamera),
        _patch(
            "sentry.autostart.platform.system",
            return_value=platform.system() if platform.system() != "Windows" else "Linux",
        ),
    ):
        config = RuntimeConfig(settings=UserSettings(), history_db_path=tmp_path / "h.db")
        app = create_app(config)
        with TestClient(app) as client:
            r = client.get("/api/autostart")
            assert r.status_code == 200
            assert r.json()["enabled"] is False
            r = client.post("/api/autostart", json={"enabled": True})
            assert r.status_code == 200
            assert r.json()["enabled"] is True
            r = client.post("/api/autostart", json={"enabled": False})
            assert r.json()["enabled"] is False

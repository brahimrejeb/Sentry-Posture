"""Camera lifecycle tests, using a fake VideoCapture so no hardware is needed."""

from __future__ import annotations

import time
from unittest.mock import patch

import numpy as np
from sentry import camera as camera_mod
from sentry.camera import CameraStream, list_devices


class FakeCapture:
    def __init__(self, *_args, **_kwargs):
        self.opened = True
        self.frame = np.zeros((10, 10, 3), dtype=np.uint8)

    def isOpened(self) -> bool:
        return self.opened

    def read(self):
        return True, self.frame.copy()

    def release(self) -> None:
        self.opened = False


def test_invalid_source_returns_false() -> None:
    cam = CameraStream()
    with patch("cv2.VideoCapture") as vc:
        instance = vc.return_value
        instance.isOpened.return_value = False
        assert cam.start(source="does-not-exist") is False
    assert not cam.is_running


def test_start_stop_with_fake_capture() -> None:
    cam = CameraStream()
    with patch("cv2.VideoCapture", FakeCapture):
        assert cam.start(source=0) is True
        # Wait briefly for the reader thread to populate a frame.
        deadline = time.time() + 1.0
        frame = None
        while time.time() < deadline and frame is None:
            frame = cam.read_frame(timeout=0.2)
        assert frame is not None
        assert frame.shape == (10, 10, 3)
        cam.stop()
    assert not cam.is_running


def test_list_devices_always_includes_ip_fallback() -> None:
    # Bypass the cache to exercise the enumeration path.
    camera_mod._DEVICE_CACHE = None
    devs = list_devices()
    assert devs[-1]["id"] == "ip"
    assert any(d["name"] for d in devs)

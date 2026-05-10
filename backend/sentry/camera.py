"""Camera capture and OS-aware device enumeration."""

from __future__ import annotations

import json
import platform
import re
import subprocess
import threading
import time
from collections.abc import Iterator
from glob import glob

import cv2
import numpy as np


def _capture_backend() -> int:
    system = platform.system()
    if system == "Windows":
        return cv2.CAP_DSHOW
    if system == "Darwin":
        return cv2.CAP_AVFOUNDATION
    if system == "Linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


class CameraStream:
    """Background-threaded camera reader.

    The reader thread pushes RGB frames into a single slot. Consumers wait on
    a condition variable so we don't busy-poll between frames.
    """

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self._is_running = False
        self._cond = threading.Condition()
        self._frame: np.ndarray | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, source: int | str = 0) -> bool:
        if self._is_running:
            self.stop()

        backend = _capture_backend() if isinstance(source, int) else cv2.CAP_ANY
        cap = cv2.VideoCapture(source, backend) if isinstance(source, int) else cv2.VideoCapture(source)
        if not cap.isOpened():
            cap.release()
            return False

        with self._cond:
            self._cap = cap
            self._frame = None
        self._is_running = True
        self._thread = threading.Thread(target=self._update, daemon=True, name="camera-reader")
        self._thread.start()
        return True

    def _update(self) -> None:
        cap = self._cap
        assert cap is not None
        while self._is_running:
            ret, frame = cap.read()
            if not ret or frame is None:
                # Camera unplugged or transient failure — back off briefly.
                time.sleep(0.1)
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with self._cond:
                self._frame = rgb
                self._cond.notify_all()

    def read_frame(self, timeout: float | None = None) -> np.ndarray | None:
        with self._cond:
            if self._frame is None and timeout is not None:
                self._cond.wait(timeout=timeout)
            return None if self._frame is None else self._frame.copy()

    def stop(self) -> None:
        self._is_running = False
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._cond:
            if self._cap is not None:
                self._cap.release()
            self._cap = None
            self._frame = None


# ---------------------------------------------------------------------------
# Device enumeration. Each platform has its own native trick to surface a
# friendly device name; we cache the result so we don't fork a subprocess
# every time the UI polls.

_DEVICE_CACHE: tuple[float, list[dict[str, str]]] | None = None
_DEVICE_CACHE_TTL = 5.0


def list_devices() -> list[dict[str, str]]:
    """Return a cached list of cameras, with a Phone/IP entry appended."""
    global _DEVICE_CACHE
    now = time.time()
    if _DEVICE_CACHE is not None and now - _DEVICE_CACHE[0] < _DEVICE_CACHE_TTL:
        return _DEVICE_CACHE[1]

    devices = list(_enumerate_devices())
    if not devices:
        devices.append({"id": "0", "name": "Default Camera"})
    devices.append({"id": "ip", "name": "Phone / IP Camera"})

    _DEVICE_CACHE = (now, devices)
    return devices


def _enumerate_devices() -> Iterator[dict[str, str]]:
    system = platform.system()
    if system == "Windows":
        yield from _windows_devices()
    elif system == "Darwin":
        yield from _macos_devices()
    elif system == "Linux":
        yield from _linux_devices()


def _windows_devices() -> Iterator[dict[str, str]]:
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-PnpDevice -Class Camera -Status OK | Select-Object -ExpandProperty FriendlyName",
            ],
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    for index, name in enumerate(line.strip() for line in result.stdout.splitlines() if line.strip()):
        yield {"id": str(index), "name": name}


def _macos_devices() -> Iterator[dict[str, str]]:
    try:
        result = subprocess.run(
            ["system_profiler", "-json", "SPCameraDataType"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return
    for index, entry in enumerate(data.get("SPCameraDataType", [])):
        name = entry.get("_name") or f"Camera {index}"
        yield {"id": str(index), "name": name}


def _linux_devices() -> Iterator[dict[str, str]]:
    seen: set[int] = set()
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"], capture_output=True, text=True, timeout=4
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None

    if result and result.returncode == 0:
        current_name: str | None = None
        for line in result.stdout.splitlines():
            if line and not line.startswith("\t") and not line.startswith(" "):
                current_name = line.strip().rstrip(":")
                continue
            match = re.search(r"/dev/video(\d+)", line)
            if match and current_name:
                idx = int(match.group(1))
                if idx not in seen:
                    seen.add(idx)
                    yield {"id": str(idx), "name": current_name}

    for path in sorted(glob("/dev/video*")):
        match = re.search(r"/dev/video(\d+)", path)
        if not match:
            continue
        idx = int(match.group(1))
        if idx in seen:
            continue
        seen.add(idx)
        yield {"id": str(idx), "name": f"Camera {idx}"}

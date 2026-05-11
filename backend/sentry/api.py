"""HTTP API and the long-running monitoring loop.

Wires :class:`CameraStream`, :class:`PostureDetector`, and :class:`Tracker`
together. The :class:`AppState` dataclass holds the few mutable bits of
process state instead of relying on module-level globals.
"""

from __future__ import annotations

import statistics
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import autostart
from .camera import CameraStream, list_devices
from .config import MODEL_REGISTRY, UI_DIST_DIR, RuntimeConfig, has_model
from .history import HistoryStore
from .models import (
    AutostartRequest,
    AutostartResponse,
    ConfigRequest,
    DayHistory,
    DevicesResponse,
    RangeHistory,
    SimpleResponse,
    StartRequest,
    StatusResponse,
    StreaksResponse,
)
from .notifications import notify
from .posture import PoseObservation, PostureDetector, draw_debug
from .tracker import Tracker, TrackerState

MONITOR_FPS = 4.0
MONITOR_PERIOD = 1.0 / MONITOR_FPS
HISTORY_FLUSH_INTERVAL = 60.0


@dataclass
class AppState:
    config: RuntimeConfig
    camera: CameraStream = field(init=False)
    detector: PostureDetector | None = field(default=None, init=False)
    tracker: Tracker = field(default_factory=Tracker)
    history: HistoryStore = field(init=False)
    monitor_thread: threading.Thread | None = None
    running: bool = True
    monitoring: bool = False
    # ``paused`` releases the OS camera handle so other apps (Teams, browser,
    # Windows Camera) can use the webcam while keeping the tracker, history
    # session, and calibration alive. Distinct from ``monitoring`` so the user
    # can pause without tearing down session state.
    paused: bool = False
    _paused_source: int | str | None = None
    last_observations: list[PoseObservation] = field(default_factory=list)
    last_primary: PoseObservation | None = None
    last_is_slouching: bool = False
    last_alert_at: float | None = None
    welcome_back_pending: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_break_state_paused: bool = False
    _paused_placeholder_jpeg: bytes | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        # Construct camera/detector/history here (not via default_factory) so
        # test fixtures that patch ``sentry.api.CameraStream`` and
        # ``sentry.api.PostureDetector`` actually take effect.
        self.camera = CameraStream()
        self.history = HistoryStore(db_path=self.config.history_db_path)
        s = self.config.settings
        self._apply_settings_to_tracker(s)
        self.detector = PostureDetector(model_level=s.model_level)

    def _apply_settings_to_tracker(self, s) -> None:  # type: ignore[no-untyped-def]
        self.tracker.sensitivity_threshold = s.sensitivity_threshold
        self.tracker.slouch_time_threshold = s.slouch_time_threshold
        self.tracker.alert_cooldown = s.alert_cooldown
        self.tracker.settling_seconds = s.settling_window
        self.tracker.away_recalibrate_seconds = s.away_recalibrate_seconds
        self.tracker.stand_up_after_seconds = s.stand_up_after_minutes * 60.0

    # ------------------------------------------------------------------
    @property
    def is_advanced(self) -> bool:
        return self.config.settings.mode == "advanced"

    def start_monitoring(self, source: int | str) -> bool:
        if not self.camera.start(source):
            return False
        self.monitoring = True
        self.paused = False
        self._paused_source = source
        self.tracker.start(fps=MONITOR_FPS)
        if self.is_advanced:
            self.history.start_session()
        self._last_break_state_paused = False
        return True

    def stop_monitoring(self) -> None:
        self.monitoring = False
        self.paused = False
        self._paused_source = None
        if self._last_break_state_paused:
            self.history.end_break(min_seconds=self.config.settings.break_min_seconds)
            self._last_break_state_paused = False
        self.history.end_session()
        self.tracker.stop()
        self.camera.stop()
        self.last_observations = []
        self.last_primary = None
        self.last_is_slouching = False

    def pause_monitoring(self) -> bool:
        """Release the camera so other apps can use it, keeping tracker state."""
        if not self.monitoring or self.paused:
            return False
        # Close any open break cleanly so the pause window doesn't get
        # counted as one giant break (or, in advanced mode, get truncated
        # weirdly when the loop stops ticking).
        if self._last_break_state_paused:
            self.history.end_break(min_seconds=self.config.settings.break_min_seconds)
            self._last_break_state_paused = False
        self.camera.stop()
        self.paused = True
        self.last_observations = []
        self.last_primary = None
        self.last_is_slouching = False
        return True

    def resume_monitoring(self) -> bool:
        if not self.paused or self._paused_source is None:
            return False
        if not self.camera.start(self._paused_source):
            return False
        self.paused = False
        return True

    def calibrate(self, samples: int = 30) -> tuple[bool, str]:
        """Average several frames so the baseline is stable."""
        assert self.detector is not None
        readings: list[float] = []
        attempts = 0
        deadline = time.time() + 4.0
        while len(readings) < samples and attempts < samples * 4 and time.time() < deadline:
            attempts += 1
            frame = self.camera.read_frame(timeout=0.5)
            if frame is None:
                continue
            people = self.detector.detect(frame)
            if not people:
                continue
            primary = max(people, key=lambda p: p.torso_length or 0.0)
            readings.append(primary.cva)
        if len(readings) < 5:
            return False, "Could not see you clearly. Sit in front of the camera and try again."
        baseline = statistics.median(readings)
        self.tracker.set_baseline(baseline)
        return True, f"Calibrated at {baseline:.1f}°"


def _monitor_loop(state: AppState) -> None:
    assert state.detector is not None
    last_flush = time.time()
    last_tick_at: float | None = None
    while state.running:
        if not state.monitoring or state.paused:
            time.sleep(0.1)
            last_tick_at = None
            continue
        frame = state.camera.read_frame(timeout=0.5)
        if frame is None:
            time.sleep(0.05)
            continue
        people = state.detector.detect(frame)
        now = time.time()
        result = state.tracker.tick(people, now=now)
        with state._lock:
            state.last_observations = people
            state.last_primary = result.primary
            state.last_is_slouching = result.is_slouching
            if result.welcome_back:
                state.welcome_back_pending = True

        # ----- record history (advanced mode only) --------------------
        dt = (now - last_tick_at) if last_tick_at is not None else MONITOR_PERIOD
        last_tick_at = now
        # Bound dt — if the loop stalled, don't credit hours of locked time.
        dt = min(max(dt, 0.0), 2.0)

        if state.is_advanced:
            is_paused_now = result.state is TrackerState.PAUSED
            if is_paused_now and not state._last_break_state_paused:
                state.history.start_break(now=now)
            elif not is_paused_now and state._last_break_state_paused:
                state.history.end_break(
                    now=now,
                    min_seconds=state.config.settings.break_min_seconds,
                )
            state._last_break_state_paused = is_paused_now

            is_locked = result.state is TrackerState.LOCKED
            primary = result.primary
            state.history.record_sample(
                is_locked=is_locked,
                is_slouching=result.is_slouching,
                cva=primary.cva if primary is not None else None,
                deviation=result.deviation if is_locked else None,
                dt_seconds=dt,
                now=now,
            )

            if now - last_flush >= HISTORY_FLUSH_INTERVAL:
                state.history.flush()
                last_flush = now

        # ----- notifications ------------------------------------------
        # Slouch alerts always fire — that's the core feature.
        if result.should_alert:
            state.last_alert_at = now
            if state.is_advanced:
                state.history.record_alert(kind="slouch", now=now)
            notify("Sentry", "Forward head posture detected. Sit up to reset your CVA.")
        # Stand-up nudges are advanced-only.
        if result.should_stand_up and state.is_advanced:
            state.history.record_alert(kind="standup", now=now)
            mins = int(state.tracker.stand_up_after_seconds // 60)
            notify(
                "Sentry — time to stand up",
                f"You've been at your desk for {mins} minutes. Stretch for a moment.",
            )

        time.sleep(MONITOR_PERIOD)


def _paused_placeholder(state: AppState) -> bytes:
    """A one-shot JPEG shown in the video feed while the camera is released."""
    if state._paused_placeholder_jpeg is not None:
        return state._paused_placeholder_jpeg
    import numpy as np

    img = np.zeros((360, 640, 3), dtype=np.uint8)
    img[:] = (32, 32, 38)
    text1 = "Camera released"
    text2 = "Other apps can use the webcam"
    cv2.putText(img, text1, (140, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (220, 220, 220), 2)
    cv2.putText(img, text2, (110, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (160, 160, 170), 2)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    state._paused_placeholder_jpeg = buf.tobytes() if ok else b""
    return state._paused_placeholder_jpeg


def _video_generator(state: AppState, debug: bool):
    last_jpeg: bytes | None = None
    while state.running:
        if state.paused or not state.monitoring:
            jpeg = _paused_placeholder(state)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.5)
            continue
        frame = state.camera.read_frame(timeout=0.5)
        if frame is None:
            time.sleep(0.05)
            if last_jpeg is not None:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last_jpeg + b"\r\n"
                )
            continue
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if debug:
            primary = state.last_primary
            bgr = draw_debug(
                bgr,
                primary.image_landmarks if primary is not None else None,
                tracker_state=state.tracker.state,
                is_slouching=state.last_is_slouching,
            )
        ok, buffer = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            time.sleep(0.05)
            continue
        last_jpeg = buffer.tobytes()
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last_jpeg + b"\r\n"
        time.sleep(1 / 30.0)


def create_app(config: RuntimeConfig | None = None) -> FastAPI:
    state = AppState(config=config or RuntimeConfig())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.monitor_thread = threading.Thread(
            target=_monitor_loop, args=(state,), daemon=True, name="sentry-monitor"
        )
        state.monitor_thread.start()
        try:
            yield
        finally:
            state.running = False
            state.stop_monitoring()
            state.history.close()
            if state.monitor_thread is not None:
                state.monitor_thread.join(timeout=1.0)

    app = FastAPI(title="Sentry", version="0.1.0", lifespan=lifespan)
    app.state.sentry = state

    if state.config.dev_mode:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ------- API routes ------------------------------------------------
    @app.get("/api/devices", response_model=DevicesResponse)
    def devices() -> DevicesResponse:
        return DevicesResponse(devices=list_devices())

    @app.post("/api/start", response_model=SimpleResponse)
    def start(req: StartRequest) -> SimpleResponse:
        src: int | str = int(req.source) if req.source.isdigit() else req.source
        if state.start_monitoring(src):
            return SimpleResponse(status="started")
        return SimpleResponse(status="error", message="Could not open camera.")

    @app.post("/api/stop", response_model=SimpleResponse)
    def stop() -> SimpleResponse:
        state.stop_monitoring()
        return SimpleResponse(status="stopped")

    @app.post("/api/pause", response_model=SimpleResponse)
    def pause() -> SimpleResponse:
        if state.pause_monitoring():
            return SimpleResponse(status="success", message="Camera released.")
        if state.paused:
            return SimpleResponse(status="success", message="Already paused.")
        raise HTTPException(status_code=400, detail="Start monitoring first.")

    @app.post("/api/resume", response_model=SimpleResponse)
    def resume() -> SimpleResponse:
        if state.resume_monitoring():
            return SimpleResponse(status="success", message="Monitoring resumed.")
        if not state.paused:
            return SimpleResponse(status="success", message="Not paused.")
        raise HTTPException(status_code=400, detail="Could not reopen the camera.")

    @app.post("/api/calibrate", response_model=SimpleResponse)
    def calibrate() -> SimpleResponse:
        if not state.monitoring:
            raise HTTPException(status_code=400, detail="Start monitoring first.")
        if state.paused:
            raise HTTPException(status_code=400, detail="Resume monitoring to calibrate.")
        ok, msg = state.calibrate()
        return SimpleResponse(status="success" if ok else "error", message=msg)

    @app.post("/api/config", response_model=StatusResponse)
    def update_config(req: ConfigRequest) -> StatusResponse:
        s = state.config.settings
        if req.model_level is not None:
            if not has_model(req.model_level):
                raise HTTPException(
                    status_code=409,
                    detail=f"Model '{req.model_level}' is not downloaded yet.",
                )
            assert state.detector is not None
            state.detector.set_model(req.model_level)
            s.model_level = req.model_level
        if req.sensitivity_threshold is not None:
            s.sensitivity_threshold = req.sensitivity_threshold
        if req.slouch_time_threshold is not None:
            s.slouch_time_threshold = req.slouch_time_threshold
        if req.alert_cooldown is not None:
            s.alert_cooldown = req.alert_cooldown
        if req.stand_up_after_minutes is not None:
            s.stand_up_after_minutes = req.stand_up_after_minutes
        if req.daily_slouch_goal_pct is not None:
            s.daily_slouch_goal_pct = req.daily_slouch_goal_pct
        if req.daily_break_goal is not None:
            s.daily_break_goal = req.daily_break_goal
        if req.break_min_seconds is not None:
            s.break_min_seconds = req.break_min_seconds
        if req.mode is not None:
            s.mode = req.mode
        state._apply_settings_to_tracker(s)
        s.save()
        return _build_status(state)

    @app.get("/api/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        return _build_status(state)

    @app.get("/api/feed")
    def feed(debug: bool = False) -> StreamingResponse:
        return StreamingResponse(
            _video_generator(state, debug=debug),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    # ------- History routes --------------------------------------------
    @app.get("/api/history/today", response_model=DayHistory)
    def history_today() -> DayHistory:
        state.history.flush()
        return DayHistory.model_validate(state.history.day(date.today()))

    @app.get("/api/history/week", response_model=RangeHistory)
    def history_week() -> RangeHistory:
        state.history.flush()
        return RangeHistory.model_validate(state.history.week(date.today()))

    @app.get("/api/history/month", response_model=RangeHistory)
    def history_month() -> RangeHistory:
        state.history.flush()
        return RangeHistory.model_validate(state.history.month(date.today(), days=30))

    @app.get("/api/history/year", response_model=RangeHistory)
    def history_year() -> RangeHistory:
        state.history.flush()
        return RangeHistory.model_validate(state.history.year(date.today()))

    @app.get("/api/history/streaks", response_model=StreaksResponse)
    def history_streaks() -> StreaksResponse:
        state.history.flush()
        s = state.config.settings
        return StreaksResponse.model_validate(
            state.history.streaks(
                date.today(), s.daily_slouch_goal_pct, s.daily_break_goal
            )
        )

    @app.post("/api/history/clear", response_model=SimpleResponse)
    def history_clear() -> SimpleResponse:
        state.history.clear()
        return SimpleResponse(status="success", message="History cleared.")

    # ------- Autostart routes -----------------------------------------
    @app.get("/api/autostart", response_model=AutostartResponse)
    def autostart_get() -> AutostartResponse:
        info = autostart.describe()
        return AutostartResponse(
            enabled=info.enabled,
            supported=info.supported,
            command=info.command,
            target=info.target,
            platform=info.platform,
        )

    @app.post("/api/autostart", response_model=AutostartResponse)
    def autostart_set(req: AutostartRequest) -> AutostartResponse:
        try:
            if req.enabled:
                autostart.enable()
            else:
                autostart.disable()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        info = autostart.describe()
        return AutostartResponse(
            enabled=info.enabled,
            supported=info.supported,
            command=info.command,
            target=info.target,
            platform=info.platform,
        )

    # ------- Static UI in production ----------------------------------
    if not state.config.dev_mode and UI_DIST_DIR.exists():
        app.mount("/", StaticFiles(directory=str(UI_DIST_DIR), html=True), name="ui")

    return app


def _build_status(state: AppState) -> StatusResponse:
    primary = state.last_primary
    s = state.config.settings
    available = [level for level in MODEL_REGISTRY if has_model(level)]
    welcome_back = state.welcome_back_pending
    state.welcome_back_pending = False
    return StatusResponse(
        monitoring=state.monitoring,
        paused=state.paused,
        state=state.tracker.state,
        calibrated=state.tracker.baseline_cva is not None,
        is_slouching=state.tracker.state is TrackerState.LOCKED
        and primary is not None
        and state.tracker.baseline_cva is not None
        and (state.tracker.baseline_cva - primary.cva) > state.tracker.sensitivity_threshold,
        person_detected=primary is not None,
        people_in_frame=len(state.last_observations),
        settling=state.tracker.is_settling,
        welcome_back=welcome_back,
        current_cva=primary.cva if primary else None,
        baseline_cva=state.tracker.baseline_cva,
        deviation=(state.tracker.baseline_cva - primary.cva)
        if (primary and state.tracker.baseline_cva is not None)
        else None,
        last_alert_at=state.last_alert_at,
        sensitivity_threshold=s.sensitivity_threshold,
        slouch_time_threshold=s.slouch_time_threshold,
        alert_cooldown=s.alert_cooldown,
        current_model=s.model_level,
        available_models=available,
        locked_streak_seconds=state.tracker.locked_streak_seconds(),
        stand_up_after_seconds=s.stand_up_after_minutes * 60.0,
        daily_slouch_goal_pct=s.daily_slouch_goal_pct,
        daily_break_goal=s.daily_break_goal,
        break_min_seconds=s.break_min_seconds,
        mode=s.mode,
    )


# Used by tests that just need a default app instance.
def default_app() -> FastAPI:
    return create_app()


__all__ = ["AppState", "create_app", "default_app"]

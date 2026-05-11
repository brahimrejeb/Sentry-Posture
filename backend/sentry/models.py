"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .tracker import TrackerState

ModelLevel = Literal["lite", "full", "heavy"]
Mode = Literal["simple", "advanced"]


class StartRequest(BaseModel):
    source: str = "0"


class ConfigRequest(BaseModel):
    model_level: ModelLevel | None = None
    sensitivity_threshold: float | None = Field(default=None, ge=1.0, le=45.0)
    slouch_time_threshold: float | None = Field(default=None, ge=2.0, le=600.0)
    alert_cooldown: float | None = Field(default=None, ge=0.0, le=600.0)
    stand_up_after_minutes: float | None = Field(default=None, ge=10.0, le=240.0)
    daily_slouch_goal_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    daily_break_goal: int | None = Field(default=None, ge=0, le=24)
    break_min_seconds: float | None = Field(default=None, ge=0.0, le=1800.0)
    mode: Mode | None = None


class DeviceInfo(BaseModel):
    id: str
    name: str


class DevicesResponse(BaseModel):
    devices: list[DeviceInfo]


class StatusResponse(BaseModel):
    monitoring: bool
    paused: bool = False
    state: TrackerState
    calibrated: bool
    is_slouching: bool
    person_detected: bool
    people_in_frame: int
    settling: bool
    welcome_back: bool
    current_cva: float | None = None
    baseline_cva: float | None = None
    deviation: float | None = None
    last_alert_at: float | None = None
    sensitivity_threshold: float
    slouch_time_threshold: float
    alert_cooldown: float
    current_model: str
    available_models: list[str]
    locked_streak_seconds: float = 0.0
    stand_up_after_seconds: float = 3000.0
    daily_slouch_goal_pct: float = 0.20
    daily_break_goal: int = 5
    break_min_seconds: float = 120.0
    mode: Mode = "simple"


class AutostartResponse(BaseModel):
    enabled: bool
    supported: bool
    command: str | None = None
    target: str | None = None
    platform: str


class AutostartRequest(BaseModel):
    enabled: bool


class HourBucket(BaseModel):
    hour: int
    locked_seconds: float
    slouch_seconds: float
    breaks: int


class DayTotals(BaseModel):
    locked_seconds: float
    slouch_seconds: float
    breaks: int
    alerts: int
    longest_uninterrupted_seconds: float
    slouch_pct: float


class DayHistory(BaseModel):
    date: str
    buckets: list[HourBucket]
    totals: DayTotals


class DaySummary(BaseModel):
    date: str
    locked_seconds: float
    slouch_seconds: float
    breaks: int
    alerts: int
    slouch_pct: float


class RangeHistory(BaseModel):
    days: list[DaySummary]


class StreaksResponse(BaseModel):
    good_posture_days: int
    break_goal_days: int


class SimpleResponse(BaseModel):
    status: Literal["success", "error", "started", "stopped"]
    message: str | None = None

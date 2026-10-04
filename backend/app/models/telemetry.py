from pydantic import BaseModel
from typing import Optional, List


class TelemetryFrame(BaseModel):
    """Normalised telemetry frame — game-agnostic format."""

    # Motion
    speed: float = 0.0           # km/h
    rpm: float = 0.0
    gear: int = 0                # 0 = neutral, -1 = reverse
    suggested_gear: Optional[int] = None

    # Inputs
    throttle: float = 0.0        # 0.0 – 1.0
    brake: float = 0.0           # 0.0 – 1.0
    steering: Optional[float] = None   # packet B+ only — not decoded yet, see telemetry_service.py

    # Lap info
    lap_number: int = 0
    lap_time_ms: int = 0         # current lap time in ms
    last_lap_ms: int = 0
    best_lap_ms: int = 0
    position: int = 0
    total_laps: int = 0

    # Fuel
    fuel_level: float = 0.0      # percentage 0–100
    fuel_per_lap: float = 0.0    # percentage consumed last lap (frontend-tracked, kept for compat)

    # Tyres (FL, FR, RL, RR) — offsets unchanged from the working build, do not touch
    tyre_temp_fl: float = 0.0
    tyre_temp_fr: float = 0.0
    tyre_temp_rl: float = 0.0
    tyre_temp_rr: float = 0.0

    # Wheel slip ratio — wheel surface speed ÷ car speed (see docs.gt7-datalogger.com).
    # <1 under braking = locking, >1 under power = spinning. Pinned to 1.0 below 1 m/s.
    slip_fl: float = 1.0
    slip_fr: float = 1.0
    slip_rl: float = 1.0
    slip_rr: float = 1.0

    # Suspension travel, mm
    sus_fl: Optional[float] = None
    sus_fr: Optional[float] = None
    sus_rl: Optional[float] = None
    sus_rr: Optional[float] = None

    # Engine health
    boost: Optional[float] = None          # bar
    water_temp: Optional[float] = None     # °C
    oil_temp: Optional[float] = None       # °C
    oil_pressure: Optional[float] = None   # bar
    rpm_alert_min: Optional[int] = None
    rpm_alert_max: Optional[int] = None

    # Driver aids — ACTIVE flags only. GT7 never sends the configured TC/ABS/
    # BIAS/MAP levels, only whether TCS/ASM kicked in on this tick.
    tcs_active: bool = False
    asm_active: bool = False
    handbrake: bool = False
    rev_limiter: bool = False
    car_on_track: bool = True

    # Accelerometers — packet B+ only, not decoded yet
    acc_lat: Optional[float] = None
    acc_long: Optional[float] = None
    acc_vert: Optional[float] = None

    # Per-wheel surface — packet C only (GT7 v1.68+), not decoded yet
    surface_fl: Optional[int] = None
    surface_fr: Optional[int] = None
    surface_rl: Optional[int] = None
    surface_rr: Optional[int] = None

    # Misc
    paused: bool = False
    car_id: int = 0
    packet_format: str = "A"
    source_game: str = "gt7"


class ConnectionStatus(BaseModel):
    connected: bool = False
    game: str = "gt7"
    source_ip: Optional[str] = None
    frames_received: int = 0
    packet_format: str = "A"
    last_seen: Optional[float] = None


class StrategyProjection(BaseModel):
    """Live fuel / pit-window projection.

    last N completed laps for the current car, partial-lap outliers dropped,
    laps-to-empty = fuel_level / avg_fuel_per_lap.
    """
    avg_fuel_per_lap: Optional[float] = None   # % per lap
    avg_lap_ms: Optional[float] = None
    laps_to_empty: Optional[float] = None
    time_to_empty_ms: Optional[float] = None
    pit_before_lap: Optional[int] = None
    fuel_ok_for_race: Optional[bool] = None
    fuel_shortfall_pct: Optional[float] = None
    warning: str = "none"   # "none" | "amber" | "red"


class LiveEvent(BaseModel):
    """A single Pitwall 'Live Events' entry — rule-based, no ML."""
    kind: str            # e.g. "tyre_temp_fl", "fuel_critical", "pace_drop"
    severity: str         # "info" | "warning" | "critical"
    message: str
    lap: int
    ts: float
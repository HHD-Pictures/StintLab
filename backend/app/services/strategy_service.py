"""
Fuel & pit-window projection.

  recent        = last N completed laps for the CURRENT CAR that consumed > 0.01 %
  usable        = recent minus partial-lap outliers (consumed < 50% of window max)
  avgFuelPerLap = mean(usable.fuel_consumed)
  lapsToEmpty   = current_fuel_level / avgFuelPerLap

Units here are % of tank (StintLab's fuel_level is already a percentage), not
litres like the docs' reference implementation — the math is unit-agnostic.
"""

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from app.core.config import settings
from app.models.telemetry import TelemetryFrame, StrategyProjection

FUEL_CRITICAL_LAPS = 2.0
FUEL_WARNING_LAPS = 4.0


@dataclass
class _LapFuelRecord:
    lap_number: int
    fuel_consumed_pct: float
    lap_time_ms: int


class StrategyService:
    def __init__(self, window: Optional[int] = None):
        self.window = window or settings.STRATEGY_WINDOW_LAPS
        self._history: Deque[_LapFuelRecord] = deque(maxlen=self.window)
        self._current_car_id: Optional[int] = None
        self._fuel_at_lap_start: Optional[float] = None
        self._last_lap_seen: int = 0

    def reset(self):
        self._history.clear()
        self._fuel_at_lap_start = None
        self._last_lap_seen = 0

    def on_frame(self, frame: TelemetryFrame) -> Optional[StrategyProjection]:
        # Switching cars drops the old car's laps from the window.
        if self._current_car_id is not None and frame.car_id != self._current_car_id:
            self.reset()
        self._current_car_id = frame.car_id

        if self._fuel_at_lap_start is None:
            self._fuel_at_lap_start = frame.fuel_level

        # Lap boundary: counter advanced exactly +1, previous lap was real (>0),
        # and GT7 reported a time for it — same guard the docs use.
        if (frame.lap_number == self._last_lap_seen + 1
                and self._last_lap_seen > 0
                and frame.last_lap_ms > 0):
            consumed = max(0.0, self._fuel_at_lap_start - frame.fuel_level)
            if consumed > 0.01:
                self._history.append(_LapFuelRecord(
                    lap_number=self._last_lap_seen,
                    fuel_consumed_pct=consumed,
                    lap_time_ms=frame.last_lap_ms,
                ))
            self._fuel_at_lap_start = frame.fuel_level

        if frame.lap_number != self._last_lap_seen:
            self._last_lap_seen = frame.lap_number

        return self._project(frame)

    def _project(self, frame: TelemetryFrame) -> Optional[StrategyProjection]:
        if not self._history:
            return None

        window_max = max(r.fuel_consumed_pct for r in self._history)
        usable = [r for r in self._history if r.fuel_consumed_pct >= 0.5 * window_max]
        if not usable:
            return None

        avg_fuel = sum(r.fuel_consumed_pct for r in usable) / len(usable)
        avg_lap_ms = sum(r.lap_time_ms for r in usable) / len(usable)
        if avg_fuel <= 0:
            return None

        laps_to_empty = frame.fuel_level / avg_fuel
        time_to_empty_ms = laps_to_empty * avg_lap_ms
        pit_before_lap = frame.lap_number + int(laps_to_empty)

        warning = "none"
        if laps_to_empty < FUEL_CRITICAL_LAPS:
            warning = "red"
        elif laps_to_empty < FUEL_WARNING_LAPS:
            warning = "amber"

        fuel_ok = None
        shortfall = None
        if frame.total_laps > 0:
            laps_remaining = frame.total_laps - frame.lap_number + 1
            needed = laps_remaining * avg_fuel
            fuel_ok = needed <= frame.fuel_level
            shortfall = None if fuel_ok else round(needed - frame.fuel_level, 1)

        return StrategyProjection(
            avg_fuel_per_lap=round(avg_fuel, 2),
            avg_lap_ms=round(avg_lap_ms, 0),
            laps_to_empty=round(laps_to_empty, 1),
            time_to_empty_ms=round(time_to_empty_ms, 0),
            pit_before_lap=pit_before_lap,
            fuel_ok_for_race=fuel_ok,
            fuel_shortfall_pct=shortfall,
            warning=warning,
        )
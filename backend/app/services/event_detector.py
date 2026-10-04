"""
Pitwall "Live Events" — rule-based, no ML, per the original spec:

    IF tyre_temp_fl > threshold        -> "Front-left overheating"
    IF fuel_laps_remaining < 2         -> "Fuel critical"
    IF lap_delta > X                   -> "Pace degradation"

"Car ahead within DRS range" from the original spec is deliberately not
implemented: GT7's UDP telemetry only ever describes YOUR car. There is no
gap-to-other-cars data to build that rule on.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.models.telemetry import TelemetryFrame, StrategyProjection, LiveEvent

TYRE_TEMP_HIGH_C = 100.0     # tune to your car/tyre compound
TYRE_TEMP_SPIKE_C = 8.0      # sudden jump between ticks, catches overheating faster than an absolute value
PACE_DROP_MS = 500           # lap-to-lap slowdown considered "degradation"
COOLDOWN_S = 15.0            # don't re-fire the same kind of event more than once per window

_WHEELS = ("fl", "fr", "rl", "rr")
_WHEEL_LABELS = {"fl": "Front-left", "fr": "Front-right", "rl": "Rear-left", "rr": "Rear-right"}


@dataclass
class EventDetector:
    _last_fired: Dict[str, float] = field(default_factory=dict)
    _prev_tyre_temps: Optional[Tuple[float, float, float, float]] = None
    _prev_lap_ms: Optional[int] = None
    _last_lap_number: int = 0

    def reset(self):
        self._last_fired.clear()
        self._prev_tyre_temps = None
        self._prev_lap_ms = None
        self._last_lap_number = 0

    def _fire(self, kind: str, severity: str, message: str, lap: int) -> Optional[LiveEvent]:
        now = time.time()
        if now - self._last_fired.get(kind, 0.0) < COOLDOWN_S:
            return None
        self._last_fired[kind] = now
        return LiveEvent(kind=kind, severity=severity, message=message, lap=lap, ts=now)

    def check(self, frame: TelemetryFrame, strategy: Optional[StrategyProjection]) -> List[LiveEvent]:
        events: List[LiveEvent] = []
        temps = (frame.tyre_temp_fl, frame.tyre_temp_fr, frame.tyre_temp_rl, frame.tyre_temp_rr)

        for wheel, temp in zip(_WHEELS, temps):
            if temp >= TYRE_TEMP_HIGH_C:
                ev = self._fire(f"tyre_temp_{wheel}", "warning",
                                 f"{_WHEEL_LABELS[wheel]} tyre temp {temp:.0f}°C", frame.lap_number)
                if ev:
                    events.append(ev)

        if self._prev_tyre_temps is not None:
            for wheel, prev, cur in zip(_WHEELS, self._prev_tyre_temps, temps):
                if cur - prev >= TYRE_TEMP_SPIKE_C:
                    ev = self._fire(f"tyre_spike_{wheel}", "warning",
                                     f"{_WHEEL_LABELS[wheel]} temp +{cur - prev:.0f}°C", frame.lap_number)
                    if ev:
                        events.append(ev)
        self._prev_tyre_temps = temps

        if strategy and strategy.laps_to_empty is not None:
            if strategy.warning == "red":
                ev = self._fire("fuel_critical", "critical",
                                 f"Fuel critical — {strategy.laps_to_empty:.1f} laps left", frame.lap_number)
                if ev:
                    events.append(ev)
            elif strategy.warning == "amber":
                ev = self._fire("fuel_window", "info",
                                 f"Pit window open — est. lap {strategy.pit_before_lap}", frame.lap_number)
                if ev:
                    events.append(ev)

        if frame.lap_number != self._last_lap_number and frame.last_lap_ms > 0:
            if self._prev_lap_ms is not None:
                delta = frame.last_lap_ms - self._prev_lap_ms
                if delta >= PACE_DROP_MS:
                    ev = self._fire("pace_drop", "info",
                                     f"Pace degradation — +{delta / 1000:.2f}s vs last lap", frame.lap_number)
                    if ev:
                        events.append(ev)
            self._prev_lap_ms = frame.last_lap_ms
            self._last_lap_number = frame.lap_number

        return events
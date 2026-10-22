"""Base risk score for the next mission, from fixed rules so it is repeatable (PRD "Risk scoring").

The Risk agent may move the result by at most 10 points and must say why. Points:
  predicted battery at landing < 10 % / < 20 % / 20-30 %   +45 / +30 / +15
      (below 10 % the battery failsafe would abort the mission: an AeroMind addition)
  battery at landing Bad in the latest flight              +15  (AeroMind addition, like wind)
  telemetry dropouts Bad / Caution                         +20 / +10
  GPS Bad / Caution                                        +20 / +10
  wind Bad in the latest flight                            +15
  vibration Bad                                            +15
  each failsafe not set (FS_THR_ENABLE, BATT_FS_LOW_ACT,
  FENCE_ENABLE = 0)                                        +10
  a recurring issue from history                           +10
Levels: Low < 30, Medium 30-59, High >= 60, capped at 100.
"""
from typing import Optional

from agents.schemas import Metrics

BATTERY_ABORT_PCT, BATTERY_BAD_PCT, BATTERY_CAUTION_PCT = 10.0, 20.0, 30.0
FAILSAFE_PARAMS = ("FS_THR_ENABLE", "BATT_FS_LOW_ACT", "FENCE_ENABLE")
MEDIUM_FROM, HIGH_FROM = 30, 60
MAX_SCORE = 100
MIN_HISTORY = 3
SEVERITY = {"good": 0, "caution": 1, "bad": 2}


def _worst(status: dict, keys: tuple) -> Optional[str]:
    found = [status[k] for k in keys if k in status]
    return max(found, key=SEVERITY.get) if found else None


def level(score: int) -> str:
    return "High" if score >= HIGH_FROM else "Medium" if score >= MEDIUM_FROM else "Low"


def base_score(metrics: Metrics, params: Optional[dict], predicted_battery_pct: Optional[float],
               recurring: list, history_flights: int) -> dict:
    factors = []

    def add(points: int, text: str) -> None:
        factors.append({"factor": text, "points": points})

    battery = predicted_battery_pct
    source = "predicted"
    if battery is None:
        battery, source = metrics.battery.remaining_end_pct, "this flight's"
    if battery is not None:
        if battery < BATTERY_ABORT_PCT:
            add(45, f"{source} battery at landing {battery:.0f} % (< 10 %: the battery failsafe would end the mission)")
        elif battery < BATTERY_BAD_PCT:
            add(30, f"{source} battery at landing {battery:.0f} % (< 20 %)")
        elif battery <= BATTERY_CAUTION_PCT:
            add(15, f"{source} battery at landing {battery:.0f} % (20-30 %)")
    if source == "predicted" and metrics.status.get("battery_end") == "bad":
        add(15, f"latest flight landed with {metrics.battery.remaining_end_pct:.0f} % battery")

    link = _worst(metrics.status, ("dropouts", "link_uptime"))
    if link in ("bad", "caution"):
        count = len(metrics.link.dropouts)
        add(20 if link == "bad" else 10, f"telemetry link {link}: {count} dropout(s), uptime {metrics.link.uptime_pct} %")
    gps = _worst(metrics.status, ("gps_sats", "gps_hdop"))
    if gps in ("bad", "caution"):
        add(20 if gps == "bad" else 10, f"GPS {gps}: min {metrics.gps.min_sats} satellites, HDOP {metrics.gps.max_hdop}")
    if metrics.status.get("wind") == "bad":
        add(15, f"wind {metrics.wind.max_ms} m/s in the latest flight")
    if metrics.status.get("vibration") == "bad":
        add(15, "vibration Bad")

    if params is not None:
        for name in FAILSAFE_PARAMS:
            if params.get(name) == 0:
                add(10, f"failsafe not set: {name} = 0")
    if recurring:
        add(10, f"recurring issue: {', '.join(recurring)}")

    score = min(MAX_SCORE, sum(f["points"] for f in factors))
    return {"score": score, "level": level(score), "factors": factors,
            "confidence": "low" if history_flights < MIN_HISTORY else "normal",
            "params_checked": params is not None}

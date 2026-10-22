"""Good / Caution / Bad bands for every metric (PRD "Metrics and thresholds"), and the health score.

Vibration bands follow ArduPilot's guidance; the rest are project defaults. A metric that could not
be computed has no status at all, so it neither helps nor hurts the health score.
"""
from typing import Optional

CAUTION_PENALTY = 10
BAD_PENALTY = 25

XTRACK_GOOD_M, XTRACK_BAD_M = 1.0, 3.0
BATTERY_GOOD_PCT, BATTERY_BAD_PCT = 30.0, 20.0
VIBRATION_GOOD, VIBRATION_BAD = 30.0, 60.0
SATS_GOOD, SATS_BAD = 10, 6
HDOP_GOOD, HDOP_BAD = 1.5, 2.5
WIND_GOOD_MS, WIND_BAD_MS = 5.0, 8.0
TILT_GOOD_DEG, TILT_BAD_DEG = 25.0, 35.0
WARNINGS_BAD = 2
UPTIME_GOOD_PCT, UPTIME_BAD_PCT = 99.0, 95.0
DROPOUTS_BAD_COUNT = 2
DROPOUT_BAD_S = 10.0
PACKET_LOSS_GOOD_PCT, PACKET_LOSS_BAD_PCT = 2.0, 5.0
POSITION_RATE_BAD_RATIO = 0.5


def higher_is_worse(value, good_below, bad_above) -> Optional[str]:
    if value is None:
        return None
    if value < good_below:
        return "good"
    return "bad" if value > bad_above else "caution"


def lower_is_worse(value, good_at_least, bad_below) -> Optional[str]:
    if value is None:
        return None
    if value >= good_at_least:
        return "good"
    return "bad" if value < bad_below else "caution"


def battery_end(pct):
    if pct is None:
        return None
    if pct > BATTERY_GOOD_PCT:
        return "good"
    return "bad" if pct < BATTERY_BAD_PCT else "caution"


def clipping(count):
    return None if count is None else ("good" if count == 0 else "caution")


def completion(pct):
    return None if pct is None else ("good" if pct >= 100.0 else "bad")


def warnings(count):
    return None if count is None else ("good" if count == 0 else "bad" if count > WARNINGS_BAD else "caution")


def dropouts(durations: Optional[list]):
    """0 good; 1-2 dropouts of at most 10 s caution; more than 2, or any longer than 10 s, bad."""
    if durations is None:
        return None
    if not durations:
        return "good"
    if len(durations) > DROPOUTS_BAD_COUNT or max(durations) > DROPOUT_BAD_S:
        return "bad"
    return "caution"


def position_rate(min_ratio):
    return None if min_ratio is None else ("bad" if min_ratio < POSITION_RATE_BAD_RATIO else "good")


def health_score(statuses: dict) -> int:
    values = list(statuses.values())
    score = 100 - CAUTION_PENALTY * values.count("caution") - BAD_PENALTY * values.count("bad")
    return max(0, score)


def statuses(metrics: dict) -> dict:
    """metric key -> status, from a metrics dict shaped like agents.schemas.Metrics."""
    vib = metrics["vibration"]
    vib_values = [v for v in (vib.get("max_x"), vib.get("max_y"), vib.get("max_z")) if v is not None]
    att = metrics["attitude"]
    tilt_values = [v for v in (att.get("max_roll_deg"), att.get("max_pitch_deg")) if v is not None]
    link = metrics["link"]
    uptime = link.get("uptime_pct")
    result = {
        "xtrack_max_m": higher_is_worse(metrics["tracking"].get("xtrack_max_m"), XTRACK_GOOD_M, XTRACK_BAD_M),
        "battery_end": battery_end(metrics["battery"].get("remaining_end_pct")),
        "vibration": higher_is_worse(max(vib_values) if vib_values else None, VIBRATION_GOOD, VIBRATION_BAD),
        "clipping": clipping(vib.get("clip_total")),
        "gps_sats": lower_is_worse(metrics["gps"].get("min_sats"), SATS_GOOD, SATS_BAD),
        "gps_hdop": higher_is_worse(metrics["gps"].get("max_hdop"), HDOP_GOOD, HDOP_BAD),
        "wind": higher_is_worse(metrics["wind"].get("max_ms"), WIND_GOOD_MS, WIND_BAD_MS),
        "attitude": higher_is_worse(max(tilt_values) if tilt_values else None, TILT_GOOD_DEG, TILT_BAD_DEG),
        "mission_completion": completion(metrics["tracking"].get("mission_completion_pct")),
        "warnings": warnings(metrics.get("warnings")),
        "link_uptime": lower_is_worse(uptime, UPTIME_GOOD_PCT, UPTIME_BAD_PCT),
        "dropouts": dropouts([d["duration_s"] for d in link.get("dropouts", [])] if uptime is not None else None),
        "packet_loss": higher_is_worse(link.get("packet_loss_pct"), PACKET_LOSS_GOOD_PCT, PACKET_LOSS_BAD_PCT),
        "position_rate": position_rate(link.get("position_rate_min_ratio")),
    }
    return {key: status for key, status in result.items() if status is not None}

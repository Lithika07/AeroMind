"""Cause hint rules: which metric patterns point to which root cause.

Given to the Diagnosis agent as guidance, and used as-is by its rule-based fallback, so both reach
the same causes from the same evidence.
"""
SEVERITY = {"good": 0, "caution": 1, "bad": 2}
FAST_LEG_MS = 8.0


def worst(status: dict, *keys) -> str:
    found = [status[k] for k in keys if k in status]
    return max(found, key=SEVERITY.get) if found else "good"


def flagged(status: dict, *keys) -> bool:
    return worst(status, *keys) != "good"


HINT_TEXT = """Cause hints (category: evidence):
- wind_drift: wind Caution/Bad together with cross-track Caution/Bad or attitude near its limit.
- speed_too_high: legs flown faster than 8 m/s with cross-track Caution/Bad or attitude Caution/Bad.
- low_battery: battery at landing Caution/Bad, or a battery failsafe event.
- link_loss: telemetry dropouts or link uptime Caution/Bad (the mission may still have completed).
- gps_weak: minimum satellites or HDOP Caution/Bad.
- vibration: vibration Caution/Bad or accelerometer clipping.
- setup: a failsafe parameter (FS_THR_ENABLE, BATT_FS_LOW_ACT, FENCE_ENABLE) is 0.
Pilot notes are supporting evidence only, never a cause on their own."""


def causes(metrics: dict, params: dict = None) -> list:
    """[(category, cause text, confidence, metric keys)] for the patterns present, strongest first."""
    status = metrics["status"]
    found = []
    legs = metrics["tracking"]["legs"]
    fast = [leg for leg in legs if (leg.get("speed_ms") or 0) > FAST_LEG_MS]
    tracking_hit = flagged(status, "xtrack_max_m", "attitude")
    windy = flagged(status, "wind") and tracking_hit
    top = max((leg["speed_ms"] for leg in fast), default=None)
    if windy:
        # wind and speed together are one cause: the drift comes from flying fast into the crosswind
        text = f"Crosswind of {metrics['wind']['max_ms']} m/s pushed the drone off its track"
        text += f" while flying at up to {top} m/s" if fast else ""
        found.append(("wind_drift", text, 0.8 if worst(status, "wind") == "bad" else 0.6,
                      ["wind.max_ms", "tracking.xtrack_max_m"] + (["attitude.max_roll_deg"] if fast else [])))
    elif fast and tracking_hit:
        found.append(("speed_too_high", f"Legs flown at up to {top} m/s left too little control margin",
                      0.7, ["tracking.xtrack_max_m", "attitude.max_roll_deg"]))
    if flagged(status, "battery_end"):
        found.append(("low_battery", f"Battery too small for this route: landed with "
                      f"{metrics['battery']['remaining_end_pct']:.0f} %", 0.85 if worst(status, "battery_end") == "bad"
                      else 0.6, ["battery.remaining_end_pct", "battery.used_pct_per_km"]))
    if flagged(status, "dropouts", "link_uptime"):
        count = len(metrics["link"]["dropouts"])
        found.append(("link_loss", f"Telemetry link dropped {count} time(s); uptime {metrics['link']['uptime_pct']} %",
                      0.9, ["link.uptime_pct", "link.dropouts"]))
    if flagged(status, "gps_sats", "gps_hdop"):
        found.append(("gps_weak", f"Weak GPS: {metrics['gps']['min_sats']} satellites, HDOP {metrics['gps']['max_hdop']}",
                      0.8, ["gps.min_sats", "gps.max_hdop"]))
    if flagged(status, "vibration", "clipping"):
        found.append(("vibration", "High vibration or accelerometer clipping", 0.7, ["vibration.max_z"]))
    unset = [p for p in ("FS_THR_ENABLE", "BATT_FS_LOW_ACT", "FENCE_ENABLE") if params and params.get(p) == 0]
    if unset:
        found.append(("setup", f"Failsafe disabled in the parameters: {', '.join(unset)}", 0.5,
                      [f"params.{p}" for p in unset]))
    return sorted(found, key=lambda c: -c[2])

"""Rule-based output for every agent, from the metrics alone.

Used when no LLM is configured, when a call fails twice, or to fill what the Verifier rejected.
Every number here is read from the state, so these outputs always pass verification.
"""
from agents import hints
from agents.schemas import (AdvisorOut, Cause, Claim, DiagnosisOut, Edit, FlightSummaryOut, Recommendation,
                            RiskOut, StoryLine, TelemetryLinkOut)
from tools import mission_io
from tools import thresholds as th
from tools import waypoints as wp

SAFE_SPEED_MS = 6.0
TARGET_BATTERY_PCT = 30.0
VERDICT_GOOD_HEALTH = 80
VERDICT_UNSAFE_HEALTH = 40


def verdict(m: dict) -> str:
    status = m["status"]
    failsafe = any(e["kind"] == "failsafe" for e in m["events"])
    if m["health_score"] < VERDICT_UNSAFE_HEALTH or failsafe or status.get("mission_completion") == "bad":
        return "Unsafe"
    if m["health_score"] >= VERDICT_GOOD_HEALTH and "bad" not in status.values():
        return "Good"
    return "Needs attention"


def _leg_line(m: dict, phase: dict, leg: dict) -> StoryLine:
    status = th.higher_is_worse(leg["xtrack_max_m"], th.XTRACK_GOOD_M, th.XTRACK_BAD_M) or "good"
    dropouts = [d for d in m["link"]["dropouts"] if phase["t_start"] <= d["t"] <= phase["t_end"]]
    text = f"{leg['speed_ms']} m/s, cross-track up to {leg['xtrack_max_m']} m"
    if dropouts:
        text += f"; link lost {dropouts[0]['duration_s']} s"
        status = "bad" if dropouts[0]["duration_s"] > th.DROPOUT_BAD_S else max(status, "caution", key=hints.SEVERITY.get)
    return StoryLine(phase=phase["name"], status=status, text=text)


def story(m: dict) -> list:
    legs = {leg["t_start"]: leg for leg in m["tracking"]["legs"]}
    lines = []
    for phase in m["phases"]:
        seconds = round(phase["t_end"] - phase["t_start"])
        if phase["kind"] == "leg" and phase["t_start"] in legs:
            lines.append(_leg_line(m, phase, legs[phase["t_start"]]))
        elif phase["kind"] == "takeoff":
            lines.append(StoryLine(phase=phase["name"], status="good",
                                   text=f"climbed to {m['flight']['max_alt_m']} m in {seconds} s"))
        elif phase["kind"] == "land":
            battery = m["battery"]["remaining_end_pct"]
            status = th.battery_end(battery) or "good"
            lines.append(StoryLine(phase=phase["name"], status=status, text=f"landed with {battery:.0f} % battery"
                                   if battery is not None else f"landed after {seconds} s"))
        else:
            lines.append(StoryLine(phase=phase["name"], status="good", text=f"{seconds} s"))
    return lines


def flight_summary(state: dict) -> FlightSummaryOut:
    m = state["metrics"]
    flight = m["flight"]
    problems = [k.replace("_", " ") for k, v in m["status"].items() if v == "bad"]
    duration = "an unknown time" if flight["duration_s"] is None else f"{flight['duration_s']:.0f} s"
    distance = "an unknown distance" if flight["distance_m"] is None else f"{flight['distance_m']:.0f} m"
    first = f"The flight lasted {duration} over {distance} and scored {m['health_score']} out of 100."
    second = (f"The main problems were: {', '.join(problems)}." if problems
              else "No metric was in the Bad band.")
    battery = m["battery"]["remaining_end_pct"]
    uptime = m["link"]["uptime_pct"]
    third = (f"It landed with {battery:.0f} % battery" if battery is not None else "Battery level was not reported") + \
        (f" and the telemetry link was up {uptime} % of the time." if uptime is not None else ".")
    claims = [Claim(id="S1", text="health score", metric="health_score", value=m["health_score"])]
    if battery is not None:
        claims.append(Claim(id="S2", text="battery at landing", metric="battery.remaining_end_pct", value=battery))
    return FlightSummaryOut(verdict=verdict(m), summary=" ".join([first, second, third]), flight_story=story(m),
                            claims=claims)


def telemetry_link(state: dict) -> TelemetryLinkOut:
    link = state["metrics"]["link"]
    status = state["metrics"]["status"]
    link_verdict = hints.worst(status, "dropouts", "link_uptime", "packet_loss", "position_rate")
    findings = [Claim(id="L1", text=f"Link uptime {link['uptime_pct']} % across the flight",
                      metric="link.uptime_pct", value=link["uptime_pct"])]
    for k, d in enumerate(link["dropouts"]):
        near = f" near WP{d['near_wp']}" if d["near_wp"] is not None else ""
        findings.append(Claim(id=f"L{k + 2}", text=f"Link lost {d['duration_s']} s at t={d['t']:.0f} s{near}",
                              metric=f"link.dropouts[{k}].duration_s", value=d["duration_s"]))
    if link["packet_loss_pct"] is not None:
        findings.append(Claim(id=f"L{len(findings) + 1}", text=f"Packet loss {link['packet_loss_pct']} %",
                              metric="link.packet_loss_pct", value=link["packet_loss_pct"]))
    if link["rssi"] is None:
        findings.append(Claim(id=f"L{len(findings) + 1}", text="Radio RSSI not reported (no telemetry radio in the log)"))
    return TelemetryLinkOut(link_verdict=link_verdict, safe_for_mission=link_verdict != "bad", link_findings=findings)


def _value(state: dict, path: str):
    from agents.verifier import evidence, resolve
    found, value = resolve(evidence(state), path)
    return value if found and isinstance(value, (int, float)) else None


def diagnosis(state: dict) -> DiagnosisOut:
    m = state["metrics"]
    findings, causes = [], []
    for category, text, confidence, paths in hints.causes(m, state.get("params")):
        ids = []
        for path in paths:
            value = _value(state, path)
            if value is None:
                continue
            existing = next((f for f in findings if f.metric == path), None)
            if existing is None:
                existing = Claim(id=f"F{len(findings) + 1}", text=f"{path} = {value}", metric=path, value=value)
                findings.append(existing)
            ids.append(existing.id)
        causes.append(Cause(id=f"C{len(causes) + 1}", cause=text, category=category, confidence=confidence,
                            findings=ids))
    return DiagnosisOut(findings=findings, causes=causes[:3])


def risk(state: dict, adjustment: int = 0, reason: str = "No adjustment: the rule-based score stands.") -> RiskOut:
    base = state["risk_base"]
    return RiskOut(risk_level=base["level"], risk_score=base["score"], adjustment=adjustment,
                   adjustment_reason=reason, factors=[f["factor"] for f in base["factors"]],
                   predicted_battery_pct=state["history"]["battery_prediction"]["predicted_end_pct"],
                   confidence=base["confidence"])


def _removals_needed(state: dict, mission: list) -> list:
    entry = state["history_entry"]
    rate, capacity = entry.get("battery_mah_per_km"), entry.get("battery_capacity_mah")
    candidates = mission_io.best_removals(mission, len(wp.nav_waypoints(mission)))
    if not rate or not capacity:
        return candidates[:1]
    for count in range(1, len(candidates) + 1):
        remaining = [i for i in mission if i.seq not in candidates[:count]]
        used = 100.0 * rate * mission_io.route_length_m(remaining) / 1000.0 / capacity
        if 100.0 - used >= TARGET_BATTERY_PCT:
            return candidates[:count]
    return candidates


ADVICE = {
    "wind_drift": ("Fly the legs at {speed:g} m/s in strong wind", "cross-track grew with wind",
                   "wind {wind} m/s, cross-track {xtrack} m"),
    "speed_too_high": ("Reduce cruise speed to {speed:g} m/s", "the airframe reached its tilt limit",
                       "max roll {roll} deg, cross-track {xtrack} m"),
    "low_battery": ("Shorten the route or fit a larger battery", "the battery margin was too small",
                    "landed with {battery} % battery"),
    "link_loss": ("Raise the ground antenna and keep the route within radio range",
                  "the telemetry link dropped during the mission", "uptime {uptime} %"),
    "gps_weak": ("Wait for at least 10 satellites before arming", "GPS quality was low",
                 "{sats} satellites, HDOP {hdop}"),
    "vibration": ("Balance the propellers and check the flight controller mounting", "vibration was high",
                  "vibration up to {vib} m/s/s"),
    "setup": ("Enable a geofence sized for the route and keep failsafes on", "a failsafe parameter is 0",
              "{unset}"),
}


def advisor(state: dict, mission: list, diag: DiagnosisOut) -> AdvisorOut:
    m = state["metrics"]
    edits, recommendations = [], []
    legs = m["tracking"]["legs"]
    first_wp = wp.nav_waypoints(mission)[0].seq if mission and wp.nav_waypoints(mission) else None
    for cause in diag.causes:
        if mission and first_wp is not None and cause.category in ("wind_drift", "speed_too_high") \
                and not any(e.action == "set_speed" for e in edits):
            edits.append(Edit(action="set_speed", wp=first_wp, value=SAFE_SPEED_MS, cause=cause.id))
        if mission and cause.category == "low_battery":
            edits += [Edit(action="remove_waypoint", wp=seq, cause=cause.id) for seq in _removals_needed(state, mission)]
    values = {"speed": SAFE_SPEED_MS, "wind": m["wind"]["max_ms"], "xtrack": m["tracking"]["xtrack_max_m"],
              "roll": m["attitude"]["max_roll_deg"], "battery": m["battery"]["remaining_end_pct"],
              "uptime": m["link"]["uptime_pct"], "sats": m["gps"]["min_sats"], "hdop": m["gps"]["max_hdop"],
              "unset": ", ".join(f"{p} = 0" for p in ("FS_THR_ENABLE", "BATT_FS_LOW_ACT", "FENCE_ENABLE")
                                 if (state.get("params") or {}).get(p) == 0),
              "vib": max([v for v in (m["vibration"]["max_x"], m["vibration"]["max_y"], m["vibration"]["max_z"])
                          if v is not None], default=None)}
    for cause in diag.causes:
        text, reason, evidence = ADVICE[cause.category] if cause.category in ADVICE else (cause.cause, "", "")
        if cause.category == "link_loss" and m["link"]["dropouts"]:
            near = m["link"]["dropouts"][0]["near_wp"]
            text += f" (first loss near WP{near})" if near is not None else ""
        if cause.category == "low_battery":
            removed = [e.wp for e in edits if e.action == "remove_waypoint"]
            if removed:
                text = f"Shorten the route by removing WP{', WP'.join(str(s) for s in removed)}"
        recommendations.append(Recommendation(rank=len(recommendations) + 1, text=text.format(**values),
                                              reason=reason, evidence=evidence.format(**values)))
    if not recommendations:
        recommendations.append(Recommendation(rank=1, text="Keep this flight profile; no changes needed",
                                              reason="every metric was Good",
                                              evidence=f"cross-track {m['tracking']['xtrack_max_m']} m, "
                                                       f"landed with {m['battery']['remaining_end_pct']:.0f} % battery"))
    return AdvisorOut(edits=edits[:mission_io.MAX_EDITS], recommendations=recommendations[:3])

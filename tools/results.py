"""The PRD's success metrics and results table, computed from outputs/, data/*/truth.json and history.

    python3 run.py --results            # prints and writes docs/RESULTS.md
"""
import json
from pathlib import Path

from tools import memory, mission_io
from tools import waypoints as wp

INJECTED = {"s1": ({"wind", "xtrack_max_m", "attitude"}, {"wind_drift", "speed_too_high"}),
            "s2": ({"battery_end"}, {"low_battery"}),
            "s3": ({"dropouts", "link_uptime"}, {"link_loss"}),
            "s4": ({"wind", "battery_end", "dropouts", "link_uptime"}, {"wind_drift", "speed_too_high", "low_battery",
                                                                       "link_loss"})}
REFLOWN = ("s1", "s2", "s4")
DROPOUT_TOLERANCE_S = 3.0
TRACKING_TARGET = 0.40
BATTERY_TARGET_PCT = 25.0
PREDICTION_TOLERANCE = 10.0
SPEED_TARGET_S = 60.0


def _load(outputs: Path, run: str):
    path = Path(outputs) / run / "state.json"
    return json.loads(path.read_text()) if path.exists() else None


def _row(name, measured, target, passed):
    return {"metric": name, "measured": measured, "target": target,
            "result": "n/a" if passed is None else ("pass" if passed else "fail")}


def detection(states: dict) -> list:
    flagged = {r: bool(INJECTED[r][0] & {k for k, v in s["metrics"]["status"].items() if v != "good"})
               for r, s in states.items() if r in INJECTED}
    top = {r: (s["agents"]["approved"].get("diagnosis", {}).get("causes") or [{}])[0].get("category")
           for r, s in states.items() if r in INJECTED}
    correct = {r: top[r] in INJECTED[r][1] for r in top}
    return [_row("Fault detection", f"{sum(flagged.values())} of {len(flagged)} ({', '.join(r for r, ok in flagged.items() if ok)})",
                 ">= 3 of 4", sum(flagged.values()) >= 3 if flagged else None),
            _row("Root-cause accuracy", f"{sum(correct.values())} of {len(correct)} (top: "
                 + ", ".join(f"{r} {top[r]}" for r in top) + ")", ">= 3 of 4", sum(correct.values()) >= 3 if correct else None)]


def localisation(states: dict, data: Path) -> dict:
    s3, truth_path = states.get("s3"), Path(data) / "s3" / "truth.json"
    if not s3 or not truth_path.exists():
        return _row("Dropout localisation", "s3 not analysed", "both S3 dropouts within 3 s", None)
    truth = json.loads(truth_path.read_text())["outages"]
    starts = [d["t"] + s3["log_start_unix"] for d in s3["metrics"]["link"]["dropouts"]]
    errors = [min((abs(t - o["start_unix"]) for t in starts), default=None) for o in truth]
    ok = len(truth) == 2 and all(e is not None and e <= DROPOUT_TOLERANCE_S for e in errors)
    return _row("Dropout localisation", ", ".join("missed" if e is None else f"{e:.1f} s off" for e in errors),
                "both S3 dropouts within 3 s", ok)


def false_alarms(states: dict) -> dict:
    s0 = states.get("s0")
    if not s0:
        return _row("False alarms", "s0 not analysed", "0 Bad on S0", None)
    bad = [k for k, v in s0["metrics"]["status"].items() if v == "bad"]
    return _row("False alarms", f"{len(bad)} Bad on S0" + (f" ({', '.join(bad)})" if bad else ""), "0", not bad)


def refly_rows(states: dict, history: list) -> list:
    rows = []
    s1, s1f = states.get("s1"), states.get("s1_fixed")
    if s1 and s1f:
        before, after = s1["metrics"]["tracking"]["xtrack_max_m"], s1f["metrics"]["tracking"]["xtrack_max_m"]
        drop = (before - after) / before
        rows.append(_row("Tracking improvement", f"S1 max cross-track {before} m -> {after} m ({drop:.0%} lower)",
                         ">= 40 % lower", drop >= TRACKING_TARGET))
    else:
        rows.append(_row("Tracking improvement", "S1 re-flight not analysed", ">= 40 % lower", None))
    s2f = states.get("s2_fixed")
    rows.append(_row("Battery margin", f"S2 fixed landed with {s2f['metrics']['battery']['remaining_end_pct']:.0f} %"
                     if s2f else "S2 re-flight not analysed", ">= 25 %",
                     s2f["metrics"]["battery"]["remaining_end_pct"] >= BATTERY_TARGET_PCT if s2f else None))
    errors = []
    for run in REFLOWN:
        fixed = states.get(f"{run}_fixed")
        if not fixed:
            continue
        before = [e for e in history if e.date < fixed["history_entry"]["date"] and not e.parent_run]
        from pipeline import resolve
        mission = wp.load(resolve(fixed["sources"]["mission"]))
        predicted = memory.predict_battery(before, mission_io.route_length_m(mission),
                                           fixed["history_entry"]["battery_capacity_mah"])["predicted_end_pct"]
        actual = fixed["metrics"]["battery"]["remaining_end_pct"]
        if predicted is not None and actual is not None:
            errors.append((run, predicted, actual, abs(predicted - actual)))
    rows.append(_row("Battery prediction error", "; ".join(f"{r}: predicted {p:.0f} %, actual {a:.0f} %" for r, p, a, _ in errors)
                     or "no re-flights", "within 10 points",
                     all(e <= PREDICTION_TOLERANCE for *_, e in errors) if errors else None))
    return rows


def risk_row(states: dict) -> dict:
    levels = {r: states[r]["agents"]["approved"]["risk"]["risk_level"] for r in ("s0", "s2", "s4") if r in states}
    ok = levels.get("s0") == "Low" and levels.get("s2") == "High" and levels.get("s4") == "High"
    return _row("Risk ranking", ", ".join(f"{r} {lvl}" for r, lvl in levels.items()), "S0 Low; S2, S4 High",
                ok if len(levels) == 3 else None)


def grounding_and_speed(states: dict) -> list:
    claims = sum(s["agents"]["verification"]["claims"] for s in states.values())
    rejected = sum(s["agents"]["verification"]["rejected"] for s in states.values())
    times = [s.get("seconds_total") for s in states.values() if s.get("seconds_total")]
    backends = sorted({f"{s['agents']['backend']} {s['agents'].get('model') or ''}".strip() for s in states.values()})
    return [_row("Grounding", f"{rejected} of {claims} claims rejected ({100 * rejected / max(1, claims):.0f} %) "
                 f"via {', '.join(backends)}", "report the rate", None),
            _row("Speed", f"files in -> dashboard ready: max {max(times):.0f} s, median "
                 f"{sorted(times)[len(times) // 2]:.0f} s" if times else "not recorded", "< 60 s",
                 max(times) < SPEED_TARGET_S if times else None)]


def results_table(states: dict) -> list:
    rows = []
    for run in ("s0", "s1", "s2", "s3", "s4"):
        before, after = states.get(run), states.get(f"{run}_fixed")
        if not before:
            continue
        key = {"s1": ("max cross-track m", lambda s: s["metrics"]["tracking"]["xtrack_max_m"]),
               "s2": ("battery at landing %", lambda s: s["metrics"]["battery"]["remaining_end_pct"]),
               "s3": ("link uptime %", lambda s: s["metrics"]["link"]["uptime_pct"]),
               "s4": ("battery at landing %", lambda s: s["metrics"]["battery"]["remaining_end_pct"])}.get(
            run, ("health", lambda s: s["metrics"]["health_score"]))
        risk = lambda s: f"{s['agents']['approved']['risk']['risk_level']} {s['agents']['approved']['risk']['risk_score']}"
        rows.append({"scenario": run, "verdict": before["agents"]["approved"]["flight_summary"]["verdict"],
                     "health": f"{before['metrics']['health_score']} -> {after['metrics']['health_score']}" if after
                     else str(before["metrics"]["health_score"]),
                     "risk": f"{risk(before)} -> {risk(after)}" if after else risk(before),
                     "key metric": f"{key[0]}: {key[1](before)}" + (f" -> {key[1](after)}" if after else ""),
                     "edits flown": flown_edits(run, after)})
    return rows


def flown_edits(run: str, after) -> str:
    """The changes in the mission actually re-flown (data/<run>_fixed) against the original."""
    if not after:
        return "–"
    from pipeline import resolve
    original = wp.load(resolve(f"data/{run}/mission.waypoints"))
    fixed = wp.load(resolve(f"data/{run}_fixed/mission.waypoints"))
    return "; ".join(mission_io.describe_changes(original, fixed)) or "none"


def _markdown(rows: list) -> str:
    if not rows:
        return "_none_\n"
    keys = list(rows[0])
    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    lines += ["| " + " | ".join(str(r[k]).replace("|", "/") for k in keys) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def build(outputs: Path, data: Path, history_path: Path) -> str:
    runs = [p.name for p in Path(outputs).iterdir() if (p / "state.json").exists()] if Path(outputs).is_dir() else []
    states = {r: _load(outputs, r) for r in runs}
    history = memory.load(history_path)
    metrics = (detection(states) + [localisation(states, data), false_alarms(states)] + refly_rows(states, history)
               + [risk_row(states)] + grounding_and_speed(states))
    return ("# AeroMind results\n\nComputed by `python3 run.py --results` from the analysed SITL flights in "
            "`outputs/` and the injected faults in `data/*/truth.json`.\n\n## Success metrics\n\n" + _markdown(metrics)
            + "\n## Results table\n\n" + _markdown(results_table(states)))

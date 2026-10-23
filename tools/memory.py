"""Flight history (history.json): baselines, battery prediction, recurring issues, fix effectiveness.

AeroMind 'learns' by keeping a record of every analysed flight and computing statistics from it;
there is no model training.
"""
import json
import os
import statistics
import tempfile
from pathlib import Path

from agents.schemas import HistoryEntry

MIN_BASELINE_FLIGHTS = 3
SIGMA = 2.0
RECURRING_WINDOW = 5
RECURRING_MIN = 3

#: metric -> (True if higher is worse, smallest standard deviation that counts). The floors keep
#: near-identical simulator flights from turning a 0.1 m difference into "worse than usual".
BASELINE_METRICS = {
    "xtrack_max_m": (True, 0.25),
    "battery_mah_per_km": (True, 50.0),
    "vibration_max": (True, 2.0),
    "wind_max_ms": (True, 1.0),
    "link_uptime_pct": (False, 0.5),
    "health_score": (False, 5.0),
}
#: metrics compared between a re-flown mission and its parent: name -> True if higher is worse
COMPARED = {"xtrack_max_m": True, "battery_end_pct": False, "link_uptime_pct": False, "health_score": False,
            "mission_completion_pct": False, "duration_s": True}


class MemoryError_(RuntimeError):
    pass


def load(path: Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    try:
        flights = json.loads(path.read_text())["flights"]
        return [HistoryEntry.model_validate(f) for f in flights]
    except (ValueError, KeyError, TypeError) as error:
        raise MemoryError_(f"history file {path} is unreadable: {error}") from error


def save(path: Path, entries: list) -> None:
    """Write atomically, so a crash never leaves a half-written history."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"flights": [e.model_dump() for e in entries]}, indent=2)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".history-", suffix=".json")
    with os.fdopen(handle, "w") as out:
        out.write(payload)
    os.replace(temp, path)


def add(entries: list, new: HistoryEntry) -> list:
    """A new list with `new` in place of any earlier analysis of the same run."""
    kept = [e for e in entries if e.run_id != new.run_id]
    return kept + [new]


def baselines(entries: list, exclude: str) -> dict:
    """metric -> {mean, std, n} over past flights, once there are at least three of them."""
    past = [e for e in entries if e.run_id != exclude]
    result = {}
    for metric, (_, floor) in BASELINE_METRICS.items():
        values = [getattr(e, metric) for e in past if getattr(e, metric) is not None]
        if len(values) < MIN_BASELINE_FLIGHTS:
            continue
        result[metric] = {"mean": statistics.fmean(values), "std": max(statistics.pstdev(values), floor),
                          "n": len(values)}
    return result


def worse_than_usual(current: HistoryEntry, base: dict) -> list:
    flags = []
    for metric, stats in base.items():
        value = getattr(current, metric)
        if value is None:
            continue
        higher_is_worse = BASELINE_METRICS[metric][0]
        limit = stats["mean"] + SIGMA * stats["std"] if higher_is_worse else stats["mean"] - SIGMA * stats["std"]
        if (value > limit) if higher_is_worse else (value < limit):
            flags.append({"metric": metric, "value": value, "mean": round(stats["mean"], 2),
                          "std": round(stats["std"], 2), "limit": round(limit, 2)})
    return flags


def predict_battery(entries: list, mission_length_m: float, capacity_mah: float) -> dict:
    """Battery left at landing for a mission of this length: median mAh per km of past flights."""
    rates = [e.battery_mah_per_km for e in entries if e.battery_mah_per_km]
    if not rates or not mission_length_m or not capacity_mah:
        return {"predicted_end_pct": None, "mah_per_km": None, "flights": len(rates)}
    rate = statistics.median(rates)
    used_pct = 100.0 * rate * (mission_length_m / 1000.0) / capacity_mah
    return {"predicted_end_pct": round(max(0.0, 100.0 - used_pct), 1), "mah_per_km": round(rate, 1),
            "flights": len(rates)}


def recurring(entries: list) -> list:
    """Cause categories found in at least 3 of the last 5 flights."""
    recent = entries[-RECURRING_WINDOW:]
    counts = {}
    for e in recent:
        for cause in set(e.causes):
            counts[cause] = counts.get(cause, 0) + 1
    return sorted(cause for cause, count in counts.items() if count >= RECURRING_MIN)


def fix_effectiveness(entries: list) -> list:
    """For each re-flown mission, which metrics improved against the run it fixed."""
    by_id = {e.run_id: e for e in entries}
    results = []
    for e in entries:
        parent = by_id.get(e.parent_run) if e.parent_run else None
        if parent is None:
            continue
        changes = {}
        for metric, higher_is_worse in COMPARED.items():
            before, after = getattr(parent, metric), getattr(e, metric)
            if before is None or after is None:
                continue
            improved = after < before if higher_is_worse else after > before
            changes[metric] = {"before": before, "after": after, "improved": improved}
        # the edits that made this mission were applied to the parent's: they are the parent's edits
        results.append({"run_id": e.run_id, "parent_run": parent.run_id, "edits": parent.edits_applied,
                        "changes": changes})
    return results

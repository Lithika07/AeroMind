"""The deterministic half of an analysis: files -> metrics -> history -> base risk.

Builds the shared state (the blackboard) the agents read and write. Nothing here calls an LLM.
"""
import datetime
from pathlib import Path

from agents.schemas import HistoryEntry, Metrics
from tools import ingest, memory, metrics, mission_io, risk_rules

DEFAULT_CAPACITY_MAH = None


def history_entry(run_id: str, m: Metrics, flight, scenario=None, parent=None, causes=(), edits=()) -> HistoryEntry:
    capacity = (flight.params or {}).get("BATT_CAPACITY")
    distance_km = (m.flight.distance_m or 0) / 1000.0
    used = m.battery.used_pct
    mah_per_km = used / 100.0 * capacity / distance_km if capacity and used is not None and distance_km else None
    vib = [v for v in (m.vibration.max_x, m.vibration.max_y, m.vibration.max_z) if v is not None]
    date = datetime.datetime.fromtimestamp(flight.t0).isoformat(timespec="seconds")
    return HistoryEntry(
        run_id=run_id, date=date, scenario=scenario, parent_run=parent,
        mission_length_m=round(mission_io.route_length_m(flight.mission), 0) if flight.mission else None,
        duration_s=m.flight.duration_s, battery_used_pct=used, battery_pct_per_km=m.battery.used_pct_per_km,
        battery_capacity_mah=capacity, battery_mah_per_km=round(mah_per_km, 1) if mah_per_km else None,
        battery_end_pct=m.battery.remaining_end_pct, mission_completion_pct=m.tracking.mission_completion_pct,
        xtrack_max_m=m.tracking.xtrack_max_m, link_uptime_pct=m.link.uptime_pct, dropouts=len(m.link.dropouts),
        vibration_max=max(vib) if vib else None, wind_max_ms=m.wind.max_ms, health_score=m.health_score,
        causes=list(causes), edits_applied=list(edits))


def analyse(run_id: str, tlogs: list, history_path: Path, mission=None, params=None, notes=None,
            scenario=None, parent=None) -> dict:
    """Metrics, history context and base risk for one flight. Saves the flight to history."""
    flight = ingest.load_flight(tlogs, mission, params, notes)
    m = metrics.compute(flight)
    entry = history_entry(run_id, m, flight, scenario, parent)
    past = [e for e in memory.load(history_path) if e.run_id != run_id]
    entries = memory.add(past, entry)
    base = memory.baselines(entries, exclude=run_id)
    capacity = (flight.params or {}).get("BATT_CAPACITY")
    prediction = memory.predict_battery(entries, entry.mission_length_m or m.flight.distance_m, capacity)
    recurring = memory.recurring(entries)
    risk = risk_rules.base_score(m, flight.params, prediction["predicted_end_pct"], recurring, len(past))
    memory.save(history_path, entries)
    return {
        "run_id": run_id,
        "scenario": scenario,
        "parent_run": parent,
        "sources": flight.sources,
        "notes": flight.notes,
        "metrics": m.model_dump(),
        "mission": {"items": len(flight.mission), "length_m": entry.mission_length_m} if flight.mission else None,
        "params": {k: flight.params[k] for k in risk_rules.FAILSAFE_PARAMS + ("BATT_CAPACITY",)
                   if flight.params and k in flight.params} or None,
        "history": {"flights": len(past), "baselines": base, "worse_than_usual": memory.worse_than_usual(entry, base),
                    "battery_prediction": prediction, "recurring": recurring,
                    "fix_effectiveness": memory.fix_effectiveness(entries)},
        "risk_base": risk,
        "history_entry": entry.model_dump(),
    }

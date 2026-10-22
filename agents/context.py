"""What each agent is shown: the part of the shared state it needs, as compact JSON.

Small contexts keep a local model fast and focused; nothing here is raw telemetry.
"""
import json

from agents import fallbacks, hints
from tools import waypoints as wp


def _metrics_core(m: dict) -> dict:
    return {key: m[key] for key in ("flight", "battery", "wind", "attitude", "gps", "vibration", "status",
                                    "health_score", "warnings")}


def _mission_view(mission) -> list:
    if not mission:
        return []
    return [{"wp": i.seq, "command": wp.command_name(i.command), "alt_m": i.alt,
             **({"speed_ms": i.param2} if i.command == wp.DO_CHANGE_SPEED else {})} for i in mission[1:]]


def build(agent: str, state: dict, outputs: dict, mission=None) -> dict:
    m = state["metrics"]
    notes = state.get("notes")
    if agent == "flight_summary":
        return {"suggested_verdict": fallbacks.verdict(m), "metrics": _metrics_core(m),
                "tracking": {k: m["tracking"][k] for k in ("xtrack_max_m", "mission_completion_pct", "legs")},
                "link": {k: m["link"][k] for k in ("uptime_pct", "dropouts")}, "phases": m["phases"],
                "events": [e for e in m["events"] if e["kind"] != "statustext" or (e["severity"] or 9) <= 4],
                "worse_than_usual": state["history"]["worse_than_usual"], "pilot_notes": notes}
    if agent == "telemetry_link":
        return {"link": m["link"], "statuses": {k: v for k, v in m["status"].items()
                                                if k in ("link_uptime", "dropouts", "packet_loss", "position_rate")},
                "flight_duration_s": m["flight"]["duration_s"]}
    if agent == "diagnosis":
        candidates = [{"category": c, "cause": t, "confidence": conf, "metrics": paths}
                      for c, t, conf, paths in hints.causes(m, state.get("params"))]
        return {"metrics": _metrics_core(m), "tracking": m["tracking"], "link": m["link"],
                "anomalies": m["anomalies"], "events": m["events"][-20:], "params": state.get("params"),
                "candidate_causes": candidates, "pilot_notes": notes}
    if agent == "risk":
        causes = outputs.get("diagnosis", {}).get("causes", [])
        return {"base": {**state["risk_base"],
                         "predicted_battery_pct": state["history"]["battery_prediction"]["predicted_end_pct"]},
                "causes": causes, "history_flights": state["history"]["flights"],
                "recurring": state["history"]["recurring"]}
    if agent == "advisor":
        diagnosis = outputs.get("diagnosis") or {"findings": [], "causes": []}
        from agents.schemas import DiagnosisOut
        suggested = fallbacks.advisor(state, mission, DiagnosisOut.model_validate(diagnosis)) if mission else None
        return {"causes": diagnosis["causes"], "risk": outputs.get("risk"), "mission": _mission_view(mission),
                "metrics": _metrics_core(m), "legs": m["tracking"]["legs"],
                "suggested_edits": [e.model_dump() for e in suggested.edits] if suggested else [],
                "what_worked_before": state["history"]["fix_effectiveness"]}
    raise ValueError(f"no context for agent {agent}")


def to_prompt(context: dict) -> str:
    return json.dumps(context, separators=(",", ":"), default=str)

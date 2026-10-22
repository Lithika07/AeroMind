"""One analysis end to end: files -> metrics -> agents -> fixed mission -> outputs/<run_id>/.

Shared by the CLI (run.py) and the dashboard (app.py). Writes:
    state.json               everything computed and every agent's output (replayable)
    mission_fixed.waypoints  the mission with the approved edits (only when a mission was given)
    changelog.md             which edits were applied or rejected, and why
    report.html              the whole analysis as one printable page
"""
import json
import time
from pathlib import Path

from agents import llm, orchestrator
from agents.schemas import Edit, HistoryEntry
from tools import analysis, link_metrics, memory, mission_io, report
from tools import waypoints as wp

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
HISTORY = ROOT / "history.json"
AUTO = "auto"


def fix_mission(state: dict, mission: list, out_dir: Path) -> dict:
    approved = state["agents"]["approved"]
    edits = [Edit.model_validate(e) for e in approved.get("advisor", {}).get("edits", [])]
    causes = approved.get("diagnosis", {}).get("causes", [])
    advice_only = {c["id"] for c in causes if c["category"] == "link_loss"}
    fixed, applied, rejected = mission_io.apply_edits(mission, edits, {c["id"] for c in causes}, advice_only)
    rejected += state["agents"].get("edit_check", {}).get("dropped", [])
    wp.save(out_dir / "mission_fixed.waypoints", fixed)
    (out_dir / "changelog.md").write_text(mission_io.changelog(state["run_id"], mission, fixed, applied, rejected))
    return {"applied": applied, "rejected": rejected, "length_before_m": round(mission_io.route_length_m(mission)),
            "length_after_m": round(mission_io.route_length_m(fixed)),
            "waypoints_before": len(wp.nav_waypoints(mission)), "waypoints_after": len(wp.nav_waypoints(fixed)),
            "file": "mission_fixed.waypoints"}


def record_outcome(state: dict, history_path: Path) -> None:
    """Store the approved causes and edits with the flight, for recurrence and fix effectiveness."""
    causes = [c["category"] for c in state["agents"]["approved"].get("diagnosis", {}).get("causes", [])]
    edits = [a["text"] for a in (state.get("mission_fix") or {}).get("applied", [])]
    entry = HistoryEntry.model_validate({**state["history_entry"], "causes": causes, "edits_applied": edits})
    memory.save(history_path, memory.add(memory.load(history_path), entry))
    state["history_entry"] = entry.model_dump()


def analyse_flight(run_id: str, tlogs: list, mission=None, params=None, notes=None, scenario=None, parent=None,
                   history_path: Path = HISTORY, out_root: Path = OUTPUTS, backend=AUTO) -> dict:
    started = time.monotonic()
    state, flight = analysis.analyse_with_flight(run_id, tlogs, history_path, mission, params, notes, scenario, parent)
    items = wp.load(mission) if mission else None
    chosen = llm.get_backend() if backend == AUTO else backend
    state["agents"] = orchestrator.run(state, chosen, items)
    out_dir = Path(out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    state["mission_fix"] = fix_mission(state, items, out_dir) if items else None
    record_outcome(state, history_path)
    state["seconds_total"] = round(time.monotonic() - started, 1)
    (out_dir / "state.json").write_text(json.dumps(state, indent=2, default=str))
    (out_dir / "report.html").write_text(report.render(state, link_metrics.quality_per_second(flight)))
    return state


def load_state(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "state.json").read_text())


COMPARED_ROWS = (
    ("verdict", lambda s: s["agents"]["approved"]["flight_summary"]["verdict"]),
    ("health score", lambda s: s["metrics"]["health_score"]),
    ("risk", lambda s: f"{s['agents']['approved']['risk']['risk_level']} {s['agents']['approved']['risk']['risk_score']}"),
    ("max cross-track (m)", lambda s: s["metrics"]["tracking"]["xtrack_max_m"]),
    ("battery at landing (%)", lambda s: s["metrics"]["battery"]["remaining_end_pct"]),
    ("predicted battery (%)", lambda s: s["history"]["battery_prediction"]["predicted_end_pct"]),
    ("link uptime (%)", lambda s: s["metrics"]["link"]["uptime_pct"]),
    ("mission completion (%)", lambda s: s["metrics"]["tracking"]["mission_completion_pct"]),
    ("flight time (s)", lambda s: s["metrics"]["flight"]["duration_s"]),
    ("route (m)", lambda s: (s.get("mission") or {}).get("length_m")),
)


def compare(before: dict, after: dict) -> list:
    """[(metric, before, after, change %)] for the before/after table."""
    rows = []
    for name, get in COMPARED_ROWS:
        try:
            a, b = get(before), get(after)
        except (KeyError, TypeError):
            a = b = None
        change = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
            change = round(100.0 * (b - a) / abs(a), 1)
        rows.append((name, a, b, change))
    return rows

"""AeroMind command line.

    python3 run.py --tlog data/s1/*.tlog --mission data/s1/mission.waypoints --params data/s1/params.param \\
                   --notes "drifted on leg 3"
    python3 run.py --batch data/                       # every flight folder under data/, in time order
    python3 run.py --compare outputs/s1 outputs/s1_fixed
    --llm anthropic|ollama|none                        # default: Claude if ANTHROPIC_API_KEY is set, else Ollama
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import pipeline  # noqa: E402  (reads AEROMIND_* settings after .env is loaded)
from tools.ingest import IngestError  # noqa: E402
from tools.memory import MemoryError_  # noqa: E402


def folder_inputs(folder: Path) -> dict:
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    tlogs = sorted(folder.glob("*.tlog"))
    if not tlogs:
        raise IngestError(f"{folder} has no .tlog files")
    mission, params = folder / "mission.waypoints", folder / "params.param"
    return {"run_id": folder.name, "tlogs": tlogs, "mission": mission if mission.exists() else None,
            "params": params if params.exists() else None, "scenario": meta.get("scenario"),
            "parent": meta.get("parent_run"), "started": meta.get("armed_unix", 0)}


def is_complete_flight(folder: Path) -> bool:
    """A folder with logs, and not a simulator flight still in the air (truth.json but no meta.json)."""
    if not folder.is_dir() or folder.name.startswith(".") or not any(folder.glob("*.tlog")):
        return False
    return not ((folder / "truth.json").exists() and not (folder / "meta.json").exists())


def summary_line(state: dict) -> str:
    m = state["metrics"]
    approved = state["agents"]["approved"]
    risk = approved["risk"]
    bad = [k for k, v in m["status"].items() if v == "bad"]
    fix = state.get("mission_fix") or {}
    return (f"{state['run_id']}: {approved['flight_summary']['verdict']}, health {m['health_score']}, "
            f"bad {bad or '-'}, risk {risk['risk_level']} {risk['risk_score']}, "
            f"edits {len(fix.get('applied', []))}, agents via {state['agents']['backend']} "
            f"in {state['agents']['seconds']} s, {state['agents']['verification']['rejected']} claim(s) rejected")


def print_compare(before: Path, after: Path) -> None:
    rows = pipeline.compare(pipeline.load_state(before), pipeline.load_state(after))
    print(f"{'metric':<26}{before.name:>16}{after.name:>16}{'change':>10}")
    for name, a, b, change in rows:
        print(f"{name:<26}{str(a):>16}{str(b):>16}{(f'{change:+.1f} %' if change is not None else ''):>10}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tlog", nargs="+", type=Path, help="one flight's .tlog file(s)")
    parser.add_argument("--mission", type=Path)
    parser.add_argument("--params", type=Path)
    parser.add_argument("--notes")
    parser.add_argument("--run-id", help="name for this analysis (default: the first log's folder)")
    parser.add_argument("--batch", type=Path, help="analyse every flight folder under this directory")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"), help="two outputs/<run> folders")
    parser.add_argument("--results", action="store_true", help="success metrics and results table -> docs/RESULTS.md")
    parser.add_argument("--llm", choices=("anthropic", "ollama", "none"), help="LLM backend for the agents")
    parser.add_argument("--history", type=Path, default=pipeline.HISTORY)
    args = parser.parse_args()
    if args.llm:
        os.environ["AEROMIND_LLM"] = args.llm
    try:
        if args.results:
            from tools import results
            text = results.build(pipeline.OUTPUTS, ROOT / "data", args.history)
            (ROOT / "docs" / "RESULTS.md").write_text(text)
            print(text)
            return 0
        if args.compare:
            print_compare(*args.compare)
            return 0
        if args.batch:
            flights = [folder_inputs(p) for p in args.batch.iterdir() if is_complete_flight(p)]
            for flight in sorted(flights, key=lambda f: f["started"]):
                inputs = {k: v for k, v in flight.items() if k != "started"}
                state = pipeline.analyse_flight(history_path=args.history, **inputs)
                print(summary_line(state), flush=True)
            return 0
        if not args.tlog:
            parser.error("give --tlog, --batch or --compare")
        run_id = args.run_id or args.tlog[0].resolve().parent.name
        state = pipeline.analyse_flight(run_id, args.tlog, args.mission, args.params, args.notes,
                                        history_path=args.history)
        print(f"{summary_line(state)}\noutputs: {pipeline.OUTPUTS / run_id}")
        return 0
    except (IngestError, MemoryError_, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

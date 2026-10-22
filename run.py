"""AeroMind command line.

    python3 run.py --tlog data/s1/*.tlog --mission data/s1/mission.waypoints --params data/s1/params.param \
                   --notes "drifted on leg 3"
    python3 run.py --batch data/                       # every flight folder under data/
    python3 run.py --compare outputs/s1 outputs/s1_fixed
"""
import argparse
import json
import sys
from pathlib import Path

from tools import analysis
from tools.ingest import IngestError

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
HISTORY = ROOT / "history.json"


def save_state(state: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "state.json"
    path.write_text(json.dumps(state, indent=2, default=str))
    return path


def analyse_folder(folder: Path, history: Path, notes: str = None) -> dict:
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    tlogs = sorted(folder.glob("*.tlog"))
    if not tlogs:
        raise IngestError(f"{folder} has no .tlog files")
    mission = folder / "mission.waypoints"
    params = folder / "params.param"
    return analysis.analyse(folder.name, tlogs, history, mission if mission.exists() else None,
                            params if params.exists() else None, notes, meta.get("scenario"), meta.get("parent_run"))


def is_complete_flight(folder: Path) -> bool:
    """A folder with logs, and not a simulator flight still in the air (truth.json but no meta.json)."""
    if not folder.is_dir() or folder.name.startswith(".") or not any(folder.glob("*.tlog")):
        return False
    return not ((folder / "truth.json").exists() and not (folder / "meta.json").exists())


def summary_line(state: dict) -> str:
    m = state["metrics"]
    bad = [k for k, v in m["status"].items() if v == "bad"]
    risk = state["risk_base"]
    return (f"{state['run_id']}: health {m['health_score']}, bad {bad or '-'}, "
            f"risk {risk['level']} {risk['score']} ({risk['confidence']} confidence)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tlog", nargs="+", type=Path, help="one flight's .tlog file(s)")
    parser.add_argument("--mission", type=Path)
    parser.add_argument("--params", type=Path)
    parser.add_argument("--notes")
    parser.add_argument("--run-id", help="name for this analysis (default: the first log's folder)")
    parser.add_argument("--batch", type=Path, help="analyse every flight folder under this directory")
    parser.add_argument("--history", type=Path, default=HISTORY)
    args = parser.parse_args()
    try:
        if args.batch:
            folders = sorted(p for p in args.batch.iterdir() if is_complete_flight(p))
            for folder in folders:
                state = analyse_folder(folder, args.history)
                save_state(state, OUTPUTS / state["run_id"])
                print(summary_line(state))
            return 0
        if not args.tlog:
            parser.error("give --tlog or --batch")
        run_id = args.run_id or args.tlog[0].resolve().parent.name
        state = analysis.analyse(run_id, args.tlog, args.history, args.mission, args.params, args.notes)
        print(f"{summary_line(state)}\nstate: {save_state(state, OUTPUTS / run_id)}")
        return 0
    except (IngestError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

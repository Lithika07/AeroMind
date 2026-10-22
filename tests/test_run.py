import json
from pathlib import Path

import pytest

import pipeline
import run

DATA = Path(__file__).resolve().parents[1] / "data"


def test_incomplete_and_hidden_folders_are_not_flights(tmp_path):
    for name, files in {"flying": ["a.tlog", "truth.json"], ".s1.partial": ["a.tlog"],
                        "done": ["a.tlog", "truth.json", "meta.json"], "user": ["a.tlog"]}.items():
        (tmp_path / name).mkdir()
        for f in files:
            (tmp_path / name / f).write_text("{}")
    assert sorted(p.name for p in tmp_path.iterdir() if run.is_complete_flight(p)) == ["done", "user"]


@pytest.fixture(scope="module")
def s2_outputs(tmp_path_factory):
    if not (DATA / "s2").is_dir():
        pytest.skip("s2 not flown")
    root = tmp_path_factory.mktemp("run")
    history = root / "history.json"
    for run_id in ("s0", "s2"):
        if (DATA / run_id).is_dir():
            inputs = run.folder_inputs(DATA / run_id)
            inputs.pop("started")
            pipeline.analyse_flight(history_path=history, out_root=root / "outputs", backend=None, **inputs)
    return root


def test_pipeline_writes_state_fixed_mission_and_changelog(s2_outputs):
    out = s2_outputs / "outputs" / "s2"
    state = json.loads((out / "state.json").read_text())
    assert state["agents"]["approved"]["risk"]["risk_level"] == "High"
    fix = state["mission_fix"]
    assert fix["waypoints_after"] < fix["waypoints_before"] and fix["length_after_m"] < fix["length_before_m"]
    assert (out / "mission_fixed.waypoints").read_text().startswith("QGC WPL 110")
    assert "## Applied" in (out / "changelog.md").read_text()


def test_history_records_causes_and_edits(s2_outputs):
    flights = {f["run_id"]: f for f in json.loads((s2_outputs / "history.json").read_text())["flights"]}
    assert "low_battery" in flights["s2"]["causes"]
    assert any(e.startswith("remove_waypoint") for e in flights["s2"]["edits_applied"])


def test_compare_rows(s2_outputs):
    out = s2_outputs / "outputs"
    if not (out / "s0").is_dir():
        pytest.skip("s0 not flown")
    rows = {name: (a, b, change) for name, a, b, change in
            pipeline.compare(pipeline.load_state(out / "s0"), pipeline.load_state(out / "s2"))}
    assert rows["battery at landing (%)"][1] < rows["battery at landing (%)"][0]
    assert rows["battery at landing (%)"][2] < 0

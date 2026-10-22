import json
from pathlib import Path

import pytest

import run

DATA = Path(__file__).resolve().parents[1] / "data"


def test_incomplete_and_hidden_folders_are_not_flights(tmp_path):
    (tmp_path / "flying").mkdir()
    (tmp_path / "flying" / "a.tlog").write_bytes(b"")
    (tmp_path / "flying" / "truth.json").write_text("{}")
    (tmp_path / ".s1.partial").mkdir()
    (tmp_path / ".s1.partial" / "a.tlog").write_bytes(b"")
    (tmp_path / "done").mkdir()
    (tmp_path / "done" / "a.tlog").write_bytes(b"")
    (tmp_path / "done" / "truth.json").write_text("{}")
    (tmp_path / "done" / "meta.json").write_text("{}")
    (tmp_path / "user").mkdir()
    (tmp_path / "user" / "a.tlog").write_bytes(b"")
    assert sorted(p.name for p in tmp_path.iterdir() if run.is_complete_flight(p)) == ["done", "user"]


def test_s0_analysis_fills_state_and_history(tmp_path):
    if not (DATA / "s0").is_dir():
        pytest.skip("s0 not flown")
    history = tmp_path / "history.json"
    state = run.analyse_folder(DATA / "s0", history)
    assert state["metrics"]["health_score"] >= 80
    assert state["risk_base"]["level"] == "Low"
    assert state["history"]["battery_prediction"]["predicted_end_pct"] > 70
    saved = json.loads(history.read_text())["flights"]
    assert [f["run_id"] for f in saved] == ["s0"]
    # analysing the same run again replaces it
    run.analyse_folder(DATA / "s0", history)
    assert len(json.loads(history.read_text())["flights"]) == 1

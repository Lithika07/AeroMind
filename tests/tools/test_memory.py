import json

import pytest

from agents.schemas import HistoryEntry
from tools import memory


def entry(run_id, **values):
    defaults = {"date": "2026-10-22", "battery_capacity_mah": 10000.0, "battery_mah_per_km": 1500.0,
                "xtrack_max_m": 0.5, "link_uptime_pct": 100.0, "vibration_max": 5.0, "health_score": 100}
    return HistoryEntry(run_id=run_id, **{**defaults, **values})


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "history.json"
    memory.save(path, [entry("a"), entry("b")])
    assert [e.run_id for e in memory.load(path)] == ["a", "b"]
    assert json.loads(path.read_text())["flights"][0]["run_id"] == "a"


def test_load_missing_file_is_empty(tmp_path):
    assert memory.load(tmp_path / "none.json") == []


def test_load_rejects_a_corrupt_file(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not json")
    with pytest.raises(memory.MemoryError_, match="history"):
        memory.load(path)


def test_add_replaces_the_same_run_and_keeps_others():
    entries = memory.add([entry("a"), entry("b", health_score=50)], entry("b", health_score=90))
    assert [(e.run_id, e.health_score) for e in entries] == [("a", 100), ("b", 90)]


def test_baselines_need_three_past_flights():
    assert memory.baselines([entry("a"), entry("b")], exclude="c") == {}
    base = memory.baselines([entry("a"), entry("b"), entry("c", xtrack_max_m=1.0)], exclude="x")
    assert base["xtrack_max_m"]["n"] == 3
    assert base["xtrack_max_m"]["mean"] == pytest.approx(2.0 / 3.0)


def test_worse_than_usual_flags_beyond_two_sigma_in_the_bad_direction():
    past = [entry(str(i), xtrack_max_m=0.5 + 0.01 * i, link_uptime_pct=100.0) for i in range(5)]
    current = entry("now", xtrack_max_m=6.8, link_uptime_pct=93.0, health_score=100)
    flags = {f["metric"] for f in memory.worse_than_usual(current, memory.baselines(past, exclude="now"))}
    assert flags == {"xtrack_max_m", "link_uptime_pct"}


def test_better_than_usual_is_not_flagged():
    past = [entry(str(i)) for i in range(4)]
    assert memory.worse_than_usual(entry("now", xtrack_max_m=0.1), memory.baselines(past, exclude="now")) == []


def test_battery_prediction_uses_mah_per_km_and_the_next_capacity():
    history = [entry("a", battery_mah_per_km=1500), entry("b", battery_mah_per_km=1600),
               entry("c", battery_mah_per_km=9000)]
    prediction = memory.predict_battery(history, mission_length_m=1200, capacity_mah=2200)
    # median 1600 mAh/km * 1.2 km = 1920 mAh of 2200 -> 12.7 % left
    assert prediction["predicted_end_pct"] == pytest.approx(12.7, abs=0.1)
    assert prediction["flights"] == 3


def test_battery_prediction_without_history_is_none():
    assert memory.predict_battery([], 1200, 10000)["predicted_end_pct"] is None


def test_recurring_causes_in_three_of_the_last_five():
    history = [entry(str(i), causes=c) for i, c in enumerate(
        [["link_loss"], ["wind_drift"], ["wind_drift", "link_loss"], [], ["wind_drift"], ["wind_drift"]])]
    assert memory.recurring(history) == ["wind_drift"]


def test_fix_effectiveness_compares_with_the_parent_run():
    history = [entry("s1", xtrack_max_m=6.0, battery_end_pct=40.0),
               entry("s1_fixed", parent_run="s1", xtrack_max_m=2.0, battery_end_pct=45.0,
                     edits_applied=["set_speed WP3 7 m/s"])]
    (result,) = memory.fix_effectiveness(history)
    assert result["run_id"] == "s1_fixed" and result["parent_run"] == "s1"
    assert result["changes"]["xtrack_max_m"] == {"before": 6.0, "after": 2.0, "improved": True}
    assert result["edits"] == ["set_speed WP3 7 m/s"]

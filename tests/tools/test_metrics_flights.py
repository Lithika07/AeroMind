"""Metrics on the real SITL flights in data/ (skipped when a flight has not been flown yet)."""
import json
from pathlib import Path

import pytest

from tools import ingest, metrics

DATA = Path(__file__).resolve().parents[2] / "data"


def load(run: str):
    folder = DATA / run
    if not folder.is_dir():
        pytest.skip(f"{run} not flown")
    flight = ingest.load_flight(sorted(folder.glob("*.tlog")), folder / "mission.waypoints", folder / "params.param")
    return flight, metrics.compute(flight), folder


@pytest.fixture(scope="module")
def s0():
    return load("s0")


def test_s0_baseline_is_healthy_with_no_bad_metric(s0):
    _, m, _ = s0
    assert m.health_score >= 80
    assert "bad" not in m.status.values()
    assert m.tracking.mission_completion_pct == 100.0
    assert m.link.dropouts == [] and m.link.uptime_pct == 100.0


def test_s0_phases_are_takeoff_eight_legs_rtl_land(s0):
    _, m, _ = s0
    names = [p.name for p in m.phases]
    assert names[0] == "Takeoff" and names[-2:] == ["RTL", "Land"]
    assert [p.name for p in m.phases if p.kind == "leg"] == [f"Leg {i} (to WP{i + 2})" for i in range(1, 9)]


def test_s0_battery_and_distance(s0):
    _, m, _ = s0
    assert 1100 < m.flight.distance_m < 1400
    assert m.battery.remaining_end_pct > 70
    assert m.battery.used_pct_per_km > 0


def test_s3_dropouts_match_the_injected_outages():
    flight, m, folder = load("s3")
    truth = json.loads((folder / "truth.json").read_text())["outages"]
    assert len(m.link.dropouts) == len(truth) == 2
    for dropout, outage in zip(m.link.dropouts, truth):
        assert abs(dropout.t + flight.t0 - outage["start_unix"]) <= 3.0
        assert dropout.near_wp is not None
    assert m.status["link_uptime"] == "bad"

"""Regressions for the defects found in the code review (2026-10-22)."""
import pandas as pd
import pytest
from pymavlink.dialects.v20 import ardupilotmega as mavlink

from agents import base, fallbacks
from agents.schemas import Edit, FlightSummaryOut, Metrics
from dashboard.text import plain
from sim import scenarios, world
from sim.tlog import TlogWriter
from tools import ingest, metrics, mission_io


def write_log(tmp_path, armed_flags):
    mav = mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
    writer = TlogWriter(tmp_path)
    for k, armed in enumerate(armed_flags):
        writer.write(mav.heartbeat_encode(mavlink.MAV_TYPE_HEXAROTOR, mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                                          128 if armed else 0, 3, 0).pack(mav), now=100.0 + k)
    writer.close()
    return writer.paths


@pytest.mark.parametrize("flags", [[False, False], [True]])
def test_logs_with_almost_nothing_still_produce_a_summary(tmp_path, flags):
    flight = ingest.load_flight(write_log(tmp_path, flags))
    m = metrics.compute(flight).model_dump()
    state = {"metrics": m}
    summary = fallbacks.flight_summary(state)
    assert "unknown" in summary.summary or "Battery level was not reported" in summary.summary


def test_missing_nav_and_hud_messages_do_not_crash(tmp_path):
    flight = ingest.load_flight(write_log(tmp_path, [True, True, True, False]))
    assert metrics.column(pd.DataFrame({"t": [1.0]}), "xtrack_error").empty
    metrics.compute(flight)


@pytest.fixture(scope="module")
def mission():
    return scenarios.mission(scenarios.load()["s0"], scenarios.load_route(), world.origin(world.DEFAULT_WORLD))


def test_home_can_never_be_edited(mission):
    _, applied, rejected = mission_io.apply_edits(mission, [Edit(action="set_speed", wp=0, value=5, cause="C1")], {"C1"})
    assert applied == [] and "home" in rejected[0]["reason"]


def test_an_edit_cannot_add_obstacle_conflicts_to_a_mission_that_already_has_one(monkeypatch, mission):
    # one existing conflict; lowering/raising any waypoint off 30 m adds a second
    monkeypatch.setattr(mission_io, "obstacle_conflicts",
                        lambda items: ["radio_mast"] * (2 if any(i.alt not in (30.0, 0.0, 584.0) for i in items) else 1))
    _, applied, rejected = mission_io.apply_edits(
        mission, [Edit(action="change_altitude", wp=4, value=10, cause="C1")], {"C1"})
    assert applied == [] and "too low" in rejected[0]["reason"]


def test_unexpected_backend_errors_fall_back(states):
    state, mission = states.get("s0") or pytest.skip("s0 not flown")

    class Broken:
        name, model = "broken", None

        def complete(self, *_):
            raise ConnectionResetError("server went away")

    result = base.run_agent("risk", state, {}, Broken(), lambda: fallbacks.risk(state), mission)
    assert result.source == "fallback" and "ConnectionResetError" in result.errors[0]


def test_an_invalid_reply_is_retried_with_the_error(states):
    state, mission = states.get("s0") or pytest.skip("s0 not flown")
    prompts = []

    class Flaky:
        name, model = "flaky", None

        def complete(self, system, user, schema):
            prompts.append(user)
            if len(prompts) == 1:
                raise base.LLMError("risk_score missing")
            return fallbacks.risk(state)

    result = base.run_agent("risk", state, {}, Flaky(), lambda: fallbacks.risk(state), mission)
    assert result.source == "llm" and "risk_score missing" in prompts[1]


def test_llm_cannot_make_the_verdict_milder_than_the_data(states):
    state, _ = states.get("s4") or pytest.skip("s4 not flown")
    rule = fallbacks.verdict(state["metrics"])
    soft = FlightSummaryOut(verdict="Good", summary="fine", flight_story=[])
    assert base.guard("flight_summary", soft, state, True).verdict == rule


def test_plain_text_cannot_load_images_or_links():
    shown = plain("![x](https://example.com/?leak=1)")
    assert "![" not in shown and "](" not in shown

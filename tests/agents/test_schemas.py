import pydantic
import pytest

from agents import schemas

PRD_METRICS = {
    "flight": {"duration_s": 412, "distance_m": 1850, "max_alt_m": 40.2, "max_speed_ms": 12.1},
    "battery": {"remaining_end_pct": 18, "used_pct_per_km": 44.3},
    "tracking": {"xtrack_max_m": 6.8, "legs": [{"leg": 3, "to_wp": 5, "t_start": 120, "t_end": 168,
                                                 "xtrack_max_m": 6.8, "speed_ms": 12.0}]},
    "vibration": {"max_x": 14, "max_y": 16, "max_z": 22, "clip_total": 0},
    "gps": {"min_sats": 12, "max_hdop": 0.9},
    "wind": {"max_ms": 9.1},
    "link": {"uptime_pct": 94.1, "packet_loss_pct": 3.2, "rssi": None,
             "dropouts": [{"t": 233, "duration_s": 12.4, "lat": 23.0231, "lon": 72.5702, "near_wp": 5}]},
    "phases": [{"name": "Leg 3", "t_start": 120, "t_end": 168, "kind": "leg"}],
    "anomalies": [{"t": 141, "signal": "current", "value": 38.0, "z": 4.1}],
    "events": [{"t": 385, "text": "Battery low"}],
    "status": {"xtrack_max_m": "bad", "link_uptime": "bad", "battery_end": "bad"},
    "health_score": 25,
}

PRD_OUTPUTS = {
    "flight_summary": {"verdict": "Needs attention", "summary": "s",
                       "flight_story": [{"phase": "Leg 3", "status": "bad", "text": "Drifted 6.8 m in 9.1 m/s wind"}]},
    "telemetry_link": {"link_verdict": "caution", "safe_for_mission": False,
                       "link_findings": [{"id": "L1", "text": "Link lost 12.4 s near WP5",
                                          "metric": "link.dropouts[0].duration_s", "value": 12.4}]},
    "diagnosis": {"findings": [{"id": "F1", "text": "x", "metric": "tracking.xtrack_max_m", "value": 6.8}],
                  "causes": [{"id": "C1", "cause": "Crosswind drift at high speed", "confidence": 0.8,
                              "findings": ["F1", "F3"]}]},
    "risk": {"risk_level": "High", "risk_score": 65, "adjustment": 0, "adjustment_reason": "none",
             "predicted_battery_pct": 16, "factors": ["battery < 20%", "telemetry dropout", "wind"],
             "confidence": "normal"},
    "advisor": {"edits": [{"action": "set_speed", "wp": 3, "value": 7, "cause": "C1"}],
                "recommendations": [{"rank": 1, "text": "Reduce speed to 7 m/s", "reason": "r", "evidence": "e"}]},
    "verifier": {"verdicts": [{"agent": "diagnosis", "claim_id": "F1", "status": "supported", "reason": "ok"}]},
}


def test_prd_metrics_example_validates():
    metrics = schemas.Metrics.model_validate(PRD_METRICS)
    assert metrics.link.dropouts[0].near_wp == 5
    assert metrics.link.rssi is None


def test_empty_metrics_are_all_null():
    metrics = schemas.Metrics()
    assert metrics.flight.duration_s is None and metrics.health_score == 100


@pytest.mark.parametrize("agent", schemas.AGENT_NAMES)
def test_prd_agent_examples_validate(agent):
    schemas.AGENT_OUTPUTS[agent].model_validate(PRD_OUTPUTS[agent])


def test_plan_validates():
    plan = schemas.Plan.model_validate({"plan": [{"agent": "flight_summary", "reason": "always first"}]})
    assert plan.source == "llm"


@pytest.mark.parametrize("model, data", [
    (schemas.RiskOut, {**PRD_OUTPUTS["risk"], "adjustment": 15}),
    (schemas.RiskOut, {**PRD_OUTPUTS["risk"], "risk_level": "Extreme"}),
    (schemas.Cause, {"id": "C1", "cause": "x", "confidence": 1.5, "findings": []}),
    (schemas.Edit, {"action": "teleport", "wp": 1, "cause": "C1"}),
    (schemas.FlightSummaryOut, {**PRD_OUTPUTS["flight_summary"], "extra": 1}),
    (schemas.Metrics, {"health_score": 101}),
])
def test_invalid_shapes_are_rejected(model, data):
    with pytest.raises(pydantic.ValidationError):
        model.model_validate(data)


def test_advisor_limits_edits_and_recommendations():
    edit = {"action": "add_hold", "wp": 3, "value": 2, "cause": "C1"}
    with pytest.raises(pydantic.ValidationError):
        schemas.AdvisorOut.model_validate({"edits": [edit] * 6, "recommendations": []})


def test_contracts_are_immutable():
    metrics = schemas.Metrics()
    with pytest.raises(pydantic.ValidationError):
        metrics.health_score = 5


def test_every_agent_output_has_a_json_schema():
    for model in schemas.AGENT_OUTPUTS.values():
        assert model.model_json_schema()["type"] == "object"

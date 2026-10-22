import pytest

from agents import orchestrator
from agents.llm import LLMError
from agents.schemas import Plan

from .conftest import FakeBackend


def man(**overrides):
    base = {"inputs": {"tlog_files": 1, "mission": True, "params": True, "pilot_notes": False}, "statuses": {},
            "problems": [], "link_all_good": True, "history_flights": 5, "dropouts": 0}
    return {**base, **overrides}


def agents_of(plan):
    return [s.agent for s in plan.plan]


def test_default_plan_without_problems_skips_diagnosis():
    plan = orchestrator.default_plan(man())
    assert agents_of(plan) == ["flight_summary", "telemetry_link", "risk", "advisor", "verifier"]
    assert "one-line" in plan.plan[1].reason


def test_default_plan_with_problems_and_no_mission():
    plan = orchestrator.default_plan(man(problems=["wind"], inputs={"mission": False}, history_flights=1))
    assert agents_of(plan)[2] == "diagnosis"
    assert "advice only" in plan.plan[4].reason and "confidence low" in plan.plan[3].reason


def test_llm_plan_is_forced_into_the_rules():
    proposal = Plan(plan=[{"agent": "verifier", "reason": "v"}, {"agent": "diagnosis", "reason": "d"},
                          {"agent": "flight_summary", "reason": "f"}, {"agent": "flight_summary", "reason": "again"}])
    plan = orchestrator.checked_plan(proposal, man())
    assert agents_of(plan) == ["flight_summary", "telemetry_link", "risk", "advisor", "verifier"]
    assert plan.plan[0].reason == "f" and "(added by rule)" in plan.plan[1].reason


def test_without_backend_everything_is_rule_based(states):
    state, mission = states.get("s4") or pytest.skip("s4 not flown")
    result = orchestrator.run(state, None, mission)
    assert result["plan"]["source"] == "default"
    assert {a["source"] for a in result["agents"].values()} <= {"fallback", "rule"}
    assert result["verification"]["rejected"] == 0
    assert {c["category"] for c in result["approved"]["diagnosis"]["causes"]} == {"link_loss", "wind_drift",
                                                                                "low_battery"}


def test_failing_llm_falls_back_after_retries(states):
    state, mission = states.get("s1") or pytest.skip("s1 not flown")
    backend = FakeBackend({})
    result = orchestrator.run(state, backend, mission)
    assert result["plan"]["source"] == "default" and result["plan_error"]
    assert result["agents"]["flight_summary"]["source"] == "fallback"
    assert len(result["agents"]["flight_summary"]["errors"]) == 2


def test_risk_score_is_base_plus_adjustment_whatever_the_llm_says(states):
    state, mission = states.get("s2") or pytest.skip("s2 not flown")
    risk = {"risk_level": "Low", "risk_score": 3, "adjustment": -10, "adjustment_reason": "a shorter route is planned",
            "factors": ["made up"], "predicted_battery_pct": 99, "confidence": "normal"}
    result = orchestrator.run(state, FakeBackend({"RiskOut": [risk]}), mission)
    approved = result["approved"]["risk"]
    base = state["risk_base"]["score"]
    assert approved["risk_score"] == base - 10
    assert approved["factors"] == [f["factor"] for f in state["risk_base"]["factors"]]
    assert approved["predicted_battery_pct"] == state["history"]["battery_prediction"]["predicted_end_pct"]


def test_agent_with_many_rejections_is_rerun_with_the_reasons(states):
    state, mission = states.get("s3") or pytest.skip("s3 not flown")
    bad = {"link_verdict": "good", "safe_for_mission": True,
           "link_findings": [{"id": "L1", "text": "Link lost 99 s", "metric": "link.uptime_pct", "value": 10}]}
    good = {"link_verdict": "bad", "safe_for_mission": False,
            "link_findings": [{"id": "L1", "text": "uptime", "metric": "link.uptime_pct",
                               "value": state["metrics"]["link"]["uptime_pct"]}]}
    backend = FakeBackend({"TelemetryLinkOut": [bad, good]})
    result = orchestrator.run(state, backend, mission)
    assert [r["agent"] for r in result["verification"]["reruns"]] == ["telemetry_link"]
    rerun_prompt = [u for k, u in backend.calls if k == "TelemetryLinkOut"][-1]
    assert "rejected by the verifier" in rerun_prompt
    link = result["approved"]["telemetry_link"]
    assert link["link_verdict"] == "bad" and link["link_findings"][0]["value"] == state["metrics"]["link"]["uptime_pct"]


def test_invalid_llm_edits_are_replaced_by_valid_rule_edits(states):
    state, mission = states.get("s1") or pytest.skip("s1 not flown")
    advisor = {"edits": [{"action": "remove_waypoint", "wp": 1, "cause": "C1"}],
               "recommendations": [{"rank": 1, "text": "remove_waypoint WP1", "reason": "r", "evidence": "e"}]}
    result = orchestrator.run(state, FakeBackend({"AdvisorOut": [advisor]}), mission)
    assert result["edit_check"]["replaced_by_rules"] is True
    assert result["approved"]["advisor"]["edits"][0]["action"] == "set_speed"
    assert all("WP1" not in r["text"] for r in result["approved"]["advisor"]["recommendations"])


def test_link_healthy_needs_no_llm_call(states):
    state, mission = states.get("s0") or pytest.skip("s0 not flown")
    backend = FakeBackend({})
    result = orchestrator.run(state, backend, mission)
    assert result["agents"]["telemetry_link"]["source"] == "rule"
    assert all(k != "TelemetryLinkOut" for k, _ in backend.calls)
    assert "diagnosis" not in result["agents"]

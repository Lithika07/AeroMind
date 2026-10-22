import pytest

from agents import verifier

METRICS = {"link": {"uptime_pct": 92.4, "dropouts": [{"t": 90.1, "duration_s": 12.3}]},
           "tracking": {"xtrack_max_m": 1.8}, "health_score": 50}


@pytest.mark.parametrize("path, expected", [
    ("link.uptime_pct", (True, 92.4)),
    ("link.dropouts[0].duration_s", (True, 12.3)),
    ("link.dropouts[3].duration_s", (False, None)),
    ("link.nothing", (False, None)),
    ("health_score", (True, 50)),
])
def test_resolve(path, expected):
    assert verifier.resolve(METRICS, path) == expected


@pytest.mark.parametrize("claim, ok", [
    ({"text": "uptime", "metric": "link.uptime_pct", "value": 92.4}, True),
    ({"text": "uptime", "metric": "link.uptime_pct", "value": 92.0}, True),       # within 5 %
    ({"text": "uptime", "metric": "link.uptime_pct", "value": 80.0}, False),
    ({"text": "x", "metric": "link.bogus", "value": 1}, False),
    ({"text": "two dropouts", "metric": "link.dropouts", "value": 1}, True),      # list length
    ({"text": "lost 12 s", "metric": None, "value": None}, False),               # number, no metric
    ({"text": "RSSI not reported", "metric": None, "value": None}, True),
])
def test_check_claim(claim, ok):
    assert (verifier.check_claim(claim, METRICS) == "") is ok


def test_numbers_in_text_must_be_in_the_data():
    known = verifier.numbers(METRICS)
    assert verifier.check_text("link lost 12.3 s, uptime 92.4 %", known) == ""
    assert "47 m" in verifier.check_text("drifted 47 m", known)
    assert verifier.check_text("Leg 3 near WP5", known) == ""          # no unit: not a measurement
    assert "no number" in verifier.check_text("F5", known, require_number=True)


def test_recommendations_may_only_name_edits_that_passed():
    kept = {("set_speed", 3)}
    assert verifier.check_edit_mentions("set_speed at WP3 to 6 m/s", kept) == ""
    assert "failed" in verifier.check_edit_mentions("add_hold (value 30 s at WP3)", kept)


def test_rule_based_outputs_always_pass(states):
    from agents import fallbacks
    from agents.schemas import DiagnosisOut
    for run, (state, mission) in states.items():
        diagnosis = fallbacks.diagnosis(state)
        outputs = {"flight_summary": fallbacks.flight_summary(state).model_dump(),
                   "telemetry_link": fallbacks.telemetry_link(state).model_dump(),
                   "diagnosis": diagnosis.model_dump(), "risk": fallbacks.risk(state).model_dump(),
                   "advisor": fallbacks.advisor(state, mission, diagnosis).model_dump()}
        result = verifier.verify(outputs, state, [fallbacks.SAFE_SPEED_MS])
        rejected = [v for v in result.verdicts if v.status == "rejected"]
        assert rejected == [], (run, rejected)


def test_story_status_must_match_the_data(states):
    state, _ = states.get("s1") or pytest.skip("s1 not flown")
    from agents import fallbacks
    summary = fallbacks.flight_summary(state).model_dump()
    leg = next(k for k, line in enumerate(summary["flight_story"]) if line["status"] == "good")
    summary["flight_story"][leg] = {**summary["flight_story"][leg], "status": "bad"}
    result = verifier.verify({"flight_summary": summary}, state)
    (bad,) = [v for v in result.verdicts if v.status == "rejected"]
    assert bad.claim_id == f"story[{leg}]" and "disagrees" in bad.reason


def test_rejection_rates():
    from agents.schemas import ClaimVerdict, VerifierOut
    result = VerifierOut(verdicts=[ClaimVerdict(agent="risk", claim_id="a", status="rejected", reason="x"),
                                   ClaimVerdict(agent="risk", claim_id="b", status="supported", reason="y")])
    assert verifier.rejection_rates(result) == {"risk": 0.5}


@pytest.mark.parametrize("adjustment, reason, ok", [
    (-10, "The link dropped twice, a significant factor. Reducing the score by 10.", False),
    (-5, "The wind factor is overstated: the fixed mission flies at 6 m/s.", True),
    (10, "Wind and the small battery together make a forced landing likely.", True),
    (0, "The rules capture the risk.", True),
])
def test_a_lower_risk_must_name_what_reduces_it(adjustment, reason, ok):
    assert (verifier.check_adjustment({"adjustment": adjustment, "adjustment_reason": reason}) == "") is ok

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
    assert (verifier.check_claim(claim, METRICS, verifier.pools(METRICS)) == "") is ok


def test_numbers_in_text_must_be_in_the_data():
    known = verifier.pools(METRICS)
    assert verifier.check_text("link lost 12.3 s, uptime 92.4 %", known) == ""
    assert "47 m" in verifier.check_text("drifted 47 m", known)
    assert verifier.check_text("Leg 3 near WP5", known) == ""          # no unit: not a measurement
    assert "no number" in verifier.check_text("F5", known, require_number=True)


def test_recommendations_may_only_name_edits_that_passed():
    kept = {("set_speed", 3)}
    assert verifier.check_edit_mentions("set_speed at WP3 to 6 m/s", kept) == ""
    assert "not among" in verifier.check_edit_mentions("add_hold (value 30 s at WP3)", kept)


def test_rule_based_outputs_always_pass(states):
    from agents import fallbacks
    from agents.schemas import DiagnosisOut
    for run, (state, mission) in states.items():
        diagnosis = fallbacks.diagnosis(state)
        outputs = {"flight_summary": fallbacks.flight_summary(state).model_dump(),
                   "telemetry_link": fallbacks.telemetry_link(state).model_dump(),
                   "diagnosis": diagnosis.model_dump(), "risk": fallbacks.risk(state).model_dump(),
                   "advisor": fallbacks.advisor(state, mission, diagnosis).model_dump()}
        result = verifier.verify(outputs, state, {"m/s": [fallbacks.SAFE_SPEED_MS]})
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


def test_numbers_only_match_values_of_the_same_unit():
    known = verifier.pools(METRICS)
    assert "92.4 m/s" in verifier.check_text("flew at 92.4 m/s", known)      # 92.4 is a percentage
    assert "1.8 %" in verifier.check_text("loss 1.8 %", known)               # 1.8 is metres


@pytest.mark.parametrize("text", ["lost link for 45 seconds", "drifted 300 metres", "in 40 knot wind",
                                  "a 2 minute gap", "drifted 0.3 km"])
def test_word_units_are_checked_too(text):
    assert verifier.check_text(text, verifier.pools(METRICS)) != ""


def test_word_units_convert_before_comparing():
    known = verifier.pools({"link": {"duration_s": 120.0}, "wind": {"max_ms": 5.144}})
    assert verifier.check_text("a 2 minute gap in 10 knots", known) == ""


def test_text_value_for_a_numeric_metric_is_rejected():
    claim = {"text": "uptime", "metric": "link.uptime_pct", "value": "high"}
    assert "text" in verifier.check_claim(claim, METRICS, {})
    claim = {"text": "uptime", "metric": "link.uptime_pct", "value": "50"}
    assert "does not match" in verifier.check_claim(claim, METRICS, {})


def test_cause_on_a_rejected_finding_is_rejected(states):
    state, _ = states.get("s2") or pytest.skip("s2 not flown")
    diagnosis = {"findings": [{"id": "F1", "text": "battery", "metric": "battery.remaining_end_pct", "value": 97}],
                 "causes": [{"id": "C1", "cause": "small battery", "category": "low_battery", "confidence": 0.9,
                             "findings": ["F1"]}]}
    verdicts = {v.claim_id: v for v in verifier.verify({"diagnosis": diagnosis}, state).verdicts}
    assert verdicts["F1"].status == verdicts["C1"].status == "rejected"
    assert "rejected findings" in verdicts["C1"].reason


def test_invented_number_in_a_cause_is_rejected(states):
    state, _ = states.get("s1") or pytest.skip("s1 not flown")
    diagnosis = {"findings": [{"id": "F1", "text": "wind", "metric": "wind.max_ms",
                               "value": state["metrics"]["wind"]["max_ms"]}],
                 "causes": [{"id": "C1", "cause": "Motor 3 failing at 2400 rpm and 77 m/s gusts",
                             "category": "other", "confidence": 0.5, "findings": ["F1"]}]}
    verdicts = {v.claim_id: v for v in verifier.verify({"diagnosis": diagnosis}, state).verdicts}
    assert verdicts["C1"].status == "rejected"


def test_a_good_topic_cannot_be_called_a_problem():
    status = {"vibration": "good", "gps_sats": "good", "battery_end": "caution"}
    assert "vibration" in verifier.check_topics("The drone had significant vibrations.", status)
    assert "GPS" in verifier.check_topics("Poor GPS signal was a problem.", status)
    assert verifier.check_topics("Battery was a problem: it landed with 24 %.", status) == ""
    assert verifier.check_topics("Vibration stayed low throughout.", status) == ""


def test_percentages_must_match_to_rounding():
    known = verifier.pools({"link": {"uptime_pct": 98.3}})
    assert verifier.check_text("uptime 98 %", known) == ""
    assert "97.2 %" in verifier.check_text("uptime fell to 97.2 %", known)


def test_edits_named_in_plain_words_must_have_passed():
    kept = {("remove_waypoint", 3)}
    assert verifier.check_edit_mentions("Remove WP3 to shorten the route", kept) == ""
    assert "add_hold" in verifier.check_edit_mentions("Add a hold of 30 seconds at WP5", kept)
    assert "remove_waypoint" in verifier.check_edit_mentions("Consider removing WP7", kept)


def test_recommendations_must_be_plain_words():
    assert "plain words" in verifier.check_plain("change_altitude(wp=2, value=-20.0, cause=C1)")
    assert verifier.check_plain("Lower WP4 by 10 m (we keep 25 m clearance)") == ""


def test_edit_mentions_in_call_form_are_checked():
    assert "change_altitude" in verifier.check_edit_mentions("change_altitude(wp=2, value=-20)", {("set_speed", 3)})


def test_a_caution_phase_cannot_be_called_fine():
    line = {"phase": "Leg 6", "status": "caution", "text": "All metrics were within acceptable limits."}
    assert "caution phase fine" in verifier.check_story_line(line, "caution", {})
    assert verifier.check_story_line({**line, "status": "good"}, "good", {}) == ""

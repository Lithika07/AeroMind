from agents.schemas import Metrics
from tools import risk_rules

SAFE_PARAMS = {"FS_THR_ENABLE": 1, "BATT_FS_LOW_ACT": 2, "FENCE_ENABLE": 1}


def metrics(**status_and_values):
    status = status_and_values.pop("status", {})
    return Metrics.model_validate({**status_and_values, "status": status})


def test_clean_flight_is_low_risk():
    result = risk_rules.base_score(metrics(battery={"remaining_end_pct": 80}), SAFE_PARAMS, 80.0, [], 5)
    assert result == {"score": 0, "level": "Low", "factors": [], "confidence": "normal", "params_checked": True}


def test_prd_example_scores_high():
    m = metrics(battery={"remaining_end_pct": 18}, wind={"max_ms": 9.1},
                link={"uptime_pct": 94.1, "dropouts": [{"t": 233, "duration_s": 12.4}]},
                status={"battery_end": "bad", "wind": "bad", "dropouts": "bad", "link_uptime": "bad"})
    result = risk_rules.base_score(m, SAFE_PARAMS, 16.0, [], 6)
    assert result["score"] == 30 + 15 + 20 + 15
    assert result["level"] == "High"


def test_each_unset_failsafe_adds_ten():
    result = risk_rules.base_score(metrics(), {"FS_THR_ENABLE": 0, "BATT_FS_LOW_ACT": 0, "FENCE_ENABLE": 0},
                                   None, [], 5)
    assert result["score"] == 30 and result["level"] == "Medium"


def test_without_prediction_this_flights_battery_is_used_once():
    m = metrics(battery={"remaining_end_pct": 25}, status={"battery_end": "caution"})
    result = risk_rules.base_score(m, None, None, [], 1)
    assert [f["points"] for f in result["factors"]] == [15]
    assert result["confidence"] == "low" and not result["params_checked"]


def test_caution_link_and_gps_and_recurring():
    m = metrics(gps={"min_sats": 8, "max_hdop": 1.2}, status={"dropouts": "caution", "gps_sats": "caution"})
    result = risk_rules.base_score(m, SAFE_PARAMS, 70.0, ["link_loss"], 5)
    assert result["score"] == 10 + 10 + 10


def test_score_is_capped_at_100():
    m = metrics(battery={"remaining_end_pct": 5}, status={k: "bad" for k in
                ("battery_end", "dropouts", "gps_sats", "wind", "vibration")})
    result = risk_rules.base_score(m, {"FS_THR_ENABLE": 0, "BATT_FS_LOW_ACT": 0, "FENCE_ENABLE": 0}, 5.0, ["x"], 5)
    assert result["score"] == 100


def test_levels():
    assert [risk_rules.level(s) for s in (0, 29, 30, 59, 60, 100)] == ["Low", "Low", "Medium", "Medium", "High", "High"]


def test_predicted_battery_below_ten_percent_is_high_on_its_own_with_one_more_factor():
    m = metrics(battery={"remaining_end_pct": 14}, status={"battery_end": "bad"})
    result = risk_rules.base_score(m, SAFE_PARAMS, 8.0, [], 5)
    assert result["score"] == 45 + 15 and result["level"] == "High"

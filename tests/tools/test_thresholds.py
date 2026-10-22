import pytest

from agents.schemas import Metrics
from tools import thresholds as th


@pytest.mark.parametrize("value, expected", [(0.5, "good"), (1.0, "caution"), (3.0, "caution"),
                                             (3.1, "bad"), (None, None)])
def test_xtrack_bands(value, expected):
    assert th.higher_is_worse(value, th.XTRACK_GOOD_M, th.XTRACK_BAD_M) == expected


@pytest.mark.parametrize("value, expected", [(31, "good"), (30, "caution"), (20, "caution"), (19.9, "bad")])
def test_battery_bands(value, expected):
    assert th.battery_end(value) == expected


@pytest.mark.parametrize("value, expected", [(12, "good"), (10, "good"), (9, "caution"), (6, "caution"), (5, "bad")])
def test_satellite_bands(value, expected):
    assert th.lower_is_worse(value, th.SATS_GOOD, th.SATS_BAD) == expected


@pytest.mark.parametrize("durations, expected", [([], "good"), ([4.0], "caution"), ([9.0, 3.0], "caution"),
                                                 ([12.4], "bad"), ([1, 1, 1], "bad"), (None, None)])
def test_dropout_bands(durations, expected):
    assert th.dropouts(durations) == expected


def test_health_score_penalties_and_floor():
    assert th.health_score({}) == 100
    assert th.health_score({"a": "good", "b": "caution", "c": "bad"}) == 65
    assert th.health_score({k: "bad" for k in "abcde"}) == 0


def test_statuses_skip_missing_metrics():
    statuses = th.statuses(Metrics().model_dump())
    assert statuses == {}


def test_statuses_for_the_prd_example():
    metrics = Metrics.model_validate({
        "battery": {"remaining_end_pct": 18},
        "tracking": {"xtrack_max_m": 6.8},
        "link": {"uptime_pct": 94.1, "packet_loss_pct": 3.2,
                 "dropouts": [{"t": 233, "duration_s": 12.4}]},
        "wind": {"max_ms": 9.1},
    }).model_dump()
    statuses = th.statuses(metrics)
    assert statuses == {"xtrack_max_m": "bad", "battery_end": "bad", "wind": "bad", "link_uptime": "bad",
                        "dropouts": "bad", "packet_loss": "caution"}
    assert th.health_score(statuses) == 0

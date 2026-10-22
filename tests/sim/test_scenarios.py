import math

import pytest

from sim import scenarios
from tools import waypoints as wp

ORIGIN = (-35.363262, 149.165237, 584.0)
CONFIG = {
    "route": {"altitude_m": 30, "waypoints": [[100, 0], [100, 100]]},
    "scenarios": {
        "s0": {"title": "Baseline", "speed_ms": 5},
        "s1": {"title": "Wind", "speed_ms": 12, "wind": {"speed_ms": 10, "from_deg": 90},
               "params": {"BATT_CAPACITY": 2000}, "link": {"windows": [[90, 12]]}},
    },
}


def test_load_builds_typed_scenarios():
    table = scenarios.from_dict(CONFIG)
    s1 = table["s1"]
    assert s1.speed_ms == 12.0
    assert s1.wind == scenarios.Wind(10.0, 90.0)
    assert s1.params == {"BATT_CAPACITY": 2000.0}
    assert s1.link.windows == ((90.0, 12.0),)
    assert table["s0"].wind is None and table["s0"].params == {}


def test_repository_scenarios_file_is_valid():
    table = scenarios.load()
    assert {"s0", "s1", "s2", "s3", "s4"} <= set(table)


@pytest.mark.parametrize("bad, match", [
    ({"speed_ms": 0}, "speed"),
    ({"speed_ms": 30}, "speed"),
    ({"speed_ms": 5, "wind": {"speed_ms": -1, "from_deg": 0}}, "wind"),
    ({"speed_ms": 5, "params": {"bad name": 1}}, "parameter"),
    ({"speed_ms": 5, "surprise": 1}, "unknown"),
])
def test_invalid_scenarios_are_rejected(bad, match):
    config = {**CONFIG, "scenarios": {"x": {"title": "x", **bad}}}
    with pytest.raises(ValueError, match=match):
        scenarios.from_dict(config)


def test_route_altitude_must_clear_the_buildings():
    config = {**CONFIG, "route": {"altitude_m": 10, "waypoints": [[1, 1]]}}
    with pytest.raises(ValueError, match="altitude"):
        scenarios.from_dict(config)


def test_wind_from_east_pushes_west():
    fx, fy = scenarios.Wind(10.0, 90.0).force_n()
    assert fx == pytest.approx(-9.0) and fy == pytest.approx(0.0, abs=1e-9)


def test_wind_from_south_west_pushes_north_east():
    fx, fy = scenarios.Wind(10.0, 225.0).force_n()
    assert fx == pytest.approx(9.0 / math.sqrt(2)) and fy == pytest.approx(9.0 / math.sqrt(2))


def test_mission_layout():
    table = scenarios.from_dict(CONFIG)
    items = scenarios.mission(table["s1"], scenarios.route_from_dict(CONFIG["route"]), ORIGIN)
    assert [i.command for i in items] == [wp.NAV_WAYPOINT, wp.NAV_TAKEOFF, wp.DO_CHANGE_SPEED,
                                          wp.NAV_WAYPOINT, wp.NAV_WAYPOINT, wp.NAV_RETURN_TO_LAUNCH]
    home, takeoff, speed, first = items[:4]
    assert (home.lat, home.lon, home.alt) == (ORIGIN[0], ORIGIN[1], ORIGIN[2])
    assert takeoff.alt == 30.0 and takeoff.frame == wp.FRAME_GLOBAL_RELATIVE_ALT
    assert speed.param2 == 12.0
    assert first.lat == pytest.approx(ORIGIN[0]) and first.lon > ORIGIN[1]
    assert [i.seq for i in items] == list(range(6))

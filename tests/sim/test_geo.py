import pytest

from sim import geo

ORIGIN = (-35.363262, 149.165237)


def test_origin_maps_to_zero():
    assert geo.to_enu(ORIGIN, *ORIGIN) == pytest.approx((0.0, 0.0))


def test_round_trip_within_a_millimetre():
    lat, lon = geo.to_geodetic(ORIGIN, 150.0, -110.0)
    assert geo.to_enu(ORIGIN, lat, lon) == pytest.approx((150.0, -110.0), abs=1e-3)


def test_north_is_positive_y_and_east_positive_x():
    lat, lon = geo.to_geodetic(ORIGIN, 0.0, 100.0)
    assert lat > ORIGIN[0] and lon == pytest.approx(ORIGIN[1])
    lat, lon = geo.to_geodetic(ORIGIN, 100.0, 0.0)
    assert lon > ORIGIN[1] and lat == pytest.approx(ORIGIN[0])


def test_hundred_metres_north_is_about_0_0009_degrees():
    lat, _ = geo.to_geodetic(ORIGIN, 0.0, 100.0)
    assert lat - ORIGIN[0] == pytest.approx(100.0 / 111_132.0, rel=1e-2)


def test_distance_m():
    a = geo.to_geodetic(ORIGIN, 0.0, 0.0)
    b = geo.to_geodetic(ORIGIN, 30.0, 40.0)
    assert geo.distance_m(*a, *b) == pytest.approx(50.0, abs=0.01)

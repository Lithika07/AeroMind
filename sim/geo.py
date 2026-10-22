"""World ENU metres <-> latitude/longitude on the world origin.

A local tangent plane: the world spans a few hundred metres, where the flat-earth error is
millimetres, well below GPS noise.
"""
import math

EARTH_RADIUS_M = 6_378_137.0


def to_geodetic(origin: tuple, east_m: float, north_m: float) -> tuple:
    """(lat, lon) of a point `east_m`, `north_m` from `origin` (lat, lon)."""
    lat0, lon0 = origin[0], origin[1]
    lat = lat0 + math.degrees(north_m / EARTH_RADIUS_M)
    lon = lon0 + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lon


def to_enu(origin: tuple, lat: float, lon: float) -> tuple:
    """(east, north) metres of (lat, lon) from `origin` (lat, lon)."""
    lat0, lon0 = origin[0], origin[1]
    north = math.radians(lat - lat0) * EARTH_RADIUS_M
    east = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    return east, north


def distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    east, north = to_enu((lat_a, lon_a), lat_b, lon_b)
    return math.hypot(east, north)

"""The demo scenarios (sim/scenarios.yaml): the route, and what each scenario does to the flight."""
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tools import geo
from sim.link import LinkFaults
from tools import waypoints as wp

SCENARIOS_FILE = Path(__file__).resolve().parent / "scenarios.yaml"
#: Horizontal drag of the airframe (aeromind_hexa Hydrodynamics xU/yV). With linear drag
#: F = -k (v - w), wind w is exactly a constant extra force k * w.
DRAG_N_PER_MPS = 0.9
MIN_SPEED_MS = 1.0
MAX_SPEED_MS = 20.0
#: 16.4 m buildings and 9 m wires, plus clearance.
MIN_ROUTE_ALT_M = 25.0
PARAM_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,15}$")
KNOWN_KEYS = {"title", "speed_ms", "wind", "params", "link"}
GROUND_SPEED = 1   # DO_CHANGE_SPEED param1


@dataclass(frozen=True)
class Wind:
    speed_ms: float
    from_deg: float   # meteorological: where it blows from, clockwise from north

    def force_n(self) -> tuple:
        """(east, north) force on the airframe in newtons."""
        toward = math.radians(self.from_deg + 180.0)
        magnitude = DRAG_N_PER_MPS * self.speed_ms
        return magnitude * math.sin(toward), magnitude * math.cos(toward)


@dataclass(frozen=True)
class Route:
    altitude_m: float
    waypoints: tuple


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    speed_ms: float
    wind: Wind = None
    params: dict = field(default_factory=dict)
    link: LinkFaults = field(default_factory=LinkFaults)


def route_from_dict(config: dict) -> Route:
    altitude = float(config["altitude_m"])
    if altitude < MIN_ROUTE_ALT_M:
        raise ValueError(f"route altitude {altitude} m is below the {MIN_ROUTE_ALT_M} m minimum")
    points = tuple((float(x), float(y)) for x, y in config["waypoints"])
    if not points:
        raise ValueError("route has no waypoints")
    return Route(altitude, points)


def _scenario(scenario_id: str, config: dict) -> Scenario:
    unknown = set(config) - KNOWN_KEYS
    if unknown:
        raise ValueError(f"{scenario_id}: unknown keys {sorted(unknown)}")
    speed = float(config.get("speed_ms", 0))
    if not MIN_SPEED_MS <= speed <= MAX_SPEED_MS:
        raise ValueError(f"{scenario_id}: speed_ms must be {MIN_SPEED_MS}-{MAX_SPEED_MS}, got {speed}")
    wind = None
    if config.get("wind"):
        wind = Wind(float(config["wind"]["speed_ms"]), float(config["wind"]["from_deg"]))
        if wind.speed_ms < 0:
            raise ValueError(f"{scenario_id}: wind speed must be >= 0")
    params = {str(k): float(v) for k, v in (config.get("params") or {}).items()}
    bad = [name for name in params if not PARAM_NAME.match(name)]
    if bad:
        raise ValueError(f"{scenario_id}: invalid parameter names {bad}")
    return Scenario(scenario_id, str(config.get("title", scenario_id)), speed, wind, params,
                    LinkFaults.from_dict(config.get("link") or {}))


def from_dict(config: dict) -> dict:
    route_from_dict(config["route"])
    return {sid: _scenario(sid, body) for sid, body in config["scenarios"].items()}


def load(path: Path = SCENARIOS_FILE) -> dict:
    return from_dict(yaml.safe_load(Path(path).read_text()))


def load_route(path: Path = SCENARIOS_FILE) -> Route:
    return route_from_dict(yaml.safe_load(Path(path).read_text())["route"])


def mission(scenario: Scenario, route: Route, origin: tuple) -> list:
    """Home, take-off, cruise speed, the route's waypoints, RTL."""
    lat0, lon0, elevation = origin
    rel = wp.FRAME_GLOBAL_RELATIVE_ALT
    items = [wp.Item(0, 1, wp.FRAME_GLOBAL, wp.NAV_WAYPOINT, 0, 0, 0, 0, lat0, lon0, elevation),
             wp.Item(0, 0, rel, wp.NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, route.altitude_m),
             wp.Item(0, 0, rel, wp.DO_CHANGE_SPEED, GROUND_SPEED, scenario.speed_ms, -1, 0, 0, 0, 0)]
    for east, north in route.waypoints:
        lat, lon = geo.to_geodetic((lat0, lon0), east, north)
        items.append(wp.Item(0, 0, rel, wp.NAV_WAYPOINT, 0, 0, 0, 0, round(lat, 7), round(lon, 7),
                             route.altitude_m))
    items.append(wp.Item(0, 0, rel, wp.NAV_RETURN_TO_LAUNCH, 0, 0, 0, 0, 0, 0, 0))
    return wp.renumber(items)

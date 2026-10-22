"""Mission geometry, and applying the Advisor's edits (PRD "Mission I/O")."""
from tools import geo
from tools import waypoints as wp


def route_length_m(items: list) -> float:
    """Horizontal length of home -> each navigation waypoint -> home (RTL), in metres."""
    if not items:
        return 0.0
    home = (items[0].lat, items[0].lon)
    points = [home] + [(i.lat, i.lon) for i in wp.nav_waypoints(items)]
    if wp.ends_with_return(items) and items[-1].command == wp.NAV_RETURN_TO_LAUNCH:
        points.append(home)
    return sum(geo.distance_m(*points[k], *points[k + 1]) for k in range(len(points) - 1))

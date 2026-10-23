"""Mission geometry, and applying the Advisor's edits within hard limits (PRD "Mission edits").

The Advisor only proposes. Each edit is checked here against the limits, applied to a copy of the
mission, and the mission is checked again for the site's obstacles; an edit that fails is rejected
with its reason and listed in the change log. Edits name waypoints by their sequence number in the
mission as flown; numbers are reassigned only when the fixed mission is written.
"""
from dataclasses import replace

from tools import geo, site
from tools import waypoints as wp

MAX_EDITS = 5
SPEED_MIN_MS, SPEED_MAX_MS = 3.0, 10.0
ALT_STEP_MAX_M = 20.0
HOLD_MAX_S = 10.0
MAX_REMOVED_FRACTION = 0.3
PROTECTED = {wp.NAV_TAKEOFF, wp.NAV_RETURN_TO_LAUNCH, wp.NAV_LAND}
GROUND_SPEED = 1


def route_length_m(items: list) -> float:
    """Horizontal length of home -> each navigation waypoint -> home (RTL), in metres."""
    if not items:
        return 0.0
    home = (items[0].lat, items[0].lon)
    points = [home] + [(i.lat, i.lon) for i in wp.nav_waypoints(items)]
    if wp.ends_with_return(items) and items[-1].command == wp.NAV_RETURN_TO_LAUNCH:
        points.append(home)
    return sum(geo.distance_m(*points[k], *points[k + 1]) for k in range(len(points) - 1))


def best_removals(items: list, count: int) -> list:
    """Sequence numbers of up to `count` waypoints whose removal shortens the route most (greedy)."""
    allowed = int(MAX_REMOVED_FRACTION * len(wp.nav_waypoints(items)))
    chosen, current = [], list(items)
    for _ in range(min(count, allowed)):
        options = [(route_length_m([i for i in current if i.seq != item.seq]), item.seq)
                   for item in wp.nav_waypoints(current)]
        if not options:
            break
        _, seq = min(options)
        chosen.append(seq)
        current = [i for i in current if i.seq != seq]
    return chosen


def _segment_distance(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return ((ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2) ** 0.5


def obstacle_conflicts(items: list) -> list:
    """Obstacles a leg passes within its clearance while flying lower than its top."""
    points = [(geo.to_enu(site.SITE_ORIGIN, i.lat, i.lon), i.alt) for i in wp.nav_waypoints(items)]
    conflicts = []
    for (a, alt_a), (b, alt_b) in zip(points, points[1:]):
        for name, (east, north, height, clearance) in site.OBSTACLES.items():
            low = min(alt_a, alt_b) < height + site.VERTICAL_MARGIN_M
            if low and _segment_distance((east, north), a, b) < clearance:
                conflicts.append(name)
    return conflicts


def _check(edit, by_seq: dict, nav_count: int, removed: int) -> str:
    """Why the edit breaks a limit, or '' if it is within them."""
    item = by_seq.get(edit.wp)
    if item is None:
        return f"WP{edit.wp} is not in the mission"
    if edit.wp == 0:
        return "WP0 is home and cannot be edited"
    if edit.action == "set_speed":
        if edit.value is None or not SPEED_MIN_MS <= edit.value <= SPEED_MAX_MS:
            return f"speed must be {SPEED_MIN_MS:g}-{SPEED_MAX_MS:g} m/s"
        return "" if item.command == wp.NAV_WAYPOINT else f"WP{edit.wp} is not a navigation waypoint"
    if item.command != wp.NAV_WAYPOINT or item.command in PROTECTED or edit.wp == 0:
        return f"WP{edit.wp} ({wp.command_name(item.command)}) cannot be edited"
    if edit.action == "change_altitude":
        if edit.value is None or abs(edit.value) > ALT_STEP_MAX_M:
            return f"altitude change must be within +/-{ALT_STEP_MAX_M:g} m"
        final = item.alt + edit.value
        if not site.MIN_ALT_M <= final <= site.MAX_ALT_M:
            return f"altitude {final:g} m is outside {site.MIN_ALT_M:g}-{site.MAX_ALT_M:g} m"
        return ""
    if edit.action == "remove_waypoint":
        if removed + 1 > MAX_REMOVED_FRACTION * nav_count:
            return f"would remove more than {MAX_REMOVED_FRACTION:.0%} of the waypoints"
        return ""
    if edit.action == "add_hold":
        return "" if edit.value is not None and 0 <= edit.value <= HOLD_MAX_S else f"hold must be 0-{HOLD_MAX_S:g} s"
    return f"unknown action {edit.action}"


def _apply_one(items: list, edit) -> list:
    if edit.action == "remove_waypoint":
        return [i for i in items if i.seq != edit.wp]
    if edit.action == "change_altitude":
        return [replace(i, alt=i.alt + edit.value) if i.seq == edit.wp else i for i in items]
    if edit.action == "add_hold":
        return [replace(i, param1=float(edit.value)) if i.seq == edit.wp else i for i in items]
    # set_speed: change the speed command right before the waypoint, or insert one there
    index = next(k for k, i in enumerate(items) if i.seq == edit.wp)
    before = items[index - 1] if index > 0 else None
    if before is not None and before.command == wp.DO_CHANGE_SPEED:
        return items[:index - 1] + [replace(before, param2=float(edit.value))] + items[index:]
    speed = wp.Item(-1, 0, wp.FRAME_GLOBAL_RELATIVE_ALT, wp.DO_CHANGE_SPEED, GROUND_SPEED, float(edit.value),
                    -1, 0, 0, 0, 0)
    return items[:index] + [speed] + items[index:]


def describe(edit) -> str:
    unit = {"set_speed": " m/s", "change_altitude": " m", "add_hold": " s"}.get(edit.action, "")
    value = "" if edit.value is None else f" {edit.value:g}{unit}"
    return f"{edit.action} WP{edit.wp}{value} (cause {edit.cause})"


def apply_edits(items: list, edits: list, cause_ids: set, advice_only_causes: set = frozenset()) -> tuple:
    """(new mission, applied [{edit, text}], rejected [{edit, reason}]). `items` is not modified."""
    current = list(items)
    nav_count = len(wp.nav_waypoints(items))
    applied, rejected = [], []
    removed = 0
    for edit in edits:
        candidate = None
        if len(applied) >= MAX_EDITS:
            reason = f"more than {MAX_EDITS} edits"
        elif edit.cause not in cause_ids:
            reason = f"cause {edit.cause} was not diagnosed"
        elif edit.cause in advice_only_causes:
            reason = f"cause {edit.cause} calls for advice, not a mission edit"
        else:
            reason = _check(edit, {i.seq: i for i in current}, nav_count, removed)
        if not reason:
            candidate = _apply_one(current, edit)
            if not wp.ends_with_return(candidate):
                reason = "the mission would no longer end in RTL or LAND"
            elif len(obstacle_conflicts(candidate)) > len(obstacle_conflicts(current)):
                reason = f"a leg would pass the {', '.join(obstacle_conflicts(candidate))} too low"
        if reason:
            rejected.append({"edit": edit.model_dump(), "reason": reason})
            continue
        current = candidate
        removed += edit.action == "remove_waypoint"
        applied.append({"edit": edit.model_dump(), "text": describe(edit)})
    return wp.renumber(current), applied, rejected


def describe_dict(edit: dict) -> str:
    value = "" if edit.get("value") is None else f" {edit['value']:g}"
    return f"{edit['action']} WP{edit['wp']}{value} (cause {edit['cause']})"


def changelog(run_id: str, original: list, fixed: list, applied: list, rejected: list) -> str:
    lines = [f"# Mission changes for {run_id}", "",
             f"Route: {route_length_m(original):.0f} m -> {route_length_m(fixed):.0f} m, "
             f"{len(wp.nav_waypoints(original))} -> {len(wp.nav_waypoints(fixed))} waypoints.", "",
             "## Applied", ""]
    lines += [f"- {a['text']}" for a in applied] or ["- none"]
    lines += ["", "## Rejected", ""]
    lines += [f"- {describe_dict(r['edit'])}: {r['reason']}" for r in rejected] or ["- none"]
    lines += ["", "Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.",
              "Nothing is uploaded to the vehicle: review the file in a ground station before flying it.", ""]
    return "\n".join(lines)


def describe_changes(original: list, fixed: list) -> list:
    """What differs between two versions of a mission, in waypoint numbers of the original."""
    key = lambda i: (round(i.lat, 6), round(i.lon, 6))
    fixed_nav = {key(i): i for i in wp.nav_waypoints(fixed)}
    changes = []
    removed = [i.seq for i in wp.nav_waypoints(original) if key(i) not in fixed_nav]
    if removed:
        changes.append("removed " + ", ".join(f"WP{seq}" for seq in removed))
    speeds = lambda items: [i.param2 for i in items if i.command == wp.DO_CHANGE_SPEED]
    if speeds(original) != speeds(fixed):
        before, after = speeds(original), speeds(fixed)
        changes.append(f"speed {before[0]:g} → {after[0]:g} m/s" if before and after else "speed changed")
    for item in wp.nav_waypoints(original):
        new = fixed_nav.get(key(item))
        if new is not None and new.alt != item.alt:
            changes.append(f"WP{item.seq} altitude {item.alt:g} → {new.alt:g} m")
        if new is not None and new.param1 != item.param1:
            changes.append(f"WP{item.seq} hold {new.param1:g} s")
    return changes

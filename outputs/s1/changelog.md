# Mission changes for s1

Route: 1330 m -> 1330 m, 8 -> 8 waypoints.

## Applied

- set_speed WP3 6 m/s (cause C1)

## Rejected

- remove_waypoint WP1 (cause C1): WP1 (NAV_TAKEOFF) cannot be edited
- remove_waypoint WP1 (cause C1): WP1 (NAV_TAKEOFF) cannot be edited
- change_altitude WP3 -15 (cause C1): altitude 15 m is outside 25-120 m

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

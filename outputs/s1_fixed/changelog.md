# Mission changes for s1_fixed

Route: 1330 m -> 1330 m, 8 -> 8 waypoints.

## Applied

- set_speed WP3 6 m/s (cause C1)

## Rejected

- change_altitude WP2 -30 (cause C1): WP2 (DO_CHANGE_SPEED) cannot be edited
- add_hold WP2 10 (cause C1): WP2 (DO_CHANGE_SPEED) cannot be edited

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

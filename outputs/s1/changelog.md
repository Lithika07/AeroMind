# Mission changes for s1

Route: 1330 m -> 1330 m, 8 -> 8 waypoints.

## Applied

- set_speed WP3 6 m/s (cause C2)

## Rejected

- set_speed WP2 12 (cause C1): speed must be 3-10 m/s
- change_altitude WP2 -30 (cause C1): WP2 (DO_CHANGE_SPEED) cannot be edited
- add_hold WP2 5 (cause C1): WP2 (DO_CHANGE_SPEED) cannot be edited

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

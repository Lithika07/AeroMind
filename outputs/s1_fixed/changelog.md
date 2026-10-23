# Mission changes for s1_fixed

Route: 1330 m -> 1330 m, 8 -> 8 waypoints.

## Applied

- set_speed WP3 6 m/s (cause C1)

## Rejected

- set_speed WP3 (cause C1): speed must be 3-10 m/s
- change_altitude WP3 -15 (cause C1): altitude 15 m is outside 25-120 m
- remove_waypoint WP1 (cause what_worked_before): cause what_worked_before was not diagnosed

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

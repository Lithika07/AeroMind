# Mission changes for s4

Route: 1330 m -> 1330 m, 8 -> 8 waypoints.

## Applied

- set_speed WP3 6 m/s (cause C3)

## Rejected

- change_altitude WP2 -20 (cause C1): WP2 (DO_CHANGE_SPEED) cannot be edited
- add_hold WP2 10 (cause C2): cause C2 calls for advice, not a mission edit
- remove_waypoint WP1 1 (cause C2): cause C2 calls for advice, not a mission edit

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

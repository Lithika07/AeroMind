# Mission changes for s4_fixed

Route: 1016 m -> 853 m, 6 -> 5 waypoints.

## Applied

- set_speed WP3 6 m/s (cause C2)
- remove_waypoint WP3 (cause C3)

## Rejected

- add_hold WP3 30 (cause C1): cause C1 calls for advice, not a mission edit

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

# Mission changes for s4_fixed

Route: 1016 m -> 853 m, 6 -> 5 waypoints.

## Applied

- remove_waypoint WP3 (cause C1)

## Rejected

- set_speed WP3 6 (cause C1): WP3 is not in the mission
- change_altitude WP3 -30 (cause C2): WP3 is not in the mission

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

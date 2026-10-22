# Mission changes for s2_fixed

Route: 1016 m -> 853 m, 6 -> 5 waypoints.

## Applied

- remove_waypoint WP3 (cause C1)

## Rejected

- change_altitude WP2 -15 (cause C1): WP2 (DO_CHANGE_SPEED) cannot be edited
- change_altitude WP8 -15 (cause C1): altitude 15 m is outside 25-120 m

Waypoint numbers above refer to the mission as flown; the fixed mission is renumbered.
Nothing is uploaded to the vehicle: review the file in a ground station before flying it.

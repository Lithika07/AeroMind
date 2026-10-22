# AeroMind results

Computed by `python3 run.py --results` from the analysed SITL flights in `outputs/` and the injected faults in `data/*/truth.json`.

## Success metrics

| metric | measured | target | result |
|---|---|---|---|
| Fault detection | 4 of 4 (s2, s1, s3, s4) | >= 3 of 4 | pass |
| Root-cause accuracy | 4 of 4 (top: s2 low_battery, s1 wind_drift, s3 link_loss, s4 link_loss) | >= 3 of 4 | pass |
| Dropout localisation | 0.1 s off, 0.1 s off | both S3 dropouts within 3 s | pass |
| False alarms | 0 Bad on S0 | 0 | pass |
| Tracking improvement | S1 max cross-track 1.8 m -> 1.44 m (20% lower) | >= 40 % lower | fail |
| Battery margin | S2 fixed landed with 25 % | >= 25 % | pass |
| Battery prediction error | s1: predicted 80 %, actual 81 %; s2: predicted 31 %, actual 25 %; s4: predicted 31 %, actual 24 % | within 10 points | pass |
| Risk ranking | s0 Low, s2 High, s4 High | S0 Low; S2, S4 High | pass |
| Grounding | 54 of 189 claims rejected (29 %) via ollama qwen2.5:3b | report the rate | n/a |
| Speed | files in -> dashboard ready: max 126 s, median 92 s | < 60 s | fail |

## Results table

| scenario | verdict | health | risk | key metric | edits applied |
|---|---|---|---|---|---|
| s0 | Good | 100 | Low 10 | health: 100 | none |
| s1 | Needs attention | 55 -> 55 | Medium 35 -> Medium 35 | max cross-track m: 1.8 -> 1.44 | set_speed WP3 6 m/s (cause C1) |
| s2 | Needs attention | 75 -> 90 | High 60 -> Low 20 | battery at landing %: 14.0 -> 25.0 | remove_waypoint WP3 (cause C1); remove_waypoint WP4 (cause C1) |
| s3 | Needs attention | 50 | Medium 30 | link uptime %: 92.4 | none |
| s4 | Unsafe | 25 -> 25 | High 80 -> Medium 45 | battery at landing %: 24.0 -> 24.0 | set_speed WP3 6 m/s (cause C2); remove_waypoint WP3 (cause C3); remove_waypoint WP4 (cause C3) |

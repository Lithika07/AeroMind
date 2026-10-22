# AeroMind — Build Plan

How to build everything in the [PRD](AeroMind%20—%20Final%20PRD.pdf), with every flight flown in the
**Aero Sense disaster world**. That world is the only simulation environment. It and the Hexa-X
airframe are copied into `sim/` (provenance in [sim/README.md](../sim/README.md)), so AeroMind does
not depend on the `~/sih_2026` checkout.
The PRD assumed Mission Planner's built-in SITL on Windows. This plan replaces that with the
Gazebo Harmonic + ArduPilot SITL setup this machine already runs. The rest of the PRD (tools, agents,
orchestrator, dashboard, success metrics) stays as written. Where this world changes a PRD number,
the change is listed in [Changes to the PRD](#changes-to-the-prd).

---

## 1. What the world gives us, and what it is missing

Checked on this machine on 2026-10-22:

| Fact | Where | Consequence for AeroMind |
|---|---|---|
| World `aero_sense_disaster.sdf`, Gazebo Harmonic (gz-sim 8), 1 ms physics | copied to `sim/worlds/` | Kept exactly as copied; additions go in a runtime overlay |
| Geodetic origin −35.363262, 149.165237, 584 m; SITL `--home` = origin | world `<spherical_coordinates>`, `simulation.launch.py` | Waypoints are written as world ENU metres → lat/lon on this origin |
| Ground 440 × 360 m centred on (0, 20); drone pad at (0, −110), nose north | `aero_sense_ground`, `drone_spawn` frame | Mission loop must fit roughly x −200…200, y −140…180 |
| Buildings up to 16.4 m, overhead wires 8.6–9.1 m, **radio mast 44 m at (−40, 60)** | sih_2026 `CLAUDE.md` | PRD's 40 m loop would hit the mast. Fly 30 m and keep ≥ 30 m from the mast; min altitude 25 m |
| Bespoke Hexa-X (6S 10 Ah, 2.55 kg, linear drag 0.9 N per m/s) | `aero_sense_description/config/sensors.yaml` | Use this airframe; `hexa.parm` sets frame and EKF3 |
| ArduCopter 4.6-dev from `~/uav_ws/src/ardupilot`, MAVProxy, pymavlink installed | `~/uav_ws` | Nothing new to install for SITL |
| Existing `mav.tlog` has HEARTBEAT, SYS_STATUS, VIBRATION, WIND, NAV_CONTROLLER_OUTPUT, MISSION_CURRENT, GPS_RAW_INT, ATTITUDE, GLOBAL_POSITION_INT, VFR_HUD, STATUSTEXT, RC_CHANNELS | probed `~/.ros/aero_sense/sitl/mav.tlog` | Every PRD metric has a source message |
| **Battery is never simulated**: SYS_STATUS reads 100 %, 12.6 V, 0 A for 5 h | same tlog | S2 (undersized battery) cannot work as-is. **Fix: §3.2** |
| **Wind is always 0**: no wind in the world, and the EKF does not estimate it | same tlog (`WIND.speed` max 0.0) | S1 (strong wind) cannot work as-is. **Fix: §3.3** |
| MAVProxy appends every session to one `mav.tlog` (185 MB, 5 h) | `~/.ros/aero_sense/sitl/` | AeroMind needs one tlog set per flight. **Fix: §3.4** |
| No RADIO_STATUS (perfect link, as the PRD expects) | same tlog | Link analysis uses heartbeat gaps and packet loss, as the PRD planned |
| Port 5760 is used by the Aero Sense dashboard sim if it is running | — | `launch_sim` refuses to start and says so |
| Stream rates are `MAV1_*` in this ArduPilot (were `SR0_*`) | `sim/run/sitl/mav.parm` | Set in `sim/params/aeromind.parm` |

## 2. Decisions taken (change any of them before Phase 0)

1. **Simulation stack = the disaster world + Hexa-X + ArduCopter SITL + MAVProxy, no ROS.**
   Aero Sense's mission manager flies GUIDED and would fight an AUTO mission. AeroMind needs only
   physics and autopilot. World, models, airframe and frame parameters are copied into `sim/`; the
   only external software is Gazebo, the `ardupilot_gazebo` plugin, `arducopter`, MAVProxy and
   pymavlink.
2. **No Mission Planner.** A Python flight runner uploads `.waypoints`, sets fault parameters, arms,
   flies AUTO and resets. This makes all 8 flights scripted and repeatable. QGroundControl can
   still watch on UDP 14550.
3. **LLM:** Claude through the Anthropic API with structured JSON output, with local Ollama
   (Qwen 2.5 7B) as the PRD's fallback. One `.env` line switches between them. Cached
   `state.json` replays cover the demo.
4. **Simulated link faults happen on the recording path only.** `sim/capture.py`, AeroMind's
   recording ground station, drops packets before writing them. The autopilot never loses its own link, which matches the
   PRD's `FS_GCS_ENABLE = 0` assumption.

## 3. Simulation harness (new, not in the PRD)

All of this lives in `aeromind/sim/`.

```
SITL arducopter ──tcp:5760── MAVProxy ──udp:14550──▶ QGC (optional, watching)
   ▲  JSON                       ├──udp:14560──▶ capture.py ──▶ data/<scenario>/*.tlog + truth.json
   │                             │               (link.py faults; tlog.py writer, new file after a 5 s gap)
Gazebo: disaster world (overlay) └──udp:14562──▶ fly_scenario.py (params, mission, arm, AUTO, reset)
   + Hexa-X + ApplyLinkWrench (wind)
```

### 3.1 `launch_sim.py`: world, drone, SITL
**Built** (`python3 -m sim.launch_sim [--gui]`, `--stop`).
- `sim/world.py` writes `sim/run/aero_sense_disaster.sdf`: the copied world plus the
  `gz-sim-apply-link-wrench-system` plugin and an `<include>` of `model://aeromind_hexa` on
  `drone_spawn` (dropped 5 cm onto the pad). No spawn service needed.
- `arducopter --model JSON --defaults copter.parm,hexa.parm,aeromind.parm --home <origin>` runs in
  `sim/run/sitl/` (Lua scripts copied to `scripts/`), then MAVProxy with the outputs above.
- `hexa.parm` lost its proximity/avoidance block: this airframe has no rangefinders, and
  `PRX1_TYPE 2` blocked arming ("PRX1: No Data").
- `aeromind.parm` contains `SCR_ENABLE 1`, `BATT_MONITOR 29` (scripting), `BATT_CAPACITY 10000`,
  the EKF drag terms (§3.3) and the failsafe parameters each scenario changes.
- `--stop` kills only the processes this launcher started.

### 3.2 Battery: `battery.lua` (fixes the 100 % / 0 A battery)
ArduPilot's JSON backend can accept battery fields, but the Gazebo plugin never sends them.
Instead, an ArduPilot Lua script feeds the **scripting battery backend**
(`AP_BattMonitor_Scripting`, present in this build):
- Current is estimated from motor outputs: `I = I_hover · (throttle / throttle_hover)^1.5 + I_avionics`.
- Voltage follows a 6S discharge curve on consumed charge.
- mAh is integrated over time.
- `BATT_CAPACITY` then drives `battery_remaining`, so S2 is just a smaller `BATT_CAPACITY`.

The constants are a model, not measurements, and are documented in the script. **Measured in
SITL:** hover at 30 m is PWM 1527 (a 0.534 motor fraction), drawing about 20.5 A, which is about 3.4 % of 10 Ah per minute.
Check in Phase 1 that S0 (about 1.3 km at 5 m/s) uses 15–20 %. Then pick the S2 capacity (around 2000 mAh) so S2 lands below 20 %, or triggers
the battery failsafe RTL, as the PRD story expects.

### 3.3 Wind: a constant wrench plus EKF drag fusion (fixes wind = 0)
- **Physical wind.** The airframe's drag is linear: F = −k(v − w), with k = 0.9 N per m/s. Wind
  is therefore exactly a constant extra force k·w. For S1, `fly_scenario.py` publishes a
  persistent wrench of 9 N (10 m/s from 90°) to `/world/<name>/wrench/persistent` on the base
  link, and clears it afterwards.
- **Wind in the log.** EKF3 drag fusion: `EK3_DRAG_MCOEF 0.375`, `EK3_DRAG_M_NSE 0.2`,
  `EK3_WIND_P_NSE 1.0`. **Measured:** with defaults the estimate was 0.2 m/s after a minute. With
  `EK3_DRAG_M_NSE`/`EK3_WIND_P_NSE` changed it reached 10.7 m/s from 91° within 10 s (MCOEF was 0.35 at the time),
  against the true 10 m/s from 90°, and the drone held position at 19.9° roll. MCOEF was then
  raised to 0.375 to remove the 7 % over-read (not yet re-flown).
- **Fallback.** If `WIND` still reads 0, `metrics.py` derives wind from steady-flight tilt:
  w = v_ground − m·g·tanθ / k. It is labelled "estimated from attitude".

### 3.4 Link and recording: `capture.py` (built)
- `link.py` holds the fault model, with three modes per scenario:
  - `timed`: drop windows at given seconds into the mission (S3: 2 × 12 s).
  - `zone`: drop while the drone is inside the world's no-network zones (`sim/zones.py`).
    This is a real radio shadow over the north-east earthquake blocks, used in S4.
  - `loss`: random packet loss %.

  Every drop is written to `data/<scenario>/truth.json`. This is the ground truth for the
  "dropout within 3 s" success metric.
- `tlog.py` writes tlog format. It starts a new file after any gap longer than 5 s, as Mission
  Planner does on reconnect. This exercises the PRD's multi-tlog merge.
- **Measured:** a 12 s window 30 s after arming gave an outage at 30.06 s lasting 11.999 s and
  two tlog files. A 1 % configured loss measured 1.1 % from sequence gaps.

### 3.5 Mission and scenarios
- `make_mission.py`: turns ENU waypoints into a QGC WPL 110 `.waypoints` file on the world origin.
- `missions/base_loop.waypoints`:
  - takeoff to 30 m, then 8 waypoints round the society (about 1.3 km), then RTL;
  - stays ≥ 30 m from the mast at (−40, 60);
  - one leg crosses the north-east no-network blocks, so S4's zone dropout lands near a known waypoint.
- `scenarios.yaml` + `fly_scenario.py <id>`:
  1. Set the fault parameters, wrench and link mode.
  2. Upload the mission, arm and switch to AUTO.
  3. Wait until disarmed.
  4. Reset everything and write `data/<id>/{*.tlog, mission.waypoints, params.param, truth.json}`.

| ID | Fault in this world | How |
|---|---|---|
| S0 | none, 5 m/s | — |
| S1 | wind 10 m/s from 90° + 12 m/s cruise | wrench 9 N, `WPNAV_SPEED 1200` |
| S2 | undersized battery | `BATT_CAPACITY ≈ 2000` (calibrated) |
| S3 | two 12 s link dropouts | `link_sim timed` |
| S4 | S1 + S2 + zone dropout over the NE blocks | all of the above, `link_sim zone` |
| S5 (opt.) | weak GPS | `SIM_GPS1_NUMSATS 5`, raised HDOP |

---

## 4. Phases

Each phase ends with a **done-when** check. Do not start the next phase until it passes.
Tests come first in each phase (pytest; 80 % coverage target on `tools/` and `agents/`). Test
fixtures are short slices of real S0–S4 tlogs, never hand-made data.

| # | Phase | Work | Done when | Est. |
|---|---|---|---|---|
| 0 ✅ | **Sim spikes** (done 2026-10-22) | `launch_sim.py`, overlay world, Hexa-X, SITL + MAVProxy; `battery.lua`; wind wrench + EKF drag fusion; `capture.py` | One hand-flown hover shows: battery falling with current > 0; `WIND.speed` ≈ 10 under the wrench (or the attitude fallback agrees within 2 m/s); a 12 s gap in the recorded tlog | 4 h |
| 1 ✅ | **Scenario runner + data** | `make_mission.py`, `base_loop.waypoints`, `scenarios.yaml`, `fly_scenario.py`; fly S0–S4 | Five filled `data/s*/` folders; S0 lands with 80–85 % battery; S2 below 20 %; truth.json for S3 has 2 drops | 3 h |
| 2 ✅ | **Data contracts** | Pydantic models for `metrics.json`, plan, every agent output, `history.json` entry | Schemas validate the PRD examples; tests green | 1 h |
| 3 ✅ | **Ingest + metrics** (PRD step 2) | `ingest.py` (merge tlogs, gap = dropout), `metrics.py` (flight + link, statuses, health), `phases.py`, `anomalies.py`. Packet loss is computed outside dropout windows, because sequence numbers wrap at 256 | S3 shows 2 dropouts within 3 s of truth.json, nearest WP correct; S0 health ≥ 80 with 0 Bad | 3 h |
| 4 ✅ | **Memory + risk rules** (PRD step 3) | `memory.py` (baselines, mean + 2σ, battery % per km, recurring causes), `risk_rules.py` | `run.py --batch data/` stores 5 flights; S0 Low, S2/S4 High from rules alone | 1.5 h |
| 5 ✅ | **Agents + orchestrator** (PRD step 4) | `base.py run_agent()` (JSON schema, one retry), `prompts.py` (6 prompts + cause hints), `orchestrator.py` (manifest → plan → validate → run → Verifier re-run at > 30 % rejected), LLM config | S1 → wind/speed cause + `set_speed` edit; no mission file → plan skips mission edits; Verifier rejects an injected false number | 4 h |
| 6 ✅ | **Mission I/O** (PRD step 5) | `mission_io.py`: bounds checks (§5), apply edits, `mission_fixed.waypoints` + `changelog.md` | Fixed S1 mission uploads to SITL via `fly_scenario.py` and flies AUTO to RTL | 1.5 h |
| 7 ✅ | **CLI** | `run.py` single / `--batch` / `--compare`; `outputs/<run_id>/state.json` cache | S4 end-to-end in < 60 s; `--compare` prints the results table | 1 h |
| 8 ✅ | **Dashboard** (PRD step 6) | Streamlit: Summary tab first, then Track (plotly map on the world origin, path coloured by link), Telemetry, Anomalies, Power & attitude, History, Agents; "Use cached run" | Uploading S4 shows verdict, story, signal strip with the zone dropout near its WP, top 3, risk | 4 h |
| 9 ✅ | **Re-fly + compare** (PRD step 7) | Fly fixed S1, S2, S4 under the same faults; `--compare` | S1 cross-track ≥ 40 % lower; S2 fixed ≥ 25 % battery; battery prediction within 10 points | 1.5 h |
| 10 ✅ | **Report + Ask** (PRD step 8) | Jinja2 `report.html`; Ask tab answering from state with citations | "Why did the link drop?" gets an answer citing `link.dropouts[0]` | 2 h |
| 11 ✅ | **Review + package** (PRD step 9) | Code + security review (API key in `.env`, upload validation); README with sim setup; results table; cached runs S0–S4 + re-flights; 6 slides; 2-min video | Fresh clone + README → demo runs from cache with no network | 2 h |

Status 2026-10-23: all phases done. Not produced: the 6-slide deck and the 2-minute video.
Measured results are in [RESULTS.md](RESULTS.md) once `python3 run.py --results` has run.

About 29 hours in total. Phase 0 is the main risk, so do it first. If a spike fails, the
fallbacks are in §6. The PRD's cut order still applies to Phases 8–11: Ask → HTML report →
Power & attitude → Verifier re-run → S4. Never cut the Summary tab, telemetry analysis or the
re-fly comparison.

## 5. Changes to the PRD

| PRD says | In this world | Why |
|---|---|---|
| Mission Planner SITL, Disconnect button, MP logs folder | `launch_sim.py`, `link_sim.py`, `recorder.py` | Linux machine, Gazebo world |
| 8-waypoint loop at 40 m, ~1.5 km | 30 m, ~1.3 km, ≥ 30 m from the mast | Mast is 44 m; the ground is 440 × 360 m |
| `change_altitude` final 10–120 m | **25–120 m** | 16.4 m buildings + wires; a fix must never fly lower than that |
| `SIM_WIND_SPD 10` | 9 N persistent wrench (+ EK3 drag fusion) | `SIM_WIND_*` does not move a JSON (Gazebo) vehicle |
| `BATT_CAPACITY 1500` | Lua battery + calibrated capacity (~2000) | No battery simulation without §3.2 |
| "opens in Mission Planner" | uploads and flies in SITL via `fly_scenario.py` (QGC optional) | No MP on this machine |
| Orchestrator "skip Mission Fixer" | Advisor gives advice only and `mission_io` is skipped | The PRD has no Mission Fixer agent |
| Packet loss from sequence gaps | Sequence gaps outside dropout windows only | 8-bit sequence wraps across a 12 s gap |

Mission edit rules are otherwise unchanged:
- at most 5 edits per run, each tied to a cause;
- `set_speed` 3–10 m/s;
- remove at most 30 % of waypoints, never home, takeoff, RTL or land;
- `add_hold` 0–10 s;
- the mission still ends in RTL or LAND.

New world-specific check: no leg passes within 20 m of the mast below 50 m.

## 6. Risks specific to this setup

| Risk | Mitigation |
|---|---|
| Lua battery backend not built into this SITL | Build with scripting (default for SITL); else extend the Gazebo plugin to send `battery` in JSON (`SIM_JSON.cpp` already reads `bat_volt`/`bat_amp`) |
| `EK3_DRAG_MCOEF` gives no WIND estimate | Attitude-based wind estimate in `metrics.py` (§3.3), labelled as such |
| Heavy world runs below real time | The airframe's camera payload is already removed; 8 flights × 5–7 min is about 1 h |
| Another SITL holding port 5760 | `launch_sim.py` refuses to start and names the command to stop it |
| Wrench direction / frame wrong | Phase 0 check: under the wrench, a hover in LOITER drifts and leans the expected way |

## 7. Target layout

```
aeromind/
├── sim/            launch_sim.py, world.py, geo.py, zones.py, link.py, tlog.py, capture.py,
│                   make_mission.py, fly_scenario.py, scenarios.yaml, missions/,
│                   params/ (copter, hexa, aeromind), scripts/battery.lua,
│                   worlds/, models/ (copied world + aeromind_hexa), tools/make_textures.py
├── data/<scenario>/  *.tlog, mission.waypoints, params.param, truth.json
├── tools/          ingest, metrics, anomalies, phases, risk_rules, memory, mission_io   (PRD)
├── agents/         base, prompts, orchestrator, schemas                                 (PRD + schemas)
├── report/template.html
├── tests/          fixtures/ (real tlog slices), one test file per module
├── run.py · app.py · history.json · outputs/<run_id>/ · .env.example · README.md
```

Run order once built:

```bash
python3 -m sim.launch_sim &                          # world + Hexa-X + SITL
python3 -m sim.fly_scenario s0 s1 s2 s3 s4           # ~35 min of flying
python run.py --batch data/                          # fill history
python3 -m sim.fly_scenario s1 --mission outputs/s1/mission_fixed.waypoints --tag s1_fixed
python run.py --compare outputs/s1 outputs/s1_fixed
streamlit run app.py
```

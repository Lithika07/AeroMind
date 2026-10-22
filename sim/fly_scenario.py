"""Fly demo scenarios in the disaster world and save each flight's files for AeroMind.

    python3 -m sim.fly_scenario s0 s1 s2 s3 s4
    python3 -m sim.fly_scenario s1 --mission outputs/s1/mission_fixed.waypoints --tag s1_fixed --parent s1

Each flight starts a fresh simulator (same pad, full battery, default parameters), applies the
scenario's faults, flies the mission in AUTO until the vehicle disarms, and writes to data/<tag>/:
    *.tlog            what the recording ground station received (with the link faults)
    mission.waypoints the mission that was flown
    params.param      every parameter as flown (Mission Planner format)
    truth.json        the link outages that were injected (ground truth)
    meta.json         scenario, wind, parameters changed, times, outcome
"""
import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from sim import scenarios, wind, world
from sim.capture import Capture
from sim.vehicle import Vehicle, VehicleError, write_param_file
from tools import waypoints as wp

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SIM_START_TIMEOUT_S = 120
FLIGHT_TIMEOUT_S = 30 * 60
#: Wind blows only above this height, like a ground boundary layer. A persistent push on a
#: landed airframe kept ArduPilot's land detector from ever disarming it.
WIND_ON_ALT_M = 3.0
PROGRESS_EVERY_S = 30.0


class Simulator:
    """A fresh `sim.launch_sim` for one flight."""

    def __enter__(self):
        self.process = subprocess.Popen([sys.executable, "-m", "sim.launch_sim"], cwd=ROOT,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ready = threading.Event()
        lines = []

        def read():
            for line in self.process.stdout:
                lines.append(line.rstrip())
                if "simulation up" in line:
                    ready.set()

        threading.Thread(target=read, daemon=True).start()
        if not ready.wait(SIM_START_TIMEOUT_S):
            self.__exit__(None, None, None)
            raise RuntimeError(f"simulator did not start: {' | '.join(lines[-5:])}")
        return self

    def __exit__(self, *_):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()


def fly(vehicle: Vehicle, scenario: scenarios.Scenario) -> dict:
    """Start the uploaded mission and follow it until the vehicle disarms."""
    vehicle.start_mission()
    started = time.time()
    outcome = {"armed_unix": started, "wind_applied_unix": None, "wind_cleared_unix": None, "max_rel_alt_m": 0.0}
    wind_on = False
    last_progress = 0.0
    seq = None
    while time.time() - started < FLIGHT_TIMEOUT_S:
        msg = vehicle.recv(["HEARTBEAT", "GLOBAL_POSITION_INT", "MISSION_CURRENT", "SYS_STATUS", "STATUSTEXT"])
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == "GLOBAL_POSITION_INT":
            alt = msg.relative_alt / 1000.0
            outcome["max_rel_alt_m"] = max(outcome["max_rel_alt_m"], alt)
            if scenario.wind and not wind_on and alt > WIND_ON_ALT_M and outcome["wind_cleared_unix"] is None:
                wind.apply(*scenario.wind.force_n())
                wind_on = True
                outcome["wind_applied_unix"] = time.time()
                vehicle.log(f"  wind on: {scenario.wind.speed_ms} m/s from {scenario.wind.from_deg} deg")
            elif wind_on and alt < WIND_ON_ALT_M:
                wind.clear()
                wind_on = False
                outcome["wind_cleared_unix"] = time.time()
                vehicle.log("  wind off (below boundary layer)")
        elif kind == "MISSION_CURRENT" and msg.seq != seq:
            seq = msg.seq
            vehicle.log(f"  mission item {seq}")
        elif kind == "SYS_STATUS" and time.time() - last_progress > PROGRESS_EVERY_S:
            last_progress = time.time()
            vehicle.log(f"  t+{time.time() - started:.0f}s battery {msg.battery_remaining}% "
                        f"{msg.voltage_battery / 1000:.2f} V")
        elif kind == "HEARTBEAT" and msg.get_srcSystem() == vehicle.conn.target_system:
            if not vehicle.conn.motors_armed() and outcome["max_rel_alt_m"] > WIND_ON_ALT_M:
                outcome["disarmed_unix"] = time.time()
                outcome["duration_s"] = round(outcome["disarmed_unix"] - started, 1)
                return outcome
    raise VehicleError(f"flight did not finish within {FLIGHT_TIMEOUT_S} s")


def run(scenario: scenarios.Scenario, out_dir: Path, mission_path: Path = None, parent: str = None) -> dict:
    origin = world.origin(world.DEFAULT_WORLD)
    items = wp.load(mission_path) if mission_path else scenarios.mission(scenario, scenarios.load_route(), origin)
    out_dir.mkdir(parents=True)
    wp.save(out_dir / "mission.waypoints", items)
    stop = threading.Event()
    capture = Capture(out_dir, scenario.link, origin[:2])
    meta = {"scenario": scenario.id, "title": scenario.title, "speed_ms": scenario.speed_ms,
            "wind": vars(scenario.wind) if scenario.wind else None, "params_set": scenario.params,
            "mission_source": str(mission_path) if mission_path else "generated", "parent_run": parent}
    with Simulator():
        vehicle = Vehicle()
        vehicle.wait_heartbeat()
        vehicle.wait_ready()
        for name, value in scenario.params.items():
            vehicle.set_param(name, value)
        vehicle.reset_battery(100.0)
        vehicle.upload_mission(items)
        write_param_file(out_dir / "params.param", vehicle.fetch_all_params())
        thread = threading.Thread(target=capture.run, args=(stop,), daemon=True)
        thread.start()
        try:
            meta.update(fly(vehicle, scenario))
        finally:
            if scenario.wind:
                wind.clear()
            time.sleep(2.0)      # the last packets after disarming
            stop.set()
            thread.join(timeout=10)
    meta["tlogs"] = [p.name for p in capture.writer.paths]
    meta["outages"] = len(capture.tracker.outages)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenarios", nargs="+", help="scenario ids from sim/scenarios.yaml")
    parser.add_argument("--mission", type=Path, help="fly this .waypoints instead of the generated route")
    parser.add_argument("--tag", help="output folder name under data/ (default: the scenario id)")
    parser.add_argument("--parent", help="run id this flight re-flies (a fixed mission's original)")
    parser.add_argument("--force", action="store_true", help="replace an existing data/<tag> folder")
    args = parser.parse_args()
    table = scenarios.load()
    unknown = [s for s in args.scenarios if s not in table]
    if unknown:
        parser.error(f"unknown scenarios {unknown}; known: {sorted(table)}")
    if (args.tag or args.mission) and len(args.scenarios) != 1:
        parser.error("--tag and --mission take exactly one scenario")
    for scenario_id in args.scenarios:
        out_dir = DATA_DIR / (args.tag or scenario_id)
        if out_dir.exists():
            if not args.force:
                print(f"{out_dir} exists; skipping (use --force to replace)")
                continue
            shutil.rmtree(out_dir)
        print(f"== {scenario_id}: {table[scenario_id].title} -> {out_dir}", flush=True)
        try:
            meta = run(table[scenario_id], out_dir, args.mission, args.parent)
        except (Exception, KeyboardInterrupt) as error:
            shutil.rmtree(out_dir, ignore_errors=True)
            print(f"   {scenario_id} failed, partial data removed: {error!r}", flush=True)
            return 1
        print(f"   done in {meta['duration_s']} s, {len(meta['tlogs'])} tlog(s), {meta['outages']} outage(s)",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

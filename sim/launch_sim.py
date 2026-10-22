"""Start the simulation: Gazebo with the disaster world and the Hexa-X, ArduCopter SITL, MAVProxy.

    python3 -m sim.launch_sim [--gui]       # runs until Ctrl-C
    python3 -m sim.launch_sim --stop        # stops a launch running in another terminal

MAVLink outputs (MAVProxy):
    udp 14550  any ground station (QGroundControl listens there)
    udp 14560  sim/link_sim.py -> sim/recorder.py (the recorded, fault-injected link)
    udp 14562  sim/fly_scenario.py (flight control; never faulted)
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from sim import world

RUN_DIR = world.SIM_DIR / "run"
SITL_DIR = RUN_DIR / "sitl"
PID_FILE = RUN_DIR / "launch.pid"
PARAMS_DIR = world.SIM_DIR / "params"
SCRIPTS_DIR = world.SIM_DIR / "scripts"
PARAM_FILES = ("copter.parm", "hexa.parm", "aeromind.parm")
DRONE_MODEL = "aeromind_hexa"

ARDUCOPTER = Path(os.environ.get("AEROMIND_ARDUCOPTER",
                                 Path.home() / "uav_ws/install/ardupilot_sitl/bin/arducopter"))
SITL_TCP_PORT = 5760
JSON_FDM_PORT = 9002
MAVLINK_OUTS = ("127.0.0.1:14550", "127.0.0.1:14560", "127.0.0.1:14562")
SITL_READY_TIMEOUT_S = 60
POLL_S = 0.5
STOP_TIMEOUT_S = 5


def write_world(source: Path = world.DEFAULT_WORLD) -> Path:
    x, y, z, yaw = world.spawn_pose(source)
    text = world.overlay(source.read_text(), DRONE_MODEL, (x, y, z + world.SPAWN_DROP_M, yaw))
    out = RUN_DIR / source.name
    out.write_text(text)
    return out


def prepare_sitl_dir() -> None:
    """SITL loads Lua scripts from ./scripts in its working directory."""
    scripts = SITL_DIR / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for script in SCRIPTS_DIR.glob("*.lua"):
        shutil.copy2(script, scripts / script.name)


def gazebo_env() -> dict:
    paths = ":".join(str(p) for p in world.resource_paths())
    existing = os.environ.get("GZ_SIM_RESOURCE_PATH")
    return {**os.environ, "GZ_SIM_RESOURCE_PATH": f"{paths}:{existing}" if existing else paths}


def sitl_command(source: Path) -> list:
    lat, lon, elevation = world.origin(source)
    defaults = ",".join(str(PARAMS_DIR / name) for name in PARAM_FILES)
    return [str(ARDUCOPTER), "--model", "JSON", "--speedup", "1", "--slave", "0", "-w",
            "--defaults", defaults, "--sim-address", "127.0.0.1", "-I0",
            "--home", f"{lat},{lon},{elevation},0"]


def mavproxy_command() -> list:
    command = ["mavproxy.py", "--master", f"tcp:127.0.0.1:{SITL_TCP_PORT}", "--non-interactive",
               "--streamrate=-1", "--state-basedir", str(SITL_DIR)]
    for out in MAVLINK_OUTS:
        command += ["--out", f"udp:{out}"]
    return command


def check_ports() -> None:
    if not world.port_is_free(SITL_TCP_PORT):
        sys.exit(f"port {SITL_TCP_PORT} is in use: another SITL is running "
                 "(the Aero Sense dashboard sim? stop it with ~/sih_2026/tools/dashboard.sh --stop)")
    import socket
    if not world.port_is_free(JSON_FDM_PORT, kind=socket.SOCK_DGRAM):
        sys.exit(f"UDP port {JSON_FDM_PORT} is in use: another Gazebo drone is running")
    if not ARDUCOPTER.is_file():
        sys.exit(f"arducopter not found at {ARDUCOPTER} (set AEROMIND_ARDUCOPTER)")


def wait_for_port(port: int, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + SITL_READY_TIMEOUT_S
    while world.port_is_free(port):
        if process.poll() is not None:
            raise RuntimeError(f"SITL exited with code {process.returncode}; see {SITL_DIR / 'sitl.log'}")
        if time.monotonic() > deadline:
            raise RuntimeError(f"SITL did not open port {port} within {SITL_READY_TIMEOUT_S} s")
        time.sleep(POLL_S)


def stop_processes(processes: list) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()


def start(gui: bool) -> int:
    check_ports()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    prepare_sitl_dir()
    world_file = write_world()
    env = gazebo_env()
    logs = {name: open(RUN_DIR / f"{name}.log", "w") for name in ("gazebo", "sitl", "mavproxy")}
    processes = []
    try:
        processes.append(subprocess.Popen(["gz", "sim", "-r", "-s", "-v2", str(world_file)], env=env,
                                          stdout=logs["gazebo"], stderr=subprocess.STDOUT))
        if gui:
            processes.append(subprocess.Popen(["gz", "sim", "-g", "-v2"], env=env,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        sitl = subprocess.Popen(sitl_command(world.DEFAULT_WORLD), cwd=SITL_DIR,
                                stdout=logs["sitl"], stderr=subprocess.STDOUT)
        processes.append(sitl)
        wait_for_port(SITL_TCP_PORT, sitl)
        processes.append(subprocess.Popen(mavproxy_command(), cwd=SITL_DIR,
                                          stdout=logs["mavproxy"], stderr=subprocess.STDOUT))
        PID_FILE.write_text(str(os.getpid()))
        print(f"simulation up: world {world.world_name(world_file)}, logs in {RUN_DIR}", flush=True)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while all(p.poll() is None for p in processes):
            time.sleep(POLL_S)
        dead = [p.args[0] for p in processes if p.poll() is not None]
        print(f"stopping: {', '.join(dead)} exited", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop_processes(processes)
        for log in logs.values():
            log.close()
        PID_FILE.unlink(missing_ok=True)


def stop() -> int:
    if not PID_FILE.exists():
        print("no simulation running")
        return 0
    pid = int(PID_FILE.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("stale pid file removed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gui", action="store_true", help="also open the Gazebo window")
    parser.add_argument("--stop", action="store_true", help="stop a running launch")
    args = parser.parse_args()
    return stop() if args.stop else start(args.gui)


if __name__ == "__main__":
    sys.exit(main())

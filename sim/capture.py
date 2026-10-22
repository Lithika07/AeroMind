"""The recording ground station: receives MAVProxy's output, applies link faults, writes tlogs.

    python3 -m sim.capture --out data/s3 --faults '{"windows": [[90, 12], [200, 12]]}'

Packets the faulted link loses are never written, exactly as a ground station that lost its radio
would never see them. Outages (the ground truth) go to <out>/truth.json as they happen.
"""
import argparse
import json
import random
import signal
import socket
import sys
import threading
import time
from pathlib import Path

from pymavlink.dialects.v20 import ardupilotmega as mavlink

from sim import geo, link, world
from sim.tlog import TlogWriter

LISTEN = ("127.0.0.1", 14560)
VEHICLE_SYSID = 1
VEHICLE_COMPID = 1
RECV_BYTES = 65535
SOCKET_TIMEOUT_S = 0.5
DEG_E7 = 1e7
TRUTH_FILE = "truth.json"


class VehicleState:
    """What the link simulator knows of the vehicle: armed since when, and where."""

    def __init__(self, origin: tuple):
        self.origin = origin
        self.armed_at = None
        self.lat_lon = None
        self.enu = None
        self.has_disarmed_after_flight = False

    def observe(self, msg, now: float) -> None:
        if msg.get_srcSystem() != VEHICLE_SYSID or msg.get_srcComponent() != VEHICLE_COMPID:
            return
        kind = msg.get_type()
        if kind == "HEARTBEAT" and msg.type != mavlink.MAV_TYPE_GCS:
            armed = bool(msg.base_mode & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if armed and self.armed_at is None:
                self.armed_at = now
            elif not armed and self.armed_at is not None:
                self.has_disarmed_after_flight = True
        elif kind == "GLOBAL_POSITION_INT":
            self.lat_lon = (msg.lat / DEG_E7, msg.lon / DEG_E7)
            self.enu = geo.to_enu(self.origin, *self.lat_lon)

    def t_armed(self, now: float):
        return None if self.armed_at is None else now - self.armed_at


class Capture:
    def __init__(self, out_dir: Path, faults: link.LinkFaults, origin: tuple, seed: int = 0):
        self.out_dir = Path(out_dir)
        self.faults = faults
        self.state = VehicleState(origin)
        self.writer = TlogWriter(self.out_dir)
        self.tracker = link.OutageTracker()
        self.rng = random.Random(seed)
        self.parser = mavlink.MAVLink(None)
        self.parser.robust_parsing = True
        self.packets_in = 0
        self.packets_written = 0

    def handle(self, datagram: bytes, now: float) -> None:
        for msg in self.parser.parse_buffer(datagram) or ():
            if msg.get_type() == "BAD_DATA":
                continue
            self.packets_in += 1
            self.state.observe(msg, now)
            t_armed = self.state.t_armed(now)
            was_down = self.tracker.current is not None
            reason = link.outage(self.faults, t_armed, self.state.enu, was_down)
            tracker = self.tracker.update(now, t_armed, reason, self.state.lat_lon)
            if (tracker.current is None) != (self.tracker.current is None):
                self.tracker = tracker
                self.write_truth()
            self.tracker = tracker
            if reason is None and not link.lose_packet(self.faults, self.rng):
                self.writer.write(msg.get_msgbuf(), now)
                self.packets_written += 1

    def write_truth(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        truth = {
            "armed_unix": self.state.armed_at,
            "faults": {"windows": [list(w) for w in self.faults.windows],
                       "zones": [vars(z) for z in self.faults.zones], "loss_pct": self.faults.loss_pct},
            "outages": [o.as_dict() for o in self.tracker.outages],
            "packets_in": self.packets_in,
            "packets_written": self.packets_written,
        }
        (self.out_dir / TRUTH_FILE).write_text(json.dumps(truth, indent=2))

    def close(self, now: float) -> None:
        self.tracker = self.tracker.finish(now)
        self.writer.close()
        self.write_truth()

    def run(self, stop: threading.Event, listen: tuple = LISTEN) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(listen)
            sock.settimeout(SOCKET_TIMEOUT_S)
            try:
                while not stop.is_set():
                    try:
                        datagram = sock.recv(RECV_BYTES)
                    except socket.timeout:
                        continue
                    self.handle(datagram, time.time())
            finally:
                self.close(time.time())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="directory for the tlogs and truth.json")
    parser.add_argument("--faults", default="{}", help='link faults as JSON, e.g. {"loss_pct": 2}')
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    try:
        faults = link.LinkFaults.from_dict(json.loads(args.faults))
    except (ValueError, json.JSONDecodeError) as error:
        parser.error(f"--faults: {error}")
    origin = world.origin(world.DEFAULT_WORLD)[:2]
    capture = Capture(args.out, faults, origin, args.seed)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    capture.run(stop)
    print(f"wrote {[str(p) for p in capture.writer.paths]}, {len(capture.tracker.outages)} outages")
    return 0


if __name__ == "__main__":
    sys.exit(main())

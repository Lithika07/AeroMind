import json

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink

from sim import capture, link

ORIGIN = (-35.363262, 149.165237)
ARMED = mavlink.MAV_MODE_FLAG_SAFETY_ARMED


class Vehicle:
    def __init__(self, sysid=1):
        self.mav = mavlink.MAVLink(None, srcSystem=sysid, srcComponent=1)

    def heartbeat(self, armed: bool) -> bytes:
        return self.mav.heartbeat_encode(mavlink.MAV_TYPE_HEXAROTOR, mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                                         ARMED if armed else 0, 0, 0).pack(self.mav)

    def position(self, lat: float, lon: float) -> bytes:
        return self.mav.global_position_int_encode(0, int(lat * 1e7), int(lon * 1e7), 0, 30000, 0, 0, 0, 0
                                                   ).pack(self.mav)


def test_timed_outage_drops_packets_and_records_truth(tmp_path):
    cap = capture.Capture(tmp_path, link.LinkFaults(windows=((10.0, 5.0),)), ORIGIN)
    vehicle = Vehicle()
    cap.handle(vehicle.heartbeat(armed=True), now=100.0)
    cap.handle(vehicle.position(*ORIGIN), now=105.0)
    for t in (111.0, 112.0, 114.0):
        cap.handle(vehicle.heartbeat(armed=True), now=t)
    cap.handle(vehicle.heartbeat(armed=True), now=116.0)
    cap.close(now=120.0)

    assert cap.packets_in == 6 and cap.packets_written == 3
    truth = json.loads((tmp_path / "truth.json").read_text())
    (outage,) = truth["outages"]
    assert outage["reason"] == "timed"
    assert outage["start_unix"] == 111.0 and outage["end_unix"] == 116.0
    assert outage["lat"] == ORIGIN[0]


def test_written_log_has_a_gap_where_the_link_was_down(tmp_path):
    cap = capture.Capture(tmp_path, link.LinkFaults(windows=((1.0, 8.0),)), ORIGIN)
    vehicle = Vehicle()
    for t in range(0, 15):
        cap.handle(vehicle.heartbeat(armed=True), now=1000.0 + t)
    cap.close(now=1015.0)
    times = []
    for path in cap.writer.paths:
        log = mavutil.mavlink_connection(str(path))
        while (msg := log.recv_match(type="HEARTBEAT")) is not None:
            times.append(msg._timestamp)
    assert times == [1000.0, 1009.0, 1010.0, 1011.0, 1012.0, 1013.0, 1014.0]
    assert len(cap.writer.paths) == 2


def test_other_systems_do_not_arm_the_clock(tmp_path):
    cap = capture.Capture(tmp_path, link.LinkFaults(windows=((0.0, 5.0),)), ORIGIN)
    cap.handle(Vehicle(sysid=255).heartbeat(armed=True), now=1.0)
    assert cap.state.armed_at is None and cap.packets_written == 1


def test_disarm_after_flight_is_noticed(tmp_path):
    cap = capture.Capture(tmp_path, link.LinkFaults(), ORIGIN)
    vehicle = Vehicle()
    cap.handle(vehicle.heartbeat(armed=True), now=1.0)
    assert not cap.state.has_disarmed_after_flight
    cap.handle(vehicle.heartbeat(armed=False), now=2.0)
    assert cap.state.has_disarmed_after_flight


def test_garbage_is_ignored(tmp_path):
    cap = capture.Capture(tmp_path, link.LinkFaults(), ORIGIN)
    cap.handle(b"\x00\x01garbage", now=1.0)
    assert cap.packets_in == 0

"""MAVLink control of the simulated vehicle for the scenario runner (MAVProxy output udp 14562)."""
import time

from pymavlink import mavutil

from tools import waypoints as wp

CONTROL_URL = "udpin:127.0.0.1:14562"
SOURCE_SYSTEM = 250          # not 255, which a ground station on 14550 may use
EKF_POS_HORIZ_ABS = 16       # EKF_STATUS_REPORT flag
GPS_3D_FIX = 3
PARAM_RETRIES = 5
PARAM_TIMEOUT_S = 2.0
MISSION_TIMEOUT_S = 20.0
ARM_ATTEMPTS = 30
ARM_RETRY_S = 2.0
PARAM_FETCH_TIMEOUT_S = 60.0
MAV_CMD_BATTERY_RESET = 42651


class VehicleError(RuntimeError):
    pass


class Vehicle:
    def __init__(self, url: str = CONTROL_URL, log=print):
        self.conn = mavutil.mavlink_connection(url, source_system=SOURCE_SYSTEM)
        self.log = log

    # -- receiving -------------------------------------------------------------------------
    def recv(self, types=None, timeout: float = 1.0):
        msg = self.conn.recv_match(type=types, blocking=True, timeout=timeout)
        if msg is not None and msg.get_type() == "STATUSTEXT":
            self.log(f"  vehicle: {msg.text}")
        return msg

    def wait_heartbeat(self, timeout: float = 60.0) -> None:
        if self.conn.wait_heartbeat(timeout=timeout) is None:
            raise VehicleError(f"no heartbeat within {timeout} s")

    def wait_ready(self, timeout: float = 120.0) -> None:
        """Until GPS has a 3D fix and the EKF has an absolute horizontal position."""
        deadline = time.monotonic() + timeout
        fix = ekf = False
        while time.monotonic() < deadline:
            msg = self.recv(["GPS_RAW_INT", "EKF_STATUS_REPORT", "STATUSTEXT"])
            if msg is None:
                continue
            if msg.get_type() == "GPS_RAW_INT":
                fix = msg.fix_type >= GPS_3D_FIX
            elif msg.get_type() == "EKF_STATUS_REPORT":
                ekf = bool(msg.flags & EKF_POS_HORIZ_ABS)
            if fix and ekf:
                return
        raise VehicleError(f"vehicle not ready within {timeout} s (GPS fix {fix}, EKF position {ekf})")

    # -- parameters ------------------------------------------------------------------------
    def get_param(self, name: str) -> float:
        for _ in range(PARAM_RETRIES):
            self.conn.param_fetch_one(name)
            msg = self._param_value(name)
            if msg is not None:
                return msg.param_value
        raise VehicleError(f"could not read parameter {name}")

    def set_param(self, name: str, value: float) -> None:
        for _ in range(PARAM_RETRIES):
            self.conn.param_set_send(name, value)
            msg = self._param_value(name)
            if msg is not None and abs(msg.param_value - value) < 1e-4 * max(1.0, abs(value)):
                return
        raise VehicleError(f"could not set parameter {name} to {value}")

    def _param_value(self, name: str):
        deadline = time.monotonic() + PARAM_TIMEOUT_S
        while time.monotonic() < deadline:
            msg = self.recv("PARAM_VALUE", timeout=0.5)
            if msg is not None and msg.param_id == name:
                return msg
        return None

    def fetch_all_params(self) -> dict:
        """Every parameter, as Mission Planner's Full Parameter List would save it."""
        self.conn.param_fetch_all()
        values, count = {}, None
        deadline = time.monotonic() + PARAM_FETCH_TIMEOUT_S
        while time.monotonic() < deadline and (count is None or len(values) < count):
            msg = self.recv("PARAM_VALUE", timeout=1.0)
            if msg is not None:
                values[msg.param_id] = msg.param_value
                count = msg.param_count
        if count is None or len(values) < count:
            raise VehicleError(f"parameter download incomplete ({len(values)} of {count})")
        return values

    # -- commands --------------------------------------------------------------------------
    def command(self, command: int, *params: float, timeout: float = 5.0) -> None:
        padded = list(params) + [0.0] * (7 - len(params))
        self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component, command, 0, *padded)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ack = self.recv("COMMAND_ACK", timeout=0.5)
            if ack is not None and ack.command == command:
                if ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    raise VehicleError(f"command {command} refused (result {ack.result})")
                return
        raise VehicleError(f"no acknowledgement for command {command}")

    def reset_battery(self, percent: float = 100.0) -> None:
        self.command(MAV_CMD_BATTERY_RESET, 1, percent)

    def set_mode(self, mode: str, timeout: float = 10.0) -> None:
        mode_id = self.conn.mode_mapping()[mode]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.conn.set_mode(mode_id)
            msg = self.recv("HEARTBEAT", timeout=1.0)
            if msg is not None and msg.get_srcSystem() == self.conn.target_system and msg.custom_mode == mode_id:
                return
        raise VehicleError(f"mode {mode} not accepted")

    def arm(self) -> None:
        for _ in range(ARM_ATTEMPTS):
            self.conn.arducopter_arm()
            deadline = time.monotonic() + ARM_RETRY_S
            while time.monotonic() < deadline:
                self.recv(timeout=0.5)
                if self.conn.motors_armed():
                    return
        raise VehicleError("vehicle would not arm")

    # -- mission ---------------------------------------------------------------------------
    def upload_mission(self, items: list) -> None:
        mav = self.conn.mav
        target = (self.conn.target_system, self.conn.target_component)
        mav.mission_count_send(*target, len(items))
        deadline = time.monotonic() + MISSION_TIMEOUT_S
        while time.monotonic() < deadline:
            msg = self.recv(["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"], timeout=1.0)
            if msg is None:
                continue
            if msg.get_type() == "MISSION_ACK":
                if msg.type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    raise VehicleError(f"mission rejected (MAV_MISSION_RESULT {msg.type})")
                return
            item = items[msg.seq]
            mav.mission_item_int_send(*target, msg.seq, item.frame, item.command, item.current,
                                      item.autocontinue, item.param1, item.param2, item.param3, item.param4,
                                      int(round(item.lat * 1e7)), int(round(item.lon * 1e7)), item.alt)
        raise VehicleError("mission upload timed out")

    def start_mission(self) -> None:
        self.set_mode("GUIDED")
        self.arm()
        self.set_mode("AUTO")
        self.command(mavutil.mavlink.MAV_CMD_MISSION_START, 0, 0)


def write_param_file(path, values: dict) -> None:
    """Mission Planner's .param format: NAME,VALUE per line, sorted."""
    lines = [f"{name},{value:.6g}" for name, value in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n")


def mission_text(items: list) -> str:
    return wp.dumps(items)

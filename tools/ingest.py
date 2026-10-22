"""Read a flight's files into one FlightData: telemetry logs, mission, parameters, pilot notes.

Several .tlog files from one flight (a ground station starts a new file on each reconnect) are
merged by timestamp; the gaps between them are kept so the link analysis can count them as
dropouts. Only the vehicle's own messages are kept.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
from pymavlink import mavutil

from tools import waypoints as wp

#: Message types the metrics use. Anything else is skipped while reading.
MESSAGE_TYPES = frozenset({
    "HEARTBEAT", "SYS_STATUS", "BATTERY_STATUS", "GLOBAL_POSITION_INT", "GPS_RAW_INT", "VFR_HUD",
    "ATTITUDE", "VIBRATION", "WIND", "NAV_CONTROLLER_OUTPUT", "MISSION_CURRENT", "MISSION_ITEM_REACHED",
    "STATUSTEXT", "RADIO_STATUS", "RC_CHANNELS", "EKF_STATUS_REPORT",
})
MAV_TYPE_GCS = 6
MAV_AUTOPILOT_INVALID = 8
MAX_NOTES_CHARS = 2000


class IngestError(ValueError):
    pass


@dataclass(frozen=True)
class LogFile:
    path: str
    t_start: float
    t_end: float
    messages: int


@dataclass(frozen=True)
class FlightData:
    frames: dict                       # message type -> DataFrame (column t = unix seconds)
    sequence: pd.DataFrame             # every vehicle message: t, seq (for packet loss)
    files: tuple                       # LogFile, in time order
    vehicle_sysid: int
    mission: Optional[list] = None     # tools.waypoints.Item list
    params: Optional[dict] = None
    notes: Optional[str] = None
    sources: dict = field(default_factory=dict)

    @property
    def t0(self) -> float:
        return self.files[0].t_start

    def frame(self, msg_type: str) -> pd.DataFrame:
        return self.frames.get(msg_type, pd.DataFrame(columns=["t"]))


def _vehicle_sysid(msg) -> Optional[int]:
    if msg.get_type() != "HEARTBEAT":
        return None
    if msg.type == MAV_TYPE_GCS or msg.autopilot == MAV_AUTOPILOT_INVALID:
        return None
    return msg.get_srcSystem()


def _read_tlog(path: Path) -> tuple:
    """(rows by type, sequence rows, sysid, LogFile) for one .tlog."""
    try:
        log = mavutil.mavlink_connection(str(path), dialect="ardupilotmega")
    except Exception as error:  # pymavlink raises bare exceptions for unreadable files
        raise IngestError(f"cannot open {path}: {error}") from error
    rows, sequence, sysid = {}, [], None
    first = last = None
    count = 0
    while True:
        msg = log.recv_match()
        if msg is None:
            break
        kind = msg.get_type()
        if kind == "BAD_DATA":
            continue
        sysid = sysid or _vehicle_sysid(msg)
        if sysid is None or msg.get_srcSystem() != sysid or msg.get_srcComponent() != 1:
            continue
        t = msg._timestamp
        first = t if first is None else first
        last = t
        count += 1
        sequence.append((t, msg.get_seq()))
        if kind in MESSAGE_TYPES:
            row = msg.to_dict()
            row.pop("mavpackettype", None)
            row["t"] = t
            rows.setdefault(kind, []).append(row)
    if count == 0:
        raise IngestError(f"{path} has no messages from a vehicle")
    return rows, sequence, sysid, LogFile(str(path), first, last, count)


def read_tlogs(paths: list) -> tuple:
    """(frames, sequence, files, sysid) for one flight's .tlog files, merged by time."""
    if not paths:
        raise IngestError("no telemetry log given")
    merged, sequence, files, sysids = {}, [], [], set()
    for path in paths:
        rows, seq_rows, sysid, info = _read_tlog(Path(path))
        sysids.add(sysid)
        files.append(info)
        sequence.extend(seq_rows)
        for kind, kind_rows in rows.items():
            merged.setdefault(kind, []).extend(kind_rows)
    if len(sysids) > 1:
        raise IngestError(f"logs come from different vehicles (system ids {sorted(sysids)})")
    frames = {kind: pd.DataFrame(r).sort_values("t", kind="stable").reset_index(drop=True)
              for kind, r in merged.items()}
    seq_frame = pd.DataFrame(sequence, columns=["t", "seq"]).sort_values("t", kind="stable").reset_index(drop=True)
    return frames, seq_frame, tuple(sorted(files, key=lambda f: f.t_start)), sysids.pop()


def read_params(path: Path) -> dict:
    """Mission Planner (NAME,VALUE) or MAVProxy (NAME VALUE) parameter files."""
    params = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").replace("\t", " ").split()
        if len(parts) < 2:
            raise IngestError(f"{path} line {number}: expected NAME,VALUE")
        try:
            params[parts[0]] = float(parts[1])
        except ValueError as error:
            raise IngestError(f"{path} line {number}: {error}") from error
    return params


def clean_notes(notes: Optional[str]) -> Optional[str]:
    if notes is None:
        return None
    text = " ".join(notes.split())[:MAX_NOTES_CHARS]
    return text or None


def load_flight(tlogs: list, mission: Path = None, params: Path = None, notes: str = None) -> FlightData:
    frames, sequence, files, sysid = read_tlogs([Path(p) for p in tlogs])
    try:
        mission_items = wp.load(mission) if mission else None
    except ValueError as error:
        raise IngestError(f"{mission}: {error}") from error
    return FlightData(frames=frames, sequence=sequence, files=files, vehicle_sysid=sysid,
                      mission=mission_items, params=read_params(params) if params else None,
                      notes=clean_notes(notes),
                      sources={"tlogs": [str(p) for p in tlogs], "mission": str(mission) if mission else None,
                               "params": str(params) if params else None})

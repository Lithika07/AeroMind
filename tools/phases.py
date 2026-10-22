"""Split a flight into phases: takeoff, one leg per waypoint, RTL, land (PRD "Phase splitter").

From mode changes, the mission item being flown (MISSION_CURRENT) and the mission file. Times are
seconds from the start of the log. Waypoints are named by mission sequence number, as Mission
Planner numbers them.
"""
import numpy as np
import pandas as pd

from agents.schemas import Phase
from tools import timeline
from tools import waypoints as wp

LANDING_SPEED_MS = 1.0
MIN_PHASE_S = 2.0            # shorter mode blips (GUIDED while arming) are not phases
RETURN_MODES = {"RTL", "SMART_RTL"}
LAND_MODES = {"LAND"}


def _segments(times: np.ndarray, labels: list) -> list:
    """[(label, start, end)] for runs of equal consecutive labels; a None label continues the run."""
    segments = []
    for t, label in zip(times, labels):
        if segments and (label is None or segments[-1][0] == label):
            segments[-1][2] = t
        elif label is None:
            continue
        else:
            if segments:
                segments[-1][2] = t
            segments.append([label, t, t])
    return [tuple(s) for s in segments]


def _label(mode: str, seq, commands: dict) -> tuple:
    if mode in RETURN_MODES:
        return ("rtl", None)
    if mode in LAND_MODES:
        return ("land", None)
    if mode != "AUTO" or seq is None:
        return ("other", mode)
    if int(seq) == 0:
        return None           # home: reported for a moment before take-off and after landing
    command = commands.get(int(seq))
    if command == wp.NAV_TAKEOFF:
        return ("takeoff", None)
    if command == wp.NAV_RETURN_TO_LAUNCH:
        return ("rtl", None)
    if command == wp.NAV_LAND:
        return ("land", None)
    if command is None or command == wp.NAV_WAYPOINT:
        return ("leg", int(seq))
    return ("other", f"item {int(seq)}")


def landing_start(position: pd.DataFrame, vfr: pd.DataFrame, after: float, end: float) -> float:
    """When horizontal motion stopped for the final descent: the last moment above walking pace."""
    moving = vfr[(vfr["t"] >= after) & (vfr["t"] <= end) & (vfr["groundspeed"] > LANDING_SPEED_MS)]
    return float(moving["t"].iloc[-1]) if not moving.empty else after


def split(flight) -> list:
    hb = timeline.heartbeat_states(flight.frame("HEARTBEAT"))
    window = timeline.armed_window(flight.frame("HEARTBEAT"))
    if window is None:
        return []
    commands = {item.seq: item.command for item in flight.mission} if flight.mission else {}
    current = flight.frame("MISSION_CURRENT")
    hb = timeline.in_window(hb, window)
    labels = [_label(row.mode, timeline.value_at(current, "seq", row.t), commands) for row in hb.itertuples()]
    phases, leg_number = [], 0
    segments = [s for s in _segments(hb["t"].to_numpy(), labels) if s[2] - s[1] >= MIN_PHASE_S or s[0][0] != "other"]
    for (kind, detail), start, end in segments:
        if kind == "leg":
            leg_number += 1
            name = f"Leg {leg_number} (to WP{detail})"
        elif kind == "other":
            name = str(detail).title() if detail else "Other"
        else:
            name = {"takeoff": "Takeoff", "rtl": "RTL", "land": "Land"}[kind]
        phases.append([name, kind, start, end])
    if phases and phases[-1][1] in ("rtl", "land"):
        last = phases[-1]
        touchdown = landing_start(flight.frame("GLOBAL_POSITION_INT"), flight.frame("VFR_HUD"), last[2], window[1])
        if last[1] == "rtl" and last[2] < touchdown < window[1]:
            phases[-1] = [last[0], "rtl", last[2], touchdown]
            phases.append(["Land", "land", touchdown, window[1]])
    if not phases:
        return []
    phases[-1][3] = window[1]
    t0 = flight.t0
    return [Phase(name=name, kind=kind, t_start=round(start - t0, 1), t_end=round(end - t0, 1))
            for name, kind, start, end in phases]

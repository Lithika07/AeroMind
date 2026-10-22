"""When the vehicle was armed, airborne and in which mode: shared by the metrics, phases and link tools."""
from typing import Optional

import numpy as np
import pandas as pd
from pymavlink import mavutil

ARMED_FLAG = 128                 # MAV_MODE_FLAG_SAFETY_ARMED
AIRBORNE_ALT_M = 1.0
COPTER_MODES = dict(mavutil.mode_mapping_acm)   # number -> name


def mode_name(custom_mode: int) -> str:
    return COPTER_MODES.get(int(custom_mode), f"MODE_{int(custom_mode)}")


def heartbeat_states(heartbeat: pd.DataFrame) -> pd.DataFrame:
    """t, armed, mode for every vehicle heartbeat."""
    if heartbeat.empty:
        return pd.DataFrame(columns=["t", "armed", "mode"])
    return pd.DataFrame({"t": heartbeat["t"],
                         "armed": (heartbeat["base_mode"].astype(int) & ARMED_FLAG) > 0,
                         "mode": heartbeat["custom_mode"].map(mode_name)}).reset_index(drop=True)


def armed_window(heartbeat: pd.DataFrame) -> Optional[tuple]:
    """(first arm, last disarm) in unix seconds; the log's last heartbeat if never disarmed."""
    states = heartbeat_states(heartbeat)
    armed = states[states["armed"]]
    if armed.empty:
        return None
    start = float(armed["t"].iloc[0])
    after = states[(states["t"] > armed["t"].iloc[-1]) & ~states["armed"]]
    end = float(after["t"].iloc[0]) if not after.empty else float(states["t"].iloc[-1])
    return start, end


def in_window(frame: pd.DataFrame, window: Optional[tuple]) -> pd.DataFrame:
    if window is None or frame.empty:
        return frame.iloc[0:0]
    return frame[(frame["t"] >= window[0]) & (frame["t"] <= window[1])]


def airborne_intervals(position: pd.DataFrame, window: Optional[tuple]) -> list:
    """[(start, end)] while armed and more than 1 m above home."""
    rows = in_window(position, window)
    if rows.empty:
        return []
    up = (rows["relative_alt"].to_numpy() / 1000.0) > AIRBORNE_ALT_M
    times = rows["t"].to_numpy()
    intervals, start = [], None
    for t, flag in zip(times, up):
        if flag and start is None:
            start = t
        elif not flag and start is not None:
            intervals.append((float(start), float(t)))
            start = None
    if start is not None:
        intervals.append((float(start), float(times[-1])))
    return intervals


def mask(times: np.ndarray, intervals: list) -> np.ndarray:
    result = np.zeros(len(times), dtype=bool)
    for start, end in intervals:
        result |= (times >= start) & (times <= end)
    return result


def during(frame: pd.DataFrame, intervals: list) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[mask(frame["t"].to_numpy(), intervals)]


def value_at(frame: pd.DataFrame, column: str, t: float):
    """The latest value of `column` at or before t (None if there is none)."""
    if frame.empty:
        return None
    index = np.searchsorted(frame["t"].to_numpy(), t, side="right") - 1
    return None if index < 0 else frame[column].iloc[index]


def subtract(intervals: list, cuts: list) -> list:
    """`intervals` with every (start, end) in `cuts` removed."""
    result = list(intervals)
    for cut_start, cut_end in cuts:
        pieces = []
        for start, end in result:
            if cut_end <= start or cut_start >= end:
                pieces.append((start, end))
                continue
            if start < cut_start:
                pieces.append((start, cut_start))
            if cut_end < end:
                pieces.append((cut_end, end))
        result = pieces
    return result

import numpy as np
import pandas as pd
import pytest

from tools import timeline


def heartbeat(rows):
    return pd.DataFrame([{"t": t, "base_mode": 128 if armed else 0, "custom_mode": mode} for t, armed, mode in rows])


def test_mode_names():
    assert timeline.mode_name(3) == "AUTO" and timeline.mode_name(6) == "RTL"
    assert timeline.mode_name(99) == "MODE_99"


def test_armed_window_from_first_arm_to_disarm():
    hb = heartbeat([(0, False, 4), (1, True, 4), (2, True, 3), (5, True, 3), (6, False, 3), (7, False, 3)])
    assert timeline.armed_window(hb) == (1.0, 6.0)


def test_armed_window_never_disarmed_ends_at_last_heartbeat():
    assert timeline.armed_window(heartbeat([(1, True, 3), (4, True, 3)])) == (1.0, 4.0)


def test_armed_window_none_when_never_armed():
    assert timeline.armed_window(heartbeat([(1, False, 0)])) is None


def test_airborne_intervals():
    position = pd.DataFrame({"t": [0, 1, 2, 3, 4, 5], "relative_alt": [0, 500, 2000, 3000, 900, 0]})
    assert timeline.airborne_intervals(position, (0, 5)) == [(2.0, 4.0)]


def test_subtract_cuts_out_pieces():
    assert timeline.subtract([(0, 10)], [(2, 3), (8, 12)]) == [(0, 2), (3, 8)]
    assert timeline.subtract([(0, 10)], [(20, 30)]) == [(0, 10)]


def test_value_at_takes_the_latest_before():
    frame = pd.DataFrame({"t": [1.0, 2.0, 3.0], "seq": [5, 6, 7]})
    assert timeline.value_at(frame, "seq", 2.5) == 6
    assert timeline.value_at(frame, "seq", 0.5) is None


def test_mask_and_during():
    frame = pd.DataFrame({"t": np.arange(6.0), "v": range(6)})
    assert list(timeline.during(frame, [(1, 2), (4, 4)])["v"]) == [1, 2, 4]

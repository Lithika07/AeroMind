import numpy as np
import pandas as pd
import pytest

from tools import link_metrics as lm
from tools import waypoints as wp


def test_find_gaps_over_two_seconds():
    times = np.array([0.0, 0.1, 0.2, 3.0, 3.1, 4.0, 15.0])
    assert lm.find_gaps(times) == [(0.2, pytest.approx(2.8)), (4.0, 11.0)]


def test_link_gaps_drops_simulator_stalls():
    clock = pd.DataFrame({"t": [0.0, 0.1, 5.0, 5.1, 10.0, 22.0],
                          "boot_s": [0.0, 0.1, 0.2, 0.3, 5.0, 17.0]})
    gaps = [(0.1, 4.9), (10.0, 12.0)]
    assert lm.link_gaps(gaps, clock) == [(10.0, 12.0)]


def test_packet_loss_counts_missing_sequence_numbers_with_wrap():
    seq = pd.DataFrame({"t": np.arange(6.0), "seq": [253, 254, 0, 1, 3, 4]})
    # 255 and 2 are missing: 2 lost of 8
    assert lm.packet_loss_pct(seq, []) == 25.0


def test_packet_loss_ignores_pairs_across_a_dropout():
    seq = pd.DataFrame({"t": [0.0, 1.0, 20.0, 21.0], "seq": [10, 11, 200, 201]})
    assert lm.packet_loss_pct(seq, [(1.0, 19.0)]) == 0.0


def test_packet_loss_needs_two_packets():
    assert lm.packet_loss_pct(pd.DataFrame({"t": [0.0], "seq": [1]}), []) is None


def test_nearest_waypoint_uses_mission_sequence_numbers():
    mission = [wp.Item(0, 1, 0, 16, 0, 0, 0, 0, -35.0, 149.0, 0),
               wp.Item(1, 0, 3, 22, 0, 0, 0, 0, 0, 0, 30),
               wp.Item(2, 0, 3, 16, 0, 0, 0, 0, -35.001, 149.0, 30),
               wp.Item(3, 0, 3, 16, 0, 0, 0, 0, -35.002, 149.0, 30)]
    assert lm.nearest_waypoint(mission, -35.0019, 149.0) == 3
    assert lm.nearest_waypoint(None, -35.0, 149.0) is None

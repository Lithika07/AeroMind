import random

import pytest

from sim import link
from sim.zones import Area


def faults(**kwargs):
    return link.LinkFaults(**kwargs)


def test_no_faults_never_drops():
    assert link.outage(faults(), t_armed=100.0, position=(0.0, 0.0)) is None


def test_timed_window_drops_only_inside_it():
    f = faults(windows=((60.0, 12.0),))
    assert link.outage(f, 59.9, None) is None
    assert link.outage(f, 60.0, None) == "timed"
    assert link.outage(f, 71.9, None) == "timed"
    assert link.outage(f, 72.0, None) is None


def test_timed_window_needs_arming():
    assert link.outage(faults(windows=((0.0, 10.0),)), None, None) is None


def test_zone_drops_inside_and_holds_for_the_margin():
    f = faults(zones=(Area(0.0, 0.0, 10.0, 10.0),))
    assert link.outage(f, 5.0, (5.0, 5.0)) == "zone"
    assert link.outage(f, 5.0, (12.0, 5.0)) is None
    assert link.outage(f, 5.0, (12.0, 5.0), was_down=True) == "zone"
    assert link.outage(f, 5.0, (14.0, 5.0), was_down=True) is None


def test_zone_without_position_is_up():
    assert link.outage(faults(zones=(Area(0, 0, 1, 1),)), 1.0, None) is None


def test_random_loss_rate_is_close_to_configured():
    f = faults(loss_pct=5.0)
    rng = random.Random(1)
    lost = sum(link.lose_packet(f, rng) for _ in range(20_000))
    assert lost / 20_000 == pytest.approx(0.05, abs=0.006)


def test_zero_loss_never_loses():
    rng = random.Random(1)
    assert not any(link.lose_packet(faults(), rng) for _ in range(1000))


def test_tracker_records_one_outage_per_down_edge():
    tracker = link.OutageTracker()
    tracker = tracker.update(10.0, 5.0, None, (1.0, 2.0))
    tracker = tracker.update(11.0, 6.0, "timed", (1.0, 2.0))
    tracker = tracker.update(12.0, 7.0, "timed", (3.0, 4.0))
    tracker = tracker.update(23.0, 18.0, None, (5.0, 6.0))
    (outage,) = tracker.outages
    assert outage == link.Outage(reason="timed", start_unix=11.0, end_unix=23.0, start_t_armed=6.0,
                                 lat=1.0, lon=2.0)
    assert outage.duration_s == 12.0


def test_tracker_is_immutable():
    tracker = link.OutageTracker()
    tracker.update(1.0, 0.0, "timed", None)
    assert tracker.outages == () and tracker.current is None


def test_open_outage_is_closed_on_finish():
    tracker = link.OutageTracker().update(1.0, 0.0, "zone", None)
    (outage,) = tracker.finish(4.0).outages
    assert outage.end_unix == 4.0


def test_faults_from_dict_validates():
    f = link.LinkFaults.from_dict({"windows": [[90, 12], [200, 12]], "loss_pct": 1,
                                   "zones": ["north_east_blocks"]})
    assert f.windows == ((90.0, 12.0), (200.0, 12.0))
    assert f.zones[0].min_x == -110.0
    with pytest.raises(ValueError):
        link.LinkFaults.from_dict({"loss_pct": 150})
    with pytest.raises(ValueError):
        link.LinkFaults.from_dict({"zones": ["nowhere"]})
    with pytest.raises(ValueError):
        link.LinkFaults.from_dict({"windows": [[10, -1]]})

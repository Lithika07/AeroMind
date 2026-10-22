import numpy as np
import pandas as pd

from tools import anomalies
from tools.ingest import FlightData, LogFile


def flight_with_current(values, rate_hz=5.0):
    times = 1000.0 + np.arange(len(values)) / rate_hz
    status = pd.DataFrame({"t": times, "current_battery": np.asarray(values) * 100.0})
    return FlightData(frames={"SYS_STATUS": status}, sequence=pd.DataFrame(columns=["t", "seq"]),
                      files=(LogFile("x", float(times[0]), float(times[-1]), len(times)),), vehicle_sysid=1)


def test_steady_signal_with_small_noise_has_no_anomalies():
    rng = np.random.default_rng(0)
    flight = flight_with_current(20 + rng.normal(0, 0.2, 300))
    assert anomalies.detect(flight, [(0, 2e9)]) == []


def test_spike_is_found_once_at_its_peak():
    values = np.full(300, 20.0)
    values[200:203] = [30.0, 40.0, 30.0]
    (found,) = anomalies.detect(flight_with_current(values), [(0, 2e9)])
    assert found.signal == "current" and found.value == 40.0
    assert found.t == 40.2 and found.z > 3


def test_drops_in_current_are_not_spikes():
    values = np.full(300, 30.0)
    values[200:] = 15.0
    assert anomalies.detect(flight_with_current(values), [(0, 2e9)]) == []


def test_outside_airborne_is_ignored():
    values = np.full(300, 20.0)
    values[200] = 60.0
    assert anomalies.detect(flight_with_current(values), [(0, 1)]) == []

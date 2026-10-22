"""Spikes in vibration, current and altitude error: a trailing rolling z-score, |z| > 3, while airborne.

Each signal has a floor on its standard deviation, so a perfectly steady signal (the simulator's,
often) does not turn a tiny wobble into a 'spike'. Consecutive flagged samples are one anomaly,
reported at its largest |z|.
"""
import numpy as np
import pandas as pd

from agents.schemas import Anomaly
from tools import timeline

Z_LIMIT = 3.0
WINDOW_S = 20.0
MIN_SAMPLES = 10
CLUSTER_GAP_S = 5.0
MAX_ANOMALIES = 20

#: name -> (message, value function, minimum standard deviation, one-sided)
#: Vibration and current are spikes only when they rise: current falls every time a climb ends.
SIGNALS = {
    "vibration": ("VIBRATION", lambda f: f[["vibration_x", "vibration_y", "vibration_z"]].max(axis=1), 1.0, True),
    "current": ("SYS_STATUS", lambda f: f["current_battery"] / 100.0, 2.0, True),
    "altitude_error": ("NAV_CONTROLLER_OUTPUT", lambda f: f["alt_error"], 0.3, False),
}


def zscores(times: np.ndarray, values: np.ndarray, min_std: float) -> np.ndarray:
    """z of each sample against the samples in the WINDOW_S before it (nan with too few)."""
    series = pd.Series(values, index=pd.to_datetime(times, unit="s"))
    previous = series.shift(1)
    rolling = previous.rolling(f"{int(WINDOW_S)}s", min_periods=MIN_SAMPLES)
    mean, std = rolling.mean().to_numpy(), rolling.std().to_numpy()
    return (values - mean) / np.maximum(np.nan_to_num(std, nan=min_std), min_std)


def _clusters(times: np.ndarray, z: np.ndarray, one_sided: bool) -> list:
    score = np.nan_to_num(z) if one_sided else np.abs(np.nan_to_num(z))
    flagged = np.flatnonzero(score > Z_LIMIT)
    clusters, current = [], []
    for index in flagged:
        if current and times[index] - times[current[-1]] > CLUSTER_GAP_S:
            clusters.append(current)
            current = []
        current.append(index)
    if current:
        clusters.append(current)
    return [max(cluster, key=lambda i: abs(z[i])) for cluster in clusters]


def detect(flight, airborne: list) -> list:
    anomalies = []
    for signal, (message, value_of, min_std, one_sided) in SIGNALS.items():
        frame = timeline.during(flight.frame(message), airborne)
        if len(frame) < MIN_SAMPLES:
            continue
        times = frame["t"].to_numpy()
        values = value_of(frame).to_numpy(dtype=float)
        z = zscores(times, values, min_std)
        for index in _clusters(times, z, one_sided):
            anomalies.append(Anomaly(t=round(float(times[index] - flight.t0), 1), signal=signal,
                                     value=round(float(values[index]), 2), z=round(float(z[index]), 1)))
    anomalies.sort(key=lambda a: -abs(a.z))
    return sorted(anomalies[:MAX_ANOMALIES], key=lambda a: a.t)

"""Telemetry link quality across the whole flight (PRD "Telemetry link metrics").

A dropout is any silence from the vehicle longer than 2 s, measured on every vehicle message rather
than only on 1 Hz heartbeats so its start and length are accurate to a tenth of a second. The
vehicle's own clock (time_boot_ms) must also have moved on by more than 2 s across the silence: a
ground station that stalls, or a simulator running slower than real time, leaves gaps in the
receive times that are not link losses. Packet
loss counts missing MAVLink sequence numbers, but only between packets on either side of no
dropout: the 8-bit sequence wraps every 256 packets, so a gap's count is meaningless.
"""
import numpy as np
import pandas as pd

from agents.schemas import Dropout, LinkInfo, Rssi
from tools import geo
from tools import timeline
from tools import waypoints as wp

DROPOUT_GAP_S = 2.0
SEQ_MODULO = 256
RC_RSSI_UNKNOWN = 255
RATE_WINDOW_S = 10.0
STRIP_STEP_S = 1.0
LOSS_CAUTION_PCT = 5.0
DEG_E7 = 1e7


def find_gaps(times: np.ndarray, limit: float = DROPOUT_GAP_S) -> list:
    """[(start, duration)] of every silence longer than `limit`."""
    if len(times) < 2:
        return []
    steps = np.diff(times)
    return [(float(times[i]), float(steps[i])) for i in np.flatnonzero(steps > limit)]


def vehicle_clock(flight) -> pd.DataFrame:
    """t (receive time), boot_s (vehicle time) from the 10 Hz messages that carry time_boot_ms."""
    parts = [flight.frame(kind)[["t", "time_boot_ms"]] for kind in ("ATTITUDE", "GLOBAL_POSITION_INT")
             if "time_boot_ms" in flight.frame(kind)]
    if not parts:
        return pd.DataFrame(columns=["t", "boot_s"])
    clock = pd.concat(parts).sort_values("t", kind="stable")
    return pd.DataFrame({"t": clock["t"].to_numpy(), "boot_s": clock["time_boot_ms"].to_numpy() / 1000.0})


def link_gaps(gaps: list, clock: pd.DataFrame, limit: float = DROPOUT_GAP_S) -> list:
    """The gaps across which the vehicle's clock also advanced by more than `limit`."""
    if clock.empty:
        return gaps
    times, boot = clock["t"].to_numpy(), clock["boot_s"].to_numpy()
    kept = []
    for start, duration in gaps:
        before = np.searchsorted(times, start, side="right") - 1
        after = np.searchsorted(times, start + duration, side="left")
        if before < 0 or after >= len(times) or boot[after] - boot[before] > limit:
            kept.append((start, duration))
    return kept


def packet_loss_pct(sequence: pd.DataFrame, gaps: list):
    if len(sequence) < 2:
        return None
    seq = sequence["seq"].to_numpy(dtype=int)
    times = sequence["t"].to_numpy()
    missing = (np.diff(seq) - 1) % SEQ_MODULO
    across_gap = np.zeros(len(missing), dtype=bool)
    for start, duration in gaps:
        across_gap |= (times[:-1] <= start) & (times[1:] >= start + duration)
    lost = int(missing[~across_gap].sum())
    received = len(seq)
    return round(100.0 * lost / (lost + received), 2)


def nearest_waypoint(mission, lat, lon):
    """Sequence number of the mission waypoint nearest (lat, lon)."""
    if not mission or lat is None:
        return None
    candidates = [item for item in wp.nav_waypoints(mission) if item.lat or item.lon]
    if not candidates:
        return None
    return min(candidates, key=lambda item: geo.distance_m(lat, lon, item.lat, item.lon)).seq


def dropouts(flight, gaps: list) -> list:
    position = flight.frame("GLOBAL_POSITION_INT")
    current = flight.frame("MISSION_CURRENT")
    boundaries = [f.t_end for f in flight.files[:-1]]
    result = []
    for start, duration in gaps:
        lat = timeline.value_at(position, "lat", start)
        lon = timeline.value_at(position, "lon", start)
        lat = None if lat is None else float(lat) / DEG_E7
        lon = None if lon is None else float(lon) / DEG_E7
        near = nearest_waypoint(flight.mission, lat, lon)
        if near is None:
            seq = timeline.value_at(current, "seq", start)
            near = None if seq is None else int(seq)
        result.append(Dropout(t=round(start - flight.t0, 1), duration_s=round(duration, 1), lat=lat, lon=lon,
                              near_wp=near, between_files=any(abs(b - start) < 0.5 for b in boundaries)))
    return result


def rssi(flight):
    radio = flight.frame("RADIO_STATUS")
    rc = flight.frame("RC_CHANNELS")
    rc_values = rc["rssi"][rc["rssi"] != RC_RSSI_UNKNOWN] if not rc.empty else pd.Series(dtype=float)
    if radio.empty and rc_values.empty:
        return None
    return Rssi(rssi_min=float(radio["rssi"].min()) if not radio.empty else None,
                rssi_mean=round(float(radio["rssi"].mean()), 1) if not radio.empty else None,
                remrssi_min=float(radio["remrssi"].min()) if not radio.empty else None,
                noise_max=float(radio["noise"].max()) if not radio.empty else None,
                rc_rssi_min=float(rc_values.min()) if not rc_values.empty else None)


def position_rate(position: pd.DataFrame, window, gaps: list) -> tuple:
    """(median Hz, worst 10 s window / median) in vehicle time, ignoring dropouts, which are counted
    separately."""
    rows = timeline.in_window(position, window)
    if len(rows) < 2:
        return None, None
    times = rows["time_boot_ms"].to_numpy() / 1000.0
    receive = rows["t"].to_numpy()
    edges = np.arange(times[0], times[-1] + RATE_WINDOW_S, RATE_WINDOW_S)
    counts, _ = np.histogram(times, bins=edges)
    usable = np.ones(len(counts), dtype=bool)
    for start, duration in gaps:
        inside = times[(receive >= start - 0.5) & (receive <= start + duration + 0.5)]
        if len(inside):
            usable &= ~((edges[1:] > inside.min()) & (edges[:-1] < inside.max()))
    full = usable & (edges[1:] <= times[-1])
    rates = counts[full] / RATE_WINDOW_S
    if len(rates) == 0:
        return None, None
    median = float(np.median(rates))
    return round(median, 1), (round(float(rates.min() / median), 2) if median > 0 else None)


def compute(flight, window) -> LinkInfo:
    if window is None:
        return LinkInfo()
    times = flight.sequence["t"].to_numpy()
    in_flight = times[(times >= window[0]) & (times <= window[1])]
    clock = vehicle_clock(flight)
    gaps = link_gaps(find_gaps(np.concatenate(([window[0]], in_flight, [window[1]]))), clock)
    flight_s = window[1] - window[0]
    lost_s = sum(duration for _, duration in gaps)
    rate, ratio = position_rate(flight.frame("GLOBAL_POSITION_INT"), window, gaps)
    return LinkInfo(uptime_pct=round(100.0 * (1 - lost_s / flight_s), 1) if flight_s > 0 else None,
                    packet_loss_pct=packet_loss_pct(flight.sequence, link_gaps(find_gaps(times), clock)),
                    dropouts=dropouts(flight, gaps), rssi=rssi(flight),
                    position_rate_hz=rate, position_rate_min_ratio=ratio)


def quality_per_second(flight) -> pd.DataFrame:
    """Link quality each second of the flight: bad in a dropout, caution with >5 % packet loss, else good."""
    window = timeline.armed_window(flight.frame("HEARTBEAT"))
    if window is None:
        return pd.DataFrame(columns=["t", "link", "rate"])
    seq = flight.sequence
    times, numbers = seq["t"].to_numpy(), seq["seq"].to_numpy(dtype=int)
    gaps = link_gaps(find_gaps(times), vehicle_clock(flight))
    starts = np.arange(window[0], window[1], STRIP_STEP_S)
    missing = (np.diff(numbers) - 1) % SEQ_MODULO
    rows = []
    for start in starts:
        inside = (times[1:] >= start) & (times[1:] < start + STRIP_STEP_S)
        received = int(inside.sum())
        lost = int(missing[inside].sum()) if received else 0
        in_gap = any(g <= start < g + d for g, d in gaps)
        loss = 100.0 * lost / (lost + received) if received else 100.0
        quality = "bad" if in_gap else "caution" if loss > LOSS_CAUTION_PCT else "good"
        rows.append((start - flight.t0, quality, received / STRIP_STEP_S))
    return pd.DataFrame(rows, columns=["t", "link", "rate"])

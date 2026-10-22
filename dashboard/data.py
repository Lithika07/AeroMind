"""Data for the dashboard: saved runs, time series from the flight's own logs, the link strip."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools import ingest, link_metrics, timeline
from tools import waypoints as wp

DEG_E7 = 1e7


def saved_runs(outputs: Path) -> list:
    """Run ids with a state.json, newest first."""
    runs = [p for p in Path(outputs).iterdir() if (p / "state.json").exists()] if Path(outputs).is_dir() else []
    return [p.name for p in sorted(runs, key=lambda p: (p / "state.json").stat().st_mtime, reverse=True)]


def load_state(outputs: Path, run_id: str) -> dict:
    return json.loads((Path(outputs) / run_id / "state.json").read_text())


def load_flight(sources: dict):
    """The flight's data again from the files the analysis read (None if they are gone)."""
    from pipeline import resolve
    tlogs = [resolve(p) for p in sources["tlogs"]]
    if not tlogs or not all(p.exists() for p in tlogs):
        return None
    mission = resolve(sources["mission"]) if sources.get("mission") else None
    return ingest.load_flight(tlogs, mission if mission and mission.exists() else None)


def series(flight, msg_type: str, columns: dict) -> pd.DataFrame:
    """t (s from log start) plus `columns` {name: function(frame)} for one message type."""
    frame = flight.frame(msg_type)
    if frame.empty:
        return pd.DataFrame(columns=["t", *columns])
    data = {"t": frame["t"] - flight.t0}
    data.update({name: fn(frame) for name, fn in columns.items()})
    return pd.DataFrame(data)


def track(flight) -> pd.DataFrame:
    """Flown path with each point's link quality at that moment."""
    window = timeline.armed_window(flight.frame("HEARTBEAT"))
    rows = timeline.in_window(flight.frame("GLOBAL_POSITION_INT"), window)
    if rows.empty:
        return pd.DataFrame(columns=["t", "lat", "lon", "alt", "link"])
    strip = link_strip(flight)
    t = rows["t"].to_numpy() - flight.t0
    quality = strip.set_index("t")["link"].reindex(np.floor(t), method="nearest").to_numpy() if not strip.empty \
        else np.array(["good"] * len(t))
    return pd.DataFrame({"t": t, "lat": rows["lat"] / DEG_E7, "lon": rows["lon"] / DEG_E7,
                         "alt": rows["relative_alt"] / 1000.0, "link": quality})


def link_strip(flight) -> pd.DataFrame:
    return link_metrics.quality_per_second(flight)


def mission_points(mission) -> pd.DataFrame:
    if not mission:
        return pd.DataFrame(columns=["wp", "lat", "lon"])
    home = mission[0]
    points = [(0, home.lat, home.lon)] + [(i.seq, i.lat, i.lon) for i in wp.nav_waypoints(mission)]
    if wp.ends_with_return(mission):
        points.append((mission[-1].seq, home.lat, home.lon))
    return pd.DataFrame(points, columns=["wp", "lat", "lon"])


def message_rates(flight) -> pd.DataFrame:
    duration = max(1e-6, flight.files[-1].t_end - flight.files[0].t_start)
    rows = [(kind, len(frame), round(len(frame) / duration, 2)) for kind, frame in flight.frames.items()]
    return pd.DataFrame(sorted(rows, key=lambda r: -r[1]), columns=["message", "count", "per second"])

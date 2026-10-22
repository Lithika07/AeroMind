"""Telemetry link faults between the vehicle and the recording ground station. Pure logic.

Three kinds, combinable per scenario:
  windows   the link is down for (start_s, duration_s) after arming (S3's disconnects)
  zones     the link is down while the drone is inside a no-network zone (S4's radio shadow)
  loss_pct  individual packets are lost at random while the link is up

Every outage is kept with its start, end and position: the ground truth that dropout detection
is scored against.
"""
import random
from dataclasses import dataclass, field, replace

from sim import zones as zone_table

#: Once inside a zone, the link stays down until the drone is this far outside it, so a drone on
#: the boundary does not flap.
ZONE_LEAVE_MARGIN_M = 3.0
MAX_LOSS_PCT = 100.0


@dataclass(frozen=True)
class LinkFaults:
    windows: tuple = ()
    zones: tuple = ()
    loss_pct: float = 0.0

    @classmethod
    def from_dict(cls, config: dict) -> "LinkFaults":
        """From a scenario's `link:` block; zones are named from the world's zone table."""
        windows = tuple((float(start), float(duration)) for start, duration in config.get("windows", ()))
        if any(start < 0 or duration <= 0 for start, duration in windows):
            raise ValueError(f"link windows need start >= 0 and duration > 0: {windows}")
        network_zones = zone_table.of_kind(zone_table.NETWORK)
        unknown = [name for name in config.get("zones", ()) if name not in network_zones]
        if unknown:
            raise ValueError(f"unknown no-network zones {unknown}; known: {sorted(network_zones)}")
        loss_pct = float(config.get("loss_pct", 0.0))
        if not 0.0 <= loss_pct <= MAX_LOSS_PCT:
            raise ValueError(f"loss_pct must be 0-100, got {loss_pct}")
        return cls(windows=windows, zones=tuple(network_zones[n] for n in config.get("zones", ())),
                   loss_pct=loss_pct)


def outage(faults: LinkFaults, t_armed, position, was_down: bool = False):
    """Why the link is down now ("timed" or "zone"), or None if it is up.

    t_armed: seconds since the vehicle armed, None before arming.
    position: (east, north) metres, None if not yet known.
    """
    if t_armed is not None and any(start <= t_armed < start + duration for start, duration in faults.windows):
        return "timed"
    if position is not None and faults.zones:
        distance = min(area.distance_outside(*position) for area in faults.zones)
        if distance == 0.0 or (was_down and distance < ZONE_LEAVE_MARGIN_M):
            return "zone"
    return None


def lose_packet(faults: LinkFaults, rng: random.Random) -> bool:
    return faults.loss_pct > 0 and rng.random() * 100.0 < faults.loss_pct


@dataclass(frozen=True)
class Outage:
    reason: str
    start_unix: float
    end_unix: float
    start_t_armed: float
    lat: float
    lon: float

    @property
    def duration_s(self) -> float:
        return self.end_unix - self.start_unix

    def as_dict(self) -> dict:
        return {"reason": self.reason, "start_unix": self.start_unix, "end_unix": self.end_unix,
                "duration_s": round(self.duration_s, 3), "start_t_armed": self.start_t_armed,
                "lat": self.lat, "lon": self.lon}


@dataclass(frozen=True)
class OutageTracker:
    """Turns the per-packet up/down decision into outages. Each update returns a new tracker."""
    outages: tuple = ()
    current: Outage = field(default=None)

    def update(self, now_unix: float, t_armed, reason, lat_lon) -> "OutageTracker":
        if reason and self.current is None:
            lat, lon = lat_lon if lat_lon else (None, None)
            start = Outage(reason, now_unix, now_unix, t_armed, lat, lon)
            return replace(self, current=start)
        if not reason and self.current is not None:
            return self.finish(now_unix)
        return self

    def finish(self, now_unix: float) -> "OutageTracker":
        if self.current is None:
            return self
        closed = replace(self.current, end_unix=now_unix)
        return OutageTracker(outages=self.outages + (closed,), current=None)

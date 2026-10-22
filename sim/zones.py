"""Where the disaster world has no network or no GPS (world ENU metres).

Copied from Aero Sense's zone table, which the world's red/orange/purple ground outlines
(model aero_sense_zone_signs) are drawn from. AeroMind's link simulator uses the no-network zones
as radio shadows.
"""
from dataclasses import dataclass

NETWORK, GPS = "network", "gps"


@dataclass(frozen=True)
class Area:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def distance_outside(self, x: float, y: float) -> float:
        """Metres from (x, y) to the area, 0 inside it."""
        dx = max(self.min_x - x, 0.0, x - self.max_x)
        dy = max(self.min_y - y, 0.0, y - self.max_y)
        return (dx * dx + dy * dy) ** 0.5


#: name -> (area, what is lost there)
ZONES = {
    # the radio mast in the north-east blocks lost its antennas: no coverage, GPS still fine
    "north_east_blocks": (Area(-110.0, 50.0, -20.0, 92.0), frozenset({NETWORK})),
    # collapsed concrete canyons in the north-west: satellites blocked, the link still up
    "north_west_blocks": (Area(-180.0, 50.0, -122.0, 92.0), frozenset({GPS})),
    # the southern lanes lost both
    "south_lanes": (Area(-160.0, 10.0, -60.0, 38.0), frozenset({GPS, NETWORK})),
}


def of_kind(kind: str) -> dict:
    """name -> area of every zone where `kind` is lost."""
    return {name: area for name, (area, lost) in ZONES.items() if kind in lost}

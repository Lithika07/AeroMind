"""Mission files in the QGC WPL 110 format (Mission Planner's and QGroundControl's .waypoints).

Each row: seq, current, frame, command, param1-4, lat, lon, alt, autocontinue (tab separated).
Row 0 is home. Items are immutable; `seq` is reassigned when a mission is written.
"""
from dataclasses import dataclass, replace

HEADER = "QGC WPL 110"
FIELDS = 12

NAV_WAYPOINT = 16
NAV_RETURN_TO_LAUNCH = 20
NAV_LAND = 21
NAV_TAKEOFF = 22
DO_CHANGE_SPEED = 178

FRAME_GLOBAL = 0
FRAME_GLOBAL_RELATIVE_ALT = 3

COMMAND_NAMES = {
    NAV_WAYPOINT: "NAV_WAYPOINT",
    NAV_RETURN_TO_LAUNCH: "NAV_RETURN_TO_LAUNCH",
    NAV_LAND: "NAV_LAND",
    NAV_TAKEOFF: "NAV_TAKEOFF",
    DO_CHANGE_SPEED: "DO_CHANGE_SPEED",
}


@dataclass(frozen=True)
class Item:
    seq: int
    current: int
    frame: int
    command: int
    param1: float
    param2: float
    param3: float
    param4: float
    lat: float
    lon: float
    alt: float
    autocontinue: int = 1


def command_name(command: int) -> str:
    return COMMAND_NAMES.get(command, f"CMD_{command}")


def parse(text: str) -> list:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].strip().startswith("QGC WPL"):
        raise ValueError(f"not a {HEADER} mission file (first line must be '{HEADER}')")
    items = []
    for number, line in enumerate(lines[1:], start=2):
        fields = line.split()
        if len(fields) != FIELDS:
            raise ValueError(f"line {number}: expected {FIELDS} fields, got {len(fields)}")
        try:
            seq, current, frame, command = (int(f) for f in fields[:4])
            params = [float(f) for f in fields[4:11]]
            autocontinue = int(float(fields[11]))
        except ValueError as error:
            raise ValueError(f"line {number}: {error}") from error
        items.append(Item(seq, current, frame, command, *params, autocontinue))
    return items


def load(path) -> list:
    with open(path) as handle:
        return parse(handle.read())


def _number(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))


def dumps(items: list) -> str:
    rows = [HEADER]
    for seq, item in enumerate(items):
        values = (seq, item.current, item.frame, item.command, item.param1, item.param2, item.param3,
                  item.param4, item.lat, item.lon, item.alt, item.autocontinue)
        rows.append("\t".join(_number(v) if isinstance(v, float) else str(v) for v in values))
    return "\n".join(rows) + "\n"


def save(path, items: list) -> None:
    with open(path, "w") as handle:
        handle.write(dumps(items))


def renumber(items: list) -> list:
    return [replace(item, seq=seq) for seq, item in enumerate(items)]


def nav_waypoints(items: list) -> list:
    return [item for item in items[1:] if item.command == NAV_WAYPOINT]


def ends_with_return(items: list) -> bool:
    return bool(items) and items[-1].command in (NAV_RETURN_TO_LAUNCH, NAV_LAND)

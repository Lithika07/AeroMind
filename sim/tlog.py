"""Write MAVLink telemetry logs (.tlog) the way a ground station does.

A tlog is a sequence of records: an 8-byte big-endian time in microseconds since the Unix epoch,
then one raw MAVLink packet. Mission Planner starts a new file when it reconnects, so a link that
falls silent for longer than `rotate_gap_s` starts a new file here too.
"""
import struct
import time
from pathlib import Path

ROTATE_GAP_S = 5.0
TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
US_PER_S = 1_000_000


class TlogWriter:
    def __init__(self, directory: Path, rotate_gap_s: float = ROTATE_GAP_S):
        self.directory = Path(directory)
        self.rotate_gap_s = rotate_gap_s
        self.paths = []
        self._file = None
        self._last_write = None

    def write(self, packet: bytes, now: float = None) -> None:
        now = time.time() if now is None else now
        if self._file is None or (self._last_write is not None and now - self._last_write > self.rotate_gap_s):
            self._open(now)
        self._file.write(struct.pack(">Q", int(round(now * US_PER_S))) + packet)
        self._last_write = now

    def _open(self, now: float) -> None:
        self.close()
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = time.strftime(TIME_FORMAT, time.localtime(now))
        path = self.directory / f"{stem}.tlog"
        suffix = 1
        while path.exists() or path in self.paths:
            path = self.directory / f"{stem}_{suffix}.tlog"
            suffix += 1
        self._file = open(path, "wb")
        self.paths.append(path)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

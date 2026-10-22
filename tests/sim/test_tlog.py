import struct

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink

from sim import tlog


def heartbeat_bytes(seq: int = 0) -> bytes:
    mav = mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
    mav.seq = seq
    msg = mav.heartbeat_encode(mavlink.MAV_TYPE_HEXAROTOR, mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, 0, 0, 0)
    return msg.pack(mav)


def test_written_tlog_reads_back_with_pymavlink(tmp_path):
    writer = tlog.TlogWriter(tmp_path)
    writer.write(heartbeat_bytes(0), now=1000.0)
    writer.write(heartbeat_bytes(1), now=1000.5)
    writer.close()
    (path,) = writer.paths
    log = mavutil.mavlink_connection(str(path))
    first = log.recv_match(type="HEARTBEAT")
    second = log.recv_match(type="HEARTBEAT")
    assert first._timestamp == 1000.0 and second._timestamp == 1000.5
    assert second.get_seq() == 1


def test_record_format_is_big_endian_microseconds_then_bytes(tmp_path):
    writer = tlog.TlogWriter(tmp_path)
    packet = heartbeat_bytes()
    writer.write(packet, now=2.5)
    writer.close()
    data = writer.paths[0].read_bytes()
    assert struct.unpack(">Q", data[:8])[0] == 2_500_000
    assert data[8:] == packet


def test_gap_longer_than_rotate_starts_a_new_file(tmp_path):
    writer = tlog.TlogWriter(tmp_path, rotate_gap_s=5.0)
    writer.write(heartbeat_bytes(), now=100.0)
    writer.write(heartbeat_bytes(), now=104.9)
    writer.write(heartbeat_bytes(), now=110.0)
    writer.close()
    assert len(writer.paths) == 2
    assert all(p.suffix == ".tlog" for p in writer.paths)
    assert writer.paths[0] != writer.paths[1]


def test_close_without_writes_creates_nothing(tmp_path):
    writer = tlog.TlogWriter(tmp_path)
    writer.close()
    assert writer.paths == [] and list(tmp_path.iterdir()) == []

import pytest
from pymavlink.dialects.v20 import ardupilotmega as mavlink

from sim.tlog import TlogWriter
from tools import ingest


def vehicle_packets(sysid=1):
    mav = mavlink.MAVLink(None, srcSystem=sysid, srcComponent=1)
    return (lambda armed: mav.heartbeat_encode(mavlink.MAV_TYPE_HEXAROTOR, mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                                               128 if armed else 0, 3, 0).pack(mav),
            lambda: mav.attitude_encode(0, 0.1, 0.2, 0.3, 0, 0, 0).pack(mav))


def write_log(directory, entries, rotate_gap_s=5.0):
    writer = TlogWriter(directory, rotate_gap_s=rotate_gap_s)
    for t, packet in entries:
        writer.write(packet, now=t)
    writer.close()
    return writer.paths


def test_two_files_merge_in_time_order(tmp_path):
    heartbeat, attitude = vehicle_packets()
    paths = write_log(tmp_path, [(100.0, heartbeat(True)), (100.5, attitude()), (120.0, heartbeat(True)),
                                 (120.5, attitude())])
    assert len(paths) == 2
    frames, sequence, files, sysid = ingest.read_tlogs(list(reversed(paths)))
    assert sysid == 1
    assert list(frames["HEARTBEAT"]["t"]) == [100.0, 120.0]
    assert list(frames["ATTITUDE"]["roll"].round(3)) == [0.1, 0.1]
    assert [f.t_start for f in files] == [100.0, 120.0]
    assert len(sequence) == 4


def test_ground_station_messages_are_dropped(tmp_path):
    heartbeat, _ = vehicle_packets()
    gcs = mavlink.MAVLink(None, srcSystem=255, srcComponent=190)
    gcs_hb = gcs.heartbeat_encode(mavlink.MAV_TYPE_GCS, mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0).pack(gcs)
    paths = write_log(tmp_path, [(1.0, gcs_hb), (1.1, heartbeat(False)), (1.2, gcs_hb)])
    frames, sequence, _, _ = ingest.read_tlogs(paths)
    assert len(frames["HEARTBEAT"]) == 1 and len(sequence) == 1


def test_log_without_a_vehicle_is_rejected(tmp_path):
    gcs = mavlink.MAVLink(None, srcSystem=255, srcComponent=190)
    paths = write_log(tmp_path, [(1.0, gcs.heartbeat_encode(6, 8, 0, 0, 0).pack(gcs))])
    with pytest.raises(ingest.IngestError, match="no messages from a vehicle"):
        ingest.read_tlogs(paths)


def test_no_logs_is_an_error():
    with pytest.raises(ingest.IngestError):
        ingest.read_tlogs([])


@pytest.mark.parametrize("text", ["BATT_CAPACITY,2200\nFS_THR_ENABLE,1\n",
                                  "BATT_CAPACITY 2200\nFS_THR_ENABLE\t1\n# comment\n\n"])
def test_read_params_both_formats(tmp_path, text):
    path = tmp_path / "p.param"
    path.write_text(text)
    assert ingest.read_params(path) == {"BATT_CAPACITY": 2200.0, "FS_THR_ENABLE": 1.0}


def test_read_params_rejects_garbage(tmp_path):
    path = tmp_path / "p.param"
    path.write_text("BATT_CAPACITY,abc\n")
    with pytest.raises(ingest.IngestError, match="line 1"):
        ingest.read_params(path)


def test_notes_are_trimmed_and_capped():
    assert ingest.clean_notes("  wobbly \n on   landing ") == "wobbly on landing"
    assert ingest.clean_notes("   ") is None
    assert len(ingest.clean_notes("x" * 5000)) == ingest.MAX_NOTES_CHARS

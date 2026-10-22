import pytest

from tools import waypoints as wp

SAMPLE = """QGC WPL 110
0\t1\t0\t16\t0\t0\t0\t0\t-35.363262\t149.165237\t584.000000\t1
1\t0\t3\t22\t0\t0\t0\t0\t0\t0\t30\t1
2\t0\t3\t178\t1\t5\t-1\t0\t0\t0\t0\t1
3\t0\t3\t16\t0\t0\t0\t0\t-35.364\t149.166\t30\t1
4\t0\t3\t20\t0\t0\t0\t0\t0\t0\t0\t1
"""


def test_parse_reads_every_row():
    items = wp.parse(SAMPLE)
    assert [i.command for i in items] == [16, 22, 178, 16, 20]
    assert items[0].current == 1 and items[0].frame == 0
    assert items[2].param2 == 5.0
    assert items[3].lat == -35.364 and items[3].alt == 30.0


def test_round_trip_is_lossless():
    items = wp.parse(SAMPLE)
    assert wp.parse(wp.dumps(items)) == items


def test_dumps_renumbers_sequentially():
    items = wp.parse(SAMPLE)
    text = wp.dumps(items[:2] + items[3:])
    assert [line.split("\t")[0] for line in text.splitlines()[1:]] == ["0", "1", "2", "3"]


def test_parse_rejects_missing_header():
    with pytest.raises(ValueError, match="QGC WPL"):
        wp.parse("1\t0\t3\t16\t0\t0\t0\t0\t0\t0\t0\t1\n")


def test_parse_rejects_short_rows():
    with pytest.raises(ValueError, match="line 2"):
        wp.parse("QGC WPL 110\n0\t1\t0\t16\n")


def test_parse_ignores_blank_lines():
    assert len(wp.parse(SAMPLE + "\n\n")) == 5


def test_nav_waypoints_and_names():
    items = wp.parse(SAMPLE)
    assert [i.seq for i in wp.nav_waypoints(items)] == [3]
    assert wp.command_name(178) == "DO_CHANGE_SPEED"
    assert wp.command_name(999) == "CMD_999"


def test_ends_with_return():
    items = wp.parse(SAMPLE)
    assert wp.ends_with_return(items)
    assert not wp.ends_with_return(items[:-1])

import pytest

from agents.schemas import Edit
from sim import scenarios, world
from tools import mission_io
from tools import waypoints as wp


@pytest.fixture(scope="module")
def mission():
    table = scenarios.load()
    return scenarios.mission(table["s1"], scenarios.load_route(), world.origin(world.DEFAULT_WORLD))


def edit(action, seq, value=None, cause="C1"):
    return Edit(action=action, wp=seq, value=value, cause=cause)


def test_route_length_of_the_demo_route(mission):
    assert 1250 < mission_io.route_length_m(mission) < 1400


def test_set_speed_updates_the_speed_command_before_the_first_waypoint(mission):
    fixed, applied, rejected = mission_io.apply_edits(mission, [edit("set_speed", 3, 6)], {"C1"})
    assert rejected == [] and len(fixed) == len(mission)
    assert [i.param2 for i in fixed if i.command == wp.DO_CHANGE_SPEED] == [6.0]


def test_set_speed_mid_route_inserts_a_speed_command(mission):
    fixed, applied, _ = mission_io.apply_edits(mission, [edit("set_speed", 6, 7)], {"C1"})
    assert len(fixed) == len(mission) + 1
    speeds = [k for k, i in enumerate(fixed) if i.command == wp.DO_CHANGE_SPEED]
    assert fixed[speeds[-1]].param2 == 7.0 and fixed[speeds[-1] + 1].command == wp.NAV_WAYPOINT
    assert [i.seq for i in fixed] == list(range(len(fixed)))


def test_original_is_not_modified(mission):
    before = list(mission)
    mission_io.apply_edits(mission, [edit("remove_waypoint", 5)], {"C1"})
    assert mission == before


@pytest.mark.parametrize("bad, reason", [
    (edit("set_speed", 3, 15), "speed must be"),
    (edit("set_speed", 1, 5), "not a navigation waypoint"),
    (edit("change_altitude", 4, -10), "outside 25-120"),
    (edit("change_altitude", 4, 30), "within +/-20"),
    (edit("remove_waypoint", 1), "cannot be edited"),
    (edit("remove_waypoint", 11), "cannot be edited"),
    (edit("add_hold", 4, 30), "hold must be"),
    (edit("add_hold", 99, 3), "not in the mission"),
    (edit("set_speed", 3, 6, cause="C9"), "was not diagnosed"),
])
def test_out_of_limit_edits_are_rejected_with_a_reason(mission, bad, reason):
    fixed, applied, rejected = mission_io.apply_edits(mission, [bad], {"C1"})
    assert applied == [] and reason in rejected[0]["reason"]
    assert fixed == wp.renumber(mission)


def test_link_causes_get_advice_not_edits(mission):
    _, applied, rejected = mission_io.apply_edits(mission, [edit("set_speed", 3, 6, cause="C2")], {"C1", "C2"},
                                                  advice_only_causes={"C2"})
    assert applied == [] and "advice" in rejected[0]["reason"]


def test_at_most_thirty_percent_of_waypoints_removed(mission):
    edits = [edit("remove_waypoint", s) for s in (4, 5, 6)]
    _, applied, rejected = mission_io.apply_edits(mission, edits, {"C1"})
    assert len(applied) == 2 and "30%" in rejected[0]["reason"]


def test_at_most_five_edits(mission):
    edits = [edit("add_hold", s, 1) for s in range(3, 10)]
    _, applied, rejected = mission_io.apply_edits(mission, edits, {"C1"})
    assert len(applied) == 5 and len(rejected) == 2


def test_best_removals_shorten_the_route(mission):
    seqs = mission_io.best_removals(mission, 2)
    assert len(seqs) == 2
    shorter = [i for i in mission if i.seq not in seqs]
    assert mission_io.route_length_m(shorter) < mission_io.route_length_m(mission) - 100


def test_the_demo_route_clears_the_mast(mission):
    assert mission_io.obstacle_conflicts(mission) == []


def test_changelog_lists_both(mission):
    fixed, applied, rejected = mission_io.apply_edits(mission, [edit("set_speed", 3, 6), edit("set_speed", 3, 50)],
                                                      {"C1"})
    text = mission_io.changelog("s1", mission, fixed, applied, rejected)
    assert "set_speed WP3 6 m/s (cause C1)" in text and "speed must be" in text


def test_describe_changes_between_flown_missions(mission):
    fixed, _, _ = mission_io.apply_edits(mission, [edit("set_speed", 3, 6), edit("remove_waypoint", 4)], {"C1"})
    assert mission_io.describe_changes(mission, fixed) == ["removed WP4", "speed 12 → 6 m/s"]
    assert mission_io.describe_changes(mission, mission) == []

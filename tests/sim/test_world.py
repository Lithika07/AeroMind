import math
import xml.etree.ElementTree as ET

import pytest

from sim import world

WORLD_SDF = """<?xml version="1.0"?>
<sdf version="1.9">
  <world name="test_world">
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <spherical_coordinates>
      <latitude_deg>-35.363262</latitude_deg>
      <longitude_deg>149.165237</longitude_deg>
      <elevation>584</elevation>
    </spherical_coordinates>
    <frame name="drone_spawn"><pose>0 -110 0.1 0 0 1.5708</pose></frame>
  </world>
</sdf>
"""


@pytest.fixture
def world_file(tmp_path):
    path = tmp_path / "w.sdf"
    path.write_text(WORLD_SDF)
    return path


def test_origin_reads_spherical_coordinates(world_file):
    assert world.origin(world_file) == (-35.363262, 149.165237, 584.0)


def test_spawn_pose_stands_the_drone_on_its_gear_above_the_frame(world_file):
    x, y, z, yaw = world.spawn_pose(world_file)
    assert (x, y) == (0.0, -110.0)
    assert z == pytest.approx(0.1 + world.GEAR_HEIGHT_M)
    assert yaw == pytest.approx(1.5708)


def test_spawn_pose_converts_degrees(tmp_path):
    path = tmp_path / "w.sdf"
    path.write_text(WORLD_SDF.replace("<pose>0 -110 0.1 0 0 1.5708</pose>",
                                      '<pose degrees="true">1 2 0 0 0 90</pose>'))
    assert world.spawn_pose(path)[3] == pytest.approx(math.pi / 2)


def test_spawn_pose_without_frame_raises(tmp_path):
    path = tmp_path / "w.sdf"
    path.write_text(WORLD_SDF.replace('name="drone_spawn"', 'name="elsewhere"'))
    with pytest.raises(ValueError, match="drone_spawn"):
        world.spawn_pose(path)


def test_overlay_adds_drone_and_wind_wrench_without_touching_the_rest(world_file):
    text = world.overlay(world_file.read_text(), "aeromind_hexa", (1.0, 2.0, 3.0, 0.5))
    root = ET.fromstring(text)
    sdf_world = root.find("world")
    include = sdf_world.find("include")
    assert include.findtext("uri") == "model://aeromind_hexa"
    assert include.findtext("name") == "aeromind_hexa"
    assert [float(v) for v in include.findtext("pose").split()] == [1.0, 2.0, 3.0, 0.0, 0.0, 0.5]
    plugins = [p.get("filename") for p in sdf_world.findall("plugin")]
    assert plugins == ["gz-sim-physics-system", "gz-sim-apply-link-wrench-system"]
    assert sdf_world.find("spherical_coordinates/elevation").text == "584"


def test_overlay_does_not_mutate_the_source_text(world_file):
    source = world_file.read_text()
    world.overlay(source, "aeromind_hexa", (0, 0, 0, 0))
    assert world_file.read_text() == source


def test_world_name(world_file):
    assert world.world_name(world_file) == "test_world"


def test_resource_paths_include_models_and_their_texture_dirs(tmp_path):
    (tmp_path / "a" / "materials" / "textures").mkdir(parents=True)
    (tmp_path / "b").mkdir()
    paths = world.resource_paths(tmp_path)
    assert paths[0] == tmp_path
    assert tmp_path / "a" / "materials" / "textures" in paths
    assert len(paths) == 2


def test_port_is_free_detects_a_bound_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert not world.port_is_free(s.getsockname()[1])

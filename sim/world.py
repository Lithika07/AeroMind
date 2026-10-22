"""The simulation world: where it is on Earth, where the drone stands, and the runtime copy of the
world that adds the drone and the wind wrench.

The world file in sim/worlds is kept exactly as copied. Everything AeroMind needs on top of it
(the airframe, the ApplyLinkWrench system that simulates wind) goes into a generated copy under
sim/run/, so the source world is never edited.
"""
import math
import socket
import xml.etree.ElementTree as ET
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
MODELS_DIR = SIM_DIR / "models"
WORLDS_DIR = SIM_DIR / "worlds"
DEFAULT_WORLD = WORLDS_DIR / "aero_sense_disaster.sdf"

SPAWN_FRAME = "drone_spawn"
#: base_link height of the Hexa-X standing on its skids.
GEAR_HEIGHT_M = 0.5825
#: Dropped this far onto the pad: placed exactly at rest, Gazebo never writes the IMU link's pose
#: and SITL believes the drone stands at the world origin until take-off.
SPAWN_DROP_M = 0.05
WRENCH_PLUGIN = ("gz-sim-apply-link-wrench-system", "gz::sim::systems::ApplyLinkWrench")


def _world_element(path: Path) -> ET.Element:
    element = ET.parse(path).getroot().find("world")
    if element is None:
        raise ValueError(f"{path} has no <world>")
    return element


def world_name(path: Path) -> str:
    return _world_element(path).get("name")


def origin(path: Path) -> tuple:
    """(lat, lon, elevation) of the world origin. SITL gets this as its home, so ArduPilot's
    local NED origin is the Gazebo world origin."""
    coords = _world_element(path).find("spherical_coordinates")
    if coords is None:
        raise ValueError(f"{path} has no <spherical_coordinates>")
    return tuple(float(coords.findtext(tag)) for tag in ("latitude_deg", "longitude_deg", "elevation"))


def spawn_pose(path: Path) -> tuple:
    """(x, y, z, yaw) of base_link for a drone standing on the `drone_spawn` frame (ENU, rad)."""
    pose = _world_element(path).find(f"frame[@name='{SPAWN_FRAME}']/pose")
    if pose is None:
        raise ValueError(f"{path} has no <frame name='{SPAWN_FRAME}'><pose>")
    x, y, z, _, _, yaw = (float(v) for v in pose.text.split())
    if pose.get("degrees") == "true":
        yaw = math.radians(yaw)
    return x, y, z + GEAR_HEIGHT_M, yaw


def overlay(source_text: str, model: str, pose: tuple) -> str:
    """The world with the drone included at `pose` (x, y, z, yaw) and the ApplyLinkWrench system
    loaded. Returns new SDF text; the source is not modified."""
    root = ET.fromstring(source_text)
    sdf_world = root.find("world")
    if sdf_world is None:
        raise ValueError("source has no <world>")
    filename, name = WRENCH_PLUGIN
    plugins = sdf_world.findall("plugin")
    insert_at = list(sdf_world).index(plugins[-1]) + 1 if plugins else 0
    sdf_world.insert(insert_at, ET.Element("plugin", {"filename": filename, "name": name}))
    include = ET.SubElement(sdf_world, "include")
    ET.SubElement(include, "uri").text = f"model://{model}"
    ET.SubElement(include, "name").text = model
    x, y, z, yaw = pose
    ET.SubElement(include, "pose").text = f"{x} {y} {z} 0 0 {yaw}"
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def resource_paths(models_dir: Path = MODELS_DIR) -> list:
    """GZ_SIM_RESOURCE_PATH entries: the models, plus each model's materials/textures, because
    the copied third-party meshes name their textures by bare filename."""
    textures = sorted(d for d in models_dir.glob("*/materials/textures") if d.is_dir())
    return [models_dir, *textures]


def port_is_free(port: int, host: str = "127.0.0.1", kind: int = socket.SOCK_STREAM) -> bool:
    with socket.socket(socket.AF_INET, kind) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True

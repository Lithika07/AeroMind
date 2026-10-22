"""Wind in Gazebo: a persistent force on the airframe through the ApplyLinkWrench system."""
import subprocess

WORLD = "aero_sense_disaster"
LINK = "aeromind_hexa::base_link"
TIMEOUT_S = 10


def _publish(topic: str, msg_type: str, payload: str) -> None:
    result = subprocess.run(["gz", "topic", "-t", topic, "-m", msg_type, "-p", payload],
                            capture_output=True, text=True, timeout=TIMEOUT_S)
    if result.returncode != 0:
        raise RuntimeError(f"gz topic {topic} failed: {result.stderr.strip()}")


def apply(force_east_n: float, force_north_n: float, world: str = WORLD) -> None:
    payload = (f'entity: {{name: "{LINK}", type: LINK}}, '
               f"wrench: {{force: {{x: {force_east_n:.4f}, y: {force_north_n:.4f}, z: 0}}}}")
    _publish(f"/world/{world}/wrench/persistent", "gz.msgs.EntityWrench", payload)


def clear(world: str = WORLD) -> None:
    _publish(f"/world/{world}/wrench/clear", "gz.msgs.Entity", f'name: "{LINK}", type: LINK')

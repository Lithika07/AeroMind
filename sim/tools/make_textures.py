"""Generate the two textures AeroMind cannot redistribute from their source repos.

The ground's grass (GPL-3 upstream) and the bus's wheel texture (unlicensed upstream) are replaced
by procedural images of the same size, so the copied world renders without third-party files.

    python3 sim/tools/make_textures.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
GRASS_PATH = MODELS_DIR / "aero_sense_ground" / "materials" / "textures" / "grass_green.png"
WHEELS_PATH = MODELS_DIR / "bus" / "materials" / "textures" / "wheels_01.png"
GRASS_SIZE_PX = 512
WHEELS_SIZE_PX = 256
SEED = 7


def grass(size: int, rng: np.random.Generator) -> np.ndarray:
    """Mottled green: coarse patches plus fine blade noise."""
    coarse = rng.random((size // 32, size // 32))
    coarse = np.kron(coarse, np.ones((32, 32)))
    fine = rng.random((size, size))
    shade = 0.6 * coarse + 0.4 * fine
    base = np.array([62, 110, 44], dtype=float)
    spread = np.array([30, 40, 20], dtype=float)
    return (base + (shade[..., None] - 0.5) * spread).clip(0, 255).astype(np.uint8)


def wheels(size: int) -> np.ndarray:
    """Dark tyre with a grey hub, centred."""
    y, x = np.mgrid[0:size, 0:size]
    radius = np.hypot(x - size / 2, y - size / 2) / (size / 2)
    image = np.full((size, size, 3), 25, dtype=np.uint8)
    image[radius < 0.55] = 120
    image[radius < 0.15] = 70
    return image


def main() -> None:
    rng = np.random.default_rng(SEED)
    GRASS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WHEELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(grass(GRASS_SIZE_PX, rng), "RGB").save(GRASS_PATH)
    Image.fromarray(wheels(WHEELS_SIZE_PX), "RGB").save(WHEELS_PATH)


if __name__ == "__main__":
    main()

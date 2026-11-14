"""Shaded relief of the south polar region for the site map of the app (part of pipeline/build.py).

    uv run python pipeline/build_basemap.py

Reads the LOLA 40 m model (data/raw/lola, docs/SOURCES.md), averages it to about 630 m per
pixel over +-220 km around the pole and writes data/processed/basemap/south_pole_relief.png with
its extent in a JSON file next to it. The image is only a backdrop: no number in the app is
read from it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "lola" / "LDEM_80S_40MPP_ADJ.TIF"
OUT = ROOT / "data" / "processed" / "basemap" / "south_pole_relief.png"
HALF_WIDTH_M = 220_000.0
PIXELS = 700
#: Direction of the light for the shading (clockwise from map up) and its elevation, degrees.
LIGHT_AZIMUTH_DEG, LIGHT_ELEVATION_DEG = 315.0, 35.0
#: Slopes are exaggerated for the picture only (gentle polar terrain at 630 m per pixel).
VERTICAL_EXAGGERATION = 3.0


def shaded_relief(height_m: np.ndarray, pixel_m: float) -> np.ndarray:
    """Lambertian shading of a height grid (rows from top to bottom), values 0..1."""
    dz_dy, dz_dx = np.gradient(VERTICAL_EXAGGERATION * height_m, pixel_m)
    dz_dy = -dz_dy  # rows run towards -y
    azimuth, elevation = np.deg2rad(LIGHT_AZIMUTH_DEG), np.deg2rad(LIGHT_ELEVATION_DEG)
    light = np.array([np.sin(azimuth) * np.cos(elevation), np.cos(azimuth) * np.cos(elevation), np.sin(elevation)])
    normal = np.stack([-dz_dx, -dz_dy, np.ones_like(height_m)])
    normal /= np.linalg.norm(normal, axis=0)
    return np.clip(np.tensordot(light, normal, axes=1), 0.0, 1.0)


def build(source: Path = SOURCE, out: Path = OUT) -> dict:
    with rasterio.open(source) as dataset:
        window = from_bounds(-HALF_WIDTH_M, -HALF_WIDTH_M, HALF_WIDTH_M, HALF_WIDTH_M, dataset.transform)
        height = dataset.read(1, window=window, out_shape=(PIXELS, PIXELS), resampling=Resampling.average)
    pixel_m = 2.0 * HALF_WIDTH_M / PIXELS
    shade = shaded_relief(height.astype(np.float64), pixel_m)
    # Light grey tones, so markers and labels on top stay readable.
    tone = 95 + 145 * shade
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(tone.astype(np.uint8), mode="L").save(out, optimize=True)
    meta = {
        "source": source.name,
        "extent_km": [-HALF_WIDTH_M / 1000, HALF_WIDTH_M / 1000, -HALF_WIDTH_M / 1000, HALF_WIDTH_M / 1000],
        "pixel_m": pixel_m,
        "projection": "south polar stereographic, as the LOLA models; +y towards 0 E, +x towards 90 E",
        "light": {"azimuth_deg": LIGHT_AZIMUTH_DEG, "elevation_deg": LIGHT_ELEVATION_DEG},
        "vertical_exaggeration": VERTICAL_EXAGGERATION,
        "note": "backdrop only; no number in the app is read from this image",
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


if __name__ == "__main__":
    print(build())
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1024:.0f} KB")

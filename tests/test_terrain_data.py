"""Sanity checks of the downloaded LOLA terrain files (data/raw/lola, not committed).

These tests verify the *data*, not the solution code: projection, pixel size, nodata and
height range must match what NASA PGDA documents (see docs/SOURCES.md). Each test is
skipped when its file has not been downloaded.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.windows import Window

LOLA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "lola"
MOON_RADIUS_M = 1_737_400.0

# File name -> pixel size in metres.
TERRAIN_FILES = {
    "LDEM_80S_40MPP_ADJ.TIF": 40.0,
    "Site01_final_adj_5mpp_surf.tif": 5.0,
    "Site23_final_adj_5mpp_surf.tif": 5.0,
    "DM2_final_adj_5mpp_surf.tif": 5.0,
    "Site04_final_adj_5mpp_surf.tif": 5.0,
    "Site07_final_adj_5mpp_surf.tif": 5.0,
    "Site11_final_adj_5mpp_surf.tif": 5.0,
    "Site06_final_adj_5mpp_surf.tif": 5.0,
    "Site20v2_final_adj_5mpp_surf.tif": 5.0,
    "Haworth_final_adj_5mpp_surf.tif": 5.0,
}

# Loose sanity bound only (catches wrong units such as km, or a raw radius instead of a
# height above the 1737.4 km sphere). The 40 m file documents its own range as
# -7296.5 .. +7026.8 m in its `z#actual_range` tag.
PLAUSIBLE_HEIGHT_RANGE_M = (-12_000.0, 12_000.0)


def _open(name: str) -> rasterio.DatasetReader:
    path = LOLA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} is not downloaded (see docs/SOURCES.md)")
    return rasterio.open(path)


@pytest.mark.parametrize(("name", "pixel_m"), TERRAIN_FILES.items())
def test_projection_is_south_polar_stereographic_on_lunar_sphere(name: str, pixel_m: float) -> None:
    with _open(name) as ds:
        crs = ds.crs.to_dict()
        assert crs["proj"] == "stere"
        assert crs["lat_0"] == -90
        assert crs["lon_0"] == 0
        assert crs.get("x_0", 0) == 0 and crs.get("y_0", 0) == 0
        # Sphere of radius 1737.4 km: either R=... or a=b=...
        radius = crs.get("R", crs.get("a"))
        assert radius == MOON_RADIUS_M
        assert crs.get("b", radius) == MOON_RADIUS_M
        assert ds.res == (pixel_m, pixel_m)
        assert ds.count == 1
        assert ds.dtypes[0] == "float32"


@pytest.mark.parametrize(("name", "pixel_m"), TERRAIN_FILES.items())
def test_heights_are_plausible(name: str, pixel_m: float) -> None:
    with _open(name) as ds:
        # Coarsest overview (or a decimated read) is enough for a range check.
        factor = max(1, max(ds.width, ds.height) // 1024)
        data = ds.read(1, out_shape=(ds.height // factor, ds.width // factor), masked=True)
        valid = np.ma.masked_invalid(data).compressed()
        assert valid.size > 0.5 * data.size, "more than half of the raster is nodata"
        low, high = PLAUSIBLE_HEIGHT_RANGE_M
        assert low < valid.min() < valid.max() < high


def test_south_pole_height_is_readable() -> None:
    with _open("LDEM_80S_40MPP_ADJ.TIF") as ds:
        # The grid is centred on the pole: (x, y) = (0, 0) is a corner shared by four pixels.
        assert ds.bounds.left == -ds.bounds.right
        assert ds.bounds.bottom == -ds.bounds.top
        row, col = ds.index(0.0, 0.0)
        window = ds.read(1, window=Window(col - 1, row - 1, 2, 2))
        assert np.isfinite(window).all()
        low, high = PLAUSIBLE_HEIGHT_RANGE_M
        assert low < float(window.mean()) < high


@pytest.mark.parametrize("name", [n for n in TERRAIN_FILES if n != "LDEM_80S_40MPP_ADJ.TIF"])
def test_site_dem_agrees_with_regional_dem(name: str) -> None:
    """The 5 m site model and the 40 m regional model describe the same surface."""
    with _open(name) as site, _open("LDEM_80S_40MPP_ADJ.TIF") as regional:
        x = 0.5 * (site.bounds.left + site.bounds.right)
        y = 0.5 * (site.bounds.bottom + site.bounds.top)
        half = 400.0  # metres; compare mean height of an 800 m square at the site centre
        heights = []
        for ds in (site, regional):
            window = rasterio.windows.from_bounds(x - half, y - half, x + half, y + half, ds.transform)
            block = ds.read(1, window=window.round_offsets().round_lengths(), masked=True)
            heights.append(float(np.ma.masked_invalid(block).mean()))
        assert abs(heights[0] - heights[1]) < 20.0, heights

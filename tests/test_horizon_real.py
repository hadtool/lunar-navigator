"""Checks of the cached horizons (data/processed/horizons) against real LOLA terrain.

The landmark test is independent of the ray-marching code: it takes the highest pixel of
a 5 m site raster and computes its direction from another site with plain 3-D vectors.
Tests are skipped when the cached horizons or the rasters are missing.
"""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio

from lunarnav.ephemeris import MOON_RADIUS_M, local_axes, site_vector_m
from lunarnav.horizon import HorizonProfile, cache_path

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
LOLA_DIR = ROOT / "data" / "raw" / "lola"
MAST_HEIGHTS_M = (0.0, 2.0, 5.0, 10.0, 20.0)
POLAR_SITES = [
    site for site in json.loads((ROOT / "data" / "sites.json").read_text(encoding="utf-8"))["sites"]
    if site["role"] != "validation_only"
]


def load_profile(site_id: str, mast_height_m: float) -> HorizonProfile:
    path = cache_path(HORIZON_DIR, site_id, mast_height_m)
    if not path.is_file():
        pytest.skip(f"{path.name} is not built (pipeline/build_horizons.py)")
    return HorizonProfile.load(path)


@pytest.mark.parametrize("site", POLAR_SITES, ids=lambda site: site["id"])
def test_cached_profiles_are_complete_and_ordered_by_mast_height(site: dict) -> None:
    profiles = [load_profile(site["id"], height) for height in MAST_HEIGHTS_M]
    for profile in profiles:
        assert profile.azimuth_rad.size == 720
        assert np.isfinite(profile.elevation_rad).all()
        assert profile.lat_rad == pytest.approx(np.deg2rad(site["lat_deg"]))
        assert profile.lon_east_rad == pytest.approx(np.deg2rad(site["lon_east_deg"]))
        # Horizon points lie between the first sample and the end of the rays.
        assert (profile.distance_m > 0).all() and (profile.distance_m <= profile.max_range_m).all()
    for lower, higher in zip(profiles, profiles[1:]):
        # Rounding in the JSON cache is 1e-5 deg.
        assert (higher.elevation_rad <= lower.elevation_rad + np.deg2rad(2e-5)).all()
        assert higher.ground_height_m == lower.ground_height_m


def summit_of(raster_name: str) -> tuple[float, float, float]:
    """Latitude, east longitude (rad) and height (m) of the highest pixel of a raster."""
    path = LOLA_DIR / raster_name
    if not path.is_file():
        pytest.skip(f"{raster_name} is not downloaded (docs/SOURCES.md)")
    with rasterio.open(path) as dataset:
        heights = dataset.read(1)
        row, col = np.unravel_index(np.nanargmax(heights), heights.shape)
        x, y = dataset.xy(row, col)
        height = float(heights[row, col])
    lat = -np.pi / 2 + 2.0 * np.arctan(np.hypot(x, y) / (2.0 * MOON_RADIUS_M))
    return float(lat), float(np.arctan2(x, y)), height


@pytest.mark.parametrize("mast_height_m", [2.0, 10.0, 20.0])
def test_malapert_summit_is_on_the_horizon_of_connecting_ridge(mast_height_m: float) -> None:
    """Malapert massif (5.2 km high, 135 km away) is a horizon landmark from Connecting Ridge."""
    profile = load_profile("connecting_ridge", mast_height_m)
    lat, lon, height = summit_of("Site23_final_adj_5mpp_surf.tif")
    observer = site_vector_m(profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + mast_height_m)
    east, north, up = local_axes(profile.lat_rad, profile.lon_east_rad)
    line_of_sight = site_vector_m(lat, lon, height) - observer
    distance = np.linalg.norm(line_of_sight)
    azimuth = np.arctan2(line_of_sight @ east, line_of_sight @ north)
    elevation = np.arcsin(line_of_sight @ up / distance)

    assert 130_000.0 < distance < 140_000.0
    horizon = float(profile.elevation_at(azimuth))
    assert horizon >= elevation - np.deg2rad(0.01)  # terrain there cannot be below its own summit
    # The summit is seen on the horizon: the profile agrees with the direct calculation
    # to 0.01 deg (the 40 m model used at this distance smooths the 5 m summit slightly).
    assert np.rad2deg(horizon) == pytest.approx(np.rad2deg(elevation), abs=0.01)
    nearest_bin = int(round(np.mod(azimuth, 2 * np.pi) / (2 * np.pi / 720))) % 720
    assert profile.distance_m[nearest_bin] == pytest.approx(distance, rel=0.02)

"""Compute terrain horizons for landing sites and cache them as JSON.

    uv run python pipeline/build_horizons.py                      # all polar sites, default masts
    uv run python pipeline/build_horizons.py --sites haworth --heights 0 2 5

Needs the LOLA rasters in data/raw/lola (docs/SOURCES.md). Output:
data/processed/horizons/<site>_h<height>.json, read by the app without any terrain file.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from lunarnav.horizon import (
    DEFAULT_MAX_RANGE_M,
    HorizonProfile,
    RasterTerrain,
    Terrain,
    cache_path,
    horizon_profiles,
)

ROOT = Path(__file__).resolve().parents[1]
SITES_FILE = ROOT / "data" / "sites.json"
LOLA_DIR = ROOT / "data" / "raw" / "lola"
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"

#: Regional model for the far horizon (80-90 S, 40 m/pixel).
REGIONAL_FILE = "LDEM_80S_40MPP_ADJ.TIF"
#: Optional third layer north of 80 S. Not needed for the current sites (docs/ASSUMPTIONS.md, A5).
FAR_FILE = "LDEM_60S_240MPP_ADJ.TIF"
DEFAULT_MAST_HEIGHTS_M = (0.0, 2.0, 5.0, 10.0, 20.0)


def load_sites(path: Path = SITES_FILE) -> list[dict]:
    """Sites that have polar terrain (everything except validation-only entries)."""
    document = json.loads(path.read_text(encoding="utf-8"))
    return [site for site in document["sites"] if site["role"] != "validation_only"]


def load_regional_terrains(lola_dir: Path = LOLA_DIR, with_far: bool = False) -> list[Terrain]:
    """Load the 40 m regional raster and, on request, the 240 m raster of 60-90 S."""
    names = (REGIONAL_FILE, FAR_FILE) if with_far else (REGIONAL_FILE,)
    terrains: list[Terrain] = []
    for name in names:
        path = lola_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"{path} is missing, see docs/SOURCES.md")
        terrains.append(RasterTerrain.from_file(path))
    return terrains


def site_terrains(site: dict, regional: list[Terrain], lola_dir: Path = LOLA_DIR) -> list[Terrain]:
    """Terrain chain of a site: its 5 m model (if downloaded) followed by the regional ones."""
    terrains: list[Terrain] = []
    url = site.get("pgda_5m_dem")
    if url:
        path = lola_dir / url.rsplit("/", 1)[-1]
        if path.is_file():
            terrains.append(RasterTerrain.from_file(path))
    return terrains + list(regional)


def build_site(
    site: dict,
    regional: list[Terrain],
    mast_heights_m: tuple[float, ...] = DEFAULT_MAST_HEIGHTS_M,
    max_range_m: float = DEFAULT_MAX_RANGE_M,
    out_dir: Path = HORIZON_DIR,
    lola_dir: Path = LOLA_DIR,
) -> list[HorizonProfile]:
    terrains = site_terrains(site, regional, lola_dir)
    profiles = horizon_profiles(
        np.deg2rad(site["lat_deg"]),
        np.deg2rad(site["lon_east_deg"]),
        mast_heights_m,
        terrains,
        max_range_m=max_range_m,
    )
    for profile in profiles:
        profile.save(cache_path(out_dir, site["id"], profile.mast_height_m))
    return profiles


def near_coverage_edge(profile: HorizonProfile, margin: float = 0.95) -> int:
    """Number of azimuth bins whose horizon point lies within 5 % of the end of terrain data.

    Such a horizon may be cut short by the edge of the terrain model (docs/ASSUMPTIONS.md, A5).
    """
    truncated = profile.covered_range_m < profile.max_range_m
    return int(np.count_nonzero(truncated & (profile.distance_m >= margin * profile.covered_range_m)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sites", nargs="+", help="site ids (default: all polar sites)")
    parser.add_argument("--heights", nargs="+", type=float, default=list(DEFAULT_MAST_HEIGHTS_M))
    parser.add_argument("--max-range-km", type=float, default=DEFAULT_MAX_RANGE_M / 1000.0)
    parser.add_argument("--out", type=Path, default=HORIZON_DIR)
    parser.add_argument("--with-240m", action="store_true",
                        help="add the 240 m model of 60-90 S beyond the 40 m model")
    args = parser.parse_args()

    sites = load_sites()
    if args.sites:
        known = {site["id"] for site in sites}
        unknown = set(args.sites) - known
        if unknown:
            parser.error(f"unknown site ids: {sorted(unknown)}; known: {sorted(known)}")
        sites = [site for site in sites if site["id"] in args.sites]

    started = time.perf_counter()
    regional = load_regional_terrains(with_far=args.with_240m)
    print(f"regional terrain loaded in {time.perf_counter() - started:.1f} s: "
          f"{', '.join(terrain.name for terrain in regional)}")
    for site in sites:
        site_started = time.perf_counter()
        profiles = build_site(site, regional, tuple(args.heights), args.max_range_km * 1000.0, args.out)
        summary = ", ".join(
            f"h={profile.mast_height_m:g} m: mean {np.rad2deg(profile.elevation_rad.mean()):+.2f} deg"
            for profile in profiles
        )
        print(f"{site['id']}: {time.perf_counter() - site_started:.1f} s ({profiles[0].terrain_names[0]}) {summary}")
        for profile in profiles:
            edge_bins = near_coverage_edge(profile)
            if edge_bins:
                print(f"  WARNING {site['id']} h={profile.mast_height_m:g} m: horizon point within 5 % of the "
                      f"end of terrain data in {edge_bins} azimuth bins; consider --with-240m")
    print(f"total {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()

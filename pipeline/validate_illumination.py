"""Compare our illumination and Earth-visibility statistics with the published LOLA maps.

    uv run python pipeline/validate_illumination.py

Reference: the average-illumination and Earth-visibility maps of the LOLA team
(AVGVISIB_*_201608, method of Mazarico et al. 2011; PGDA product 69, docs/SOURCES.md).
Each map value is the fraction of hourly time steps over 18.6 years in which any part of
the solar disc (or of the Earth's disc) was visible from the surface, computed on a 60 m
or 120 m terrain model. The script reads the values of the 60 m maps (85-90 S) at our sites,
computes the same statistic with our ephemeris and horizons over 18.6 years with an hourly
step, and writes data/processed/validation/illumination_vs_lola.json.

Needs the two map files in data/raw/illumination (docs/SOURCES.md), the SPICE kernels and
the LOLA rasters (the horizon from the 40 m model alone is
computed here because it is the closest analogue of the 60 m map).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_horizons  # noqa: E402

from lunarnav.ephemeris import MOON_RADIUS_M, CentreEphemeris, centre_ephemeris  # noqa: E402
from lunarnav.horizon import HorizonProfile, Terrain, cache_path, horizon_profiles, lat_lon_to_xy  # noqa: E402
from lunarnav.visibility import site_visibility, window_metrics  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_FILE = ROOT / "data" / "processed" / "validation" / "illumination_vs_lola.json"
MAP_DIR = ROOT / "data" / "raw" / "illumination"
#: 60 m maps of 85-90 S (a square of +-151.74 km around the pole); all four sites are inside.
SUN_MAP = "AVGVISIB_85S_060M_201608"
EARTH_MAP = "AVGVISIB_85S_060M_201608_EARTH"
SITES = ("connecting_ridge", "de_gerlache_rim", "malapert_massif", "haworth")
START = np.datetime64("2027-01-01T00")
#: One lunar nutation cycle, as in the published maps.
YEARS = 18.6
MAST_HEIGHTS_M = (0.0, 2.0, 10.0)
#: Period shown in the app, used to measure how much the choice of period matters.
APP_PERIOD = ("2027-01-01", "2030-01-01")


def read_map(name: str, x_m: float, y_m: float) -> dict[str, Any]:
    """Map value at the pixel containing the point, and the range over the 3 x 3 pixels around it."""
    path = MAP_DIR / f"{name}.TIF"
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing, see docs/SOURCES.md")
    with rasterio.open(path) as dataset:
        row, col = dataset.index(x_m, y_m)
        if not (1 <= row < dataset.height - 1 and 1 <= col < dataset.width - 1):
            raise ValueError("site outside the map")
        block = dataset.read(1, window=Window(col - 1, row - 1, 3, 3)).astype(np.float64)
        # int16 digital numbers; value = DN * 0.00004 (PDS label and GeoTIFF scale tag).
        block = block * dataset.scales[0] + dataset.offsets[0]
        pixel = float(dataset.transform.a)
        centres = [dataset.xy(row + d_row, col + d_col) for d_row in (-1, 0, 1) for d_col in (-1, 0, 1)]
    if not 0.0 <= block.min() <= block.max() <= 1.0:
        raise ValueError(f"{name}: unexpected value range {block.min()}..{block.max()}, check the scaling")
    return {
        "pixel_m": pixel,
        "value_pct": round(100.0 * float(block[1, 1]), 2),
        "min_3x3_pct": round(100.0 * float(block.min()), 2),
        "max_3x3_pct": round(100.0 * float(block.max()), 2),
        # Row by row from the top-left pixel, with the X/Y of each pixel centre (m).
        "values_3x3_pct": [round(100.0 * float(value), 2) for value in block.ravel()],
        "centres_3x3_m": [[float(cx), float(cy)] for cx, cy in centres],
    }


def xy_to_lat_lon(x_m: float, y_m: float) -> tuple[float, float]:
    """Inverse of the south polar stereographic projection of the rasters (radians)."""
    lat = -np.pi / 2 + 2.0 * np.arctan(np.hypot(x_m, y_m) / (2.0 * MOON_RADIUS_M))
    return float(lat), float(np.arctan2(x_m, y_m))


def patch_comparison(
    published_sun: dict[str, Any], published_earth: dict[str, Any], regional: list[Terrain], centre: CentreEphemeris
) -> dict[str, Any]:
    """Our statistic at the centres of the 3 x 3 map pixels around a site (40 m model, surface)."""
    ours_sun, ours_earth = [], []
    for x, y in published_sun["centres_3x3_m"]:
        lat, lon = xy_to_lat_lon(x, y)
        metrics = window_metrics(site_visibility(horizon_profiles(lat, lon, [0.0], regional)[0], centre))
        ours_sun.append(round(metrics.sunlit_pct, 2))
        ours_earth.append(round(metrics.earth_any_part_pct, 2))
    sun_diff = np.array(ours_sun) - np.array(published_sun["values_3x3_pct"])
    earth_diff = np.array(ours_earth) - np.array(published_earth["values_3x3_pct"])
    return {
        "ours_sun_3x3_pct": ours_sun,
        "ours_earth_3x3_pct": ours_earth,
        "sun_mean_difference_pct": round(float(sun_diff.mean()), 2),
        "sun_rms_difference_pct": round(float(np.sqrt((sun_diff ** 2).mean())), 2),
        "earth_mean_difference_pct": round(float(earth_diff.mean()), 2),
        "earth_rms_difference_pct": round(float(np.sqrt((earth_diff ** 2).mean())), 2),
    }


def main() -> None:
    hours = int(round(YEARS * 365.25 * 24))
    times = START + np.arange(hours) * np.timedelta64(1, "h")
    print(f"ephemeris for {hours} hourly steps, {times[0]} .. {times[-1]}")
    centre = centre_ephemeris(times)
    regional = build_horizons.load_regional_terrains()
    sites = {site["id"]: site for site in build_horizons.load_sites()}

    results = []
    for site_id in SITES:
        site = sites[site_id]
        lat, lon = np.deg2rad(site["lat_deg"]), np.deg2rad(site["lon_east_deg"])
        x, y = lat_lon_to_xy(lat, lon)
        published = {"sun": read_map(SUN_MAP, x, y), "earth": read_map(EARTH_MAP, x, y)}
        ours = []
        variants = [("5 m near field + 40 m (as in the app)", height, None) for height in MAST_HEIGHTS_M]
        variants.append(("40 m model only", 0.0, regional))
        for label, height, terrains in variants:
            if terrains is None:
                profile = HorizonProfile.load(cache_path(build_horizons.HORIZON_DIR, site_id, height))
            else:
                profile = horizon_profiles(lat, lon, [height], terrains)[0]
            metrics = window_metrics(site_visibility(profile, centre))
            ours.append({
                "terrain": label,
                "observer_height_m": height,
                "sunlit_any_part_pct": round(metrics.sunlit_pct, 2),
                "mean_sun_disc_fraction_pct": round(metrics.mean_sun_fraction_pct, 2),
                "earth_any_part_pct": round(metrics.earth_any_part_pct, 2),
                "earth_centre_pct": round(metrics.earth_pct, 2),
            })
        patch = patch_comparison(published["sun"], published["earth"], regional, centre)
        # Sensitivity of the 40 m / 0 m value to two of our own choices.
        base = window_metrics(site_visibility(horizon_profiles(lat, lon, [0.0], regional)[0], centre))
        three_years = window_metrics(
            site_visibility(horizon_profiles(lat, lon, [0.0], regional)[0], centre), APP_PERIOD[0], APP_PERIOD[1]
        )
        one_ray = window_metrics(
            site_visibility(horizon_profiles(lat, lon, [0.0], regional, subrays=1)[0], centre)
        )
        sensitivity = {
            "period_2027_2029_minus_18_6_years_sun_pct": round(three_years.sunlit_pct - base.sunlit_pct, 2),
            "period_2027_2029_minus_18_6_years_earth_pct": round(
                three_years.earth_any_part_pct - base.earth_any_part_pct, 2),
            "one_ray_per_bin_minus_four_sun_pct": round(one_ray.sunlit_pct - base.sunlit_pct, 2),
            "one_ray_per_bin_minus_four_earth_pct": round(one_ray.earth_any_part_pct - base.earth_any_part_pct, 2),
        }
        results.append({"site": site_id, "lat_deg": site["lat_deg"], "lon_east_deg": site["lon_east_deg"],
                        "published": published, "ours": ours, "patch_3x3_40m_surface": patch,
                        "sensitivity_40m_surface": sensitivity})
        print(f"\n{site_id}: published: Sun {published['sun']['value_pct']} % "
              f"(3x3: {published['sun']['min_3x3_pct']}-{published['sun']['max_3x3_pct']}), "
              f"Earth {published['earth']['value_pct']} % "
              f"(3x3: {published['earth']['min_3x3_pct']}-{published['earth']['max_3x3_pct']})")
        for row in ours:
            print(f"  ours, {row['terrain']}, {row['observer_height_m']:g} m: Sun {row['sunlit_any_part_pct']} % "
                  f"(mean disc fraction {row['mean_sun_disc_fraction_pct']} %), Earth any part "
                  f"{row['earth_any_part_pct']} %, Earth centre {row['earth_centre_pct']} %")

        print(f"  3 x 3 map pixels, ours (40 m model, 0 m) minus published: Sun mean "
              f"{patch['sun_mean_difference_pct']:+.2f}, rms {patch['sun_rms_difference_pct']:.2f}; Earth mean "
              f"{patch['earth_mean_difference_pct']:+.2f}, rms {patch['earth_rms_difference_pct']:.2f} (percentage points)")
        print(f"  sensitivity (percentage points): {sensitivity}")
        print(f"    published Sun {published['sun']['values_3x3_pct']}")
        print(f"    ours      Sun {patch['ours_sun_3x3_pct']}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "description": "Share of hourly time steps with any part of the disc visible; ours versus the LOLA maps",
        "our_period_utc": [str(times[0]), str(times[-1])],
        "our_step_hours": 1,
        "published_source": f"{SUN_MAP} and {EARTH_MAP} (LOLA team, PGDA product 69): 18.6 years, hourly, 60 m terrain",
        "sites": results,
    }, indent=1), encoding="utf-8")
    print(f"\nsaved {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Visual check of terrain horizons against LROC WAC imagery (task T06).

    uv run python pipeline/check_horizon_wac.py

For each site the highest peaks of the cached horizon panorama are found; for each peak the
terrain point that defines it (azimuth and distance from the horizon profile) is placed on the
LROC WAC south-polar summer mosaic, the imagery LROC QuickMap shows (independent of the LOLA
heights the horizon is computed from). If the azimuth convention or the distances were wrong,
the rays would end on plains or crater floors instead of on the crests of the massifs and rims
that face the site. Writes docs/figures/horizon_check_wac_<site>_h<height>.png.

Imagery: data/raw/lroc_wac/WAC_ROI_SOUTH_SUMMER_064P.TIF (docs/SOURCES.md), 473.8 m/pixel, the
same south polar stereographic projection as the LOLA terrain.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.windows import from_bounds

from lunarnav.ephemeris import MOON_RADIUS_M
from lunarnav.horizon import lat_lon_to_xy
from lunarnav.store import load_horizon, load_sites

ROOT = Path(__file__).resolve().parents[1]
WAC = ROOT / "data" / "raw" / "lroc_wac" / "WAC_ROI_SOUTH_SUMMER_064P.TIF"
FIGURES = ROOT / "docs" / "figures"
CASES = (("connecting_ridge", 20.0), ("malapert_massif", 20.0), ("haworth", 2.0))
COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6")


def destination(lat: float, lon: float, azimuth: float, distance_m: float) -> tuple[float, float]:
    """Point at a great-circle distance and azimuth (clockwise from north) from (lat, lon), radians."""
    delta = distance_m / MOON_RADIUS_M
    lat2 = np.arcsin(np.sin(lat) * np.cos(delta) + np.cos(lat) * np.sin(delta) * np.cos(azimuth))
    lon2 = lon + np.arctan2(np.sin(azimuth) * np.sin(delta) * np.cos(lat), np.cos(delta) - np.sin(lat) * np.sin(lat2))
    return float(lat2), float(lon2)


def peaks(elevation: np.ndarray, count: int = 6, half_width: int = 10, separation_deg: float = 25.0) -> list[int]:
    """Indices of the highest local maxima of a circular series, at least ``separation_deg`` apart."""
    size = elevation.size
    window = np.stack([np.roll(elevation, shift) for shift in range(-half_width, half_width + 1)])
    local = np.flatnonzero(elevation >= window.max(axis=0))
    chosen: list[int] = []
    for index in local[np.argsort(elevation[local])[::-1]]:
        if all(min(abs(index - other), size - abs(index - other)) * 360.0 / size >= separation_deg for other in chosen):
            chosen.append(int(index))
        if len(chosen) == count:
            break
    return sorted(chosen)


def check(site: dict, height_m: float) -> Path:
    profile = load_horizon(site["id"], height_m)
    azimuth_deg = np.rad2deg(profile.azimuth_rad)
    elevation_deg = np.rad2deg(profile.elevation_rad)
    chosen = peaks(elevation_deg)
    site_x, site_y = lat_lon_to_xy(profile.lat_rad, profile.lon_east_rad)
    points = []
    for index in chosen:
        lat, lon = destination(profile.lat_rad, profile.lon_east_rad, profile.azimuth_rad[index],
                               profile.distance_m[index])
        points.append(lat_lon_to_xy(lat, lon))
    reach = max(max(np.hypot(x - site_x, y - site_y) for x, y in points), 20_000.0) * 1.15

    with rasterio.open(WAC) as dataset:
        window = from_bounds(site_x - reach, site_y - reach, site_x + reach, site_y + reach, dataset.transform)
        image = dataset.read(1, window=window, boundless=True, fill_value=0)
    extent_km = [(site_x - reach) / 1000, (site_x + reach) / 1000, (site_y - reach) / 1000, (site_y + reach) / 1000]

    fig, (map_axis, pano_axis) = plt.subplots(1, 2, figsize=(15, 6.6), dpi=110,
                                              gridspec_kw={"width_ratios": [1.0, 1.35]})
    map_axis.imshow(image, cmap="gray", extent=extent_km, origin="upper", vmin=0,
                    vmax=float(np.percentile(image[image > 0], 99.5)) if np.any(image > 0) else 255)
    for number, ((x, y), index) in enumerate(zip(points, chosen), start=1):
        color = COLORS[(number - 1) % len(COLORS)]
        map_axis.plot([site_x / 1000, x / 1000], [site_y / 1000, y / 1000], color=color, linewidth=1.4)
        map_axis.plot(x / 1000, y / 1000, "o", color=color, markersize=7, markeredgecolor="white")
        map_axis.annotate(str(number), (x / 1000, y / 1000), xytext=(5, 5), textcoords="offset points",
                          color="white", fontsize=11, fontweight="bold")
        pano_axis.plot(azimuth_deg[index], elevation_deg[index], "o", color=color, markersize=8)
        pano_axis.annotate(f"{number}: {azimuth_deg[index]:.1f}°, {profile.distance_m[index] / 1000:.0f} km",
                           (azimuth_deg[index], elevation_deg[index]), xytext=(0, 8), textcoords="offset points",
                           ha="center", fontsize=9, color=color)
    map_axis.plot(site_x / 1000, site_y / 1000, "*", color="#ffffff", markersize=14, markeredgecolor="#0b0b0b")
    map_axis.set(xlabel="x, km (towards 90° E)", ylabel="y, km (towards 0° E)",
                 title="LROC WAC south summer mosaic (as in QuickMap)")
    pano_axis.fill_between(azimuth_deg, elevation_deg, elevation_deg.min() - 0.5, color="#c3c2b7")
    pano_axis.plot(azimuth_deg, elevation_deg, color="#52514e", linewidth=1)
    pano_axis.set(xlim=(0, 360), xticks=range(0, 361, 45), xlabel="Azimuth, deg (clockwise from north)",
                  ylabel="Horizon elevation, deg", title=f"Our terrain horizon, observer {height_m:g} m above the surface")
    pano_axis.grid(True, linewidth=0.3)
    fig.suptitle(f"{site['name']}: the terrain points that define the main horizon peaks, placed on independent imagery",
                 fontsize=12)
    fig.tight_layout()
    path = FIGURES / f"horizon_check_wac_{site['id']}_h{height_m:g}.png"
    fig.savefig(path)
    plt.close(fig)
    others = [other for other in load_sites() if other["id"] != site["id"]]
    for number, (index, (x, y)) in enumerate(zip(chosen, points), start=1):
        nearest = min(others, key=lambda other: np.hypot(*(np.subtract(
            lat_lon_to_xy(np.deg2rad(other["lat_deg"]), np.deg2rad(other["lon_east_deg"])), (x, y)))))
        gap_km = np.hypot(*np.subtract(lat_lon_to_xy(np.deg2rad(nearest["lat_deg"]), np.deg2rad(nearest["lon_east_deg"])),
                                        (x, y))) / 1000
        print(f"  {number}: azimuth {azimuth_deg[index]:6.1f} deg, horizon {elevation_deg[index]:+.2f} deg, "
              f"defined by terrain {profile.distance_m[index] / 1000:6.1f} km away; nearest listed site: "
              f"{nearest['name']} ({gap_km:.1f} km)")
    return path


def main() -> None:
    sites = {site["id"]: site for site in load_sites()}
    for site_id, height_m in CASES:
        print(sites[site_id]["name"], f"{height_m:g} m")
        print("  ->", check(sites[site_id], height_m).relative_to(ROOT))


if __name__ == "__main__":
    main()

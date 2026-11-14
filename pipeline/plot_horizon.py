"""Draw the horizon panorama of a site with the Sun and Earth tracks of one year.

    uv run python pipeline/plot_horizon.py connecting_ridge --year 2027

Reads the cached horizons (pipeline/build_horizons.py) and writes
docs/figures/horizon_<site>.png. Used to check the panorama by eye against LROC Quickmap
or Moon Trek; it is not part of the app.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from lunarnav.ephemeris import centre_ephemeris, sky_track
from lunarnav.horizon import HorizonProfile, cache_path

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
FIGURE_DIR = ROOT / "docs" / "figures"
MAST_HEIGHTS_M = (2.0, 10.0)


def plot_site(site: dict, year: int, out_dir: Path = FIGURE_DIR) -> Path:
    profiles = [HorizonProfile.load(cache_path(HORIZON_DIR, site["id"], h)) for h in MAST_HEIGHTS_M]
    base = profiles[0]
    times = np.arange(np.datetime64(f"{year}-01-01T00"), np.datetime64(f"{year + 1}-01-01T00"), np.timedelta64(2, "h"))
    track = sky_track(base.lat_rad, base.lon_east_rad, base.ground_height_m + base.mast_height_m, centre_ephemeris(times))

    figure, axis = plt.subplots(figsize=(14, 5), dpi=110)
    azimuth_deg = np.rad2deg(base.azimuth_rad)
    axis.fill_between(azimuth_deg, np.rad2deg(base.elevation_rad), -90, color="0.45", step="mid",
                      label=f"terrain, observer {base.mast_height_m:g} m above surface")
    axis.plot(azimuth_deg, np.rad2deg(profiles[1].elevation_rad), color="black", linewidth=0.8,
              label=f"horizon for {profiles[1].mast_height_m:g} m")
    axis.scatter(np.rad2deg(track.sun.azimuth_rad), np.rad2deg(track.sun.elevation_rad), s=1.5,
                 color="tab:orange", label=f"Sun centre, {year}, every 2 h")
    axis.scatter(np.rad2deg(track.earth.azimuth_rad), np.rad2deg(track.earth.elevation_rad), s=1.5,
                 color="tab:blue", label=f"Earth centre, {year}, every 2 h")
    low = min(-4.0, float(np.rad2deg(profiles[1].elevation_rad.min())) - 0.5)
    high = max(8.0, float(np.rad2deg(base.elevation_rad.max())) + 1.0, float(np.rad2deg(track.earth.elevation_rad.max())) + 0.5)
    axis.set(xlim=(0, 360), ylim=(low, high), xlabel="Azimuth, degrees clockwise from north",
             ylabel="Elevation, degrees",
             title=f"{site['name']} ({site['lat_deg']:.4f}, {site['lon_east_deg']:.4f} E): terrain horizon from LOLA, Sun and Earth")
    axis.set_xticks(np.arange(0, 361, 30))
    axis.grid(True, linewidth=0.3)
    axis.legend(loc="upper right", fontsize=8, markerscale=4)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"horizon_{site['id']}.png"
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sites", nargs="+")
    parser.add_argument("--year", type=int, default=2027)
    args = parser.parse_args()
    sites = {site["id"]: site for site in json.loads((ROOT / "data" / "sites.json").read_text(encoding="utf-8"))["sites"]}
    unknown = [site_id for site_id in args.sites if site_id not in sites]
    if unknown:
        parser.error(f"unknown site ids: {unknown}; known: {sorted(sites)}")
    for site_id in args.sites:
        print(plot_site(sites[site_id], args.year))


if __name__ == "__main__":
    main()

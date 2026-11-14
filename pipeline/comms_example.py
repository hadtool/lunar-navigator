"""Earth contact windows of a site as a table and on a timeline (worked example).

    uv run python pipeline/comms_example.py
    uv run python pipeline/comms_example.py --site malapert_massif --start 2027-01-01 --days 120 --mast 2

Uses the cached horizon, the ephemeris and the communication rule of
docs/ENGINEERING_INPUTS.md (placeholder: centre of the Earth's disc above the terrain
horizon, margin 0 deg). Writes the window table to
data/processed/validation/comms_windows_<site>_h<mast>.csv and the timeline to
docs/figures/comms_timeline_<site>_h<mast>.png.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from lunarnav.comms import (
    comm_summary,
    contact_windows,
    default_comm_settings,
    intervals_table,
    link_mask,
    link_parameters_from_inputs,
)
from lunarnav.ephemeris import centre_ephemeris, sky_track
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.visibility import visibility

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
FIGURE_DIR = ROOT / "docs" / "figures"
OUT_DIR = ROOT / "data" / "processed" / "validation"


def bars(axis: plt.Axes, mask: np.ndarray, times: np.ndarray, row: float, color: str) -> None:
    """Draw the True runs of a mask as horizontal bars."""
    numbers = mdates.date2num(times.astype("datetime64[s]").astype(object))
    step = numbers[1] - numbers[0]
    padded = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    starts, stops = np.flatnonzero(padded == 1), np.flatnonzero(padded == -1)
    axis.broken_barh([(numbers[a], (b - a) * step) for a, b in zip(starts, stops)], (row - 0.35, 0.7), color=color)


def run(site_id: str, start: str, days: int, mast_height_m: float) -> dict:
    times = np.datetime64(start, "h") + np.arange(days * 24) * np.timedelta64(1, "h")
    profile = HorizonProfile.load(cache_path(HORIZON_DIR, site_id, mast_height_m))
    track = sky_track(
        profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m,
        centre_ephemeris(times),
    )
    vis = visibility(track, profile)
    settings, placeholders = default_comm_settings()
    mask = link_mask(vis, track.earth.angular_radius_rad, settings)
    windows = contact_windows(mask, times)
    table = intervals_table(windows)
    summary = asdict(comm_summary(mask, times, settings))

    stem = f"{site_id}_h{mast_height_m:g}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_DIR / f"comms_windows_{stem}.csv", index=False, date_format="%Y-%m-%dT%H:%M")

    figure, (upper, lower) = plt.subplots(
        2, 1, figsize=(13, 5.5), dpi=110, sharex=True, gridspec_kw={"height_ratios": [2, 1.2]}
    )
    plot_times = times.astype("datetime64[s]").astype(object)
    upper.plot(plot_times, np.rad2deg(vis.earth_clearance_rad), color="tab:blue", linewidth=1.0,
               label="Earth centre above the terrain horizon")
    upper.plot(plot_times, np.rad2deg(vis.sun_clearance_rad), color="tab:orange", linewidth=1.0,
               label="Sun centre above the terrain horizon")
    upper.axhline(np.rad2deg(settings.margin_rad), color="tab:red", linestyle="--", linewidth=0.8,
                  label=f"link margin {np.rad2deg(settings.margin_rad):g} deg")
    upper.set(ylabel="Clearance, degrees")
    upper.legend(loc="upper right", fontsize=8, ncols=3)
    upper.grid(True, linewidth=0.3)
    sunlit = vis.sun_fraction > 0.0
    bars(lower, sunlit, times, 2.0, "tab:orange")
    bars(lower, mask, times, 1.0, "tab:blue")
    bars(lower, sunlit & mask, times, 0.0, "tab:green")
    lower.set_yticks([2.0, 1.0, 0.0], ["Sun (any part)", f"Earth ({settings.rule})", "Sun and Earth"])
    lower.set(ylim=(-0.6, 2.6), xlabel="UTC")
    lower.grid(True, axis="x", linewidth=0.3)
    marker = " (placeholder link rule)" if placeholders else ""
    figure.suptitle(
        f"{site_id}, observer {mast_height_m:g} m above the surface, {days} days from {start}: Earth in line of "
        f"sight {summary['visible_pct']:.1f} % of the time, longest gap {summary['longest_gap_h']:.0f} h{marker}",
        fontsize=10,
    )
    figure.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_DIR / f"comms_timeline_{stem}.png")
    plt.close(figure)

    summary.update(
        site=site_id, mast_height_m=mast_height_m, start_utc=start, days=days,
        placeholder_keys=list(placeholders),
        link_budget="configured" if link_parameters_from_inputs() else "not configured (engineer inputs empty)",
        earth_distance_km=[round(float(track.earth.distance_m.min()) / 1000.0), round(float(track.earth.distance_m.max()) / 1000.0)],
    )
    print(table.to_string(index=False, max_rows=12))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", default="connecting_ridge")
    parser.add_argument("--start", default="2027-01-01")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--mast", type=float, default=2.0, help="observer height in m (a cached one)")
    args = parser.parse_args()
    for key, value in run(args.site, args.start, args.days, args.mast).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

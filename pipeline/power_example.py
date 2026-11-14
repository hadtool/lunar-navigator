"""Worked example of the power model for the engineer's review: one site, one month.

    uv run python pipeline/power_example.py
    uv run python pipeline/power_example.py --site haworth --month 2027-06 --mast 5

Uses the cached horizon of the site, the ephemeris and the default power system
(docs/ENGINEERING_INPUTS.md; placeholders where it is empty). Prints the energy balance
and writes docs/figures/power_example_<site>_<month>_h<mast>.png and a JSON file with the
same numbers in data/processed/validation/.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from lunarnav.ephemeris import centre_ephemeris, sky_track
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.power import default_power_system, generation_from_track, required_capacity_wh, simulate
from lunarnav.visibility import visibility, window_metrics

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
FIGURE_DIR = ROOT / "docs" / "figures"
OUT_DIR = ROOT / "data" / "processed" / "validation"


def run(site_id: str, month: str, mast_height_m: float) -> dict:
    start = np.datetime64(f"{month}-01T00")
    stop = (start.astype("datetime64[M]") + np.timedelta64(1, "M")).astype("datetime64[h]")
    times = np.arange(start, stop, np.timedelta64(1, "h"))
    profile = HorizonProfile.load(cache_path(HORIZON_DIR, site_id, mast_height_m))
    track = sky_track(
        profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m,
        centre_ephemeris(times),
    )
    vis = visibility(track, profile)
    metrics = window_metrics(vis)
    system, placeholders = default_power_system()
    generation = generation_from_track(system, track.sun, vis.sun_fraction)
    result = simulate(system, times, generation, vis.sun_fraction)
    needed = required_capacity_wh(system, times, generation, vis.sun_fraction)

    summary = {
        "site": site_id,
        "mast_height_m": mast_height_m,
        "window_utc": [str(times[0]), str(result.times_utc[-1])],
        "step_hours": result.step_hours,
        "power_system": asdict(system),
        "placeholder_keys": list(placeholders),
        "hours_total": int(times.size),
        "hours_sunlit_any_part": int(np.count_nonzero(vis.sun_fraction > 0)),
        "mean_sun_disc_fraction_pct": round(metrics.mean_sun_fraction_pct, 2),
        "longest_night_h": metrics.longest_night.hours,
        "longest_night_start_utc": metrics.longest_night.start_utc,
        "longest_night_reaches_window_edge": metrics.longest_night.reaches_window_edge,
        "peak_generation_w": round(float(generation.max()), 1),
        "generated_wh": round(result.generated_wh, 1),
        "load_wh": round(result.load_wh, 1),
        "unused_generation_wh": round(result.unused_generation_wh, 1),
        "unserved_wh": round(result.unserved_wh, 1),
        "start_energy_wh": round(float(result.energy_wh[0]), 1),
        "end_energy_wh": round(float(result.energy_wh[-1]), 1),
        "min_energy_wh": round(result.min_energy_wh, 1),
        "min_soc_pct": round(100.0 * result.min_soc, 1),
        "min_energy_utc": result.min_energy_utc,
        "allowed_min_soc_pct": round(100.0 * system.battery_min_soc, 1),
        "survives": result.survives,
        "first_violation_utc": result.first_violation_utc,
        "required_capacity_wh": round(needed, 1),
        "required_battery_mass_kg": (
            round(needed / system.battery_specific_energy_wh_per_kg, 2)
            if system.battery_specific_energy_wh_per_kg else None
        ),
    }

    figure, axes = plt.subplots(3, 1, figsize=(12, 8), dpi=110, sharex=True)
    step_times = result.times_utc[:-1]
    axes[0].fill_between(step_times, 100.0 * vis.sun_fraction, step="post", color="tab:orange", alpha=0.6)
    axes[0].set(ylabel="Visible share of\nthe solar disc, %", ylim=(0, 105))
    axes[1].step(step_times, result.generation_w, where="post", color="tab:orange", label="generation")
    axes[1].step(step_times, result.load_w, where="post", color="tab:red", label="load")
    axes[1].set(ylabel="Power, W")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[2].plot(result.times_utc, 100.0 * result.soc, color="tab:blue", label="state of charge")
    axes[2].axhline(100.0 * system.battery_min_soc, color="tab:red", linestyle="--", linewidth=0.8,
                    label="allowed minimum")
    axes[2].set(ylabel="Battery state\nof charge, %", ylim=(0, 105), xlabel="UTC")
    axes[2].legend(loc="lower right", fontsize=8)
    verdict = "survives" if result.survives else "does not survive"
    marker = " (PLACEHOLDER power system)" if placeholders else ""
    figure.suptitle(
        f"{site_id}, {month}, panel and observer {mast_height_m:g} m above the surface: {verdict}{marker}\n"
        f"panel {system.panel_area_m2:g} m2 at {100 * system.panel_efficiency:g} %, battery "
        f"{system.battery_capacity_wh:g} Wh, load {system.load_day_w:g} W day / {system.load_night_w:g} W night",
        fontsize=10,
    )
    for axis in axes:
        axis.grid(True, linewidth=0.3)
    figure.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"power_example_{site_id}_{month}_h{mast_height_m:g}"
    figure.savefig(FIGURE_DIR / f"{stem}.png")
    plt.close(figure)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    summary["figure"] = str((FIGURE_DIR / f"{stem}.png").relative_to(ROOT))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", default="connecting_ridge")
    parser.add_argument("--month", default="2027-06", help="YYYY-MM")
    parser.add_argument("--mast", type=float, default=2.0, help="observer height in m (a cached one)")
    args = parser.parse_args()
    for key, value in run(args.site, args.month, args.mast).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

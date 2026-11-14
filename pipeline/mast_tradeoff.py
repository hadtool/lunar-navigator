"""Mast-height trade-off for a few sites: table and figure (T10).

    uv run python pipeline/mast_tradeoff.py
    uv run python pipeline/mast_tradeoff.py --sites connecting_ridge haworth --start 2027-01-01 --stop 2028-01-01

For every site and every mast height of docs/ENGINEERING_INPUTS.md (placeholder: 0, 2, 5,
10 and 20 m, panel and antenna both on the mast) the script recomputes the visibility of the
Sun and the Earth and the battery simulation over the window from the cached horizons.
Horizons that are not cached yet are first computed from the LOLA rasters
(pipeline/build_horizons.py). Power system and link rule come from the same file, with the
placeholders of docs/ASSUMPTIONS.md (A12, A14) for empty rows.

Writes data/processed/mast/mast_tradeoff_<start>_<stop>.csv (one row per site and height),
a JSON file with the inputs and the heights where the gain levels off, and the figure
docs/figures/mast_tradeoff_<start>_<stop>.png. Prints a Markdown table of the results.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import StrMethodFormatter
from matplotlib.transforms import offset_copy

from lunarnav.comms import default_comm_settings
from lunarnav.ephemeris import centre_ephemeris
from lunarnav.horizon import HorizonProfile, Terrain, cache_path
from lunarnav.mast import (
    LEVELLING_SHARE,
    MIN_MEANINGFUL_HEIGHT_M,
    default_mast_settings,
    levelling_off_heights,
    mast_tradeoff,
)
from lunarnav.power import default_power_system

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_horizons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
OUT_DIR = ROOT / "data" / "processed" / "mast"
FIGURE_DIR = ROOT / "docs" / "figures"
DEFAULT_SITES = ("connecting_ridge", "malapert_massif", "haworth")

# Chart tokens (light surface) and the first three categorical slots, checked with the
# dataviz palette validator: CVD and normal-vision separation pass for all pairs; the aqua
# slot is below 3:1 contrast, so every line carries a direct end label and a marker shape.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
MARKERS = ("o", "s", "^")

_regional_terrains: list[Terrain] | None = None


def site_profiles(site: dict, heights_m: tuple[float, ...]) -> tuple[list[HorizonProfile], list[float]]:
    """Cached horizons of a site for the heights; missing ones are computed from the LOLA rasters."""
    global _regional_terrains
    missing = [height for height in heights_m if not cache_path(HORIZON_DIR, site["id"], height).is_file()]
    if missing:
        if _regional_terrains is None:
            _regional_terrains = build_horizons.load_regional_terrains()
        build_horizons.build_site(site, _regional_terrains, tuple(missing), out_dir=HORIZON_DIR)
    profiles = [HorizonProfile.load(cache_path(HORIZON_DIR, site["id"], height)) for height in heights_m]
    return profiles, missing


def run(site_ids: list[str], start: str, stop: str) -> tuple[pd.DataFrame, dict]:
    settings, mast_placeholders = default_mast_settings()
    system, power_placeholders = default_power_system()
    comm, comm_placeholders = default_comm_settings()
    sites = {site["id"]: site for site in build_horizons.load_sites()}
    unknown = sorted(set(site_ids) - set(sites))
    if unknown:
        raise SystemExit(f"unknown site ids: {unknown}; known: {sorted(sites)}")

    if np.datetime64(stop, "D") <= np.datetime64(start, "D"):
        raise SystemExit(f"--stop ({stop}) must be after --start ({start})")
    times = np.arange(np.datetime64(start, "h"), np.datetime64(stop, "h"), np.timedelta64(1, "h"))
    started = time.perf_counter()
    centre = centre_ephemeris(times)
    timing = {"ephemeris_s": round(time.perf_counter() - started, 2)}

    tables, levelling, computed = [], {}, {}
    for site_id in site_ids:
        site = sites[site_id]
        profiles, missing = site_profiles(site, settings.heights_m)
        if missing:
            computed[site_id] = missing
        started = time.perf_counter()
        table = mast_tradeoff(profiles, centre, system, comm, carries=settings.carries)
        timing[f"{site_id}_s"] = round(time.perf_counter() - started, 2)
        levelling[site_id] = levelling_off_heights(table)
        table.insert(0, "site", site_id)
        table.insert(1, "site_name", site["name"])
        table.insert(2, "near_field_model", "5 m" if site.get("pgda_5m_dem") else "40 m")
        tables.append(table)

    meta = {
        "task": "T10 mast-height trade-off",
        "window_utc": [str(times[0]), str(times[-1] + np.timedelta64(1, "h"))],
        "step_hours": 1.0,
        "samples": int(times.size),
        "mast_heights_m": list(settings.heights_m),
        "mast_carries": settings.carries,
        "placeholder_keys": {
            "mast": list(mast_placeholders),
            "power": list(power_placeholders),
            "comm": list(comm_placeholders),
        },
        "power_system": asdict(system),
        "comm": {"rule": comm.rule, "margin_deg": float(np.rad2deg(comm.margin_rad))},
        "levelling_off": {
            "definition": (
                f"lowest height that gives {LEVELLING_SHARE:.0%} of the largest gain among the listed heights, "
                f"gain counted from the lowest height >= {MIN_MEANINGFUL_HEIGHT_M:g} m (docs/ASSUMPTIONS.md, A7, A20)"
            ),
            "by_site": levelling,
        },
        "horizons_computed_now": computed,
        "timing": timing,
        "notes": [
            "0 m is an observer on the terrain-model surface; its horizon is set by pixel-scale slopes (A7).",
            "Power-system values marked as placeholders are not data of a real lander (A14).",
            "The mast's own mass and shadow are not modelled; weigh the battery mass saved against them.",
        ],
    }
    return pd.concat(tables, ignore_index=True), meta


def _end_labels(axis: plt.Axes, ends: list[tuple[float, float, str, str, str]], min_gap_pt: float = 11.0) -> None:
    """Direct labels right of the last point of each line, pushed apart so they do not overlap.

    ``ends`` holds (x, y, text, colour, marker); a small marker of the series stands before
    the text, so a label stays attributable when two lines end at the same point.
    """
    if not ends:
        return
    to_points = 72.0 / axis.figure.dpi
    placed = sorted(
        ((axis.transData.transform((x, y))[1] * to_points, x, y, text, color, marker)
         for x, y, text, color, marker in ends),
        key=lambda item: item[0],
    )
    positions = [item[0] for item in placed]
    for index in range(1, len(positions)):
        positions[index] = max(positions[index], positions[index - 1] + min_gap_pt)
    shift = (positions[-1] - placed[-1][0]) / 2.0  # centre the stack on the points
    for (y_pt, x, y, text, color, marker), target in zip(placed, positions):
        dy = target - y_pt - shift
        glyph = offset_copy(axis.transData, fig=axis.figure, x=11.0, y=dy, units="points")
        axis.plot([x], [y], linestyle="none", marker=marker, markersize=5, color=color, transform=glyph,
                  clip_on=False, zorder=4)
        axis.annotate(
            text, xy=(x, y), xytext=(16.0, dy), textcoords="offset points",
            va="center", ha="left", fontsize=8, color=TEXT_SECONDARY, annotation_clip=False,
        )


def figure(table: pd.DataFrame, meta: dict, path: Path) -> None:
    panels = (
        ("sunlit_pct", "Time with any part of the Sun visible, %", "{:.1f} %", (0.0, 100.0)),
        ("longest_night_h", "Longest night (no part of the Sun visible), h", "{:.0f} h", None),
        ("required_capacity_wh", "Smallest battery that survives the window, Wh", "{:,.0f} Wh", None),
        ("earth_pct", "Time with the Earth in line of sight, %", "{:.1f} %", (0.0, 100.0)),
    )
    specific = meta["power_system"]["battery_specific_energy_wh_per_kg"]
    # 0 m is left out of the figure: its values (nights of months) would set the scale and
    # are not those of a real lander (A7). They stay in the table.
    left_out = sorted(table.loc[table["mast_height_m"] < MIN_MEANINGFUL_HEIGHT_M, "mast_height_m"].unique().tolist())
    table = table[table["mast_height_m"] >= MIN_MEANINGFUL_HEIGHT_M]
    heights = sorted(table["mast_height_m"].unique().tolist())
    if not heights:
        print(f"figure skipped: no mast height of at least {MIN_MEANINGFUL_HEIGHT_M:g} m")
        return
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": TEXT_SECONDARY,
                         "xtick.color": TEXT_SECONDARY, "ytick.color": TEXT_SECONDARY})
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), dpi=120, facecolor=SURFACE)
    for axis, (column, title, label_format, limits) in zip(axes.flat, panels):
        axis.set_facecolor(SURFACE)
        ends = []
        for index, (site_id, rows) in enumerate(table.groupby("site", sort=False)):
            color, marker = SERIES[index % len(SERIES)], MARKERS[index % len(MARKERS)]
            x = rows["mast_height_m"].to_numpy()
            y = rows[column].to_numpy(dtype=float)
            axis.plot(x, y, color=color, linewidth=1.8, solid_capstyle="round", solid_joinstyle="round",
                      marker=marker, markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.5,
                      label=rows["site_name"].iloc[0], zorder=3)
            if not np.isfinite(y[-1]):
                continue  # e.g. no battery capacity survives the window; the table says so
            text = label_format.format(y[-1])
            if column == "required_capacity_wh" and specific:
                text += f" · {y[-1] / specific:.1f} kg"
            ends.append((x[-1], y[-1], text, color, marker))
        axis.set_title(title, fontsize=9.5, color=TEXT_PRIMARY, loc="left")
        axis.set_xticks(heights)
        axis.set_xlim(min(heights) - 0.6, max(heights) + 0.6)
        if limits:
            axis.set_ylim(*limits)
        else:
            axis.set_ylim(bottom=0.0, top=axis.get_ylim()[1] * 1.05)
        axis.grid(True, color=GRID, linewidth=0.8)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        if column == "required_capacity_wh":
            axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        _end_labels(axis, ends)
    for axis in axes[1]:
        axis.set_xlabel("Height of the panel and the antenna above the surface (mast), m"
                        if meta["mast_carries"] == "both" else f"Mast height, m (mast carries: {meta['mast_carries']})")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.06, 0.935), ncol=len(labels), frameon=False,
               fontsize=9, labelcolor=TEXT_PRIMARY)
    start, stop = meta["window_utc"]
    placeholder_power = bool(meta["placeholder_keys"]["power"])
    fig.suptitle(
        f"Mast-height trade-off, {start[:10]} to {stop[:10]} UTC (1 h steps)"
        + ("  -  lander values not confirmed by the engineer (A14)" if placeholder_power else ""),
        x=0.06, ha="left", fontsize=11, color=TEXT_PRIMARY,
    )
    system = meta["power_system"]
    low_note = (
        f"Heights below {MIN_MEANINGFUL_HEIGHT_M:g} m ({', '.join(f'{h:g}' for h in left_out)} m) are in the table only: "
        "an observer that low has a horizon set by pixel-scale slopes of the terrain model (docs/ASSUMPTIONS.md, A7).\n"
        if left_out else ""
    )
    panel = (
        "tracking vertical panel" if system["panel_type"] == "tracking"
        else f"fixed vertical panel facing {np.rad2deg(system['panel_fixed_azimuth_rad']):g} deg"
    )
    fig.text(
        0.06, 0.012,
        low_note
        + f"Power system{' (not confirmed by the engineer, A14)' if placeholder_power else ''}: {panel} "
        f"{system['panel_area_m2']:g} m2 at {100 * system['panel_efficiency']:g} %, load {system['load_day_w']:g} W "
        f"in day mode ({system['day_load_rule'].replace('_', ' ')}) and {system['load_night_w']:g} W otherwise, usable depth of discharge "
        f"{system['battery_max_dod']:g}, efficiencies {system['battery_charge_efficiency']:g} / "
        f"{system['battery_discharge_efficiency']:g}"
        + (f", battery mass at {specific:g} Wh/kg. " if specific else ", no battery mass (specific energy not given). ")
        + f"Earth: {meta['comm']['rule']} of the disc above the terrain horizon, margin {meta['comm']['margin_deg']:g} deg.",
        fontsize=7.5, color=TEXT_SECONDARY, va="bottom", wrap=True,
    )
    fig.subplots_adjust(left=0.06, right=0.86, top=0.87, bottom=0.12, hspace=0.32, wspace=0.42)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def markdown(table: pd.DataFrame, meta: dict) -> str:
    lines = [
        "| Site | Mast, m | Sun visible, % | Mean visible disc, % | Longest night, h | Earth in view, % | "
        "Longest Earth gap, h | Battery needed, Wh | Battery mass, kg |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in table.itertuples(index=False):
        night = f"{row.longest_night_h:.0f}" + (" (edge)" if row.longest_night_at_window_edge else "")
        gap = f"{row.longest_earth_gap_h:.0f}" + (" (edge)" if row.longest_earth_gap_at_window_edge else "")
        capacity = f"{row.required_capacity_wh:,.0f}" if np.isfinite(row.required_capacity_wh) else "none suffices"
        mass = f"{row.required_battery_mass_kg:.1f}" if np.isfinite(row.required_battery_mass_kg) else "n/a"
        lines.append(
            f"| {row.site_name} | {row.mast_height_m:g} | {row.sunlit_pct:.1f} | {row.mean_sun_fraction_pct:.1f} | "
            f"{night} | {row.earth_pct:.1f} | {gap} | {capacity} | {mass} |"
        )
    lines.append("")
    lines.append("Height where the gain levels off (" + meta["levelling_off"]["definition"] + "):")
    for site_id, heights in meta["levelling_off"]["by_site"].items():
        lines.append(f"- {site_id}: " + ", ".join(f"{key} {value:g} m" if value is not None else f"{key} none"
                                                  for key, value in heights.items()))
    return "\n".join(lines)


def iso_date(text: str) -> str:
    """Argument type: a calendar date (YYYY-MM-DD); also keeps ':' out of the file names."""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"'{text}' is not a date YYYY-MM-DD") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sites", nargs="+", default=list(DEFAULT_SITES))
    parser.add_argument("--start", type=iso_date, default="2027-01-01", help="UTC date, inclusive")
    parser.add_argument("--stop", type=iso_date, default="2028-01-01", help="UTC date, exclusive")
    args = parser.parse_args()

    started = time.perf_counter()
    table, meta = run(args.sites, args.start, args.stop)
    meta["timing"]["total_s"] = round(time.perf_counter() - started, 2)
    stem = f"mast_tradeoff_{args.start}_{args.stop}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_DIR / f"{stem}.csv", index=False, float_format="%.4f")
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    figure(table, meta, FIGURE_DIR / f"{stem}.png")
    print(markdown(table, meta))
    print(f"\nwritten: {(OUT_DIR / stem).relative_to(ROOT)}.csv/.json, {(FIGURE_DIR / stem).relative_to(ROOT)}.png")
    print(f"timing: {meta['timing']}")


if __name__ == "__main__":
    main()

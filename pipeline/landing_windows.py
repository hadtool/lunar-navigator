"""Landing-date calendar of one site (T11): survival, battery margin and Earth link per landing day.

    uv run python pipeline/landing_windows.py
    uv run python pipeline/landing_windows.py --site malapert_massif --mast 2 --start 2027-01-01 --stop 2029-01-01

For every landing day in [start, stop) a mission of `mission_duration_days` from
docs/ENGINEERING_INPUTS.md (placeholder: 14 days) is simulated with the power system and the
link rule of the same file (placeholders of docs/ASSUMPTIONS.md where it is empty), battery
at its initial state of charge at landing. Uses the cached horizon of the site and height.

Writes data/processed/windows/landing_<site>_h<mast>_<start>_<stop>.csv (one row per
landing day) and .json (inputs, up to five best dates, timing) and two figures in
docs/figures/: the calendar (landing_calendar_...) and the daily Sun and Earth time with
the best missions marked (landing_timeline_...), which explains the ranking.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch, Rectangle

from lunarnav.comms import default_comm_settings, link_mask
from lunarnav.ephemeris import centre_ephemeris, sky_track
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.power import default_power_system, with_capacity
from lunarnav.visibility import runs, visibility
from lunarnav.windows import best_landing_dates, default_mission_days, landing_windows

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_horizons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
OUT_DIR = ROOT / "data" / "processed" / "windows"
FIGURE_DIR = ROOT / "docs" / "figures"

# Chart tokens (light surface), dataviz reference palette: sequential blue ramp for the
# battery margin, status "critical" (always with a cross and a legend label) for failure,
# categorical slots 1-3 for Earth, Sun and the battery line.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BLUE_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")
CRITICAL = "#d03b3b"
EARTH, SUN, BATTERY = "#2a78d6", "#eb6834", "#1baf7a"


def iso_date(text: str) -> str:
    """Argument type: a calendar date (YYYY-MM-DD)."""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"'{text}' is not a date YYYY-MM-DD") from error


def run(site_id: str, mast_height_m: float, start: str, stop: str,
        battery_wh: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    sites = {site["id"]: site for site in build_horizons.load_sites()}
    if site_id not in sites:
        raise SystemExit(f"unknown site id {site_id}; known: {sorted(sites)}")
    path = cache_path(HORIZON_DIR, site_id, mast_height_m)
    if not path.is_file():
        raise SystemExit(f"{path} is missing; run: uv run python pipeline/build_horizons.py "
                         f"--sites {site_id} --heights {mast_height_m:g}")
    if np.datetime64(stop, "D") <= np.datetime64(start, "D"):
        raise SystemExit(f"--stop ({stop}) must be after --start ({start})")
    profile = HorizonProfile.load(path)
    days, mission_placeholders = default_mission_days()
    system, power_placeholders = default_power_system()
    if battery_wh is not None:  # an illustration with another battery, named so in the outputs
        system = with_capacity(system, battery_wh)
    comm, comm_placeholders = default_comm_settings()
    duration_h = days * 24.0
    if abs(duration_h - round(duration_h)) > 1e-9:
        raise SystemExit(f"mission length {days} days is not a whole number of hours")
    first_landing = np.datetime64(start, "h")
    last_landing = np.datetime64(stop, "h") - np.timedelta64(24, "h")
    hour = np.timedelta64(1, "h")
    times = np.arange(first_landing, last_landing + int(round(duration_h)) * hour, hour)

    timing = {}
    started = time.perf_counter()
    centre = centre_ephemeris(times)
    timing["ephemeris_s"] = round(time.perf_counter() - started, 2)
    started = time.perf_counter()
    track = sky_track(profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m, centre)
    vis = visibility(track, profile)
    timing["visibility_s"] = round(time.perf_counter() - started, 2)
    started = time.perf_counter()
    try:
        table = landing_windows(track, vis, system, comm, duration_h=duration_h, last_landing_utc=last_landing)
    except ValueError as error:
        raise SystemExit(f"cannot build the calendar: {error}") from error
    best = best_landing_dates(table)
    timing["calendar_s"] = round(time.perf_counter() - started, 2)

    link = link_mask(vis, track.earth.angular_radius_rad, comm)
    hourly = pd.DataFrame({"sun": vis.sun_fraction > 0.0, "earth": link}, index=pd.to_datetime(times))

    meta = {
        "task": "T11 landing-date search",
        "site": site_id,
        "site_name": sites[site_id]["name"],
        "mast_height_m": mast_height_m,
        "landing_days_utc": [start, str(last_landing.astype("datetime64[D]"))],
        "mission_days": days,
        "series_utc": [str(times[0]), str(times[-1] + hour)],
        "landings": int(len(table)),
        "surviving_landings": int(table["survives"].sum()),
        "placeholder_keys": {
            "mission": list(mission_placeholders),
            "power": list(power_placeholders),
            "comm": list(comm_placeholders),
        },
        "power_system": {key: value for key, value in system.__dict__.items()},
        "battery_overridden_for_illustration": battery_wh is not None,
        "comm": {"rule": comm.rule, "margin_deg": float(np.rad2deg(comm.margin_rad))},
        "ranking": "survives, then highest lowest state of charge, then highest Earth-link share, then earlier date; "
                   "missions of the chosen dates do not overlap (docs/ASSUMPTIONS.md, A22)",
        "best": [
            {
                "rank": int(row.rank),
                "landing_utc": row.landing_utc.strftime("%Y-%m-%d"),
                "survives": bool(row.survives),
                "min_soc_pct": round(float(row.min_soc_pct), 1),
                "earth_pct": round(float(row.earth_pct), 1),
                "sunlit_pct": round(float(row.sunlit_pct), 1),
                "longest_night_h": float(row.longest_night_h),
                "sun_and_earth_pct": round(float(row.sun_and_earth_pct), 1),
            }
            for row in best.itertuples(index=False)
        ],
        "timing": timing,
    }
    return table, best, hourly, meta


def _style(axis: plt.Axes) -> None:
    axis.set_facecolor(SURFACE)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(MUTED)
    axis.tick_params(colors=TEXT_SECONDARY, labelsize=8)


def _best_words(best: pd.DataFrame) -> str:
    """'best' when the ranked days survive, 'least bad' when none does (the ranking still applies)."""
    if best.empty:
        return "best"
    if not best["survives"].any():
        return "least bad (no landing day survives)"
    return "best" if best["survives"].all() else "best (crossed cells among them do not survive)"


def _title(meta: dict) -> str:
    placeholder = "  -  lander values not confirmed by the engineer (A14)" if meta["placeholder_keys"]["power"] else ""
    return (f"{meta['site_name']}: landing days {meta['landing_days_utc'][0]} to {meta['landing_days_utc'][1]} (UTC)\n"
            f"{meta['mission_days']:g}-day mission, panel and antenna {meta['mast_height_m']:g} m above the surface"
            f"{placeholder}")


def calendar_figure(table: pd.DataFrame, best: pd.DataFrame, meta: dict, path: Path) -> None:
    months = pd.period_range(table["landing_utc"].min(), table["landing_utc"].max(), freq="M")
    row_of = {month: index for index, month in enumerate(months)}
    margin = np.full((len(months), 31), np.nan)
    fails = np.zeros(margin.shape, dtype=bool)
    for landing, survives, min_soc in zip(table["landing_utc"], table["survives"], table["min_soc_pct"]):
        cell = row_of[landing.to_period("M")], landing.day - 1
        margin[cell] = min_soc
        fails[cell] = not survives
    allowed_min = 100.0 * (1.0 - meta["power_system"]["battery_max_dod"])

    height_in = 0.3 * len(months) + 2.2
    fig, axis = plt.subplots(figsize=(11.5, height_in), dpi=120, facecolor=SURFACE)
    _style(axis)
    cmap = LinearSegmentedColormap.from_list("margin", BLUE_RAMP)
    cmap.set_bad(SURFACE)
    norm = Normalize(vmin=allowed_min, vmax=100.0)
    image = axis.imshow(np.where(fails, np.nan, margin), cmap=cmap, norm=norm, aspect="auto", interpolation="nearest")
    failed = np.zeros((*margin.shape, 4))
    failed[fails] = matplotlib.colors.to_rgba(CRITICAL)
    axis.imshow(failed, aspect="auto", interpolation="nearest")
    for row, col in zip(*np.nonzero(fails)):
        axis.text(col, row, "×", ha="center", va="center", color="white", fontsize=7)
    for item in best.itertuples(index=False):
        row, col = row_of[item.landing_utc.to_period("M")], item.landing_utc.day - 1
        axis.add_patch(Rectangle((col - 0.5, row - 0.5), 1, 1, fill=False, edgecolor=TEXT_PRIMARY, linewidth=2.0))
        dark = (not item.survives) or norm(item.min_soc_pct) > 0.45
        axis.text(col, row, str(item.rank), ha="center", va="center", fontsize=7.5, fontweight="bold",
                  color="white" if dark else TEXT_PRIMARY)
    # Surface-coloured gaps between the cells.
    axis.set_xticks(np.arange(-0.5, 31, 1), minor=True)
    axis.set_yticks(np.arange(-0.5, len(months), 1), minor=True)
    axis.grid(which="minor", color=SURFACE, linewidth=1.6)
    axis.tick_params(which="minor", length=0)
    axis.set_xticks(range(31), [str(day) for day in range(1, 32)])
    axis.set_yticks(range(len(months)), [month.strftime("%b %Y") for month in months])
    axis.tick_params(length=0)
    for side in ("left", "bottom"):
        axis.spines[side].set_visible(False)
    axis.set_xlabel("Landing day of the month (UTC)", color=TEXT_SECONDARY, fontsize=8.5)
    bar = fig.colorbar(image, ax=axis, fraction=0.03, pad=0.015)
    bar.set_label("Lowest state of charge during the mission, %", color=TEXT_SECONDARY, fontsize=8.5)
    bar.ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
    bar.outline.set_visible(False)
    handles = [
        Patch(facecolor=CRITICAL, label=f"× does not survive: the charge falls below {allowed_min:g} %"),
        Patch(facecolor="none", edgecolor=TEXT_PRIMARY, linewidth=2.0,
              label=f"1-{len(best)}: {_best_words(best)} landing days (survival, then charge margin, then Earth link; "
                    "missions do not overlap)"),
    ]
    axis.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, frameon=False, fontsize=8,
                labelcolor=TEXT_PRIMARY, handlelength=1.2, borderaxespad=0.3)
    fig.suptitle(_title(meta), x=0.02, ha="left", fontsize=10, color=TEXT_PRIMARY)
    fig.text(0.02, 0.01, f"{meta['landings']} landing days, {meta['surviving_landings']} of them survive. "
             "Blank cells: no landing day in the range.", fontsize=7.5, color=TEXT_SECONDARY)
    fig.subplots_adjust(left=0.08, right=0.96, top=1.0 - 1.05 / height_in, bottom=0.55 / height_in + 0.03)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def _bars(axis: plt.Axes, mask: np.ndarray, times: pd.DatetimeIndex, row: float, color: str) -> None:
    """Runs of True in a uniformly sampled mask as horizontal bars on one row."""
    numbers = mdates.date2num(times.to_pydatetime())
    step = float(numbers[1] - numbers[0]) if numbers.size > 1 else 1.0 / 24.0
    spans = [(numbers[start], (stop - start) * step) for start, stop in runs(mask)]
    axis.broken_barh(spans, (row - 0.32, 0.64), facecolor=color, linewidth=0)


def timeline_figure(table: pd.DataFrame, best: pd.DataFrame, hourly: pd.DataFrame, meta: dict, path: Path) -> None:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(12, 6.2), dpi=120, sharex=True, facecolor=SURFACE,
                                      gridspec_kw={"height_ratios": [1.0, 1.7]})
    for axis in (top, bottom):
        _style(axis)
        for item in best.itertuples(index=False):
            axis.axvspan(item.landing_utc, item.end_utc, color=TEXT_PRIMARY, alpha=0.08, linewidth=0, zorder=0)
    rule = f"{meta['comm']['rule'].replace('_', ' ')} of the disc,\nmargin {meta['comm']['margin_deg']:g} deg"
    _bars(top, hourly["sun"].to_numpy(), hourly.index, 1.0, SUN)
    _bars(top, hourly["earth"].to_numpy(), hourly.index, 0.0, EARTH)
    top.set_yticks([1.0, 0.0], ["Sun visible\n(any part of the disc)", f"Earth link\n({rule})"])
    top.set_ylim(-0.6, 1.6)
    top.tick_params(axis="y", length=0)
    top.spines["left"].set_visible(False)
    for item in best.itertuples(index=False):
        top.text(item.landing_utc + (item.end_utc - item.landing_utc) / 2, 1.42, str(item.rank), ha="center",
                 va="bottom", fontsize=8, fontweight="bold", color=TEXT_PRIMARY)
    top.set_title(f"When the Sun and the Earth are in view (hourly); grey bands: missions of the {len(best)} "
                  f"{_best_words(best)} landing days", loc="left", fontsize=9.5, color=TEXT_PRIMARY)
    allowed_min = 100.0 * (1.0 - meta["power_system"]["battery_max_dod"])
    bottom.grid(True, axis="y", color=GRID, linewidth=0.8)
    bottom.set_axisbelow(True)
    bottom.set_ylim(0, 100)
    bottom.plot(table["landing_utc"], table["min_soc_pct"], color=BATTERY, linewidth=1.6, zorder=3)
    bottom.axhline(allowed_min, color=MUTED, linewidth=0.9, zorder=2)
    bottom.text(table["landing_utc"].iloc[-1], allowed_min + 1.5, f"allowed minimum {allowed_min:g} %", ha="right",
                va="bottom", fontsize=7.5, color=TEXT_SECONDARY)
    bottom.set_title(f"Lowest state of charge during a {meta['mission_days']:g}-day mission that lands on the day, %",
                     loc="left", fontsize=9.5, color=TEXT_PRIMARY)
    bottom.set_xlabel("UTC date", color=TEXT_SECONDARY, fontsize=8.5)
    fig.suptitle(_title(meta), x=0.02, ha="left", fontsize=10, color=TEXT_PRIMARY)
    fig.subplots_adjust(left=0.13, right=0.98, top=0.86, bottom=0.09, hspace=0.3)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", default="connecting_ridge")
    parser.add_argument("--mast", type=float, default=2.0, help="observer height in m (a cached horizon)")
    parser.add_argument("--start", type=iso_date, default="2027-01-01", help="first landing day (UTC)")
    parser.add_argument("--stop", type=iso_date, default="2029-01-01", help="day after the last landing day")
    parser.add_argument("--battery-wh", type=float, default=None,
                        help="illustration with another battery capacity (outputs get a _battery<Wh> suffix)")
    args = parser.parse_args()

    started = time.perf_counter()
    table, best, hourly, meta = run(args.site, args.mast, args.start, args.stop, args.battery_wh)
    meta["timing"]["total_s"] = round(time.perf_counter() - started, 2)
    stem = f"{args.site}_h{args.mast:g}_{args.start}_{args.stop}"
    if args.battery_wh is not None:
        stem += f"_battery{args.battery_wh:g}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_DIR / f"landing_{stem}.csv", index=False, float_format="%.4f", date_format="%Y-%m-%dT%H:%M")
    (OUT_DIR / f"landing_{stem}.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    calendar_figure(table, best, meta, FIGURE_DIR / f"landing_calendar_{stem}.png")
    timeline_figure(table, best, hourly, meta, FIGURE_DIR / f"landing_timeline_{stem}.png")

    print(f"{meta['site_name']}, {meta['mast_height_m']:g} m, {meta['mission_days']:g}-day missions: "
          f"{meta['surviving_landings']} of {meta['landings']} landing days survive")
    print(f"ranked landing days: {_best_words(best)}")
    columns = ["rank", "landing_utc", "survives", "min_soc_pct", "earth_pct", "sunlit_pct", "longest_night_h",
               "sun_and_earth_pct"]
    print(best[columns].to_string(index=False, float_format=lambda value: f"{value:.1f}"))
    print(f"timing: {meta['timing']}")


if __name__ == "__main__":
    main()

"""Rebuild all precomputed data of the app from scratch (T12).

    uv run python pipeline/build.py                  # horizons, ephemeris, metrics, manifest
    uv run python pipeline/build.py --skip-horizons  # reuse the cached horizons (no terrain needed)

Needs the LOLA rasters (horizons, unless --skip-horizons) and the SPICE kernels (ephemeris,
always) in data/raw/, see docs/SOURCES.md; both are checked before anything is written. The
old manifest is removed first, so a build that stops half-way leaves no manifest that
vouches for the files. Writes into data/processed/:

* horizons/<site>_h<height>.json: terrain horizon of every polar site for every mast height
  of docs/ENGINEERING_INPUTS.md (placeholder 0, 2, 5, 10, 20 m);
* ephemeris/centre_ephemeris_hourly.parquet: apparent Sun and Earth vectors from the Moon's
  centre, hourly, 2027-01-01 to 2030-02-01 UTC (one month beyond the analysis period, so a
  mission landing late in 2029 fits);
* metrics/visibility_metrics.json: visibility statistics per site, height and period
  (2027-2029 and each year);
* basemap/south_pole_relief.png: shaded relief behind the site map of the app (backdrop only;
  kept as it is with --skip-horizons, which needs no terrain);
* manifest.json: what was built, with sizes, checksums, timings and the inputs used.

The app reads only these files (lunarnav.store); it needs neither the terrain nor the kernels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow
import spiceypy

from lunarnav import ephemeris, store
from lunarnav.comms import CommSettings, comm_summary, default_comm_settings, link_mask
from lunarnav.horizon import cache_path
from lunarnav.mast import default_mast_settings
from lunarnav.visibility import window_metrics

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_basemap  # noqa: E402
import build_horizons  # noqa: E402

#: Size budget of data/processed (the files are committed for the deployed app).
SIZE_BUDGET_BYTES = 50 * 1024 * 1024
PERIODS = {
    "2027-2029": (store.ANALYSIS_START, store.ANALYSIS_STOP),
    "2027": (np.datetime64("2027-01-01T00:00", "ms"), np.datetime64("2028-01-01T00:00", "ms")),
    "2028": (np.datetime64("2028-01-01T00:00", "ms"), np.datetime64("2029-01-01T00:00", "ms")),
    "2029": (np.datetime64("2029-01-01T00:00", "ms"), np.datetime64("2030-01-01T00:00", "ms")),
}
METRIC_COLUMNS = (
    "site",
    "mast_height_m",
    "period",
    "start_utc",
    "stop_utc",
    "hours",
    "sunlit_pct",
    "mean_sun_fraction_pct",
    "longest_night_h",
    "longest_night_start_utc",
    "longest_night_at_period_edge",
    "earth_link_pct",
    "earth_any_part_pct",
    "longest_earth_gap_h",
    "longest_earth_gap_start_utc",
    "longest_earth_gap_at_period_edge",
    "sun_and_earth_pct",
)


def build_all_horizons(sites: list[dict], heights_m: tuple[float, ...]) -> dict:
    """Horizons of every site for every height from the LOLA rasters; returns timings in s."""
    started = time.perf_counter()
    regional = build_horizons.load_regional_terrains()
    timing = {"load_regional_terrain": round(time.perf_counter() - started, 1)}
    for site in sites:
        site_started = time.perf_counter()
        build_horizons.build_site(site, regional, heights_m, out_dir=store.HORIZON_DIR)
        timing[site["id"]] = round(time.perf_counter() - site_started, 1)
        print(f"  horizons {site['id']}: {timing[site['id']]} s")
    return timing


def site_metrics(site_id: str, mast_height_m: float, centre: ephemeris.CentreEphemeris,
                 comm: CommSettings) -> list[list]:
    """Rows of :data:`METRIC_COLUMNS` for one site and height, one per period."""
    track, vis = store.observer(store.load_horizon(site_id, mast_height_m), centre)
    times = np.asarray(track.times_utc)
    link = link_mask(vis, track.earth.angular_radius_rad, comm)
    rows = []
    for name, (start, stop) in PERIODS.items():
        metrics = window_metrics(vis, start, stop)
        selected = (times >= start) & (times < stop)
        summary = comm_summary(link[selected], times[selected], comm)
        both = (vis.sun_fraction[selected] > 0.0) & link[selected]
        rows.append([
            site_id,
            mast_height_m,
            name,
            metrics.start_utc,
            metrics.stop_utc,
            metrics.samples * metrics.step_hours,
            round(metrics.sunlit_pct, 4),
            round(metrics.mean_sun_fraction_pct, 4),
            metrics.longest_night.hours,
            metrics.longest_night.start_utc,
            metrics.longest_night.reaches_window_edge,
            round(summary.visible_pct, 4),
            round(metrics.earth_any_part_pct, 4),
            summary.longest_gap_h,
            summary.longest_gap_start_utc,
            summary.longest_gap_reaches_period_edge,
            round(float(100.0 * np.mean(both)), 4),
        ])
    return rows


def terrain_files(sites: list[dict]) -> list[Path]:
    """Raster files the horizons are computed from: the 40 m model and the 5 m site models."""
    files = [build_horizons.LOLA_DIR / build_horizons.REGIONAL_FILE]
    for site in sites:
        url = site.get("pgda_5m_dem")
        if url and (build_horizons.LOLA_DIR / url.rsplit("/", 1)[-1]).is_file():
            files.append(build_horizons.LOLA_DIR / url.rsplit("/", 1)[-1])
    return sorted(set(files))


def describe(paths: list[Path]) -> list[dict]:
    return [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in paths]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--skip-horizons", action="store_true",
                        help="reuse data/processed/horizons instead of recomputing them from the terrain "
                             "(the SPICE kernels are still needed)")
    args = parser.parse_args()

    total_started = time.perf_counter()
    sites = store.load_sites()
    mast, mast_placeholders = default_mast_settings()
    comm, comm_placeholders = default_comm_settings()
    timing: dict = {}

    # Fail before writing anything.
    kernels = [ephemeris.kernel_dir() / name for name in ephemeris.KERNEL_FILES]
    if missing := [path.name for path in kernels if not path.is_file()]:
        raise SystemExit(f"SPICE kernels missing in {ephemeris.kernel_dir()}: {missing}; see docs/SOURCES.md")
    expected_horizons = [cache_path(store.HORIZON_DIR, site["id"], height) for site in sites for height in mast.heights_m]
    if args.skip_horizons:
        if missing := [path for path in expected_horizons if not path.is_file()]:
            raise SystemExit(f"--skip-horizons, but {len(missing)} horizons are missing, e.g. {missing[0]}")
    elif not (build_horizons.LOLA_DIR / build_horizons.REGIONAL_FILE).is_file():
        raise SystemExit(f"{build_horizons.REGIONAL_FILE} missing in {build_horizons.LOLA_DIR}; see docs/SOURCES.md "
                         "(or use --skip-horizons)")
    store.MANIFEST_FILE.unlink(missing_ok=True)

    print(f"1/4 horizons: {len(sites)} sites x {len(mast.heights_m)} heights {list(mast.heights_m)} m")
    started = time.perf_counter()
    if args.skip_horizons:
        timing["horizons"] = {"skipped": True}
    else:
        timing["horizons"] = build_all_horizons(sites, mast.heights_m)
    timing["horizons_s"] = round(time.perf_counter() - started, 1)
    extra = sorted(set(store.HORIZON_DIR.glob("*.json")) - set(expected_horizons))
    if extra:
        print(f"  note: {len(extra)} horizon files are not for the current sites and heights and were left in "
              f"place (e.g. {extra[0].name}); delete them by hand if they are not needed")

    print(f"2/4 centre ephemeris {store.ANALYSIS_START} .. {store.EPHEMERIS_STOP} hourly")
    started = time.perf_counter()
    times = np.arange(store.ANALYSIS_START, store.EPHEMERIS_STOP, np.timedelta64(1, "h"))
    store.save_centre_ephemeris(ephemeris.centre_ephemeris(times))
    timing["ephemeris_s"] = round(time.perf_counter() - started, 1)

    print("3/4 visibility metrics (from the stored files, as the app reads them)")
    started = time.perf_counter()
    centre = store.load_centre_ephemeris()
    rows = [row for site in sites for height in mast.heights_m
            for row in site_metrics(site["id"], height, centre, comm)]
    store.write_text_atomic(store.METRICS_FILE, json.dumps({
        "description": "Visibility statistics per site, observer height and period; see docs/SOURCES.md",
        "sun_rule": "sunlit_pct, longest_night_*: any part of the solar disc above the terrain horizon "
                    "(docs/ASSUMPTIONS.md, A12); mean_sun_fraction_pct: mean visible share of the disc",
        "earth_link_rule": {"columns": "earth_link_pct, longest_earth_gap_*", "rule": comm.rule,
                            "margin_deg": float(np.rad2deg(comm.margin_rad)),
                            "placeholder_keys": list(comm_placeholders)},
        "earth_any_part_rule": "earth_any_part_pct: any part of the Earth's disc above the terrain horizon "
                               "(definition of the LOLA Earth-visibility map), independent of the link rule",
        "sun_and_earth_rule": "sun_and_earth_pct: any part of the Sun visible and the Earth link rule met at once",
        "columns": list(METRIC_COLUMNS),
        "rows": rows,
    }, separators=(",", ":")))
    timing["metrics_s"] = round(time.perf_counter() - started, 1)

    if not args.skip_horizons:
        print("4/4 basemap of the site map")
        started = time.perf_counter()
        build_basemap.build()
        timing["basemap_s"] = round(time.perf_counter() - started, 1)
    timing["total_s"] = round(time.perf_counter() - total_started, 1)

    files = sorted(path for path in store.PROCESSED_DIR.rglob("*")
                   if path.is_file() and path != store.MANIFEST_FILE and path.name != ".gitkeep")
    manifest = {
        "built_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "uv run python pipeline/build.py" + (" --skip-horizons" if args.skip_horizons else ""),
        "timing": timing,
        "ephemeris_period_utc": [str(store.ANALYSIS_START), str(store.EPHEMERIS_STOP)],
        "analysis_period_utc": [str(store.ANALYSIS_START), str(store.ANALYSIS_STOP)],
        "sites": [site["id"] for site in sites],
        "mast_heights_m": list(mast.heights_m),
        "placeholder_keys": {"mast": list(mast_placeholders), "comm": list(comm_placeholders)},
        "kernels": describe(kernels),
        "terrain": "not used (--skip-horizons)" if args.skip_horizons else describe(terrain_files(sites)),
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "spiceypy": spiceypy.__version__, "pyarrow": pyarrow.__version__},
        "files": [{"path": str(path.relative_to(store.ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)}
                  for path in files],
    }
    manifest["total_bytes"] = sum(item["bytes"] for item in manifest["files"])
    store.write_text_atomic(store.MANIFEST_FILE, json.dumps(manifest, indent=1))

    size_mb = manifest["total_bytes"] / 1024 / 1024
    print(f"done in {timing['total_s']} s: {len(files)} files, {size_mb:.1f} MB in data/processed")
    print(f"timing: horizons {timing['horizons_s']} s, ephemeris {timing['ephemeris_s']} s, "
          f"metrics {timing['metrics_s']} s")
    if manifest["total_bytes"] > SIZE_BUDGET_BYTES:
        raise SystemExit(f"data/processed is {size_mb:.1f} MB, above the budget of "
                         f"{SIZE_BUDGET_BYTES / 1024 / 1024:.0f} MB for the deployed app")


if __name__ == "__main__":
    main()

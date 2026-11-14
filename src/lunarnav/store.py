"""Precomputed data the app reads: site list, terrain horizons, centre ephemeris and metrics.

Nothing here needs the terrain rasters or the SPICE kernels:

* horizons are the cached JSON files of ``lunarnav.horizon`` (one per site and height);
* the Sun and Earth vectors of ``lunarnav.ephemeris.CentreEphemeris`` are stored once for
  all sites (Parquet); the sky track of any site follows from them with numpy
  (``ephemeris.sky_track``), exactly as in the pipeline;
* visibility metrics per site, height and period are a small JSON table.

``pipeline/build.py`` writes the files; docs/SOURCES.md describes them.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from lunarnav import ephemeris
from lunarnav.ephemeris import CentreEphemeris, SkyTrack, sky_track
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.visibility import Visibility, visibility

ROOT = Path(__file__).resolve().parents[2]
SITES_FILE = ROOT / "data" / "sites.json"
PROCESSED_DIR = ROOT / "data" / "processed"
HORIZON_DIR = PROCESSED_DIR / "horizons"
EPHEMERIS_FILE = PROCESSED_DIR / "ephemeris" / "centre_ephemeris_hourly.parquet"
METRICS_FILE = PROCESSED_DIR / "metrics" / "visibility_metrics.json"
MANIFEST_FILE = PROCESSED_DIR / "manifest.json"

#: Analysis period of the app, [start, stop): the years 2027-2029.
ANALYSIS_START = np.datetime64("2027-01-01T00:00", "ms")
ANALYSIS_STOP = np.datetime64("2030-01-01T00:00", "ms")
#: The stored ephemeris runs one month longer, so that a mission landing late in 2029 fits.
EPHEMERIS_STOP = np.datetime64("2030-02-01T00:00", "ms")

_METADATA_KEY = b"lunarnav"
_HEIGHT = re.compile(r"_h(?P<height>[0-9.]+)\.json$")
_EPHEMERIS_COLUMNS = ("time_utc", "et_s", "sun_x_m", "sun_y_m", "sun_z_m", "earth_x_m", "earth_y_m", "earth_z_m")


def write_text_atomic(path: str | Path, text: str) -> None:
    """Write a text file so that a crash never leaves a truncated file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def load_sites(path: str | Path = SITES_FILE, *, polar_only: bool = True) -> list[dict]:
    """Sites of data/sites.json; by default without the validation-only entries (Apollo 11)."""
    sites = json.loads(Path(path).read_text(encoding="utf-8"))["sites"]
    return [site for site in sites if site.get("role") != "validation_only"] if polar_only else sites


def horizon_heights(site_id: str, directory: str | Path = HORIZON_DIR) -> list[float]:
    """Observer heights (m) with a cached horizon for the site, sorted."""
    heights = []
    for path in Path(directory).glob(f"{glob.escape(site_id)}_h*.json"):
        match = _HEIGHT.search(path.name)
        # The site id itself may contain "_h" (e.g. "..._haworth"); the name must round-trip.
        if match and path == cache_path(directory, site_id, float(match["height"])):
            heights.append(float(match["height"]))
    return sorted(heights)


def load_horizon(site_id: str, mast_height_m: float, directory: str | Path = HORIZON_DIR) -> HorizonProfile:
    """Cached horizon of a site for one observer height."""
    path = cache_path(directory, site_id, mast_height_m)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run pipeline/build.py")
    return HorizonProfile.load(path)


# --- centre ephemeris ----------------------------------------------------------------------


def save_centre_ephemeris(centre: CentreEphemeris, path: str | Path = EPHEMERIS_FILE) -> None:
    """Store the centre ephemeris losslessly (float64, UTC times in ms, radii as metadata)."""
    times = np.asarray(centre.times_utc)
    if times.dtype != np.dtype("datetime64[ms]"):
        raise ValueError(f"times must be datetime64[ms] as made by lunarnav.ephemeris, got {times.dtype}")
    table = pa.table(
        {
            "time_utc": pa.array(times),
            "et_s": np.asarray(centre.et_s),
            "sun_x_m": centre.sun_m[:, 0],
            "sun_y_m": centre.sun_m[:, 1],
            "sun_z_m": centre.sun_m[:, 2],
            "earth_x_m": centre.earth_m[:, 0],
            "earth_y_m": centre.earth_m[:, 1],
            "earth_z_m": centre.earth_m[:, 2],
        }
    )
    metadata = {
        "sun_radius_m": centre.sun_radius_m,
        "earth_radius_m": centre.earth_radius_m,
        "frame": ephemeris.MOON_FRAME,
        "aberration_correction": ephemeris._ABERRATION_CORRECTION,
        "time_scale": "UTC (time_utc); TDB seconds past J2000 (et_s)",
        "kernels": list(ephemeris.KERNEL_FILES),
        "vectors": "Moon centre to the apparent position of the body, metres, ME frame at each time",
    }
    table = table.replace_schema_metadata({_METADATA_KEY: json.dumps(metadata).encode("utf-8")})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, path)


def _read_only(array: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(array)
    array.flags.writeable = False
    return array


def load_centre_ephemeris(path: str | Path = EPHEMERIS_FILE) -> CentreEphemeris:
    """Centre ephemeris written by :func:`save_centre_ephemeris` (no SPICE needed)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run pipeline/build.py")
    table = pq.read_table(path)
    stored = table.schema.metadata or {}
    missing = [name for name in _EPHEMERIS_COLUMNS if name not in table.column_names]
    if _METADATA_KEY not in stored or missing:
        raise ValueError(f"{path} is not a centre ephemeris written by lunarnav.store (missing: "
                         f"{missing or 'metadata'}); run pipeline/build.py")
    metadata = json.loads(stored[_METADATA_KEY])
    if metadata.get("frame") != ephemeris.MOON_FRAME:
        raise ValueError(f"{path} uses the frame {metadata.get('frame')}, expected {ephemeris.MOON_FRAME}")
    columns = {name: table.column(name).to_numpy() for name in _EPHEMERIS_COLUMNS}
    return CentreEphemeris(
        times_utc=_read_only(columns["time_utc"].astype("datetime64[ms]")),
        et_s=_read_only(columns["et_s"].astype(np.float64)),
        sun_m=_read_only(np.column_stack([columns["sun_x_m"], columns["sun_y_m"], columns["sun_z_m"]])),
        earth_m=_read_only(np.column_stack([columns["earth_x_m"], columns["earth_y_m"], columns["earth_z_m"]])),
        sun_radius_m=float(metadata["sun_radius_m"]),
        earth_radius_m=float(metadata["earth_radius_m"]),
    )


def centre_window(
    centre: CentreEphemeris, start_utc: str | np.datetime64, stop_utc: str | np.datetime64
) -> CentreEphemeris:
    """The part of a centre ephemeris inside ``[start_utc, stop_utc)``.

    A window that reaches outside the stored times is refused instead of silently shortened.
    """
    times = np.asarray(centre.times_utc)
    start, stop = np.datetime64(start_utc, "ms"), np.datetime64(stop_utc, "ms")
    step = times[1] - times[0] if times.size > 1 else np.timedelta64(0, "ms")
    if start < times[0] or stop > times[-1] + step:
        raise ValueError(f"window {start} .. {stop} is outside the stored ephemeris ({times[0]} .. {times[-1] + step})")
    selected = (times >= start) & (times < stop)
    if np.count_nonzero(selected) < 2:
        raise ValueError("the window contains fewer than two time steps")
    return CentreEphemeris(
        times_utc=_read_only(times[selected]),
        et_s=_read_only(centre.et_s[selected]),
        sun_m=_read_only(centre.sun_m[selected]),
        earth_m=_read_only(centre.earth_m[selected]),
        sun_radius_m=centre.sun_radius_m,
        earth_radius_m=centre.earth_radius_m,
    )


def observer(profile: HorizonProfile, centre: CentreEphemeris) -> tuple[SkyTrack, Visibility]:
    """Sky track and visibility for the observer of a horizon profile (surface plus mast)."""
    track = sky_track(profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m, centre)
    return track, visibility(track, profile)


# --- metrics -------------------------------------------------------------------------------


def load_metrics(path: str | Path = METRICS_FILE) -> pd.DataFrame:
    """Visibility metrics per site, height and period written by pipeline/build.py."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run pipeline/build.py")
    document = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(document["rows"], columns=document["columns"])

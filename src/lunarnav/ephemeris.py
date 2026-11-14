"""Apparent azimuth and elevation of the Sun and the Earth for a site on the Moon.

The calculation is local (SPICE kernels, see docs/SOURCES.md); JPL Horizons is only used
as an independent check in the tests.

Conventions
-----------
* Site coordinates are planetocentric latitude and east longitude in the lunar mean
  Earth / polar axis (ME) frame, the frame of the LOLA terrain. The Moon is a sphere of
  radius 1737.4 km and ``height_m`` is measured above that sphere, exactly like LOLA
  heights.
* Angles are radians, distances metres, times UTC.
* Azimuth is measured from local north, clockwise (towards east), in [0, 2*pi).
  Elevation is measured from the local horizontal plane of the sphere, so it does not
  include terrain: compare it with the terrain horizon from ``lunarnav.horizon``.
* Directions are apparent: corrected for light time and stellar aberration. There is no
  atmosphere, hence no refraction.

At the exact pole the north direction is undefined; the regular formulas are still used
with the longitude that was passed in, so azimuth 0 points along the meridian ``lon`` at
the south pole and along ``lon + 180 deg`` at the north pole. The result is continuous
along every meridian but depends on the longitude given for the pole.

Two-step use for many sites: :func:`centre_ephemeris` does all SPICE work once for a set
of times; :func:`sky_track` then turns it into azimuth and elevation for any site with
plain numpy. :func:`sun_earth_track` combines both for a single site.

SPICE keeps global state and is not thread-safe, so every SPICE call in this module is
made under one module-level lock.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import spiceypy as spice
from numpy.typing import ArrayLike, NDArray

MOON_RADIUS_M = 1_737_400.0

#: Body-fixed frame of the site coordinates: lunar mean Earth / polar axis frame realised
#: with the DE440 lunar orientation and aligned with the DE421 ME frame used by LOLA.
MOON_FRAME = "MOON_ME_DE440_ME421"

#: Kernels of the DE440 set, all from the NAIF generic kernels archive.
KERNEL_FILES = (
    "naif0012.tls",
    "pck00011.tpc",
    "de440s.bsp",
    "moon_pa_de440_200625.bpc",
    "moon_de440_250416.tf",
)

KERNEL_DIR_ENV = "LUNARNAV_KERNEL_DIR"
DEFAULT_KERNEL_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "kernels"

_ABERRATION_CORRECTION = "LT+S"
_KM = 1000.0
_J2000_UTC = np.datetime64("2000-01-01T12:00:00", "ms")

_spice_lock = threading.RLock()
_loaded_kernel_dir: Path | None = None


@dataclass(frozen=True)
class CentreEphemeris:
    """Site-independent part of the calculation for a set of times.

    Vectors point from the Moon's centre to the apparent position of the body and are
    expressed in the ME frame at each time. Arrays are read-only.
    """

    times_utc: NDArray[np.datetime64]
    et_s: NDArray[np.float64]
    sun_m: NDArray[np.float64]
    earth_m: NDArray[np.float64]
    sun_radius_m: float
    earth_radius_m: float


@dataclass(frozen=True)
class BodyTrack:
    """Apparent position of one body as seen from the site, one value per time."""

    azimuth_rad: NDArray[np.float64]
    elevation_rad: NDArray[np.float64]
    angular_radius_rad: NDArray[np.float64]
    distance_m: NDArray[np.float64]


@dataclass(frozen=True)
class SkyTrack:
    """Sun and Earth as seen from one site. Arrays are read-only, one value per time."""

    lat_rad: float
    lon_east_rad: float
    height_m: float
    times_utc: NDArray[np.datetime64]
    sun: BodyTrack
    earth: BodyTrack


def _read_only(array: NDArray) -> NDArray:
    array.flags.writeable = False
    return array


def kernel_dir() -> Path:
    """Directory with the SPICE kernels (``LUNARNAV_KERNEL_DIR`` overrides the default)."""
    return Path(os.environ.get(KERNEL_DIR_ENV, DEFAULT_KERNEL_DIR))


def load_kernels(directory: str | Path | None = None) -> None:
    """Load the SPICE kernels once per process (safe to call repeatedly and from threads)."""
    global _loaded_kernel_dir
    directory = Path(directory if directory is not None else kernel_dir()).resolve()
    with _spice_lock:
        if _loaded_kernel_dir == directory:
            return
        missing = [name for name in KERNEL_FILES if not (directory / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"SPICE kernels missing in {directory}: {', '.join(missing)}. "
                "Download them as described in docs/SOURCES.md."
            )
        previous = _loaded_kernel_dir
        loaded: list[str] = []
        try:
            for name in KERNEL_FILES:
                spice.furnsh(str(directory / name))
                loaded.append(name)
        except spice.SpiceyError:
            for name in loaded:
                spice.unload(str(directory / name))
            raise
        if previous is not None:
            for name in KERNEL_FILES:
                spice.unload(str(previous / name))
        _loaded_kernel_dir = directory


def site_vector_m(lat_rad: float, lon_east_rad: float, height_m: float = 0.0) -> NDArray[np.float64]:
    """Cartesian position of a site in the ME frame (metres from the Moon's centre)."""
    radius = MOON_RADIUS_M + height_m
    cos_lat = np.cos(lat_rad)
    return radius * np.array(
        [cos_lat * np.cos(lon_east_rad), cos_lat * np.sin(lon_east_rad), np.sin(lat_rad)]
    )


def local_axes(lat_rad: float, lon_east_rad: float) -> NDArray[np.float64]:
    """Rows are the unit vectors east, north and up of the site in the ME frame.

    The formulas stay valid at the poles, where they use the longitude passed in.
    """
    sin_lat, cos_lat = np.sin(lat_rad), np.cos(lat_rad)
    sin_lon, cos_lon = np.sin(lon_east_rad), np.cos(lon_east_rad)
    east = np.array([-sin_lon, cos_lon, 0.0])
    north = np.array([-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat])
    up = np.array([cos_lat * cos_lon, cos_lat * sin_lon, sin_lat])
    return np.vstack([east, north, up])


def normalise_times(times_utc: ArrayLike) -> NDArray[np.datetime64]:
    """Return UTC times as a one-dimensional ``datetime64[ms]`` array.

    Accepts ISO strings, ``datetime``/``datetime64`` scalars or sequences and pandas
    objects. Values without a time zone are taken as UTC; time-zone-aware values are
    converted to UTC. Resolution is one millisecond (finer input is truncated). A scalar
    gives an array of length one.
    """
    native = np.asarray(times_utc)
    if native.dtype.kind == "M":
        # Already datetime64 (any unit, always time-zone-naive, taken as UTC). Converting
        # it to objects would turn nanosecond values into plain integers.
        values = np.atleast_1d(native)
        if values.ndim != 1:
            raise ValueError("times_utc must be a scalar or a one-dimensional sequence")
        if np.isnat(values).any():
            raise ValueError("times_utc contains NaT")
        return values.astype("datetime64[ms]")
    values = np.atleast_1d(np.asarray(times_utc, dtype=object))
    if values.ndim != 1:
        raise ValueError("times_utc must be a scalar or a one-dimensional sequence")
    index = pd.DatetimeIndex(pd.to_datetime(values, utc=True, format="ISO8601"))
    if index.isna().any():
        raise ValueError("times_utc contains NaT")
    return index.tz_localize(None).to_numpy().astype("datetime64[ms]")


def utc_to_et(times_utc: ArrayLike) -> tuple[NDArray[np.datetime64], NDArray[np.float64]]:
    """Convert UTC times to SPICE ephemeris time (TDB seconds past J2000).

    ``datetime64`` cannot represent a leap second (23:59:60), so a uniform UTC series
    that crosses one advances by two seconds of ephemeris time over that step.
    """
    times = normalise_times(times_utc)
    # Seconds past J2000 counted on the UTC calendar; SPICE adds TDB - UTC (leap seconds
    # and the periodic relativistic term), exactly as spice.utc2et does for a string.
    formal_utc_s = (times - _J2000_UTC).astype(np.int64) / 1000.0
    with _spice_lock:
        load_kernels()
        delta = np.fromiter(
            (spice.deltet(float(value), "UTC") for value in formal_utc_s),
            dtype=np.float64,
            count=formal_utc_s.size,
        )
    return times, formal_utc_s + delta


def centre_ephemeris(times_utc: ArrayLike) -> CentreEphemeris:
    """Apparent Sun and Earth positions relative to the Moon's centre (all SPICE work).

    Raises ``ValueError`` when a time lies outside the coverage of the kernels
    (de440s.bsp: years 1850-2149).
    """
    times, et = utc_to_et(times_utc)
    with _spice_lock:
        load_kernels()
        try:
            vectors = {}
            for body in ("SUN", "EARTH"):
                if et.size:
                    position_km, _ = spice.spkpos(
                        body, et, MOON_FRAME, _ABERRATION_CORRECTION, "MOON"
                    )
                    vectors[body] = np.asarray(position_km, dtype=np.float64).reshape(-1, 3) * _KM
                else:
                    vectors[body] = np.empty((0, 3))
            radii = {
                body: float(spice.bodvrd(body, "RADII", 3)[1][0]) * _KM for body in vectors
            }
        except spice.SpiceyError as error:
            spice.reset()
            short = getattr(error, "short", "")
            if "SPKINSUFFDATA" not in short:
                raise  # missing frame, damaged kernel, ...: not a problem of the input
            raise ValueError(
                "times are outside the coverage of the ephemeris kernels "
                f"({times.min()} .. {times.max()}): {short}"
            ) from error
    return CentreEphemeris(
        times_utc=_read_only(times),
        et_s=_read_only(et),
        sun_m=_read_only(vectors["SUN"]),
        earth_m=_read_only(vectors["EARTH"]),
        sun_radius_m=radii["SUN"],
        earth_radius_m=radii["EARTH"],
    )


def _body_track(
    centre_to_body_m: NDArray[np.float64],
    body_radius_m: float,
    site_m: NDArray[np.float64],
    axes: NDArray[np.float64],
) -> BodyTrack:
    # Light time and aberration were evaluated at the Moon's centre; subtracting the site
    # vector gives the exact parallax. Evaluating them at the site instead would change
    # the direction by less than 1e-6 deg (1737 km is 6 ms of light time and the site
    # moves at most 4.6 m/s relative to the centre).
    site_to_body_m = centre_to_body_m - site_m
    distance_m = np.linalg.norm(site_to_body_m, axis=1)
    east, north, up = (site_to_body_m @ axes.T).T
    azimuth = np.mod(np.arctan2(east, north), 2.0 * np.pi)
    elevation = np.arcsin(np.clip(up / distance_m, -1.0, 1.0))
    angular_radius = np.arcsin(np.clip(body_radius_m / distance_m, 0.0, 1.0))
    return BodyTrack(
        _read_only(azimuth), _read_only(elevation), _read_only(angular_radius), _read_only(distance_m)
    )


def sky_track(
    lat_rad: float,
    lon_east_rad: float,
    height_m: float,
    centre: CentreEphemeris,
) -> SkyTrack:
    """Azimuth, elevation and angular radius of the Sun and the Earth for one site.

    Pure numpy on top of :func:`centre_ephemeris`; safe to call from several threads.
    """
    if not -np.pi / 2 <= lat_rad <= np.pi / 2:
        raise ValueError(f"lat_rad must be within [-pi/2, pi/2], got {lat_rad}")
    if not np.isfinite(lon_east_rad) or not np.isfinite(height_m):
        raise ValueError("lon_east_rad and height_m must be finite")
    site_m = site_vector_m(lat_rad, lon_east_rad, height_m)
    axes = local_axes(lat_rad, lon_east_rad)
    return SkyTrack(
        lat_rad=float(lat_rad),
        lon_east_rad=float(lon_east_rad),
        height_m=float(height_m),
        times_utc=centre.times_utc,
        sun=_body_track(centre.sun_m, centre.sun_radius_m, site_m, axes),
        earth=_body_track(centre.earth_m, centre.earth_radius_m, site_m, axes),
    )


def sun_earth_track(
    lat_rad: float,
    lon_east_rad: float,
    height_m: float,
    times_utc: ArrayLike,
) -> SkyTrack:
    """Apparent azimuth, elevation and angular radius of the Sun and the Earth.

    Parameters
    ----------
    lat_rad, lon_east_rad:
        Planetocentric latitude and east longitude of the site in the ME frame, radians.
    height_m:
        Height of the observer above the 1737.4 km sphere (terrain height plus mast).
    times_utc:
        UTC times, see :func:`normalise_times`.

    Returns
    -------
    SkyTrack
        Centre directions of the two bodies; elevations refer to the local horizontal
        plane, not to the terrain horizon. For many sites and the same times call
        :func:`centre_ephemeris` once and :func:`sky_track` per site.
    """
    if not -np.pi / 2 <= lat_rad <= np.pi / 2:  # fail before the SPICE work
        raise ValueError(f"lat_rad must be within [-pi/2, pi/2], got {lat_rad}")
    return sky_track(lat_rad, lon_east_rad, height_m, centre_ephemeris(times_utc))

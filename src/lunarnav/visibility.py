"""Visibility of the Sun and the Earth above the terrain horizon, and window statistics.

Inputs are the apparent directions from ``lunarnav.ephemeris`` and the terrain horizon
from ``lunarnav.horizon``. For every time step the module gives

* the fraction of the solar disc (by area) that is above the terrain horizon,
* the same fraction for the Earth's disc,
* the clearance of each centre: its elevation minus the horizon at its azimuth.

Disc fraction
-------------
The disc is cut into vertical strips. Each strip looks up the horizon at its own azimuth,
so a horizon that slopes or steps across the disc is handled; the visible part of each
chord is summed with Gauss-Chebyshev weights (exact area weighting of the strips). For a
level horizon the result equals the circular-segment formula (:func:`segment_fraction`)
to about 0.001. With 32 strips a sliver thinner than 0.11 % of the disc radius (0.0003 deg
for the Sun) is not seen, which is negligible for "any part of the disc" statistics.

What the numbers do not include: the phase of the Earth, the brightness distribution of
the solar disc (limb darkening), light scattered by terrain, and anything that is not in
the terrain model (docs/ASSUMPTIONS.md). A visible Sun is therefore not yet guaranteed
power and a visible Earth is not yet a guaranteed link.

Angles are radians, times UTC. Durations of nights and gaps are counted in whole time
steps, so they are uncertain by about one step at each end.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from lunarnav.ephemeris import BodyTrack, CentreEphemeris, SkyTrack, sky_track
from lunarnav.horizon import HorizonProfile

#: Number of vertical strips across a disc. The Earth (about 1.9 deg wide) spans four
#: 0.5 deg horizon bins, the Sun one or two.
DEFAULT_STRIPS = 32
_HOUR = np.timedelta64(1, "h")


def segment_fraction(depth: ArrayLike) -> NDArray[np.float64]:
    """Fraction of a disc above a level line.

    ``depth`` is (elevation of the disc centre - elevation of the line) / disc radius:
    -1 or less gives 0 (disc fully below), 0 gives 0.5, +1 or more gives 1.
    """
    d = np.clip(np.asarray(depth, dtype=np.float64), -1.0, 1.0)
    return 0.5 + (d * np.sqrt(1.0 - d * d) + np.arcsin(d)) / np.pi


def disc_fraction(
    body: BodyTrack, profile: HorizonProfile, strips: int = DEFAULT_STRIPS
) -> NDArray[np.float64]:
    """Fraction of the disc area above the terrain horizon, one value per time (0..1)."""
    if strips < 1:
        raise ValueError("strips must be >= 1")
    azimuth = np.asarray(body.azimuth_rad, dtype=np.float64)
    elevation = np.asarray(body.elevation_rad, dtype=np.float64)
    radius = np.asarray(body.angular_radius_rad, dtype=np.float64)
    if azimuth.size == 0:
        return np.empty(0)
    if not np.all(radius > 0.0):
        raise ValueError("angular radii must be positive")
    # Gauss-Chebyshev nodes of the second kind: sum(w * g(x)) = integral of sqrt(1 - x^2) g(x).
    k = np.arange(1, strips + 1)
    theta = k * np.pi / (strips + 1)
    x = np.cos(theta)  # strip position across the disc, in disc radii
    weight = np.sin(theta) ** 2 / (strips + 1)  # includes the 1/pi of the disc area
    half_chord = np.sin(theta)  # sqrt(1 - x^2)

    # A small circle of angular radius r spans r / cos(elevation) in azimuth.
    stretch = radius / np.maximum(np.cos(elevation), 0.05)
    strip_azimuth = azimuth[:, None] + stretch[:, None] * x[None, :]
    horizon = profile.elevation_at(strip_azimuth)
    # Height of the horizon above the disc centre in disc radii, per strip.
    t = (horizon - elevation[:, None]) / radius[:, None]
    visible_part_of_chord = np.clip(1.0 - t / half_chord[None, :], 0.0, 2.0)
    fraction = visible_part_of_chord @ weight
    return np.clip(fraction, 0.0, 1.0)


def centre_clearance(body: BodyTrack, profile: HorizonProfile) -> NDArray[np.float64]:
    """Elevation of the body's centre minus the terrain horizon at its azimuth (radians)."""
    return np.asarray(body.elevation_rad) - profile.elevation_at(body.azimuth_rad)


@dataclass(frozen=True)
class Visibility:
    """Sun and Earth visibility from one observer position, one value per time."""

    times_utc: NDArray[np.datetime64]
    sun_fraction: NDArray[np.float64]
    earth_fraction: NDArray[np.float64]
    sun_clearance_rad: NDArray[np.float64]
    earth_clearance_rad: NDArray[np.float64]


def visibility(
    track: SkyTrack, profile: HorizonProfile, strips: int = DEFAULT_STRIPS
) -> Visibility:
    """Visibility of the Sun and the Earth for a sky track and the horizon of the same site."""
    if abs(track.lat_rad - profile.lat_rad) > 1e-9 or (
        abs(np.angle(np.exp(1j * (track.lon_east_rad - profile.lon_east_rad)))) > 1e-9
    ):
        raise ValueError("the sky track and the horizon profile belong to different sites")
    return Visibility(
        times_utc=track.times_utc,
        sun_fraction=disc_fraction(track.sun, profile, strips),
        earth_fraction=disc_fraction(track.earth, profile, strips),
        sun_clearance_rad=centre_clearance(track.sun, profile),
        earth_clearance_rad=centre_clearance(track.earth, profile),
    )


def site_visibility(
    profile: HorizonProfile, centre: CentreEphemeris, strips: int = DEFAULT_STRIPS
) -> Visibility:
    """Visibility for the observer of a horizon profile (surface height plus mast)."""
    track = sky_track(
        profile.lat_rad,
        profile.lon_east_rad,
        profile.ground_height_m + profile.mast_height_m,
        centre,
    )
    return visibility(track, profile, strips)


def time_step_hours(times_utc: NDArray[np.datetime64]) -> float:
    """Step of a uniformly sampled time series in hours; raises if it is not uniform."""
    times = np.asarray(times_utc)
    if times.size < 2:
        raise ValueError("at least two time steps are needed")
    steps = np.diff(times) / _HOUR
    if not np.allclose(steps, steps[0], rtol=0.0, atol=1e-6) or steps[0] <= 0:
        raise ValueError("times must be uniformly spaced and increasing")
    return float(steps[0])


def runs(mask: ArrayLike) -> list[tuple[int, int]]:
    """Runs of consecutive True values as (first index, index after the last)."""
    flags = np.asarray(mask, dtype=bool)
    if flags.size == 0:
        return []
    padded = np.concatenate([[False], flags, [False]]).astype(np.int8)
    change = np.diff(padded)
    starts = np.flatnonzero(change == 1)
    stops = np.flatnonzero(change == -1)
    return list(zip(starts.tolist(), stops.tolist()))


@dataclass(frozen=True)
class LongestRun:
    """Longest uninterrupted run of a condition inside a window."""

    hours: float
    start_utc: str | None
    #: True when the run touches the first or the last sample of the window: the real
    #: night or gap may be longer than the reported value.
    reaches_window_edge: bool


def longest_run(mask: ArrayLike, times_utc: NDArray[np.datetime64]) -> LongestRun:
    """Longest run of True values; its duration is the number of samples times the step."""
    flags = np.asarray(mask, dtype=bool)
    found = runs(flags)
    if not found:
        return LongestRun(0.0, None, False)
    step_h = time_step_hours(times_utc)
    start, stop = max(found, key=lambda run: run[1] - run[0])
    return LongestRun(
        hours=(stop - start) * step_h,
        start_utc=str(np.datetime_as_string(times_utc[start], unit="m")),
        reaches_window_edge=bool(start == 0 or stop == flags.size),
    )


@dataclass(frozen=True)
class WindowMetrics:
    """Statistics of one site, one observer height and one window of dates.

    Percentages are fractions of the time steps in the window.
    """

    start_utc: str
    stop_utc: str
    step_hours: float
    samples: int
    #: Rule used for "Sun": disc fraction must exceed this value.
    sun_min_fraction: float
    #: Rule used for "Earth": centre must clear the terrain horizon by this margin (deg).
    earth_margin_deg: float
    sunlit_pct: float
    mean_sun_fraction_pct: float
    earth_pct: float
    earth_any_part_pct: float
    sun_and_earth_pct: float
    longest_night: LongestRun
    longest_earth_gap: LongestRun

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def window_metrics(
    vis: Visibility,
    start_utc: str | np.datetime64 | None = None,
    stop_utc: str | np.datetime64 | None = None,
    *,
    sun_min_fraction: float = 0.0,
    earth_margin_rad: float = 0.0,
) -> WindowMetrics:
    """Statistics of a visibility series inside ``[start_utc, stop_utc)``.

    Parameters
    ----------
    sun_min_fraction:
        The site counts as sunlit when the visible fraction of the solar disc is larger
        than this value. The default 0 means "any part of the disc", the definition of
        the published LOLA illumination maps.
    earth_margin_rad:
        The Earth counts as visible when its centre is above the terrain horizon by more
        than this margin. ``earth_any_part_pct`` is reported in addition and uses "any
        part of the disc", the definition of the published LOLA Earth-visibility maps.
    """
    if not 0.0 <= sun_min_fraction < 1.0:
        raise ValueError("sun_min_fraction must be in [0, 1)")
    times = np.asarray(vis.times_utc)
    step_h = time_step_hours(times)
    step = np.timedelta64(round(step_h * 3600), "s")
    selected = np.ones(times.size, dtype=bool)
    # A window that sticks out of the series would silently describe a shorter period.
    if start_utc is not None:
        if np.datetime64(start_utc) < times[0]:
            raise ValueError(f"window starts before the series ({times[0]})")
        selected &= times >= np.datetime64(start_utc)
    if stop_utc is not None:
        if np.datetime64(stop_utc) > times[-1] + step:
            raise ValueError(f"window ends after the series ({times[-1] + step})")
        selected &= times < np.datetime64(stop_utc)
    times = times[selected]
    if times.size < 2:
        raise ValueError("the window contains fewer than two time steps")

    sun_fraction = vis.sun_fraction[selected]
    sunlit = sun_fraction > sun_min_fraction
    earth = vis.earth_clearance_rad[selected] > earth_margin_rad
    earth_any = vis.earth_fraction[selected] > 0.0

    def percent(flags: NDArray[np.bool_]) -> float:
        return float(100.0 * np.count_nonzero(flags) / flags.size)

    return WindowMetrics(
        start_utc=str(np.datetime_as_string(times[0], unit="m")),
        stop_utc=str(np.datetime_as_string(times[-1] + step, unit="m")),
        step_hours=step_h,
        samples=int(times.size),
        sun_min_fraction=float(sun_min_fraction),
        earth_margin_deg=float(np.rad2deg(earth_margin_rad)),
        sunlit_pct=percent(sunlit),
        mean_sun_fraction_pct=float(100.0 * sun_fraction.mean()),
        earth_pct=percent(earth),
        earth_any_part_pct=percent(earth_any),
        sun_and_earth_pct=percent(sunlit & earth),
        longest_night=longest_run(~sunlit, times),
        longest_earth_gap=longest_run(~earth, times),
    )

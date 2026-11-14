"""Mast-height trade-off: what a taller mast buys in light, link time and battery size.

For one site the terrain horizon is known for several observer heights
(``lunarnav.horizon``, cached by ``pipeline/build_horizons.py``). For each height this
module recomputes the visibility of the Sun and the Earth (``lunarnav.visibility``), the
contact windows (``lunarnav.comms``) and the battery simulation (``lunarnav.power``) and
collects one row of a table.

What the mast carries (panel, antenna or both) is an engineering input. Equipment that is
not on the mast is taken at the lowest height of the list, 0 m by default
(docs/ASSUMPTIONS.md, A19).

Not part of the result: the mass, cost and deployment risk of the mast itself and the
shadow it casts. The table gives the battery mass that a height saves; the engineer has to
weigh it against the mast. "The gain levels off" is a description of the computed table
for the listed heights only (A20), not an optimum.

Two steps, so that an app can keep the expensive part while power parameters change:
:func:`observer_series` (sky track and visibility per height, needs the horizons and the
centre ephemeris) and :func:`tradeoff_table` (power and link statistics, fast).
:func:`mast_tradeoff` does both.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray

from lunarnav.comms import CommSettings, comm_summary, link_mask
from lunarnav.ephemeris import CentreEphemeris, SkyTrack, sky_track
from lunarnav.horizon import HorizonProfile
from lunarnav.inputs import EngineeringValue, load_engineering_inputs
from lunarnav.power import PowerSystem, generation_from_track, required_capacity_wh, simulate
from lunarnav.visibility import Visibility, time_step_hours, visibility, window_metrics

#: Heights compared when ``mast_heights_m`` in docs/ENGINEERING_INPUTS.md is empty (task T10).
DEFAULT_MAST_HEIGHTS_M = (0.0, 2.0, 5.0, 10.0, 20.0)
#: Lowest observer height whose horizon we consider physically meaningful (A7): at 0 m the
#: horizon is set by pixel-level slopes of the terrain model.
MIN_MEANINGFUL_HEIGHT_M = 2.0
#: "The gain levels off" at the lowest height that gives this share of the best gain (A20).
LEVELLING_SHARE = 0.9

CARRIES_BOTH = "both"
CARRIES_PANELS = "panels"
CARRIES_ANTENNA = "antenna"
CARRIES = (CARRIES_BOTH, CARRIES_PANELS, CARRIES_ANTENNA)

#: Columns of the trade-off table, in order.
COLUMNS = (
    "mast_height_m",
    "sunlit_pct",
    "mean_sun_fraction_pct",
    "longest_night_h",
    "longest_night_start_utc",
    "longest_night_at_window_edge",
    "mean_generation_w",
    "earth_pct",
    "longest_earth_gap_h",
    "longest_earth_gap_at_window_edge",
    "sun_and_earth_pct",
    "required_capacity_wh",
    "required_battery_mass_kg",
    "survives_with_given_battery",
    "min_soc_pct_with_given_battery",
)

#: Columns used for the "gain levels off" conclusion, with True where lower is better.
TRADEOFF_METRICS: dict[str, bool] = {
    "sunlit_pct": False,
    "mean_sun_fraction_pct": False,
    "longest_night_h": True,
    "required_capacity_wh": True,
    "earth_pct": False,
    "longest_earth_gap_h": True,
}


@dataclass(frozen=True)
class MastSettings:
    """Heights to compare (sorted, metres) and what the mast carries."""

    heights_m: tuple[float, ...] = DEFAULT_MAST_HEIGHTS_M
    carries: str = CARRIES_BOTH

    def __post_init__(self) -> None:
        heights = tuple(float(height) for height in self.heights_m)
        if not heights:
            raise ValueError("at least one mast height is required")
        if not all(np.isfinite(heights)) or min(heights) < 0.0:
            raise ValueError("mast heights must be finite and >= 0")
        if len(set(heights)) != len(heights):
            raise ValueError("mast heights must not repeat")
        if self.carries not in CARRIES:
            raise ValueError(f"carries must be one of {CARRIES}")
        object.__setattr__(self, "heights_m", tuple(sorted(heights)))


#: Word stems (start of a word) that name the panel or the antenna, and words for "both".
_PANEL_STEMS = ("панел", "солнеч", "panel", "solar")
_ANTENNA_STEMS = ("антен", "antenna")
_BOTH_WORDS = {"оба", "обе", "both"}
#: Connecting words that may stand next to them. Any other word (a place such as "на
#: корпусе", a negation such as "без") makes the cell ambiguous, so it is refused.
_FILLER_WORDS = {
    "и", "то", "другое", "только", "на", "мачте", "мачта", "батареи", "батарея", "батарей",
    "and", "only", "the", "a", "on", "top", "of", "mast", "array", "arrays",
}


def _carries_from_text(raw: str) -> str:
    """What the mast carries, from a free-text cell; anything ambiguous is refused.

    Understood: words for the panel, the antenna and "both" plus a few connecting words,
    e.g. "панели", "только антенна", "и то и другое", "solar panels and antenna". Text that
    says where the other item is ("антенна на корпусе, панели на мачте") is refused.
    """
    text = raw.strip().lower()
    if text in CARRIES:
        return text
    words = re.findall(r"\w+", text)
    panel = any(word.startswith(_PANEL_STEMS) for word in words)
    antenna = any(word.startswith(_ANTENNA_STEMS) for word in words)
    both = bool(_BOTH_WORDS.intersection(words)) or {"то", "другое"} <= set(words)
    understood = all(
        word.startswith(_PANEL_STEMS + _ANTENNA_STEMS) or word in _BOTH_WORDS or word in _FILLER_WORDS
        for word in words
    )
    if understood:
        if both or (panel and antenna):
            return CARRIES_BOTH
        if panel:
            return CARRIES_PANELS
        if antenna:
            return CARRIES_ANTENNA
    raise ValueError(
        f"mast_carries: cannot interpret '{raw}'; write one of: "
        "панели (panels), антенна (antenna), и то и другое (both)"
    )


def default_mast_settings(
    inputs: Mapping[str, EngineeringValue] | None = None,
) -> tuple[MastSettings, tuple[str, ...]]:
    """Settings from docs/ENGINEERING_INPUTS.md and the keys that are still placeholders."""
    if inputs is None:
        inputs = load_engineering_inputs()
    keys = ("mast_heights_m", "mast_carries")
    placeholders = tuple(key for key in keys if key not in inputs)
    heights = tuple(inputs[keys[0]].numbers()) if keys[0] in inputs else DEFAULT_MAST_HEIGHTS_M
    carries = _carries_from_text(inputs[keys[1]].raw) if keys[1] in inputs else CARRIES_BOTH
    return MastSettings(heights, carries), placeholders


# --- per-height series ---------------------------------------------------------------------


@dataclass(frozen=True)
class ObserverSeries:
    """Sky track and visibility of one observer height over one window of dates."""

    mast_height_m: float
    track: SkyTrack
    vis: Visibility


def _window_mask(
    times: NDArray[np.datetime64],
    start_utc: str | np.datetime64 | None,
    stop_utc: str | np.datetime64 | None,
) -> NDArray[np.bool_]:
    """Time steps inside ``[start_utc, stop_utc)``; a window outside the series is an error."""
    step = np.timedelta64(round(time_step_hours(times) * 3600), "s")
    selected = np.ones(times.size, dtype=bool)
    if start_utc is not None:
        if np.datetime64(start_utc) < times[0]:
            raise ValueError(f"window starts before the series ({times[0]})")
        selected &= times >= np.datetime64(start_utc)
    if stop_utc is not None:
        if np.datetime64(stop_utc) > times[-1] + step:
            raise ValueError(f"window ends after the series ({times[-1] + step})")
        selected &= times < np.datetime64(stop_utc)
    if np.count_nonzero(selected) < 2:
        raise ValueError("the window contains fewer than two time steps")
    return selected


def _centre_subset(centre: CentreEphemeris, selected: NDArray[np.bool_]) -> CentreEphemeris:
    return CentreEphemeris(
        times_utc=centre.times_utc[selected],
        et_s=centre.et_s[selected],
        sun_m=centre.sun_m[selected],
        earth_m=centre.earth_m[selected],
        sun_radius_m=centre.sun_radius_m,
        earth_radius_m=centre.earth_radius_m,
    )


def observer_series(
    profiles: Sequence[HorizonProfile],
    centre: CentreEphemeris,
    start_utc: str | np.datetime64 | None = None,
    stop_utc: str | np.datetime64 | None = None,
) -> list[ObserverSeries]:
    """Sky track and visibility for every horizon profile, sorted by mast height.

    ``profiles`` are horizons of the same site for different mast heights. The window is
    ``[start_utc, stop_utc)`` inside the times of ``centre`` (default: all of them).
    """
    if not profiles:
        raise ValueError("at least one horizon profile is required")
    first = profiles[0]
    for profile in profiles[1:]:
        lon_difference = abs(np.angle(np.exp(1j * (profile.lon_east_rad - first.lon_east_rad))))
        if abs(profile.lat_rad - first.lat_rad) > 1e-9 or lon_difference > 1e-9:
            raise ValueError("all profiles must belong to the same site")
    heights = [profile.mast_height_m for profile in profiles]
    if len(set(heights)) != len(heights):
        raise ValueError("each mast height may appear only once")
    window = _centre_subset(centre, _window_mask(np.asarray(centre.times_utc), start_utc, stop_utc))
    result = []
    for profile in sorted(profiles, key=lambda item: item.mast_height_m):
        track = sky_track(
            profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m, window
        )
        result.append(ObserverSeries(profile.mast_height_m, track, visibility(track, profile)))
    return result


# --- trade-off table -----------------------------------------------------------------------


def tradeoff_table(
    series: Sequence[ObserverSeries],
    system: PowerSystem,
    comm: CommSettings = CommSettings(),
    carries: str = CARRIES_BOTH,
) -> pd.DataFrame:
    """One row per mast height (columns :data:`COLUMNS`).

    The panel sees the Sun from the mast height when the mast carries it, otherwise from
    the lowest height in ``series``; the same holds for the antenna and the Earth.
    ``required_capacity_wh`` is the smallest battery that survives the whole series with
    the other parameters of ``system``; ``survives_with_given_battery`` uses the capacity
    of ``system`` itself. Percentages are shares of the time steps.
    """
    if not series:
        raise ValueError("at least one observer series is required")
    if carries not in CARRIES:
        raise ValueError(f"carries must be one of {CARRIES}")
    ordered = sorted(series, key=lambda item: item.mast_height_m)
    times = np.asarray(ordered[0].track.times_utc)
    for item in ordered[1:]:
        if not np.array_equal(np.asarray(item.track.times_utc), times):
            raise ValueError("all observer series must cover the same times")
    lowest = ordered[0]
    specific = system.battery_specific_energy_wh_per_kg

    rows = []
    for item in ordered:
        panel = item if carries in (CARRIES_BOTH, CARRIES_PANELS) else lowest
        antenna = item if carries in (CARRIES_BOTH, CARRIES_ANTENNA) else lowest
        metrics = window_metrics(panel.vis)
        sun_fraction = panel.vis.sun_fraction
        link = link_mask(antenna.vis, antenna.track.earth.angular_radius_rad, comm)
        link_summary = comm_summary(link, times, comm)
        generation = generation_from_track(system, panel.track.sun, sun_fraction)
        result = simulate(system, times, generation, sun_fraction)
        needed = required_capacity_wh(system, times, generation, sun_fraction)
        rows.append(
            {
                "mast_height_m": item.mast_height_m,
                "sunlit_pct": metrics.sunlit_pct,
                "mean_sun_fraction_pct": metrics.mean_sun_fraction_pct,
                "longest_night_h": metrics.longest_night.hours,
                "longest_night_start_utc": metrics.longest_night.start_utc,
                "longest_night_at_window_edge": metrics.longest_night.reaches_window_edge,
                "mean_generation_w": float(generation.mean()),
                "earth_pct": link_summary.visible_pct,
                "longest_earth_gap_h": link_summary.longest_gap_h,
                "longest_earth_gap_at_window_edge": link_summary.longest_gap_reaches_period_edge,
                "sun_and_earth_pct": float(100.0 * np.count_nonzero((sun_fraction > 0.0) & link) / link.size),
                "required_capacity_wh": needed,
                "required_battery_mass_kg": needed / specific if specific else np.nan,
                "survives_with_given_battery": result.survives,
                "min_soc_pct_with_given_battery": 100.0 * result.min_soc,
            }
        )
    return pd.DataFrame(rows, columns=list(COLUMNS))


def mast_tradeoff(
    profiles: Sequence[HorizonProfile],
    centre: CentreEphemeris,
    system: PowerSystem,
    comm: CommSettings = CommSettings(),
    start_utc: str | np.datetime64 | None = None,
    stop_utc: str | np.datetime64 | None = None,
    carries: str = CARRIES_BOTH,
) -> pd.DataFrame:
    """:func:`observer_series` followed by :func:`tradeoff_table`."""
    return tradeoff_table(observer_series(profiles, centre, start_utc, stop_utc), system, comm, carries)


# --- where the gain levels off -------------------------------------------------------------


def diminishing_returns_height(
    heights_m: ArrayLike,
    values: ArrayLike,
    *,
    lower_is_better: bool = False,
    share: float = LEVELLING_SHARE,
) -> float | None:
    """Smallest height that already gives ``share`` of the best improvement over the lowest height.

    The improvement is measured against the value at the lowest height in ``heights_m``;
    the best improvement is the largest one among the given heights. Returns None when no
    height improves on the lowest one by more than rounding noise (1e-9 of the largest
    finite value), when the lowest height has no finite value, or when the best gain is
    infinite. A NaN at another height counts as no gain there. This is a description of
    the computed table, not an optimum: the cost of the mast is not included.
    """
    if not 0.0 < share <= 1.0:
        raise ValueError("share must be within (0, 1]")
    heights = np.asarray(heights_m, dtype=np.float64)
    data = np.asarray(values, dtype=np.float64)
    if heights.shape != data.shape or heights.ndim != 1 or heights.size < 2:
        raise ValueError("heights_m and values must be 1-D arrays of the same length (at least 2)")
    order = np.argsort(heights)
    heights, data = heights[order], data[order]
    with np.errstate(invalid="ignore"):  # inf - inf gives NaN: no gain
        gain = (data[0] - data) if lower_is_better else (data - data[0])
    gain = np.where(np.isnan(gain), -np.inf, gain)
    best = float(gain.max())
    finite = np.abs(data[np.isfinite(data)])
    tolerance = 1e-9 * (float(finite.max()) if finite.size and finite.max() > 0 else 1.0)
    if not np.isfinite(best) or best <= tolerance:
        return None
    reached = np.flatnonzero(gain >= share * best - tolerance)
    return float(heights[reached[0]])


def levelling_off_heights(
    table: pd.DataFrame,
    *,
    min_height_m: float = MIN_MEANINGFUL_HEIGHT_M,
    share: float = LEVELLING_SHARE,
) -> dict[str, float | None]:
    """:func:`diminishing_returns_height` of every column in :data:`TRADEOFF_METRICS`.

    Only rows at or above ``min_height_m`` are used, so the gain is counted from the lowest
    meaningful height (A7). None means no gain, or fewer than two such rows.
    """
    rows = table[table["mast_height_m"] >= min_height_m]
    if len(rows) < 2:
        return dict.fromkeys(TRADEOFF_METRICS)
    return {
        column: diminishing_returns_height(
            rows["mast_height_m"], rows[column], lower_is_better=lower_is_better, share=share
        )
        for column, lower_is_better in TRADEOFF_METRICS.items()
    }

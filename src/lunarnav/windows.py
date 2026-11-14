"""Landing-date search: on which landing dates a lander survives a mission of given length.

For one site and one observer height the mission lasts ``duration`` from the landing time.
For every landing time (one per day by default) the battery starts at its initial state of
charge (full by default) and the power model (``lunarnav.power``) runs through the mission;
the table also gives the shares of the mission with the Sun, with the Earth link
(``lunarnav.comms``) and with both.

The best dates are ranked by (1) survival, (2) the lowest state of charge during the
mission, i.e. the energy margin, (3) the share of time with the Earth link, and are picked so
that their missions do not overlap (docs/ASSUMPTIONS.md, A22). A visible Sun is not yet
power and a visible Earth is not yet a link; the power-system placeholders apply (A14).

Times are UTC, durations hours. The series must be uniformly sampled; landing times and
the mission length must be whole multiples of its step.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray

from lunarnav.comms import CommSettings, link_mask
from lunarnav.ephemeris import SkyTrack
from lunarnav.inputs import EngineeringValue, load_engineering_inputs
from lunarnav.power import PowerSystem, generation_from_track, required_capacity_wh, simulate
from lunarnav.visibility import Visibility, longest_run, time_step_hours

#: Mission length when ``mission_duration_days`` in docs/ENGINEERING_INPUTS.md is empty (task T11).
DEFAULT_MISSION_DAYS = 14.0

#: Columns of the landing table, in order.
COLUMNS = (
    "landing_utc",
    "end_utc",
    "survives",
    "min_soc_pct",
    "min_soc_utc",
    "first_violation_utc",
    "sunlit_pct",
    "mean_sun_fraction_pct",
    "longest_night_h",
    "earth_pct",
    "longest_earth_gap_h",
    "sun_and_earth_pct",
    "required_capacity_wh",
)


def default_mission_days(
    inputs: Mapping[str, EngineeringValue] | None = None,
) -> tuple[float, tuple[str, ...]]:
    """Mission length in days from docs/ENGINEERING_INPUTS.md and the keys still placeholders."""
    if inputs is None:
        inputs = load_engineering_inputs()
    key = "mission_duration_days"
    if key not in inputs:
        return DEFAULT_MISSION_DAYS, (key,)
    days = inputs[key].number()
    if not np.isfinite(days) or days <= 0:
        raise ValueError(f"{key} must be a positive number of days")
    return days, ()


def _whole_steps(hours: float, step_h: float, name: str, minimum: int = 1) -> int:
    count = hours / step_h
    if not np.isfinite(count) or count < minimum - 1e-9 or abs(count - round(count)) > 1e-9:
        raise ValueError(
            f"{name} ({hours} h) must be a whole number of time steps ({step_h} h), at least {minimum}"
        )
    return int(round(count))


def _index_of(times: NDArray[np.datetime64], value: str | np.datetime64, name: str) -> int:
    moment = np.datetime64(value)
    index = int(np.searchsorted(times, moment))
    if index >= times.size or times[index] != moment:
        raise ValueError(f"{name} {value} is not one of the times of the series")
    return index


def landing_table(
    times_utc: NDArray[np.datetime64],
    sun_fraction: ArrayLike,
    generation_w: ArrayLike,
    link: ArrayLike,
    system: PowerSystem,
    *,
    duration_h: float,
    landing_step_h: float = 24.0,
    first_landing_utc: str | np.datetime64 | None = None,
    last_landing_utc: str | np.datetime64 | None = None,
) -> pd.DataFrame:
    """One row per landing time (columns :data:`COLUMNS`).

    ``sun_fraction``, ``generation_w`` (W) and ``link`` (Earth link mask) hold one value per
    time step. A landing at ``t`` uses the steps in ``[t, t + duration_h)``; the series must
    cover them. Landing times run from ``first_landing_utc`` (default: the first time) to
    ``last_landing_utc`` (default: the last time whose mission fits), every
    ``landing_step_h``. A mission has at least two time steps. ``required_capacity_wh`` is the
    smallest battery that survives that mission with the other parameters of ``system``.
    ``longest_night_h`` and ``longest_earth_gap_h`` count only the part inside the mission: a
    night that started before the landing is cut at the landing time.
    """
    times = np.asarray(times_utc)
    fraction = np.asarray(sun_fraction, dtype=np.float64)
    generation = np.asarray(generation_w, dtype=np.float64)
    flags = np.asarray(link, dtype=bool)
    if not (times.shape == fraction.shape == generation.shape == flags.shape) or times.ndim != 1:
        raise ValueError("times_utc, sun_fraction, generation_w and link must be 1-D arrays of the same length")
    step_h = time_step_hours(times)
    mission_steps = _whole_steps(duration_h, step_h, "duration_h", minimum=2)
    stride = _whole_steps(landing_step_h, step_h, "landing_step_h")
    last_possible = times.size - mission_steps
    if last_possible < 0:
        raise ValueError("the series is shorter than one mission")
    first = 0 if first_landing_utc is None else _index_of(times, first_landing_utc, "first_landing_utc")
    last = last_possible if last_landing_utc is None else _index_of(times, last_landing_utc, "last_landing_utc")
    if last > last_possible:
        raise ValueError(f"the mission landing at {times[last]} ends after the series ({times[-1]})")
    if first > last:
        raise ValueError("no landing time between first_landing_utc and last_landing_utc")
    step = np.timedelta64(round(step_h * 3600), "s")

    rows = []
    for start in range(first, last + 1, stride):
        window = slice(start, start + mission_steps)
        mission_times = times[window]
        mission_fraction = fraction[window]
        mission_generation = generation[window]
        mission_link = flags[window]
        result = simulate(system, mission_times, mission_generation, mission_fraction)
        sunlit = mission_fraction > 0.0
        rows.append(
            {
                "landing_utc": mission_times[0],
                "end_utc": mission_times[-1] + step,
                "survives": result.survives,
                "min_soc_pct": 100.0 * result.min_soc,
                "min_soc_utc": result.min_energy_utc,
                "first_violation_utc": result.first_violation_utc,
                "sunlit_pct": float(100.0 * np.mean(sunlit)),
                "mean_sun_fraction_pct": float(100.0 * np.mean(mission_fraction)),
                "longest_night_h": longest_run(~sunlit, mission_times).hours,
                "earth_pct": float(100.0 * np.mean(mission_link)),
                "longest_earth_gap_h": longest_run(~mission_link, mission_times).hours,
                "sun_and_earth_pct": float(100.0 * np.mean(sunlit & mission_link)),
                "required_capacity_wh": required_capacity_wh(
                    system, mission_times, mission_generation, mission_fraction
                ),
            }
        )
    table = pd.DataFrame(rows, columns=list(COLUMNS))
    for column in ("landing_utc", "end_utc"):
        table[column] = pd.to_datetime(table[column])
    return table


def landing_windows(
    track: SkyTrack,
    vis: Visibility,
    system: PowerSystem,
    comm: CommSettings = CommSettings(),
    *,
    duration_h: float,
    landing_step_h: float = 24.0,
    first_landing_utc: str | np.datetime64 | None = None,
    last_landing_utc: str | np.datetime64 | None = None,
) -> pd.DataFrame:
    """:func:`landing_table` for a sky track and the visibility of the same observer."""
    if not np.array_equal(np.asarray(track.times_utc), np.asarray(vis.times_utc)):
        raise ValueError("the sky track and the visibility must cover the same times")
    generation = generation_from_track(system, track.sun, vis.sun_fraction)
    link = link_mask(vis, track.earth.angular_radius_rad, comm)
    return landing_table(
        track.times_utc,
        vis.sun_fraction,
        generation,
        link,
        system,
        duration_h=duration_h,
        landing_step_h=landing_step_h,
        first_landing_utc=first_landing_utc,
        last_landing_utc=last_landing_utc,
    )


def best_landing_dates(
    table: pd.DataFrame, count: int = 5, min_separation_h: float | None = None
) -> pd.DataFrame:
    """Up to ``count`` rows of a landing table, best first, with a ``rank`` column from 1.

    Ranking (A22): surviving missions first, then the highest lowest state of charge, then
    the largest share of time with the Earth link, then the earlier date. Percentages are
    compared after rounding to 1e-6, so rounding noise does not hide a tie. Rows are taken
    from the top down and a date closer than ``min_separation_h`` to one already taken is
    skipped; the default separation is the mission length, so the missions do not overlap.
    The rows keep their content; the index of the result is new (0, 1, ...).
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    table = table.reset_index(drop=True)
    if table.empty:
        return table.assign(rank=pd.Series(dtype=np.int64))[["rank", *table.columns]]
    if min_separation_h is None:
        separation = (table["end_utc"] - table["landing_utc"]).max()
    else:
        if min_separation_h < 0:
            raise ValueError("min_separation_h must be >= 0")
        separation = pd.Timedelta(hours=min_separation_h)
    keys = pd.DataFrame(
        {
            "survives": table["survives"].astype(bool),
            "margin": table["min_soc_pct"].round(6),
            "earth": table["earth_pct"].round(6),
            "landing": table["landing_utc"],
        }
    )
    ordered = keys.sort_values(
        ["survives", "margin", "earth", "landing"], ascending=[False, False, False, True], kind="mergesort"
    )
    taken: list[int] = []
    for position, landing in zip(ordered.index, ordered["landing"]):
        if all(abs(landing - table.at[other, "landing_utc"]) >= separation for other in taken):
            taken.append(position)
            if len(taken) == count:
                break
    best = table.loc[taken].reset_index(drop=True)
    best.insert(0, "rank", np.arange(1, len(best) + 1))
    return best

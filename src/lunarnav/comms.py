"""Direct-to-Earth communication windows and a simple link budget.

A window is an uninterrupted period in which the Earth is in line of sight above the
terrain horizon according to a visibility rule:

* ``centre``: the centre of the Earth's disc is above the horizon by more than the margin;
* ``full_disc``: the whole disc is visible and its lowest point clears the horizon at the
  centre azimuth by more than the margin;
* ``any_part``: any part of the disc is visible and its highest point clears the horizon
  at the centre azimuth by more than the margin.

Line of sight to the Earth is necessary for a direct link but not sufficient: a ground
station must also see the Moon and the link must close. Which station is in view is not
modelled; the optional link budget below only checks the power balance for a given set
of radio parameters. Relay satellites are not considered.

Rule and margin come from docs/ENGINEERING_INPUTS.md; while those rows are empty the
placeholder is the ``centre`` rule with a margin of 0 deg (docs/ASSUMPTIONS.md, A12).

Angles are radians, times UTC, durations hours (counted in whole time steps).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray

from lunarnav.inputs import EngineeringValue, load_engineering_inputs
from lunarnav.visibility import Visibility, runs, time_step_hours

RULE_CENTRE = "centre"
RULE_FULL_DISC = "full_disc"
RULE_ANY_PART = "any_part"
RULES = (RULE_CENTRE, RULE_FULL_DISC, RULE_ANY_PART)

#: Speed of light, m/s (exact, SI definition).
SPEED_OF_LIGHT_M_S = 299_792_458.0
#: Boltzmann constant, J/K (exact, SI definition of 2019).
BOLTZMANN_J_K = 1.380649e-23

_FULL = 1.0 - 1e-9


@dataclass(frozen=True)
class CommSettings:
    """Rule that decides when the Earth counts as visible for a link."""

    rule: str = RULE_CENTRE
    margin_rad: float = 0.0

    def __post_init__(self) -> None:
        if self.rule not in RULES:
            raise ValueError(f"rule must be one of {RULES}")
        if not np.isfinite(self.margin_rad) or self.margin_rad < 0.0:
            raise ValueError("margin_rad must be finite and >= 0")


_RULE_WORDS = {
    RULE_CENTRE: ("центр", "centre", "center"),
    RULE_FULL_DISC: ("весь", "вся", "целиком", "полност", "full", "whole"),
    RULE_ANY_PART: ("люб", "any"),
}
_NEGATION = re.compile(r"\b(?:не|нет|not|no)\b")


def _rule_from_text(raw: str) -> str:
    """Rule named by a free-text cell; anything ambiguous is refused instead of guessed."""
    text = raw.strip().lower()
    if text in RULES:
        return text
    matches = [rule for rule, words in _RULE_WORDS.items() if any(word in text for word in words)]
    if len(matches) != 1 or _NEGATION.search(text):
        raise ValueError(
            f"comm_earth_disk_rule: cannot interpret '{raw}'; write one of: "
            "центр диска (centre), весь диск (full_disc), любая часть диска (any_part)"
        )
    return matches[0]


def default_comm_settings(
    inputs: Mapping[str, EngineeringValue] | None = None,
) -> tuple[CommSettings, tuple[str, ...]]:
    """Settings from docs/ENGINEERING_INPUTS.md and the keys that are still placeholders."""
    if inputs is None:
        inputs = load_engineering_inputs()
    keys = ("comm_earth_disk_rule", "comm_elevation_margin_deg")
    placeholders = tuple(key for key in keys if key not in inputs)
    rule = _rule_from_text(inputs[keys[0]].raw) if keys[0] in inputs else RULE_CENTRE
    margin_deg = inputs[keys[1]].number() if keys[1] in inputs else 0.0
    return CommSettings(rule, float(np.deg2rad(margin_deg))), placeholders


def link_mask(
    vis: Visibility, earth_angular_radius_rad: ArrayLike, settings: CommSettings = CommSettings()
) -> NDArray[np.bool_]:
    """True for the time steps in which the Earth is visible according to the settings."""
    clearance = np.asarray(vis.earth_clearance_rad, dtype=np.float64)
    radius = np.broadcast_to(np.asarray(earth_angular_radius_rad, dtype=np.float64), clearance.shape)
    if settings.rule == RULE_CENTRE:
        return clearance > settings.margin_rad
    if settings.rule == RULE_FULL_DISC:
        return (vis.earth_fraction >= _FULL) & (clearance - radius > settings.margin_rad)
    return (vis.earth_fraction > 0.0) & (clearance + radius > settings.margin_rad)


@dataclass(frozen=True)
class Interval:
    """A contact window or a gap between windows."""

    start_utc: np.datetime64
    end_utc: np.datetime64
    hours: float
    #: True when the interval touches the start or the end of the analysed period, so
    #: its real duration may be longer.
    reaches_period_edge: bool


def intervals(mask: ArrayLike, times_utc: NDArray[np.datetime64]) -> list[Interval]:
    """Uninterrupted runs of True in a uniformly sampled mask.

    A run of n samples lasts n time steps: it starts at its first sample and ends one
    step after its last sample.
    """
    flags = np.asarray(mask, dtype=bool)
    times = np.asarray(times_utc)
    if flags.shape != times.shape or flags.ndim != 1:
        raise ValueError("mask and times_utc must be 1-D arrays of the same length")
    step_h = time_step_hours(times)
    step = np.timedelta64(round(step_h * 3600), "s")
    return [
        Interval(
            start_utc=times[start],
            end_utc=times[stop - 1] + step,
            hours=(stop - start) * step_h,
            reaches_period_edge=bool(start == 0 or stop == flags.size),
        )
        for start, stop in runs(flags)
    ]


def contact_windows(mask: ArrayLike, times_utc: NDArray[np.datetime64]) -> list[Interval]:
    """Periods with the Earth visible."""
    return intervals(mask, times_utc)


def contact_gaps(mask: ArrayLike, times_utc: NDArray[np.datetime64]) -> list[Interval]:
    """Periods without the Earth."""
    return intervals(~np.asarray(mask, dtype=bool), times_utc)


def intervals_table(items: list[Interval]) -> pd.DataFrame:
    """Intervals as a table with the columns start_utc, end_utc, hours, reaches_period_edge."""
    return pd.DataFrame(
        {
            "start_utc": pd.to_datetime([item.start_utc for item in items]),
            "end_utc": pd.to_datetime([item.end_utc for item in items]),
            "hours": np.array([item.hours for item in items], dtype=np.float64),
            "reaches_period_edge": np.array([item.reaches_period_edge for item in items], dtype=bool),
        }
    )


@dataclass(frozen=True)
class CommSummary:
    """Statistics of the contact windows of one period."""

    rule: str
    margin_deg: float
    period_hours: float
    visible_pct: float
    window_count: int
    longest_window_h: float
    median_window_h: float
    gap_count: int
    longest_gap_h: float
    longest_gap_start_utc: str | None
    #: True when the longest gap touches the period edge (its real length may be larger).
    longest_gap_reaches_period_edge: bool


def comm_summary(
    mask: ArrayLike, times_utc: NDArray[np.datetime64], settings: CommSettings = CommSettings()
) -> CommSummary:
    """Summary of windows and gaps for a link mask."""
    flags = np.asarray(mask, dtype=bool)
    windows = contact_windows(flags, times_utc)
    gaps = contact_gaps(flags, times_utc)
    step_h = time_step_hours(np.asarray(times_utc))
    longest_gap = max(gaps, key=lambda gap: gap.hours) if gaps else None
    return CommSummary(
        rule=settings.rule,
        margin_deg=float(np.rad2deg(settings.margin_rad)),
        period_hours=flags.size * step_h,
        visible_pct=float(100.0 * np.count_nonzero(flags) / flags.size),
        window_count=len(windows),
        longest_window_h=max((window.hours for window in windows), default=0.0),
        median_window_h=float(np.median([window.hours for window in windows])) if windows else 0.0,
        gap_count=len(gaps),
        longest_gap_h=longest_gap.hours if longest_gap else 0.0,
        longest_gap_start_utc=(
            str(np.datetime_as_string(longest_gap.start_utc, unit="m")) if longest_gap else None
        ),
        longest_gap_reaches_period_edge=bool(longest_gap.reaches_period_edge) if longest_gap else False,
    )


# --- link budget ---------------------------------------------------------------------------


def free_space_path_loss_db(distance_m: ArrayLike, frequency_hz: float) -> NDArray[np.float64]:
    """Free-space path loss, dB: 20 log10(4 pi d f / c)."""
    distance = np.asarray(distance_m, dtype=np.float64)
    if frequency_hz <= 0 or np.any(distance <= 0):
        raise ValueError("distance and frequency must be positive")
    return 20.0 * np.log10(4.0 * np.pi * distance * frequency_hz / SPEED_OF_LIGHT_M_S)


@dataclass(frozen=True)
class LinkParameters:
    """Radio parameters of the downlink (lander transmits, ground station receives)."""

    frequency_hz: float
    tx_power_w: float
    tx_antenna_gain_dbi: float
    rx_antenna_gain_dbi: float
    rx_system_noise_temp_k: float
    data_rate_bps: float
    required_ebn0_db: float
    other_losses_db: float = 0.0
    required_margin_db: float = 0.0

    def __post_init__(self) -> None:
        for name in ("frequency_hz", "tx_power_w", "rx_system_noise_temp_k", "data_rate_bps"):
            if not getattr(self, name) > 0:
                raise ValueError(f"{name} must be positive")
        if self.other_losses_db < 0:
            raise ValueError("other_losses_db must be >= 0")


#: Engineering-input keys of the link budget; the first seven are required.
LINK_KEYS = (
    "link_frequency_mhz",
    "link_tx_power_w",
    "link_tx_antenna_gain_dbi",
    "link_rx_antenna_gain_dbi",
    "link_rx_system_noise_temp_k",
    "link_data_rate_bps",
    "link_required_ebn0_db",
    "link_other_losses_db",
    "link_required_margin_db",
)


def link_parameters_from_inputs(
    inputs: Mapping[str, EngineeringValue] | None = None,
) -> LinkParameters | None:
    """Link parameters from docs/ENGINEERING_INPUTS.md, or None while any required row is empty.

    There are no placeholder radio parameters: without the engineer's values no link
    budget is shown.
    """
    if inputs is None:
        inputs = load_engineering_inputs()
    if any(key not in inputs for key in LINK_KEYS[:7]):
        return None
    return LinkParameters(
        frequency_hz=inputs["link_frequency_mhz"].number() * 1e6,
        tx_power_w=inputs["link_tx_power_w"].number(),
        tx_antenna_gain_dbi=inputs["link_tx_antenna_gain_dbi"].number(),
        rx_antenna_gain_dbi=inputs["link_rx_antenna_gain_dbi"].number(),
        rx_system_noise_temp_k=inputs["link_rx_system_noise_temp_k"].number(),
        data_rate_bps=inputs["link_data_rate_bps"].number(),
        required_ebn0_db=inputs["link_required_ebn0_db"].number(),
        other_losses_db=inputs["link_other_losses_db"].number() if "link_other_losses_db" in inputs else 0.0,
        required_margin_db=(
            inputs["link_required_margin_db"].number() if "link_required_margin_db" in inputs else 0.0
        ),
    )


def received_ebn0_db(parameters: LinkParameters, distance_m: ArrayLike) -> NDArray[np.float64]:
    """Eb/N0 at the receiver, dB.

    EIRP + receive gain - path loss - other losses gives the received power; dividing by
    the noise density k T and by the data rate gives the energy per bit over the noise
    density. ``distance_m`` is the range of the link (the ephemeris gives the distance to
    the Earth's centre; a station on the surface is up to one Earth radius closer, which
    changes the result by about 0.15 dB).
    """
    eirp_dbw = 10.0 * np.log10(parameters.tx_power_w) + parameters.tx_antenna_gain_dbi
    received_dbw = (
        eirp_dbw
        + parameters.rx_antenna_gain_dbi
        - free_space_path_loss_db(distance_m, parameters.frequency_hz)
        - parameters.other_losses_db
    )
    noise_density_dbw_hz = 10.0 * np.log10(BOLTZMANN_J_K * parameters.rx_system_noise_temp_k)
    return received_dbw - noise_density_dbw_hz - 10.0 * np.log10(parameters.data_rate_bps)


def link_margin_db(parameters: LinkParameters, distance_m: ArrayLike) -> NDArray[np.float64]:
    """Received Eb/N0 minus the required Eb/N0 and the required margin, dB (>= 0: link closes)."""
    return received_ebn0_db(parameters, distance_m) - parameters.required_ebn0_db - parameters.required_margin_db

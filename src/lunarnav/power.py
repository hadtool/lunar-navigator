"""Energy balance of a lander: solar generation, loads and battery state of charge.

Model
-----
Generation of a flat panel::

    P = S * (1 au / d)^2 * efficiency * (1 - losses) * area * disc_fraction * cos(incidence)

``S`` is the solar constant at 1 au, ``d`` the Sun-site distance, ``disc_fraction`` the
visible share of the solar disc from ``lunarnav.visibility``. Two panel types:

* ``tracking``: a vertical panel that turns about the vertical axis to face the Sun's
  azimuth, cos(incidence) = cos(Sun elevation);
* ``fixed``: a vertical panel facing a fixed azimuth, lit from one side only,
  cos(incidence) = cos(Sun elevation) * cos(Sun azimuth - panel azimuth), never below 0.

Battery: in every time step the power is constant. A surplus charges the battery with
the charge efficiency until it is full (the rest is not used); a deficit is drawn from
the battery and divided by the discharge efficiency. The lander survives the window when
the stored energy never falls below the allowed minimum (1 - depth of discharge).

The load is ``load_day_w`` while the Sun is visible and ``load_night_w`` otherwise.

Not modelled: temperature of the panels and of the battery, heater power as a function of
temperature, panel degradation, shadowing by the lander itself, battery self-discharge,
limits on charge and discharge power. Default numbers are placeholders until the
engineer fills in docs/ENGINEERING_INPUTS.md (docs/ASSUMPTIONS.md).

Units: W, Wh, hours in this module's interface (energy bookkeeping); angles in radians.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import ArrayLike, NDArray

from lunarnav.ephemeris import BodyTrack
from lunarnav.inputs import EngineeringValue, load_engineering_inputs
from lunarnav.visibility import time_step_hours

#: Total solar irradiance at 1 au, W/m2 (Kopp & Lean 2011, see docs/SOURCES.md).
SOLAR_CONSTANT_W_M2 = 1361.0
#: Astronomical unit in metres (IAU 2012 Resolution B2, exact).
AU_M = 149_597_870_700.0

PANEL_TRACKING = "tracking"
PANEL_FIXED = "fixed"

#: Placeholder values used for every key the engineer has not filled in yet. They are
#: round numbers chosen by the programmer, not data of a real lander (docs/ASSUMPTIONS.md).
PLACEHOLDER_INPUTS: dict[str, float | str] = {
    "panel_type": PANEL_TRACKING,
    "panel_area_m2": 1.0,
    "panel_efficiency": 0.30,
    "panel_fixed_azimuth_deg": 0.0,
    "panel_losses": 0.0,
    "battery_capacity_wh": 1000.0,
    "battery_max_dod": 0.8,
    "battery_charge_efficiency": 0.95,
    "battery_discharge_efficiency": 0.95,
    "battery_specific_energy_wh_per_kg": 150.0,
    "battery_initial_soc": 1.0,
    "load_day_w": 100.0,
    "load_night_w": 20.0,
}


@dataclass(frozen=True)
class PowerSystem:
    """Parameters of the power system. Fractions are 0..1, see the module docstring."""

    panel_area_m2: float
    panel_efficiency: float
    battery_capacity_wh: float
    load_day_w: float
    load_night_w: float
    panel_type: str = PANEL_TRACKING
    panel_fixed_azimuth_rad: float = 0.0
    panel_losses: float = 0.0
    battery_max_dod: float = 0.8
    battery_charge_efficiency: float = 1.0
    battery_discharge_efficiency: float = 1.0
    battery_initial_soc: float = 1.0
    battery_specific_energy_wh_per_kg: float | None = None

    def __post_init__(self) -> None:
        if self.panel_type not in (PANEL_TRACKING, PANEL_FIXED):
            raise ValueError(f"panel_type must be '{PANEL_TRACKING}' or '{PANEL_FIXED}'")
        if self.panel_area_m2 < 0 or self.battery_capacity_wh < 0:
            raise ValueError("panel area and battery capacity must be >= 0")
        if self.load_day_w < 0 or self.load_night_w < 0:
            raise ValueError("loads must be >= 0")
        if not 0.0 <= self.panel_efficiency <= 1.0 or not 0.0 <= self.panel_losses <= 1.0:
            raise ValueError("panel efficiency and losses must be within 0..1")
        if not 0.0 < self.battery_max_dod <= 1.0:
            raise ValueError("battery_max_dod must be within (0, 1]")
        for name in ("battery_charge_efficiency", "battery_discharge_efficiency"):
            if not 0.0 < getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be within (0, 1]")
        if not 0.0 <= self.battery_initial_soc <= 1.0:
            raise ValueError("battery_initial_soc must be within 0..1")
        if self.battery_specific_energy_wh_per_kg is not None and self.battery_specific_energy_wh_per_kg <= 0:
            raise ValueError("battery_specific_energy_wh_per_kg must be positive")

    @property
    def battery_min_soc(self) -> float:
        """Lowest allowed state of charge, 1 - depth of discharge."""
        return 1.0 - self.battery_max_dod

    @property
    def battery_mass_kg(self) -> float | None:
        """Battery mass from the specific energy, None when it is not given."""
        if self.battery_specific_energy_wh_per_kg is None:
            return None
        return self.battery_capacity_wh / self.battery_specific_energy_wh_per_kg


def _panel_type(raw: str) -> str:
    text = raw.strip().lower()
    if text in (PANEL_TRACKING, PANEL_FIXED):
        return text
    if "неподвиж" in text or "fixed" in text:
        return PANEL_FIXED
    if "поворот" in text or "track" in text:
        return PANEL_TRACKING
    raise ValueError(f"panel_type: cannot interpret '{raw}'")


def default_power_system(
    inputs: Mapping[str, EngineeringValue] | None = None,
) -> tuple[PowerSystem, tuple[str, ...]]:
    """Power system from docs/ENGINEERING_INPUTS.md and the keys that are still placeholders.

    The second item lists the keys taken from :data:`PLACEHOLDER_INPUTS`; the app shows
    them as placeholders.
    """
    if inputs is None:
        inputs = load_engineering_inputs()
    placeholders = tuple(key for key in PLACEHOLDER_INPUTS if key not in inputs)

    def number(key: str) -> float:
        return inputs[key].number() if key in inputs else float(PLACEHOLDER_INPUTS[key])

    panel_type = _panel_type(inputs["panel_type"].raw) if "panel_type" in inputs else PANEL_TRACKING
    system = PowerSystem(
        panel_area_m2=number("panel_area_m2"),
        panel_efficiency=number("panel_efficiency"),
        battery_capacity_wh=number("battery_capacity_wh"),
        load_day_w=number("load_day_w"),
        load_night_w=number("load_night_w"),
        panel_type=panel_type,
        panel_fixed_azimuth_rad=float(np.deg2rad(number("panel_fixed_azimuth_deg"))),
        panel_losses=number("panel_losses"),
        battery_max_dod=number("battery_max_dod"),
        battery_charge_efficiency=number("battery_charge_efficiency"),
        battery_discharge_efficiency=number("battery_discharge_efficiency"),
        battery_initial_soc=number("battery_initial_soc"),
        battery_specific_energy_wh_per_kg=number("battery_specific_energy_wh_per_kg"),
    )
    return system, placeholders


def incidence_cosine(
    system: PowerSystem, sun_azimuth_rad: ArrayLike, sun_elevation_rad: ArrayLike
) -> NDArray[np.float64]:
    """Cosine of the angle between the panel normal and the direction to the Sun (>= 0)."""
    azimuth = np.asarray(sun_azimuth_rad, dtype=np.float64)
    elevation = np.asarray(sun_elevation_rad, dtype=np.float64)
    cosine = np.cos(elevation)
    if system.panel_type == PANEL_FIXED:
        cosine = cosine * np.cos(azimuth - system.panel_fixed_azimuth_rad)
    return np.maximum(cosine, 0.0)


def generation_w(
    system: PowerSystem,
    sun_fraction: ArrayLike,
    sun_azimuth_rad: ArrayLike,
    sun_elevation_rad: ArrayLike,
    sun_distance_m: ArrayLike | None = None,
) -> NDArray[np.float64]:
    """Electrical power of the panel, W, one value per time.

    ``sun_distance_m`` scales the solar constant with the inverse square of the distance;
    without it the value at 1 au is used.
    """
    fraction = np.asarray(sun_fraction, dtype=np.float64)
    if np.any((fraction < 0.0) | (fraction > 1.0)):
        raise ValueError("sun_fraction must be within 0..1")
    irradiance = SOLAR_CONSTANT_W_M2
    if sun_distance_m is not None:
        irradiance = irradiance * (AU_M / np.asarray(sun_distance_m, dtype=np.float64)) ** 2
    return (
        irradiance
        * system.panel_efficiency
        * (1.0 - system.panel_losses)
        * system.panel_area_m2
        * fraction
        * incidence_cosine(system, sun_azimuth_rad, sun_elevation_rad)
    )


def generation_from_track(
    system: PowerSystem, sun: BodyTrack, sun_fraction: ArrayLike
) -> NDArray[np.float64]:
    """:func:`generation_w` for a Sun track from ``lunarnav.ephemeris``."""
    return generation_w(system, sun_fraction, sun.azimuth_rad, sun.elevation_rad, sun.distance_m)


def load_w(system: PowerSystem, sun_fraction: ArrayLike) -> NDArray[np.float64]:
    """Load per time step: the day load while any part of the Sun is visible, else the night load."""
    return np.where(np.asarray(sun_fraction) > 0.0, system.load_day_w, system.load_night_w).astype(np.float64)


def _checked_series(
    times_utc: NDArray[np.datetime64], generation: ArrayLike, sun_fraction: ArrayLike
) -> tuple[NDArray[np.datetime64], NDArray[np.float64], NDArray[np.float64], float]:
    """Validated copies of the inputs of a simulation and the time step in hours."""
    times = np.asarray(times_utc)
    power = np.asarray(generation, dtype=np.float64)
    fraction = np.asarray(sun_fraction, dtype=np.float64)
    if not (times.shape == power.shape == fraction.shape) or times.ndim != 1:
        raise ValueError("times_utc, generation and sun_fraction must be 1-D arrays of the same length")
    if not np.all(np.isfinite(power)) or np.any(power < 0.0):
        raise ValueError("generation must be finite and >= 0")
    if not np.all(np.isfinite(fraction)):
        raise ValueError("sun_fraction must be finite")
    return times, power, fraction, time_step_hours(times)


def _battery_flow_wh(
    system: PowerSystem, generation: NDArray[np.float64], load: NDArray[np.float64], step_h: float
) -> NDArray[np.float64]:
    """Change of the stored energy per step if the battery had no limits (Wh)."""
    net_wh = (generation - load) * step_h
    return np.where(
        net_wh >= 0.0,
        net_wh * system.battery_charge_efficiency,
        net_wh / system.battery_discharge_efficiency,
    )


@dataclass(frozen=True)
class PowerResult:
    """Outcome of a battery simulation.

    ``times_utc`` and ``energy_wh`` have one entry more than the input series: the state
    at the start of every step and at the end of the last one. ``generation_w`` and
    ``load_w`` hold one value per step.
    """

    system: PowerSystem
    times_utc: NDArray[np.datetime64]
    energy_wh: NDArray[np.float64]
    generation_w: NDArray[np.float64]
    load_w: NDArray[np.float64]
    step_hours: float
    #: Lowest stored energy and when it occurred.
    min_energy_wh: float
    min_energy_utc: str
    #: True when the energy never fell below the allowed minimum.
    survives: bool
    #: First time the energy was below the allowed minimum, None if it never was.
    first_violation_utc: str | None
    #: Load that could not be supplied because the battery was empty (Wh).
    unserved_wh: float
    #: Generation that could not be used because the battery was full (Wh).
    unused_generation_wh: float

    @property
    def soc(self) -> NDArray[np.float64]:
        """State of charge 0..1 (NaN for a battery of zero capacity)."""
        capacity = self.system.battery_capacity_wh
        return self.energy_wh / capacity if capacity > 0 else np.full(self.energy_wh.shape, np.nan)

    @property
    def min_soc(self) -> float:
        capacity = self.system.battery_capacity_wh
        return self.min_energy_wh / capacity if capacity > 0 else float("nan")

    @property
    def generated_wh(self) -> float:
        """Energy the panel could deliver in the window (before battery limits)."""
        return float(self.generation_w.sum() * self.step_hours)

    @property
    def load_wh(self) -> float:
        """Energy the loads ask for in the window."""
        return float(self.load_w.sum() * self.step_hours)


def simulate(
    system: PowerSystem,
    times_utc: NDArray[np.datetime64],
    generation: ArrayLike,
    sun_fraction: ArrayLike,
) -> PowerResult:
    """Step the battery through a uniformly sampled series.

    ``generation`` (W) and ``sun_fraction`` have one value per time; each value holds for
    the step that starts at that time. When the battery is empty the simulation goes on
    with an empty battery (the unsupplied load is summed in ``unserved_wh``), so the curve
    after the first violation shows when the lander could recharge, not that it survived.
    """
    times, generation, fraction, step_h = _checked_series(times_utc, generation, sun_fraction)
    load = load_w(system, fraction)
    flow = _battery_flow_wh(system, generation, load, step_h)

    capacity = system.battery_capacity_wh
    energy = np.empty(times.size + 1)
    energy[0] = system.battery_initial_soc * capacity
    # Level each step asked for before the clamp at empty: a battery that ran empty is a
    # violation even when the allowed minimum is 0 (depth of discharge 1).
    wanted = energy.copy()
    unserved = 0.0
    unused = 0.0
    level = float(energy[0])
    for index, change in enumerate(flow.tolist()):
        level += change
        wanted[index + 1] = level
        if level > capacity:
            unused += (level - capacity) / system.battery_charge_efficiency
            level = capacity
        elif level < 0.0:
            unserved += -level * system.battery_discharge_efficiency
            level = 0.0
        energy[index + 1] = level

    step = np.timedelta64(round(step_h * 3600), "s")
    all_times = np.concatenate([times, [times[-1] + step]])
    floor = system.battery_min_soc * capacity
    below = np.minimum(wanted, energy) < floor - 1e-9 * max(capacity, 1.0)
    lowest = int(np.argmin(energy))
    return PowerResult(
        system=system,
        times_utc=all_times,
        energy_wh=energy,
        generation_w=generation,
        load_w=load,
        step_hours=step_h,
        min_energy_wh=float(energy[lowest]),
        min_energy_utc=str(np.datetime_as_string(all_times[lowest], unit="m")),
        survives=not bool(below.any()),
        first_violation_utc=(
            str(np.datetime_as_string(all_times[int(np.argmax(below))], unit="m")) if below.any() else None
        ),
        unserved_wh=unserved,
        unused_generation_wh=unused,
    )


def required_capacity_wh(
    system: PowerSystem,
    times_utc: NDArray[np.datetime64],
    generation: ArrayLike,
    sun_fraction: ArrayLike,
) -> float:
    """Smallest battery capacity (Wh) with which the lander survives the window.

    All other parameters are those of ``system`` (its capacity is ignored). The battery
    starts at ``battery_initial_soc`` of the capacity being sought. Returns ``inf`` when
    no capacity is enough: the initial state of charge is below the allowed minimum, or
    equal to it while the window starts with a deficit.

    Method: with ``S`` the running sum of the battery flow and ``M`` its running maximum,
    the energy missing from a full battery after each step is ``max(D0, M) - S`` where
    ``D0 = (1 - initial_soc) * capacity`` (a battery that is capped when full). Requiring
    this to stay within the usable part ``max_dod * capacity`` gives two linear conditions
    on the capacity, solved directly.
    """
    times, generation, fraction, step_h = _checked_series(times_utc, generation, sun_fraction)
    headroom = system.battery_initial_soc - system.battery_min_soc
    if headroom < -1e-12:
        return float("inf")  # the battery starts below its allowed minimum
    flow = _battery_flow_wh(system, generation, load_w(system, fraction), step_h)
    running = np.cumsum(flow)
    # Deficit below a battery that has been full at least once: largest drop from a running maximum.
    drop_from_peak = float(np.max(np.maximum.accumulate(running) - running))
    from_full = drop_from_peak / system.battery_max_dod
    # Deficit below the initial level before the battery first fills.
    drop_from_start = float(max(0.0, -running.min()))
    if drop_from_start == 0.0:
        from_start = 0.0
    elif headroom <= 1e-12:  # also catches 0.2 - (1 - 0.8) = 5.6e-17
        return float("inf")
    else:
        from_start = drop_from_start / headroom
    return max(from_full, from_start)


def with_capacity(system: PowerSystem, capacity_wh: float) -> PowerSystem:
    """Copy of the system with another battery capacity."""
    return replace(system, battery_capacity_wh=float(capacity_wh))

"""Tests of lunarnav.power (energy balance) and lunarnav.inputs (engineering inputs file).

All series are synthetic and built in the tests.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from lunarnav.inputs import EngineeringValue, load_engineering_inputs, parse_engineering_inputs
from lunarnav.power import (
    AU_M,
    PANEL_FIXED,
    PANEL_TRACKING,
    PLACEHOLDER_INPUTS,
    SOLAR_CONSTANT_W_M2,
    PowerSystem,
    default_power_system,
    generation_w,
    incidence_cosine,
    load_w,
    required_capacity_wh,
    simulate,
    with_capacity,
)


def hourly(count: int, step_minutes: int = 60) -> np.ndarray:
    return np.datetime64("2027-01-01T00:00") + np.arange(count) * np.timedelta64(step_minutes, "m")


def make_system(**changes: float | str | None) -> PowerSystem:
    base = PowerSystem(
        panel_area_m2=2.0, panel_efficiency=0.25, battery_capacity_wh=1000.0,
        load_day_w=100.0, load_night_w=20.0, battery_max_dod=0.8,
        battery_charge_efficiency=0.9, battery_discharge_efficiency=0.8,
    )
    return replace(base, **changes)


# --- generation ----------------------------------------------------------------------------


def test_generation_of_a_tracking_panel() -> None:
    system = make_system()
    # Full disc, Sun on the horizon, 1 au: S * efficiency * area.
    assert generation_w(system, 1.0, 0.3, 0.0) == pytest.approx(SOLAR_CONSTANT_W_M2 * 0.25 * 2.0)
    # Proportional to the visible share of the disc and to cos(elevation); azimuth does not matter.
    power = generation_w(system, [0.5, 1.0, 0.0], [0.0, 2.0, 1.0], np.deg2rad([0.0, 60.0, 0.0]))
    np.testing.assert_allclose(power, np.array([0.5, 0.5, 0.0]) * SOLAR_CONSTANT_W_M2 * 0.5)
    assert generation_w(replace(system, panel_losses=0.1), 1.0, 0.0, 0.0) == pytest.approx(
        0.9 * SOLAR_CONSTANT_W_M2 * 0.5
    )


def test_generation_scales_with_the_inverse_square_of_distance() -> None:
    system = make_system()
    near, far = generation_w(system, [1.0, 1.0], [0.0, 0.0], [0.0, 0.0], [0.983 * AU_M, 1.017 * AU_M])
    assert near / far == pytest.approx((1.017 / 0.983) ** 2)
    assert generation_w(system, 1.0, 0.0, 0.0, AU_M) == pytest.approx(generation_w(system, 1.0, 0.0, 0.0))


def test_fixed_panel_follows_the_cosine_of_the_azimuth_difference_and_is_one_sided() -> None:
    system = make_system(panel_type=PANEL_FIXED, panel_fixed_azimuth_rad=np.deg2rad(90.0))
    azimuth = np.deg2rad([90.0, 30.0, 150.0, 180.0, 270.0, 0.0])
    np.testing.assert_allclose(
        incidence_cosine(system, azimuth, np.zeros(6)), [1.0, 0.5, 0.5, 0.0, 0.0, 0.0], atol=1e-12
    )
    # Elevation enters as for the tracking panel.
    assert incidence_cosine(system, np.deg2rad(90.0), np.deg2rad(60.0)) == pytest.approx(0.5)
    tracking = make_system(panel_type=PANEL_TRACKING)
    np.testing.assert_allclose(incidence_cosine(tracking, azimuth, np.zeros(6)), 1.0)


def test_generation_rejects_fractions_outside_0_1() -> None:
    with pytest.raises(ValueError):
        generation_w(make_system(), 1.2, 0.0, 0.0)


def test_load_is_day_load_while_any_part_of_the_sun_is_visible() -> None:
    np.testing.assert_array_equal(load_w(make_system(), [0.0, 0.001, 1.0]), [20.0, 100.0, 100.0])


# --- battery -------------------------------------------------------------------------------


def test_without_sun_the_charge_falls_linearly_by_the_load() -> None:
    system = make_system(battery_discharge_efficiency=1.0)
    result = simulate(system, hourly(10), np.zeros(10), np.zeros(10))
    np.testing.assert_allclose(result.energy_wh, 1000.0 - 20.0 * np.arange(11))
    assert result.times_utc.size == 11
    assert result.times_utc[-1] == np.datetime64("2027-01-01T10:00")
    assert (result.min_energy_wh, result.min_energy_utc) == (800.0, "2027-01-01T10:00")
    assert result.survives
    assert result.first_violation_utc is None
    assert result.load_wh == pytest.approx(200.0)
    assert result.generated_wh == 0.0


def test_discharge_efficiency_makes_the_battery_drain_faster() -> None:
    result = simulate(make_system(), hourly(10), np.zeros(10), np.zeros(10))
    np.testing.assert_allclose(result.energy_wh, 1000.0 - 20.0 / 0.8 * np.arange(11))


def test_time_step_is_taken_into_account() -> None:
    system = make_system(battery_discharge_efficiency=1.0)
    result = simulate(system, hourly(8, step_minutes=30), np.zeros(8), np.zeros(8))
    assert result.step_hours == 0.5
    np.testing.assert_allclose(result.energy_wh, 1000.0 - 10.0 * np.arange(9))


def test_without_load_the_charge_never_exceeds_the_capacity() -> None:
    system = make_system(load_day_w=0.0, load_night_w=0.0, battery_initial_soc=0.5)
    generation = np.full(24, 100.0)
    result = simulate(system, hourly(24), generation, np.ones(24))
    assert result.energy_wh.max() == pytest.approx(1000.0)
    assert np.all(result.energy_wh <= 1000.0 + 1e-9)
    assert np.all(np.diff(result.energy_wh) >= 0.0)
    # 90 Wh stored per hour: 500 Wh missing are filled after 5.56 h, the rest is not used.
    np.testing.assert_allclose(result.energy_wh[:6], 500.0 + 90.0 * np.arange(6))
    assert result.unused_generation_wh == pytest.approx(24 * 100.0 - 500.0 / 0.9)
    assert result.unserved_wh == 0.0


def test_energy_is_conserved_over_a_mixed_series() -> None:
    rng = np.random.default_rng(7)
    fraction = (rng.random(500) > 0.4).astype(float)
    generation = fraction * rng.uniform(0.0, 400.0, 500)
    system = make_system(battery_initial_soc=0.6)
    result = simulate(system, hourly(500), generation, fraction)
    net = (generation - result.load_w) * 1.0
    charged = net[net > 0].sum()
    discharged = -net[net < 0].sum()
    # Energy that entered the battery minus energy that left it equals the change of the store.
    stored_in = (charged - result.unused_generation_wh) * 0.9
    taken_out = (discharged - result.unserved_wh) / 0.8
    assert result.energy_wh[-1] - result.energy_wh[0] == pytest.approx(stored_in - taken_out)
    assert result.energy_wh.min() >= 0.0
    assert result.energy_wh.max() <= 1000.0 + 1e-9


def test_verdict_and_first_violation() -> None:
    system = make_system(battery_discharge_efficiency=1.0, load_night_w=100.0)
    # 100 W for 9 h takes the battery from 1000 to 100 Wh; the allowed minimum is 200 Wh.
    result = simulate(system, hourly(9), np.zeros(9), np.zeros(9))
    assert not result.survives
    assert result.first_violation_utc == "2027-01-01T09:00"  # 100 Wh, reached at the end of step 9
    assert result.min_energy_wh == pytest.approx(100.0)
    assert result.min_soc == pytest.approx(0.1)
    exactly = simulate(system, hourly(8), np.zeros(8), np.zeros(8))  # ends exactly at 200 Wh
    assert exactly.survives
    assert exactly.min_soc == pytest.approx(0.2)


def test_empty_battery_stays_at_zero_and_counts_unserved_load() -> None:
    system = make_system(battery_discharge_efficiency=1.0, load_night_w=300.0)
    result = simulate(system, hourly(5), np.zeros(5), np.zeros(5))
    np.testing.assert_allclose(result.energy_wh, [1000.0, 700.0, 400.0, 100.0, 0.0, 0.0])
    assert result.unserved_wh == pytest.approx(500.0)
    assert not result.survives


@pytest.mark.parametrize("max_dod", [1.0, 0.8])
def test_running_empty_is_a_violation_even_when_the_whole_battery_is_usable(max_dod: float) -> None:
    system = make_system(battery_max_dod=max_dod, battery_discharge_efficiency=1.0, load_night_w=300.0)
    result = simulate(system, hourly(5), np.zeros(5), np.zeros(5))  # asks for 1500 Wh from 1000 Wh
    assert result.unserved_wh == pytest.approx(500.0)
    assert not result.survives
    expected_first = "2027-01-01T04:00" if max_dod == 1.0 else "2027-01-01T03:00"
    assert result.first_violation_utc == expected_first
    # Exactly emptying a fully usable battery is still allowed.
    exact = simulate(make_system(battery_max_dod=1.0, battery_discharge_efficiency=1.0, load_night_w=250.0),
                     hourly(4), np.zeros(4), np.zeros(4))
    assert exact.survives and exact.min_energy_wh == pytest.approx(0.0)


def test_zero_capacity_survives_only_without_any_deficit() -> None:
    system = make_system(battery_capacity_wh=0.0, load_day_w=10.0)
    assert simulate(system, hourly(5), np.full(5, 50.0), np.ones(5)).survives
    assert not simulate(system, hourly(5), np.zeros(5), np.zeros(5)).survives


def test_simulate_rejects_bad_input() -> None:
    system = make_system()
    with pytest.raises(ValueError):
        simulate(system, hourly(5), np.zeros(4), np.zeros(5))
    with pytest.raises(ValueError):
        simulate(system, hourly(5), np.full(5, -1.0), np.zeros(5))
    with pytest.raises(ValueError):
        simulate(system, hourly(1), np.zeros(1), np.zeros(1))
    with pytest.raises(ValueError):
        required_capacity_wh(system, hourly(5), np.array([0.0, np.nan, 0.0, 0.0, 0.0]), np.zeros(5))


# --- required capacity ---------------------------------------------------------------------


def test_required_capacity_for_one_night() -> None:
    system = make_system()  # night load 20 W, discharge efficiency 0.8, usable share 0.8
    times = hourly(100)
    capacity = required_capacity_wh(system, times, np.zeros(100), np.zeros(100))
    assert capacity == pytest.approx(100 * 20.0 / 0.8 / 0.8)
    assert simulate(with_capacity(system, capacity), times, np.zeros(100), np.zeros(100)).survives
    assert not simulate(with_capacity(system, 0.99 * capacity), times, np.zeros(100), np.zeros(100)).survives


@pytest.mark.parametrize("max_dod", [0.8, 1.0])
@pytest.mark.parametrize("initial_soc", [1.0, 0.7, 0.35])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_required_capacity_is_the_threshold_between_failing_and_surviving(
    initial_soc: float, seed: int, max_dod: float
) -> None:
    rng = np.random.default_rng(seed)
    # Alternating days and nights of random length with random generation.
    fraction = np.repeat(rng.integers(0, 2, 40), rng.integers(5, 60, 40)).astype(float)
    generation = fraction * rng.uniform(50.0, 500.0, fraction.size)
    times = hourly(fraction.size)
    system = make_system(battery_initial_soc=initial_soc, battery_max_dod=max_dod)
    capacity = required_capacity_wh(system, times, generation, fraction)
    assert capacity > 0.0
    assert simulate(with_capacity(system, capacity * 1.0001), times, generation, fraction).survives
    assert not simulate(with_capacity(system, capacity * 0.999), times, generation, fraction).survives


def test_required_capacity_special_cases() -> None:
    times = hourly(10)
    always_enough = make_system(load_day_w=10.0)
    assert required_capacity_wh(always_enough, times, np.full(10, 50.0), np.ones(10)) == 0.0
    # Starting at the allowed minimum with a deficit ahead: no capacity is enough.
    stuck = make_system(battery_initial_soc=0.2)
    assert required_capacity_wh(stuck, times, np.zeros(10), np.zeros(10)) == float("inf")
    # Starting at the allowed minimum is fine when the window begins with a surplus.
    day_then_night = np.array([200.0] * 5 + [0.0] * 5)
    sun = (day_then_night > 0).astype(float)
    capacity = required_capacity_wh(stuck, times, day_then_night, sun)
    assert capacity == pytest.approx(5 * 20.0 / 0.8 / 0.8)
    assert simulate(with_capacity(stuck, capacity * 1.0001), times, day_then_night, sun).survives
    # Starting below the allowed minimum is a violation at once, whatever the capacity.
    low = make_system(battery_initial_soc=0.1)
    assert required_capacity_wh(low, times, day_then_night, sun) == float("inf")
    assert not simulate(low, times, day_then_night, sun).survives


# --- parameters and engineering inputs -----------------------------------------------------


def test_power_system_validation_and_battery_mass() -> None:
    system = make_system(battery_specific_energy_wh_per_kg=200.0)
    assert system.battery_min_soc == pytest.approx(0.2)
    assert system.battery_mass_kg == pytest.approx(5.0)
    assert make_system().battery_mass_kg is None
    for bad in (
        {"panel_efficiency": 1.2}, {"battery_max_dod": 0.0}, {"battery_charge_efficiency": 0.0},
        {"load_night_w": -1.0}, {"panel_type": "sideways"}, {"battery_initial_soc": 1.5},
        {"battery_specific_energy_wh_per_kg": 0.0},
    ):
        with pytest.raises(ValueError):
            make_system(**bad)


INPUTS_TEXT = """
## 1. Солнечные панели

| Ключ | Параметр | Значение | Единицы | Источник или обоснование |
|---|---|---|---|---|
| `panel_type` | Тип панелей | неподвижная вертикальная | — | инженерная оценка |
| `panel_area_m2` | Площадь панелей | 0,5–3 (по умолчанию 1,5) | м² | расчёт |
| `panel_efficiency` | КПД панелей | 0.28 | доля 0–1 | паспорт |
| `panel_fixed_azimuth_deg` | Азимут | 45 | градусы | |
| `battery_capacity_wh` | Ёмкость батареи | | Вт·ч | |
| `mast_heights_m` | Список высот мачты | 0, 2,5, 10 | м | |
"""


def test_engineering_inputs_parser() -> None:
    values = parse_engineering_inputs(INPUTS_TEXT)
    assert set(values) == {"panel_type", "panel_area_m2", "panel_efficiency", "panel_fixed_azimuth_deg", "mast_heights_m"}
    assert values["panel_area_m2"].number() == 1.5
    assert values["panel_area_m2"].bounds() == (0.5, 3.0)
    assert values["panel_efficiency"].number() == 0.28
    assert values["panel_efficiency"].bounds() is None
    assert values["panel_efficiency"].source == "паспорт"
    assert values["mast_heights_m"].numbers() == [0.0, 2.5, 10.0]
    with pytest.raises(ValueError):
        values["panel_type"].number()
    assert EngineeringValue("x", "0.5-2 (default 1)").number() == 1.0
    assert EngineeringValue("x", "0,5–2 (По умолч. 1,25)").number() == 1.25
    assert EngineeringValue("x", "0.5 — 2 (default: 1)").bounds() == (0.5, 2.0)
    assert EngineeringValue("x", "0.3 (BOL)").number() == 0.3
    assert EngineeringValue("x", "-5").number() == -5.0
    assert EngineeringValue("x", "0; 2,5; 10").numbers() == [0.0, 2.5, 10.0]
    for unclear in ("0.5-2", "0,5 – 2", "30 %", "30%"):
        with pytest.raises(ValueError):
            EngineeringValue("x", unclear).number()
    marks = "| `a_b` | имя | — | м | |\n| `c_d` | имя | TBD | | |\n| `e_f` | имя \\| с чертой | 7 | м | |\n"
    parsed = parse_engineering_inputs(marks)
    assert set(parsed) == {"e_f"}
    assert parsed["e_f"].number() == 7.0
    with pytest.raises(ValueError, match="duplicate"):
        parse_engineering_inputs(INPUTS_TEXT + "| `panel_efficiency` | КПД | 0.3 | | |\n")


def test_default_power_system_uses_filled_values_and_reports_placeholders() -> None:
    system, placeholders = default_power_system(parse_engineering_inputs(INPUTS_TEXT))
    assert system.panel_type == PANEL_FIXED
    assert system.panel_area_m2 == 1.5
    assert system.panel_efficiency == 0.28
    assert system.panel_fixed_azimuth_rad == pytest.approx(np.deg2rad(45.0))
    assert system.battery_capacity_wh == PLACEHOLDER_INPUTS["battery_capacity_wh"]
    assert "battery_capacity_wh" in placeholders and "load_night_w" in placeholders
    assert "panel_area_m2" not in placeholders and "panel_type" not in placeholders

    empty_system, all_placeholders = default_power_system({})
    assert set(all_placeholders) == set(PLACEHOLDER_INPUTS)
    assert empty_system.panel_type == PANEL_TRACKING
    assert empty_system.battery_mass_kg == pytest.approx(1000.0 / 150.0)


def test_project_inputs_file_is_readable(tmp_path: Path) -> None:
    """The real docs/ENGINEERING_INPUTS.md must parse, whatever the engineer has filled in so far."""
    system, placeholders = default_power_system(load_engineering_inputs())
    assert isinstance(system, PowerSystem)
    assert set(placeholders) <= set(PLACEHOLDER_INPUTS)
    assert load_engineering_inputs(tmp_path / "missing.md") == {}

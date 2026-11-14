"""Tests of the day-load rule (task T23) and of provisional engineering inputs."""

import numpy as np
import pytest

from lunarnav.inputs import parse_engineering_inputs
from lunarnav.power import (
    DAY_LOAD_POWER,
    DAY_LOAD_SUN_VISIBLE,
    PowerSystem,
    default_power_system,
    load_w,
    required_capacity_wh,
    simulate,
    with_capacity,
)


def system(rule: str, capacity_wh: float = 1000.0) -> PowerSystem:
    return PowerSystem(panel_area_m2=1.0, panel_efficiency=0.3, battery_capacity_wh=capacity_wh, load_day_w=100.0,
                       load_night_w=20.0, battery_max_dod=0.8, day_load_rule=rule)


def test_day_mode_needs_enough_power_under_the_power_rule() -> None:
    fraction = np.array([1.0, 0.1, 0.0, 0.5])
    generation = np.array([300.0, 30.0, 0.0, 100.0])
    np.testing.assert_array_equal(load_w(system(DAY_LOAD_SUN_VISIBLE), fraction, generation), [100, 100, 20, 100])
    np.testing.assert_array_equal(load_w(system(DAY_LOAD_POWER), fraction, generation), [100, 20, 20, 100])
    with pytest.raises(ValueError, match="needs the generation"):
        load_w(system(DAY_LOAD_POWER), fraction)
    with pytest.raises(ValueError):
        PowerSystem(panel_area_m2=1.0, panel_efficiency=0.3, battery_capacity_wh=1.0, load_day_w=1.0,
                    load_night_w=1.0, day_load_rule="always")


def test_a_sliver_of_sun_no_longer_drains_the_battery() -> None:
    """28 h of weak light (60 W against a 100 W day load), as found at Connecting Ridge (T11)."""
    times = np.datetime64("2027-08-01T00") + np.arange(48) * np.timedelta64(1, "h")
    fraction = np.where(np.arange(48) < 28, 0.15, 1.0)
    generation = np.where(np.arange(48) < 28, 60.0, 400.0)
    old = required_capacity_wh(system(DAY_LOAD_SUN_VISIBLE), times, generation, fraction)
    new = required_capacity_wh(system(DAY_LOAD_POWER), times, generation, fraction)
    assert old == pytest.approx(28 * 40.0 / 0.8)  # 40 W deficit for 28 h, lossless battery
    assert new == 0.0  # 60 W covers the 20 W night load


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_required_capacity_matches_simulation_under_the_power_rule(seed: int) -> None:
    rng = np.random.default_rng(seed)
    times = np.datetime64("2027-01-01T00") + np.arange(500) * np.timedelta64(1, "h")
    fraction = np.clip(rng.normal(0.5, 0.5, 500), 0.0, 1.0)
    generation = 250.0 * fraction
    base = system(DAY_LOAD_POWER)
    needed = required_capacity_wh(base, times, generation, fraction)
    assert np.isfinite(needed) and needed > 0
    assert simulate(with_capacity(base, needed * 1.0001), times, generation, fraction).survives
    assert not simulate(with_capacity(base, needed * 0.99), times, generation, fraction).survives


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("пока генерация панели покрывает дневную нагрузку", DAY_LOAD_POWER),
        ("power_covers_load", DAY_LOAD_POWER),
        ("while the generation covers the day load", DAY_LOAD_POWER),
        ("пока видна любая часть Солнца", DAY_LOAD_SUN_VISIBLE),
        ("sun visible", DAY_LOAD_SUN_VISIBLE),
    ],
)
def test_the_rule_is_read_from_the_engineering_inputs(text: str, expected: str) -> None:
    inputs = parse_engineering_inputs(f"| `load_day_rule` | Правило | {text} | — | инженер |\n")
    assert default_power_system(inputs)[0].day_load_rule == expected


def test_an_ambiguous_rule_is_refused() -> None:
    with pytest.raises(ValueError, match="load_day_rule"):
        default_power_system(parse_engineering_inputs("| `load_day_rule` | x | как придётся | — | |\n"))


def test_proposed_values_are_used_but_stay_flagged() -> None:
    text = (
        "| `battery_capacity_wh` | Ёмкость | 20000 | Вт·ч | NASA, 2022 [предложено] |\n"
        "| `load_night_w` | Ночь | 46 | Вт | инженер, расчёт |\n"
    )
    inputs = parse_engineering_inputs(text)
    assert inputs["battery_capacity_wh"].provisional and not inputs["load_night_w"].provisional
    system_, flagged = default_power_system(inputs)
    assert system_.battery_capacity_wh == 20000.0 and system_.load_night_w == 46.0
    assert "battery_capacity_wh" in flagged and "load_night_w" not in flagged
    assert "load_day_w" in flagged  # still empty
    assert system_.day_load_rule == DAY_LOAD_POWER  # the placeholder rule

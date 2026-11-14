"""Tests of lunarnav.mast: settings, the mast-height trade-off table and where the gain levels off."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lunarnav import ephemeris
from lunarnav.comms import RULE_ANY_PART, CommSettings, link_mask
from lunarnav.ephemeris import centre_ephemeris
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.inputs import parse_engineering_inputs
from lunarnav.mast import (
    CARRIES_ANTENNA,
    CARRIES_BOTH,
    CARRIES_PANELS,
    COLUMNS,
    DEFAULT_MAST_HEIGHTS_M,
    TRADEOFF_METRICS,
    MastSettings,
    default_mast_settings,
    diminishing_returns_height,
    levelling_off_heights,
    mast_tradeoff,
    observer_series,
    tradeoff_table,
)
from lunarnav.power import PowerSystem

HORIZON_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "horizons"
needs_kernels = pytest.mark.skipif(
    not all((ephemeris.kernel_dir() / name).is_file() for name in ephemeris.KERNEL_FILES),
    reason="SPICE kernels are not downloaded (see docs/SOURCES.md)",
)
SYSTEM = PowerSystem(
    panel_area_m2=1.0, panel_efficiency=0.3, battery_capacity_wh=1000.0, load_day_w=100.0, load_night_w=20.0,
    battery_charge_efficiency=0.95, battery_discharge_efficiency=0.95, battery_specific_energy_wh_per_kg=150.0,
)
SUN_COLUMNS = ("sunlit_pct", "mean_sun_fraction_pct", "longest_night_h", "mean_generation_w", "required_capacity_wh")
EARTH_COLUMNS = ("earth_pct", "longest_earth_gap_h")


def flat_profile(mast_height_m: float, horizon_deg: float, lat_deg: float = -89.4441) -> HorizonProfile:
    """Synthetic site: the same horizon elevation at every azimuth."""
    return HorizonProfile(
        lat_rad=np.deg2rad(lat_deg), lon_east_rad=np.deg2rad(222.709), ground_height_m=1955.9,
        mast_height_m=mast_height_m, max_range_m=300e3, azimuth_rad=np.arange(720) * np.deg2rad(0.5),
        elevation_rad=np.full(720, np.deg2rad(horizon_deg)), distance_m=np.full(720, 1000.0),
        covered_range_m=np.full(720, 300e3),
    )


def hourly(start: str, stop: str) -> np.ndarray:
    return np.arange(np.datetime64(f"{start}T00"), np.datetime64(f"{stop}T00"), np.timedelta64(1, "h"))


# --- settings ------------------------------------------------------------------------------


def test_settings_default_to_the_task_values_and_report_placeholders() -> None:
    settings, placeholders = default_mast_settings({})
    assert settings == MastSettings(DEFAULT_MAST_HEIGHTS_M, CARRIES_BOTH)
    assert settings.heights_m == (0.0, 2.0, 5.0, 10.0, 20.0)
    assert placeholders == ("mast_heights_m", "mast_carries")


def test_settings_are_read_from_the_engineering_inputs() -> None:
    text = (
        "| `mast_heights_m` | Высоты | 10; 0; 3,5; 1 | м | инженер |\n"
        "| `mast_carries` | Что стоит на мачте | только солнечные панели | — | инженер |\n"
    )
    settings, placeholders = default_mast_settings(parse_engineering_inputs(text))
    assert settings.heights_m == (0.0, 1.0, 3.5, 10.0)  # sorted, decimal comma
    assert settings.carries == CARRIES_PANELS
    assert placeholders == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("both", CARRIES_BOTH),
        ("и то и другое", CARRIES_BOTH),
        ("панели и антенна", CARRIES_BOTH),
        ("оба", CARRIES_BOTH),
        ("панели", CARRIES_PANELS),
        ("Solar panel only", CARRIES_PANELS),
        ("антенна", CARRIES_ANTENNA),
        ("only the antenna", CARRIES_ANTENNA),
        ("солнечные батареи", CARRIES_PANELS),
        ("панели и антенна на мачте", CARRIES_BOTH),
    ],
)
def test_what_the_mast_carries_is_parsed(text: str, expected: str) -> None:
    inputs = parse_engineering_inputs(f"| `mast_carries` | x | {text} | — | |\n")
    assert default_mast_settings(inputs)[0].carries == expected


@pytest.mark.parametrize(
    "text",
    [
        "панели, без антенны",
        "не антенна",
        "мачта",
        "small dish",
        "батарея",  # a battery is not a solar panel
        # Where the other item is: the words for both appear, but the answer is not "both".
        "антенна на корпусе, панели на мачте",
        "панели на мачте, антенна внизу",
        "only panels, antenna fixed to hull",
    ],
)
def test_ambiguous_mast_load_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="mast_carries"):
        default_mast_settings(parse_engineering_inputs(f"| `mast_carries` | x | {text} | — | |\n"))


def test_settings_validation() -> None:
    with pytest.raises(ValueError):
        MastSettings(())
    with pytest.raises(ValueError):
        MastSettings((0.0, -1.0))
    with pytest.raises(ValueError):
        MastSettings((2.0, 2.0))
    with pytest.raises(ValueError):
        MastSettings((0.0, float("nan")))
    with pytest.raises(ValueError):
        MastSettings((0.0, 2.0), "rover")


# --- where the gain levels off -------------------------------------------------------------


def test_diminishing_returns_height() -> None:
    heights = [0.0, 2.0, 5.0, 10.0, 20.0]
    # Gains over the lowest height: 0, 20, 36, 39, 40 -> 90 % of 40 is first reached at 5 m.
    assert diminishing_returns_height(heights, [50.0, 70.0, 86.0, 89.0, 90.0]) == 5.0
    assert diminishing_returns_height(heights, [50.0, 70.0, 86.0, 89.0, 90.0], share=1.0) == 20.0
    assert diminishing_returns_height(heights, [50.0, 70.0, 86.0, 89.0, 90.0], share=0.5) == 2.0
    # Lower is better (longest night, battery mass).
    assert diminishing_returns_height(heights, [300.0, 200.0, 110.0, 100.0, 100.0], lower_is_better=True) == 5.0
    # Unsorted input is sorted by height first: gains over 2 m are 0, 18, 19 -> 5 m.
    assert diminishing_returns_height([10.0, 2.0, 5.0], [89.0, 70.0, 88.0]) == 5.0
    # Same values with 86 at 5 m: gains 0, 16, 19 and 16 < 0.9 * 19, so 10 m.
    assert diminishing_returns_height([10.0, 2.0, 5.0], [89.0, 70.0, 86.0]) == 10.0
    # Nothing improves: no height to report.
    assert diminishing_returns_height(heights, [50.0, 50.0, 49.0, 50.0, 50.0]) is None
    assert diminishing_returns_height(heights, [0.0, 0.0, 0.0, 0.0, 0.0], lower_is_better=True) is None
    # A battery that no capacity can save at the lowest height gives no finite gain.
    assert diminishing_returns_height([2.0, 5.0], [np.inf, 10.0], lower_is_better=True) is None
    # Rounding noise is no gain; a NaN elsewhere counts as no gain at that height only.
    assert diminishing_returns_height([2.0, 5.0, 10.0], [50.0, 50.0 + 1e-12, 50.0]) is None
    assert diminishing_returns_height([2.0, 5.0, 10.0], [50.0, np.nan, 60.0]) == 10.0
    assert diminishing_returns_height([2.0, 5.0, 10.0], [np.nan, 55.0, 60.0]) is None
    with pytest.raises(ValueError):
        diminishing_returns_height([1.0], [1.0])
    with pytest.raises(ValueError):
        diminishing_returns_height(heights, [1.0, 2.0])
    with pytest.raises(ValueError):
        diminishing_returns_height(heights, [1.0, 2.0, 3.0, 4.0, 5.0], share=0.0)


def test_levelling_off_starts_from_the_lowest_meaningful_height() -> None:
    heights = [0.0, 2.0, 5.0, 10.0, 20.0]
    table = pd.DataFrame({"mast_height_m": heights})
    for column in TRADEOFF_METRICS:
        table[column] = 1.0
    # Counted from 2 m the gains are 0, 5, 6.5, 7, so 90 % (6.3) is reached at 10 m.
    # Counted from 0 m they are 0, 63, 68, 69.5, 70 and 2 m would look like the answer.
    table["sunlit_pct"] = [10.0, 73.0, 78.0, 79.5, 80.0]
    table["required_capacity_wh"] = [9000.0, 4000.0, 3000.0, 2000.0, 2000.0]
    result = levelling_off_heights(table)
    assert set(result) == set(TRADEOFF_METRICS)
    assert result["sunlit_pct"] == 10.0
    assert result["required_capacity_wh"] == 10.0
    assert result["earth_pct"] is None  # flat column: no gain
    assert levelling_off_heights(table, min_height_m=0.0)["sunlit_pct"] == 2.0
    assert levelling_off_heights(table, min_height_m=15.0) == dict.fromkeys(TRADEOFF_METRICS)


@pytest.mark.parametrize(("column", "lower_is_better"), list(TRADEOFF_METRICS.items()))
def test_each_metric_improves_in_its_own_direction(column: str, lower_is_better: bool) -> None:
    """A wrong 'lower is better' flag would turn the gain into a loss and give None."""
    expected_direction = {
        "sunlit_pct": False, "mean_sun_fraction_pct": False, "earth_pct": False,
        "longest_night_h": True, "longest_earth_gap_h": True, "required_capacity_wh": True,
    }
    assert lower_is_better == expected_direction[column]
    table = pd.DataFrame({"mast_height_m": [2.0, 5.0, 10.0, 20.0]})
    for other in TRADEOFF_METRICS:
        table[other] = 1.0
    improving = np.array([10.0, 18.0, 19.5, 20.0])  # gains 0, 8, 9.5, 10 -> 90 % at 10 m
    table[column] = -improving if lower_is_better else improving
    assert levelling_off_heights(table)[column] == 10.0


# --- trade-off table -----------------------------------------------------------------------


@needs_kernels
def test_lower_horizon_gives_more_light_and_a_smaller_battery() -> None:
    """Synthetic site: the mast lowers a level horizon from +1 deg to -1 deg."""
    centre = centre_ephemeris(hourly("2027-01-01", "2027-07-01"))
    profiles = [flat_profile(10.0, -1.0), flat_profile(0.0, 1.0), flat_profile(5.0, 0.0)]
    table = mast_tradeoff(profiles, centre, SYSTEM)
    assert list(table.columns) == list(COLUMNS)
    assert table["mast_height_m"].tolist() == [0.0, 5.0, 10.0]  # sorted by height
    for column in ("sunlit_pct", "mean_sun_fraction_pct", "mean_generation_w", "earth_pct", "sun_and_earth_pct"):
        assert table[column].is_monotonic_increasing, column
        assert table[column].iloc[-1] > table[column].iloc[0], column
    for column in ("longest_night_h", "longest_earth_gap_h", "required_capacity_wh", "required_battery_mass_kg"):
        assert table[column].is_monotonic_decreasing, column
    np.testing.assert_allclose(table["required_battery_mass_kg"], table["required_capacity_wh"] / 150.0)
    assert np.all(table["mean_sun_fraction_pct"] <= table["sunlit_pct"])
    assert np.all(table["sun_and_earth_pct"] <= np.minimum(table["sunlit_pct"], table["earth_pct"]))
    # The verdict for the given 1000 Wh battery agrees with the required capacity.
    np.testing.assert_array_equal(table["survives_with_given_battery"], table["required_capacity_wh"] <= 1000.0)


@needs_kernels
def test_two_step_api_gives_the_same_table() -> None:
    centre = centre_ephemeris(hourly("2027-01-01", "2027-03-01"))
    profiles = [flat_profile(0.0, 0.5), flat_profile(5.0, -0.5)]
    series = observer_series(profiles, centre, "2027-01-15", "2027-02-15")
    assert [item.mast_height_m for item in series] == [0.0, 5.0]
    assert series[0].track.times_utc[0] == np.datetime64("2027-01-15T00")
    assert series[0].track.times_utc.size == 31 * 24
    windowed = mast_tradeoff(profiles, centre, SYSTEM, start_utc="2027-01-15", stop_utc="2027-02-15")
    pd.testing.assert_frame_equal(tradeoff_table(series, SYSTEM), windowed)
    # The window cut from a longer ephemeris equals an ephemeris made for the window alone.
    window_only = centre_ephemeris(hourly("2027-01-15", "2027-02-15"))
    pd.testing.assert_frame_equal(windowed, mast_tradeoff(profiles, window_only, SYSTEM))
    # The end of the window is exclusive and may coincide with the end of the last step.
    last_step_end = np.datetime64("2027-03-01T00")
    assert observer_series(profiles, centre, stop_utc=last_step_end)[0].track.times_utc.size == centre.times_utc.size
    assert observer_series(profiles, centre, stop_utc="2027-02-28T23:00")[0].track.times_utc[-1] == np.datetime64(
        "2027-02-28T22:00"
    )


@needs_kernels
def test_window_and_settings_are_respected() -> None:
    centre = centre_ephemeris(hourly("2027-01-01", "2027-05-01"))
    profiles = [flat_profile(0.0, 0.5), flat_profile(5.0, -0.5)]
    whole = mast_tradeoff(profiles, centre, SYSTEM)
    part = mast_tradeoff(profiles, centre, SYSTEM, start_utc="2027-02-01", stop_utc="2027-03-01")
    assert not np.allclose(whole["sunlit_pct"], part["sunlit_pct"])
    assert np.all(part["longest_night_h"] <= 28 * 24)
    assert np.all(part["required_capacity_wh"] <= whole["required_capacity_wh"] + 1e-6)
    # "Any part of the disc" can only add link time compared with the centre rule.
    any_part = mast_tradeoff(profiles, centre, SYSTEM, CommSettings(RULE_ANY_PART))
    assert np.all(any_part["earth_pct"] >= whole["earth_pct"])
    # Without a specific energy there is no battery mass.
    no_mass = mast_tradeoff(profiles, centre, replace(SYSTEM, battery_specific_energy_wh_per_kg=None))
    assert no_mass["required_battery_mass_kg"].isna().all()
    with pytest.raises(ValueError):
        mast_tradeoff([], centre, SYSTEM)
    with pytest.raises(ValueError, match="same site"):
        mast_tradeoff([flat_profile(0.0, 0.5), flat_profile(5.0, 0.0, lat_deg=-85.0)], centre, SYSTEM)
    with pytest.raises(ValueError, match="only once"):
        mast_tradeoff([flat_profile(2.0, 0.5), flat_profile(2.0, 0.0)], centre, SYSTEM)
    with pytest.raises(ValueError, match="fewer than two"):
        mast_tradeoff(profiles, centre, SYSTEM, start_utc="2027-04-30T23:00")
    # A window that sticks out of the ephemeris is refused instead of silently shortened.
    with pytest.raises(ValueError, match="before the series"):
        mast_tradeoff(profiles, centre, SYSTEM, start_utc="2026-12-01")
    with pytest.raises(ValueError, match="after the series"):
        mast_tradeoff(profiles, centre, SYSTEM, stop_utc="2027-06-01")
    with pytest.raises(ValueError, match="carries"):
        mast_tradeoff(profiles, centre, SYSTEM, carries="rover")


@needs_kernels
def test_equipment_off_the_mast_stays_at_the_lowest_height() -> None:
    centre = centre_ephemeris(hourly("2027-01-01", "2027-04-01"))
    profiles = [flat_profile(0.0, 1.0), flat_profile(5.0, 0.0), flat_profile(10.0, -1.0)]
    both = mast_tradeoff(profiles, centre, SYSTEM, carries=CARRIES_BOTH)
    panels = mast_tradeoff(profiles, centre, SYSTEM, carries=CARRIES_PANELS)
    antenna = mast_tradeoff(profiles, centre, SYSTEM, carries=CARRIES_ANTENNA)
    for column in SUN_COLUMNS:
        pd.testing.assert_series_equal(panels[column], both[column])
        assert antenna[column].nunique() == 1, column  # the panel stays at 0 m
        assert antenna[column].iloc[0] == both[column].iloc[0], column
    for column in EARTH_COLUMNS:
        pd.testing.assert_series_equal(antenna[column], both[column])
        assert panels[column].nunique() == 1, column  # the antenna stays at 0 m
        assert panels[column].iloc[0] == both[column].iloc[0], column
    assert both["earth_pct"].iloc[-1] > both["earth_pct"].iloc[0]
    # The battery verdict follows the panel.
    for column in ("survives_with_given_battery", "min_soc_pct_with_given_battery"):
        pd.testing.assert_series_equal(panels[column], both[column])
        assert antenna[column].nunique() == 1, column
    # "Sun and Earth" combines the Sun seen by the panel with the link of the antenna.
    series = observer_series(profiles, centre)
    sunlit = [item.vis.sun_fraction > 0.0 for item in series]
    link = [link_mask(item.vis, item.track.earth.angular_radius_rad) for item in series]
    for row, _ in enumerate(series):
        assert panels["sun_and_earth_pct"].iloc[row] == pytest.approx(100.0 * np.mean(sunlit[row] & link[0]))
        assert antenna["sun_and_earth_pct"].iloc[row] == pytest.approx(100.0 * np.mean(sunlit[0] & link[row]))
        assert both["sun_and_earth_pct"].iloc[row] == pytest.approx(100.0 * np.mean(sunlit[row] & link[row]))
    assert panels["sun_and_earth_pct"].iloc[-1] != antenna["sun_and_earth_pct"].iloc[-1]


@needs_kernels
@pytest.mark.skipif(
    not all(cache_path(HORIZON_DIR, "connecting_ridge", h).is_file() for h in DEFAULT_MAST_HEIGHTS_M),
    reason="needs the cached horizons of all five heights",
)
def test_real_site_mast_never_loses_light() -> None:
    centre = centre_ephemeris(hourly("2027-01-01", "2027-07-01"))
    profiles = [HorizonProfile.load(cache_path(HORIZON_DIR, "connecting_ridge", h)) for h in DEFAULT_MAST_HEIGHTS_M]
    table = mast_tradeoff(profiles, centre, SYSTEM)
    assert table["sunlit_pct"].is_monotonic_increasing
    assert table["required_capacity_wh"].is_monotonic_decreasing
    assert table["sunlit_pct"].iloc[-1] - table["sunlit_pct"].iloc[0] > 5.0  # the ridge reacts to a mast

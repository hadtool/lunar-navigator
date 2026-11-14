"""Tests of lunarnav.windows: landing-date table and the choice of the best landing dates."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lunarnav import ephemeris
from lunarnav.ephemeris import centre_ephemeris, sky_track
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.inputs import parse_engineering_inputs
from lunarnav.power import PowerSystem
from lunarnav.visibility import visibility
from lunarnav.windows import (
    COLUMNS,
    DEFAULT_MISSION_DAYS,
    best_landing_dates,
    default_mission_days,
    landing_table,
    landing_windows,
)

HORIZON_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "horizons"
needs_kernels = pytest.mark.skipif(
    not all((ephemeris.kernel_dir() / name).is_file() for name in ephemeris.KERNEL_FILES),
    reason="SPICE kernels are not downloaded (see docs/SOURCES.md)",
)


def system(capacity_wh: float = 1000.0) -> PowerSystem:
    """Lossless battery usable down to 20 %, 100 W by day and 20 W by night."""
    return PowerSystem(
        panel_area_m2=1.0, panel_efficiency=0.3, battery_capacity_wh=capacity_wh, load_day_w=100.0,
        load_night_w=20.0, battery_max_dod=0.8, battery_specific_energy_wh_per_kg=150.0,
    )


@pytest.fixture
def series() -> dict:
    """Ten days, hourly. Sun everywhere except one 24 h night (hours 96-119); 300 W while the
    Sun is up; the Earth link is on for 12 h and off for 12 h, starting on."""
    hours = np.arange(240)
    times = np.datetime64("2027-01-01T00") + hours * np.timedelta64(1, "h")
    sun = np.where((hours >= 96) & (hours < 120), 0.0, 1.0)
    return {
        "times": times,
        "sun": sun,
        "generation": 300.0 * sun,
        "link": (hours // 12) % 2 == 0,
    }


def run(series: dict, capacity_wh: float = 1000.0, **kwargs) -> pd.DataFrame:
    kwargs.setdefault("duration_h", 48.0)
    return landing_table(
        series["times"], series["sun"], series["generation"], series["link"], system(capacity_wh), **kwargs
    )


# --- settings ------------------------------------------------------------------------------


def test_mission_length_from_the_engineering_inputs() -> None:
    assert default_mission_days({}) == (DEFAULT_MISSION_DAYS, ("mission_duration_days",))
    assert DEFAULT_MISSION_DAYS == 14.0
    filled = parse_engineering_inputs("| `mission_duration_days` | Длительность | 10,5 | сут | инженер |\n")
    assert default_mission_days(filled) == (10.5, ())
    with pytest.raises(ValueError):
        default_mission_days(parse_engineering_inputs("| `mission_duration_days` | x | -3 | сут | |\n"))


# --- landing table ---------------------------------------------------------------------------


def test_one_row_per_landing_day_with_the_expected_values(series: dict) -> None:
    table = run(series)
    assert list(table.columns) == list(COLUMNS)
    # Missions of 48 h fit for landings on days 0..8.
    assert table["landing_utc"].tolist() == list(pd.date_range("2027-01-01", periods=9, freq="D"))
    assert (table["end_utc"] - table["landing_utc"] == pd.Timedelta(hours=48)).all()
    with_night = table["landing_utc"].isin(pd.to_datetime(["2027-01-04", "2027-01-05"]))
    # The night costs 24 h x 20 W = 480 Wh of the 1000 Wh battery.
    np.testing.assert_allclose(table.loc[with_night, "min_soc_pct"], 52.0)
    np.testing.assert_allclose(table.loc[~with_night, "min_soc_pct"], 100.0)
    assert table["survives"].all()
    assert (table.loc[with_night, "min_soc_utc"] == "2027-01-06T00:00").all()
    np.testing.assert_allclose(table.loc[with_night, "required_capacity_wh"], 480.0 / 0.8)
    np.testing.assert_allclose(table.loc[~with_night, "required_capacity_wh"], 0.0)
    np.testing.assert_allclose(table.loc[with_night, "sunlit_pct"], 50.0)
    np.testing.assert_allclose(table.loc[with_night, "longest_night_h"], 24.0)
    np.testing.assert_allclose(table.loc[~with_night, "longest_night_h"], 0.0)
    np.testing.assert_allclose(table["earth_pct"], 50.0)
    np.testing.assert_allclose(table["longest_earth_gap_h"], 12.0)
    # Day 3 (hours 72-119): Sun in 72-95, link in 72-83 -> 12 of 48 h.
    assert table.loc[table["landing_utc"] == pd.Timestamp("2027-01-04"), "sun_and_earth_pct"].item() == 25.0
    np.testing.assert_allclose(table.loc[~with_night, "sun_and_earth_pct"], 50.0)


def test_small_battery_fails_only_on_missions_with_the_night(series: dict) -> None:
    table = run(series, capacity_wh=500.0)  # usable 400 Wh < 480 Wh
    with_night = table["landing_utc"].isin(pd.to_datetime(["2027-01-04", "2027-01-05"]))
    assert (~table.loc[with_night, "survives"]).all()
    assert table.loc[~with_night, "survives"].all()
    assert table.loc[with_night, "first_violation_utc"].notna().all()
    assert table.loc[~with_night, "first_violation_utc"].isna().all()
    # The verdict agrees with the required capacity.
    np.testing.assert_array_equal(table["survives"], table["required_capacity_wh"] <= 500.0)


def test_landing_range_and_step(series: dict) -> None:
    table = run(series, landing_step_h=48.0, first_landing_utc="2027-01-02", last_landing_utc="2027-01-08")
    assert table["landing_utc"].tolist() == list(pd.to_datetime(["2027-01-02", "2027-01-04", "2027-01-06", "2027-01-08"]))
    assert len(run(series, duration_h=240.0)) == 1  # one mission over the whole series
    # Hourly landings: the last mission (hours 192-239) ends exactly at the end of the series.
    hourly = run(series, landing_step_h=1.0)
    assert len(hourly) == 193
    assert hourly["landing_utc"].iloc[-1] == pd.Timestamp("2027-01-09T00")
    assert hourly["end_utc"].iloc[-1] == pd.Timestamp("2027-01-11T00")
    assert len(run(series, landing_step_h=1.0, last_landing_utc="2027-01-09T00")) == 193
    with pytest.raises(ValueError, match="ends after the series"):
        run(series, landing_step_h=1.0, last_landing_utc="2027-01-09T01")
    # Timestamps and datetime64 of another unit are accepted as landing times.
    assert len(run(series, first_landing_utc=pd.Timestamp("2027-01-08"))) == 2
    assert len(run(series, first_landing_utc=np.datetime64("2027-01-08T00:00:00.000000000"))) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration_h": 1.5},  # not a whole number of steps
        {"duration_h": 0.0},
        {"duration_h": 1.0},  # a mission needs at least two steps
        {"duration_h": 241.0},  # longer than the series
        {"landing_step_h": 0.0},
        {"first_landing_utc": "2027-01-01T00:30"},  # not a time of the series
        {"last_landing_utc": "2027-01-09T01"},  # its mission ends after the series
        {"first_landing_utc": "2027-01-05", "last_landing_utc": "2027-01-03"},
    ],
)
def test_bad_arguments_are_refused(series: dict, kwargs: dict) -> None:
    with pytest.raises(ValueError):
        run(series, **kwargs)


def test_inputs_of_different_length_are_refused(series: dict) -> None:
    with pytest.raises(ValueError):
        landing_table(series["times"], series["sun"][:-1], series["generation"], series["link"], system(),
                      duration_h=48.0)


# --- best dates ------------------------------------------------------------------------------


def test_best_dates_do_not_overlap_by_default(series: dict) -> None:
    table = run(series)
    best = best_landing_dates(table)
    # Ranked: full battery throughout, then the earliest; dates closer than one mission (48 h)
    # to a date already taken are skipped, so only four fit into the nine days.
    assert best["rank"].tolist() == [1, 2, 3, 4]
    assert best["landing_utc"].tolist() == list(pd.to_datetime(["2027-01-01", "2027-01-03", "2027-01-06", "2027-01-08"]))
    without_gap = best_landing_dates(table, min_separation_h=0.0)
    assert without_gap["landing_utc"].tolist() == list(
        pd.to_datetime(["2027-01-01", "2027-01-02", "2027-01-03", "2027-01-06", "2027-01-07"])
    )
    assert len(best_landing_dates(table, count=2)) == 2


def test_ranking_order_survival_then_margin_then_earth() -> None:
    landing = pd.to_datetime(["2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01", "2027-05-01"])
    table = pd.DataFrame(
        {
            "landing_utc": landing,
            "end_utc": landing + pd.Timedelta(days=14),
            "survives": [True, True, False, True, True],
            "min_soc_pct": [100.0, 100.0, 100.0, 90.0, 100.0],
            "earth_pct": [40.0, 60.0, 99.0, 99.0, 60.0],
        }
    )
    best = best_landing_dates(table)
    # Feb and May tie on survival, margin and Earth: the earlier comes first.
    assert best["landing_utc"].dt.month.tolist() == [2, 5, 1, 4, 3]
    assert best["rank"].tolist() == [1, 2, 3, 4, 5]
    assert best_landing_dates(table.iloc[0:0]).empty
    assert len(best_landing_dates(table, count=100)) == 5
    with pytest.raises(ValueError):
        best_landing_dates(table, count=0)
    # Any index works: shuffled, filtered or with repeated labels (tables of two sites joined).
    shuffled = table.sample(frac=1.0, random_state=3)
    pd.testing.assert_frame_equal(best_landing_dates(shuffled), best)
    repeated = table.set_axis([0, 0, 1, 1, 2])
    pd.testing.assert_frame_equal(best_landing_dates(repeated), best)
    assert best_landing_dates(table[table["survives"]])["landing_utc"].dt.month.tolist() == [2, 5, 1, 4]
    # Rounding noise in the margin does not hide a tie: Earth decides between Jan and Feb.
    noisy = table.assign(min_soc_pct=[100.0, 100.0 - 1e-9, 100.0, 90.0, 100.0 - 1e-9])
    assert best_landing_dates(noisy)["landing_utc"].dt.month.tolist() == [2, 5, 1, 4, 3]


# --- real site -------------------------------------------------------------------------------


@needs_kernels
@pytest.mark.skipif(not cache_path(HORIZON_DIR, "connecting_ridge", 2.0).is_file(), reason="needs the cached horizon")
def test_real_site_verdict_agrees_with_the_required_battery() -> None:
    profile = HorizonProfile.load(cache_path(HORIZON_DIR, "connecting_ridge", 2.0))
    times = np.arange(np.datetime64("2027-01-01T00"), np.datetime64("2027-04-01T00"), np.timedelta64(1, "h"))
    track = sky_track(profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m,
                      centre_ephemeris(times))
    vis = visibility(track, profile)
    with pytest.raises(ValueError, match="same times"):
        shorter = sky_track(profile.lat_rad, profile.lon_east_rad, profile.ground_height_m + profile.mast_height_m,
                            centre_ephemeris(times[:-1]))
        landing_windows(shorter, vis, system(2000.0), duration_h=14 * 24.0)
    table = landing_windows(track, vis, system(2000.0), duration_h=14 * 24.0)
    assert table["landing_utc"].iloc[0] == pd.Timestamp("2027-01-01")
    assert table["landing_utc"].iloc[-1] == pd.Timestamp("2027-03-18")  # last mission ends 2027-04-01
    np.testing.assert_array_equal(table["survives"], table["required_capacity_wh"] <= 2000.0 * (1 + 1e-9))
    assert (table.loc[table["survives"], "min_soc_pct"] >= 20.0 - 1e-6).all()
    assert table["survives"].any() and not table["survives"].all()  # the window is long enough to differ
    assert np.all(table["sun_and_earth_pct"] <= np.minimum(table["sunlit_pct"], table["earth_pct"]) + 1e-9)

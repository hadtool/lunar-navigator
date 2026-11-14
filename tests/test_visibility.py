"""Tests of lunarnav.visibility: disc fraction above the horizon and window statistics.

All profiles and tracks here are synthetic (built in the test), except the last test,
which uses the cached horizons and the SPICE kernels when they are available.
"""

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import ArrayLike

from lunarnav import ephemeris
from lunarnav.ephemeris import BodyTrack, SkyTrack, centre_ephemeris
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.visibility import (
    Visibility,
    centre_clearance,
    disc_fraction,
    longest_run,
    runs,
    segment_fraction,
    site_visibility,
    time_step_hours,
    visibility,
    window_metrics,
)

SUN_RADIUS = np.deg2rad(0.266)
EARTH_RADIUS = np.deg2rad(0.95)
HORIZON_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "horizons"


def make_profile(elevation_deg: ArrayLike) -> HorizonProfile:
    """Synthetic horizon: one elevation per 0.5 deg bin (or one value for all bins)."""
    elevation = np.deg2rad(np.broadcast_to(np.asarray(elevation_deg, dtype=float), (720,)).copy())
    return HorizonProfile(
        lat_rad=np.deg2rad(-89.0), lon_east_rad=0.0, ground_height_m=0.0, mast_height_m=2.0,
        max_range_m=300e3, azimuth_rad=np.arange(720) * np.deg2rad(0.5), elevation_rad=elevation,
        distance_m=np.full(720, 1000.0), covered_range_m=np.full(720, 300e3),
    )


def make_body(azimuth_deg: ArrayLike, elevation_deg: ArrayLike, radius_rad: float = SUN_RADIUS) -> BodyTrack:
    azimuth = np.deg2rad(np.atleast_1d(np.asarray(azimuth_deg, dtype=float)))
    elevation = np.deg2rad(np.atleast_1d(np.asarray(elevation_deg, dtype=float)))
    azimuth, elevation = np.broadcast_arrays(azimuth, elevation)
    return BodyTrack(azimuth, elevation, np.full(azimuth.shape, radius_rad), np.full(azimuth.shape, 1.5e11))


def hourly(count: int, start: str = "2027-01-01T00") -> np.ndarray:
    return np.datetime64(start) + np.arange(count) * np.timedelta64(1, "h")


def make_visibility(sun_fraction, earth_clearance_deg=None, earth_fraction=None) -> Visibility:
    sun_fraction = np.asarray(sun_fraction, dtype=float)
    count = sun_fraction.size
    clearance = np.deg2rad(np.full(count, 1.0) if earth_clearance_deg is None else np.asarray(earth_clearance_deg, float))
    fraction = (clearance > 0).astype(float) if earth_fraction is None else np.asarray(earth_fraction, float)
    return Visibility(hourly(count), sun_fraction, fraction, np.zeros(count), clearance)


# --- disc fraction -------------------------------------------------------------------------


def test_segment_fraction_known_values() -> None:
    np.testing.assert_allclose(segment_fraction([-5.0, -1.0, 0.0, 1.0, 5.0]), [0.0, 0.0, 0.5, 1.0, 1.0], atol=1e-12)
    # Segment of a unit circle cut half a radius below the centre: 1/2 + (sqrt(3)/4 + pi/6) / pi.
    assert segment_fraction(0.5) == pytest.approx(0.5 + (np.sqrt(3) / 4 + np.pi / 6) / np.pi)
    depth = np.linspace(-1.0, 1.0, 41)
    np.testing.assert_allclose(segment_fraction(depth) + segment_fraction(-depth), 1.0, atol=1e-12)
    assert np.all(np.diff(segment_fraction(depth)) > 0)


def test_disc_fraction_is_0_below_1_above_and_half_on_the_horizon() -> None:
    profile = make_profile(1.0)
    radius_deg = np.rad2deg(SUN_RADIUS)
    body = make_body(100.0, [1.0 - radius_deg - 0.001, 1.0 + radius_deg + 0.001, 1.0, -30.0, 40.0])
    np.testing.assert_allclose(disc_fraction(body, profile), [0.0, 1.0, 0.5, 0.0, 1.0], atol=1e-12)


@pytest.mark.parametrize("radius", [SUN_RADIUS, EARTH_RADIUS])
def test_disc_fraction_on_a_level_horizon_matches_the_segment_formula(radius: float) -> None:
    profile = make_profile(-0.7)
    depth = np.linspace(-1.2, 1.2, 97)
    body = make_body(250.0, -0.7 + np.rad2deg(radius) * depth, radius)
    np.testing.assert_allclose(disc_fraction(body, profile), segment_fraction(depth), atol=1e-3)


def test_disc_fraction_with_a_wall_on_one_side_of_the_disc() -> None:
    """Horizon far below on the left of azimuth 90 and far above on the right: half a disc."""
    azimuth_deg = np.arange(720) * 0.5
    profile = make_profile(np.where(azimuth_deg < 90.0, -5.0, 5.0))
    # Bin k covers [k/2 - 0.25, k/2 + 0.25) deg, so the wall starts at 89.75 deg.
    centred = make_body(89.75, 0.0)
    assert disc_fraction(centred, profile)[0] == pytest.approx(0.5, abs=0.02)
    assert disc_fraction(make_body(89.0, 0.0), profile)[0] == pytest.approx(1.0)
    assert disc_fraction(make_body(90.5, 0.0), profile)[0] == pytest.approx(0.0)
    # A quarter of the radius into the wall: the segment formula applied sideways.
    quarter = make_body(89.75 + 0.25 * np.rad2deg(SUN_RADIUS), 0.0)
    assert disc_fraction(quarter, profile)[0] == pytest.approx(float(segment_fraction(-0.25)), abs=0.02)


def test_disc_fraction_wraps_around_north() -> None:
    azimuth_deg = np.arange(720) * 0.5
    both_sides = make_profile(np.where((azimuth_deg < 2.0) | (azimuth_deg > 358.0), 3.0, -3.0))
    body = make_body([0.0, 359.9, 0.1, 180.0], 0.0, EARTH_RADIUS)
    np.testing.assert_allclose(disc_fraction(body, both_sides), [0.0, 0.0, 0.0, 1.0], atol=1e-12)
    # Wall only east of north, bins 0..3 (from -0.25 to 1.75 deg). A disc centred on its
    # edge at 359.75 deg is half hidden only if the strips beyond 360 deg wrap to bin 0.
    east_only = make_profile(np.where(azimuth_deg < 2.0, 3.0, -3.0))
    np.testing.assert_allclose(disc_fraction(make_body(359.75, 0.0), east_only), 0.5, atol=0.02)
    np.testing.assert_allclose(disc_fraction(make_body(-0.25, 0.0), east_only), 0.5, atol=0.02)
    # Same wall seen from the other side: its far edge at 1.75 deg.
    np.testing.assert_allclose(disc_fraction(make_body(1.75, 0.0), east_only), 0.5, atol=0.02)
    np.testing.assert_allclose(disc_fraction(make_body([359.0, 1.0], 0.0), east_only), [1.0, 0.0], atol=1e-12)


def test_disc_fraction_handles_empty_input_and_rejects_zero_strips() -> None:
    profile = make_profile(0.0)
    assert disc_fraction(make_body(np.array([]), np.array([])), profile).shape == (0,)
    with pytest.raises(ValueError):
        disc_fraction(make_body(0.0, 0.0), profile, strips=0)
    with pytest.raises(ValueError, match="positive"):
        disc_fraction(make_body(0.0, 0.0, radius_rad=0.0), profile)


def test_centre_clearance_is_elevation_minus_horizon() -> None:
    azimuth_deg = np.arange(720) * 0.5
    profile = make_profile(np.where(azimuth_deg < 180.0, 1.0, -2.0))
    clearance = centre_clearance(make_body([10.0, 200.0], [1.5, 0.0]), profile)
    np.testing.assert_allclose(np.rad2deg(clearance), [0.5, 2.0], atol=1e-12)


def test_visibility_rejects_a_profile_of_another_site() -> None:
    profile = make_profile(0.0)
    body = make_body([10.0, 20.0], 1.0)
    times = hourly(2)
    good = SkyTrack(profile.lat_rad, profile.lon_east_rad + 2 * np.pi, 2.0, times, body, body)
    result = visibility(good, profile)
    np.testing.assert_allclose(result.sun_fraction, 1.0)
    np.testing.assert_allclose(np.rad2deg(result.earth_clearance_rad), 1.0)
    other = SkyTrack(profile.lat_rad + 0.01, profile.lon_east_rad, 2.0, times, body, body)
    with pytest.raises(ValueError, match="different sites"):
        visibility(other, profile)


# --- runs and window statistics ------------------------------------------------------------


def test_runs_and_longest_run() -> None:
    mask = np.array([1, 1, 0, 1, 1, 1, 0, 0, 1], dtype=bool)
    assert runs(mask) == [(0, 2), (3, 6), (8, 9)]
    assert runs(np.zeros(4, dtype=bool)) == []
    assert runs(np.array([], dtype=bool)) == []
    times = hourly(mask.size)
    longest = longest_run(mask, times)
    assert (longest.hours, longest.start_utc, longest.reaches_window_edge) == (3.0, "2027-01-01T03:00", False)
    at_edge = longest_run(~mask[:8], times[:8])  # [0,0,1,0,0,0,1,1] -> run of 2 at the end
    assert (at_edge.hours, at_edge.reaches_window_edge) == (2.0, True)
    none = longest_run(np.zeros(5, dtype=bool), hourly(5))
    assert (none.hours, none.start_utc, none.reaches_window_edge) == (0.0, None, False)


def test_time_step_must_be_uniform() -> None:
    assert time_step_hours(hourly(5)) == 1.0
    assert time_step_hours(np.datetime64("2027-01-01T00") + np.arange(4) * np.timedelta64(30, "m")) == 0.5
    with pytest.raises(ValueError):
        time_step_hours(hourly(1))
    with pytest.raises(ValueError):
        time_step_hours(np.array(["2027-01-01T00", "2027-01-01T01", "2027-01-01T03"], dtype="datetime64[h]"))


def test_window_metrics_on_a_synthetic_series() -> None:
    #            hour: 0    1    2    3    4    5    6    7    8    9
    sun = np.array([1.0, 0.5, 0.0, 0.0, 0.0, 0.2, 1.0, 0.0, 0.0, 1.0])
    earth_deg = np.array([2.0, 2.0, 2.0, -1.0, -1.0, 0.3, 0.3, 2.0, 2.0, 2.0])
    earth_fraction = np.array([1, 1, 1, 0, 0, 0.6, 0.6, 1, 1, 1], dtype=float)
    metrics = window_metrics(make_visibility(sun, earth_deg, earth_fraction))
    assert (metrics.samples, metrics.step_hours) == (10, 1.0)
    assert (metrics.start_utc, metrics.stop_utc) == ("2027-01-01T00:00", "2027-01-01T10:00")
    assert metrics.sunlit_pct == pytest.approx(50.0)
    assert metrics.mean_sun_fraction_pct == pytest.approx(37.0)
    assert metrics.earth_pct == pytest.approx(80.0)
    assert metrics.earth_any_part_pct == pytest.approx(80.0)
    assert metrics.sun_and_earth_pct == pytest.approx(50.0)
    assert (metrics.longest_night.hours, metrics.longest_night.start_utc) == (3.0, "2027-01-01T02:00")
    assert not metrics.longest_night.reaches_window_edge
    assert (metrics.longest_earth_gap.hours, metrics.longest_earth_gap.start_utc) == (2.0, "2027-01-01T03:00")
    assert metrics.to_dict()["longest_night"]["hours"] == 3.0


def test_window_metrics_rules_and_window_limits() -> None:
    sun = np.array([1.0, 0.5, 0.0, 0.0, 0.0, 0.2, 1.0, 0.0, 0.0, 1.0])
    earth_deg = np.array([2.0, 2.0, 2.0, -1.0, -1.0, 0.3, 0.3, 2.0, 2.0, 2.0])
    vis = make_visibility(sun, earth_deg)
    strict = window_metrics(vis, sun_min_fraction=0.5, earth_margin_rad=np.deg2rad(0.5))
    assert strict.sunlit_pct == pytest.approx(30.0)  # fractions strictly above 0.5
    assert strict.earth_pct == pytest.approx(60.0)
    assert strict.earth_margin_deg == pytest.approx(0.5)
    assert strict.longest_earth_gap.hours == 4.0
    part = window_metrics(vis, "2027-01-01T02:00", "2027-01-01T07:00")
    assert (part.samples, part.start_utc, part.stop_utc) == (5, "2027-01-01T02:00", "2027-01-01T07:00")
    assert part.sunlit_pct == pytest.approx(40.0)
    assert part.longest_night.reaches_window_edge  # the night starts at the window start
    with pytest.raises(ValueError):
        window_metrics(vis, "2027-01-01T02:00", "2027-01-01T03:00")
    with pytest.raises(ValueError):
        window_metrics(vis, sun_min_fraction=1.0)
    # A window that sticks out of the series is refused instead of being shortened silently.
    with pytest.raises(ValueError, match="after the series"):
        window_metrics(vis, "2027-01-01T02:00", "2027-01-01T11:00")
    with pytest.raises(ValueError, match="before the series"):
        window_metrics(vis, "2026-12-31T23:00", "2027-01-01T05:00")
    whole = window_metrics(vis, "2027-01-01T00:00", "2027-01-01T10:00")
    assert whole.samples == 10


def test_all_dark_and_all_lit_windows() -> None:
    dark = window_metrics(make_visibility(np.zeros(24), np.full(24, -1.0)))
    assert (dark.sunlit_pct, dark.earth_pct, dark.sun_and_earth_pct) == (0.0, 0.0, 0.0)
    assert (dark.longest_night.hours, dark.longest_night.reaches_window_edge) == (24.0, True)
    lit = window_metrics(make_visibility(np.ones(24)))
    assert (lit.sunlit_pct, lit.earth_pct, lit.sun_and_earth_pct) == (100.0, 100.0, 100.0)
    assert (lit.longest_night.hours, lit.longest_night.start_utc) == (0.0, None)


# --- real horizons and ephemeris -----------------------------------------------------------


@pytest.mark.skipif(
    not all((ephemeris.kernel_dir() / name).is_file() for name in ephemeris.KERNEL_FILES)
    or not cache_path(HORIZON_DIR, "connecting_ridge", 2.0).is_file(),
    reason="needs the SPICE kernels and the cached horizons",
)
def test_real_site_statistics_are_consistent() -> None:
    times = np.arange(np.datetime64("2027-01-01T00"), np.datetime64("2027-07-01T00"), np.timedelta64(1, "h"))
    centre = centre_ephemeris(times)
    by_height = {
        height: site_visibility(HorizonProfile.load(cache_path(HORIZON_DIR, "connecting_ridge", height)), centre)
        for height in (2.0, 20.0)
    }
    low, high = (window_metrics(by_height[height]) for height in (2.0, 20.0))
    for metrics in (low, high):
        assert 0.0 < metrics.mean_sun_fraction_pct <= metrics.sunlit_pct < 100.0
        assert metrics.sun_and_earth_pct <= min(metrics.sunlit_pct, metrics.earth_pct)
        assert metrics.earth_pct <= metrics.earth_any_part_pct
        # Earth at the pole: visible roughly half of the time (libration), never all of it.
        assert 20.0 < metrics.earth_pct < 80.0
        assert metrics.longest_night.hours > 0.0
    # A higher mast never raises the horizon, so it cannot lose light.
    assert high.sunlit_pct >= low.sunlit_pct
    assert high.longest_night.hours <= low.longest_night.hours
    assert np.all(by_height[20.0].sun_fraction >= by_height[2.0].sun_fraction - 1e-3)

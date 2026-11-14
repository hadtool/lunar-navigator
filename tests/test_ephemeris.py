"""Tests of lunarnav.ephemeris against JPL Horizons and basic lunar geometry.

Reference tables in tests/data/horizons_*.txt are unmodified Horizons API responses
(pipeline/fetch_horizons_reference.py; query documented in docs/SOURCES.md).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import spiceypy as spice

from lunarnav import ephemeris
from lunarnav.ephemeris import centre_ephemeris, local_axes, site_vector_m, sky_track, sun_earth_track

DATA_DIR = Path(__file__).parent / "data"
ARCSEC = np.deg2rad(1.0 / 3600.0)
MONTHS = {name: number for number, name in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

# Agreement required with Horizons, degrees. Deliberately far below the size of stellar
# aberration (about 0.006 deg): dropping the aberration or light-time correction must fail.
# The observed agreement is 0.00003 deg at the polar sites and 0.0002 deg for Apollo 11.
HORIZONS_TOLERANCE_DEG = 5e-4

# name -> (latitude deg, east longitude deg, height m), as sent to Horizons.
HORIZONS_SITES = {
    "connecting_ridge": (-89.4441, 222.7090, 1955.7),
    "malapert_massif": (-85.9919, 2.0564, 5169.4),
    "apollo_11": (0.67416, 23.47314, 0.0),
}

pytestmark = pytest.mark.skipif(
    not all((ephemeris.kernel_dir() / name).is_file() for name in ephemeris.KERNEL_FILES),
    reason="SPICE kernels are not downloaded (see docs/SOURCES.md)",
)


def read_horizons(site: str, body: str) -> dict[str, np.ndarray]:
    """Parse time, azimuth, elevation (deg) and angular diameter (arcsec) from a table."""
    lines = (DATA_DIR / f"horizons_{site}_{body}.txt").read_text(encoding="utf-8").splitlines()
    rows = lines[lines.index("$$SOE") + 1 : lines.index("$$EOE")]
    times, azimuth, elevation, diameter = [], [], [], []
    for row in rows:
        cells = [cell.strip() for cell in row.split(",")]
        date, clock = cells[0].split()
        year, month, day = date.split("-")  # e.g. 2027-Jan-01; parsed without locale
        times.append(np.datetime64(f"{year}-{MONTHS[month]:02d}-{day}T{clock}", "s"))
        azimuth.append(float(cells[3]))
        elevation.append(float(cells[4]))
        diameter.append(float(cells[5]))
    return {
        "times": np.array(times),
        "azimuth_deg": np.array(azimuth),
        "elevation_deg": np.array(elevation),
        "diameter_arcsec": np.array(diameter),
    }


def track_for(site: str, times: np.ndarray) -> ephemeris.SkyTrack:
    lat_deg, lon_deg, height_m = HORIZONS_SITES[site]
    return sun_earth_track(np.deg2rad(lat_deg), np.deg2rad(lon_deg), height_m, times)


def angular_separation_deg(az1, el1, az2, el2) -> np.ndarray:
    """Great-circle distance between two directions given in degrees."""
    az1, el1, az2, el2 = map(np.deg2rad, (az1, el1, az2, el2))
    cos_sep = np.sin(el1) * np.sin(el2) + np.cos(el1) * np.cos(el2) * np.cos(az1 - az2)
    return np.rad2deg(np.arccos(np.clip(cos_sep, -1.0, 1.0)))


@pytest.mark.parametrize("site", ["connecting_ridge", "malapert_massif"])
@pytest.mark.parametrize("body", ["sun", "earth"])
def test_matches_horizons(site: str, body: str) -> None:
    reference = read_horizons(site, body)
    assert reference["times"].size >= 24
    computed = getattr(track_for(site, reference["times"]), body)
    azimuth_deg = np.rad2deg(computed.azimuth_rad)
    elevation_deg = np.rad2deg(computed.elevation_rad)

    separation = angular_separation_deg(
        azimuth_deg, elevation_deg, reference["azimuth_deg"], reference["elevation_deg"]
    )
    assert separation.max() < HORIZONS_TOLERANCE_DEG
    assert np.abs(elevation_deg - reference["elevation_deg"]).max() < HORIZONS_TOLERANCE_DEG
    # Near the horizon a great-circle error maps almost one to one into azimuth.
    azimuth_error = (azimuth_deg - reference["azimuth_deg"] + 180.0) % 360.0 - 180.0
    assert np.abs(azimuth_error).max() < 2 * HORIZONS_TOLERANCE_DEG


@pytest.mark.parametrize("correction", ["LT", "NONE"])
def test_horizons_tolerance_detects_missing_aberration(correction: str, monkeypatch) -> None:
    """Guard for the test above: a calculation without aberration must not pass it."""
    monkeypatch.setattr(ephemeris, "_ABERRATION_CORRECTION", correction)
    reference = read_horizons("connecting_ridge", "sun")
    sun = track_for("connecting_ridge", reference["times"]).sun
    separation = angular_separation_deg(
        np.rad2deg(sun.azimuth_rad), np.rad2deg(sun.elevation_rad),
        reference["azimuth_deg"], reference["elevation_deg"],
    )
    assert separation.max() > HORIZONS_TOLERANCE_DEG


@pytest.mark.parametrize("site", ["connecting_ridge", "malapert_massif"])
@pytest.mark.parametrize("body", ["sun", "earth"])
def test_angular_radius_matches_horizons(site: str, body: str) -> None:
    reference = read_horizons(site, body)
    computed = getattr(track_for(site, reference["times"]), body)
    radius_arcsec = computed.angular_radius_rad / ARCSEC
    # Horizons prints the angular diameter to 0.001 arcsec.
    np.testing.assert_allclose(2.0 * radius_arcsec, reference["diameter_arcsec"], rtol=2e-4)


def test_apollo_11_sun_elevation_at_landing() -> None:
    """Landing: 20 July 1969, 20:17:40 UTC.

    Published value: NASA SP-4029 "Apollo by the Numbers" (Apollo 11 summary) states that
    the launch window was planned for a Sun elevation of 10.8 deg at the landing site.
    It is a planned value, so the tolerance is 0.3 deg; Horizons gives the tight check.
    """
    reference = read_horizons("apollo_11", "sun")
    sun = track_for("apollo_11", reference["times"][:1]).sun
    elevation_deg = float(np.rad2deg(sun.elevation_rad[0]))
    assert elevation_deg == pytest.approx(10.8, abs=0.3)
    assert elevation_deg == pytest.approx(reference["elevation_deg"][0], abs=HORIZONS_TOLERANCE_DEG)
    # Morning Sun, almost due east: checks the clockwise-from-north azimuth convention.
    azimuth_deg = float(np.rad2deg(sun.azimuth_rad[0]))
    assert azimuth_deg == pytest.approx(reference["azimuth_deg"][0], abs=HORIZONS_TOLERANCE_DEG)
    assert 80.0 < azimuth_deg < 100.0


def test_apollo_11_earth_is_high_in_the_sky() -> None:
    reference = read_horizons("apollo_11", "earth")
    earth = track_for("apollo_11", reference["times"]).earth
    np.testing.assert_allclose(
        np.rad2deg(earth.elevation_rad), reference["elevation_deg"], atol=HORIZONS_TOLERANCE_DEG
    )
    assert np.rad2deg(earth.elevation_rad).min() > 50.0


@pytest.fixture(scope="module")
def year_at_polar_site() -> tuple[float, ephemeris.SkyTrack]:
    lat_deg = -89.4441
    times = np.arange(np.datetime64("2027-01-01T00"), np.datetime64("2028-01-01T00"), np.timedelta64(2, "h"))
    return lat_deg, sun_earth_track(np.deg2rad(lat_deg), np.deg2rad(222.7090), 0.0, times)


def test_sun_stays_near_horizon_at_pole(year_at_polar_site) -> None:
    """The lunar spin axis is tilted about 1.5 deg to the ecliptic normal."""
    lat_deg, track = year_at_polar_site
    elevation_deg = np.rad2deg(track.sun.elevation_rad)
    colatitude_deg = 90.0 - abs(lat_deg)
    assert elevation_deg.max() < colatitude_deg + 1.6
    assert elevation_deg.min() > -(colatitude_deg + 1.6)
    # The seasonal amplitude must actually be present, not just bounded.
    assert elevation_deg.max() > 1.0
    assert elevation_deg.min() < -1.0


def test_earth_librates_about_horizon_at_pole(year_at_polar_site) -> None:
    """Earth stays within roughly +-7 deg of the horizon (libration in latitude plus parallax)."""
    _, track = year_at_polar_site
    elevation_deg = np.rad2deg(track.earth.elevation_rad)
    assert 5.0 < elevation_deg.max() < 9.0
    assert -9.0 < elevation_deg.min() < -5.0
    # Unlike the Sun, the Earth does not circle the sky: it stays on the Earth-facing
    # side (towards longitude 0).
    earth_az = track.earth.azimuth_rad
    sun_az = track.sun.azimuth_rad
    assert np.ptp(np.unwrap(sun_az)) > 20 * np.pi  # Sun circles about 12 times a year
    assert np.ptp(np.unwrap(earth_az)) < 2 * np.pi


def test_angular_radii_are_physical(year_at_polar_site) -> None:
    _, track = year_at_polar_site
    sun_deg = np.rad2deg(track.sun.angular_radius_rad)
    earth_deg = np.rad2deg(track.earth.angular_radius_rad)
    assert 0.25 < sun_deg.min() < sun_deg.max() < 0.28
    assert 0.85 < earth_deg.min() < earth_deg.max() < 1.05
    assert 1.4e11 < track.sun.distance_m.min() < track.sun.distance_m.max() < 1.6e11
    assert 3.5e8 < track.earth.distance_m.min() < track.earth.distance_m.max() < 4.1e8


def test_local_axes_known_values() -> None:
    """Explicit anchors: orthonormality alone cannot tell east/north from their opposites."""
    np.testing.assert_allclose(
        local_axes(0.0, 0.0), [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]], atol=1e-15
    )
    half = np.sqrt(0.5)
    np.testing.assert_allclose(
        local_axes(np.deg2rad(45.0), np.deg2rad(90.0)),
        [[-1.0, 0.0, 0.0], [0.0, -half, half], [0.0, half, half]],
        atol=1e-15,
    )
    # South pole reached along the 0 deg meridian: "north" is the +X axis (longitude 0).
    np.testing.assert_allclose(
        local_axes(np.deg2rad(-90.0), 0.0), [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]], atol=1e-15
    )


def test_local_axes_are_orthonormal_and_right_handed() -> None:
    for lat_deg, lon_deg in [(-89.4, 222.7), (-85.0, 0.0), (0.7, 23.5), (45.0, 300.0), (-90.0, 0.0), (90.0, 137.0)]:
        east, north, up = local_axes(np.deg2rad(lat_deg), np.deg2rad(lon_deg))
        np.testing.assert_allclose(np.cross(east, north), up, atol=1e-12)
        for axis in (east, north, up):
            assert np.linalg.norm(axis) == pytest.approx(1.0)


@pytest.mark.parametrize("lon_deg", [0.0, 90.0, 222.7])
@pytest.mark.parametrize("pole_deg", [-90.0, 90.0])
def test_pole_is_continuous_along_every_meridian(pole_deg: float, lon_deg: float) -> None:
    lon = np.deg2rad(lon_deg)
    at_pole = local_axes(np.deg2rad(pole_deg), lon)
    near_pole = local_axes(np.deg2rad(pole_deg * (1 - 1e-9)), lon)
    np.testing.assert_allclose(at_pole, near_pole, atol=1e-7)
    times = np.array(["2027-03-01T00:00:00"], dtype="datetime64[s]")
    exact = sun_earth_track(np.deg2rad(pole_deg), lon, 0.0, times).sun
    beside = sun_earth_track(np.deg2rad(pole_deg * (1 - 1e-9)), lon, 0.0, times).sun
    assert abs(exact.azimuth_rad[0] - beside.azimuth_rad[0]) < 1e-6
    assert abs(exact.elevation_rad[0] - beside.elevation_rad[0]) < 1e-6


def test_site_vector_length_and_direction() -> None:
    vector = site_vector_m(np.deg2rad(-90.0), 0.0, 1000.0)
    np.testing.assert_allclose(vector, [0.0, 0.0, -(ephemeris.MOON_RADIUS_M + 1000.0)], atol=1e-6)
    vector = site_vector_m(0.0, np.deg2rad(90.0), 0.0)
    np.testing.assert_allclose(vector, [0.0, ephemeris.MOON_RADIUS_M, 0.0], atol=1e-6)


def test_height_changes_elevation_only_slightly_but_measurably() -> None:
    """Raising the observer by 20 m must not change the direction to the Sun noticeably."""
    times = np.array(["2027-03-01T00:00:00"], dtype="datetime64[s]")
    low = sun_earth_track(np.deg2rad(-89.4441), np.deg2rad(222.7090), 0.0, times)
    high = sun_earth_track(np.deg2rad(-89.4441), np.deg2rad(222.7090), 20.0, times)
    assert abs(high.sun.elevation_rad[0] - low.sun.elevation_rad[0]) < 1e-9
    assert abs(high.earth.elevation_rad[0] - low.earth.elevation_rad[0]) < 1e-6


def test_time_inputs_are_equivalent() -> None:
    lat, lon = np.deg2rad(-85.0), np.deg2rad(10.0)
    reference = sun_earth_track(lat, lon, 0.0, "2027-06-01T07:00:00").sun.azimuth_rad
    aware = datetime(2027, 6, 1, 12, 0, tzinfo=timezone(timedelta(hours=5)))
    variants = [
        np.array(["2027-06-01T07:00"], dtype="datetime64[m]"),
        np.array(["2027-06-01T07:00"], dtype="datetime64[ns]"),
        np.array(["2027-06-01T07:00"], dtype="datetime64[us]"),
        np.datetime64("2027-06-01T07:00:00"),
        datetime(2027, 6, 1, 7, 0),
        aware,
        pd.DatetimeIndex(["2027-06-01 07:00"]),
        pd.DatetimeIndex(["2027-06-01 12:00"], tz="Asia/Dushanbe"),
        ["2027-06-01T07:00:00Z"],
    ]
    for variant in variants:
        track = sun_earth_track(lat, lon, 0.0, variant)
        assert track.times_utc.shape == (1,)
        assert track.times_utc[0] == np.datetime64("2027-06-01T07:00:00")
        np.testing.assert_array_equal(track.sun.azimuth_rad, reference)


def test_empty_time_array_gives_empty_track() -> None:
    track = sun_earth_track(np.deg2rad(-85.0), 0.0, 0.0, np.array([], dtype="datetime64[s]"))
    assert track.times_utc.size == 0
    assert track.sun.azimuth_rad.shape == (0,)
    assert track.earth.distance_m.shape == (0,)


def test_invalid_inputs_raise_value_error() -> None:
    lat, lon = np.deg2rad(-85.0), np.deg2rad(10.0)
    with pytest.raises(ValueError):
        sun_earth_track(np.deg2rad(95.0), lon, 0.0, "2027-06-01T12:00:00")
    with pytest.raises(ValueError):
        sun_earth_track(lat, lon, 0.0, np.array(["NaT"], dtype="datetime64[s]"))
    with pytest.raises(ValueError):
        sun_earth_track(lat, float("nan"), 0.0, "2027-06-01T12:00:00")
    with pytest.raises(ValueError):
        sun_earth_track(lat, lon, 0.0, np.zeros((2, 2), dtype="datetime64[s]"))
    with pytest.raises(ValueError, match="coverage"):
        sun_earth_track(lat, lon, 0.0, "2200-01-01T00:00:00")
    # The module must stay usable after a SPICE error.
    assert sun_earth_track(lat, lon, 0.0, "2027-06-01T12:00:00").sun.azimuth_rad.shape == (1,)


def test_et_conversion_matches_spice_utc2et() -> None:
    """Includes 1969 (before leap seconds) and both sides of the 2017-01-01 leap second."""
    texts = ["1969-07-20T20:17:40", "2016-12-31T23:59:59", "2017-01-01T00:00:00",
             "2027-06-01T12:00:00.250", "2029-12-31T23:00:00"]
    _, et = ephemeris.utc_to_et(texts)
    expected = [spice.utc2et(text) for text in texts]
    np.testing.assert_allclose(et, expected, rtol=0, atol=1e-6)


def test_sky_track_reuses_centre_ephemeris_for_many_sites() -> None:
    times = np.arange(np.datetime64("2027-01-01T00"), np.datetime64("2027-01-03T00"), np.timedelta64(6, "h"))
    centre = centre_ephemeris(times)
    for lat_deg, lon_deg, height in [(-89.4441, 222.709, 1955.7), (-85.9919, 2.0564, 5169.4)]:
        lat, lon = np.deg2rad(lat_deg), np.deg2rad(lon_deg)
        split = sky_track(lat, lon, height, centre)
        direct = sun_earth_track(lat, lon, height, times)
        np.testing.assert_array_equal(split.sun.azimuth_rad, direct.sun.azimuth_rad)
        np.testing.assert_array_equal(split.earth.elevation_rad, direct.earth.elevation_rad)
        assert (split.lat_rad, split.lon_east_rad, split.height_m) == (lat, lon, height)


def test_results_are_read_only() -> None:
    track = sun_earth_track(np.deg2rad(-85.0), 0.0, 0.0, "2027-06-01T12:00:00")
    with pytest.raises(ValueError):
        track.sun.elevation_rad[0] = 0.0


def test_concurrent_calls_give_the_single_thread_result() -> None:
    """SPICE is not thread-safe; the module serialises its SPICE calls."""
    lat, lon = np.deg2rad(-89.4441), np.deg2rad(222.709)
    times = np.arange(np.datetime64("2027-01-01T00"), np.datetime64("2027-03-01T00"), np.timedelta64(1, "h"))
    expected = sun_earth_track(lat, lon, 0.0, times)

    def work(_: int) -> ephemeris.SkyTrack:
        return sun_earth_track(lat, lon, 0.0, times)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, range(24)))
    for result in results:
        np.testing.assert_array_equal(result.sun.azimuth_rad, expected.sun.azimuth_rad)
        np.testing.assert_array_equal(result.earth.elevation_rad, expected.earth.elevation_rad)

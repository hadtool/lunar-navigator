"""Tests of lunarnav.horizon on synthetic terrain (no data files needed)."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import CRS, Geod, Transformer
from rasterio.transform import from_origin

from lunarnav.ephemeris import MOON_RADIUS_M, local_axes
from lunarnav.horizon import (
    FunctionTerrain,
    HorizonProfile,
    RasterTerrain,
    cache_path,
    horizon_profile,
    horizon_profiles,
    lat_lon_to_xy,
    ray_distances,
    sample_terrains,
)

R = MOON_RADIUS_M
SITE_LAT = np.deg2rad(-88.0)
SITE_LON = np.deg2rad(40.0)
LOLA_PROJ = "+proj=stere +lat_0=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"


def flat(x, y):
    return np.zeros(np.shape(x))


def polar_about_site(x, y, lat=SITE_LAT, lon=SITE_LON):
    """Great-circle distance (m) and bearing (rad, clockwise from north) from the site."""
    # Inverse south polar stereographic projection to unit vectors.
    rho2 = (x**2 + y**2) / (2.0 * R) ** 2
    unit = np.stack([y / (2.0 * R), x / (2.0 * R), np.full(np.shape(x), -0.5)], axis=-1)
    unit = unit * (2.0 / (1.0 + rho2))[..., None]
    unit[..., 2] = (rho2 - 1.0) / (1.0 + rho2)
    east, north, up = local_axes(lat, lon)
    distance = R * np.arccos(np.clip(unit @ up, -1.0, 1.0))
    bearing = np.mod(np.arctan2(unit @ east, unit @ north), 2.0 * np.pi)
    return distance, bearing


def expected_elevation(distance_m: float, point_height_m: float, observer_height_m: float) -> float:
    psi = distance_m / R
    return float(
        np.arctan2(
            (R + point_height_m) * np.cos(psi) - (R + observer_height_m),
            (R + point_height_m) * np.sin(psi),
        )
    )


def test_inverse_projection_helper_round_trips() -> None:
    x, y = lat_lon_to_xy(SITE_LAT, SITE_LON)
    distance, _ = polar_about_site(np.array([x]), np.array([y]))
    assert distance[0] < 0.2  # arccos near 1 limits the precision to centimetres


# --- projection and sampling -------------------------------------------------------------


@pytest.mark.parametrize(("lat_deg", "lon_deg"), [(-89.4441, 222.709), (-83.6, 59.0), (-60.0, 301.5), (-90.0, 0.0)])
def test_projection_matches_pyproj(lat_deg: float, lon_deg: float) -> None:
    transformer = Transformer.from_crs(
        CRS.from_proj4("+proj=longlat +R=1737400 +no_defs"), CRS.from_proj4(LOLA_PROJ), always_xy=True
    )
    expected = transformer.transform(lon_deg, lat_deg)
    np.testing.assert_allclose(lat_lon_to_xy(np.deg2rad(lat_deg), np.deg2rad(lon_deg)), expected, atol=1e-6)


def make_plane_raster(pixel: float = 10.0) -> tuple[RasterTerrain, callable]:
    def plane(x, y):
        return 0.01 * x - 0.02 * y + 5.0

    cols, rows = 40, 30
    x_left, y_top = 1000.0, 5000.0
    xs = x_left + (np.arange(cols) + 0.5) * pixel
    ys = y_top - (np.arange(rows) + 0.5) * pixel
    heights = plane(xs[None, :], ys[:, None]).astype(np.float32)
    return RasterTerrain(heights, x_left, y_top, pixel, name="plane"), plane


def test_raster_sampling_is_bilinear_and_pixel_centred() -> None:
    terrain, plane = make_plane_raster()
    rng = np.random.default_rng(1)
    x = rng.uniform(1010.0, 1390.0, 200)
    y = rng.uniform(4710.0, 4990.0, 200)
    np.testing.assert_allclose(terrain.sample(x, y), plane(x, y), atol=1e-3)
    # Exactly at a pixel centre the stored value is returned.
    assert terrain.sample(np.array([1005.0]), np.array([4995.0]))[0] == pytest.approx(plane(1005.0, 4995.0), abs=1e-4)


def test_raster_sampling_outside_is_nan() -> None:
    terrain, _ = make_plane_raster()
    left, bottom, right, top = terrain.bounds_m
    assert (left, bottom, right, top) == (1000.0, 4700.0, 1400.0, 5000.0)
    outside = terrain.sample(np.array([left - 1.0, right + 1.0, 1200.0]), np.array([4800.0, 4800.0, top + 1.0]))
    assert np.isnan(outside).all()


def test_raster_from_file_and_window(tmp_path: Path) -> None:
    terrain, plane = make_plane_raster()
    path = tmp_path / "plane.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=30, width=40, count=1, dtype="float32",
        crs=CRS.from_proj4(LOLA_PROJ).to_wkt(), transform=from_origin(1000.0, 5000.0, 10.0, 10.0),
    ) as dataset:
        dataset.write(terrain.heights_m, 1)
    x, y = np.array([1123.0, 1250.5]), np.array([4871.0, 4790.0])
    whole = RasterTerrain.from_file(path)
    assert whole.name == "plane.tif"
    assert whole.pixel_m == 10.0
    np.testing.assert_allclose(whole.sample(x, y), plane(x, y), atol=1e-3)
    window = RasterTerrain.from_file(path, bounds_m=(1100.0, 4750.0, 1300.0, 4900.0))
    assert window.heights_m.shape == (15, 20)
    np.testing.assert_allclose(window.sample(x, y), plane(x, y), atol=1e-3)
    with pytest.raises(ValueError):
        RasterTerrain.from_file(path, bounds_m=(9000.0, 9000.0, 9100.0, 9100.0))


def test_sample_terrains_prefers_the_first_terrain_with_data() -> None:
    fine, _ = make_plane_raster()
    coarse = FunctionTerrain(lambda x, y: np.full(np.shape(x), -100.0), pixel_m=40.0)
    x = np.array([1200.0, 2000.0])
    y = np.array([4800.0, 4800.0])
    heights = sample_terrains([fine, coarse], x, y)
    assert heights[0] == pytest.approx(0.01 * 1200.0 - 0.02 * 4800.0 + 5.0, abs=1e-3)
    assert heights[1] == -100.0


def test_ray_distances() -> None:
    distances = ray_distances(5.0, 300_000.0, growth=0.001)
    assert distances[0] == 5.0
    assert distances[-1] == pytest.approx(300_000.0)
    steps = np.diff(distances)
    assert (steps > 0).all()
    assert steps[:500] == pytest.approx(5.0)
    # Never coarser than 0.1 % of the distance (or the first step), and no jump at the
    # switch from constant to proportional steps.
    assert (steps <= np.maximum(5.0, 0.001 * distances[1:]) * (1 + 1e-9)).all()
    assert (steps[1:] / steps[:-1]).max() < 1.0011
    assert np.unique(distances).size == distances.size
    short = ray_distances(40.0, 1000.0)
    assert short[-1] <= 1000.0
    np.testing.assert_allclose(np.diff(short), 40.0)
    # Range shorter than the switch distance and not a multiple of the step.
    odd = ray_distances(5.0, 23.0)
    np.testing.assert_allclose(odd, [5.0, 10.0, 15.0, 20.0])
    with pytest.raises(ValueError):
        ray_distances(40.0, 10.0)


# --- horizon on a smooth sphere ----------------------------------------------------------


@pytest.mark.parametrize("mast_height", [2.0, 5.0, 10.0, 20.0])
def test_flat_sphere_horizon_is_the_geometric_dip(mast_height: float) -> None:
    profile = horizon_profile(
        SITE_LAT, SITE_LON, mast_height, [FunctionTerrain(flat, pixel_m=5.0)],
        azimuth_count=72, subrays=1, max_range_m=50_000.0,
    )
    dip = -np.arccos(R / (R + mast_height))
    assert dip == pytest.approx(-np.sqrt(2.0 * mast_height / R), rel=1e-3)
    np.testing.assert_allclose(profile.elevation_rad, dip, rtol=1e-4)
    # The horizon point is where the line of sight is tangent to the sphere.
    np.testing.assert_allclose(profile.distance_m, np.sqrt(2.0 * R * mast_height), rtol=0.02)
    assert profile.ground_height_m == 0.0


def test_flat_sphere_observer_on_the_surface_sees_horizon_at_zero() -> None:
    profile = horizon_profile(
        SITE_LAT, SITE_LON, 0.0, [FunctionTerrain(flat, pixel_m=5.0)],
        azimuth_count=36, subrays=1, max_range_m=20_000.0,
    )
    # Nearest sample at 5 m: elevation = -5 / (2 R).
    np.testing.assert_allclose(profile.elevation_rad, -5.0 / (2.0 * R), rtol=1e-9)


# --- single ridge ------------------------------------------------------------------------


def ring_ridge(distance_m: float, width_m: float, height_m: float, bearing_range_deg=None):
    def terrain(x, y):
        distance, bearing = polar_about_site(x, y)
        ridge = np.abs(distance - distance_m) <= 0.5 * width_m
        if bearing_range_deg is not None:
            low, high = np.deg2rad(bearing_range_deg)
            ridge &= (bearing >= low) & (bearing <= high)
        return np.where(ridge, height_m, 0.0)

    return terrain


@pytest.mark.parametrize(
    ("distance", "height", "mast"),
    [(20_000.0, 1_000.0, 2.0), (5_000.0, 300.0, 10.0), (120_000.0, 6_000.0, 0.0)],
)
def test_single_ridge_gives_the_expected_angle(distance: float, height: float, mast: float) -> None:
    width = 0.05 * distance
    profile = horizon_profile(
        SITE_LAT, SITE_LON, mast, [FunctionTerrain(ring_ridge(distance, width, height), pixel_m=10.0)],
        azimuth_count=36, subrays=1, max_range_m=1.5 * distance,
    )
    # The near edge of a flat-topped ridge is its highest point as seen from the site.
    near_edge = distance - 0.5 * width
    expected = expected_elevation(near_edge, height, mast)
    assert expected > 0
    np.testing.assert_allclose(profile.elevation_rad, expected, atol=2e-4)
    # Radial sampling can only place the edge late, never early.
    assert (profile.elevation_rad <= expected + 1e-9).all()
    np.testing.assert_allclose(profile.distance_m, near_edge, rtol=2e-3)


def test_ridge_in_the_east_appears_at_azimuth_90() -> None:
    """Checks the azimuth convention: clockwise from north, east = 90 deg."""
    terrain = FunctionTerrain(ring_ridge(10_000.0, 1_000.0, 500.0, bearing_range_deg=(70.0, 110.0)), pixel_m=10.0)
    profile = horizon_profile(SITE_LAT, SITE_LON, 2.0, [terrain], azimuth_count=360, subrays=1, max_range_m=20_000.0)
    azimuth_deg = np.rad2deg(profile.azimuth_rad)
    ridge = expected_elevation(9_500.0, 500.0, 2.0)
    dip = -np.arccos(R / (R + 2.0))
    inside = (azimuth_deg >= 72.0) & (azimuth_deg <= 108.0)
    outside = (azimuth_deg <= 68.0) | (azimuth_deg >= 112.0)
    np.testing.assert_allclose(profile.elevation_rad[inside], ridge, atol=2e-4)
    np.testing.assert_allclose(profile.elevation_rad[outside], dip, rtol=1e-3)
    assert float(profile.elevation_at(np.deg2rad(90.0))) == pytest.approx(ridge, abs=2e-4)
    assert float(profile.elevation_at(np.deg2rad(270.0))) == pytest.approx(dip, rel=1e-3)


def test_subrays_catch_a_peak_between_bin_centres() -> None:
    """A peak 0.2 deg wide lying between two bin centres (bins of 1 deg)."""
    terrain = FunctionTerrain(ring_ridge(30_000.0, 2_000.0, 2_000.0, bearing_range_deg=(45.3, 45.5)), pixel_m=10.0)
    kwargs = dict(azimuth_count=360, max_range_m=40_000.0)
    centre_only = horizon_profile(SITE_LAT, SITE_LON, 2.0, [terrain], subrays=1, **kwargs)
    with_subrays = horizon_profile(SITE_LAT, SITE_LON, 2.0, [terrain], subrays=10, **kwargs)
    peak = expected_elevation(29_000.0, 2_000.0, 2.0)
    assert centre_only.elevation_rad.max() < 0
    assert with_subrays.elevation_rad[45] == pytest.approx(peak, abs=2e-4)
    assert with_subrays.elevation_rad[44] < 0 and with_subrays.elevation_rad[46] < 0
    # The default number of sub-rays (4, i.e. every 0.25 deg here) also finds it.
    default = horizon_profile(SITE_LAT, SITE_LON, 2.0, [terrain], **kwargs)
    assert default.elevation_rad[45] == pytest.approx(peak, abs=2e-4)


# --- observer height, layering, coverage -------------------------------------------------


def rough(x, y):
    return 300.0 * np.sin(x / 3_000.0) * np.cos(y / 2_000.0) + 0.02 * (x - y) / 10.0


def test_higher_mast_never_raises_the_horizon() -> None:
    terrain = [FunctionTerrain(rough, pixel_m=20.0)]
    kwargs = dict(azimuth_count=90, subrays=2, max_range_m=60_000.0)
    profiles = [horizon_profile(SITE_LAT, SITE_LON, h, terrain, **kwargs) for h in (0.0, 2.0, 5.0, 10.0, 20.0)]
    for lower, higher in zip(profiles, profiles[1:]):
        assert (higher.elevation_rad <= lower.elevation_rad + 1e-12).all()
    assert profiles[-1].elevation_rad.mean() < profiles[0].elevation_rad.mean()
    assert profiles[0].ground_height_m == pytest.approx(float(rough(*lat_lon_to_xy(SITE_LAT, SITE_LON))))


def test_site_height_and_first_step_come_from_the_finest_terrain() -> None:
    x0, y0 = lat_lon_to_xy(SITE_LAT, SITE_LON)
    pixel = 5.0
    size = 400  # 2 km square of constant height 50 m around the site
    fine = RasterTerrain(np.full((size, size), 50.0, dtype=np.float32), x0 - size * pixel / 2, y0 + size * pixel / 2, pixel, "fine")
    coarse = FunctionTerrain(flat, pixel_m=40.0, name="coarse")
    profile = horizon_profile(SITE_LAT, SITE_LON, 2.0, [fine, coarse], azimuth_count=36, subrays=1, max_range_m=30_000.0)
    assert profile.ground_height_m == pytest.approx(50.0)
    assert profile.terrain_names == ("fine", "coarse")
    # Standing on a 50 m mesa: the horizon is the mesa edge about 1 km away, slightly below 0.
    assert (profile.distance_m < 1_500.0).all()
    assert (profile.elevation_rad < 0).all()
    assert (profile.elevation_rad > -np.deg2rad(0.3)).all()
    np.testing.assert_allclose(profile.covered_range_m, 30_000.0)


def test_covered_range_reports_where_terrain_data_ends() -> None:
    def disc(x, y):
        distance, _ = polar_about_site(x, y)
        return np.where(distance <= 25_000.0, 0.0, np.nan)

    profile = horizon_profile(
        SITE_LAT, SITE_LON, 5.0, [FunctionTerrain(disc, pixel_m=10.0)],
        azimuth_count=36, subrays=1, max_range_m=60_000.0,
    )
    np.testing.assert_allclose(profile.covered_range_m, 25_000.0, rtol=2e-3)
    assert (profile.covered_range_m <= 25_000.0).all()


def test_invalid_arguments() -> None:
    terrain = [FunctionTerrain(flat, pixel_m=5.0)]
    with pytest.raises(ValueError):
        horizon_profile(SITE_LAT, SITE_LON, 2.0, [])
    with pytest.raises(ValueError):
        horizon_profile(np.deg2rad(10.0), SITE_LON, 2.0, terrain)
    with pytest.raises(ValueError):
        horizon_profile(SITE_LAT, SITE_LON, -1.0, terrain)
    with pytest.raises(ValueError, match="no terrain data at the site"):
        horizon_profile(SITE_LAT, SITE_LON, 2.0, [FunctionTerrain(lambda x, y: np.full(np.shape(x), np.nan), 5.0)])


# --- profile object ----------------------------------------------------------------------


def test_profile_round_trips_through_json(tmp_path: Path) -> None:
    profile = horizon_profile(
        SITE_LAT, SITE_LON, 5.0, [FunctionTerrain(rough, pixel_m=20.0)],
        azimuth_count=720, subrays=1, max_range_m=20_000.0,
    )
    path = cache_path(tmp_path / "horizons", "test_site", 5.0)
    assert path.name == "test_site_h5.json"
    profile.save(path)
    loaded = HorizonProfile.load(path)
    assert loaded.azimuth_rad.size == 720
    np.testing.assert_allclose(loaded.azimuth_rad, profile.azimuth_rad)
    np.testing.assert_allclose(loaded.elevation_rad, profile.elevation_rad, atol=np.deg2rad(1e-5))
    np.testing.assert_allclose(loaded.distance_m, profile.distance_m, atol=0.5)
    assert loaded.mast_height_m == 5.0
    assert loaded.lat_rad == pytest.approx(SITE_LAT)
    assert loaded.terrain_names == profile.terrain_names
    probe = np.deg2rad(np.array([0.1, 33.3, 179.9, 180.26, 359.8]))
    np.testing.assert_allclose(loaded.elevation_at(probe), profile.elevation_at(probe), atol=np.deg2rad(1e-5))


def four_bin_profile() -> HorizonProfile:
    azimuth = np.deg2rad(np.arange(0.0, 360.0, 90.0))
    return HorizonProfile(
        lat_rad=SITE_LAT, lon_east_rad=SITE_LON, ground_height_m=0.0, mast_height_m=0.0, max_range_m=1.0,
        azimuth_rad=azimuth, elevation_rad=np.array([0.0, 1.0, 2.0, 3.0]),
        distance_m=np.zeros(4), covered_range_m=np.zeros(4),
    )


def test_elevation_at_returns_the_value_of_the_containing_bin() -> None:
    """Bins are centred on 0, 90, 180, 270 deg and span +-45 deg."""
    profile = four_bin_profile()
    azimuth_deg = np.array([0.0, 44.0, 46.0, 90.0, 134.9, 135.1, 300.0, 315.1, 359.0, -90.0, 450.0])
    expected = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 2.0, 3.0, 0.0, 0.0, 3.0, 1.0])
    np.testing.assert_array_equal(profile.elevation_at(np.deg2rad(azimuth_deg)), expected)
    assert profile.elevation_at(np.deg2rad(46.0)).shape == ()


def test_elevation_at_can_interpolate_periodically() -> None:
    profile = four_bin_profile()
    assert float(profile.elevation_at(np.deg2rad(45.0), interpolate=True)) == pytest.approx(0.5)
    # Between 270 deg (3) and 360 deg (0).
    assert float(profile.elevation_at(np.deg2rad(315.0), interpolate=True)) == pytest.approx(1.5)
    assert float(profile.elevation_at(np.deg2rad(-90.0), interpolate=True)) == pytest.approx(3.0)
    assert float(profile.elevation_at(np.deg2rad(450.0), interpolate=True)) == pytest.approx(1.0)


def test_profiles_cannot_be_compared_by_accident() -> None:
    """Array fields make value equality ambiguous, so identity is used."""
    first, second = four_bin_profile(), four_bin_profile()
    assert first != second
    assert first == first


# --- independent geometry check ----------------------------------------------------------


@pytest.mark.parametrize(("lat_deg", "lon_deg"), [(-89.44, 222.7), (-85.0, 10.0), (-86.5, 300.0)])
def test_target_placed_with_pyproj_geodesics_appears_at_its_bearing(lat_deg: float, lon_deg: float) -> None:
    """Azimuth and distance checked against pyproj.Geod, which shares no code with the module."""
    geod = Geod(a=R, b=R)
    to_xy = Transformer.from_crs(
        CRS.from_proj4("+proj=longlat +R=1737400 +no_defs"), CRS.from_proj4(LOLA_PROJ), always_xy=True
    )
    for bearing_deg in (0.0, 57.0, 133.0, 250.0, 331.0):
        target_lon, target_lat, _ = geod.fwd(lon_deg, lat_deg, bearing_deg, 8_000.0)
        target_x, target_y = to_xy.transform(target_lon, target_lat)

        def disc(x, y, cx=target_x, cy=target_y):
            return np.where(np.hypot(x - cx, y - cy) <= 300.0, 1_000.0, 0.0)

        profile = horizon_profile(
            np.deg2rad(lat_deg), np.deg2rad(lon_deg), 2.0, [FunctionTerrain(disc, pixel_m=10.0)],
            azimuth_count=360, subrays=1, max_range_m=12_000.0,
        )
        peak_bin = int(np.argmax(profile.elevation_rad))
        assert peak_bin == int(round(bearing_deg)) % 360
        # Near edge of the disc: 7700 m (the projection is conformal, scale ~1 this close to the pole).
        assert profile.distance_m[peak_bin] == pytest.approx(7_700.0, rel=5e-3)
        assert profile.elevation_rad[peak_bin] == pytest.approx(expected_elevation(7_700.0, 1_000.0, 2.0), rel=5e-3)


# --- raster edge cases -------------------------------------------------------------------


def test_nan_pixel_only_affects_points_it_has_weight_in() -> None:
    heights = np.zeros((5, 5), dtype=np.float32)
    heights[2, 2] = np.nan
    terrain = RasterTerrain(heights, 0.0, 50.0, 10.0)
    # Pixel centres are at 5, 15, ..., 45 m; pixel (row 2, col 2) is centred on (25, 25).
    x = np.array([25.0, 15.0, 35.0, 15.0, 20.0, 5.0])
    y = np.array([25.0, 35.0, 15.0, 25.0, 25.0, 45.0])
    values = terrain.sample(x, y)
    assert np.isnan(values[0])           # the hole itself
    np.testing.assert_array_equal(values[[1, 2, 3, 5]], 0.0)  # exact neighbouring centres
    assert np.isnan(values[4])           # halfway into the hole


def test_points_within_half_a_pixel_of_the_edge_use_the_edge_pixels() -> None:
    terrain, plane = make_plane_raster()
    left, bottom, right, top = terrain.bounds_m
    # On the raster edge: value of the nearest pixel centre (5 m inside), no extrapolation.
    assert terrain.sample(np.array([left]), np.array([top]))[0] == pytest.approx(plane(left + 5.0, top - 5.0), abs=1e-3)
    assert terrain.sample(np.array([right]), np.array([bottom]))[0] == pytest.approx(plane(right - 5.0, bottom + 5.0), abs=1e-3)
    assert np.isnan(terrain.sample(np.array([left - 0.01]), np.array([top]))[0])


def test_from_file_clips_bounds_and_rejects_other_projections(tmp_path: Path) -> None:
    terrain, plane = make_plane_raster()
    path = tmp_path / "plane.tif"
    profile = dict(driver="GTiff", height=30, width=40, count=1, dtype="float32",
                   transform=from_origin(1000.0, 5000.0, 10.0, 10.0))
    with rasterio.open(path, "w", crs=CRS.from_proj4(LOLA_PROJ).to_wkt(), **profile) as dataset:
        dataset.write(terrain.heights_m, 1)
    clipped = RasterTerrain.from_file(path, bounds_m=(900.0, 4900.0, 1100.0, 6000.0))
    assert clipped.bounds_m == (1000.0, 4900.0, 1100.0, 5000.0)
    assert clipped.sample(np.array([1050.0]), np.array([4950.0]))[0] == pytest.approx(plane(1050.0, 4950.0), abs=1e-3)

    north = tmp_path / "north.tif"
    wrong = "+proj=stere +lat_0=90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"
    with rasterio.open(north, "w", crs=CRS.from_proj4(wrong).to_wkt(), **profile) as dataset:
        dataset.write(terrain.heights_m, 1)
    with pytest.raises(ValueError, match="south polar stereographic"):
        RasterTerrain.from_file(north)

    # A false origin or a standard parallel away from the pole would shift or rescale the terrain.
    for index, changed in enumerate(["+x_0=1000 +y_0=0", "+x_0=0 +y_0=0 +lat_ts=-71"]):
        shifted = tmp_path / f"shifted_{index}.tif"
        proj = f"+proj=stere +lat_0=-90 +lon_0=0 {changed} +R=1737400 +units=m +no_defs"
        with rasterio.open(shifted, "w", crs=CRS.from_proj4(proj).to_wkt(), **profile) as dataset:
            dataset.write(terrain.heights_m, 1)
        with pytest.raises(ValueError, match="south polar stereographic"):
            RasterTerrain.from_file(shifted)


def test_gap_in_terrain_ends_the_covered_range() -> None:
    """Data in 0-10 km and again beyond 12 km: coverage is reported up to the first gap."""
    def with_gap(x, y):
        distance, _ = polar_about_site(x, y)
        return np.where((distance > 10_000.0) & (distance < 12_000.0), np.nan, 0.0)

    profile = horizon_profile(
        SITE_LAT, SITE_LON, 5.0, [FunctionTerrain(with_gap, pixel_m=10.0)],
        azimuth_count=36, subrays=1, max_range_m=30_000.0,
    )
    np.testing.assert_allclose(profile.covered_range_m, 10_000.0, rtol=2e-3)
    assert np.isfinite(profile.elevation_rad).all()


# --- several observer heights at once ----------------------------------------------------


def test_profiles_for_several_heights_equal_single_height_runs() -> None:
    terrain = [FunctionTerrain(rough, pixel_m=20.0)]
    kwargs = dict(azimuth_count=90, subrays=2, max_range_m=40_000.0)
    heights = [0.0, 2.0, 20.0]
    together = horizon_profiles(SITE_LAT, SITE_LON, heights, terrain, **kwargs)
    assert [profile.mast_height_m for profile in together] == heights
    for profile in together:
        alone = horizon_profile(SITE_LAT, SITE_LON, profile.mast_height_m, terrain, **kwargs)
        np.testing.assert_array_equal(profile.elevation_rad, alone.elevation_rad)
        np.testing.assert_array_equal(profile.distance_m, alone.distance_m)
        np.testing.assert_array_equal(profile.covered_range_m, alone.covered_range_m)
    with pytest.raises(ValueError):
        horizon_profiles(SITE_LAT, SITE_LON, [], terrain)
    with pytest.raises(ValueError):
        horizon_profiles(SITE_LAT, SITE_LON, [2.0, -1.0], terrain)

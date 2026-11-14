"""Tests of lunarnav.store and of the precomputed data written by pipeline/build.py (T12)."""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from lunarnav import ephemeris, horizon, store
from lunarnav.comms import comm_summary, default_comm_settings, link_mask
from lunarnav.ephemeris import CentreEphemeris
from lunarnav.mast import DEFAULT_MAST_HEIGHTS_M, default_mast_settings, mast_tradeoff
from lunarnav.power import default_power_system
from lunarnav.visibility import window_metrics
from lunarnav.windows import landing_windows

needs_kernels = pytest.mark.skipif(
    not all((ephemeris.kernel_dir() / name).is_file() for name in ephemeris.KERNEL_FILES),
    reason="SPICE kernels are not downloaded (see docs/SOURCES.md)",
)
needs_build = pytest.mark.skipif(
    not (store.EPHEMERIS_FILE.is_file() and store.METRICS_FILE.is_file()),
    reason="precomputed data missing; run pipeline/build.py",
)


def synthetic_centre(count: int = 50) -> CentreEphemeris:
    rng = np.random.default_rng(7)
    times = np.datetime64("2027-01-01T00:00", "ms") + np.arange(count) * np.timedelta64(1, "h")
    return CentreEphemeris(
        times_utc=times,
        et_s=rng.uniform(8.5e8, 8.6e8, count),
        sun_m=rng.normal(0.0, 1.5e11, (count, 3)),
        earth_m=rng.normal(0.0, 3.8e8, (count, 3)),
        sun_radius_m=695_700_000.0,
        earth_radius_m=6_378_136.6,
    )


def test_centre_ephemeris_round_trip_is_lossless(tmp_path) -> None:
    centre = synthetic_centre()
    path = tmp_path / "centre.parquet"
    store.save_centre_ephemeris(centre, path)
    loaded = store.load_centre_ephemeris(path)
    for name in ("times_utc", "et_s", "sun_m", "earth_m"):
        np.testing.assert_array_equal(getattr(loaded, name), getattr(centre, name), err_msg=name)
        assert not getattr(loaded, name).flags.writeable, name
    assert loaded.times_utc.dtype == np.dtype("datetime64[ms]")
    assert (loaded.sun_radius_m, loaded.earth_radius_m) == (centre.sun_radius_m, centre.earth_radius_m)
    assert not (tmp_path / "centre.parquet.tmp").exists()  # written atomically
    with pytest.raises(FileNotFoundError):
        store.load_centre_ephemeris(tmp_path / "missing.parquet")


def test_foreign_or_imprecise_ephemeris_files_are_refused(tmp_path) -> None:
    centre = synthetic_centre()
    # Times finer than 1 ms would be truncated: refused instead.
    with pytest.raises(ValueError, match="datetime64"):
        store.save_centre_ephemeris(
            CentreEphemeris(centre.times_utc.astype("datetime64[ns]"), centre.et_s, centre.sun_m, centre.earth_m,
                            centre.sun_radius_m, centre.earth_radius_m),
            tmp_path / "ns.parquet",
        )
    # A Parquet file without our metadata, or without a column, is not read as an ephemeris.
    plain = tmp_path / "plain.parquet"
    pq.write_table(pa.table({"time_utc": pa.array(centre.times_utc), "et_s": centre.et_s}), plain)
    with pytest.raises(ValueError, match="not a centre ephemeris"):
        store.load_centre_ephemeris(plain)
    good = tmp_path / "good.parquet"
    store.save_centre_ephemeris(centre, good)
    table = pq.read_table(good)
    pq.write_table(table.drop(["earth_z_m"]).replace_schema_metadata(table.schema.metadata), plain)
    with pytest.raises(ValueError, match="earth_z_m"):
        store.load_centre_ephemeris(plain)
    other_frame = json.loads(table.schema.metadata[b"lunarnav"]) | {"frame": "MOON_PA"}
    pq.write_table(table.replace_schema_metadata({b"lunarnav": json.dumps(other_frame).encode()}), plain)
    with pytest.raises(ValueError, match="frame"):
        store.load_centre_ephemeris(plain)


def test_horizon_heights_do_not_mix_sites_with_similar_names(tmp_path) -> None:
    names = ("de_gerlache_rim_h0", "de_gerlache_rim_h2.5", "de_gerlache_rim_2_h0", "x_haworth_h5", "x_h1", "a_h1_h5",
             "b[1]_h10")
    for name in names:
        (tmp_path / f"{name}.json").write_text("{}", encoding="utf-8")
    assert store.horizon_heights("de_gerlache_rim", tmp_path) == [0.0, 2.5]
    assert store.horizon_heights("de_gerlache_rim_2", tmp_path) == [0.0]
    assert store.horizon_heights("x", tmp_path) == [1.0]
    assert store.horizon_heights("a", tmp_path) == []  # "a_h1_h5" belongs to a site "a_h1"
    assert store.horizon_heights("a_h1", tmp_path) == [5.0]
    assert store.horizon_heights("b[1]", tmp_path) == [10.0]  # glob characters in a site id
    assert store.horizon_heights("nowhere", tmp_path) == []
    with pytest.raises(FileNotFoundError):
        store.load_horizon("nowhere", 2.0, tmp_path)


def test_every_polar_site_has_every_height_of_the_settings() -> None:
    every = store.load_sites(polar_only=False)
    sites = store.load_sites()
    assert sites and all(site["role"] != "validation_only" for site in sites)
    assert len(every) - len(sites) == sum(site["role"] == "validation_only" for site in every)
    heights = default_mast_settings()[0].heights_m  # what pipeline/build.py builds
    for site in sites:
        assert set(heights) <= set(store.horizon_heights(site["id"])), site["id"]


@needs_build
def test_stored_ephemeris_covers_the_period_hourly() -> None:
    centre = store.load_centre_ephemeris()
    times = centre.times_utc
    assert times[0] == store.ANALYSIS_START
    assert times[-1] + np.timedelta64(1, "h") == store.EPHEMERIS_STOP
    assert times.size == 1127 * 24  # 2027, 2028 (leap year), 2029 and January 2030
    assert np.all(np.diff(times) == np.timedelta64(1, "h"))
    assert centre.sun_m.shape == centre.earth_m.shape == (times.size, 3)


@needs_build
@needs_kernels
def test_stored_ephemeris_equals_a_fresh_spice_run() -> None:
    stored = store.load_centre_ephemeris()
    sample = np.array([0, 1, 4_999, 13_000, stored.times_utc.size - 1])
    fresh = ephemeris.centre_ephemeris(stored.times_utc[sample])
    np.testing.assert_array_equal(fresh.times_utc, stored.times_utc[sample])
    np.testing.assert_array_equal(fresh.et_s, stored.et_s[sample])
    np.testing.assert_array_equal(fresh.sun_m, stored.sun_m[sample])
    np.testing.assert_array_equal(fresh.earth_m, stored.earth_m[sample])
    assert (fresh.sun_radius_m, fresh.earth_radius_m) == (stored.sun_radius_m, stored.earth_radius_m)


class _NoSpice:
    def __getattr__(self, name: str):
        raise AssertionError(f"SPICE was called ({name}) although the app must not need the kernels")


@needs_build
def test_app_chain_runs_without_kernels_and_terrain(monkeypatch, tmp_path) -> None:
    """Everything the app does, with SPICE and the terrain rasters made unusable."""
    monkeypatch.setattr(ephemeris, "spice", _NoSpice())
    monkeypatch.setenv(ephemeris.KERNEL_DIR_ENV, str(tmp_path))

    def no_terrain(*args, **kwargs):
        raise AssertionError("a terrain raster was opened although the app must not need it")

    monkeypatch.setattr(horizon.RasterTerrain, "from_file", no_terrain)

    centre = store.load_centre_ephemeris()
    profiles = [store.load_horizon("connecting_ridge", height) for height in DEFAULT_MAST_HEIGHTS_M]
    track, vis = store.observer(profiles[1], centre)
    metrics = window_metrics(vis, "2027-01-01", "2028-01-01")
    system, _ = default_power_system({})
    table = mast_tradeoff(profiles, centre, system, start_utc="2027-01-01", stop_utc="2028-01-01")
    calendar = landing_windows(track, vis, system, duration_h=14 * 24.0, last_landing_utc="2027-03-01")
    assert table["sunlit_pct"].is_monotonic_increasing
    assert len(calendar) == 60
    # Same numbers as the stored metrics (and as the mast trade-off of T10).
    stored = store.load_metrics().set_index(["site", "mast_height_m", "period"])
    row = stored.loc[("connecting_ridge", 2.0, "2027")]
    assert row["sunlit_pct"] == pytest.approx(metrics.sunlit_pct, abs=1e-4)
    assert row["longest_night_h"] == metrics.longest_night.hours
    assert table.set_index("mast_height_m").loc[2.0, "sunlit_pct"] == pytest.approx(metrics.sunlit_pct)


@needs_build
def test_metrics_table_is_complete_and_consistent() -> None:
    metrics = store.load_metrics()
    sites = store.load_sites()
    assert len(metrics) == len(sites) * len(DEFAULT_MAST_HEIGHTS_M) * 4
    assert set(metrics["period"]) == {"2027-2029", "2027", "2028", "2029"}
    for column in ("sunlit_pct", "mean_sun_fraction_pct", "earth_link_pct", "earth_any_part_pct", "sun_and_earth_pct"):
        assert metrics[column].between(0.0, 100.0).all(), column
    assert (metrics["mean_sun_fraction_pct"] <= metrics["sunlit_pct"] + 1e-9).all()
    assert (metrics["sun_and_earth_pct"] <= np.minimum(metrics["sunlit_pct"], metrics["earth_link_pct"]) + 1e-9).all()
    # A centre rule with margin 0 is never more generous than "any part of the disc".
    assert (metrics["earth_link_pct"] <= metrics["earth_any_part_pct"] + 1e-9).all()
    # The three years add up to the whole period (2028 has 8784 hours).
    years = metrics[metrics["period"] != "2027-2029"].groupby(["site", "mast_height_m"])
    whole = metrics[metrics["period"] == "2027-2029"].set_index(["site", "mast_height_m"])
    weighted = years.apply(lambda group: np.average(group["sunlit_pct"], weights=group["hours"]))
    np.testing.assert_allclose(weighted.sort_index(), whole["sunlit_pct"].sort_index(), atol=1e-3)
    assert whole["hours"].eq(26_304.0).all()


@needs_build
@pytest.mark.parametrize("site_id", ["connecting_ridge", "haworth", "slater_plain"])
def test_metrics_rows_match_an_independent_recomputation(site_id: str) -> None:
    centre = store.load_centre_ephemeris()
    comm, _ = default_comm_settings()
    stored = store.load_metrics().set_index(["site", "mast_height_m", "period"])
    for height in (2.0, 10.0):
        track, vis = store.observer(store.load_horizon(site_id, height), centre)
        link = link_mask(vis, track.earth.angular_radius_rad, comm)
        times = np.asarray(track.times_utc)
        for period, start, stop in (("2027-2029", "2027-01-01", "2030-01-01"), ("2028", "2028-01-01", "2029-01-01")):
            row = stored.loc[(site_id, height, period)]
            selected = (times >= np.datetime64(start)) & (times < np.datetime64(stop))
            sunlit = vis.sun_fraction[selected] > 0.0
            summary = comm_summary(link[selected], times[selected], comm)
            assert row["hours"] == selected.sum()
            assert row["sunlit_pct"] == pytest.approx(100.0 * sunlit.mean(), abs=1e-4)
            assert row["mean_sun_fraction_pct"] == pytest.approx(100.0 * vis.sun_fraction[selected].mean(), abs=1e-4)
            assert row["earth_link_pct"] == pytest.approx(100.0 * link[selected].mean(), abs=1e-4)
            assert row["earth_any_part_pct"] == pytest.approx(100.0 * (vis.earth_fraction[selected] > 0).mean(), abs=1e-4)
            assert row["sun_and_earth_pct"] == pytest.approx(100.0 * (sunlit & link[selected]).mean(), abs=1e-4)
            assert row["longest_earth_gap_h"] == summary.longest_gap_h
            night = window_metrics(vis, start, stop).longest_night
            assert (row["longest_night_h"], row["longest_night_start_utc"]) == (night.hours, night.start_utc)


@needs_build
def test_processed_data_fits_the_size_budget() -> None:
    files = [path for path in store.PROCESSED_DIR.rglob("*") if path.is_file()]
    assert sum(path.stat().st_size for path in files) < 50 * 1024 * 1024
    manifest = pd.read_json(store.MANIFEST_FILE, typ="series")
    assert manifest["analysis_period_utc"] == ["2027-01-01T00:00:00.000", "2030-01-01T00:00:00.000"]

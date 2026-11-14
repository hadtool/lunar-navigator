"""Smoke tests of the Streamlit app (T13): every page runs without an exception on the precomputed data."""

import datetime as dt
import re
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lunarnav import ephemeris, horizon, store
from lunarnav.power import default_power_system, generation_from_track, required_capacity_wh

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
PAGES = ("views/site.py", "views/power.py", "views/mast.py", "views/compare.py", "views/landing.py",
         "views/methods.py")
pytestmark = pytest.mark.skipif(
    not (store.EPHEMERIS_FILE.is_file() and store.METRICS_FILE.is_file()),
    reason="precomputed data missing; run pipeline/build.py",
)


class _NoSpice:
    def __getattr__(self, name: str):
        raise AssertionError(f"the app called SPICE ({name}); it must work without the kernels")


@pytest.fixture(autouse=True)
def without_kernels_and_terrain(monkeypatch, tmp_path):
    """The deployed app has neither the SPICE kernels nor the terrain rasters."""
    monkeypatch.setattr(ephemeris, "spice", _NoSpice())
    monkeypatch.setenv(ephemeris.KERNEL_DIR_ENV, str(tmp_path))

    def no_terrain(*args, **kwargs):
        raise AssertionError("the app opened a terrain raster")

    monkeypatch.setattr(horizon.RasterTerrain, "from_file", no_terrain)


def run_app() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    assert not app.exception, [error.value for error in app.exception]
    return app


@pytest.mark.parametrize("page", PAGES)
def test_every_page_opens_without_errors(page: str) -> None:
    app = run_app()
    app.switch_page(page).run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.title, f"{page} shows no title"


def test_demo_scenario_three_clicks() -> None:
    """Pick a site, open the mast trade-off, give the lander a bigger battery: the verdict flips."""
    app = run_app()
    app.sidebar.selectbox[0].set_value("malapert_massif").run()  # click 1: site
    assert not app.exception
    assert app.title[0].value == "Malapert Massif"
    app.switch_page("views/mast.py").run()  # click 2: mast trade-off
    assert not app.exception
    assert "Malapert Massif" in app.caption[0].value
    assert "90 % of the gain in sunlight is reached at" in app.info[0].value
    app.switch_page("views/power.py").run()
    assert "Does not survive" in app.error[0].value  # placeholder 1000 Wh battery, year 2027
    started = time.perf_counter()
    app.slider(key="battery_capacity_wh").set_value(20000.0).run()  # click 3: a bigger battery
    elapsed = time.perf_counter() - started
    assert not app.exception
    assert app.session_state.battery_capacity_wh == 20000.0
    assert "Survives" in app.success[0].value  # 12 228 Wh are needed at 2 m (docs/VALIDATION.md, T10)
    assert elapsed < 2.0, f"recomputation took {elapsed:.2f} s"


def test_a_battery_that_no_size_can_save_is_said_so() -> None:
    """Charge at landing below the allowed minimum: the required capacity is infinite."""
    app = run_app()
    app.session_state.battery_initial_soc = 0.1
    app.session_state.battery_max_dod = 0.1
    for page in ("views/power.py", "views/mast.py", "views/compare.py"):
        app.switch_page(page).run()
        assert not app.exception, page
        texts = [element.value for kind in (app.metric, app.info, app.caption, app.markdown) for element in kind]
        assert not any(re.search(r"\binf\b", str(text)) for text in texts), page
    app.switch_page("views/power.py").run()
    needed = next(metric for metric in app.metric if metric.label == "Battery needed")
    assert needed.value == "no size is enough"


def test_odd_windows_and_a_fixed_panel() -> None:
    app = run_app()
    app.sidebar.date_input[0].set_value((dt.date(2028, 6, 1),)).run()  # one date while picking a range
    for page in PAGES:
        app.switch_page(page).run()
        assert not app.exception, page
    app.sidebar.date_input[0].set_value((dt.date(2029, 12, 1), dt.date(2029, 12, 31))).run()
    app.session_state.panel_type = "fixed"
    app.session_state.panel_fixed_azimuth_deg = 135.0
    app.session_state.mission_days = 60
    for page in ("views/power.py", "views/landing.py"):
        app.switch_page(page).run()
        assert not app.exception, page
    assert any("limited by the end of the precomputed data" in caption.value for caption in app.caption)


def test_site_and_height_change_and_numbers_match_the_library() -> None:
    app = run_app()
    app.sidebar.selectbox[0].set_value("haworth").run()
    app.sidebar.select_slider[0].set_value(10.0).run()
    app.switch_page("views/power.py").run()
    assert not app.exception
    centre = store.centre_window(store.load_centre_ephemeris(), "2027-01-01", "2028-01-01")
    track, vis = store.observer(store.load_horizon("haworth", 10.0), centre)
    system, _ = default_power_system()
    generation = generation_from_track(system, track.sun, vis.sun_fraction)
    needed = required_capacity_wh(system, track.times_utc, generation, vis.sun_fraction)
    shown = next(metric for metric in app.metric if metric.label == "Battery needed")
    assert shown.value == f"{needed:,.0f} Wh" == "15,284 Wh"  # as in the T10 table (docs/VALIDATION.md)
    app.sidebar.selectbox[0].set_value("connecting_ridge").run()
    app.switch_page("views/site.py").run()
    assert not app.exception
    assert app.session_state.mast_height_m == 10.0
    sunlit = next(metric for metric in app.metric if metric.label == "Sun visible")
    assert sunlit.value == "95.1 %"  # Connecting Ridge, 10 m, 2027 (T10)


@pytest.mark.parametrize("page", ["views/power.py", "views/mast.py", "views/landing.py", "views/compare.py"])
def test_three_years_recompute_quickly(page: str) -> None:
    """With the whole 2027-2029 window, a parameter change reruns the page in under 2 s."""
    app = run_app()
    app.sidebar.date_input[0].set_value((dt.date(2027, 1, 1), dt.date(2029, 12, 31))).run()
    app.switch_page(page).run()  # first run fills the visibility cache
    assert not app.exception
    started = time.perf_counter()
    app.session_state.load_night_w = 30.0
    app.run()
    elapsed = time.perf_counter() - started
    assert not app.exception
    assert elapsed < 2.0, f"{page}: {elapsed:.2f} s"


def test_power_values_survive_a_page_change() -> None:
    app = run_app()
    app.switch_page("views/power.py").run()
    app.slider(key="load_night_w").set_value(35.0).run()
    app.switch_page("views/compare.py").run()
    app.switch_page("views/power.py").run()
    assert not app.exception
    assert app.session_state.load_night_w == 35.0

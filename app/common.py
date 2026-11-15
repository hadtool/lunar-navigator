"""Shared state, cached data and chart helpers of the Streamlit app.

Everything is computed from the precomputed files in data/processed (lunarnav.store): no
terrain rasters and no SPICE kernels are needed. Heavy steps (visibility of a site over a
window) are cached; power and link statistics are recomputed on every change, which takes
milliseconds.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # works also when the package is not installed
    sys.path.insert(0, str(ROOT / "src"))

from lunarnav import store  # noqa: E402
from lunarnav.comms import RULE_ANY_PART, RULE_CENTRE, RULE_FULL_DISC, CommSettings, default_comm_settings  # noqa: E402
from lunarnav.ephemeris import CentreEphemeris, SkyTrack  # noqa: E402
from lunarnav.horizon import HorizonProfile, lat_lon_to_xy  # noqa: E402
from lunarnav.inputs import load_engineering_inputs  # noqa: E402
from lunarnav.mast import MIN_MEANINGFUL_HEIGHT_M, ObserverSeries, default_mast_settings  # noqa: E402
from lunarnav.power import (  # noqa: E402
    DAY_LOAD_POWER,
    DAY_LOAD_SUN_VISIBLE,
    PANEL_FIXED,
    PANEL_TRACKING,
    PowerSystem,
    default_power_system,
)
from lunarnav.visibility import Visibility  # noqa: E402

# --- look ------------------------------------------------------------------------------------
# Reference palette of the dataviz guidance: categorical slots in fixed order, status colours
# only for verdicts (always with a word), muted greys for terrain and reference lines.
SUN = "#eb6834"
EARTH = "#2a78d6"
BATTERY = "#1baf7a"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
TERRAIN = "#898781"
TERRAIN_FILL = "rgba(137, 135, 129, 0.35)"
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"
MUTED = "#898781"

FIRST_DAY = dt.date(2027, 1, 1)
LAST_DAY = dt.date(2029, 12, 31)
DEFAULT_SITE = "connecting_ridge"
RULE_LABELS = {
    RULE_CENTRE: "Centre of the Earth's disc",
    RULE_FULL_DISC: "Whole disc",
    RULE_ANY_PART: "Any part of the disc",
}
#: The same rules inside a sentence.
RULE_PHRASES = {
    RULE_CENTRE: "the centre of the Earth's disc",
    RULE_FULL_DISC: "the whole disc of the Earth",
    RULE_ANY_PART: "any part of the Earth's disc",
}
#: What a battery size of "inf" means, wherever it is shown.
NO_BATTERY_IS_ENOUGH = "no size is enough"

#: Power parameters: (state key, label, unit, minimum, maximum, step) of the sliders. The
#: limits are slider ranges only; ranges written by the engineer in docs/ENGINEERING_INPUTS.md
#: ("min-max (default X)") replace them.
POWER_SLIDERS = (
    ("panel_area_m2", "Panel area", "m²", 0.1, 10.0, 0.1),
    ("panel_efficiency", "Panel efficiency", "fraction", 0.05, 0.45, 0.001),
    ("panel_losses", "Other generation losses (dust, temperature, converter)", "fraction", 0.0, 0.5, 0.01),
    ("battery_capacity_wh", "Battery capacity", "Wh", 100.0, 60000.0, 100.0),
    ("battery_max_dod", "Usable depth of discharge", "fraction", 0.1, 1.0, 0.05),
    ("battery_charge_efficiency", "Charge efficiency", "fraction", 0.5, 1.0, 0.01),
    ("battery_discharge_efficiency", "Discharge efficiency", "fraction", 0.5, 1.0, 0.01),
    ("battery_initial_soc", "State of charge at landing", "fraction", 0.1, 1.0, 0.05),
    ("battery_specific_energy_wh_per_kg", "Battery specific energy", "Wh/kg", 50.0, 400.0, 5.0),
    ("load_day_w", "Load while the Sun is visible", "W", 0.0, 1000.0, 5.0),
    ("load_night_w", "Load at night (survival mode, heaters)", "W", 0.0, 500.0, 1.0),
)
POWER_KEYS = tuple(item[0] for item in POWER_SLIDERS) + ("panel_type", "panel_fixed_azimuth_deg", "day_load_rule")
DAY_LOAD_RULES = {
    DAY_LOAD_POWER: "Day mode only while the panel covers the day load",
    DAY_LOAD_SUN_VISIBLE: "Day mode whenever any part of the Sun is visible",
}
#: Widget keys that live on one page only but must survive page changes.
PERSISTENT_KEYS = POWER_KEYS + ("mission_days", "compare_sites", "mast_carries")
#: Values the power model accepts; ranges from the engineering inputs are clipped to them.
VALID_RANGES = {
    "panel_efficiency": (0.0, 1.0),
    "panel_losses": (0.0, 1.0),
    "battery_max_dod": (0.01, 1.0),
    "battery_charge_efficiency": (0.01, 1.0),
    "battery_discharge_efficiency": (0.01, 1.0),
    "battery_initial_soc": (0.0, 1.0),
    "battery_specific_energy_wh_per_kg": (1.0, float("inf")),
}


# --- cached data -------------------------------------------------------------------------------


@st.cache_resource(show_spinner="Loading the precomputed ephemeris ...")
def centre_full() -> CentreEphemeris:
    return store.load_centre_ephemeris()


@st.cache_resource(show_spinner=False, max_entries=32)
def centre_for(start: str, stop: str) -> CentreEphemeris:
    return store.centre_window(centre_full(), start, stop)


@st.cache_data(show_spinner=False)
def sites() -> list[dict]:
    return store.load_sites()


def site(site_id: str) -> dict:
    return next(item for item in sites() if item["id"] == site_id)


@st.cache_resource(show_spinner=False, max_entries=128)
def profile(site_id: str, height_m: float) -> HorizonProfile:
    return store.load_horizon(site_id, height_m)


@st.cache_resource(show_spinner="Computing Sun and Earth visibility ...", max_entries=64)
def observer(site_id: str, height_m: float, start: str, stop: str) -> tuple[SkyTrack, Visibility]:
    return store.observer(profile(site_id, height_m), centre_for(start, stop))


def mast_series(site_id: str, heights: tuple[float, ...], start: str, stop: str) -> list[ObserverSeries]:
    return [ObserverSeries(height, *observer(site_id, height, start, stop)) for height in heights]


@st.cache_data(show_spinner=False)
def metrics_table():
    return store.load_metrics()


@st.cache_data(show_spinner=False)
def mast_settings() -> tuple[tuple[float, ...], str, tuple[str, ...]]:
    settings, placeholders = default_mast_settings()
    return settings.heights_m, settings.carries, placeholders


def heights_for(site_id: str) -> list[float]:
    """Mast heights of the engineering inputs that have a cached horizon for the site."""
    available = set(store.horizon_heights(site_id))
    return [height for height in mast_settings()[0] if height in available]


@st.cache_data(show_spinner=False)
def basemap() -> tuple[str, list[float]] | None:
    """South-pole shaded relief as a data URI and its extent [x0, x1, y0, y1] in km, if built."""
    image = store.PROCESSED_DIR / "basemap" / "south_pole_relief.png"
    meta = image.with_suffix(".json")
    if not (image.is_file() and meta.is_file()):
        return None
    extent = json.loads(meta.read_text(encoding="utf-8"))["extent_km"]
    return "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii"), extent


# --- state -----------------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _defaults() -> dict:
    """Default widget values from docs/ENGINEERING_INPUTS.md and the placeholders in use."""
    system, power_placeholders = default_power_system()
    comm, comm_placeholders = default_comm_settings()
    values = {key: float(getattr(system, key)) for key, *_ in POWER_SLIDERS}
    values["panel_type"] = system.panel_type
    values["panel_fixed_azimuth_deg"] = float(np.rad2deg(system.panel_fixed_azimuth_rad))
    values["day_load_rule"] = system.day_load_rule
    values["comm_rule"] = comm.rule
    values["comm_margin_deg"] = float(np.rad2deg(comm.margin_rad))
    return {"values": values, "power_placeholders": power_placeholders, "comm_placeholders": comm_placeholders}


@st.cache_data(show_spinner=False)
def slider_limits() -> dict[str, tuple[float, float]]:
    """Slider ranges: the engineer's ranges where given, else the generic ones, widened to the default."""
    inputs = load_engineering_inputs()
    values = _defaults()["values"]
    limits = {}
    for key, _label, _unit, low, high, _step in POWER_SLIDERS:
        bounds = inputs[key].bounds() if key in inputs else None
        low, high = bounds if bounds else (low, high)
        valid_low, valid_high = VALID_RANGES.get(key, (0.0, float("inf")))
        low, high = max(min(low, values[key]), valid_low), min(max(high, values[key]), valid_high)
        limits[key] = (low, high if high > low else low + 1.0)
    return limits


def power_placeholders() -> tuple[str, ...]:
    return _defaults()["power_placeholders"]


def init_state() -> None:
    """Defaults for every key, and keep page-only widgets alive across page changes."""
    defaults = _defaults()["values"]
    state = st.session_state
    for key, value in defaults.items():
        state.setdefault(key, value)
    state.setdefault("site_id", DEFAULT_SITE)
    state.setdefault("dates", (FIRST_DAY, dt.date(2027, 12, 31)))
    for key in PERSISTENT_KEYS:  # Streamlit drops the state of widgets that are not drawn
        if key in state:
            state[key] = state[key]


def reset_power() -> None:
    for key in POWER_KEYS:
        st.session_state[key] = _defaults()["values"][key]


def power_system() -> PowerSystem:
    state = st.session_state
    return PowerSystem(
        panel_area_m2=float(state.panel_area_m2),
        panel_efficiency=float(state.panel_efficiency),
        battery_capacity_wh=float(state.battery_capacity_wh),
        load_day_w=float(state.load_day_w),
        load_night_w=float(state.load_night_w),
        panel_type=state.panel_type,
        panel_fixed_azimuth_rad=float(np.deg2rad(state.panel_fixed_azimuth_deg)),
        panel_losses=float(state.panel_losses),
        battery_max_dod=float(state.battery_max_dod),
        battery_charge_efficiency=float(state.battery_charge_efficiency),
        battery_discharge_efficiency=float(state.battery_discharge_efficiency),
        battery_initial_soc=float(state.battery_initial_soc),
        battery_specific_energy_wh_per_kg=float(state.battery_specific_energy_wh_per_kg),
        day_load_rule=state.day_load_rule,
    )


def power_is_default() -> bool:
    defaults = _defaults()["values"]
    return all(st.session_state[key] == defaults[key] for key in POWER_KEYS)


def comm_settings() -> CommSettings:
    return CommSettings(st.session_state.comm_rule, float(np.deg2rad(st.session_state.comm_margin_deg)))


def window() -> tuple[str, str]:
    """Selected dates as [start, stop) strings; the stop is the day after the last day.

    While the user is picking a range the date input holds one date (a one-day window); an
    empty value falls back to the year 2027.
    """
    dates = tuple(st.session_state.get("dates") or ())
    if not dates:
        first, last = FIRST_DAY, dt.date(2027, 12, 31)
    else:
        first, last = dates[0], dates[-1]
    return first.isoformat(), (last + dt.timedelta(days=1)).isoformat()


def window_label() -> str:
    start, stop = window()
    last = dt.date.fromisoformat(stop) - dt.timedelta(days=1)
    return f"{start} to {last.isoformat()} (UTC)"


# --- sidebar -----------------------------------------------------------------------------------


def sidebar() -> None:
    state = st.session_state
    names = {item["id"]: item["name"] for item in sites()}
    with st.sidebar:
        st.markdown("### Lunar Landing Site Navigator")
        st.caption("Light, Earth link and lander survival at the lunar south pole")
        st.selectbox("Landing site", list(names), format_func=names.get, key="site_id")
        heights = heights_for(state.site_id)
        if not heights:
            st.error("No precomputed horizon for this site; run pipeline/build.py.")
            st.stop()
        if state.get("mast_height_m") not in heights:
            state.mast_height_m = 2.0 if 2.0 in heights else heights[0]
        if len(heights) > 1:
            st.select_slider(
                "Panel and antenna height above the surface (mast), m", heights, key="mast_height_m",
                help="0 m is an observer on the terrain-model surface; its horizon is set by pixel-scale slopes "
                     "(docs/ASSUMPTIONS.md, A7). 2 m is the lowest height we consider meaningful.",
            )
        else:
            st.caption(f"Panel and antenna height: {heights[0]:g} m (the only precomputed height)")
        st.date_input("Dates (UTC)", min_value=FIRST_DAY, max_value=LAST_DAY, key="dates",
                      help="Window of the analysis; precomputed data cover 2027-2029.")
        with st.expander("Earth link rule"):
            st.selectbox("Earth counts as visible when", list(RULE_LABELS), format_func=RULE_LABELS.get,
                         key="comm_rule")
            st.slider("Margin above the terrain horizon, deg", 0.0, 10.0, step=0.5, key="comm_margin_deg")
            if _defaults()["comm_placeholders"]:
                st.caption("Defaults are estimates not reviewed by an engineer (docs/ASSUMPTIONS.md, A12).")
        if power_placeholders():
            st.caption(
                "⚠️ Lander power defaults come from public NASA sources, a solar-cell datasheet and a textbook sizing "
                "calculation; they are **not reviewed by an engineer** (A14). "
                "Survive / fail verdicts illustrate the method."
            )


def power_note() -> None:
    """One line under a power result that says whose numbers these are."""
    if power_placeholders() and power_is_default():
        st.caption("⚠️ Power system: default values from public sources and a sizing calculation, not reviewed by an "
                   "engineer (docs/ASSUMPTIONS.md, A14). Change them on the Power page.")
    else:
        system = power_system()
        st.caption(f"Power system set on the Power page: panel {system.panel_area_m2:g} m² at "
                   f"{100 * system.panel_efficiency:g} %, battery {system.battery_capacity_wh:,.0f} Wh, "
                   f"load {system.load_day_w:g} W / {system.load_night_w:g} W.")


# --- charts ------------------------------------------------------------------------------------


def presence(times: np.ndarray, mask: np.ndarray, row: float, color: str, name: str) -> go.Scattergl:
    """A row of bars where the mask is True: one thick line broken at the False samples."""
    return go.Scattergl(
        x=times, y=np.where(mask, row, np.nan), mode="lines", line={"color": color, "width": 16},
        name=name, connectgaps=False, hovertemplate="%{x|%Y-%m-%d %H:%M} UTC<extra>" + name + "</extra>",
    )


def site_xy_km(item: dict) -> tuple[float, float]:
    x, y = lat_lon_to_xy(np.deg2rad(item["lat_deg"]), np.deg2rad(item["lon_east_deg"]))
    return x / 1000.0, y / 1000.0


def finish(fig: go.Figure, height: int = 380, **layout) -> go.Figure:
    fig.update_layout(height=height, margin={"l": 10, "r": 30, "t": 40, "b": 10}, modebar={"orientation": "v"},
                      legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0}, **layout)
    return fig


def show(fig: go.Figure, **kwargs):
    return st.plotly_chart(fig, width="stretch", config={"displaylogo": False}, **kwargs)


def at_least_meaningful(heights: list[float]) -> list[float]:
    return [height for height in heights if height >= MIN_MEANINGFUL_HEIGHT_M]


def wh(value: float) -> str:
    """A battery size for display; inf means that no capacity survives the window."""
    return f"{value:,.0f} Wh" if np.isfinite(value) else NO_BATTERY_IS_ENOUGH


def kg(value_wh: float, specific_wh_per_kg: float | None) -> str:
    if not specific_wh_per_kg or not np.isfinite(value_wh):
        return "-"
    return f"{value_wh / specific_wh_per_kg:,.1f} kg"


PANEL_TYPES = {PANEL_TRACKING: "Tracking (turns to the Sun)", PANEL_FIXED: "Fixed, facing one azimuth"}

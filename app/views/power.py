"""Power: does the lander survive the selected dates with this power system?"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import common
from lunarnav.power import PANEL_FIXED, generation_from_track, required_capacity_wh, simulate

state = st.session_state
item = common.site(state.site_id)
start, stop = common.window()
track, vis = common.observer(state.site_id, state.mast_height_m, start, stop)

st.title("Power: does the lander survive?")
st.caption(f"{item['name']} · panel {state.mast_height_m:g} m above the surface · {common.window_label()}")
if common.power_placeholders():
    st.warning(
        "The starting values are **placeholders** chosen to exercise the model, not data of a real lander: "
        "the team's engineer has not filled in docs/ENGINEERING_INPUTS.md yet (docs/ASSUMPTIONS.md, A14). "
        "Set your own lander below; every verdict is recomputed at once.",
        icon="⚠️",
    )

limits = common.slider_limits()
spec = {key: (label, unit, step) for key, label, unit, _low, _high, step in common.POWER_SLIDERS}


FORMATS = {"Wh": "%.0f", "W": "%.0f", "Wh/kg": "%.0f", "m²": "%.1f", "fraction": "%.2f"}


def slider(key: str) -> None:
    label, unit, step = spec[key]
    low, high = limits[key]
    st.slider(f"{label}, {unit}" if unit != "fraction" else f"{label} (0-1)", float(low), float(high), step=float(step),
              format=FORMATS[unit], key=key)


panel_col, battery_col, load_col = st.columns(3)
with panel_col:
    st.markdown("**Solar panel** (vertical, at the top of the mast)")
    st.radio("Panel type", list(common.PANEL_TYPES), format_func=common.PANEL_TYPES.get, key="panel_type",
             horizontal=True)
    if state.panel_type == PANEL_FIXED:
        st.slider("Azimuth the panel faces, deg (clockwise from north)", 0.0, 359.0, step=1.0,
                  key="panel_fixed_azimuth_deg")
    for key in ("panel_area_m2", "panel_efficiency", "panel_losses"):
        slider(key)
with battery_col:
    st.markdown("**Battery**")
    for key in ("battery_capacity_wh", "battery_max_dod", "battery_initial_soc", "battery_charge_efficiency",
                "battery_discharge_efficiency", "battery_specific_energy_wh_per_kg"):
        slider(key)
with load_col:
    st.markdown("**Loads**")
    for key in ("load_day_w", "load_night_w"):
        slider(key)
    st.caption("The day load is drawn whenever any part of the Sun is visible, the night load otherwise "
               "(docs/ASSUMPTIONS.md, A15). Not modelled: temperatures, heater control, degradation, power "
               "limits of the battery (A16).")
    st.button("Reset to the engineering inputs", on_click=common.reset_power)

system = common.power_system()
times = np.asarray(track.times_utc)
generation = generation_from_track(system, track.sun, vis.sun_fraction)
result = simulate(system, times, generation, vis.sun_fraction)
needed = required_capacity_wh(system, times, generation, vis.sun_fraction)
allowed = system.battery_min_soc

if result.survives:
    st.success(f"**Survives** {common.window_label()}: the charge never falls below the allowed "
               f"{100 * allowed:.0f} %; lowest {100 * result.min_soc:.1f} % at "
               f"{result.min_energy_utc.replace('T', ' ')} UTC.", icon="✅")
else:
    st.error(f"**Does not survive**: the charge first falls below the allowed {100 * allowed:.0f} % at "
             f"{result.first_violation_utc.replace('T', ' ')} UTC; {result.unserved_wh:,.0f} Wh of load could not be "
             "supplied in the window.", icon="❌")

cols = st.columns(5)
cols[0].metric("Lowest charge", f"{100 * result.min_soc:.1f} %", border=True)
cols[1].metric("Battery needed", common.wh(needed), border=True,
               help="Smallest battery that survives the window with all other parameters as set (exact, no search)."
               if np.isfinite(needed) else
               "No battery capacity survives: the battery starts at or below its allowed minimum (state of charge "
               "at landing versus depth of discharge) while the window begins with a deficit.")
cols[2].metric("Its mass", common.kg(needed, system.battery_specific_energy_wh_per_kg), border=True,
               help="At the set specific energy of the battery.")
cols[3].metric("Mean generation", f"{generation.mean():,.0f} W", border=True,
               help="Average electrical power of the panel over the window, before battery limits.")
cols[4].metric("Unsupplied load", f"{result.unserved_wh / 1000:,.1f} kWh", border=True,
               help=f"Load that an empty battery could not supply. Energy generated "
                    f"{result.generated_wh / 1000:,.0f} kWh, asked by the loads {result.load_wh / 1000:,.0f} kWh, not "
                    f"stored because the battery was full {result.unused_generation_wh / 1000:,.0f} kWh.")

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.55, 0.45],
                    subplot_titles=("Battery state of charge, %", "Panel power and load, W"))
fig.add_trace(go.Scattergl(x=result.times_utc, y=100 * result.soc, mode="lines", name="State of charge",
                           line={"color": common.BATTERY, "width": 2},
                           hovertemplate="%{x|%Y-%m-%d %H:%M} UTC: %{y:.1f} %<extra></extra>"), row=1, col=1)
fig.add_hline(y=100 * allowed, line={"color": common.CRITICAL, "width": 1}, row=1, col=1,
              annotation_text=f"allowed minimum {100 * allowed:.0f} %", annotation_position="bottom right")
fig.add_trace(go.Scattergl(x=times, y=generation, mode="lines", name="Panel power",
                           line={"color": common.SUN, "width": 1.5, "shape": "hv"}, hovertemplate="%{x|%Y-%m-%d %H:%M} UTC: %{y:.0f} W<extra></extra>"),
              row=2, col=1)
fig.add_trace(go.Scattergl(x=times, y=result.load_w, mode="lines", name="Load",
                           line={"color": common.MUTED, "width": 1.5, "shape": "hv"}, hovertemplate="%{x|%Y-%m-%d %H:%M} UTC: %{y:.0f} W<extra></extra>"),
              row=2, col=1)
fig.update_yaxes(range=[0, 105], row=1, col=1)
fig.update_yaxes(rangemode="tozero", row=2, col=1)
common.finish(fig, height=520)
common.show(fig)
st.caption("Generation: P = S · (1 au / d)² · efficiency · (1 − losses) · area · visible share of the solar disc · "
           "cos(incidence), S = 1361 W/m², 1 h steps. A visible Sun is not yet guaranteed power: dust, "
           "temperature and the lander's own shadow are not modelled.")

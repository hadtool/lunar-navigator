"""Compare sites: two to four sites side by side for the same dates, mast height and lander."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import common
from lunarnav.comms import comm_summary, link_mask
from lunarnav.power import generation_from_track, required_capacity_wh, simulate
from lunarnav.visibility import window_metrics

state = st.session_state
start, stop = common.window()
height = state.mast_height_m
names = {item["id"]: item["name"] for item in common.sites()}
if "compare_sites" not in state:
    first = [state.site_id] + [site for site in ("malapert_massif", "haworth", "connecting_ridge") if site != state.site_id]
    state.compare_sites = first[:3]

st.title("Compare sites")
st.caption(f"Panel and antenna {height:g} m above the surface · {common.window_label()} · same lander for every site")
chosen = st.multiselect("Sites (2 to 4)", list(names), format_func=names.get, max_selections=4, key="compare_sites")
if len(chosen) < 2:
    st.info("Choose at least two sites.")
    st.stop()
missing = [site for site in chosen if height not in common.heights_for(site)]
if missing:
    st.warning(f"No horizon for {height:g} m at: {', '.join(names[s] for s in missing)}.")
    st.stop()

system = common.power_system()
comm = common.comm_settings()
rows = []
for site_id in chosen:
    track, vis = common.observer(site_id, height, start, stop)
    times = np.asarray(track.times_utc)
    metrics = window_metrics(vis)
    link = link_mask(vis, track.earth.angular_radius_rad, comm)
    gaps = comm_summary(link, times, comm)
    generation = generation_from_track(system, track.sun, vis.sun_fraction)
    result = simulate(system, times, generation, vis.sun_fraction)
    needed = required_capacity_wh(system, times, generation, vis.sun_fraction)
    rows.append({
        "Site": names[site_id],
        "Latitude, °S": round(abs(common.site(site_id)["lat_deg"]), 2),
        "Sun visible, %": metrics.sunlit_pct,
        "Mean visible solar disc, %": metrics.mean_sun_fraction_pct,
        "Longest night, h": metrics.longest_night.hours,
        "Earth link, %": gaps.visible_pct,
        "Longest Earth gap, h": gaps.longest_gap_h,
        "Sun and Earth together, %": 100.0 * np.mean((vis.sun_fraction > 0) & link),
        "Survives with the set battery": "yes" if result.survives else "no",
        "Lowest charge, %": 100.0 * result.min_soc,
        "Battery needed, Wh": needed,
        "Battery mass needed": common.kg(needed, system.battery_specific_energy_wh_per_kg),
    })
table = pd.DataFrame(rows)

bars = (("Sun visible, %", (0, 100)), ("Earth link, %", (0, 100)), ("Longest night, h", None),
        ("Battery needed, Wh", None))
fig = make_subplots(rows=1, cols=4, subplot_titles=[name for name, _ in bars], horizontal_spacing=0.06)
for index, (column, limits) in enumerate(bars, start=1):
    values = table[column].astype(float)
    finite = values[np.isfinite(values)]
    fig.add_trace(go.Bar(
        x=table["Site"], y=values.where(np.isfinite(values), np.nan), marker={"color": list(common.SERIES[:len(table)])},
        showlegend=False, textposition="outside", hovertemplate="%{x}: %{text}<extra>" + column + "</extra>",
        text=[("n/a" if not np.isfinite(value) else f"{value:,.0f}" if value >= 100 else f"{value:.1f}")
              for value in values],
    ), row=1, col=index)
    top = float(finite.max()) if len(finite) else 1.0
    fig.update_yaxes(range=list(limits) if limits else [0, 1.2 * max(top, 1.0)], row=1, col=index)
    fig.update_xaxes(tickangle=-25, row=1, col=index)
common.finish(fig, height=380, bargap=0.45)
common.show(fig)
common.power_note()

shown = table.assign(**{"Battery needed, Wh": table["Battery needed, Wh"].map(common.wh)})
st.dataframe(shown.set_index("Site").T.map(lambda value: f"{value:,.1f}" if isinstance(value, float) else value),
             width="stretch", height=36 * (len(table.columns)) + 4)
if not np.isfinite(table["Battery needed, Wh"].astype(float)).all():
    st.caption(f"'{common.NO_BATTERY_IS_ENOUGH}': with this state of charge at landing and depth of discharge no "
               "battery capacity survives the window.")

st.subheader("Horizons")
pano = go.Figure()
for color, site_id in zip(common.SERIES, chosen):
    prof = common.profile(site_id, height)
    azimuth = np.rad2deg(prof.azimuth_rad)
    pano.add_trace(go.Scatter(x=np.r_[azimuth, 360.0], y=np.r_[np.rad2deg(prof.elevation_rad), np.rad2deg(prof.elevation_rad[0])],
                              mode="lines", name=names[site_id], line={"color": color, "width": 1.6},
                              hovertemplate=names[site_id] + ": azimuth %{x:.1f}°, %{y:.2f}°<extra></extra>"))
pano.update_xaxes(range=[0, 360], tickvals=list(range(0, 361, 45)), title="Azimuth (clockwise from north)")
pano.update_yaxes(title="Terrain horizon, deg")
common.finish(pano, height=340)
common.show(pano)
st.caption("Near the pole the Sun and the Earth move close to the horizontal plane (the Sun never rises higher than "
           "90° − |latitude| + 1.6°, i.e. 2° to 8° at these sites), so a horizon difference of a fraction of a degree "
           "changes the light and link times strongly.")

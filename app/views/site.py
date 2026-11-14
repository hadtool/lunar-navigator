"""Site & dates: where the site is, what its horizon looks like, when the Sun and the Earth are in view."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import common
from lunarnav.comms import comm_summary, link_mask
from lunarnav.ephemeris import MOON_RADIUS_M
from lunarnav.visibility import window_metrics

state = st.session_state
item = common.site(state.site_id)
height = state.mast_height_m
start, stop = common.window()
comm = common.comm_settings()
track, vis = common.observer(state.site_id, height, start, stop)
times = np.asarray(track.times_utc)
metrics = window_metrics(vis)
link = link_mask(vis, track.earth.angular_radius_rad, comm)
link_stats = comm_summary(link, times, comm)
sunlit = vis.sun_fraction > 0.0


state.setdefault("map_nonce", 0)
MAP_KEY = f"site_map_{state.map_nonce}"


def _pick_site() -> None:
    """Map click: make the clicked site the selected one (runs before the next rerun).

    A new chart key afterwards clears the selection, so clicking the same site again later
    (after choosing another one in the sidebar) is seen as a new click.
    """
    event = st.session_state.get(MAP_KEY)
    points = (event or {}).get("selection", {}).get("points", [])
    if points:
        data = points[0].get("customdata")
        site_id = data[0] if isinstance(data, list | tuple) else data
        if site_id in {entry["id"] for entry in common.sites()}:
            st.session_state.site_id = site_id
            st.session_state.map_nonce += 1


st.title(item["name"])
flags = []
if item.get("artemis3_2024_candidate_region"):
    flags.append("Artemis III candidate region (NASA, Oct 2024)")
if item["role"] == "landed_mission":
    flags.append("landing site of a past mission")
if item.get("approximate"):
    flags.append("approximate position (centre of a terrain model)")
st.caption(
    f"{abs(item['lat_deg']):.4f}° S, {item['lon_east_deg']:.4f}° E · panel and antenna {height:g} m above the "
    f"surface · {common.window_label()}" + (" · " + " · ".join(flags) if flags else "")
)

cols = st.columns(6)
cols[0].metric("Sun visible", f"{metrics.sunlit_pct:.1f} %", border=True,
               help="Share of hours with any part of the solar disc above the terrain horizon (definition of the "
                    "LOLA illumination maps). A visible Sun is not yet guaranteed power.")
cols[1].metric("Visible disc", f"{metrics.mean_sun_fraction_pct:.1f} %", border=True,
               help="Average visible share of the solar disc over the window; the panel output scales with it "
                    "(and with the angle of incidence and the efficiency).")
night = metrics.longest_night
cols[2].metric("Longest night", f"{night.hours:.0f} h", border=True,
               help=(f"No part of the Sun visible, from {night.start_utc} UTC" if night.start_utc else "No night")
               + (". Touches the edge of the window: may be longer." if night.reaches_window_edge else "."))
cols[3].metric("Earth link", f"{link_stats.visible_pct:.1f} %", border=True,
               help=f"Line of sight to the Earth: {common.RULE_PHRASES[comm.rule]} above the terrain "
                    f"horizon by more than {np.rad2deg(comm.margin_rad):g}°. Not yet a closed radio link.")
cols[4].metric("Longest gap", f"{link_stats.longest_gap_h:.0f} h", border=True,
               help=(f"From {link_stats.longest_gap_start_utc} UTC" if link_stats.longest_gap_start_utc else "No gap")
               + (". Touches the edge of the window." if link_stats.longest_gap_reaches_period_edge else "."))
cols[5].metric("Sun + Earth", f"{100.0 * np.mean(sunlit & link):.1f} %", border=True,
               help="Hours with sunlight and Earth link at the same time.")

left, right = st.columns([1, 1.25])
with left:
    st.subheader("Sites at the lunar south pole")
    fig = go.Figure()
    relief = common.basemap()
    if relief:
        uri, (x0, x1, y0, y1) = relief
        fig.add_layout_image(source=uri, xref="x", yref="y", x=x0, y=y1, sizex=x1 - x0, sizey=y1 - y0,
                             sizing="stretch", layer="below", opacity=0.85)
    for lat in (89.0, 88.0, 86.0, 84.0):
        radius = 2.0 * MOON_RADIUS_M / 1000.0 * np.tan(np.deg2rad(90.0 - lat) / 2.0)
        angle = np.linspace(0.0, 2.0 * np.pi, 181)
        fig.add_trace(go.Scatter(x=radius * np.cos(angle), y=radius * np.sin(angle), mode="lines", hoverinfo="skip",
                                 line={"color": common.MUTED, "width": 0.8, "dash": "dot"}, showlegend=False))
        fig.add_annotation(x=0, y=-radius, text=f"{lat:g}° S", showarrow=False, yshift=-7,
                           font={"size": 9, "color": common.MUTED})
    groups = {
        "Artemis III candidate region": [s for s in common.sites() if s.get("artemis3_2024_candidate_region")],
        "Other site": [s for s in common.sites() if not s.get("artemis3_2024_candidate_region")],
    }
    for (label, members), color, symbol in zip(groups.items(), (common.EARTH, common.SUN), ("circle", "diamond")):
        xy = np.array([common.site_xy_km(s) for s in members])
        fig.add_trace(go.Scatter(
            x=xy[:, 0], y=xy[:, 1], mode="markers", name=label, customdata=[[s["id"]] for s in members],
            text=[s["name"] for s in members],
            marker={"size": 11, "color": color, "symbol": symbol, "line": {"width": 1.5, "color": "white"}},
            hovertemplate="%{text}<extra>click to select</extra>",
        ))
    x, y = common.site_xy_km(item)
    fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[item["name"]], textposition="top center",
                             marker={"size": 22, "color": "rgba(0,0,0,0)", "line": {"width": 2.5, "color": "#0b0b0b"}},
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers+text", text=["South pole"], textposition="bottom center",
                             marker={"symbol": "x-thin", "size": 10, "line": {"width": 2, "color": common.MUTED}},
                             hoverinfo="skip", showlegend=False, textfont={"size": 9, "color": common.MUTED}))
    extent = 215.0
    fig.update_xaxes(range=[-extent, extent], visible=False)
    fig.update_yaxes(range=[-extent, extent], visible=False, scaleanchor="x", scaleratio=1)
    common.finish(fig, height=470, dragmode="pan")
    common.show(fig, key=MAP_KEY, on_select=_pick_site, selection_mode="points")
    st.caption("Polar stereographic view, km from the pole; 0° E points up. Click a site to select it."
               + (" Shaded relief: LOLA 40 m model (PGDA)." if relief else ""))

with right:
    st.subheader("Horizon panorama")
    prof = common.profile(state.site_id, height)
    azimuth = np.rad2deg(prof.azimuth_rad)
    horizon = np.rad2deg(prof.elevation_rad)
    step = max(1, times.size // 4000)  # thin long windows for drawing only
    sun_az, sun_el = np.rad2deg(track.sun.azimuth_rad[::step]), np.rad2deg(track.sun.elevation_rad[::step])
    earth_az, earth_el = np.rad2deg(track.earth.azimuth_rad[::step]), np.rad2deg(track.earth.elevation_rad[::step])
    floor = float(min(horizon.min(), sun_el.min(), earth_el.min())) - 0.5
    top = float(max(horizon.max(), sun_el.max(), earth_el.max())) + 0.5
    pano = go.Figure()
    pano.add_trace(go.Scatter(x=np.r_[azimuth, 360.0], y=np.full(azimuth.size + 1, floor), mode="lines",
                              line={"width": 0}, hoverinfo="skip", showlegend=False))
    pano.add_trace(go.Scatter(x=np.r_[azimuth, 360.0], y=np.r_[horizon, horizon[0]], mode="lines", fill="tonexty",
                              fillcolor=common.TERRAIN_FILL, line={"color": common.TERRAIN, "width": 1.2},
                              name=f"Terrain horizon ({height:g} m)",
                              hovertemplate="azimuth %{x:.1f}°, horizon %{y:.2f}°<extra></extra>"))
    for label, az, el, visible, color in (
        ("Sun", sun_az, sun_el, sunlit[::step], common.SUN),
        ("Earth", earth_az, earth_el, link[::step], common.EARTH),
    ):
        pano.add_trace(go.Scattergl(x=az[visible], y=el[visible], mode="markers", name=f"{label} in view",
                                    marker={"size": 3, "color": color},
                                    hovertemplate=f"{label}: azimuth %{{x:.1f}}°, elevation %{{y:.2f}}°<extra></extra>"))
        pano.add_trace(go.Scattergl(x=az[~visible], y=el[~visible], mode="markers", name=f"{label} hidden",
                                    marker={"size": 3, "color": color, "opacity": 0.18}, hoverinfo="skip",
                                    showlegend=False))
    pano.update_xaxes(range=[0, 360], tickvals=list(range(0, 361, 45)),
                      ticktext=["N 0°", "NE", "E 90°", "SE", "S 180°", "SW", "W 270°", "NW", "N 360°"],
                      title="Azimuth (clockwise from north)")
    pano.update_yaxes(range=[floor, top], title="Elevation, deg")
    common.finish(pano, height=470)
    common.show(pano)
    st.caption("Grey: terrain above the local horizontal plane, from LOLA terrain models (5 m near the site where "
               "available, 40 m beyond, rays of 300 km). Points: hourly positions of the centres of the Sun and the "
               "Earth over the selected dates; faint points are hidden by terrain.")

st.subheader("When the Sun and the Earth are in view")
timeline = go.Figure()
timeline.add_trace(common.presence(times, sunlit, 1.0, common.SUN, "Sun visible (any part of the disc)"))
timeline.add_trace(common.presence(times, link, 0.0, common.EARTH, f"Earth link ({common.RULE_LABELS[comm.rule]})"))
timeline.update_yaxes(tickvals=[1, 0], ticktext=["Sun", "Earth"], range=[-0.7, 1.7])
timeline.update_xaxes(title="UTC")
common.finish(timeline, height=230)
common.show(timeline)
st.caption(f"{common.window_label()}, 1 h steps. Durations are counted in whole hours (docs/ASSUMPTIONS.md, A13).")

"""Landing windows: on which days a lander can land and survive its mission (task T11)."""

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common
from lunarnav import store
from lunarnav.comms import link_mask
from lunarnav.windows import best_landing_dates, default_mission_days, landing_windows

BLUE_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")


@st.cache_data(show_spinner=False)
def _mission_default() -> tuple[int, bool]:
    days, placeholders = default_mission_days()
    return int(round(days)), bool(placeholders)


state = st.session_state
item = common.site(state.site_id)
height = state.mast_height_m
default_days, mission_placeholder = _mission_default()
state.setdefault("mission_days", default_days)

st.title("Landing windows")
st.caption(f"{item['name']} · panel and antenna {height:g} m above the surface · one landing per day at 00:00 UTC, "
           "battery as set at landing")
st.number_input("Mission length, days" + (f" (placeholder {default_days} days, A23)" if mission_placeholder else ""),
                min_value=2, max_value=60, step=1, key="mission_days")
mission = dt.timedelta(days=int(state.mission_days))
first_day = dt.date.fromisoformat(common.window()[0])
last_wanted = dt.date.fromisoformat(common.window()[1]) - dt.timedelta(days=1)
last_possible = store.EPHEMERIS_STOP.astype("datetime64[D]").astype(dt.date) - mission
last_day = min(last_wanted, last_possible)
if last_day < first_day:
    st.warning("No landing day fits: shorten the mission or move the dates.")
    st.stop()

track, vis = common.observer(state.site_id, height, first_day.isoformat(), (last_day + mission).isoformat())
system = common.power_system()
comm = common.comm_settings()
table = landing_windows(track, vis, system, comm, duration_h=24.0 * state.mission_days,
                        last_landing_utc=np.datetime64(last_day.isoformat()))
best = best_landing_dates(table)
surviving = int(table["survives"].sum())
st.caption(f"Landing days {first_day} to {last_day}: **{surviving} of {len(table)} survive** a "
           f"{state.mission_days}-day mission." + (" The last landing days are limited by the end of the "
                                                    f"precomputed data ({str(store.EPHEMERIS_STOP)[:10]})."
                                                    if last_day < last_wanted else ""))

# --- calendar --------------------------------------------------------------------------------
allowed = 100.0 * system.battery_min_soc
months = pd.period_range(table["landing_utc"].min(), table["landing_utc"].max(), freq="M")
row_of = {month: index for index, month in enumerate(months)}
margin = np.full((len(months), 31), np.nan)
failed = np.full(margin.shape, np.nan)
hover = np.full(margin.shape, "", dtype=object)
for row in table.itertuples(index=False):
    cell = row_of[row.landing_utc.to_period("M")], row.landing_utc.day - 1
    hover[cell] = (f"{row.landing_utc:%Y-%m-%d}: {'survives' if row.survives else 'does not survive'}<br>"
                   f"lowest charge {row.min_soc_pct:.0f} %<br>Sun {row.sunlit_pct:.0f} % · Earth {row.earth_pct:.0f} %"
                   f" · longest night {row.longest_night_h:.0f} h")
    if row.survives:
        margin[cell] = row.min_soc_pct
    else:
        failed[cell] = 1.0
labels = [month.strftime("%b %Y") for month in months]
days = list(range(1, 32))
calendar = go.Figure()
calendar.add_trace(go.Heatmap(
    z=margin, x=days, y=labels, zmin=allowed, zmax=100.0, xgap=2, ygap=2, hovertext=hover, hoverinfo="text",
    colorscale=[[index / (len(BLUE_RAMP) - 1), color] for index, color in enumerate(BLUE_RAMP)],
    colorbar={"title": {"text": "Lowest charge<br>during the<br>mission, %"}, "thickness": 12},
))
calendar.add_trace(go.Heatmap(
    z=failed, x=days, y=labels, xgap=2, ygap=2, showscale=False, hovertext=hover, hoverinfo="text",
    colorscale=[[0.0, common.CRITICAL], [1.0, common.CRITICAL]],
    text=np.where(np.isnan(failed), "", "×"), texttemplate="%{text}", textfont={"color": "white", "size": 10},
))
if not best.empty:
    calendar.add_trace(go.Scatter(
        x=best["landing_utc"].dt.day, y=[f"{day:%b %Y}" for day in best["landing_utc"]], mode="markers+text",
        text=best["rank"].astype(str), textfont={"color": "white", "size": 11},
        marker={"symbol": "square-open", "size": 19, "color": "#ffffff", "line": {"width": 2.5}},
        hoverinfo="skip", showlegend=False,
    ))
calendar.update_yaxes(autorange="reversed", type="category")
calendar.update_xaxes(title="Landing day of the month", tickvals=days, side="top")
common.finish(calendar, height=120 + 24 * len(months))
common.show(calendar)
st.caption(f"Blue: the lander survives; darker means more charge left at the worst moment. Red ×: the charge falls "
           f"below the allowed {allowed:.0f} %. Framed numbers: the best landing days (below).")
common.power_note()

# --- best days -------------------------------------------------------------------------------
st.subheader("Best landing days")
if best.empty:
    st.stop()
if not best["survives"].any():
    st.error("No landing day survives with this lander; the days below are the least bad ones.")
top = best.iloc[0]
tied = (
    table["survives"].eq(bool(top["survives"]))
    & table["min_soc_pct"].round(6).eq(round(float(top["min_soc_pct"]), 6))
    & table["earth_pct"].round(6).eq(round(float(top["earth_pct"]), 6))
)
ties = int(tied.sum()) if top["survives"] else 0
st.dataframe(pd.DataFrame({
    "Rank": best["rank"], "Landing (UTC)": best["landing_utc"].dt.strftime("%Y-%m-%d"),
    "Survives": best["survives"].map({True: "yes", False: "no"}), "Lowest charge, %": best["min_soc_pct"].round(1),
    "Earth link, %": best["earth_pct"].round(1), "Sun visible, %": best["sunlit_pct"].round(1),
    "Longest night, h": best["longest_night_h"],
}), hide_index=True, width="stretch")
st.caption("Ranked by survival, then the lowest charge during the mission, then the share of time with the Earth "
           "link, then the earlier date; missions of the chosen days do not overlap (docs/ASSUMPTIONS.md, A22)."
           + (f" {ties} landing days share the best score; the earliest non-overlapping ones are shown." if ties > 1 else ""))

times = np.asarray(track.times_utc)
link = link_mask(vis, track.earth.angular_radius_rad, comm)
timeline = go.Figure()
timeline.add_trace(common.presence(times, vis.sun_fraction > 0, 1.0, common.SUN, "Sun visible"))
timeline.add_trace(common.presence(times, link, 0.0, common.EARTH, "Earth link"))
for row in best.itertuples(index=False):
    timeline.add_vrect(x0=row.landing_utc, x1=row.end_utc, fillcolor="#0b0b0b", opacity=0.12, line_width=0,
                       annotation_text=str(row.rank), annotation_position="top")
timeline.update_yaxes(tickvals=[1, 0], ticktext=["Sun", "Earth"], range=[-0.7, 1.9])
common.finish(timeline, height=240)
common.show(timeline)
st.caption("Why these days: each grey band (a best mission) lies where the Sun and the Earth stay in view. A visible "
           "Earth is line of sight only, not yet a closed radio link (A17).")

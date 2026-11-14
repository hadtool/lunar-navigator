"""Mast trade-off: what a taller mast buys in light, link time and battery mass (task T10)."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import common
from lunarnav.mast import CARRIES, CARRIES_BOTH, LEVELLING_SHARE, MIN_MEANINGFUL_HEIGHT_M, levelling_off_heights, tradeoff_table

MIN = MIN_MEANINGFUL_HEIGHT_M

state = st.session_state
item = common.site(state.site_id)
start, stop = common.window()
heights = common.at_least_meaningful(common.heights_for(state.site_id))
state.setdefault("mast_carries", common.mast_settings()[1])
if len(heights) < 2:
    st.title("Mast trade-off")
    st.warning(f"This site has fewer than two precomputed heights of at least {MIN:g} m.")
    st.stop()

st.title("Mast trade-off")
st.caption(f"{item['name']} · {common.window_label()} · heights {', '.join(f'{h:g}' for h in heights)} m")
carry_labels = {CARRIES_BOTH: "Panel and antenna", "panels": "Panel only", "antenna": "Antenna only"}
st.radio(f"What the mast carries (the other item stays at {heights[0]:g} m, the lowest height shown)", CARRIES,
         format_func=carry_labels.get, key="mast_carries", horizontal=True)

series = common.mast_series(state.site_id, tuple(heights), start, stop)
system = common.power_system()
table = tradeoff_table(series, system, common.comm_settings(), state.mast_carries)
levels = levelling_off_heights(table)
shown = table

if len(shown) >= 2:
    low, high = shown.iloc[0], shown.iloc[-1]
    gain = high["sunlit_pct"] - low["sunlit_pct"]
    level = levels["sunlit_pct"]
    text = (f"From {low['mast_height_m']:g} to {high['mast_height_m']:g} m the Sun is in view "
            f"{gain:+.1f} percentage points longer ({low['sunlit_pct']:.1f} → {high['sunlit_pct']:.1f} %), the longest "
            f"night goes from {low['longest_night_h']:.0f} to {high['longest_night_h']:.0f} h")
    low_wh, high_wh = low["required_capacity_wh"], high["required_capacity_wh"]
    if np.isfinite(low_wh) and np.isfinite(high_wh):
        text += f" and the battery needed from {low_wh:,.0f} to {high_wh:,.0f} Wh"
        if system.battery_specific_energy_wh_per_kg:
            kilograms = (low_wh - high_wh) / system.battery_specific_energy_wh_per_kg
            text += (f" ({kilograms:,.1f} kg of battery saved)" if kilograms >= 0
                     else f" ({-kilograms:,.1f} kg more battery needed)")
    else:
        text += "; with this battery setting no battery size survives the window at some heights (see the table)"
    text += "."
    if level is not None:
        text += (f" **{100 * LEVELLING_SHARE:.0f} % of the gain in sunlight is reached at {level:g} m**; above that "
                 "the gain grows slowly.")
    st.info(text)

panels = (
    ("sunlit_pct", "Sun visible, %", "{:.1f} %"),
    ("longest_night_h", "Longest night, h", "{:.0f} h"),
    ("required_capacity_wh", "Battery needed, Wh", "{:,.0f} Wh"),
    ("earth_pct", "Earth link, %", "{:.1f} %"),
)
fig = make_subplots(rows=1, cols=4, subplot_titles=[title for _, title, _ in panels], horizontal_spacing=0.07)
for index, (column, title, fmt) in enumerate(panels, start=1):
    values = shown[column].to_numpy(dtype=float)
    fig.add_trace(go.Scatter(
        x=shown["mast_height_m"], y=values, mode="lines+markers+text", name=title,
        text=[fmt.format(v) if np.isfinite(v) and i in (0, len(values) - 1) else ""
              for i, v in enumerate(values)], textposition="top center",
        textfont={"size": 10}, line={"color": common.SERIES[0], "width": 2},
        marker={"size": 9, "line": {"width": 1.5, "color": "white"}}, showlegend=False,
        customdata=[fmt.format(v) if np.isfinite(v) else "-" for v in values],
        hovertemplate="%{x:g} m: %{customdata}<extra></extra>",
    ), row=1, col=index)
    fig.update_xaxes(title="Mast height, m", tickvals=shown["mast_height_m"], row=1, col=index)
    if column.endswith("_pct"):
        fig.update_yaxes(range=[0, 108], row=1, col=index)
    else:
        top = float(np.nanmax(np.where(np.isfinite(values), values, np.nan))) if np.isfinite(values).any() else 1.0
        fig.update_yaxes(range=[0, 1.18 * max(top, 1.0)], row=1, col=index)
common.finish(fig, height=360)
common.show(fig)
common.power_note()
st.caption(
    f"Heights from {MIN:g} m; 0 m (an observer on the terrain-model surface, A7) is left out here, while the table of "
    "pipeline/mast_tradeoff.py keeps it. Not modelled: the mass, cost and shadow of the mast itself; compare the "
    "battery mass saved with the "
    "mass of the mast. With the placeholder load rule (A15) a taller mast can need a larger battery when a thin "
    "sliver of the Sun stays visible for many hours (docs/VALIDATION.md, T10)."
)

with st.expander("Full table"):
    labels = {
        "mast_height_m": "Mast, m", "sunlit_pct": "Sun visible, %", "mean_sun_fraction_pct": "Mean visible disc, %",
        "longest_night_h": "Longest night, h", "mean_generation_w": "Mean generation, W", "earth_pct": "Earth link, %",
        "longest_earth_gap_h": "Longest Earth gap, h", "sun_and_earth_pct": "Sun and Earth, %",
        "required_capacity_wh": "Battery needed, Wh", "required_battery_mass_kg": "Battery mass, kg",
        "survives_with_given_battery": "Survives with the set battery",
        "min_soc_pct_with_given_battery": "Lowest charge with the set battery, %",
    }
    display = table[list(labels)].rename(columns=labels).round(1)
    display["Battery needed, Wh"] = table["required_capacity_wh"].map(common.wh)
    display["Battery mass, kg"] = [common.kg(value, system.battery_specific_energy_wh_per_kg)
                                   for value in table["required_capacity_wh"]]
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption("Height where the gain levels off (lowest height with "
               f"{100 * LEVELLING_SHARE:.0f} % of the largest gain, counted from {MIN:g} m, A20): "
               + ", ".join(f"{labels.get(key, key)} {value:g} m" if value is not None else f"{labels.get(key, key)}: no gain"
                           for key, value in levels.items()))

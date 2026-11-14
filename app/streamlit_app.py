"""Lunar Landing Site Navigator: Streamlit app (NASA Space Apps Challenge 2026).

    uv run streamlit run app/streamlit_app.py

Reads only the precomputed files in data/processed (pipeline/build.py); see the Methods & data
page for formulas, data sources, assumptions and limitations.
"""

import streamlit as st

import common  # app/ is on sys.path when Streamlit runs this file

st.set_page_config(page_title="Lunar Landing Site Navigator", page_icon="🌘", layout="wide")
common.init_state()
common.sidebar()
st.navigation(
    [
        st.Page("views/site.py", title="Site & dates", icon=":material/public:", default=True),
        st.Page("views/power.py", title="Power", icon=":material/battery_charging_full:"),
        st.Page("views/mast.py", title="Mast trade-off", icon=":material/cell_tower:"),
        st.Page("views/compare.py", title="Compare sites", icon=":material/compare_arrows:"),
        st.Page("views/landing.py", title="Landing windows", icon=":material/calendar_month:"),
        st.Page("views/methods.py", title="Methods & data", icon=":material/menu_book:"),
    ]
).run()

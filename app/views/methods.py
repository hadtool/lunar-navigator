"""Methods & data: how the numbers are made, from which data, how they were checked, and their limits."""

import streamlit as st

import common

DOCS = common.ROOT / "docs"

st.title("Methods & data")
st.markdown(
    "The tool answers an engineering question for a landing site near the lunar south pole and a range of dates: "
    "**when do the Sun and the Earth stand above the real terrain horizon, and does a lander with a given power "
    "system survive there?** A second question is how a mast that lifts the panel and the antenna changes the answer."
)

st.header("How the numbers are made")
st.markdown(
    """
1. **Terrain horizon.** For each site and observer height (0, 2, 5, 10, 20 m) the horizon is traced along 720
   azimuths (0.5° bins, 4 rays each) to 300 km over the LOLA elevation models: the 5 m site model near the site
   where one exists, the 40 m south-pole model beyond. The Moon is a sphere of 1737.4 km carrying the LOLA heights,
   so curvature is exact.
2. **Sun and Earth.** Apparent directions (light time and stellar aberration) from the JPL planetary ephemeris DE440
   through NASA's SPICE toolkit, in the lunar mean-Earth frame of the terrain, hourly for 2027-2029.
3. **Visibility.** The share of the solar and of the Earth's disc above the terrain horizon, with the horizon
   followed across the disc in 32 strips.
4. **Power.** Hourly energy balance of a vertical solar panel and a battery: generation, day and night loads,
   charge and discharge efficiencies, allowed depth of discharge. The smallest battery that survives a window is
   solved exactly.
5. **Earth link.** Windows of line of sight to the Earth by a chosen rule (centre, whole disc or any part of the disc
   above the terrain, with a margin).
6. **Mast trade-off and landing windows** repeat the above for several heights and for every landing day.

Heavy steps run offline (`pipeline/build.py`); the app reads 3.3 MB of precomputed files and recomputes power and
link statistics in milliseconds.
"""
)

st.header("Formulas")
st.markdown("Elevation of a terrain point at central angle ψ and radius r_p, seen from radius r_o (exact on a sphere):")
st.latex(r"\varepsilon = \operatorname{atan2}\!\left(r_p\cos\psi - r_o,\; r_p\sin\psi\right)")
st.markdown("Visible share of a disc of angular radius ρ cut by a level horizon h (depth d = (e − h)/ρ, clipped to ±1):")
st.latex(r"f(d) = \tfrac12 + \frac{d\sqrt{1-d^2} + \arcsin d}{\pi}")
st.markdown("Panel power (S = 1361 W/m², d = Sun distance, θ = angle between the panel normal and the Sun):")
st.latex(r"P = S\left(\frac{1\,\mathrm{au}}{d}\right)^{2}\eta\,(1-\ell)\,A\,f_\odot\cos\theta")
st.markdown("Battery: a surplus charges with efficiency η_c up to the capacity; a deficit is divided by η_d; the lander "
            "survives when the stored energy never falls below (1 − DoD) of the capacity.")
st.markdown("Optional link budget (only with the engineer's radio parameters):")
st.latex(r"\frac{E_b}{N_0} = P_t + G_t + G_r - 20\log_{10}\frac{4\pi d f}{c} - L - 10\log_{10}(k\,T_s\,R)")

st.header("NASA and other data used")
st.markdown(
    """
| Data | Use |
|---|---|
| LOLA south-pole elevation model, 40 m/pixel, 80-90° S (PGDA product 90) | far horizon of every site |
| LOLA 5 m/pixel site models (PGDA product 78) | near horizon of 11 of the 15 sites (nine site models) |
| LOLA average Sun and Earth visibility maps (PGDA product 69) | independent check of our visibility statistics |
| JPL Horizons (lunar surface sites, DE441) | independent check of the Sun and Earth directions |
| NAIF SPICE kernels (DE440, lunar orientation, leap seconds) | Sun and Earth positions |
| LROC QuickMap, Moon Trek | visual check of horizons (by the team) |
| CSA Moon exploration pages | mission context |
| Wueller et al. (2026), Zenodo dataset (CC BY 4.0) | candidate landing points inside the Artemis III regions |

Every file, URL, size, checksum and download date is listed in docs/SOURCES.md (below).
"""
)

st.header("How it was checked")
st.markdown(
    """
- Sun and Earth directions agree with JPL Horizons to 0.00003° at two polar sites (24 times, 2027-2029).
- Apollo 11 landing (1969-07-20 20:17:40 UTC): Sun elevation 10.70° (Horizons 10.70°, mission plan 10.8°).
- Visibility statistics over 18.6 years agree with the published LOLA maps around four sites on average within
  2.7 points for the Sun and 0.8 points for the Earth; the scatter (9.2 and 2.6 points RMS) comes mostly from the
  different terrain models (docs/VALIDATION.md).
- Synthetic tests: horizon dip on a smooth sphere, a single ridge, disc fractions against the segment formula,
  energy balance and battery sizing against simulation; more than 250 automated tests.
"""
)

st.header("Limits: read before using a verdict")
st.markdown(
    """
- **Placeholders.** Until the team's engineer fills in docs/ENGINEERING_INPUTS.md, the lander power system, the
  Earth link rule, the mast heights and the mission length are placeholder values (docs/ASSUMPTIONS.md, A12, A14,
  A19, A23). The app marks them; verdicts made with them illustrate the method only.
- **A visible Sun is not yet power and a visible Earth is not yet a link.** Not modelled: dust, temperatures and
  heaters, the lander's own shadow, ground-station schedules, relay satellites.
- **Terrain.** Only terrain in the LOLA models blocks the view; boulders and features smaller than the real data
  spacing are absent. Results for an observer at 0 m depend on pixel-scale slopes and are not those of a real lander.
- **Load rule.** The day load is drawn whenever any part of the Sun is visible. This placeholder rule has the
  largest single effect found: hours with a thin sliver of Sun can drain the battery (docs/VALIDATION.md, T10 and T11).
"""
)

for title, name in (("Assumptions (docs/ASSUMPTIONS.md)", "ASSUMPTIONS.md"),
                    ("Validation report (docs/VALIDATION.md)", "VALIDATION.md"),
                    ("Sources (docs/SOURCES.md)", "SOURCES.md")):
    path = DOCS / name
    if path.is_file():
        with st.expander(title):
            st.markdown(path.read_text(encoding="utf-8"))

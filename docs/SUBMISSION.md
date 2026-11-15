# Submission form: drafts

Drafts of the Space Apps 2026 submission fields, in English. The exact list and length limits of
the fields must be checked against the official Project Submission Guide (task T17) before
pasting. Placeholders in _italics_ are filled in by the team.

## Project name

Lunar Landing Site Navigator

## High-level summary

Near the lunar south pole the Sun and the Earth stay close to the horizon, so whether a lander gets
power and a line of sight home depends on the real terrain around the exact landing point, on the
dates and on how high its panel and antenna stand. Our web tool answers the engineering question
directly: for 15 candidate sites (Artemis III regions, LOLA site models, IM-2) and any dates in
2027-2029 it shows when the Sun and the Earth are above the terrain horizon, simulates a lander's
battery hour by hour, gives a verdict — survives or not — and the smallest battery that survives,
compares sites, finds the best landing days for a mission, and shows how much a mast of 2 to 20 m
helps. Terrain comes from LOLA elevation models, Sun and Earth positions from NASA's SPICE toolkit;
both were checked against JPL Horizons and the published LOLA illumination maps.

## Project details

**What it does.** Six pages: Site & dates (map, horizon panorama with the Sun and Earth paths,
timeline of light and link, statistics); Power (sliders for panel, battery and loads; verdict;
battery needed and its mass); Mast trade-off (light, longest night, battery and Earth link versus
mast height, and where the gain levels off); Compare sites; Landing windows (calendar of every
landing day and the five best); Methods & data.

**How it works.** An offline pipeline traces the terrain horizon of each site and mast height along
720 azimuths over 300 km of LOLA terrain (5 m models near the site, 40 m beyond) with exact
spherical geometry, and stores the apparent Sun and Earth positions for 2027-2029 from the DE440
ephemeris (SPICE, light time and aberration, in the lunar frame of the terrain). The app computes
the visible share of each disc above the horizon, an hourly energy balance of panel, battery and
loads, and Earth-link windows by a chosen rule. The smallest battery that survives is solved
exactly. Everything the app needs fits in 3.6 MB; a parameter change is recomputed in well under a
second.

**Results (default lander, 2027).** At Connecting Ridge a 10 m mast instead of 2 m raises the
time with sunlight from 79.1 % to 95.1 % and cuts the battery needed for the year from 51.5 kWh to
5.1 kWh; the gain levels off at about 10 m at ridge sites, while at Haworth a mast hardly helps. At
Malapert Massif the mast also raises the time with the Earth in view from 62.7 % to 89.1 % (2 to
20 m). The best landing days keep both the Sun and the Earth in view for a whole 14-day mission.

**Benefits and intended impact.** Mission and lander engineers get a quick, transparent first answer
to "will it survive here and then?" and to the mast-or-battery trade-off, with every assumption
listed and every placeholder marked, before running detailed thermal and power analyses.

**Validation.** Sun and Earth directions agree with JPL Horizons to 0.00003°; the Sun elevation at
the Apollo 11 landing is 10.70° (Horizons 10.70°, mission plan 10.8°); our 18.6-year visibility
statistics agree with the published LOLA maps within 2.7 points (Sun) and 0.8 points (Earth) on
average around four sites; the longest sunlit spells in the 2027-2029 midsummers agree with the
peer-reviewed model of Wueller et al. (2026) within 1 day for 32 of 36 site-years; horizon peaks land
on the real massifs in LROC camera images. 287 automated tests.

**Limits.** A visible Sun is not yet power and a visible Earth is not yet a radio link; dust,
temperatures, the lander's shadow, station schedules and relays are not modelled. The lander power
values follow a NASA reference lander, a solar-cell datasheet and a textbook sizing calculation;
no engineer has reviewed them.

**Tools.** Python, NumPy, pandas, PyArrow, rasterio, SpiceyPy (NAIF SPICE), Streamlit, Plotly,
Matplotlib, pytest, uv; Claude Code (see AI use).

## Use of NASA data

- LOLA elevation models from the NASA GSFC Planetary Geodesy Data Archive: product 90 (south pole,
  40 m/pixel) for the far horizon and product 78 (5 m/pixel site models) for the near horizon of
  11 of the 15 sites.
- LOLA average Sun and Earth visibility maps (PGDA product 69) to validate our statistics.
- JPL Horizons to validate the Sun and Earth directions at two polar sites and at Apollo 11.
- NAIF SPICE kernels (DE440 planetary ephemeris, lunar orientation, leap seconds) for the positions.
- The LROC WAC south-polar mosaic (the imagery LROC QuickMap shows) to check visually that the
  terrain points defining our horizon peaks land on the real massifs and crater rims.

## Space agency partner resources

The CSA Moon exploration pages are listed by the challenge as mission context; we read them for
background on lunar exploration, and no number in the tool comes from them.

## References

- Mazarico, E. et al. (2011). Illumination conditions of the lunar polar regions using LOLA
  topography. Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030.
- Wueller et al. (2026). Assessing potential landing sites with favorable illumination and
  accessible, potentially volatile-rich permanently shadowed regions within Artemis candidate
  landing regions. JGR Planets 131(3), e2025JE009434; dataset doi:10.5281/zenodo.17084058 (CC BY 4.0).
- Kopp, G., Lean, J. L. (2011). A new, lower value of total solar irradiance. GRL 38, L01706.
- NASA SP-4029, Apollo by the Numbers (Apollo 11 summary).
- Wertz, J. R., Larson, W. J. (1999). Space Mission Analysis and Design, 3rd ed. (solar-array sizing).
- NASA (2024). State-of-the-Art of Small Spacecraft Technology (radio and antenna values).
- NASA PGDA products 69, 78, 90; JPL Horizons; NAIF SPICE generic kernels. Full list with URLs and
  checksums: docs/SOURCES.md.

## Use of artificial intelligence

The team wrote the task list and project rules and made the decisions on scope, data and method.
Claude Code (Anthropic) wrote most of the code and documentation task by task under those rules:
every number comes from a calculation, a cited source or a listed assumption; every task was
checked with tests and an automated code review before it was closed; the task reports are in
tasks/DONE.md of the repository.

## Links

- Repository: https://github.com/hadtool/lunar-navigator
- App: https://lunar-navigator-nasa.streamlit.app/
- Demo video (30 s, English subtitles burned in): https://github.com/hadtool/lunar-navigator/blob/main/docs/demo/demo_video.mp4
- Slides (7, PDF): https://github.com/hadtool/lunar-navigator/blob/main/docs/demo/slides.pdf

## Team

Hadiyatullo Ibrohimov, Zikrullo Asrorov, Umarkhon Hamdamov.

# Lunar Landing Site Navigator

**Will a lander with *this* power system survive at *this* lunar south-pole site on *these* dates —
and how much does a mast help?**

NASA Space Apps Challenge 2026 ·
[Lunar Landing Site Navigator](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/)
· **Live app:** _link added after deployment_

## The problem

Near the lunar south pole the Sun and the Earth stay within a few degrees of the horizon. Whether a
lander gets sunlight and a line of sight home depends on the real terrain around the exact spot, on
the dates and on how high its panel and antenna stand. Illumination maps say how often; engineers
need to know whether *their* lander survives *there and then*.

## What we built

A Streamlit app on top of an offline pipeline, for 15 sites (Artemis III regions, LOLA site
models, IM-2) and any dates in 2027-2029:

- **Site & dates** — map, terrain horizon panorama with the hourly Sun and Earth paths, timeline.
- **Power** — panel, battery and loads as sliders; hourly battery simulation; verdict *survives /
  does not survive*; the smallest battery that survives and its mass.
- **Mast trade-off** — light, longest night, battery and Earth link for masts of 0-20 m.
- **Compare sites**, **Landing windows** (calendar and the five best landing days), **Methods & data**.

## What it shows (2027, default lander)

- At Connecting Ridge a 10 m mast instead of 2 m raises the time with sunlight from 79.1 % to
  95.1 % and cuts the battery needed for the year from 22.8 kWh to 4.9 kWh (114 kg to 24 kg). The
  gain levels off at about 10 m there and at Malapert Massif; at Haworth a mast hardly helps.
- The Earth is often the narrow constraint: at Malapert Massif a mast raises the time with the Earth
  in view from 62.7 % to 89.1 % (2 to 20 m); at Connecting Ridge the Earth sets behind terrain
  135 km away and a mast does not help.
- With a 20 kWh battery every 14-day mission here survives; a whole year at Malapert Massif needs
  24.1 kWh at 2 m but 14.1 kWh on a 10 m mast.

Lander values follow a NASA reference lander (2022) and a solar-cell datasheet, or are placeholders;
our engineer has **not confirmed** them yet ([inputs](docs/ENGINEERING_INPUTS.md)); the app marks them.

## Try it

Three clicks: **Malapert Massif** → **Power** (*does not survive* 2027 with the 20 kWh battery at
2 m) → mast slider to **10 m** (*survives*; 14.1 kWh needed instead of 24.1).

```bash
uv sync
uv run streamlit run app/streamlit_app.py
```

The app reads only precomputed files (`data/processed/`, 3.6 MB; no terrain, no SPICE kernels).
Rebuild: `uv run python pipeline/build.py` (raw data: [docs/SOURCES.md](docs/SOURCES.md)). Tests: `uv run pytest`.

## NASA data and how we used it

| Data | Use |
|---|---|
| LOLA elevation models, PGDA [90](https://pgda.gsfc.nasa.gov/products/90) (40 m) and [78](https://pgda.gsfc.nasa.gov/products/78) (5 m sites) | Terrain horizons, 720 azimuths, 300 km rays |
| LOLA Sun and Earth visibility maps, PGDA [69](https://pgda.gsfc.nasa.gov/products/69) | Check of our visibility statistics |
| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) | Check of Sun and Earth directions, incl. Apollo 11 |
| NAIF SPICE kernels (DE440) | Hourly Sun and Earth positions |
| LROC WAC south-polar mosaic (imagery of [QuickMap](https://quickmap.lroc.asu.edu/)) | Visual check: horizon peaks land on the real massifs |
| [CSA Moon exploration](https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/) | Mission context; no number comes from it |

Site points in the Artemis III regions: Wueller et al. (2026), CC BY 4.0.

## Method and checks

Exact spherical horizon over LOLA heights → Sun and Earth directions (SPICE) → visible share of each
disc → hourly energy balance → Earth-link windows. Directions agree with JPL Horizons to 0.00003°;
visibility agrees with the LOLA maps within 2.7 (Sun) and 0.8 (Earth) points on average; midsummer
sunlit spells agree with Wueller et al. (2026) within 1 day in 32 of 36 cases ([report](docs/VALIDATION.md)).

## Limits

A visible Sun is not yet power and a visible Earth is not yet a radio link. Not modelled: dust,
temperatures, the lander's own shadow, station schedules, relays, boulders. All assumptions:
[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Team, use of AI, license

_Team names to be added._ Roles: programmer (data, code, app), engineer (power and link models).

The team wrote the task list and rules ([CLAUDE.md](CLAUDE.md)) and decided scope, data and method.
Claude Code (Anthropic) wrote most of the code and documents task by task; every number comes from a
calculation, a cited source or a listed assumption, and every task was tested and reviewed
([tasks/DONE.md](tasks/DONE.md)).

License: MIT proposed for the code, to be confirmed by the team. Data keep their own terms.

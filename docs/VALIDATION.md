# Validation

How the results were checked against independent sources, what is still uncertain, and how
large the effects are. Numbers in this file are outputs of the scripts and tests named in each
section; nothing is typed in by hand from memory. Assumptions are numbered A1-A23 in
docs/ASSUMPTIONS.md; sources and checksums are in docs/SOURCES.md.

## Summary

| What is checked | Reference | Result | Where |
|---|---|---|---|
| Directions of the Sun and the Earth | JPL Horizons, two polar sites x 24 times in 2027-2029 | largest difference 0.000026 deg (task limit 0.01 deg) | `tests/test_ephemeris.py` |
| Sun elevation at the Apollo 11 landing | JPL Horizons; NASA SP-4029 (planned 10.8 deg) | 10.7035 deg (Horizons 10.7033 deg) | `tests/test_ephemeris.py` |
| Terrain horizon geometry | horizon dip on a smooth sphere; a single ridge of known size | relative 1e-4; 0.0002 rad (0.011 deg) | `tests/test_horizon.py` |
| Horizon on real terrain | the summit of Malapert Massif seen from Connecting Ridge, 135 km away | on the horizon within 0.01 deg of its computed elevation | `tests/test_horizon_real.py` |
| Terrain beyond the 40 m model | LOLA 240 m model, rays to 500 km | no azimuth changes for 15 sites; margin at least 0.66 deg | A5 |
| Sun and Earth visibility over 18.6 years | published LOLA maps (PGDA product 69), 36 pixels at 4 sites | mean difference -2.68 / -0.82 points, RMS 9.24 / 2.59 points (Sun / Earth) | section below |
| Visible share of a disc | circular-segment formula | within 0.001 | `tests/test_visibility.py` |
| Battery sizing | simulation with the computed capacity; hand calculation | survives with it, fails below it; hand check matches | power section below, `tests/test_power.py` |
| Earth contact windows | period of the lunar libration in latitude (653 h) | windows repeat every 652 to 657 h | contact-window section below |
| Precomputed data of the app | a fresh SPICE run | identical to the last bit | `tests/test_store.py` |
| Whole app | Streamlit AppTest, no kernels, no terrain | 6 pages open, demo scenario, reruns below 2 s | `tests/test_app.py` |

Not yet done: the visual comparison of a horizon panorama with LROC QuickMap or Moon Trek
(task T06, to be done by a team member in a browser) and the engineer's review of the power,
link and mast examples below.

## Sun and Earth directions versus JPL Horizons (T05)

Our ephemeris (`lunarnav.ephemeris`: SPICE, DE440 kernels, lunar mean-Earth frame aligned with
the LOLA terrain, light time and stellar aberration) was compared with JPL Horizons observer
tables for points on the lunar surface (Horizons uses DE441 and the same 1737.4 km sphere). The
unmodified Horizons responses are committed in `tests/data/horizons_*.txt`.

| Site | Times | Largest difference, Sun | Largest difference, Earth |
|---|---|---|---|
| Connecting Ridge (89.44 S) and Malapert Massif (85.99 S) | 24 each, 2027-01-01 to 2029-11-01, every 45 days | 0.000001 deg | 0.000026 deg |
| Apollo 11 Lunar Module | 1969-07-20 20:17:40 and 20:18:40 UTC | 0.0002 deg | 0.00003 deg |

The test requires 0.0005 deg, twenty times tighter than the task limit of 0.01 deg, and a
separate test shows that a calculation without stellar aberration fails it, so the tolerance
does test the corrections.

Plausibility near the pole (2027, Connecting Ridge): the Sun's elevation never exceeds
90 deg - |latitude| + 1.6 deg (the lunar equator is tilted about 1.5 deg to the ecliptic) and the
Earth swings through about +-7 deg around the horizon without going round the sky.

## Apollo 11 (T05)

At the Lunar Module position (0.67416 N, 23.47314 E; NSSDC after Wagner et al., 2017) at
20:17:40 UTC on 1969-07-20 our Sun elevation is 10.7035 deg at azimuth 88.8055 deg; JPL
Horizons gives 10.7033 deg and 88.8055 deg. The published value, 10.8 deg (NASA SP-4029, Apollo 11
summary), is the Sun elevation for which the launch window was planned, not a measurement at
touchdown; the test therefore allows 0.3 deg against it and 0.0005 deg against Horizons.

## Terrain horizon (T06)

- **Smooth sphere.** For an observer h metres above a sphere without relief the horizon must dip
  by acos(R / (R + h)), about sqrt(2h/R), at a distance of sqrt(2Rh): reproduced to a relative
  1e-4 in angle and 2 % in distance for several heights (`tests/test_horizon.py`).
- **Single ridge.** A ridge of known height and distance gives the angle expected from exact
  spherical geometry within 0.0002 rad, never more, and at the expected distance; a ridge in the
  east appears at azimuth 90 deg (the azimuth convention); a narrow peak between two bin centres
  is caught by the sub-rays.
- **Real terrain.** From Connecting Ridge the summit of Malapert Massif, the highest pixel of its
  5 m model, lies 130 to 140 km away; the cached horizon in its direction equals the summit's
  computed elevation within 0.01 deg at mast heights of 2, 10 and 20 m (`tests/test_horizon_real.py`). The
  Earth seen from Connecting Ridge rises and sets near azimuth 137 deg, as expected for a site at
  222.7 deg east longitude.
- **Sampling.** Eight rays per bin instead of four change the mean horizon of Connecting Ridge
  (2 m) by 0.002 deg, and a radial step of one pixel everywhere changes no azimuth by more than
  0.002 deg (A9). Terrain beyond the 40 m model does not reach the horizon at any of the 15 sites
  (A5).
- **Reproducibility.** Rebuilding all 75 horizons from the raw terrain gives byte-for-byte the
  committed files (T12).

## Illumination and Earth visibility versus the published LOLA maps (T07)

Script: `pipeline/validate_illumination.py`; full output:
`data/processed/validation/illumination_vs_lola.json`. Run on 2026-11-14.

**Reference.** The 60 m/pixel maps `AVGVISIB_85S_060M_201608` (Sun) and
`AVGVISIB_85S_060M_201608_EARTH` (Earth) of the LOLA team (docs/SOURCES.md). A pixel value is
the share of hourly time steps over 18.6 years in which any part of the disc was visible from
the surface, computed on the 60 m terrain model `LDEM_85S_060M` (Mazarico et al., 2011).

**Ours.** The same statistic (`sunlit_pct` and `earth_any_part_pct` of
`lunarnav.visibility.window_metrics`): hourly steps over 18.6 years starting 2027-01-01
(163 048 steps), our ephemeris and our terrain horizon. The closest analogue of the map is our
horizon from the 40 m model alone with the observer on the surface (0 m). The app uses the
5 m site models near the site and a mast, so those rows are shown for comparison only.

### At the four sites

Share of time with any part of the disc visible, percent. "3 x 3" is the range of the map
over the pixel that contains the site and its eight neighbours (180 m x 180 m).

| Site | Published Sun (3 x 3 range) | Ours Sun, 40 m, 0 m | Difference | Published Earth (3 x 3 range) | Ours Earth, 40 m, 0 m | Difference |
|---|---|---|---|---|---|---|
| Connecting Ridge | 58.69 (37.39-66.26) | 58.99 | +0.30 | 53.52 (46.34-57.44) | 55.26 | +1.74 |
| de Gerlache Rim | 52.84 (9.73-69.88) | 53.17 | +0.33 | 53.90 (38.85-61.37) | 55.51 | +1.61 |
| Malapert Massif | 63.95 (48.51-70.38) | 54.67 | -9.28 | 70.91 (53.90-75.99) | 63.19 | -7.72 |
| Haworth | 53.97 (31.54-53.97) | 50.45 | -3.52 | 53.51 (47.81-54.73) | 53.87 | +0.36 |

### Pixel by pixel around the sites

Our value (40 m model, 0 m) at the centre of each of the 3 x 3 map pixels minus the map value,
percentage points:

| Site | Sun: mean difference | Sun: RMS difference | Earth: mean difference | Earth: RMS difference |
|---|---|---|---|---|
| Connecting Ridge | -9.44 | 12.05 | -0.88 | 2.30 |
| de Gerlache Rim | -1.91 | 10.50 | -0.40 | 3.20 |
| Malapert Massif | -2.60 | 7.33 | -1.38 | 3.14 |
| Haworth | +3.22 | 5.70 | -0.64 | 1.16 |
| All 36 pixels | -2.68 | 9.24 | -0.82 | 2.59 |

Correlation between our 36 Sun values and the published ones: 0.75.

### Reading

- Averaged over the patches our Sun statistic is 2.7 percentage points below the map and our
  Earth statistic 0.8 points below. Single pixels differ by about 9 points (RMS) for the Sun
  and 2.6 points for the Earth.
- The Sun statistic is very sensitive to position on these ridges: inside one 3 x 3 patch the
  published map itself varies by 22 to 60 points, i.e. by more than our difference from it. A
  site value therefore cannot be expected to agree better than several points with any map
  of a different resolution. The Sun moves in a narrower band around the horizontal plane than
  the Earth (its elevation never exceeds 90 deg - |latitude| + 1.6 deg: 2.2 deg at Connecting
  Ridge, 2.9 deg at de Gerlache Rim, 4.6 deg at Haworth and 5.6 deg at Malapert Massif, while the
  Earth swings through about +-7 deg), so the same horizon error moves the Sun statistic more
  than the Earth statistic; this matches the tighter Earth agreement.
- The close agreement at the exact site position of Connecting Ridge and de Gerlache Rim
  (0.3 points) is partly luck, as the pixel-by-pixel spread shows.

### Causes of the differences (measured where a number is given)

1. Different terrain models: the map uses the 60 m `LDEM_85S_060M` of 2016, we use the 40 m
   `LDEM_80S_40MPP_ADJ` (PGDA product 90, re-adjusted tracks) and sample it at a point by
   bilinear interpolation. Not separated further; given the sensitivity above we consider it
   the main cause.
2. Different 18.6-year period: the start date of the published period is not documented. For
   scale, replacing 18.6 years by the three years 2027-2029 changes our values at the four
   sites by +0.6 to +2.2 points (Sun) and +1.3 to +1.5 points (Earth).
3. Our horizon keeps the maximum over each 0.5 deg azimuth bin (docs/ASSUMPTIONS.md, A9).
   Using one ray per bin instead changes the Sun statistic by +0.09 to +0.31 points, so this
   explains only a small part of the negative mean difference.
4. Differences in the horizon and Sun models of the two codes (azimuth sampling, ray length,
   treatment of the disc) that we cannot isolate without the original code.

### What the app shows instead (not a validation)

With the 5 m site models near the site, the same statistic over the same 18.6 years:

| Site | 0 m | 2 m | 10 m |
|---|---|---|---|
| Connecting Ridge | 50.76 | 77.93 | 94.87 |
| de Gerlache Rim | 45.37 | 74.49 | 87.35 |
| Malapert Massif | 21.40 | 69.63 | 84.08 |
| Haworth | 41.96 | 61.22 | 63.76 |

These values differ strongly from the 60 m map because a point on the 5 m surface is shaded
by terrain a few pixels away, which a 60 m model does not contain, and because a mast lifts
the observer above it. The 0 m values depend on pixel-level slopes at the noise level of the
5 m models (docs/ASSUMPTIONS.md, A6 and A7). The gain from a mast is the subject of the mast
trade-off and has no published counterpart in this comparison; it rests on the 5 m models
being right at the scale of tens of metres.

## Power model: worked example for the engineer's review (T08)

Script: `pipeline/power_example.py --site connecting_ridge --month 2027-03 --mast 2`;
numbers: `data/processed/validation/power_example_connecting_ridge_2027-03_h2.json`;
figure: `docs/figures/power_example_connecting_ridge_2027-03_h2.png`.

**All power-system numbers in this example are placeholders (docs/ASSUMPTIONS.md, A14).** The
example shows how the model works; it says nothing about a real lander.

Inputs: Connecting Ridge, panel and observer 2 m above the surface, 1-31 March 2027, 1 h
steps (744 steps). Tracking vertical panel 1.0 m2 at 30 %, battery 1000 Wh, usable down to
20 % state of charge, charge and discharge efficiency 0.95, full at the start, load 100 W
while any part of the Sun is visible and 20 W otherwise.

| Quantity | Value |
|---|---|
| Hours with any part of the Sun visible | 511 of 744 |
| Mean visible share of the solar disc | 50.92 % |
| Longest night | 126 h, from 2027-03-17 13:00 UTC |
| Peak generation | 414.7 W |
| Energy the panel could deliver | 156 226 Wh |
| Energy asked by the loads | 55 760 Wh |
| Generation not used because the battery was full | 105 076 Wh |
| Load not supplied because the battery was empty | 4 231 Wh |
| Verdict with the 1000 Wh battery | does not survive; first below 20 % at 2027-03-03 05:00 UTC |
| Smallest battery that survives the month | 3 899 Wh (26.0 kg at 150 Wh/kg) |

Checks that can be repeated by hand:

- Peak generation: 1361 W/m2 x 0.30 x 1.0 m2 = 408.3 W at 1 au with the Sun on the horizon.
  In March 2027 the Sun is 0.9895 to 0.9992 au away and between -1.55 and -0.07 deg in
  elevation (the observer on a ridge sees slightly below the horizontal), so the factor
  is at most 1 / 0.9895^2 = 1.021, i.e. 417 W; the model gives 414.7 W.
- Loads: 511 h x 100 W + 233 h x 20 W = 55 760 Wh, as in the table.
- Required battery: the deepest deficit starts when the battery is last full, 2027-03-17
  09:00 UTC, and ends 2027-03-22 22:00 UTC. It consists of 126 night hours at 20 W / 0.95
  = 2 652.6 Wh and 7 dusk and dawn hours in which the 100 W day load exceeds the generation,
  466.9 Wh net. Total 3 119.5 Wh; divided by the usable share 0.8 this is 3 899.4 Wh. A
  simulation with 3 900 Wh survives with a minimum state of charge of 20.01 %, one with
  3 800 Wh falls to 17.91 %.

Questions for the engineer: (1) the placeholder values in A14; (2) the rule "day load whenever
any part of the Sun is visible" (A15), which costs 467 Wh here; (3) whether the simplifications
in A16 are acceptable, in particular a heater load that does not depend on temperature.

Speed: a three-year hourly series (26 280 steps) is simulated in 13 ms and the required
capacity is found in about 1 ms, so the app can recompute on every slider move.

## Earth contact windows: worked example for the engineer's review (T09)

Script: `pipeline/comms_example.py` (default: 120 days from 2027-01-01, observer 2 m above the
surface); tables: `data/processed/validation/comms_windows_<site>_h2.csv`; timelines:
`docs/figures/comms_timeline_<site>_h2.png`.

**The link rule is a placeholder (docs/ASSUMPTIONS.md, A12): centre of the Earth's disc above
the terrain horizon, margin 0 deg.** A window is line of sight only (A17); no link budget is
computed because the radio parameters are not filled in (A18).

| Quantity | Connecting Ridge | Malapert Massif |
|---|---|---|
| Earth in line of sight, share of the 2880 h | 48.6 % | 60.0 % |
| Complete windows inside the period | 4, of 336 to 339 h | 4, of 404 to 415 h |
| Longest gap | 319 h, from 2027-01-23 22:00 UTC | 250 h, from 2027-01-25 09:00 UTC |
| Earth distance over the period | 357 198 to 406 760 km | 357 064 to 406 626 km |

Plausibility: the Earth rises and sets once per libration cycle, so one window and one gap
together last about 27 days: successive windows start 653 to 657 h apart at Connecting Ridge
and 652 to 654 h apart at Malapert Massif, and the period of the Moon's libration in latitude
(the draconic month, 27.21 days) is 653 h. Malapert
Massif is 4 deg from the pole on the Earth-facing side, so the Earth stands higher there and
the windows are longer than at Connecting Ridge.

Questions for the engineer: the visibility rule (centre, whole disc or any part), the margin
in degrees, and the radio parameters if a link budget is wanted.

## Mast-height trade-off for the engineer's review (T10)

Script: `pipeline/mast_tradeoff.py` (default: Connecting Ridge, Malapert Massif and Haworth,
calendar year 2027, 1 h steps); table: `data/processed/mast/mast_tradeoff_2027-01-01_2028-01-01.csv`
(all columns, one row per site and height) with the inputs and the levelling-off heights in the
`.json` file next to it; figure: `docs/figures/mast_tradeoff_2027-01-01_2028-01-01.png`.

**The power system (A14), the link rule (A12), the list of heights and what the mast carries
(A19) are placeholders.** The trends with height come from the terrain and the ephemeris; the
battery sizes and masses are an illustration of the method, not data of a real lander. The
panel and the antenna sit at the top of the mast. Window and initial state: A21.

| Site | Mast, m | Sun visible, % | Mean visible disc, % | Longest night, h | Earth in view, % | Longest Earth gap, h | Battery needed, Wh | Battery mass, kg |
|---|---|---|---|---|---|---|---|---|
| Connecting Ridge | 0 | 53.4 | 47.0 | 2077 | 48.0 | 341 | 93,746 | 625.0 |
| Connecting Ridge | 2 | 79.1 | 73.1 | 302 | 50.9 | 320 | 11,608 | 77.4 |
| Connecting Ridge | 5 | 93.6 | 89.2 | 143 | 50.9 | 320 | 4,702 | 31.3 |
| Connecting Ridge | 10 | 95.1 | 92.2 | 77 | 50.9 | 320 | 3,326 | 22.2 |
| Connecting Ridge | 20 | 95.9 | 92.9 | 69 | 50.9 | 320 | 3,188 | 21.3 |
| Malapert Massif | 0 | 21.3 | 17.9 | 2063 | 52.3 | 316 | 86,489 | 576.6 |
| Malapert Massif | 2 | 70.3 | 64.9 | 446 | 62.7 | 250 | 12,228 | 81.5 |
| Malapert Massif | 5 | 81.6 | 79.0 | 303 | 71.5 | 194 | 8,510 | 56.7 |
| Malapert Massif | 10 | 85.5 | 82.7 | 261 | 79.6 | 143 | 7,084 | 47.2 |
| Malapert Massif | 20 | 86.9 | 84.0 | 261 | 89.1 | 87 | 8,070 | 53.8 |
| Haworth | 0 | 43.8 | 36.1 | 3883 | 45.8 | 357 | 115,953 | 773.0 |
| Haworth | 2 | 62.5 | 55.9 | 384 | 48.9 | 338 | 16,828 | 112.2 |
| Haworth | 5 | 63.3 | 57.4 | 382 | 49.6 | 336 | 15,586 | 103.9 |
| Haworth | 10 | 64.6 | 58.9 | 382 | 50.3 | 330 | 15,284 | 101.9 |
| Haworth | 20 | 67.4 | 61.1 | 381 | 51.3 | 322 | 14,285 | 95.2 |

"Sun visible" counts the hours with any part of the solar disc above the terrain horizon (A12);
"Battery needed" is the smallest capacity that keeps the state of charge above 20 % for the
whole year (none of the nights or gaps touches the edge of the window). The 0 m rows are an
observer on the surface of the terrain model, whose horizon is set by pixel-scale slopes (A7):
nights of 86 to 162 days there are not those of a real lander, so the figure starts at 2 m and
the conclusions count the gain from 2 m.

### Reading

1. **Hypothesis "a few metres of height markedly reduce the shadows near the pole": confirmed for
   the two sites on raised terrain, not for Haworth.** From 2 to 5 m the time with sunlight grows
   by 14.4 points at Connecting Ridge and 11.3 points at Malapert Massif, which is 86 % and 68 %
   of the whole gain from 2 to 20 m. The longest night shrinks from 302 h to 143 h and from 446 h
   to 303 h. At these sites the horizon at 2 m is set by terrain 0.1 to 0.2 km away (median,
   docs/ASSUMPTIONS.md, table "Horizon versus observer height"), which a few metres of height
   clear. At Haworth the horizon is set by terrain about 50 km away already at 2 m, and a 20 m mast
   adds only 4.9 points of sunlight and shortens the longest night by 3 h.
2. **Where the gain levels off (A20): 10 m at Connecting Ridge and Malapert Massif** for the time
   with sunlight, the mean visible share of the disc, the longest night and the battery needed:
   10 m gives 95 % (Connecting Ridge) and 92 % (Malapert Massif) of the sunlight gain from 2 to
   20 m. From 10 to 20 m Connecting Ridge gains 0.8 points of sunlight and 8 h of the longest night.
   Haworth formally levels off at 20 m, but only because its small gain grows roughly in
   proportion to the height; it does not level off within 20 m and is not large at any height.
3. **Battery mass a mast saves (placeholder power system):** from 2 to 10 m, 8,282 Wh (55.2 kg) at
   Connecting Ridge and 5,144 Wh (34.3 kg) at Malapert Massif; from 2 to 20 m, 2,543 Wh (17.0 kg)
   at Haworth. The mass of the mast itself is not modelled and has to be compared with these
   numbers.
4. **Earth in line of sight reacts differently:** at Malapert Massif, on the Earth-facing side,
   the mast keeps adding: 62.7 % at 2 m, 79.6 % at 10 m and 89.1 % at 20 m, with the longest gap
   falling from 250 h to 87 h, so for the link the gain has not levelled off at 20 m. At
   Connecting Ridge the Earth time does not change from 2 to 20 m (50.9 %): the Earth rises and
   sets at azimuths 134 to 141 deg behind terrain 134 to 140 km away, too far for a few metres
   to matter. A visible Earth is not yet a closed link (A17).
5. **A taller mast needs a larger battery at Malapert Massif: 8,070 Wh at 20 m against 7,084 Wh
   at 10 m, although there is more sunlight.** This comes from the placeholder load rule (A15),
   not from the terrain. Breakdown of the deepest deficit at 20 m (2027-03-05 18:00 to 03-15 15:00
   UTC, 237 h): 174 night hours, 3,663 Wh; 49 hours in which only a thin sliver of the Sun is
   visible, the 100 W day load is drawn and the panel gives less than that, 3,436 Wh; 14 hours of
   recharge, -643 Wh; in total 6,456 Wh, divided by the usable share 0.8 this is 8,070 Wh. At
   10 m the deepest deficit is a plain night in May (below). Check with a different rule (not part
   of the model): if the day load is drawn only while the panel covers it, Malapert Massif needs
   6,895 Wh at 10 m and 6,894 Wh at 20 m, and the levelling-off heights of all three sites stay
   the same. The engineer's choice of the load rule therefore matters for the battery numbers,
   not for the conclusion about the height.
6. **"Longest night" alone does not size the battery.** At Connecting Ridge with 2 m the deepest
   deficit lasts 540 h (2027-04-28 14:00 to 05-21 02:00 UTC) and contains three nights of 302, 21
   and 151 h; the partial days between them do not refill the battery. The battery column comes
   from the full simulation (T08), not from the longest night.

Check that can be repeated by hand: Malapert Massif with 10 m, deepest deficit 2027-05-02 23:00 to
2027-05-13 23:00 UTC (264 h). 261 night hours at 20 W / 0.95 = 5,494.7 Wh plus 3 dusk and dawn
hours in which the day load exceeds the generation, 172 Wh net, together 5,667 Wh; divided by
0.8 this is 7,084 Wh, as in the table. The deepest deficits of all three sites at 2 to 10 m fall
between 3 April and 21 May 2027, around 2027-04-27, when the Sun reaches its northernmost
latitude in the lunar frame, +1.547 deg (A21).

Speed: the ephemeris for the year (8760 steps) takes 0.3 s, the five heights of one site 0.2 s
(visibility, link windows, battery simulation and required capacity), the whole run below 1 s
plus loading.

Questions for the engineer: (1) the list of heights and what the mast carries (A19); (2) the 90 %
definition of "levels off" (A20); (3) the day-load rule (A15), which changes the battery needed at
20 m by 1.2 kWh at Malapert Massif; (4) whether a year of operation (A21) is the right case for
sizing, or a mission window; (5) the mass of a 5, 10 and 20 m mast, to compare with the battery
mass it saves.

## Landing-date search (T11)

Script: `pipeline/landing_windows.py --site <site> --mast 2` (default: landing days 2027-01-01 to
2028-12-31, one landing at 00:00 UTC per day); tables:
`data/processed/windows/landing_<site>_h2_2027-01-01_2029-01-01.csv` (one row per landing day)
and `.json` (inputs and the five best days); figures:
`docs/figures/landing_calendar_<site>_h2_2027-01-01_2029-01-01.png` (calendar) and
`docs/figures/landing_timeline_<site>_h2_2027-01-01_2029-01-01.png` (hourly Sun and Earth with
the best missions, and the battery margin per landing day).

**Placeholders: the power system (A14, battery 1000 Wh), the mission length of 14 days and the
battery full at landing (A23), the link rule (A12).** The pattern over the calendar comes from
the terrain and the ephemeris; which days pass depends on the placeholder battery.

| | Connecting Ridge, 2 m | Malapert Massif, 2 m |
|---|---|---|
| Landing days that survive 14 days | 378 of 731 | 233 of 731 |
| Days with the best possible score (battery never below full, Earth in view all 14 days) | 11 | 40 |
| Five best landing days (A22) | 2027-08-16, 2027-12-30, 2028-07-08, 2028-08-04, 2028-08-31 | 2027-01-10, 2027-08-15, 2027-09-11, 2027-10-08, 2027-11-04 |
| Time: ephemeris / visibility / calendar of 731 missions | 0.8 / 0.08 / 0.5 s | 0.5 / 0.06 / 0.3 s |

Reading:

- **Season.** At Connecting Ridge no landing between 2027-02-05 and 2027-07-16 survives with the
  placeholder battery, nor between 2028-01-24 and 2028-07-04: the southern winter of the Moon,
  when the Sun stands north of the lunar equator (+1.547 deg on 2027-04-27, A21). The failing
  season comes 12 days earlier in 2028 because the cycle of the Sun's latitude is shorter than a
  calendar year (344.5 to 348.8 days in our ephemeris).
- **Two failing runs without any night, caused by the placeholder load rule (A15).** Missions
  landing 2027-08-01 to 08-14 and 2028-12-15 to 12-28 have the Sun in view for all 336 h, yet
  the battery empties. In the mission landing 2027-08-01, for 28 h in a row only a sliver of the
  Sun is visible (15.9 % of the disc on average): the panel gives 63 W on average while the 100 W
  day load is drawn, and the battery needs 1,362 Wh. If the day load were drawn only while the
  panel covers it, the same mission would need 19 Wh (2028-12-15: 30 h, 2,038 Wh against 39 Wh).
  These runs are an effect of the load rule, not of the terrain; see the open question in A15.
- **Why the five best days.** All five have the same score at both sites: Sun and Earth in view
  for the whole mission and the battery never below full; the ranking then takes the earliest
  non-overlapping ones (A22). The timeline shows why exactly these days: every grey band lies
  inside an unbroken orange (Sun) block and inside one blue (Earth) block. The Earth is the
  narrow constraint. At Connecting Ridge an Earth window lasts 336 to 339 h (T09), almost
  exactly one 14-day mission, so the mission must start within hours of the Earth rising: only
  17 landing days of the two years keep the Earth in view all the time; 12 of them also have the
  Sun in view all the time and 11 keep the battery full. At Malapert Massif the windows last 404
  to 415 h, which leaves about three days of slack each month: 101 days keep the Earth in view
  all the time and 40 score best.
- **What the ranking does not see.** How far above the terrain the Sun and the Earth stand during
  the mission (a margin against terrain-model errors), and the landing itself; see A22.

Questions for the engineer (no review is required for T11, but the inputs are shared): the
mission length (`mission_duration_days`) and whether the ranking order of A22 (survival, then
battery margin, then Earth link) matches the mission's priorities.

## Sources of uncertainty

Ordered roughly by size of effect on the app's answers. Where a number is given it was measured
in this project; the others are named but not quantified.

| Source | Effect | Size | Assumption |
|---|---|---|---|
| Power-system values | Every verdict and battery size depends on the lander; the defaults are placeholders | not a model error: replace by the engineer's values | A14 |
| Day-load rule | Hours with a thin sliver of Sun count as "day" (100 W load) | turns a 19 Wh mission into 1362 Wh (T11); +1.2 kWh at Malapert Massif, 20 m (T10) | A15 |
| Terrain model near the site | Horizons a few metres up are set by terrain tens to hundreds of metres away, at the edge of what the 5 m models resolve | 0 m versus 2 m: 50.8 % versus 77.9 % of time with Sun at Connecting Ridge (18.6 years); results at 0 m are not used | A6, A7 |
| Sites without a 5 m model | Smoother near field, weaker reaction to a mast | not quantified | A8 |
| Terrain model resolution in general | Point statistics on ridges change by tens of points within 180 m | the published map varies by 22 to 60 points inside one 3 x 3 pixel patch; our difference to it: 9.24 points RMS (Sun) | T07 |
| Analysis period | Statistics depend on the years averaged | 2027-2029 versus 18.6 years: +0.6 to +2.2 points (Sun), +1.3 to +1.5 points (Earth) | T07 |
| Time step of 1 h | Each end of a night, gap or window is uncertain by up to one step | +-1 h per end | A13 |
| Horizon sampling | Finite rays and steps | about 0.002 deg | A9 |
| Terrain beyond 80 S | Not included | none at the current sites (margin at least 0.66 deg) | A5 |
| Ephemeris and frames | Directions of the Sun and the Earth | 0.00003 deg versus Horizons; our frame and the LOLA frame differ by 0.43 m on the surface | A1-A4 |
| Moon as a sphere of 1737.4 km | Heights and the local vertical refer to the sphere, as in LOLA and Horizons | consistent with both references; deviations of the local vertical not quantified | A1 |
| Disc model | Uniform discs: no limb darkening of the Sun, no phase of the Earth, no light reflected by terrain | not quantified | A11 |
| Earth link | Line of sight only: no ground-station schedule, relay or link closure (unless radio parameters are given) | window lengths are upper limits for a direct link | A17, A18 |
| Not modelled at all | Dust, temperatures and heaters, the lander's own shadow, boulders smaller than the terrain data | not quantified | A10, A16 |

## Automated tests

`uv run pytest -q` runs 275 tests (2026-11-14, all passing): ephemeris against the committed
Horizons tables and Apollo 11, horizons on synthetic and real terrain, disc fractions and window
statistics, energy balance and exact battery sizing against simulation, contact windows on a
synthetic libration, the mast trade-off and landing-date search on synthetic series with known
answers, the precomputed data against a fresh SPICE run, and the Streamlit app on all pages with
the SPICE kernels and the terrain rasters disabled.

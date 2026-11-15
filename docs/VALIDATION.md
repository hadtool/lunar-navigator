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
| Horizon peaks versus imagery | LROC WAC south-polar mosaic (camera images, the imagery QuickMap shows); 18 peaks at 3 sites | far peaks land on massifs and crater rims; 7 of them within 0.2-0.6 km of other listed candidate sites | `pipeline/check_horizon_wac.py`, figures below |
| Terrain beyond the 40 m model | LOLA 240 m model, rays to 500 km | no azimuth changes for 15 sites; margin at least 0.66 deg | A5 |
| Sun and Earth visibility over 18.6 years | published LOLA maps (PGDA product 69), 36 pixels at 4 sites | mean difference -2.68 / -0.82 points, RMS 9.24 / 2.59 points (Sun / Earth) | section below |
| Visible share of a disc | circular-segment formula | within 0.001 | `tests/test_visibility.py` |
| Longest sunlit spell in midsummer | Wueller et al. (2026), Table A2: 12 sites x 2027-2029 | 32 of 36 within 1 day (Sun); 21 of 24 in 2028-2029 for Sun and Earth | `pipeline/compare_wueller.py`, section below |
| Battery sizing | simulation with the computed capacity; hand calculation | survives with it, fails below it; hand check matches | power section below, `tests/test_power.py` |
| Earth contact windows | period of the lunar libration in latitude (653 h) | windows repeat every 652 to 657 h | contact-window section below |
| Precomputed data of the app | a fresh SPICE run | identical to the last bit | `tests/test_store.py` |
| Whole app | Streamlit AppTest, no kernels, no terrain | 6 pages open, demo scenario, reruns below 2 s | `tests/test_app.py` |

Not yet done: the engineer's review of the power, link and mast examples below.

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
- **Against imagery (visual check).** `pipeline/check_horizon_wac.py` takes the six highest peaks
  of a horizon panorama and puts the terrain point that defines each peak (its azimuth and
  distance) on the LROC WAC south-polar summer mosaic (Speyerer et al., 2020), i.e. on camera
  images, not on the LOLA heights the horizon comes from. A wrong azimuth convention or wrong
  distances would put the points on plains or crater floors. Figures:
  `docs/figures/horizon_check_wac_connecting_ridge_h20.png`, `..._malapert_massif_h20.png`,
  `..._haworth_h2.png`. Every far peak (beyond about 30 km) lands on a massif or a crater rim in
  the image, and several land on other candidate sites of our list, whose coordinates come from
  independent sources (docs/SOURCES.md):

  | Seen from | Peak: azimuth, distance | Lands on (distance to the listed point) |
  |---|---|---|
  | Connecting Ridge, 20 m | 93.5 deg, 38 km | de Gerlache Rim (0.2 km) |
  | Connecting Ridge, 20 m | 144.0 deg, 135 km | Malapert Massif (0.2 km) |
  | Connecting Ridge, 20 m | 175.0 deg, 159 km | Nobile Rim 1 (0.6 km) |
  | Connecting Ridge, 20 m | 238.0 deg, 42 km | Peak near Shackleton (0.3 km) |
  | Malapert Massif, 20 m | 90.5 deg, 69 km | Mons Mouton (0.3 km) |
  | Haworth, 2 m | 94.5 deg, 111 km | Leibnitz Beta Plateau / Mons Mouton massif (5.5 km) |
  | Haworth, 2 m | 205.0 deg, 67 km | de Gerlache Rim (0.3 km) |

  Candidate sites sit on the highest, best-lit summits and rims, which are exactly the features
  that close a horizon, so this agreement is expected when the geometry is right. Peaks closer
  than a few kilometres are below the resolution of the mosaic (474 m/pixel) and are not checked
  this way.

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

## Longest sunlit spells versus Wueller et al. (2026) (T22)

Script: `pipeline/compare_wueller.py`; table: `data/processed/validation/wueller2026_comparison.csv`.

**Reference.** Wueller et al. (2026, JGR Planets 131, e2025JE009434), Table A2: for each candidate
landing site the largest number of consecutive days with sunlight, and with Sun and Earth together,
inside the lunar midsummer of each year, defined there as sub-solar latitude <= -1.5 deg (their
Table 2: 2027-10-15 to 11-14, 31 days; 2028-09-27 to 10-14, 18 days; 2029-09-15 to 10-02, 18 days).
Their model (section 2.3): LROC QuickMap "TerrainShadows" on a 60 m/pixel model, 12 h steps,
observer 2 m above the surface, shadows cast by terrain up to 150 km away; a step counts when its
value is non-zero. The Earth rule is not stated. Our site coordinates are their site coordinates
(data/sites.json, T22 part 1).

**Ours.** The same windows and observer height, our horizons (5 m and 40 m LOLA models, 300 km
rays), any part of the Sun; evaluated at 00:00 and 12:00 UTC like their 12 h steps, and every hour.
Days are half the number of consecutive 12 h steps (their READ_ME) or hours / 24.

| Site (Wueller) | Year | Sun: published / ours 12 h / ours 1 h | Sun and Earth: published / ours centre / ours any part |
|---|---|---|---|
| connecting_ridge (CR06) | 2027 | 31 / 31 / 31.0 | 31 / 9.5 / 10 |
| connecting_ridge (CR06) | 2028 | 18 / 18 / 18.0 | 17 / 15.5 / 16 |
| connecting_ridge (CR06) | 2029 | 18 / 18 / 18.0 | 17 / 15.5 / 17 |
| peak_near_shackleton (007) | 2027 | 31 / 31 / 31.0 | 31 / 10 / 11 |
| peak_near_shackleton (007) | 2028 | 17 / 18 / 18.0 | 17 / 15 / 15.5 |
| peak_near_shackleton (007) | 2029 | 18 / 18 / 18.0 | 17 / 16 / 16.5 |
| de_gerlache_rim (011) | 2027 | 31 / 31 / 31.0 | 31 / 10 / 11 |
| de_gerlache_rim (011) | 2028 | 17 / 18 / 18.0 | 17 / 16 / 16.5 |
| de_gerlache_rim (011) | 2029 | 18 / 18 / 18.0 | 17 / 17 / 17.5 |
| malapert_massif (MMA_K2023) | 2027 | 31 / 31 / 31.0 | 31 / 11 / 12 |
| malapert_massif (MMA_K2023) | 2028 | 17 / 18 / 18.0 | 17 / 16.5 / 17.5 |
| malapert_massif (MMA_K2023) | 2029 | 18 / 18 / 18.0 | 17 / 17.5 / 18 |
| haworth (HW06) | 2027 | 30 / 31 / 31.0 | 15 / 9 / 10 |
| haworth (HW06) | 2028 | 17 / 18 / 18.0 | 17 / 14.5 / 15.5 |
| haworth (HW06) | 2029 | 18 / 18 / 18.0 | 17 / 14.5 / 16 |
| nobile_rim_1 (NR101) | 2027 | 31 / 31 / 31.0 | 31 / 11.5 / 12.5 |
| nobile_rim_1 (NR101) | 2028 | 17 / 18 / 18.0 | 17 / 17 / 18 |
| nobile_rim_1 (NR101) | 2029 | 18 / 18 / 18.0 | 17 / 18 / 18 |
| nobile_rim_2 (NR205) | 2027 | 3 / 16 / 16.1 | 3 / 11 / 12 |
| nobile_rim_2 (NR205) | 2028 | 20 / 10 / 9.7 | 10 / 10 / 10 |
| nobile_rim_2 (NR205) | 2029 | 12 / 11.5 / 11.0 | 11 / 11.5 / 11.5 |
| peak_near_cabeus_b (PCB02) | 2027 | 8 / 8 / 7.7 | 8 / 8 / 8 |
| peak_near_cabeus_b (PCB02) | 2028 | 13 / 13 / 12.8 | 13 / 13 / 13 |
| peak_near_cabeus_b (PCB02) | 2029 | 13 / 12.5 / 12.8 | 13 / 12.5 / 12.5 |
| mons_mouton_plateau (MMP04) | 2027 | 8 / 9 / 9.2 | 7 / 9 / 9 |
| mons_mouton_plateau (MMP04) | 2028 | 14 / 14 / 13.8 | 14 / 14 / 14 |
| mons_mouton_plateau (MMP04) | 2029 | 15 / 15 / 15.1 | 14 / 15 / 15 |
| mons_mouton (MMO01) | 2027 | 31 / 31 / 31.0 | 31 / 10.5 / 11.5 |
| mons_mouton (MMO01) | 2028 | 17 / 18 / 18.0 | 17 / 15.5 / 16.5 |
| mons_mouton (MMO01) | 2029 | 18 / 18 / 18.0 | 17 / 16.5 / 17 |
| de_gerlache_rim_2 (dGR2_K2023) | 2027 | 20 / 13 / 12.9 | 20 / 9.5 / 9.5 |
| de_gerlache_rim_2 (dGR2_K2023) | 2028 | 17 / 18 / 18.0 | 17 / 16 / 16.5 |
| de_gerlache_rim_2 (dGR2_K2023) | 2029 | 17 / 18 / 18.0 | 17 / 16.5 / 17.5 |
| slater_plain (SP06) | 2027 | 20 / 21.5 / 21.9 | 20 / 7.5 / 8.5 |
| slater_plain (SP06) | 2028 | 9 / 8.5 / 8.5 | 9 / 7.5 / 8.5 |
| slater_plain (SP06) | 2029 | 10 / 10 / 9.9 | 2 / 8.5 / 9 |

Reading:

- **Sun: 32 of 36 values agree within 1 day** (ours minus theirs: mean +0.17 day, median 0). The
  long-lit ridge and massif sites (CR06, 007, 011, MMA_K2023, NR101, MMO01, HW06) are lit through the
  whole window or one day less in both models. Our 12 h and 1 h samplings differ by at most 0.46 day,
  so the time step is not a cause.
- **Three clear differences, all at sites whose near horizon decides:** Nobile Rim 2 (NR205) in 2027,
  3 days published against 16 ours, and in 2028, 20 against 10; de Gerlache Rim 2 (dGR2_K2023) in
  2027, 20 against 13. The published 20 days for NR205 in 2028 exceed their own 18-day window, so the
  period they modelled must be longer than the window of their Table 2 (not stated in the paper).
  Further causes not separated: their 60 m model against our 5 m model near the site, shadows to
  150 km against our 300 km.
- **Sun and Earth in 2028 and 2029: 21 of 24 values agree within 1 day** when our Earth rule is "any
  part of the Earth's disc" (mean difference +0.21 day), but only 16 of 24 with "centre of the disc";
  this suggests that their Earth rule is "any part". The exception is Slater Plain (SP06) in 2029:
  2 days published against 9 ours.
- **Sun and Earth in 2027 does not agree and looks inconsistent in the paper.** For six sites (CR06,
  007, 011, MMA_K2023, NR101, MMO01) the paper gives 31 consecutive days of Sun and Earth, the whole
  window; ours are 10 to 12.5 days. Near the pole the Earth sets for a good part of every 27.2-day
  libration cycle (T09: Earth windows of 336 to 339 h at Connecting Ridge and 404 to 415 h at Malapert
  Massif), so a 31-day period with the Earth always in view cannot occur there. In 2027 the published
  Sun-and-Earth value equals the Sun value at 10 of the 12 sites, unlike 2028 and 2029; a copy of the
  Sun column is a possible explanation. Not resolved; a question for the authors.

## Power model: worked example for the engineer's review (T08)

Script: `pipeline/power_example.py --site connecting_ridge --month 2027-03 --mast 2`;
numbers: `data/processed/validation/power_example_connecting_ridge_2027-03_h2.json`;
figure: `docs/figures/power_example_connecting_ridge_2027-03_h2.png`.

**The lander values are not confirmed by the team's engineer (docs/ASSUMPTIONS.md, A14).** The
battery (20 000 Wh, usable down to 10 %, 200 Wh/kg) and the night load (46 W) follow a NASA reference
design of a small lunar lander (NASA GRC COMPASS, 2022), the cell efficiency (30.7 %) a solar-cell
datasheet. Since 2026-11-15 the panel area (0.6 m2, sized for the day load in
`pipeline/size_power_and_link.py`), the generation losses (0.23, inherent degradation of SMAD), the
day load (100 W, a design point) and the charge and discharge efficiencies (0.95 each, estimate) are
values computed or estimated by Claude because the engineer could not supply them (A14). The example shows how the model works.

Inputs: Connecting Ridge, panel and observer 2 m above the surface, 1-31 March 2027, 1 h steps (744
steps); tracking vertical panel; battery full at the start; day mode (100 W) only while the panel
covers the day load, otherwise the night load of 46 W (A15, rule chosen in T23).

| Quantity | Value |
|---|---|
| Hours with any part of the Sun visible | 511 of 744 |
| Hours in day mode (generation of at least 100 W) | 392 |
| Mean visible share of the solar disc | 50.92 % |
| Longest night | 126 h, from 2027-03-17 13:00 UTC |
| Peak generation | 196.1 W |
| Energy the panel could deliver | 73 861 Wh |
| Energy asked by the loads | 55 392 Wh |
| Generation not used because the battery was full | 19 018 Wh |
| Load not supplied because the battery was empty | 0 Wh |
| Verdict with the 20 000 Wh battery | survives; lowest state of charge 68.4 % at 2027-03-22 22:00 UTC |
| Smallest battery that survives the month | 7 014 Wh (35.1 kg at 200 Wh/kg) |

Checks that can be repeated by hand:

- Peak generation: 1361 W/m2 x 0.307 x 0.6 m2 x (1 - 0.23) = 193.0 W at 1 au with the Sun on the
  horizon. In March 2027 the Sun is 0.9895 to 0.9992 au away, so the factor is at most
  1 / 0.9895^2 = 1.021, i.e. 197.1 W; the model gives 196.1 W.
- Loads: 392 h x 100 W + 352 h x 46 W = 55 392 Wh, as in the table; 119 of the 511 sunlit hours give
  less than 100 W and stay in night mode.
- Required battery: 7 013.8 Wh x 0.9 usable = 6 312.4 Wh of deficit, which ends at the lowest state
  of charge, 2027-03-22 22:00 UTC; the 126 night hours at 46 W / 0.95 give 6 101.1 Wh of it, the
  remaining 211.3 Wh is the net deficit of weak-light hours around that night, in which the panel
  gives less than the 46 W night load. (With the earlier placeholders, 1 m2 and no losses: 6 929 Wh.)

History: with the first placeholders (1000 Wh, usable down to 20 %, 20 W at night, day load whenever
any part of the Sun is visible) the same month needed 3 899 Wh, of which 467 Wh came from 7 dusk and
dawn hours with the day load drawn under a sliver of Sun; that rule was replaced in T23 (A15).

Questions for the engineer: (1) the values in A14, in particular the panel area and the day load;
(2) the day-mode rule (A15); (3) whether the simplifications in A16 are acceptable, in particular a
heater load that does not depend on temperature.

Speed: a three-year hourly series (26 280 steps) is simulated in 13 ms and the required capacity is
found in about 1 ms, so the app can recompute on every slider move.

## Earth contact windows: worked example for the engineer's review (T09)

Script: `pipeline/comms_example.py` (default: 120 days from 2027-01-01, observer 2 m above the
surface); tables: `data/processed/validation/comms_windows_<site>_h2.csv`; timelines:
`docs/figures/comms_timeline_<site>_h2.png`.

**The link rule (docs/ASSUMPTIONS.md, A12): centre of the Earth's disc above the terrain horizon,
margin 0 deg — chosen by Claude on 2026-11-15 with the link budget below, not confirmed by an
engineer.** A window is line of sight only (A17).

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

### Link budget (added 2026-11-15)

Script: `pipeline/size_power_and_link.py`; numbers: `data/processed/validation/design_sizing.json`.
X-band direct-to-Earth downlink at 8450 MHz: lander transponder 3.98 W (IRIS V2.2, 36 dBm) and a
16 dBi patch array (both NASA SST SoA 2024, Tables 9-3 and 9-2); a 34 m ground dish with 67.35 dBi
from G = 0.6 (pi D / lambda)^2 and a system noise temperature of 30 K (both estimates; the DSN
handbook 810-005 could not be opened from this machine); 1 Mbit/s, rate-1/2 convolutional code
(4.4 dB for BER 1e-5), 2 dB other losses, 3 dB required margin.

| Quantity | Earth nearest (357 198 km) | Earth farthest (406 760 km) |
|---|---|---|
| Received Eb/N0 | 19.14 dB | 18.01 dB |
| Margin above required Eb/N0 + 3 dB | 11.74 dB | 10.61 dB |

Check by hand at 406 760 km: EIRP 6.0 + 16 = 22.0 dBW; path loss 20 log10(4 pi d / lambda) =
223.1 dB; G/T 67.35 - 14.77 = 52.58 dB/K; C/N0 = 22.0 - 223.1 - 2 + 52.58 + 228.6 = 78.0 dB-Hz;
minus 60 dB-Hz for 1 Mbit/s gives 18.0 dB.

Why the centre of the disc with 0 deg margin is used: a ray that just grazes a terrain edge loses
about 6 dB by diffraction (ITU-R P.526, knife edge at v = 0), less than the 10.6 dB of excess
margin, so the link survives grazing; the first Fresnel zone for an obstacle 1 km away has a
radius of 5.96 m (0.34 deg). This holds for these radio values only and ignores multipath.

## Mast-height trade-off for the engineer's review (T10)

Script: `pipeline/mast_tradeoff.py` (default: Connecting Ridge, Malapert Massif and Haworth,
calendar year 2027, 1 h steps); table: `data/processed/mast/mast_tradeoff_2027-01-01_2028-01-01.csv`
(all columns, one row per site and height) with the inputs and the levelling-off heights in the
`.json` file next to it; figure: `docs/figures/mast_tradeoff_2027-01-01_2028-01-01.png`.

**The lander values, the link rule (A12), the list of heights and what the mast carries (A19)
are computed or estimated by Claude (2026-11-15) and not confirmed by an engineer (A14).** The trends with height come
from the terrain and the ephemeris; the battery sizes follow the default lander of the T08 example
(20 kWh reference battery usable down to 10 %, 46 W at night, day mode only while the panel covers
the day load). The panel and the antenna sit at the top of the mast. Window and initial state: A21.

| Site | Mast, m | Sun visible, % | Mean visible disc, % | Longest night, h | Earth in view, % | Longest Earth gap, h | Battery needed, Wh | Battery mass, kg |
|---|---|---|---|---|---|---|---|---|
| Connecting Ridge | 0 | 53.4 | 47.0 | 2077 | 48.0 | 341 | 194,999 | 975.0 |
| Connecting Ridge | 2 | 79.1 | 73.1 | 302 | 50.9 | 320 | 51,466 | 257.3 |
| Connecting Ridge | 5 | 93.6 | 89.2 | 143 | 50.9 | 320 | 7,871 | 39.4 |
| Connecting Ridge | 10 | 95.1 | 92.2 | 77 | 50.9 | 320 | 5,125 | 25.6 |
| Connecting Ridge | 20 | 95.9 | 92.9 | 69 | 50.9 | 320 | 4,568 | 22.8 |
| Malapert Massif | 0 | 21.3 | 17.9 | 2063 | 52.3 | 316 | 239,777 | 1198.9 |
| Malapert Massif | 2 | 70.3 | 64.9 | 446 | 62.7 | 250 | 25,823 | 129.1 |
| Malapert Massif | 5 | 81.6 | 79.0 | 303 | 71.5 | 194 | 16,518 | 82.6 |
| Malapert Massif | 10 | 85.5 | 82.7 | 261 | 79.6 | 143 | 14,128 | 70.6 |
| Malapert Massif | 20 | 86.9 | 84.0 | 261 | 89.1 | 87 | 14,124 | 70.6 |
| Haworth | 0 | 43.8 | 36.1 | 3883 | 45.8 | 357 | 238,019 | 1190.1 |
| Haworth | 2 | 62.5 | 55.9 | 384 | 48.9 | 338 | 85,931 | 429.7 |
| Haworth | 5 | 63.3 | 57.4 | 382 | 49.6 | 336 | 74,701 | 373.5 |
| Haworth | 10 | 64.6 | 58.9 | 382 | 50.3 | 330 | 66,521 | 332.6 |
| Haworth | 20 | 67.4 | 61.1 | 381 | 51.3 | 322 | 46,522 | 232.6 |

"Sun visible" counts the hours with any part of the solar disc above the terrain horizon (A12);
"Battery needed" is the smallest capacity that keeps the state of charge above 10 % for the
whole year (none of the nights or gaps touches the edge of the window); the default lander's
20 000 Wh battery is enough at 10 and 20 m at Connecting Ridge and Malapert Massif, not at 2 m. The 0 m rows are an
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
3. **Battery mass a mast saves (default lander, 200 Wh/kg):** from 2 to 10 m, 46,341 Wh (231.7 kg)
   at Connecting Ridge and 11,695 Wh (58.5 kg) at Malapert Massif; from 2 to 20 m, 39,409 Wh
   (197.0 kg) at Haworth. With the smaller panel of 2026-11-15 (0.6 m2, losses 0.23) the partial days
   between nights recharge less, so the saving is larger than with the earlier 1 m2 placeholder.
   The mass of the mast itself is not modelled and has to be compared with these
   numbers.
4. **Earth in line of sight reacts differently:** at Malapert Massif, on the Earth-facing side,
   the mast keeps adding: 62.7 % at 2 m, 79.6 % at 10 m and 89.1 % at 20 m, with the longest gap
   falling from 250 h to 87 h, so for the link the gain has not levelled off at 20 m. At
   Connecting Ridge the Earth time does not change from 2 to 20 m (50.9 %): the Earth rises and
   sets at azimuths 134 to 141 deg behind terrain 134 to 140 km away, too far for a few metres
   to matter. A visible Earth is not yet a closed link (A17).
5. **The day-mode rule matters for the battery, not for the height.** With the first placeholder
   rule (day load whenever any part of the Sun is visible) a taller mast needed a larger battery at
   Malapert Massif (8,070 Wh at 20 m against 7,084 Wh at 10 m with the first placeholder lander):
   at 20 m a thin sliver of the Sun stayed visible for 49 hours of the deepest deficit, the 100 W
   day load was drawn and the panel gave less (3,436 Wh of the deficit). The rule chosen in T23
   (day mode only while the panel covers the day load, A15) removes this: 14,128 Wh at 10 m and
   14,124 Wh at 20 m. The heights where the gain levels off were the same under both rules.
6. **"Longest night" alone does not size the battery.** At Connecting Ridge with 2 m the longest
   night (302 h) alone needs 302 h x 46 W / 0.95 / 0.9 = 16,250 Wh, but the battery needed is
   51,466 Wh: the deepest deficit spans several nights, and the 0.6 m2 panel recharges little in
   the partial days between them.

Check that can be repeated by hand: Malapert Massif with 10 m, deepest deficit 2027-05-03 00:00 to
2027-05-13 22:00 UTC (262 h). 261 night hours at 46 W / 0.95 = 12,637.9 Wh; the battery needed,
14,128 Wh, times 0.9 is 12,715.3 Wh, so the weak-light hours of the same deficit add 77.4 Wh net. The deepest
deficits computed for Connecting Ridge and Malapert Massif at 2 and 10 m fall between 27 April and
21 May 2027, around 2027-04-27, when the Sun reaches its northernmost latitude in the lunar frame,
+1.547 deg (A21).

Speed: the ephemeris for the year (8760 steps) takes 0.3 s, the five heights of one site 0.2 s
(visibility, link windows, battery simulation and required capacity), the whole run below 1 s
plus loading.

Questions for the engineer: (1) the list of heights and what the mast carries (A19); (2) the 90 %
definition of "levels off" (A20); (3) the day-mode rule (A15); (4) whether a year of operation (A21)
is the right case for sizing, or a mission window; (5) the mass of a 5, 10 and 20 m mast, to compare
with the battery mass it saves.

## Landing-date search (T11)

Script: `pipeline/landing_windows.py --site <site> --mast 2` (default: landing days 2027-01-01 to
2028-12-31, one landing at 00:00 UTC per day); tables:
`data/processed/windows/landing_<site>_h2_2027-01-01_2029-01-01.csv` (one row per landing day)
and `.json` (inputs and the five best days); figures:
`docs/figures/landing_calendar_<site>_h2_2027-01-01_2029-01-01.png` (calendar) and
`docs/figures/landing_timeline_<site>_h2_2027-01-01_2029-01-01.png` (hourly Sun and Earth with
the best missions, and the battery margin per landing day).

**The lander values are not confirmed by the team's engineer (A14; default lander of the T08
example, 20 kWh battery); the mission length of 14 days, the battery full at landing (A23) and
the link rule (A12) are estimates by Claude (2026-11-15), not confirmed by an engineer.** The pattern over the calendar comes from the terrain and the
ephemeris; which days pass depends on the battery.

| | Connecting Ridge, 2 m | Malapert Massif, 2 m |
|---|---|---|
| Landing days that survive 14 days (default lander) | 731 of 731 | 731 of 731 |
| Lowest state of charge of any mission (allowed 10 %) | 21.1 % | 18.7 % |
| Days with the best possible score (battery never below full, Earth in view all 14 days) | 11 | 40 |
| Five best landing days (A22) | 2027-08-16, 2027-12-30, 2028-07-08, 2028-08-04, 2028-08-31 | 2027-01-10, 2027-08-15, 2027-09-11, 2027-10-08, 2027-11-04 |
| Time: ephemeris / visibility / calendar of 731 missions | 0.5 / 0.05 / 0.3 s | 0.5 / 0.06 / 0.3 s |

Reading:

- **With the default lander every landing day survives a 14-day mission** at both sites; the
  20 kWh reference battery leaves at least 21.1 % (Connecting Ridge) and 18.7 % (Malapert Massif).
- **Season (illustration with a 5 kWh battery, `--battery-wh 5000`, files with the suffix
  `_battery5000`).** At Connecting Ridge 504 of 731 landing days survive; the failing landing days
  lie between 2027-03-08 and 2027-06-29 and between 2028-02-10 and 2028-06-16, with a few surviving
  days in between: the southern winter of the Moon, when the Sun stands north of the lunar equator
  (+1.547 deg on 2027-04-27, A21).
- **History of the load rule.** With the first placeholders (1000 Wh, day load whenever any part of
  the Sun is visible) missions landing 2027-08-01 to 08-14 failed without a single night: for 28 h
  only a sliver of the Sun was visible (15.9 % of the disc), the panel gave 63 W against the 100 W
  day load, and the mission needed 1,362 Wh. Under the rule chosen in T23 (A15) the same mission
  needs 19 Wh.
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
| Power-system values | Every verdict and battery size depends on the lander; the defaults follow public sources (NASA reference lander, cell datasheet, SMAD) or are design estimates by Claude | not a model error: replace by a reviewed lander design | A14 |
| Day-mode rule | Whether a sliver of Sun puts the lander into day mode | the first rule turned a 19 Wh mission into 1362 Wh and made a 20 m mast need more battery than 10 m; the rule chosen in T23 removes both; still to be confirmed by the engineer | A15 |
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

`uv run pytest -q` runs 287 tests (2026-11-14, all passing): ephemeris against the committed
Horizons tables and Apollo 11, horizons on synthetic and real terrain, disc fractions and window
statistics, energy balance and exact battery sizing against simulation under both day-mode rules, contact windows on a
synthetic libration, the mast trade-off and landing-date search on synthetic series with known
answers, the precomputed data against a fresh SPICE run, and the Streamlit app on all pages with
the SPICE kernels and the terrain rasters disabled.

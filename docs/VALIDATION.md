# Validation

How the results were checked against independent sources. Numbers in this file are outputs
of the scripts named in each section; nothing is typed in by hand from memory.

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
  of a different resolution. The Earth swings about +-7 deg around the horizon while the Sun
  stays within about +-1.5 deg of it, so the same horizon error changes the Sun statistic
  several times more than the Earth statistic; this matches the tighter Earth agreement.
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

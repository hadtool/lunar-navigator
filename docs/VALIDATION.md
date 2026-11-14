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

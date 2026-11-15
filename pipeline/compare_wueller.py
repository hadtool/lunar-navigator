"""Compare our illumination with Wueller et al. (2026), Table A2 (task T22).

    uv run python pipeline/compare_wueller.py

Their quantity: the largest number of consecutive days with sunlight (and with Sun and Earth
together) inside the lunar "midsummer" of a year (sub-solar latitude <= -1.5 deg; windows of
their Table 2), from LROC QuickMap TerrainShadows on a 60 m/pixel model, 12 h steps, observer
2 m above the surface, shadows up to 150 km; a step counts as lit when its value is non-zero
(any part of the Sun). Ours: the same windows, the cached horizon at 2 m (5 m and 40 m LOLA
models, 300 km rays) and the stored ephemeris, evaluated (a) at 00:00 and 12:00 UTC, as their 12 h
steps, and (b) every hour. The Earth rule of the paper is not stated, so both of ours are shown.

Writes data/processed/validation/wueller2026_comparison.csv and prints a Markdown table.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from lunarnav import store
from lunarnav.comms import RULE_ANY_PART, RULE_CENTRE, CommSettings, link_mask
from lunarnav.visibility import runs

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "validation" / "wueller2026_comparison.csv"

#: Midsummer windows of Wueller et al. (2026), Table 2: first and last day, inclusive.
WINDOWS = {2027: ("2027-10-15", "2027-11-14"), 2028: ("2028-09-27", "2028-10-14"), 2029: ("2029-09-15", "2029-10-02")}

#: Wueller et al. (2026), Table A2, for the sites of data/sites.json: (Sun, Sun and Earth) per year.
PUBLISHED = {
    "CR06": {2027: (31, 31), 2028: (18, 17), 2029: (18, 17)},
    "007": {2027: (31, 31), 2028: (17, 17), 2029: (18, 17)},
    "011": {2027: (31, 31), 2028: (17, 17), 2029: (18, 17)},
    "MMA_K2023": {2027: (31, 31), 2028: (17, 17), 2029: (18, 17)},
    "HW06": {2027: (30, 15), 2028: (17, 17), 2029: (18, 17)},
    "NR101": {2027: (31, 31), 2028: (17, 17), 2029: (18, 17)},
    "NR205": {2027: (3, 3), 2028: (20, 10), 2029: (12, 11)},
    "PCB02": {2027: (8, 8), 2028: (13, 13), 2029: (13, 13)},
    "MMP04": {2027: (8, 7), 2028: (14, 14), 2029: (15, 14)},
    "MMO01": {2027: (31, 31), 2028: (17, 17), 2029: (18, 17)},
    "dGR2_K2023": {2027: (20, 20), 2028: (17, 17), 2029: (17, 17)},
    "SP06": {2027: (20, 20), 2028: (9, 9), 2029: (10, 2)},
}


def longest(mask: np.ndarray) -> int:
    return max((stop - start for start, stop in runs(mask)), default=0)


def main() -> None:
    centre = store.load_centre_ephemeris()
    sites = [site for site in store.load_sites() if site.get("wueller2026_site") in PUBLISHED]
    rows = []
    for site in sites:
        published = PUBLISHED[site["wueller2026_site"]]
        for year, (first, last) in WINDOWS.items():
            stop = (np.datetime64(last) + np.timedelta64(1, "D")).astype(str)
            track, vis = store.observer(store.load_horizon(site["id"], 2.0), store.centre_window(centre, first, stop))
            times = np.asarray(track.times_utc)
            sun = vis.sun_fraction > 0.0
            earth = {rule: link_mask(vis, track.earth.angular_radius_rad, CommSettings(rule))
                     for rule in (RULE_CENTRE, RULE_ANY_PART)}
            twelve = (times.astype("datetime64[h]").astype(int) % 12) == 0  # 00:00 and 12:00 UTC
            rows.append({
                "site": site["id"], "wueller_site": site["wueller2026_site"], "year": year,
                "window": f"{first}..{last}", "window_days": int(len(times) // 24),
                "published_sun_days": published[year][0],
                "ours_sun_days_12h": longest(sun[twelve]) / 2.0,
                "ours_sun_days_1h": longest(sun) / 24.0,
                "published_sun_earth_days": published[year][1],
                "ours_sun_earth_centre_days_12h": longest((sun & earth[RULE_CENTRE])[twelve]) / 2.0,
                "ours_sun_earth_any_part_days_12h": longest((sun & earth[RULE_ANY_PART])[twelve]) / 2.0,
            })
    table = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT, index=False)
    print("| Site (Wueller) | Year | Sun: published / ours 12 h / ours 1 h | Sun and Earth: published / ours centre / ours any part |")
    print("|---|---|---|---|")
    for row in table.itertuples(index=False):
        print(f"| {row.site} ({row.wueller_site}) | {row.year} | {row.published_sun_days} / {row.ours_sun_days_12h:g} / "
              f"{row.ours_sun_days_1h:.1f} | {row.published_sun_earth_days} / {row.ours_sun_earth_centre_days_12h:g} / "
              f"{row.ours_sun_earth_any_part_days_12h:g} |")
    difference = table["ours_sun_days_12h"] - table["published_sun_days"]
    print(f"\nSun, ours (12 h) minus published: mean {difference.mean():+.2f} d, median {difference.median():+.1f} d, "
          f"within 1 day: {int((difference.abs() <= 1).sum())} of {len(table)}")
    print(f"written {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

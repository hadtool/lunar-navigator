"""Data, images and font of the animated demo deck in docs/demo/deck/ (task T27).

    uv run --with segno python pipeline/make_deck.py     # segno draws the QR code of the app link
    uv run python pipeline/make_deck.py                  # keeps the QR code already in the folder

The deck itself (docs/demo/deck/index.html) is static; every number it shows is read from
``data.js``, which this script writes from the project's result files:

* the mast trade-off table of T10 (data/processed/mast/);
* the stored horizons and ephemeris (data/processed/) and the default lander
  (docs/ENGINEERING_INPUTS.md): hourly Sun and Earth positions, visible share of the solar
  disc and battery state of charge at Malapert Massif for a 2 m and a 10 m mast - the same
  year-long simulation as the Power page of the app, cut to a window of six weeks;
* validation figures quoted from docs/VALIDATION.md (the script stops if they are no longer there).

Images: the Moon of the deck is a shaded relief of the LOLA 40 m model (the same recipe as the
map of the app, larger), the app screens are the screenshots of docs/demo/screenshots/. The
font is a subset of Adwaita Sans (SIL Open Font License), if it is installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lunarnav import store  # noqa: E402
from lunarnav.horizon import lat_lon_to_xy  # noqa: E402
from lunarnav.power import default_power_system, generation_from_track, required_capacity_wh, simulate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "docs" / "demo" / "deck"
SHOTS = ROOT / "docs" / "demo" / "screenshots"
MAST_TABLE = ROOT / "data" / "processed" / "mast" / "mast_tradeoff_2027-01-01_2028-01-01.csv"
LOLA_40M = ROOT / "data" / "raw" / "lola" / "LDEM_80S_40MPP_ADJ.TIF"
BASEMAP = ROOT / "data" / "processed" / "basemap" / "south_pole_relief.png"
FONT = Path("/usr/share/fonts/adwaita-sans-fonts/AdwaitaSans-Regular.ttf")

APP_URL = "https://lunar-navigator-nasa.streamlit.app/"
REPO_URL = "https://github.com/hadtool/lunar-navigator"
#: Team name as registered on the Space Apps site (None: only the members are shown).
TEAM_NAME: str | None = "COSMOSMARTES"
TEAM_MEMBERS = ["Hadiyatullo Ibrohimov", "Zikrullo Asrorov", "Umarkhon Hamdamov"]
TEAM_PLACE = "Dushanbe, Tajikistan"

STORY_SITE = "malapert_massif"
STORY_YEAR = ("2027-01-01", "2028-01-01")  # the simulation of the app's demo scenario
STORY_WINDOW = ("2027-04-08", "2027-05-22")  # the part shown in the animation
MOON_PIXELS = 1200
HALF_WIDTH_KM = 220.0
SHOT_WIDTH = 1440

#: Figures quoted on the slides; each must still be present in docs/VALIDATION.md.
VALIDATION_QUOTES = {
    "horizons_max_diff_deg": "0.000026",
    "lola_maps_mean_diff_points": "-2.68 / -0.82",
    "wueller_within_one_day": "32 of 36",
}
TESTS_PASSED = 287  # `uv run pytest -q` on 2026-11-15


def mast_numbers() -> dict:
    table = pd.read_csv(MAST_TABLE)
    out: dict = {}
    for row in table.itertuples():
        if row.mast_height_m < 2:
            continue
        out.setdefault(row.site, {"name": row.site_name})[f"h{row.mast_height_m:g}"] = {
            "sunlit_pct": round(row.sunlit_pct, 1),
            "longest_night_h": round(row.longest_night_h),
            "battery_wh": round(row.required_capacity_wh),
            "battery_kg": round(row.required_battery_mass_kg, 1),
            "earth_pct": round(row.earth_pct, 1),
        }
    return out


def story() -> dict:
    """Hourly Sun, Earth and battery at the story site for 2 m and 10 m masts."""
    system, _ = default_power_system()
    year = store.centre_window(store.load_centre_ephemeris(), *STORY_YEAR)
    times = np.asarray(year.times_utc)
    inside = (times >= np.datetime64(STORY_WINDOW[0])) & (times < np.datetime64(STORY_WINDOW[1]))
    out: dict = {"site": STORY_SITE, "window_utc": list(STORY_WINDOW), "year_utc": list(STORY_YEAR),
                 "battery_wh": system.battery_capacity_wh, "min_soc": round(1.0 - system.battery_max_dod, 3),
                 "t0_utc": str(times[inside][0])[:13], "hours": int(np.count_nonzero(inside))}
    for height in (2.0, 10.0):
        profile = store.load_horizon(STORY_SITE, height)
        track, vis = store.observer(profile, year)
        generation = generation_from_track(system, track.sun, vis.sun_fraction)
        result = simulate(system, times, generation, vis.sun_fraction)
        key = f"h{height:g}"
        out[key] = {
            "horizon_deg": np.round(np.rad2deg(profile.elevation_rad), 2).tolist(),
            "sun_fraction": np.round(vis.sun_fraction[inside], 2).tolist(),
            "soc": np.round(result.soc[:-1][inside], 3).tolist(),
            "survives": bool(result.survives),
            "first_violation_utc": result.first_violation_utc,
            "min_soc_pct": round(100 * result.min_soc, 1),
            "battery_needed_wh": round(required_capacity_wh(system, times, generation, vis.sun_fraction)),
        }
        if height == 2.0:
            azimuth = np.rad2deg(profile.azimuth_rad)
            out["azimuth_step_deg"] = round(float(azimuth[1] - azimuth[0]), 3)
            out["azimuth0_deg"] = round(float(azimuth[0]), 3)
            out["sun_az"] = np.round(np.rad2deg(track.sun.azimuth_rad[inside]) % 360, 1).tolist()
            out["sun_el"] = np.round(np.rad2deg(track.sun.elevation_rad[inside]), 2).tolist()
            out["earth_az"] = np.round(np.rad2deg(track.earth.azimuth_rad[inside]) % 360, 1).tolist()
            out["earth_el"] = np.round(np.rad2deg(track.earth.elevation_rad[inside]), 2).tolist()
            out["sun_radius_deg"] = round(float(np.rad2deg(track.sun.angular_radius_rad[inside].mean())), 3)
            out["earth_radius_deg"] = round(float(np.rad2deg(track.earth.angular_radius_rad[inside].mean())), 3)
    low, high = np.array(out["h2"]["sun_fraction"]), np.array(out["h10"]["sun_fraction"])
    partly = np.flatnonzero((low > 0.3) & (low < 0.7))
    mast_only = np.flatnonzero((low == 0) & (high > 0.9) & (np.array(out["h2"]["soc"]) < 0.3))
    out["static_hour_problem"] = int(partly[len(partly) // 2])
    out["static_hour_mast"] = int(mast_only[len(mast_only) // 2])
    return out


def sites() -> list[dict]:
    """Positions of the sites on the Moon picture, as fractions of its width and height."""
    out = []
    for item in store.load_sites():
        x, y = lat_lon_to_xy(np.deg2rad(item["lat_deg"]), np.deg2rad(item["lon_east_deg"]))
        out.append({"id": item["id"], "name": item["name"],
                    "fx": round(0.5 + x / 1000.0 / (2 * HALF_WIDTH_KM), 4),
                    "fy": round(0.5 - y / 1000.0 / (2 * HALF_WIDTH_KM), 4)})
    return out


def moon_picture(out: Path) -> str:
    """Shaded relief of the south pole, darker and more contrasted than the map of the app."""
    if LOLA_40M.is_file():
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds

        import build_basemap

        half = HALF_WIDTH_KM * 1000.0
        with rasterio.open(LOLA_40M) as dataset:
            window = from_bounds(-half, -half, half, half, dataset.transform)
            height = dataset.read(1, window=window, out_shape=(MOON_PIXELS, MOON_PIXELS), resampling=Resampling.average)
        shade = build_basemap.shaded_relief(height.astype(np.float64), 2.0 * half / MOON_PIXELS)
        tone = np.clip(18.0 + 232.0 * shade**1.15, 0, 255).astype(np.uint8)
        image, source = Image.fromarray(tone, mode="L"), f"{LOLA_40M.name} (LOLA 40 m model, PGDA product 90)"
    else:  # no terrain on this machine: enlarge the map of the app
        image = Image.open(BASEMAP).convert("L").resize((MOON_PIXELS, MOON_PIXELS), Image.LANCZOS)
        source = f"{BASEMAP.name} (enlarged)"
    image.save(out, "WEBP", quality=84, method=6)
    return source


def screenshots() -> dict:
    names = {"site": "01b_site_malapert_massif.png", "power2": "02a_power_does_not_survive.png",
             "power10": "02b_power_survives.png", "mast": "03_mast_tradeoff.png", "landing": "05_landing_windows.png"}
    out = {}
    for key, name in names.items():
        image = Image.open(SHOTS / name).convert("RGB")
        scale = SHOT_WIDTH / image.width
        image = image.resize((SHOT_WIDTH, round(image.height * scale)), Image.LANCZOS)
        image.save(DECK / "img" / f"shot_{key}.webp", "WEBP", quality=82, method=6)
        out[key] = {"file": f"img/shot_{key}.webp", "width": image.width, "height": image.height}
    return out


def font_subset(out: Path) -> str | None:
    if not FONT.is_file():
        return None
    from fontTools import subset
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.flavor = "woff"
    options.layout_features = ["kern", "liga", "calt", "tnum", "case", "ccmp", "locl", "mark", "mkmk"]
    font = TTFont(FONT)
    licence = font["name"].getDebugName(13) or ""
    subsetter = subset.Subsetter(options)
    codes = list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + [
        0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2190, 0x2192, 0x2212, 0x2248, 0x2264,
        0x2265, 0x00D7, 0x2032, 0x2033]
    subsetter.populate(unicodes=codes)
    subsetter.subset(font)
    font.flavor = "woff"
    font.save(out)
    return licence.strip()


def qr_code(out: Path) -> bool:
    try:
        import segno
    except ImportError:
        return out.is_file()
    segno.make(APP_URL, error="m").save(out, kind="svg", scale=10, border=2, dark="#0b1020", light="#ffffff",
                                        xmldecl=False, svgns=True, nl=False)
    return True


def main() -> None:
    (DECK / "img").mkdir(parents=True, exist_ok=True)
    (DECK / "fonts").mkdir(parents=True, exist_ok=True)
    validation = (ROOT / "docs" / "VALIDATION.md").read_text(encoding="utf-8")
    for key, quote in VALIDATION_QUOTES.items():
        if quote not in validation:
            raise SystemExit(f"docs/VALIDATION.md no longer contains '{quote}' ({key}); update the deck text")
    moon_source = moon_picture(DECK / "img" / "moon.webp")
    licence = font_subset(DECK / "fonts" / "DeckSans.woff")
    data = {
        "si_disclosure": "Deck (layout, illustrations, animation, code) generated with Claude (Anthropic), an AI "
                         "assistant; the numbers are computed from NASA data by the project's code.",
        "team": {"name": TEAM_NAME, "members": TEAM_MEMBERS, "place": TEAM_PLACE},
        "links": {"app": APP_URL, "repo": REPO_URL},
        "mast": mast_numbers(),
        "story": story(),
        "sites": sites(),
        "validation": {**VALIDATION_QUOTES, "tests": TESTS_PASSED},
        "shots": screenshots(),
        "moon": {"file": "img/moon.webp", "source": moon_source, "half_width_km": HALF_WIDTH_KM},
        "qr": "img/qr.svg" if qr_code(DECK / "img" / "qr.svg") else None,
        "font_licence": licence,
    }
    text = "// Written by pipeline/make_deck.py - do not edit by hand.\nwindow.DECK = " + json.dumps(
        data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    (DECK / "data.js").write_text(text, encoding="utf-8")
    story_data = data["story"]
    print(f"data.js: {len(text) / 1024:.0f} KB; story {story_data['hours']} h from {story_data['t0_utc']}")
    for key in ("h2", "h10"):
        item = story_data[key]
        print(f"  {key}: survives={item['survives']} first_violation={item['first_violation_utc']} "
              f"min_soc={item['min_soc_pct']} % battery_needed={item['battery_needed_wh']} Wh")
    print(f"  Sun elevation {min(story_data['sun_el'])} .. {max(story_data['sun_el'])} deg; Earth elevation "
          f"{min(story_data['earth_el'])} .. {max(story_data['earth_el'])} deg, azimuth "
          f"{min(story_data['earth_az'])} .. {max(story_data['earth_az'])}")
    print(f"  horizon 2 m {min(story_data['h2']['horizon_deg'])} .. {max(story_data['h2']['horizon_deg'])} deg; "
          f"10 m {min(story_data['h10']['horizon_deg'])} .. {max(story_data['h10']['horizon_deg'])} deg")
    print(f"  static hours: problem {story_data['static_hour_problem']}, mast {story_data['static_hour_mast']}")
    print(f"  moon: {moon_source}; font licence: {(licence or 'no font')[:90]}; qr: {data['qr']}")
    for path in sorted(DECK.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(DECK)}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

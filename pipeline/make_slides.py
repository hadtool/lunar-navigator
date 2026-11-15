"""Seven demo slides (16:9) for the Space Apps submission (task T17).

    uv run python pipeline/make_slides.py

Reads the screenshots in docs/demo/screenshots/ and the mast trade-off table of T10, writes
docs/demo/slides.pdf and one PNG per slide in docs/demo/slides/. Text is English, as the
submission requires; numbers come from the project's result files or docs/VALIDATION.md.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
SHOTS = DEMO / "screenshots"
MAST_TABLE = ROOT / "data" / "processed" / "mast" / "mast_tradeoff_2027-01-01_2028-01-01.csv"

INK, SECOND, MUTED, ACCENT, BAD, GOOD = "#0b0b0b", "#52514e", "#898781", "#2a78d6", "#d03b3b", "#0ca30c"
WIDTH, HEIGHT = 13.333, 7.5


def slide(title: str, subtitle: str | None = None):
    fig = plt.figure(figsize=(WIDTH, HEIGHT), dpi=120, facecolor="white")
    fig.text(0.05, 0.9, title, fontsize=26, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.05, 0.83, subtitle, fontsize=14, color=SECOND, va="top")
    return fig


def bullets(fig, items: list[str], x: float = 0.05, y: float = 0.74, size: float = 15, gap: float = 0.085,
            width: int = 58) -> None:
    import textwrap

    line_height = 1.35 * size / 72.0 / HEIGHT  # one text line as a fraction of the slide height
    for item in items:
        lines = textwrap.wrap(item, width=width)
        fig.text(x, y, "•  " + "\n    ".join(lines), fontsize=size, color=INK, va="top", linespacing=1.35)
        y -= len(lines) * line_height + gap * 0.45


#: Part of a screenshot to show (fractions of width and height): the page without the sidebar.
MAIN = (0.215, 0.08, 0.985, 1.0)


def picture(fig, path: Path, box: tuple[float, float, float, float], caption: str | None = None,
            crop: tuple[float, float, float, float] = MAIN) -> None:
    image = mpimg.imread(path)
    rows, cols = image.shape[:2]
    image = image[int(crop[1] * rows):int(crop[3] * rows), int(crop[0] * cols):int(crop[2] * cols)]
    axis = fig.add_axes(box)
    axis.imshow(image)
    axis.set_axis_off()
    for spine in axis.spines.values():
        spine.set_visible(False)
    if caption:
        fig.text(box[0], box[1] - 0.03, caption, fontsize=11, color=SECOND, va="top")


def footer(fig, number: int) -> None:
    fig.text(0.05, 0.03, "Lunar Landing Site Navigator · NASA Space Apps Challenge 2026", fontsize=10, color=MUTED)
    fig.text(0.95, 0.03, f"{number} / 7", fontsize=10, color=MUTED, ha="right")


def main() -> None:
    mast = pd.read_csv(MAST_TABLE).set_index(["site", "mast_height_m"])
    ridge2, ridge10 = mast.loc[("connecting_ridge", 2.0)], mast.loc[("connecting_ridge", 10.0)]
    malapert2, malapert20 = mast.loc[("malapert_massif", 2.0)], mast.loc[("malapert_massif", 20.0)]
    slides_dir = DEMO / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    figures = []

    fig = slide("Lunar Landing Site Navigator")
    fig.text(0.05, 0.72, "Will a lander with this power system\nsurvive at this lunar south-pole site\non these dates — "
             "and how much\ndoes a mast help?", fontsize=22, color=ACCENT, va="top", linespacing=1.4)
    fig.text(0.05, 0.38, "A web tool on NASA LOLA terrain and SPICE\nephemerides, checked against JPL Horizons\n"
             "and the published LOLA illumination maps.", fontsize=15, color=SECOND, va="top", linespacing=1.4)
    fig.text(0.05, 0.16, "NASA Space Apps Challenge 2026 · challenge “Lunar Landing Site Navigator”\n"
             "Team: Hadiyatullo Ibrohimov, Zikrullo Asrorov, Umarkhon Hamdamov · App: [link] · Code: github.com/hadtool/lunar-navigator", fontsize=13, color=SECOND,
             va="top", linespacing=1.5)
    picture(fig, SHOTS / "01_site_connecting_ridge.png", (0.57, 0.24, 0.41, 0.58))
    figures.append(fig)

    fig = slide("The problem", "At the south pole the Sun and the Earth stay close to the horizon")
    bullets(fig, [
        "The Sun never rises more than 90° − |latitude| + 1.6°: 2° to 8° at the candidate sites.",
        "The Earth swings around the horizon with the libration, by about ±7°.",
        "So the exact terrain around the landing point, the dates and the height of the panel and the antenna "
        "decide whether a lander has power and a line of sight home.",
        "Illumination maps tell how often. Engineers need: does my lander survive here, then? Is a mast worth it?",
    ], width=60)
    picture(fig, SHOTS / "01_site_connecting_ridge.png", (0.6, 0.18, 0.37, 0.55),
            "Grey: terrain · orange: Sun · blue: Earth (hourly)")
    footer(fig, 2)
    figures.append(fig)

    fig = slide("What we built", "A Streamlit app on an offline pipeline · 15 sites · any dates in 2027-2029")
    bullets(fig, [
        "Site & dates: map, real terrain horizon, Sun and Earth paths, when each is in view.",
        "Power: panel, battery and loads as sliders; hour-by-hour battery; survives or not; "
        "the smallest battery, solved exactly.",
        "Mast trade-off: light, longest night, battery and Earth link for masts of 0-20 m.",
        "Compare sites · Landing windows (calendar, best days) · Methods & data.",
    ], size=14, width=52)
    picture(fig, SHOTS / "05_landing_windows.png", (0.5, 0.12, 0.48, 0.68), "Landing windows: every landing day of 2027",
            crop=(0.215, 0.1, 0.985, 0.82))
    footer(fig, 3)
    figures.append(fig)

    malapert10 = mast.loc[("malapert_massif", 10.0)]
    fig = slide("Does the lander survive?",
                "Malapert Massif, year 2027, 20 kWh battery (default lander, not confirmed by our engineer)")
    picture(fig, SHOTS / "02a_power_does_not_survive.png", (0.03, 0.17, 0.46, 0.6), "Panel and antenna at 2 m: does not survive",
            crop=(0.215, 0.45, 0.985, 0.99))
    picture(fig, SHOTS / "02b_power_survives.png", (0.51, 0.17, 0.46, 0.6), "On a 10 m mast: survives",
            crop=(0.215, 0.45, 0.985, 0.99))
    fig.text(0.05, 0.08, f"Smallest battery that survives the year: {malapert2['required_capacity_wh']:,.0f} Wh at 2 m, "
             f"{malapert10['required_capacity_wh']:,.0f} Wh on a 10 m mast — solved exactly from the hourly energy balance.",
             fontsize=13, color=INK)
    footer(fig, 4)
    figures.append(fig)

    fig = slide("A few metres of mast", "Mast trade-off, year 2027, default lander")
    bullets(fig, [
        f"Connecting Ridge, 2 m → 10 m: sunlight {ridge2['sunlit_pct']:.1f} % → {ridge10['sunlit_pct']:.1f} %, "
        f"longest night {ridge2['longest_night_h']:.0f} h → {ridge10['longest_night_h']:.0f} h, battery "
        f"{ridge2['required_capacity_wh'] / 1000:.1f} → {ridge10['required_capacity_wh'] / 1000:.1f} kWh.",
        "The gain levels off at about 10 m on ridges; at Haworth, whose horizon is 50 km away, a mast hardly helps.",
        f"Malapert Massif, Earth in view: {malapert2['earth_pct']:.1f} % (2 m) → {malapert20['earth_pct']:.1f} % (20 m).",
        "The mast's own mass is not modelled: compare it with the battery mass saved.",
    ], size=14, width=46)
    picture(fig, SHOTS / "03_mast_tradeoff.png", (0.47, 0.14, 0.51, 0.62), crop=(0.215, 0.1, 0.985, 0.86))
    footer(fig, 5)
    figures.append(fig)

    fig = slide("NASA data make it possible", "and independent NASA references check it")
    rows = [
        ("LOLA terrain, PGDA 90 (40 m) and 78 (5 m)", "terrain horizon of every site, 720 azimuths, 300 km"),
        ("NAIF SPICE kernels, DE440", "hourly apparent Sun and Earth positions"),
        ("JPL Horizons", "check: directions agree to 0.00003°; Apollo 11 Sun 10.70°"),
        ("LOLA Sun and Earth visibility maps, PGDA 69", "check: 18.6-year statistics within 2.7 / 0.8 points"),
        ("LROC WAC mosaic (as in QuickMap)", "check: horizon peaks land on Malapert, Mons Mouton, rims"),
    ]
    y = 0.72
    for name, use in rows:
        fig.text(0.05, y, name, fontsize=14, color=INK, fontweight="bold", va="top")
        fig.text(0.5, y, use, fontsize=14, color=SECOND, va="top")
        y -= 0.095
    fig.text(0.05, 0.13, "Every file, URL and checksum: docs/SOURCES.md · full validation: docs/VALIDATION.md · 287 tests",
             fontsize=12, color=SECOND)
    footer(fig, 6)
    figures.append(fig)

    fig = slide("Limits and next steps")
    bullets(fig, [
        "Lander values follow a NASA reference lander and a cell datasheet or are placeholders; our engineer has not "
        "confirmed them yet, and the app marks them.",
        "A visible Sun is not yet power and a visible Earth is not yet a radio link.",
        "Not modelled: dust, temperatures and heaters, the lander's shadow, station schedules, relays, boulders.",
        "Next: the engineer's values (panel area, day load, radio link), thermal loads, ground-station visibility.",
    ], width=80)
    fig.text(0.05, 0.16, "Try it: Malapert Massif → Power → mast 10 m. Code: github.com/hadtool/lunar-navigator",
             fontsize=14, color=ACCENT)
    footer(fig, 7)
    figures.append(fig)

    with PdfPages(DEMO / "slides.pdf") as pdf:
        for number, figure in enumerate(figures, start=1):
            pdf.savefig(figure)
            figure.savefig(slides_dir / f"slide_{number}.png", dpi=96)
            plt.close(figure)
    print(f"wrote {DEMO / 'slides.pdf'} and {len(figures)} PNGs in {slides_dir}")


if __name__ == "__main__":
    main()

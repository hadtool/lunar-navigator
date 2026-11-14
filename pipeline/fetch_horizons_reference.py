"""Download JPL Horizons reference tables used by tests/test_ephemeris.py.

Horizons is the independent check of the local SPICE calculation. Run once:

    uv run python pipeline/fetch_horizons_reference.py

Each output file is the unmodified text response of the Horizons API. The query is
documented in docs/SOURCES.md.
"""

from pathlib import Path

import requests

API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
OUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "data"
TARGETS = {"sun": "10", "earth": "399"}

# name -> (east longitude deg, latitude deg, height km, start, stop, step)
QUERIES = {
    "connecting_ridge": (222.7090, -89.4441, 1.9557, "2027-01-01 00:00", "2029-11-01 00:00", "45 d"),
    "malapert_massif": (2.0564, -85.9919, 5.1694, "2027-01-01 06:00", "2029-11-01 06:00", "45 d"),
    "apollo_11": (23.47314, 0.67416, 0.0, "1969-07-20 20:17:40", "1969-07-20 20:18:40", "1 m"),
}


def fetch(target_id: str, lon_deg: float, lat_deg: float, height_km: float,
          start: str, stop: str, step: str) -> str:
    params = {
        "format": "text",
        "COMMAND": f"'{target_id}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon_deg},{lat_deg},{height_km}'",
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": f"'{step}'",
        "QUANTITIES": "'4,13,20'",
        "APPARENT": "'AIRLESS'",
        "ANG_FORMAT": "'DEG'",
        "CSV_FORMAT": "'YES'",
        "TIME_DIGITS": "'SECONDS'",
    }
    response = requests.get(API_URL, params=params, timeout=120)
    response.raise_for_status()
    if "$$SOE" not in response.text:
        raise RuntimeError(f"Horizons returned no ephemeris table:\n{response.text[:2000]}")
    return response.text


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for site, query in QUERIES.items():
        for target_name, target_id in TARGETS.items():
            path = OUT_DIR / f"horizons_{site}_{target_name}.txt"
            path.write_text(fetch(target_id, *query), encoding="utf-8")
            print(f"saved {path.name}")


if __name__ == "__main__":
    main()

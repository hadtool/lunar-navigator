"""Schema checks for data/sites.json."""

import json
from pathlib import Path

import pytest

SITES_FILE = Path(__file__).resolve().parents[1] / "data" / "sites.json"
REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "lat_deg": float,
    "lon_east_deg": float,
    "approximate": bool,
    "coordinate_basis": str,
    "source_url": str,
    "artemis3_2024_candidate_region": bool,
    "role": str,
}
ROLES = {"candidate", "landed_mission", "validation_only"}


@pytest.fixture(scope="module")
def document() -> dict:
    return json.loads(SITES_FILE.read_text(encoding="utf-8"))


def test_document_header(document: dict) -> None:
    assert "MOON_ME" in document["frame"]
    assert document["reference_radius_m"] == 1_737_400.0


def test_at_least_eight_sites_with_unique_ids(document: dict) -> None:
    ids = [site["id"] for site in document["sites"]]
    assert len(ids) >= 8
    assert len(ids) == len(set(ids))


def test_every_site_matches_schema(document: dict) -> None:
    for site in document["sites"]:
        for field, kind in REQUIRED_FIELDS.items():
            assert field in site, f"{site.get('id')}: missing {field}"
            assert type(site[field]) is kind, f"{site['id']}: {field} must be {kind.__name__}"
        assert -90.0 <= site["lat_deg"] <= 90.0
        assert 0.0 <= site["lon_east_deg"] < 360.0
        assert site["source_url"].startswith("https://")
        assert site["coordinate_basis"].strip()
        assert site["role"] in ROLES
        dem = site.get("pgda_5m_dem")
        assert dem is None or dem.startswith("https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/")
        if site.get("wueller2026_site") is not None:
            assert "zenodo.17084058" in site["source_url"]
            assert site["approximate"] is False


def test_required_sites_are_present(document: dict) -> None:
    ids = {site["id"] for site in document["sites"]}
    assert {"connecting_ridge", "leibnitz_beta_plateau", "malapert_massif", "haworth",
            "nobile_rim_2", "im2_athena", "apollo_11"} <= ids


def test_all_nine_artemis3_2024_regions_are_present(document: dict) -> None:
    regions = {site["id"] for site in document["sites"] if site["artemis3_2024_candidate_region"]}
    assert regions == {"peak_near_cabeus_b", "haworth", "malapert_massif", "mons_mouton_plateau",
                       "mons_mouton", "nobile_rim_1", "nobile_rim_2", "de_gerlache_rim_2",
                       "slater_plain"}


def test_polar_candidates_lie_inside_regional_dem(document: dict) -> None:
    """Every south-polar site must be covered by the 80-90 S regional terrain model."""
    for site in document["sites"]:
        if site["role"] != "validation_only":
            assert site["lat_deg"] < -80.0, site["id"]

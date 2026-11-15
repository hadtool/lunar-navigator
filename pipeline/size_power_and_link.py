"""Design calculations behind the default lander inputs (docs/ENGINEERING_INPUTS.md).

    uv run python pipeline/size_power_and_link.py

The team's engineer could not supply the power and radio values, so they are derived here
from cited sources and textbook relations; the inputs table quotes the printed numbers.
Writes data/processed/validation/design_sizing.json.

1. Panel orientation: the largest Sun elevation at any site in 2027 gives the cosine loss
   of a vertical panel.
2. Panel area: energy balance of Space Mission Analysis and Design (Wertz & Larson, 3rd ed.,
   eq. 11-5): P_sa = (P_e T_e / X_e + P_d T_d / X_d) / T_d with the path efficiencies for
   peak-power tracking (X_d = 0.80, X_e = 0.60). T_d / (T_d + T_e) is the design sunlit share,
   here the median over the 15 sites of the 2027 mean visible share of the solar disc at 2 m.
   Output per m2: solar constant at aphelion x cell efficiency x (1 - losses).
3. Link budget: X-band direct-to-Earth downlink, evaluated with lunarnav.comms at the
   smallest and largest Earth distance of 2027; the 34 m dish gain comes from the aperture
   formula G = e_a (pi D / lambda)^2.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from lunarnav.comms import LinkParameters, link_margin_db, received_ebn0_db
from lunarnav.ephemeris import centre_ephemeris, sky_track
from lunarnav.horizon import HorizonProfile, cache_path
from lunarnav.visibility import visibility

ROOT = Path(__file__).resolve().parents[1]
HORIZON_DIR = ROOT / "data" / "processed" / "horizons"
OUT = ROOT / "data" / "processed" / "validation" / "design_sizing.json"

SOLAR_CONSTANT_W_M2 = 1361.0  # at 1 au (same value as lunarnav.power)
APHELION_AU = 1.0167  # Earth-Moon system at aphelion
CELL_EFFICIENCY = 0.307  # Spectrolab XTJ Prime, BOL, AM0 28 C
INHERENT_DEGRADATION = 0.77  # SMAD 3rd ed., Table 11-35, nominal I_d
LOAD_DAY_W = 100.0
LOAD_NIGHT_W = 46.0
X_DAY, X_NIGHT = 0.80, 0.60  # SMAD 3rd ed., eq. 11-5, peak-power tracking
MAST_M = 2.0

# Link: lander side from NASA SST SoA 2024 (Tables 9-2, 9-3), ground side estimated.
FREQ_HZ = 8450e6
TX_POWER_W = 10 ** (36 / 10) / 1000  # IRIS V2.2: 36 dBm
TX_GAIN_DBI = 16.0  # EnduroSat X-band patch array
DISH_M = 34.0
APERTURE_EFFICIENCY = 0.6
RX_NOISE_K = 30.0
DATA_RATE_BPS = 1.0e6
REQUIRED_EBN0_DB = 4.4  # rate-1/2 k=7 convolutional code, Viterbi, BER 1e-5
OTHER_LOSSES_DB = 2.0  # pointing 1.0 + polarisation 0.5 + circuit 0.5
REQUIRED_MARGIN_DB = 3.0
KNIFE_EDGE_GRAZING_DB = 6.0  # ITU-R P.526: loss for a ray that grazes the edge (v = 0)


def main() -> dict:
    times = np.arange(np.datetime64("2027-01-01T00"), np.datetime64("2028-01-01T00"), np.timedelta64(1, "h"))
    eph = centre_ephemeris(times)
    sites = sorted({p.name.rsplit("_h", 1)[0] for p in HORIZON_DIR.glob("*_h2.json")})
    shares, max_elev = {}, 0.0
    earth_range = None
    for site in sites:
        profile = HorizonProfile.load(cache_path(HORIZON_DIR, site, MAST_M))
        track = sky_track(profile.lat_rad, profile.lon_east_rad,
                          profile.ground_height_m + profile.mast_height_m, eph)
        shares[site] = float(visibility(track, profile).sun_fraction.mean())
        max_elev = max(max_elev, float(np.degrees(track.sun.elevation_rad).max()))
        if earth_range is None:
            earth_range = (float(track.earth.distance_m.min()), float(track.earth.distance_m.max()))

    design_share = float(np.median(list(shares.values())))
    cosine_loss = 1.0 - math.cos(math.radians(max_elev))
    t_d, t_e = design_share, 1.0 - design_share
    array_w = (LOAD_NIGHT_W * t_e / X_NIGHT + LOAD_DAY_W * t_d / X_DAY) / t_d
    w_per_m2 = SOLAR_CONSTANT_W_M2 / APHELION_AU**2 * CELL_EFFICIENCY * INHERENT_DEGRADATION
    area = array_w / w_per_m2

    wavelength = 299_792_458.0 / FREQ_HZ
    rx_gain = 10 * math.log10(APERTURE_EFFICIENCY * (math.pi * DISH_M / wavelength) ** 2)
    link = LinkParameters(FREQ_HZ, TX_POWER_W, TX_GAIN_DBI, rx_gain, RX_NOISE_K, DATA_RATE_BPS,
                          REQUIRED_EBN0_DB, OTHER_LOSSES_DB, REQUIRED_MARGIN_DB)
    ranges = np.array(earth_range)
    ebn0 = received_ebn0_db(link, ranges)
    margin = link_margin_db(link, ranges)
    fresnel_1km = math.sqrt(wavelength * 1000.0)

    result = {
        "sun_share_2027_at_2m": shares,
        "design_sun_share_median": design_share,
        "max_sun_elevation_deg": max_elev,
        "vertical_panel_cosine_loss": cosine_loss,
        "array_power_needed_w": array_w,
        "array_output_w_per_m2_aphelion": w_per_m2,
        "panel_area_m2": area,
        "link": {
            "wavelength_m": wavelength,
            "tx_power_w": TX_POWER_W,
            "rx_gain_dbi": rx_gain,
            "earth_range_m_min_max": list(earth_range),
            "received_ebn0_db_min_max_range": ebn0.tolist(),
            "margin_above_required_db_min_max_range": margin.tolist(),
            "knife_edge_grazing_loss_db": KNIFE_EDGE_GRAZING_DB,
            "fresnel_radius_m_obstacle_at_1km": fresnel_1km,
            "fresnel_angle_deg_obstacle_at_1km": math.degrees(fresnel_1km / 1000.0),
        },
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    r = main()
    print(f"design sunlit share (median of {len(r['sun_share_2027_at_2m'])} sites, 2 m, 2027): "
          f"{r['design_sun_share_median']:.3f}")
    print(f"max Sun elevation {r['max_sun_elevation_deg']:.2f} deg -> vertical panel cosine loss "
          f"{100 * r['vertical_panel_cosine_loss']:.2f} %")
    print(f"array power needed {r['array_power_needed_w']:.1f} W; output "
          f"{r['array_output_w_per_m2_aphelion']:.1f} W/m2 -> area {r['panel_area_m2']:.3f} m2")
    L = r["link"]
    print(f"34 m dish gain {L['rx_gain_dbi']:.2f} dBi; range {L['earth_range_m_min_max']}")
    print(f"Eb/N0 {L['received_ebn0_db_min_max_range']} dB; margin above required "
          f"{L['margin_above_required_db_min_max_range']} dB (grazing loss {L['knife_edge_grazing_loss_db']} dB)")
    print(f"first Fresnel zone at 1 km: {L['fresnel_radius_m_obstacle_at_1km']:.2f} m = "
          f"{L['fresnel_angle_deg_obstacle_at_1km']:.3f} deg")

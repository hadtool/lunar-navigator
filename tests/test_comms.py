"""Tests of lunarnav.comms: contact windows on synthetic Earth elevation series, link budget."""

import numpy as np
import pytest

from lunarnav.comms import (
    BOLTZMANN_J_K,
    RULE_ANY_PART,
    RULE_CENTRE,
    RULE_FULL_DISC,
    CommSettings,
    LinkParameters,
    comm_summary,
    contact_gaps,
    contact_windows,
    default_comm_settings,
    free_space_path_loss_db,
    intervals_table,
    link_margin_db,
    link_mask,
    link_parameters_from_inputs,
    received_ebn0_db,
)
from lunarnav.inputs import load_engineering_inputs, parse_engineering_inputs
from lunarnav.visibility import Visibility, segment_fraction

EARTH_RADIUS = np.deg2rad(0.95)


def hourly(count: int) -> np.ndarray:
    return np.datetime64("2027-01-01T00:00") + np.arange(count) * np.timedelta64(1, "h")


def earth_series(clearance_deg: np.ndarray) -> Visibility:
    """Synthetic series: Earth centre this many degrees above a level horizon."""
    clearance = np.deg2rad(np.asarray(clearance_deg, dtype=float))
    fraction = segment_fraction(clearance / EARTH_RADIUS)
    return Visibility(hourly(clearance.size), np.zeros(clearance.size), fraction, np.zeros(clearance.size), clearance)


def sine_series(hours: int = 240, period_h: float = 48.0, amplitude_deg: float = 4.0) -> Visibility:
    """Earth rising and setting with a period of 48 h: above a level horizon for 24 h in every 48."""
    t = np.arange(hours) + 0.5  # sample in the middle of each hour: no sample exactly on the horizon
    return earth_series(amplitude_deg * np.sin(2.0 * np.pi * t / period_h))


def test_windows_of_a_periodic_earth_elevation() -> None:
    vis = sine_series()
    mask = link_mask(vis, EARTH_RADIUS)
    windows = contact_windows(mask, vis.times_utc)
    gaps = contact_gaps(mask, vis.times_utc)
    assert [(str(w.start_utc)[:13], w.hours) for w in windows] == [
        ("2027-01-01T00", 24.0), ("2027-01-03T00", 24.0), ("2027-01-05T00", 24.0),
        ("2027-01-07T00", 24.0), ("2027-01-09T00", 24.0),
    ]
    assert [str(w.end_utc)[:13] for w in windows][:2] == ["2027-01-02T00", "2027-01-04T00"]
    assert [(str(g.start_utc)[:13], g.hours) for g in gaps] == [
        ("2027-01-02T00", 24.0), ("2027-01-04T00", 24.0), ("2027-01-06T00", 24.0),
        ("2027-01-08T00", 24.0), ("2027-01-10T00", 24.0),
    ]
    assert windows[0].reaches_period_edge and not windows[1].reaches_period_edge
    assert gaps[-1].reaches_period_edge and not gaps[0].reaches_period_edge


def test_margin_shortens_the_windows_as_expected() -> None:
    """With amplitude 4 deg and a 2 deg margin the centre is high enough for a third of the period."""
    vis = sine_series()
    settings = CommSettings(RULE_CENTRE, np.deg2rad(2.0))
    mask = link_mask(vis, EARTH_RADIUS, settings)
    windows = contact_windows(mask, vis.times_utc)
    # sin(x) > 0.5 for x in (30, 150) deg: 16 h of every 48 h, from hour 4 to hour 20.
    assert [w.hours for w in windows] == [16.0] * 5
    assert str(windows[0].start_utc)[:13] == "2027-01-01T04"
    summary = comm_summary(mask, vis.times_utc, settings)
    assert summary.visible_pct == pytest.approx(100.0 * 16.0 / 48.0)
    assert (summary.window_count, summary.longest_window_h, summary.median_window_h) == (5, 16.0, 16.0)
    assert (summary.gap_count, summary.longest_gap_h) == (6, 32.0)
    assert summary.longest_gap_start_utc == "2027-01-01T20:00"
    assert not summary.longest_gap_reaches_period_edge
    assert (summary.rule, summary.margin_deg, summary.period_hours) == (RULE_CENTRE, pytest.approx(2.0), 240.0)


def test_disc_rules_order_and_thresholds() -> None:
    clearance_deg = np.array([-2.0, -0.94, -0.5, 0.0, 0.5, 0.94, 0.96, 2.0])
    vis = earth_series(clearance_deg)
    centre = link_mask(vis, EARTH_RADIUS, CommSettings(RULE_CENTRE))
    full = link_mask(vis, EARTH_RADIUS, CommSettings(RULE_FULL_DISC))
    any_part = link_mask(vis, EARTH_RADIUS, CommSettings(RULE_ANY_PART))
    np.testing.assert_array_equal(centre, clearance_deg > 0.0)
    np.testing.assert_array_equal(full, clearance_deg > 0.95)       # lower limb above the horizon
    np.testing.assert_array_equal(any_part, clearance_deg > -0.95)  # upper limb above the horizon
    assert np.all(full <= centre) and np.all(centre <= any_part)
    # A margin applies to the lower limb (full disc) or to the upper limb (any part).
    full_margin = link_mask(vis, EARTH_RADIUS, CommSettings(RULE_FULL_DISC, np.deg2rad(0.5)))
    np.testing.assert_array_equal(full_margin, clearance_deg > 1.45)
    any_margin = link_mask(vis, EARTH_RADIUS, CommSettings(RULE_ANY_PART, np.deg2rad(0.5)))
    np.testing.assert_array_equal(any_margin, clearance_deg > -0.45)


def test_never_and_always_visible() -> None:
    times = hourly(48)
    never = comm_summary(np.zeros(48, dtype=bool), times)
    assert (never.visible_pct, never.window_count, never.longest_window_h, never.median_window_h) == (0.0, 0, 0.0, 0.0)
    assert (never.gap_count, never.longest_gap_h, never.longest_gap_reaches_period_edge) == (1, 48.0, True)
    always = comm_summary(np.ones(48, dtype=bool), times)
    assert (always.visible_pct, always.window_count, always.longest_window_h) == (100.0, 1, 48.0)
    assert (always.gap_count, always.longest_gap_h, always.longest_gap_start_utc) == (0, 0.0, None)


def test_intervals_table_and_validation() -> None:
    vis = sine_series(96)
    table = intervals_table(contact_windows(link_mask(vis, EARTH_RADIUS), vis.times_utc))
    assert list(table.columns) == ["start_utc", "end_utc", "hours", "reaches_period_edge"]
    assert table["hours"].tolist() == [24.0, 24.0]
    assert str(table["start_utc"].iloc[1]) == "2027-01-03 00:00:00"
    assert intervals_table([]).shape == (0, 4)
    with pytest.raises(ValueError):
        contact_windows(np.ones(5, dtype=bool), hourly(6))
    with pytest.raises(ValueError):
        CommSettings("sideways")
    with pytest.raises(ValueError):
        CommSettings(RULE_CENTRE, -0.1)


def test_comm_settings_from_engineering_inputs() -> None:
    settings, placeholders = default_comm_settings({})
    assert (settings.rule, settings.margin_rad) == (RULE_CENTRE, 0.0)
    assert set(placeholders) == {"comm_earth_disk_rule", "comm_elevation_margin_deg"}
    text = (
        "| `comm_elevation_margin_deg` | Запас по углу | 2,5 | градусы | оценка |\n"
        "| `comm_earth_disk_rule` | Правило | весь диск | — | |\n"
    )
    settings, placeholders = default_comm_settings(parse_engineering_inputs(text))
    assert settings.rule == RULE_FULL_DISC
    assert settings.margin_rad == pytest.approx(np.deg2rad(2.5))
    assert placeholders == ()
    for raw, rule in [
        ("центр диска", RULE_CENTRE), ("центральная часть диска", RULE_CENTRE), ("Centre of the disc", RULE_CENTRE),
        ("любая часть диска", RULE_ANY_PART), ("full_disc", RULE_FULL_DISC), ("диск целиком", RULE_FULL_DISC),
        ("вся Земля", RULE_FULL_DISC),
    ]:
        parsed = parse_engineering_inputs(f"| `comm_earth_disk_rule` | Правило | {raw} | | |\n")
        assert default_comm_settings(parsed)[0].rule == rule, raw
    # Ambiguous or negated wording is refused, not guessed.
    for raw in ("центр диска, не весь диск", "не весь диск", "другое", "центр или весь диск"):
        parsed = parse_engineering_inputs(f"| `comm_earth_disk_rule` | Правило | {raw} | | |\n")
        with pytest.raises(ValueError, match="comm_earth_disk_rule"):
            default_comm_settings(parsed)
    # The project file must parse whatever is filled in.
    assert default_comm_settings(load_engineering_inputs())[0].rule in (RULE_CENTRE, RULE_FULL_DISC, RULE_ANY_PART)


# --- link budget ---------------------------------------------------------------------------


def test_free_space_path_loss() -> None:
    # Independent form of the same formula: 32.45 + 20 log10(f / MHz) + 20 log10(d / km).
    expected = 32.45 + 20.0 * np.log10(2200.0) + 20.0 * np.log10(384_400.0)
    assert free_space_path_loss_db(384_400e3, 2200e6) == pytest.approx(expected, abs=0.01)
    assert free_space_path_loss_db(384_400e3, 2200e6) == pytest.approx(210.99, abs=0.01)
    # Twice the distance or twice the frequency costs 6.02 dB.
    loss = free_space_path_loss_db(np.array([1e8, 2e8]), 1e9)
    assert loss[1] - loss[0] == pytest.approx(20.0 * np.log10(2.0))
    assert free_space_path_loss_db(1e8, 2e9) - free_space_path_loss_db(1e8, 1e9) == pytest.approx(6.0206, abs=1e-4)
    with pytest.raises(ValueError):
        free_space_path_loss_db(0.0, 1e9)


def test_link_margin_follows_the_budget_equation() -> None:
    """Test numbers are arbitrary and only exercise the arithmetic."""
    parameters = LinkParameters(
        frequency_hz=2200e6, tx_power_w=10.0, tx_antenna_gain_dbi=6.0, rx_antenna_gain_dbi=50.0,
        rx_system_noise_temp_k=100.0, data_rate_bps=1000.0, required_ebn0_db=4.0,
        other_losses_db=3.0, required_margin_db=3.0,
    )
    distance = 384_400e3
    # 10 dBW + 6 + 50 - 210.99 - 3 = -147.99 dBW; k T = -228.60 + 20 = -208.60 dBW/Hz; rate 30 dB-Hz.
    noise_density = 10.0 * np.log10(BOLTZMANN_J_K * 100.0)
    assert noise_density == pytest.approx(-208.60, abs=0.01)
    assert received_ebn0_db(parameters, distance) == pytest.approx(-147.99 + 208.60 - 30.0, abs=0.02)
    assert link_margin_db(parameters, distance) == pytest.approx(30.61 - 4.0 - 3.0, abs=0.02)
    # Ten times the data rate costs exactly 10 dB.
    faster = LinkParameters(**{**parameters.__dict__, "data_rate_bps": 10_000.0})
    assert link_margin_db(parameters, distance) - link_margin_db(faster, distance) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        LinkParameters(**{**parameters.__dict__, "tx_power_w": 0.0})


def test_no_link_budget_without_the_engineers_parameters() -> None:
    assert link_parameters_from_inputs({}) is None
    rows = {
        "link_frequency_mhz": "2200", "link_tx_power_w": "10", "link_tx_antenna_gain_dbi": "6",
        "link_rx_antenna_gain_dbi": "50", "link_rx_system_noise_temp_k": "100",
        "link_data_rate_bps": "1000", "link_required_ebn0_db": "4",
    }
    text = "".join(f"| `{key}` | имя | {value} | | |\n" for key, value in rows.items())
    parameters = link_parameters_from_inputs(parse_engineering_inputs(text))
    assert parameters is not None
    assert (parameters.frequency_hz, parameters.other_losses_db, parameters.required_margin_db) == (2.2e9, 0.0, 0.0)
    incomplete = "".join(f"| `{key}` | имя | {value} | | |\n" for key, value in list(rows.items())[:-1])
    assert link_parameters_from_inputs(parse_engineering_inputs(incomplete)) is None

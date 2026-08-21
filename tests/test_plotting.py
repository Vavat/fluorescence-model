import numpy as np
import pytest

from fluorescence_model.plotting import CURVE_NAMES, EMISSION_SIDE_CURVES, EXCITATION_SIDE_CURVES, build_figure
from fluorescence_model.spectrum import Spectrum
from fluorescence_model.wavelength_color import wavelength_to_hex


def _spec(center=500, kind=""):
    """Flat-topped plateau - fine for shape/dash/fill checks, but argmax on
    a plateau returns its first (lowest-wavelength) point, so don't use this
    for exact peak-wavelength color assertions - use _peaked_spec for those."""
    wl = np.arange(300, 901, 1.0)
    val = np.where(np.abs(wl - center) <= 10, 0.8, 0.0)
    return Spectrum(wl, val, kind=kind)


def _peaked_spec(center):
    wl = np.arange(300, 901, 1.0)
    val = np.clip(1.0 - np.abs(wl - center) / 20.0, 0.0, None)
    return Spectrum(wl, val)


def _edge_spec(crossing_at):
    """A longpass-style curve (0 -> 1) crossing 0.5 at `crossing_at`, whose
    peak (1.0, reached at the top of the ramp and held) is far from that
    crossing - so peak-based and crossing-based coloring clearly disagree."""
    wl = np.arange(300, 901, 1.0)
    val = np.clip((wl - (crossing_at - 20)) / 40.0, 0.0, 1.0)
    return Spectrum(wl, val, kind="dichroic_T")


def _trace(fig, name):
    matches = [t for t in fig.data if t.name == name]
    assert matches, f"no trace named {name!r} found among {[t.name for t in fig.data]}"
    return matches[0]


def test_illumination_side_dashed_detection_side_solid():
    fig = build_figure(
        fluorophore_excitation=_spec(480),
        fluorophore_emission=_spec(520),
        source=_spec(480),
        excitation_filter=_spec(480),
        dichroic=_edge_spec(500),
        emission_filter=_spec(520),
    )
    assert _trace(fig, "Fluorophore excitation").line.dash == "dash"
    assert _trace(fig, "Source spectrum").line.dash == "dash"
    assert _trace(fig, "Excitation filter").line.dash == "dash"
    assert _trace(fig, "Fluorophore emission").line.dash == "solid"
    assert _trace(fig, "Emission filter").line.dash == "solid"
    assert _trace(fig, "Dichroic (%T)").line.dash == "solid"


def test_lines_colored_by_own_peak_wavelength():
    blue_ish = _peaked_spec(460)
    red_ish = _peaked_spec(650)
    fig = build_figure(source=blue_ish, fluorophore_emission=red_ish, excitation_filter=blue_ish)
    assert _trace(fig, "Source spectrum").line.color == wavelength_to_hex(460)
    assert _trace(fig, "Fluorophore emission").line.color == wavelength_to_hex(650)
    assert _trace(fig, "Excitation filter").line.color == wavelength_to_hex(460)


def test_dichroic_colored_by_crossing_point_not_peak():
    # peaks at 1.0 across the whole plateau above the ramp, but the
    # physically meaningful edge - and thus its color - is the 50% crossing.
    dichroic = _edge_spec(550)
    fig = build_figure(dichroic=dichroic)
    assert dichroic.peak_nm() != pytest.approx(550, abs=5)  # sanity: peak is NOT near the crossing
    assert _trace(fig, "Dichroic (%T)").line.color == wavelength_to_hex(dichroic.crossing_nm())


def test_dichroic_falls_back_to_neutral_color_when_it_never_crosses():
    wl = np.arange(300, 901, 1.0)
    always_high = Spectrum(wl, np.full_like(wl, 0.9), kind="dichroic_T")
    fig = build_figure(dichroic=always_high)
    assert _trace(fig, "Dichroic (%T)").line.color == "#333333"


def test_raw_curves_are_not_filled():
    fig = build_figure(fluorophore_excitation=_spec(480), source=_spec(480), dichroic=_edge_spec(500))
    for name in ("Fluorophore excitation", "Source spectrum", "Dichroic (%T)"):
        assert _trace(fig, name).fill is None


def test_combined_curves_are_gradient_filled():
    fig = build_figure(
        excitation_combined=_spec(480),
        excitation_absorbed=_spec(480),
        emission_combined=_spec(520),
    )
    for name in (
        "Excitation light at specimen",
        "Excitation light absorbed by fluorophore",
        "Emission light at camera",
    ):
        trace = _trace(fig, name)
        assert trace.fill == "tozeroy"
        assert trace.fillgradient is not None
        assert trace.fillgradient.type == "horizontal"


def test_gradient_spans_the_full_plot_xaxis_not_each_curves_own_range():
    narrow = _spec(500)  # only nonzero within 490-510
    fig = build_figure(excitation_combined=narrow)
    trace = _trace(fig, "Excitation light at specimen")
    assert trace.fillgradient.start == pytest.approx(300.0)
    assert trace.fillgradient.stop == pytest.approx(900.0)


def test_combined_curve_alpha_baked_into_colorscale():
    fig = build_figure(
        excitation_combined=_spec(480),
        excitation_absorbed=_spec(480),
        emission_combined=_spec(520),
    )
    at_specimen = _trace(fig, "Excitation light at specimen").fillgradient.colorscale[0][1]
    absorbed = _trace(fig, "Excitation light absorbed by fluorophore").fillgradient.colorscale[0][1]
    at_camera = _trace(fig, "Emission light at camera").fillgradient.colorscale[0][1]
    assert "0.15" in at_specimen
    assert absorbed.endswith(",1.0)") or absorbed.endswith(",1)")
    assert "0.5" in at_camera


def test_combined_curves_dash_matches_illumination_detection_convention():
    fig = build_figure(excitation_combined=_spec(480), emission_combined=_spec(520))
    assert _trace(fig, "Excitation light at specimen").line.dash == "dash"
    assert _trace(fig, "Emission light at camera").line.dash == "solid"


def test_raw_curves_are_peak_normalized_combined_curves_are_not():
    fig = build_figure(
        source=_spec(480),  # peaks at 0.8 raw
        excitation_combined=_spec(480),  # same underlying data, unnormalized
    )
    assert max(_trace(fig, "Source spectrum").y) == pytest.approx(1.0)
    assert max(_trace(fig, "Excitation light at specimen").y) == pytest.approx(0.8)


def test_hidden_names_are_drawn_legendonly_not_omitted():
    fig = build_figure(
        source=_spec(480),
        fluorophore_emission=_spec(520),
        excitation_combined=_spec(480),
        hidden_names={"Source spectrum", "Excitation light at specimen"},
    )
    assert _trace(fig, "Source spectrum").visible == "legendonly"
    assert _trace(fig, "Excitation light at specimen").visible == "legendonly"
    assert _trace(fig, "Fluorophore emission").visible is True


def test_no_hidden_names_means_everything_visible():
    fig = build_figure(source=_spec(480))
    assert _trace(fig, "Source spectrum").visible is True


def test_curve_names_constant_matches_actual_legend_names():
    fig = build_figure(
        fluorophore_excitation=_spec(480),
        fluorophore_emission=_spec(520),
        source=_spec(480),
        excitation_filter=_spec(480),
        dichroic=_edge_spec(500),
        emission_filter=_spec(520),
        excitation_combined=_spec(480),
        excitation_absorbed=_spec(480),
        emission_combined=_spec(520),
    )
    assert {t.name for t in fig.data} == set(CURVE_NAMES)


def test_xaxis_is_fixed_to_300_900_regardless_of_underlying_data_range():
    wl = np.arange(300, 1201, 1.0)  # extends to 1200nm, as real Thorlabs data does
    val = np.where((wl >= 1150) & (wl <= 1200), 0.5, 0.0)
    wide_spec = Spectrum(wl, val, kind="filter_T")
    fig = build_figure(excitation_filter=wide_spec)
    assert fig.layout.xaxis.range == (300.0, 900.0)


def test_xaxis_range_fixed_even_with_no_data():
    fig = build_figure()
    assert fig.layout.xaxis.range == (300.0, 900.0)


def test_linear_scale_is_default_with_fixed_range():
    fig = build_figure(source=_spec(480))
    assert fig.layout.yaxis.type == "linear"
    assert fig.layout.yaxis.range == (0, 1.05)


def test_log_scale_clips_zeros_to_floor_not_negative_infinity():
    fig = build_figure(source=_spec(480), log_y=True)
    y = np.asarray(_trace(fig, "Source spectrum").y)
    assert fig.layout.yaxis.type == "log"
    assert (y > 0).all()
    assert y.min() == pytest.approx(1e-6)


def test_none_inputs_are_simply_omitted():
    fig = build_figure(source=_spec(480))
    names = {t.name for t in fig.data}
    assert names == {"Source spectrum"}


def test_excitation_and_emission_side_groupings_partition_curve_names_excluding_dichroic():
    # app.py's excitation-only/emission-only/both switch relies on these two
    # groups covering every curve except the dichroic (which stays shown in
    # all three states) exactly once, with no overlap or omission.
    assert set(EXCITATION_SIDE_CURVES) & set(EMISSION_SIDE_CURVES) == set()
    covered = set(EXCITATION_SIDE_CURVES) | set(EMISSION_SIDE_CURVES) | {"Dichroic (%T)"}
    assert covered == set(CURVE_NAMES)

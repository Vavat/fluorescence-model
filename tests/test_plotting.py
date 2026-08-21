import numpy as np
import pytest

from fluorescence_model.plotting import CURVE_NAMES, build_figure
from fluorescence_model.spectrum import Spectrum


def _spec(center=500, kind=""):
    wl = np.arange(300, 901, 1.0)
    val = np.where(np.abs(wl - center) <= 10, 0.8, 0.0)
    return Spectrum(wl, val, kind=kind)


def _trace(fig, name):
    matches = [t for t in fig.data if t.name == name]
    assert matches, f"no trace named {name!r} found among {[t.name for t in fig.data]}"
    return matches[0]


def test_excitation_side_curves_are_dashed_emission_side_solid():
    fig = build_figure(
        fluorophore_excitation=_spec(480),
        fluorophore_emission=_spec(520),
        source=_spec(480),
        excitation_filter=_spec(480),
        dichroic=_spec(500),
        emission_filter=_spec(520),
    )
    assert _trace(fig, "Fluorophore excitation").line.dash == "dash"
    assert _trace(fig, "Source spectrum").line.dash == "dash"
    assert _trace(fig, "Excitation filter").line.dash == "dash"
    assert _trace(fig, "Fluorophore emission").line.dash == "solid"
    assert _trace(fig, "Emission filter").line.dash == "solid"
    assert _trace(fig, "Dichroic (%T)").line.dash == "solid"


def test_raw_curves_are_not_filled():
    fig = build_figure(fluorophore_excitation=_spec(480), source=_spec(480))
    for name in ("Fluorophore excitation", "Source spectrum"):
        assert _trace(fig, name).fill is None


def test_combined_curves_are_filled():
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
        assert _trace(fig, name).fill == "tozeroy"


def test_excitation_light_fill_is_faint_absorbed_fill_is_full_strength():
    fig = build_figure(
        excitation_combined=_spec(480),
        excitation_absorbed=_spec(480),
        emission_combined=_spec(520),
    )
    # opacity is applied to the fillcolor (as an rgba alpha), not the whole
    # trace, specifically so the boundary line stays visible - see below.
    assert _trace(fig, "Excitation light at specimen").fillcolor == "rgba(255,127,14,0.15)"
    assert _trace(fig, "Excitation light absorbed by fluorophore").fillcolor == "rgba(255,127,14,1.0)"
    # emission side is unaffected by this change - stays at the existing 50% fill
    assert _trace(fig, "Emission light at camera").fillcolor == "rgba(214,39,40,0.5)"


def test_filled_curve_lines_stay_fully_opaque_regardless_of_fill_alpha():
    # The whole point: even a very faint fill must have a crisp, fully
    # opaque outline, so its true extent stays traceable when another
    # same-colored trace's fill covers it completely (e.g. "absorbed"
    # nearly coinciding with "at specimen" for a well-matched fluorophore).
    fig = build_figure(excitation_combined=_spec(480))
    trace = _trace(fig, "Excitation light at specimen")
    assert trace.opacity is None  # not scaled down at the trace level
    assert trace.line.color == "#ff7f0e"  # the plain, fully-opaque hex color


def test_hidden_names_are_drawn_legendonly_not_omitted():
    fig = build_figure(
        source=_spec(480),
        fluorophore_emission=_spec(520),
        hidden_names={"Source spectrum"},
    )
    # still present (so it stays in the legend, re-showable) - just hidden
    assert _trace(fig, "Source spectrum").visible == "legendonly"
    assert _trace(fig, "Fluorophore emission").visible is True


def test_no_hidden_names_means_everything_visible():
    fig = build_figure(source=_spec(480))
    assert _trace(fig, "Source spectrum").visible is True


def test_curve_names_constant_matches_actual_legend_names():
    # app.py's persistent multiselect is built from CURVE_NAMES - if a trace
    # name here drifts from what build_figure actually emits, the show/hide
    # control silently stops matching that trace.
    fig = build_figure(
        fluorophore_excitation=_spec(480),
        fluorophore_emission=_spec(520),
        source=_spec(480),
        excitation_filter=_spec(480),
        dichroic=_spec(500),
        emission_filter=_spec(520),
        excitation_combined=_spec(480),
        excitation_absorbed=_spec(480),
        emission_combined=_spec(520),
    )
    assert {t.name for t in fig.data} == set(CURVE_NAMES)


def test_traces_have_stable_per_role_uid_regardless_of_which_others_are_present():
    # A trace's uid must depend only on its own role, not on its position in
    # fig.data, so Plotly.js can match it to its prior legend visibility
    # state even when other traces come and go around it.
    fig_with_dichroic = build_figure(
        source=_spec(480),
        emission_filter=_spec(520),
        dichroic=_spec(500),
    )
    fig_without_dichroic = build_figure(
        source=_spec(480),
        emission_filter=_spec(520),
    )
    assert _trace(fig_with_dichroic, "Source spectrum").uid == _trace(fig_without_dichroic, "Source spectrum").uid
    assert (
        _trace(fig_with_dichroic, "Emission filter").uid == _trace(fig_without_dichroic, "Emission filter").uid
    )


def test_combined_traces_sharing_a_color_key_get_distinct_uids():
    fig = build_figure(excitation_combined=_spec(480), excitation_absorbed=_spec(480))
    at_specimen = _trace(fig, "Excitation light at specimen")
    absorbed = _trace(fig, "Excitation light absorbed by fluorophore")
    assert at_specimen.uid != absorbed.uid


def test_figure_sets_a_constant_uirevision_so_legend_state_persists():
    fig1 = build_figure(source=_spec(480))
    fig2 = build_figure(source=_spec(490))  # different data, same "shape" of figure
    assert fig1.layout.uirevision is not None
    assert fig1.layout.uirevision == fig2.layout.uirevision


def test_raw_curves_are_peak_normalized_combined_curves_are_not():
    fig = build_figure(
        source=_spec(480),  # peaks at 0.8 raw
        excitation_combined=_spec(480),  # same underlying data, unnormalized
    )
    assert max(_trace(fig, "Source spectrum").y) == pytest.approx(1.0)
    assert max(_trace(fig, "Excitation light at specimen").y) == pytest.approx(0.8)


def test_linear_scale_is_default_with_fixed_range():
    fig = build_figure(source=_spec(480))
    assert fig.layout.yaxis.type == "linear"
    assert fig.layout.yaxis.range == (0, 1.05)


def test_xaxis_is_fixed_to_300_900_regardless_of_underlying_data_range():
    # Real filter data (e.g. Thorlabs) commonly has secondary passbands well
    # past 900nm - the view should stay fixed at 300-900 regardless.
    wl = np.arange(300, 1201, 1.0)  # extends to 1200nm
    val = np.where((wl >= 1150) & (wl <= 1200), 0.5, 0.0)  # only has data *outside* 300-900
    wide_spec = Spectrum(wl, val, kind="filter_T")

    fig = build_figure(excitation_filter=wide_spec)
    assert fig.layout.xaxis.range == (300.0, 900.0)


def test_xaxis_range_fixed_even_with_no_data():
    fig = build_figure()
    assert fig.layout.xaxis.range == (300.0, 900.0)


def test_log_scale_clips_zeros_to_floor_not_negative_infinity():
    fig = build_figure(source=_spec(480), log_y=True)
    y = np.asarray(_trace(fig, "Source spectrum").y)
    assert fig.layout.yaxis.type == "log"
    assert (y > 0).all()  # zeros clipped to a positive floor, not left as 0/removed
    assert y.min() == pytest.approx(1e-6)


def test_none_inputs_are_simply_omitted():
    fig = build_figure(source=_spec(480))  # everything else left as None
    names = {t.name for t in fig.data}
    assert names == {"Source spectrum"}

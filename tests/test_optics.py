import numpy as np
import pytest

from fluorescence_model.optics import evaluate_path
from fluorescence_model.spectrum import Spectrum

GRID = np.arange(300, 901, 1.0)


def _tophat(center, half_width, kind="filter_T", peak=1.0):
    wl = np.arange(300, 901, 1.0)
    val = np.where(np.abs(wl - center) <= half_width, peak, 0.0)
    return Spectrum(wl, val, kind=kind)


def test_identical_tophat_filters_give_full_efficiency():
    # source, excitation filter, and fluorophore excitation all the same
    # top-hat band -> excitation efficiency should be ~1 (perfect overlap).
    band = _tophat(480, 10)
    result = evaluate_path(
        fluorophore_excitation=_tophat(480, 10, kind="excitation"),
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=_tophat(480, 10, kind="source"),
        excitation_filter=_tophat(480, 10),
        emission_filter=_tophat(520, 10),
    )
    assert result.excitation_efficiency == pytest.approx(1.0, abs=1e-6)
    assert result.emission_efficiency == pytest.approx(1.0, abs=1e-6)
    assert result.overall_score == pytest.approx(1.0, abs=1e-6)


def test_nonoverlapping_bands_give_zero_efficiency():
    result = evaluate_path(
        fluorophore_excitation=_tophat(480, 10, kind="excitation"),
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=_tophat(650, 10, kind="source"),  # far from excitation band
        excitation_filter=_tophat(480, 10),
        emission_filter=_tophat(520, 10),
    )
    assert result.excitation_efficiency == pytest.approx(0.0, abs=1e-6)
    assert result.overall_score == pytest.approx(0.0, abs=1e-6)


def test_partial_overlap_matches_hand_integrated_ratio():
    # source band [475,495] (half_width 10 centered 485) partially overlapping
    # excitation-filter/fluorophore-excitation band [470,490] (centered 480):
    # triple-product is nonzero on [475,490], source itself spans [475,495].
    source = _tophat(485, 10, kind="source")
    ex_filter = _tophat(480, 10)
    ex_fluor = _tophat(480, 10, kind="excitation")
    result = evaluate_path(
        fluorophore_excitation=ex_fluor,
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=source,
        excitation_filter=ex_filter,
    )
    src = source.resample(GRID)
    ex = ex_filter.resample(GRID)
    fl = ex_fluor.resample(GRID)
    expected = np.trapezoid(src * ex * fl, GRID) / np.trapezoid(src, GRID)
    assert result.excitation_efficiency == pytest.approx(expected, abs=1e-9)
    # sanity: overlap is a strict, substantial fraction (not 0 or 1)
    assert 0.5 < result.excitation_efficiency < 1.0


def test_no_filters_means_full_passthrough():
    result = evaluate_path(
        fluorophore_excitation=_tophat(480, 10, kind="excitation"),
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=_tophat(480, 10, kind="source"),
    )
    assert result.excitation_efficiency == pytest.approx(1.0, abs=1e-6)
    assert result.emission_efficiency == pytest.approx(1.0, abs=1e-6)


def test_bleed_through_warning_triggers_when_emission_filter_passes_source():
    result = evaluate_path(
        fluorophore_excitation=_tophat(480, 10, kind="excitation"),
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=_tophat(480, 30, kind="source"),  # wide source spills into emission filter band
        excitation_filter=_tophat(480, 10),
        emission_filter=_tophat(500, 15),  # overlaps the wide source tail
    )
    assert result.excitation_bleed > 0.05
    assert any("bleed through" in w for w in result.warnings)


def test_no_filters_means_full_bleed_through():
    # With no dichroic/emission filter at all, ~100% of the source's power
    # is (by this model) unblocked on the way to the detector - not some
    # diluted fraction of an undefined filter band.
    result = evaluate_path(
        fluorophore_excitation=_tophat(480, 10, kind="excitation"),
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=_tophat(480, 10, kind="source"),
    )
    assert result.excitation_bleed == pytest.approx(1.0, abs=1e-6)


def test_dichroic_reflects_excitation_and_transmits_emission():
    # A dichroic that transmits (passes) the emission band and, by the R=1-T
    # convention, reflects the excitation band.
    dichroic_T = _tophat(520, 200, kind="dichroic_T")  # transmits >~420nm and up broadly (long-pass-like within window)
    # Make it NOT transmit the excitation band by construction: zero T at 480
    wl = np.arange(300, 901, 1.0)
    t_val = np.where(wl >= 500, 1.0, 0.0)
    from fluorescence_model.spectrum import Spectrum as S

    dichroic_T = S(wl, t_val, kind="dichroic_T")

    result = evaluate_path(
        fluorophore_excitation=_tophat(480, 10, kind="excitation"),
        fluorophore_emission=_tophat(520, 10, kind="emission"),
        source=_tophat(480, 10, kind="source"),
        dichroic=dichroic_T,
    )
    # excitation band (480) has T=0 -> R=1 -> fully reflected toward sample -> full excitation efficiency
    assert result.excitation_efficiency == pytest.approx(1.0, abs=1e-6)
    # emission band (520) has T=1 -> fully transmitted to detector -> full emission efficiency
    assert result.emission_efficiency == pytest.approx(1.0, abs=1e-6)

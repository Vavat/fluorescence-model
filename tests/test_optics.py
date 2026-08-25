import numpy as np
import pytest

from fluorescence_model.optics import (
    emission_light_spectrum,
    evaluate_path,
    excitation_absorption_spectrum,
    excitation_leak_spectrum,
    excitation_light_spectrum,
)
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


def test_excitation_light_spectrum_is_source_times_filter_not_normalized():
    source = _tophat(480, 10, kind="source", peak=0.8)  # source doesn't peak at 1.0
    ex_filter = _tophat(480, 5, kind="filter_T", peak=0.5)  # narrower band, half transmission

    combined = excitation_light_spectrum(source, ex_filter)
    expected = source.resample(GRID) * ex_filter.resample(GRID)
    assert np.allclose(combined.resample(GRID), expected)
    # NOT peak-normalized: product of a 0.8 source and a 0.5 filter peaks at 0.4, not 1.0
    assert combined.value.max() == pytest.approx(0.4, abs=1e-6)


def test_excitation_light_spectrum_passthrough_with_no_filter():
    source = _tophat(480, 10, kind="source")
    combined = excitation_light_spectrum(source, excitation_filter=None)
    assert np.allclose(combined.resample(GRID), source.resample(GRID))


def test_emission_light_spectrum_is_triple_product_not_normalized():
    emission = _tophat(520, 20, kind="emission", peak=0.9)
    dichroic_T = _tophat(520, 20, kind="dichroic_T", peak=0.7)
    em_filter = _tophat(520, 20, kind="filter_T", peak=0.5)

    combined = emission_light_spectrum(emission, dichroic_T, em_filter)
    expected = emission.resample(GRID) * dichroic_T.resample(GRID) * em_filter.resample(GRID)
    assert np.allclose(combined.resample(GRID), expected)
    assert combined.value.max() == pytest.approx(0.9 * 0.7 * 0.5, abs=1e-6)


def test_emission_light_spectrum_passthrough_with_no_dichroic_or_filter():
    emission = _tophat(520, 20, kind="emission")
    combined = emission_light_spectrum(emission, dichroic=None, emission_filter=None)
    assert np.allclose(combined.resample(GRID), emission.resample(GRID))


def test_excitation_light_spectrum_includes_dichroic_reflectance():
    source = _tophat(480, 10, kind="source", peak=0.8)
    ex_filter = _tophat(480, 8, kind="filter_T", peak=0.5)
    # dichroic transmits (does NOT reflect) the excitation band -> R=0 there
    wl = np.arange(300, 901, 1.0)
    dichroic_T = Spectrum(wl, np.where(np.abs(wl - 480) <= 8, 1.0, 0.0), kind="dichroic_T")

    combined = excitation_light_spectrum(source, ex_filter, dichroic_T)
    assert combined.value.max() == pytest.approx(0.0, abs=1e-9)  # fully transmitted away from the sample, not reflected


def test_combined_spectra_match_evaluate_path_efficiencies_exactly():
    # The plotted combined curves and the efficiency metrics must agree on
    # both sides now that excitation_light_spectrum includes the dichroic
    # too (same three factors as evaluate_path's excitation_efficiency).
    ex_fluor = _tophat(480, 10, kind="excitation")
    em_fluor = _tophat(520, 10, kind="emission")
    source = _tophat(480, 10, kind="source")
    ex_filter = _tophat(480, 8, kind="filter_T")
    em_filter = _tophat(520, 8, kind="filter_T")
    wl = np.arange(300, 901, 1.0)
    dichroic_T = Spectrum(wl, np.where(wl >= 500, 1.0, 0.0), kind="dichroic_T")  # reflects <500nm, transmits >=500nm

    result = evaluate_path(
        ex_fluor, em_fluor, source, excitation_filter=ex_filter, dichroic=dichroic_T, emission_filter=em_filter
    )
    excitation_combined = excitation_light_spectrum(source, ex_filter, dichroic_T)
    emission_combined = emission_light_spectrum(em_fluor, dichroic_T, em_filter)

    src_area = np.trapezoid(source.resample(GRID), GRID)
    em_area = np.trapezoid(em_fluor.resample(GRID), GRID)
    expected_excitation_efficiency = np.trapezoid(excitation_combined.resample(GRID), GRID) / src_area
    expected_emission_efficiency = np.trapezoid(emission_combined.resample(GRID), GRID) / em_area

    assert result.excitation_efficiency == pytest.approx(expected_excitation_efficiency, abs=1e-9)
    assert result.emission_efficiency == pytest.approx(expected_emission_efficiency, abs=1e-9)


def test_excitation_absorption_spectrum_is_light_at_specimen_times_fluorophore_excitation():
    source = _tophat(480, 10, kind="source", peak=0.8)
    ex_filter = _tophat(480, 8, kind="filter_T", peak=0.5)
    ex_fluor = _tophat(480, 8, kind="excitation", peak=0.6)  # fluorophore doesn't absorb 100% even at its peak

    absorbed = excitation_absorption_spectrum(source, ex_fluor, ex_filter, dichroic=None)
    light_at_specimen = excitation_light_spectrum(source, ex_filter, dichroic=None)
    expected = light_at_specimen.resample(GRID) * ex_fluor.resample(GRID)
    assert np.allclose(absorbed.resample(GRID), expected)
    assert absorbed.value.max() == pytest.approx(0.8 * 0.5 * 0.6, abs=1e-6)


def test_excitation_absorption_spectrum_never_exceeds_light_at_specimen():
    # multiplying by a fluorophore excitation curve (a 0-1 fraction) can only
    # shrink the curve, never amplify it, at every wavelength
    source = _tophat(480, 15, kind="source")
    ex_filter = _tophat(480, 12, kind="filter_T")
    ex_fluor = _tophat(478, 10, kind="excitation", peak=0.7)  # imperfectly overlapping band

    absorbed = excitation_absorption_spectrum(source, ex_fluor, ex_filter, dichroic=None)
    light_at_specimen = excitation_light_spectrum(source, ex_filter, dichroic=None)
    assert (absorbed.resample(GRID) <= light_at_specimen.resample(GRID) + 1e-12).all()


def test_excitation_absorption_spectrum_matches_excitation_efficiency_integrand():
    ex_fluor = _tophat(480, 10, kind="excitation")
    em_fluor = _tophat(520, 10, kind="emission")
    source = _tophat(480, 10, kind="source")
    ex_filter = _tophat(480, 8, kind="filter_T")

    result = evaluate_path(ex_fluor, em_fluor, source, excitation_filter=ex_filter)
    absorbed = excitation_absorption_spectrum(source, ex_fluor, ex_filter, dichroic=None)

    src_area = np.trapezoid(source.resample(GRID), GRID)
    expected = np.trapezoid(absorbed.resample(GRID), GRID) / src_area
    assert result.excitation_efficiency == pytest.approx(expected, abs=1e-9)


def test_excitation_leak_spectrum_is_source_times_ex_filter_times_em_filter():
    source = _tophat(480, 10, kind="source", peak=0.8)
    ex_filter = _tophat(480, 10, kind="filter_T", peak=0.6)
    em_filter = _tophat(480, 10, kind="filter_T", peak=0.5)

    leak = excitation_leak_spectrum(source, ex_filter, em_filter)
    expected = source.resample(GRID) * ex_filter.resample(GRID) * em_filter.resample(GRID)
    assert np.allclose(leak.resample(GRID), expected)
    assert leak.value.max() == pytest.approx(0.8 * 0.6 * 0.5, abs=1e-6)


def test_excitation_leak_spectrum_ignores_dichroic_by_design():
    # deliberately excludes the dichroic: excitation light has to pass
    # through the excitation filter on the way in and the emission filter on
    # the way out regardless of the dichroic, which is never a perfect
    # reflector/transmitter - see the function's docstring.
    source = _tophat(480, 10, kind="source")
    leak_with_no_filters = excitation_leak_spectrum(source)
    assert np.allclose(leak_with_no_filters.resample(GRID), source.resample(GRID))


def test_excitation_leak_spectrum_requires_both_filters_to_overlap():
    # no overlap between the excitation and emission filter bands -> zero
    # leak, however wide the source is, since the light can't mechanically
    # get through both filters at once.
    source = _tophat(480, 100, kind="source")
    ex_filter = _tophat(480, 10, kind="filter_T")
    em_filter = _tophat(600, 10, kind="filter_T")  # far away, no overlap with ex_filter
    leak = excitation_leak_spectrum(source, ex_filter, em_filter)
    assert leak.value.max() == pytest.approx(0.0, abs=1e-9)


def test_excitation_leak_spectrum_matches_excitation_bleed_metric_exactly():
    ex_fluor = _tophat(480, 10, kind="excitation")
    em_fluor = _tophat(520, 10, kind="emission")
    source = _tophat(480, 30, kind="source")
    ex_filter = _tophat(480, 10, kind="filter_T")
    em_filter = _tophat(500, 15, kind="filter_T")  # overlaps ex_filter's edge, like the bleed-through test above

    result = evaluate_path(ex_fluor, em_fluor, source, excitation_filter=ex_filter, emission_filter=em_filter)
    leak = excitation_leak_spectrum(source, ex_filter, em_filter)

    src_area = np.trapezoid(source.resample(GRID), GRID)
    expected = np.trapezoid(leak.resample(GRID), GRID) / src_area
    assert result.excitation_bleed == pytest.approx(expected, abs=1e-9)

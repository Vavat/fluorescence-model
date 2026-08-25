from pathlib import Path

import numpy as np
import pytest

from fluorescence_model.filter_import import parse_filter_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_thorlabs_style_xlsx():
    result = parse_filter_file(FIXTURES / "thorlabs_style.xlsx")
    assert "%T" in result.series
    spec = result.series["%T"]
    assert spec.peak_nm() == pytest.approx(475, abs=5)
    assert spec.value.max() == pytest.approx(1.0, abs=0.01)  # % converted to fraction


def test_edmund_style_csv():
    result = parse_filter_file(FIXTURES / "edmund_style.csv")
    assert "%T" in result.series
    spec = result.series["%T"]
    assert spec.peak_nm() == pytest.approx(525, abs=5)


def test_semrock_style_dichroic_txt_exposes_both_T_and_R():
    result = parse_filter_file(FIXTURES / "semrock_style_dichroic.txt")
    assert "%T" in result.series
    assert "%R" in result.series
    t_spec = result.series["%T"]
    r_spec = result.series["%R"]
    assert t_spec.peak_nm() == pytest.approx(560, abs=5)
    # T and R should be complementary at the peak
    idx = np.argmin(np.abs(t_spec.wavelength_nm - 560))
    assert t_spec.value[idx] + r_spec.value[idx] == pytest.approx(1.0, abs=0.05)


def test_missing_file_raises():
    with pytest.raises(Exception):
        parse_filter_file(FIXTURES / "does_not_exist.csv")


def test_thorlabs_bundled_filter_set_style():
    """Real Thorlabs 'Fluorescence Filter Set' downloads pack excitation
    filter + emission filter + dichroic into one file, each with its own
    wavelength axis/range/length, interleaved with metadata text in the
    leading columns, and (sometimes) cp1252 text like a (R) glyph."""
    result = parse_filter_file(FIXTURES / "thorlabs_filter_set_style.csv")
    assert set(result.series) == {"excitation", "emission", "dichroic"}

    excitation = result.series["excitation"]
    emission = result.series["emission"]
    dichroic = result.series["dichroic"]

    assert excitation.peak_nm() == pytest.approx(475, abs=1)
    assert emission.peak_nm() == pytest.approx(520, abs=1)

    # each pair keeps its own wavelength axis/range/length - they must NOT be
    # forced onto a shared axis (excitation and dichroic happen to have the
    # same length here by construction, but different ranges; emission
    # differs in both step size and length)
    assert excitation.wavelength_nm.min() == pytest.approx(300)
    assert excitation.wavelength_nm.max() == pytest.approx(480)
    assert emission.wavelength_nm.min() == pytest.approx(300.5)
    assert len(emission.wavelength_nm) == 601
    assert dichroic.wavelength_nm.min() == pytest.approx(380)

    # % values converted to 0-1 fractions
    assert excitation.value.max() <= 1.0
    assert emission.value.max() <= 1.0
    assert dichroic.value.max() <= 1.0

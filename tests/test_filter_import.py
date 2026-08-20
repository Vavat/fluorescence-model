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

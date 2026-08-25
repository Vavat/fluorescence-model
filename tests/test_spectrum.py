import numpy as np
import pytest

from fluorescence_model.spectrum import Spectrum


def test_crossing_nm_finds_longpass_cut_on():
    # rises from 0 to 1 through 0.5 exactly at 500nm
    wl = np.arange(400, 601, 1.0)
    val = np.clip((wl - 450) / 100.0, 0.0, 1.0)  # 0 at <=450, 1 at >=550, linear between
    s = Spectrum(wl, val)
    assert s.crossing_nm(0.5) == pytest.approx(500.0, abs=0.5)


def test_crossing_nm_finds_shortpass_cut_off():
    wl = np.arange(400, 601, 1.0)
    val = np.clip(1.0 - (wl - 450) / 100.0, 0.0, 1.0)  # 1 at <=450, 0 at >=550
    s = Spectrum(wl, val)
    assert s.crossing_nm(0.5) == pytest.approx(500.0, abs=0.5)


def test_crossing_nm_returns_first_crossing_not_a_later_ripple():
    # rises through 0.5 at 450nm, then ripples above/below 0.5 again later -
    # the physically meaningful edge is the first one.
    wl = np.array([400.0, 440.0, 450.0, 460.0, 500.0, 510.0, 520.0, 600.0])
    val = np.array([0.0, 0.4, 0.5, 0.6, 0.9, 0.45, 0.9, 0.95])
    s = Spectrum(wl, val)
    assert s.crossing_nm(0.5) == pytest.approx(450.0, abs=0.5)


def test_crossing_nm_none_when_never_crosses():
    wl = np.arange(400, 601, 1.0)
    val = np.full_like(wl, 0.9)  # always above 0.5, never crosses
    s = Spectrum(wl, val)
    assert s.crossing_nm(0.5) is None


def test_crossing_nm_exact_sample_match():
    wl = np.array([400.0, 450.0, 500.0])
    val = np.array([0.2, 0.5, 0.8])
    s = Spectrum(wl, val)
    assert s.crossing_nm(0.5) == pytest.approx(450.0)


def test_peak_nm_unaffected_by_crossing_nm_addition():
    wl = np.array([400.0, 450.0, 500.0])
    val = np.array([0.2, 0.9, 0.5])
    s = Spectrum(wl, val)
    assert s.peak_nm() == pytest.approx(450.0)

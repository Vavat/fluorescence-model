import numpy as np
import pytest

from fluorescence_model.sources import laser_spectrum, led_spectrum


def test_led_peaks_at_center():
    spec = led_spectrum(center_nm=470, fwhm_nm=25)
    assert spec.peak_nm() == pytest.approx(470, abs=1)
    assert spec.value.max() == pytest.approx(1.0, abs=1e-6)


def test_led_gaussian_wavenumber_is_asymmetric_in_wavelength():
    spec = led_spectrum(center_nm=470, fwhm_nm=40)
    wl, val = spec.wavelength_nm, spec.value
    peak_idx = int(np.argmax(val))
    half = 0.5
    # distance from peak to half-max on each side should differ (asymmetric),
    # with the red (long-wavelength) side wider than the blue side.
    below = wl[:peak_idx][val[:peak_idx] >= half]
    above = wl[peak_idx:][val[peak_idx:] >= half]
    blue_half_width = wl[peak_idx] - below.min()
    red_half_width = above.max() - wl[peak_idx]
    assert red_half_width > blue_half_width


def test_led_rejects_nonpositive_params():
    with pytest.raises(ValueError):
        led_spectrum(center_nm=0, fwhm_nm=10)
    with pytest.raises(ValueError):
        led_spectrum(center_nm=470, fwhm_nm=-1)


def test_laser_is_narrow():
    led = led_spectrum(center_nm=488, fwhm_nm=25)
    laser = laser_spectrum(center_nm=488, linewidth_nm=1.0)
    grid = np.arange(300, 901, 1.0)
    led_area = np.trapezoid(led.resample(grid), grid)
    laser_area = np.trapezoid(laser.resample(grid), grid)
    assert laser_area < led_area
    assert laser.peak_nm() == pytest.approx(488, abs=1)

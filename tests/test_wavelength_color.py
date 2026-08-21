import re

import pytest

from fluorescence_model.wavelength_color import wavelength_to_hex, wavelength_to_rgb

_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


def test_blue_wavelength_is_blue_dominant():
    r, g, b = wavelength_to_rgb(460)
    assert b > r and b > g


def test_green_wavelength_is_green_dominant():
    r, g, b = wavelength_to_rgb(530)
    assert g > r and g > b


def test_red_wavelength_is_red_dominant():
    r, g, b = wavelength_to_rgb(650)
    assert r > g and r > b


def test_all_channels_in_valid_byte_range_across_visible_spectrum():
    for wl in range(380, 781, 5):
        r, g, b = wavelength_to_rgb(wl)
        for c in (r, g, b):
            assert 0 <= c <= 255


def test_outside_visible_range_falls_back_to_neutral_grey():
    uv = wavelength_to_rgb(300)
    ir = wavelength_to_rgb(900)
    assert uv == (60, 60, 60)
    assert ir == (60, 60, 60)


def test_boundary_values_do_not_raise():
    wavelength_to_rgb(380)
    wavelength_to_rgb(780)
    wavelength_to_rgb(379.999)
    wavelength_to_rgb(780.001)


def test_hex_output_is_well_formed():
    assert _HEX_RE.match(wavelength_to_hex(500))
    assert _HEX_RE.match(wavelength_to_hex(300))  # out-of-range grey fallback too


def test_hex_matches_rgb():
    r, g, b = wavelength_to_rgb(600)
    assert wavelength_to_hex(600) == "#{:02x}{:02x}{:02x}".format(r, g, b)


@pytest.mark.parametrize("wl", [380, 420, 500, 600, 700, 780])
def test_intensity_never_negative_or_nan(wl):
    r, g, b = wavelength_to_rgb(wl)
    assert all(isinstance(c, int) and c >= 0 for c in (r, g, b))

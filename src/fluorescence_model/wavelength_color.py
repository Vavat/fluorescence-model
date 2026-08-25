"""Approximate mapping from a visible-light wavelength to the RGB color a
human eye would perceive - the classic "spectrum to RGB" approximation
(after Dan Bruton's widely-used algorithm: piecewise-linear hue ramps across
the visible bands, with intensity tapering off near the edges of vision).

Not physically exact (real perceived color depends on viewing conditions and
isn't representable in sRGB at the spectral extremes), but visually
recognizable and good enough for "does this curve peak in the blue or the
red" at a glance - which is the point here, not colorimetry.
"""

from __future__ import annotations

# Visible range this approximation covers. Outside it (into UV or NIR, both
# common in this app's 300-900nm working range) there's no perceptible color
# at all, so those wavelengths fall back to a dim neutral grey rather than
# extrapolating a fake hue.
VISIBLE_MIN_NM = 380.0
VISIBLE_MAX_NM = 780.0
_NOT_VISIBLE_RGB = (60, 60, 60)


def wavelength_to_rgb(wavelength_nm: float, gamma: float = 0.8) -> tuple[int, int, int]:
    """Approximate (R, G, B) in 0-255 for a wavelength in nm."""
    wl = wavelength_nm
    if wl < VISIBLE_MIN_NM or wl > VISIBLE_MAX_NM:
        return _NOT_VISIBLE_RGB

    if wl < 440:
        r, g, b = -(wl - 440) / (440 - 380), 0.0, 1.0
    elif wl < 490:
        r, g, b = 0.0, (wl - 440) / (490 - 440), 1.0
    elif wl < 510:
        r, g, b = 0.0, 1.0, -(wl - 510) / (510 - 490)
    elif wl < 580:
        r, g, b = (wl - 510) / (580 - 510), 1.0, 0.0
    elif wl < 645:
        r, g, b = 1.0, -(wl - 645) / (645 - 580), 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0

    if wl < 420:
        factor = 0.3 + 0.7 * (wl - 380) / (420 - 380)
    elif wl < 701:
        factor = 1.0
    else:
        factor = 0.3 + 0.7 * (780 - wl) / (780 - 700)

    def adjust(c: float) -> int:
        return 0 if c <= 0.0 else round(255 * (c * factor) ** gamma)

    return (adjust(r), adjust(g), adjust(b))


def wavelength_to_hex(wavelength_nm: float, gamma: float = 0.8) -> str:
    return "#{:02x}{:02x}{:02x}".format(*wavelength_to_rgb(wavelength_nm, gamma))

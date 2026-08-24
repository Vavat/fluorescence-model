"""Modeled excitation sources: LEDs and lasers.

Neither is measured data - both are analytic approximations parameterized by
just a center wavelength and a width, since that's what's normally on a
datasheet (or knowable in advance when you're picking a part).
"""

from __future__ import annotations

import numpy as np

from .spectrum import DEFAULT_GRID_NM, Spectrum

def led_spectrum(
    center_nm: float,
    fwhm_nm: float,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> Spectrum:
    """Model an LED's emission spectrum from its center wavelength and FWHM,
    as a Gaussian defined in wavenumber (1/lambda) space, transformed back to
    wavelength. This is the standard approximation for LED spectra (see e.g.
    Ohno, "Spectral design considerations for white LED color rendering",
    Opt. Eng. 44(11), 2005): because LED emission is fundamentally a function
    of photon energy, a Gaussian that's symmetric in energy/wavenumber comes
    out asymmetric in wavelength - a sharper edge on the short-wavelength
    side and a longer tail on the long-wavelength side - matching real LED
    datasheets without needing a separate asymmetry parameter.

    (An earlier version of this function also offered a simpler two-sided
    exponential decay as a lighter-weight, symmetric alternative - removed
    since the physically-motivated asymmetric model above is a strict
    improvement with no real downside once implemented.)
    """
    if center_nm <= 0 or fwhm_nm <= 0:
        raise ValueError("center_nm and fwhm_nm must be positive")

    value = _gaussian_wavenumber(grid, center_nm, fwhm_nm)

    return Spectrum(
        wavelength_nm=grid.copy(),
        value=value,
        label=f"LED {center_nm:.0f} nm (FWHM {fwhm_nm:.0f} nm)",
        kind="source",
        source="modeled:gaussian_wavenumber",
        meta={"center_nm": center_nm, "fwhm_nm": fwhm_nm},
    )


def laser_spectrum(
    center_nm: float,
    linewidth_nm: float = 1.0,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> Spectrum:
    """Model a laser line as a narrow Gaussian (FWHM = linewidth_nm).

    Real laser diodes/DPSS lasers have linewidths from a small fraction of a
    nm to a few nm; 1 nm is a reasonable default for a laser diode when the
    exact spec is unknown. This is deliberately the same functional form as
    a very narrow LED so the same overlap-integral machinery applies.
    """
    if center_nm <= 0 or linewidth_nm <= 0:
        raise ValueError("center_nm and linewidth_nm must be positive")
    value = _gaussian(grid, center_nm, linewidth_nm)
    return Spectrum(
        wavelength_nm=grid.copy(),
        value=value,
        label=f"Laser {center_nm:.1f} nm (linewidth {linewidth_nm:.2f} nm)",
        kind="source",
        source="modeled:laser_gaussian",
        meta={"center_nm": center_nm, "linewidth_nm": linewidth_nm},
    )


_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))


def _gaussian(grid: np.ndarray, center_nm: float, fwhm_nm: float) -> np.ndarray:
    sigma = fwhm_nm * _FWHM_TO_SIGMA
    return np.exp(-0.5 * ((grid - center_nm) / sigma) ** 2)


def _gaussian_wavenumber(grid: np.ndarray, center_nm: float, fwhm_nm: float) -> np.ndarray:
    # Work in wavenumber nu = 1/lambda. Convert the requested center/FWHM
    # (given in nm, as that's what's on a datasheet) into the equivalent
    # center/width in wavenumber space, build a symmetric Gaussian there,
    # then evaluate it back at each grid wavelength.
    nu = 1.0 / grid
    nu0 = 1.0 / center_nm
    # local linearization of d(nu)/d(lambda) at the center to convert the nm
    # FWHM into a wavenumber FWHM
    fwhm_nu = fwhm_nm / (center_nm**2)
    sigma_nu = fwhm_nu * _FWHM_TO_SIGMA
    return np.exp(-0.5 * ((nu - nu0) / sigma_nu) ** 2)

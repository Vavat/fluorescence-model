"""Spectral overlap math: excitation/emission efficiency figures of merit and
bleed-through checks for a given fluorophore + source + filter/dichroic path.

Everything here is *relative*, not absolute radiometric power - none of the
inputs carry real photon-flux units (source spectra are peak-normalized
models, filter/fluorophore curves are 0-1 fractions), so these numbers are
only meaningful for comparing candidate filter/source combinations against
each other for the *same* fluorophore, not as absolute brightness predictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .spectrum import DEFAULT_GRID_NM, Spectrum, integrate

# Below this fraction of a curve's peak, treat it as noise floor for the
# purposes of bleed-through warnings (avoids flagging trivial <1% overlaps).
_BLEED_THRESHOLD = 0.02


@dataclass
class PathResult:
    excitation_efficiency: float  # 0-1, fraction of source spectrum usefully driving excitation
    emission_efficiency: float  # 0-1, fraction of emitted photons that reach the detector
    overall_score: float  # excitation_efficiency * emission_efficiency
    excitation_bleed: float  # fraction of the source's own spectral power that falls inside both the excitation and emission filter passbands (0-1)
    emission_crosstalk: float  # fraction of the illumination reaching the sample that sits inside the fluorophore's emission band (0-1)
    warnings: list[str]


def _resampled(spec: Optional[Spectrum], grid: np.ndarray) -> np.ndarray:
    if spec is None:
        return np.ones_like(grid)  # "None" filter = pass everything
    return np.clip(spec.resample(grid), 0.0, None)


def _overlap_fraction(a: np.ndarray, b: np.ndarray, grid: np.ndarray) -> float:
    """Fraction of curve a's area that coincides with non-trivial values of b."""
    a_area = integrate(grid, a)
    if a_area <= 0:
        return 0.0
    mask = b > _BLEED_THRESHOLD
    return integrate(grid, np.where(mask, a, 0.0)) / a_area


def evaluate_path(
    fluorophore_excitation: Spectrum,
    fluorophore_emission: Spectrum,
    source: Spectrum,
    excitation_filter: Optional[Spectrum] = None,
    dichroic: Optional[Spectrum] = None,
    emission_filter: Optional[Spectrum] = None,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> PathResult:
    """Score one excitation/emission optical path for a given fluorophore.

    `dichroic` should be a transmission (%T) Spectrum measured in the
    excitation-reflect / emission-transmit convention (the common case for an
    epifluorescence dichroic): it reflects the excitation band toward the
    sample and transmits the longer-wavelength emission band toward the
    detector. Its reflection curve (R = 1 - T) is used on the excitation side
    and its transmission curve directly on the emission side.
    """
    ex_fluor = np.clip(fluorophore_excitation.resample(grid), 0.0, None)
    em_fluor = np.clip(fluorophore_emission.resample(grid), 0.0, None)
    src = np.clip(source.resample(grid), 0.0, None)
    ex_filt = _resampled(excitation_filter, grid)
    em_filt = _resampled(emission_filter, grid)
    dichroic_T = _resampled(dichroic, grid)
    dichroic_R = 1.0 - dichroic_T if dichroic is not None else np.ones_like(grid)

    src_area = integrate(grid, src)
    excitation_efficiency = 0.0
    if src_area > 0:
        excitation_efficiency = integrate(grid, src * ex_filt * dichroic_R * ex_fluor) / src_area

    em_area = integrate(grid, em_fluor)
    emission_efficiency = 0.0
    if em_area > 0:
        emission_efficiency = integrate(grid, em_fluor * dichroic_T * em_filt) / em_area

    overall_score = excitation_efficiency * emission_efficiency

    # What fraction of the source's own spectral power sits inside BOTH the
    # excitation and emission filter passbands - the only way excitation
    # light can mechanically reach the camera at all, since it has to pass
    # through the excitation filter on the way in and the emission filter on
    # the way out; the dichroic isn't included here on purpose, since a real
    # dichroic is never a perfect reflector/transmitter and this is meant to
    # capture the leak risk that's fundamental to the filter choice itself,
    # not however well (or poorly) a particular dichroic happens to suppress
    # it. Scaled against the source's total power, so "no filters at all"
    # correctly reads as ~100% (everything gets through), not a diluted number.
    excitation_bleed = 0.0
    if src_area > 0:
        excitation_bleed = integrate(grid, src * ex_filt * em_filt) / src_area

    # What fraction of the light actually reaching the sample (source, after
    # the excitation filter) falls inside the fluorophore's emission band -
    # i.e. does the illumination itself contain wavelengths you're trying to
    # detect as signal. Scaled against the illumination's own total power.
    illumination = src * ex_filt
    emission_crosstalk = _overlap_fraction(illumination, em_fluor, grid)

    warnings: list[str] = []
    if excitation_bleed > 0.05:
        warnings.append(
            f"{excitation_bleed:.0%} of the excitation source's spectral power falls inside both the "
            "excitation and emission filter passbands - that light can mechanically pass through both "
            "filters, so excitation light may bleed through to the detector as background."
        )
    if emission_crosstalk > 0.05:
        warnings.append(
            f"{emission_crosstalk:.0%} of the light reaching the sample falls inside the fluorophore's "
            "own emission band - the excitation filter doesn't separate illumination from detection wavelengths well."
        )
    if excitation_efficiency < 0.01:
        warnings.append("Excitation efficiency is near zero - this source/filter combo barely excites this fluorophore.")
    if emission_efficiency < 0.01:
        warnings.append("Emission efficiency is near zero - little to no emitted light reaches the detector through this path.")

    return PathResult(
        excitation_efficiency=excitation_efficiency,
        emission_efficiency=emission_efficiency,
        overall_score=overall_score,
        excitation_bleed=excitation_bleed,
        emission_crosstalk=emission_crosstalk,
        warnings=warnings,
    )


def excitation_light_spectrum(
    source: Spectrum,
    excitation_filter: Optional[Spectrum] = None,
    dichroic: Optional[Spectrum] = None,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> Spectrum:
    """The light spectrum that actually reaches the specimen: source x
    excitation filter transmission x dichroic reflectance (R = 1 - T, same
    convention as `evaluate_path`). Deliberately NOT peak-normalized - its
    height relative to the (normalized-for-display) source/filter curves
    shows how much throughput the filter and dichroic actually cost you.

    Matches `evaluate_path`'s excitation_efficiency metric exactly (same
    three factors), unlike an earlier version of this function which omitted
    the dichroic.
    """
    src = np.clip(source.resample(grid), 0.0, None)
    ex_filt = _resampled(excitation_filter, grid)
    dichroic_R = 1.0 - _resampled(dichroic, grid) if dichroic is not None else np.ones_like(grid)
    return Spectrum(
        wavelength_nm=grid.copy(),
        value=src * ex_filt * dichroic_R,
        label="Excitation light at specimen",
        kind="source",
        source="computed",
    )


def excitation_absorption_spectrum(
    source: Spectrum,
    fluorophore_excitation: Spectrum,
    excitation_filter: Optional[Spectrum] = None,
    dichroic: Optional[Spectrum] = None,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> Spectrum:
    """The light that actually reaches the specimen (see
    `excitation_light_spectrum`), further weighted by the fluorophore's own
    excitation spectrum - i.e. which wavelengths of that light actually drive
    excitation. This is exactly the integrand behind `evaluate_path`'s
    excitation_efficiency metric, and is always <= excitation_light_spectrum
    point-by-point (weighted by a 0-1 fraction, never amplified). Deliberately
    NOT peak-normalized, same reasoning as `excitation_light_spectrum`.
    """
    light_at_specimen = excitation_light_spectrum(source, excitation_filter, dichroic, grid)
    ex_fluor = np.clip(fluorophore_excitation.resample(grid), 0.0, None)
    return Spectrum(
        wavelength_nm=grid.copy(),
        value=light_at_specimen.value * ex_fluor,
        label="Excitation light absorbed by fluorophore",
        kind="source",
        source="computed",
    )


def emission_light_spectrum(
    fluorophore_emission: Spectrum,
    dichroic: Optional[Spectrum] = None,
    emission_filter: Optional[Spectrum] = None,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> Spectrum:
    """The light spectrum that actually reaches the camera: fluorophore
    emission x dichroic transmission x emission filter transmission.
    Deliberately NOT peak-normalized, for the same reason as
    `excitation_light_spectrum` - matches the three factors in
    `evaluate_path`'s emission_efficiency metric exactly.
    """
    em = np.clip(fluorophore_emission.resample(grid), 0.0, None)
    dichroic_T = _resampled(dichroic, grid)
    em_filt = _resampled(emission_filter, grid)
    return Spectrum(
        wavelength_nm=grid.copy(),
        value=em * dichroic_T * em_filt,
        label="Emission light at camera",
        kind="emission",
        source="computed",
    )


def excitation_leak_spectrum(
    source: Spectrum,
    excitation_filter: Optional[Spectrum] = None,
    emission_filter: Optional[Spectrum] = None,
    grid: np.ndarray = DEFAULT_GRID_NM,
) -> Spectrum:
    """The excitation source's own spectral power that could mechanically
    reach the camera - source x excitation filter transmission x emission
    filter transmission. Exactly the integrand behind `evaluate_path`'s
    excitation_bleed metric, so overlaying this against
    `emission_light_spectrum` (the real signal) shows where leaking
    excitation light would actually show up relative to genuine emission.
    Deliberately NOT peak-normalized, same reasoning as the other combined
    spectra.

    Note this deliberately does NOT include the dichroic: excitation light
    has to pass through the excitation filter on the way to the sample and
    the emission filter on the way to the detector no matter what, so those
    two are the only things it can't mechanically get around - a dichroic is
    never a perfect reflector/transmitter, so leaning on it to suppress a
    leak that's already possible per the two filters alone would understate
    the risk that's fundamental to the filter selection itself.
    """
    src = np.clip(source.resample(grid), 0.0, None)
    ex_filt = _resampled(excitation_filter, grid)
    em_filt = _resampled(emission_filter, grid)
    return Spectrum(
        wavelength_nm=grid.copy(),
        value=src * ex_filt * em_filt,
        label="Excitation leak at camera",
        kind="source",
        source="computed",
    )

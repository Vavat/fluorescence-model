"""Core Spectrum type: a wavelength/value curve plus the resampling and
integration helpers everything else in this package is built on.

Every curve in the model - a fluorophore's excitation or emission spectrum, a
filter's transmission curve, a modeled LED or laser output - is represented as
a Spectrum so that optics.py can combine them on a single common wavelength
grid regardless of where they came from or what resolution they were measured
at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# Shared grid used for all spectral overlap math. 300-900 nm at 1 nm covers
# UV-to-NIR fluorescence work; extend if you need deeper UV or NIR-II dyes.
DEFAULT_GRID_NM = np.arange(300, 901, 1.0)


@dataclass
class Spectrum:
    """A wavelength (nm) vs. value curve.

    `value` is unitless: for fluorophore excitation/emission it's normalized
    intensity (0-1 peak), for filters/dichroics it's transmission or
    reflection fraction (0-1), for modeled sources it's relative spectral
    power. Values outside the measured/modeled wavelength range are treated
    as 0 when resampled.
    """

    wavelength_nm: np.ndarray
    value: np.ndarray
    label: str = ""
    kind: str = ""  # e.g. "excitation", "emission", "filter_T", "dichroic_R", "source"
    source: str = ""  # provenance, e.g. "fpbase", "fluorophores.tugraz.at", "thorlabs FF01-475/35", "modeled"
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        wl = np.asarray(self.wavelength_nm, dtype=float)
        val = np.asarray(self.value, dtype=float)
        if wl.shape != val.shape:
            raise ValueError(f"wavelength_nm and value must be same shape, got {wl.shape} vs {val.shape}")
        if wl.size == 0:
            raise ValueError("Spectrum cannot be empty")
        order = np.argsort(wl)
        self.wavelength_nm = wl[order]
        self.value = val[order]

    def resample(self, grid: np.ndarray = DEFAULT_GRID_NM) -> np.ndarray:
        """Linearly interpolate onto `grid`, returning 0 outside the data's range."""
        return np.interp(grid, self.wavelength_nm, self.value, left=0.0, right=0.0)

    def normalize(self) -> "Spectrum":
        """Return a copy peak-normalized to 1.0 (for display, not for integration)."""
        peak = np.max(np.abs(self.value))
        scaled = self.value / peak if peak > 0 else self.value
        return Spectrum(self.wavelength_nm.copy(), scaled, self.label, self.kind, self.source, dict(self.meta))

    def as_reflection(self) -> "Spectrum":
        """R = 1 - T approximation, for dichroics that only publish a %T curve."""
        return Spectrum(
            self.wavelength_nm.copy(),
            1.0 - self.value,
            label=self.label,
            kind="dichroic_R",
            source=self.source,
            meta={**self.meta, "derived": "R = 1 - T approximation"},
        )

    def peak_nm(self) -> Optional[float]:
        if self.value.size == 0:
            return None
        return float(self.wavelength_nm[int(np.argmax(self.value))])

    def to_dict(self) -> dict:
        return {
            "wavelength_nm": self.wavelength_nm.tolist(),
            "value": self.value.tolist(),
            "label": self.label,
            "kind": self.kind,
            "source": self.source,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Spectrum":
        return cls(
            wavelength_nm=np.asarray(d["wavelength_nm"], dtype=float),
            value=np.asarray(d["value"], dtype=float),
            label=d.get("label", ""),
            kind=d.get("kind", ""),
            source=d.get("source", ""),
            meta=d.get("meta", {}),
        )


_trapezoid = getattr(np, "trapezoid", None) or np.trapz  # numpy >=2.0 renamed trapz -> trapezoid


def integrate(grid: np.ndarray, values: np.ndarray) -> float:
    """Trapezoidal integral over the shared grid."""
    return float(_trapezoid(values, grid))

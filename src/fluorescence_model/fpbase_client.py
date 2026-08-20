"""Fetch fluorophore excitation/emission spectra from FPbase (fpbase.org) via
the `fpbase` python package (wraps FPbase's GraphQL API), and cache them
locally as JSON so the app works offline after the first fetch.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from .spectrum import Spectrum

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "fluorophores"


@dataclass
class FluorophoreRecord:
    name: str
    slug: str
    excitation: Spectrum
    emission: Spectrum
    ex_max_nm: Optional[float]
    em_max_nm: Optional[float]
    quantum_yield: Optional[float]
    source: str
    retrieved: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "excitation": self.excitation.to_dict(),
            "emission": self.emission.to_dict(),
            "ex_max_nm": self.ex_max_nm,
            "em_max_nm": self.em_max_nm,
            "quantum_yield": self.quantum_yield,
            "source": self.source,
            "retrieved": self.retrieved,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FluorophoreRecord":
        return cls(
            name=d["name"],
            slug=d["slug"],
            excitation=Spectrum.from_dict(d["excitation"]),
            emission=Spectrum.from_dict(d["emission"]),
            ex_max_nm=d.get("ex_max_nm"),
            em_max_nm=d.get("em_max_nm"),
            quantum_yield=d.get("quantum_yield"),
            source=d.get("source", "fpbase"),
            retrieved=d.get("retrieved", ""),
        )


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def cache_path(name: str) -> Path:
    return DATA_DIR / f"{slugify(name)}.json"


def fetch_fluorophore(name: str, save: bool = True) -> FluorophoreRecord:
    """Look up `name` on FPbase and return its excitation/emission spectra.

    Raises whatever the underlying `fpbase` package raises (e.g. if the name
    isn't found) - let the caller decide how to surface that.
    """
    import fpbase  # imported lazily so the rest of the package works without network deps installed

    fluor = fpbase.get_fluorophore(name)
    state = fluor.default_state
    if state is None or state.excitation_spectrum is None or state.emission_spectrum is None:
        raise ValueError(f"FPbase has no complete excitation/emission spectrum for {name!r}")

    ex_wl, ex_val = zip(*state.excitation_spectrum.data)
    em_wl, em_val = zip(*state.emission_spectrum.data)

    record = FluorophoreRecord(
        name=fluor.name,
        slug=slugify(fluor.name),
        excitation=Spectrum(list(ex_wl), list(ex_val), label=f"{fluor.name} excitation", kind="excitation", source="fpbase"),
        emission=Spectrum(list(em_wl), list(em_val), label=f"{fluor.name} emission", kind="emission", source="fpbase"),
        ex_max_nm=state.exMax,
        em_max_nm=state.emMax,
        quantum_yield=state.qy,
        source="fpbase",
        retrieved=date.today().isoformat(),
    )
    if save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cache_path(name).write_text(json.dumps(record.to_dict(), indent=2))
    return record


def load_cached(name_or_slug: str) -> Optional[FluorophoreRecord]:
    slug = slugify(name_or_slug)
    path = DATA_DIR / f"{slug}.json"
    if not path.exists():
        return None
    return FluorophoreRecord.from_dict(json.loads(path.read_text()))


def list_cached() -> list[FluorophoreRecord]:
    if not DATA_DIR.exists():
        return []
    records = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            records.append(FluorophoreRecord.from_dict(json.loads(path.read_text())))
        except Exception:
            continue
    return records

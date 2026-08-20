"""Fetch spectra from FPbase (fpbase.org) via the `fpbase` python package
(wraps FPbase's GraphQL API):

- Fluorophore excitation/emission spectra, cached locally as JSON so the app
  works offline after the first fetch (see `fetch_fluorophore`).
- Commercial filter spectra from FPbase's own aggregated filter catalog -
  real Chroma/Omega/Thorlabs/etc. parts contributed via public microscope
  configs, no manual downloading needed for anything already in there (see
  `fetch_filter`). Coverage varies a lot by manufacturer (as of 2026-08:
  ~1100 Chroma, ~1300 Omega, ~20 Thorlabs, essentially none from Edmund
  Optics) - this looks up whatever FPbase already has; a part that isn't
  there still needs the manual "Import a filter data file" flow.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from . import catalog
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


# --------------------------------------------------------------- filters --

# FPbase's own spectrum-type code that unambiguously means "this is a
# dichroic/beamsplitter" (see fpbase.models.SpectrumType). Everything else a
# Filter can be (BP/BM/BX/LP/SP - various bandpass/edge shapes) doesn't
# self-declare whether it's used for excitation or emission - that's a
# placement choice made when a filter is put into a specific microscope
# config, not a property of the filter itself - so those require the caller
# to say which.
_DICHROIC_SUBTYPES = {"BS"}

_CATEGORY_LABELS = {"excitation": "Excitation Filter", "emission": "Emission Filter", "dichroic": "Dichroic"}


@dataclass
class FilterFetchResult:
    name: str
    manufacturer: str
    category: str  # "excitation" | "emission" | "dichroic"
    subtype: str
    spectrum: Spectrum
    filename: str
    display_name: str


def _normalize_filter_query(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@lru_cache(maxsize=1)
def _all_filter_names() -> tuple[str, ...]:
    import fpbase

    return tuple(fpbase.list_filters())


def search_filters(query: str, limit: int = 20) -> list[str]:
    """Substring-match `query` against FPbase's filter catalog, ignoring case
    and punctuation - e.g. "ET525/50m" matches the slug "chroma-et525-50m"."""
    nq = _normalize_filter_query(query)
    if not nq:
        return []
    return [n for n in _all_filter_names() if nq in _normalize_filter_query(n)][:limit]


def _resolve_filter_slug(name_or_slug: str) -> str:
    if name_or_slug in _all_filter_names():
        return name_or_slug
    matches = search_filters(name_or_slug, limit=11)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        shown = ", ".join(matches[:10])
        more = ", ..." if len(matches) > 10 else ""
        raise ValueError(f"{name_or_slug!r} matches multiple FPbase filters: {shown}{more}. Be more specific.")
    raise ValueError(f"No FPbase filter found matching {name_or_slug!r}.")


def fetch_filter(name_or_slug: str, category: Optional[str] = None, save: bool = True) -> FilterFetchResult:
    """Look up one filter on FPbase's aggregated filter catalog by (fuzzy)
    name or exact slug, and register it into data/filters/catalog.yaml the
    same way a manually-imported file would be.

    `category` ("excitation"/"emission"/"dichroic") is required UNLESS
    FPbase's own data already marks it as a dichroic/beamsplitter, in which
    case it's inferred automatically.
    """
    import fpbase

    slug = _resolve_filter_slug(name_or_slug)
    f = fpbase.get_filter(slug)
    if f.spectrum is None or not f.spectrum.data:
        raise ValueError(f"FPbase has no spectral data for {slug!r}.")

    subtype = str(f.spectrum.subtype)
    inferred = "dichroic" if subtype in _DICHROIC_SUBTYPES else None
    resolved_category = category or inferred
    if resolved_category is None:
        raise ValueError(
            f"{f.name!r} is a {subtype}-type filter - FPbase doesn't record whether it's used for "
            "excitation or emission (that depends on how it's placed in a microscope, not the filter "
            "itself). Pass category='excitation' or category='emission' explicitly."
        )
    if resolved_category not in _CATEGORY_LABELS:
        raise ValueError(f"category must be one of {sorted(_CATEGORY_LABELS)}, got {resolved_category!r}")

    wl, val = zip(*f.spectrum.data)
    value_label = _CATEGORY_LABELS[resolved_category]
    spectrum = Spectrum(
        wavelength_nm=list(wl),
        value=list(val),
        label=f.name,
        kind="dichroic_T" if resolved_category == "dichroic" else "filter_T",
        source=f"fpbase:{slug}",
    )

    manufacturer = f.manufacturer or "Unknown"
    filename = f"fpbase_{catalog.safe_filename_part(f.name)}.csv"
    display_name = f"{f.name} - {value_label} (via FPbase)"

    if save:
        _write_clean_filter_csv(catalog.FILTER_DIR / filename, spectrum, value_label)
        catalog.register_filter(
            display_name=display_name,
            manufacturer=manufacturer,
            part_number=f.name,
            category=resolved_category,
            filename=filename,
        )

    return FilterFetchResult(
        name=f.name,
        manufacturer=manufacturer,
        category=resolved_category,
        subtype=subtype,
        spectrum=spectrum,
        filename=filename,
        display_name=display_name,
    )


def _write_clean_filter_csv(path: Path, spectrum: Spectrum, value_label: str) -> None:
    lines = [f"Wavelength (nm),{value_label}"]
    lines += [f"{wl:.6g},{val:.6g}" for wl, val in zip(spectrum.wavelength_nm, spectrum.value)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

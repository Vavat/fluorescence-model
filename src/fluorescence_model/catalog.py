"""Builds the pick-lists the UI binds to: every cached fluorophore in
data/fluorophores/, and every registered filter in data/filters/catalog.yaml.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .filter_import import parse_filter_file
from .spectrum import Spectrum

REPO_ROOT = Path(__file__).resolve().parents[2]
FLUOROPHORE_DIR = REPO_ROOT / "data" / "fluorophores"
FILTER_DIR = REPO_ROOT / "data" / "filters"
FILTER_CATALOG_PATH = FILTER_DIR / "catalog.yaml"


@dataclass
class FluorophoreEntry:
    name: str
    slug: str
    excitation: Spectrum
    emission: Spectrum
    source: str
    file_path: Path


@dataclass
class FilterEntry:
    display_name: str
    manufacturer: str
    part_number: str
    category: str  # "excitation" | "emission" | "dichroic"
    filename: str

    def load(self) -> dict[str, Spectrum]:
        parsed = parse_filter_file(FILTER_DIR / self.filename)
        for spec in parsed.series.values():
            spec.source = f"{self.manufacturer} {self.part_number}"
            spec.label = self.display_name
        return parsed.series


# Which parsed series key to prefer for each filter category, in priority
# order. "excitation"/"emission"/"dichroic" are the semantic labels
# filter_import.py assigns when a file's own header text names them (e.g.
# Thorlabs' bundled filter-set downloads); "%T" is the generic fallback label
# used for simple single-curve files.
_SERIES_PRIORITY: dict[str, list[str]] = {
    "excitation": ["excitation", "%T"],
    "emission": ["emission", "%T"],
    "dichroic": ["dichroic", "%T"],
}


def pick_primary_series(series: dict[str, Spectrum], category: str) -> Spectrum:
    """Pick the Spectrum to use for `category` out of a parsed file's series
    dict, preferring a category-matched label and falling back to the
    generic "%T" curve, then whatever's first if neither is present."""
    for key in _SERIES_PRIORITY.get(category, ["%T"]):
        if key in series:
            return series[key]
    return next(iter(series.values()))


def safe_filename_part(text: str) -> str:
    """Sanitize a manufacturer/part-number string for use in a filename.

    Part numbers routinely contain '/' (e.g. Thorlabs/Semrock "FF01-475/35-25"),
    which would otherwise be read as a path separator and land the file in a
    nonexistent subdirectory - replace any filesystem-unsafe character with '-'.
    """
    return re.sub(r'[\\/:*?"<>| ]+', "-", text.strip()).strip("-") or "unknown"


def list_fluorophores() -> list[FluorophoreEntry]:
    if not FLUOROPHORE_DIR.exists():
        return []
    entries = []
    for path in sorted(FLUOROPHORE_DIR.glob("*.json")):
        try:
            d = json.loads(path.read_text())
            entries.append(
                FluorophoreEntry(
                    name=d["name"],
                    slug=d["slug"],
                    excitation=Spectrum.from_dict(d["excitation"]),
                    emission=Spectrum.from_dict(d["emission"]),
                    source=d.get("source", "unknown"),
                    file_path=path,
                )
            )
        except Exception:
            continue  # skip anything that doesn't parse rather than crash the whole catalog
    return sorted(entries, key=lambda e: e.name.lower())


def list_filters(category: Optional[str] = None) -> list[FilterEntry]:
    if not FILTER_CATALOG_PATH.exists():
        return []
    rows = yaml.safe_load(FILTER_CATALOG_PATH.read_text()) or []
    entries = [
        FilterEntry(
            display_name=r["display_name"],
            manufacturer=r.get("manufacturer", ""),
            part_number=r.get("part_number", ""),
            category=r["category"],
            filename=r["filename"],
        )
        for r in rows
    ]
    if category:
        entries = [e for e in entries if e.category == category]
    return sorted(entries, key=lambda e: e.display_name.lower())


def register_filter(
    display_name: str,
    manufacturer: str,
    part_number: str,
    category: str,
    filename: str,
) -> None:
    """Append a new filter to catalog.yaml. Assumes the data file itself has
    already been saved to data/filters/<filename>. Re-registering the same
    filename+category (e.g. re-fetching a part you already have) updates the
    existing row in place rather than adding a duplicate."""
    rows = []
    if FILTER_CATALOG_PATH.exists():
        rows = yaml.safe_load(FILTER_CATALOG_PATH.read_text()) or []
    new_row = {
        "display_name": display_name,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "category": category,
        "filename": filename,
    }
    for i, r in enumerate(rows):
        if r.get("filename") == filename and r.get("category") == category:
            rows[i] = new_row
            break
    else:
        rows.append(new_row)
    FILTER_DIR.mkdir(parents=True, exist_ok=True)
    FILTER_CATALOG_PATH.write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=True))

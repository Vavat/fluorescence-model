"""Import a filter/dichroic spectral data file downloaded from a manufacturer
product page (Thorlabs, Edmund Optics, Semrock, Chroma, ...) into Spectrum
objects.

There's no bulk API for any of these manufacturers - each part's data is a
one-off download (xlsx/csv/txt) from its own product page, and the exact
layout (header text, units, number of columns, junk rows before the table)
varies by manufacturer and even between product lines from the same one. So
rather than writing a brittle parser per manufacturer, this sniffs the table:

1. It looks for a header row containing "Wavelength" text and pairs each such
   column with the value column(s) that follow it, until the next "Wavelength"
   column resets the pairing. This handles both a single wavelength/value pair
   (most single-part downloads) *and* multiple independent wavelength/value
   pairs sharing one file (e.g. Thorlabs' bundled "Fluorescence Filter Set"
   downloads, which pack excitation filter + emission filter + dichroic - each
   with its own wavelength axis and range - into one CSV).
2. If no such header text is found, it falls back to sniffing purely by
   number: the first numeric column whose values fall in a plausible
   wavelength range is treated as a single shared wavelength axis for every
   other numeric column.

Either way, values are auto-detected as a percentage (converted to a 0-1
fraction) vs. an already-unitless fraction by their magnitude.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from .spectrum import Spectrum

# Real filter data is measured/published somewhere in this range; used to
# tell a wavelength column apart from a transmission/reflection column.
_WAVELENGTH_RANGE = (150.0, 2500.0)
_MIN_NUMERIC_ROWS = 10  # a real spectrum table has many rows; guards against picking up a small metadata block
_WAVELENGTH_HEADER_RE = re.compile(r"wavelength", re.IGNORECASE)
_HEADER_SCAN_ROWS = 50  # header text is always near the top; no need to scan huge files


@dataclass
class ParsedFilterFile:
    series: dict[str, Spectrum]  # label -> Spectrum, e.g. {"%T": ...} or {"excitation": ..., "emission": ..., "dichroic": ...}
    warnings: list[str] = field(default_factory=list)


def parse_filter_file(path: Union[str, Path], filename: str | None = None) -> ParsedFilterFile:
    """Parse a manufacturer filter data file. `path` may be a filesystem path
    or a file-like object (e.g. from a Streamlit file_uploader); pass
    `filename` explicitly when using a buffer so the extension can be sniffed.
    """
    name = filename or (path if isinstance(path, str) else getattr(path, "name", str(path)))
    ext = Path(name).suffix.lower()

    if ext in (".xlsx", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None, header=None)
        frames = list(sheets.values())
    elif ext in (".csv", ".txt", ".tsv", ".dat"):
        frames = [_read_delimited(path)]
    else:
        raise ValueError(f"Unsupported filter file type {ext!r} for {name}")

    warnings: list[str] = []
    for frame in frames:
        result = _parse_paired_columns(frame) or _parse_generic_numeric(frame)
        if result:
            return ParsedFilterFile(series=result, warnings=warnings)

    raise ValueError(
        f"Could not find a wavelength + numeric data table in {name}. "
        "Expected at least two numeric columns (wavelength and a %T/%R value) "
        "somewhere in the file."
    )


def _read_delimited(path) -> pd.DataFrame:
    # Try to sniff the delimiter: manufacturer exports show up as
    # comma, tab, or semicolon-separated depending on locale/source.
    raw_bytes: Optional[bytes] = None
    if hasattr(path, "read"):
        raw = path.read()
        raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    else:
        raw_bytes = Path(path).read_bytes()

    text = _decode_bytes(raw_bytes)
    for sep in (",", "\t", ";"):
        # Use csv.reader (not pandas' own parser) so a ragged row - e.g. a
        # stray metadata cell earlier in the row containing the delimiter
        # itself, which shifts everything after it by one column, as seen in
        # real Thorlabs exports - doesn't blow up the whole file. Rows are
        # padded to a common width rather than rejected.
        rows = list(csv.reader(io.StringIO(text), delimiter=sep))
        width = max((len(r) for r in rows), default=0)
        if width < 2:
            continue
        rows = [r + [""] * (width - len(r)) for r in rows]
        return pd.DataFrame(rows)
    raise ValueError("Could not detect a delimiter (tried comma, tab, semicolon)")


def _decode_bytes(raw: bytes) -> str:
    # Manufacturer exports are usually UTF-8, but Windows-originated tools
    # (Thorlabs' own export among them) sometimes emit Windows-1252 - e.g. the
    # (R) registered-trademark glyph in "Cy(R)5.5" is a single 0xAE byte,
    # invalid UTF-8 on its own. Try strict UTF-8 first, fall back to cp1252
    # (which never fails to decode a single byte) rather than losing/mangling
    # characters with errors="replace".
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.strip().str.rstrip("%"),
        errors="coerce",
    )


def _to_fraction(values) -> "pd.Series | list":
    # Auto-detect %-scale (0-100) vs. already-fractional (0-1) data.
    if len(values) and pd.Series(values).max() > 1.5:
        return values / 100.0
    return values


def _find_header_row(df: pd.DataFrame) -> Optional[int]:
    """Row index of the header row containing "Wavelength" text, if any."""
    best_row, best_count = None, 0
    for r in range(min(_HEADER_SCAN_ROWS, len(df))):
        count = sum(1 for cell in df.iloc[r] if _WAVELENGTH_HEADER_RE.search(str(cell)))
        if count > best_count:
            best_row, best_count = r, count
    return best_row


def _parse_paired_columns(df: pd.DataFrame) -> Optional[dict[str, Spectrum]]:
    """Primary strategy: find the header row, pair each 'Wavelength' column
    with the value column(s) following it (a new 'Wavelength' column resets
    the pairing), and extract each pair independently so pairs with different
    lengths/ranges (as in Thorlabs' bundled filter-set downloads) don't
    require rows to line up across the whole table.
    """
    header_row_idx = _find_header_row(df)
    if header_row_idx is None:
        return None

    header = df.iloc[header_row_idx]
    pairs: list[tuple[int, int, str]] = []  # (wavelength_col, value_col, value_header_text)
    current_wl_col: Optional[int] = None
    for c in range(df.shape[1]):
        text = str(header.iloc[c]).strip()
        if text.lower() == "nan":
            text = ""
        if _WAVELENGTH_HEADER_RE.search(text):
            current_wl_col = c
        elif text and current_wl_col is not None:
            pairs.append((current_wl_col, c, text))
    if not pairs:
        return None

    data = df.iloc[header_row_idx + 1 :]
    series: dict[str, Spectrum] = {}
    for wl_col, val_col, label_text in pairs:
        wl = _to_numeric(data.iloc[:, wl_col])
        val = _to_numeric(data.iloc[:, val_col])
        mask = wl.notna() & val.notna()
        if mask.sum() < _MIN_NUMERIC_ROWS:
            continue
        wl_arr = wl[mask].to_numpy()
        if not ((wl_arr >= _WAVELENGTH_RANGE[0]) & (wl_arr <= _WAVELENGTH_RANGE[1])).mean() > 0.9:
            continue  # that "Wavelength"-labeled column doesn't actually hold wavelengths - skip it
        val_arr = _to_fraction(val[mask].to_numpy())
        label = _dedupe_label(_semantic_label(label_text), series)
        series[label] = Spectrum(
            wavelength_nm=wl_arr,
            value=val_arr,
            label=label,
            kind=_kind_for_label(label),
            source="",
            meta={},
        )
    return series or None


def _parse_generic_numeric(df: pd.DataFrame) -> Optional[dict[str, Spectrum]]:
    """Fallback strategy for files with no recognizable 'Wavelength' header
    text at all: sniff purely by number, treating the first plausible
    wavelength-range column as a single shared axis for every other numeric
    column.
    """
    numeric = df.apply(_to_numeric)
    good_cols = [c for c in numeric.columns if numeric[c].notna().sum() >= _MIN_NUMERIC_ROWS]
    if len(good_cols) < 2:
        return None

    valid_rows = numeric[good_cols].notna().all(axis=1)
    if valid_rows.sum() < _MIN_NUMERIC_ROWS:
        return None
    data_start = valid_rows.idxmax()
    header_row = df.iloc[data_start - 1] if data_start > 0 else None

    block = numeric.loc[valid_rows, good_cols].loc[data_start:]

    wl_col = None
    for c in good_cols:
        if block[c].between(*_WAVELENGTH_RANGE).mean() > 0.9:
            wl_col = c
            break
    if wl_col is None:
        return None

    wavelength = block[wl_col].to_numpy()
    series: dict[str, Spectrum] = {}
    value_cols = [c for c in good_cols if c != wl_col]
    for c in value_cols:
        values = _to_fraction(block[c].to_numpy())
        label = _dedupe_label(_legacy_column_label(header_row, c, len(value_cols) > 1, len(series)), series)
        series[label] = Spectrum(
            wavelength_nm=wavelength,
            value=values,
            label=label,
            kind=_kind_for_label(label),
            source="",
            meta={},
        )
    return series or None


def _dedupe_label(label: str, existing: dict) -> str:
    if label not in existing:
        return label
    n = 2
    while f"{label} {n}" in existing:
        n += 1
    return f"{label} {n}"


def _semantic_label(text: str) -> str:
    if re.search(r"excitation", text, re.IGNORECASE):
        return "excitation"
    if re.search(r"emission", text, re.IGNORECASE):
        return "emission"
    if re.search(r"dichroic", text, re.IGNORECASE):
        return "dichroic"
    if re.search(r"\bR\b|reflect", text, re.IGNORECASE):
        return "%R"
    if re.search(r"\bT\b|transmit|%T", text, re.IGNORECASE):
        return "%T"
    return text


def _legacy_column_label(header_row, col_idx: int, multiple_value_cols: bool, ordinal: int) -> str:
    if header_row is not None:
        text = str(header_row.iloc[col_idx]).strip()
        if text and text.lower() != "nan":
            return _semantic_label(text)
    if not multiple_value_cols:
        return "%T"
    return f"Value {ordinal + 1}"


def _kind_for_label(label: str) -> str:
    if label in ("dichroic", "%T", "excitation", "emission"):
        return "dichroic_T" if label == "dichroic" else "filter_T"
    if label == "%R":
        return "dichroic_R"
    return "filter_T"

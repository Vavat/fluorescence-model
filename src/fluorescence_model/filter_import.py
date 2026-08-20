"""Import a filter/dichroic spectral data file downloaded from a manufacturer
product page (Thorlabs, Edmund Optics, Semrock, Chroma, ...) into Spectrum
objects.

There's no bulk API for any of these manufacturers - each part's data is a
one-off download (xlsx/csv/txt) from its own product page, and the exact
layout (header text, units, number of columns, junk rows before the table)
varies by manufacturer and even between product lines from the same one. So
rather than writing a brittle parser per manufacturer, this sniffs the table:
it finds where the numeric data starts, picks out the column that looks like
a wavelength axis, and treats every other numeric column as a data series
(commonly just %Transmission, but dichroics sometimes publish %R and %T side
by side).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import pandas as pd

from .spectrum import Spectrum

# Real filter data is measured/published somewhere in this range; used to
# tell a wavelength column apart from a transmission/reflection column.
_WAVELENGTH_RANGE = (150.0, 2500.0)
_MIN_NUMERIC_ROWS = 10  # a real spectrum table has many rows; guards against picking up a small metadata block


@dataclass
class ParsedFilterFile:
    series: dict[str, Spectrum]  # label -> Spectrum, e.g. {"%T": ..., "%R": ...}
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
        result = _parse_table(frame, warnings)
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
    if hasattr(path, "read"):
        raw = path.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        buf = io.StringIO(raw)
    else:
        buf = path
    for sep in (",", "\t", ";"):
        try:
            if hasattr(buf, "seek"):
                buf.seek(0)
            df = pd.read_csv(buf, sep=sep, header=None, engine="python")
        except Exception:
            continue
        if df.shape[1] >= 2:
            return df
    raise ValueError("Could not detect a delimiter (tried comma, tab, semicolon)")


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.strip().str.rstrip("%"),
        errors="coerce",
    )


def _parse_table(df: pd.DataFrame, warnings: list[str]) -> dict[str, Spectrum] | None:
    numeric = df.apply(_to_numeric)
    # A column counts as numeric data if most of its rows parse as numbers.
    good_cols = [c for c in numeric.columns if numeric[c].notna().sum() >= _MIN_NUMERIC_ROWS]
    if len(good_cols) < 2:
        return None

    # The data-start row is the first row where all "good" columns are numeric together.
    valid_rows = numeric[good_cols].notna().all(axis=1)
    if valid_rows.sum() < _MIN_NUMERIC_ROWS:
        return None
    data_start = valid_rows.idxmax()
    header_row = df.iloc[data_start - 1] if data_start > 0 else None

    block = numeric.loc[valid_rows, good_cols].loc[data_start:]

    wl_col = None
    for c in good_cols:
        vals = block[c]
        if vals.between(*_WAVELENGTH_RANGE).mean() > 0.9:
            wl_col = c
            break
    if wl_col is None:
        return None

    wavelength = block[wl_col].to_numpy()
    series: dict[str, Spectrum] = {}
    value_cols = [c for c in good_cols if c != wl_col]
    for c in value_cols:
        values = block[c].to_numpy()
        label = _column_label(header_row, c, len(value_cols) > 1, len(series))
        if label is None:
            continue
        if values.size and pd.Series(values).max() > 1.5:
            values = values / 100.0  # looked like a percentage, not a 0-1 fraction
        kind = "dichroic_R" if "R" in label.upper() and "T" not in label.upper() else "filter_T"
        series[label] = Spectrum(
            wavelength_nm=wavelength,
            value=values,
            label=label,
            kind=kind,
            source="",
            meta={},
        )
    return series or None


def _column_label(header_row, col_idx: int, multiple_value_cols: bool, ordinal: int) -> str | None:
    if header_row is not None:
        text = str(header_row.iloc[col_idx]).strip()
        if text and text.lower() != "nan":
            if re.search(r"\bR\b|reflect", text, re.IGNORECASE):
                return "%R"
            if re.search(r"\bT\b|transmit|%T", text, re.IGNORECASE):
                return "%T"
            return text
    if not multiple_value_cols:
        return "%T"
    return f"Value {ordinal + 1}"

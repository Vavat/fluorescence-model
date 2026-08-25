"""Exports the currently-plotted curves as a single wavelength-indexed
table, in whichever format the user picks (CSV, Excel, JSON).

The exported values match exactly what's drawn in the plot, not the raw
underlying data: reference curves (fluorophore excitation/emission, source,
filters, dichroic) are peak-normalized to 1.0, same as the plot's dashed/
solid lines, while the four computed "light that actually gets there" curves
are left at their real (unnormalized) relative magnitude, same as the plot's
gradient fills. That way the numbers in the exported table line up with what
you're looking at on screen.
"""

from __future__ import annotations

import io
import json
from typing import Optional

import pandas as pd

from .spectrum import DEFAULT_GRID_NM, Spectrum

EXPORT_FORMATS = ("CSV", "Excel", "JSON")

# label -> (mime type, file extension)
_FORMAT_INFO = {
    "CSV": ("text/csv", "csv"),
    "Excel": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "JSON": ("application/json", "json"),
}


def build_export_table(
    fluorophore_excitation: Spectrum,
    fluorophore_emission: Spectrum,
    source: Spectrum,
    excitation_filter: Optional[Spectrum] = None,
    dichroic: Optional[Spectrum] = None,
    emission_filter: Optional[Spectrum] = None,
    excitation_combined: Optional[Spectrum] = None,
    excitation_absorbed: Optional[Spectrum] = None,
    emission_combined: Optional[Spectrum] = None,
    excitation_leak: Optional[Spectrum] = None,
    grid=DEFAULT_GRID_NM,
) -> pd.DataFrame:
    """One row per grid wavelength, one column per curve that's actually
    present (a `None` filter/dichroic simply isn't included as a column,
    rather than filled with placeholder values)."""
    columns: dict[str, object] = {"Wavelength (nm)": grid}

    def add_normalized(spec: Optional[Spectrum], name: str) -> None:
        if spec is not None:
            columns[name] = spec.normalize().resample(grid)

    def add_raw(spec: Optional[Spectrum], name: str) -> None:
        if spec is not None:
            columns[name] = spec.resample(grid)

    add_normalized(fluorophore_excitation, "Fluorophore excitation")
    add_normalized(fluorophore_emission, "Fluorophore emission")
    add_normalized(source, "Source spectrum")
    add_normalized(excitation_filter, "Excitation filter")
    add_normalized(dichroic, "Dichroic (%T)")
    add_normalized(emission_filter, "Emission filter")
    add_raw(excitation_combined, "Excitation light at specimen")
    add_raw(excitation_absorbed, "Excitation light absorbed by fluorophore")
    add_raw(emission_combined, "Emission light at camera")
    add_raw(excitation_leak, "Excitation leak at camera")

    return pd.DataFrame(columns)


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Spectra")
    return buf.getvalue()


def _to_json_bytes(df: pd.DataFrame) -> bytes:
    # orient="records" - a list of {column: value} rows - is the most
    # broadly-compatible/readable JSON shape for tabular data, easier to
    # consume from other tools than pandas' own column-oriented default.
    return json.dumps(df.to_dict(orient="records"), indent=2).encode("utf-8")


_EXPORTERS = {
    "CSV": _to_csv_bytes,
    "Excel": _to_excel_bytes,
    "JSON": _to_json_bytes,
}


def export_bytes(df: pd.DataFrame, fmt: str) -> tuple[bytes, str, str]:
    """Serialize `df` as `fmt` (one of EXPORT_FORMATS). Returns (data,
    mime_type, file_extension)."""
    if fmt not in _EXPORTERS:
        raise ValueError(f"Unknown export format {fmt!r}, expected one of {EXPORT_FORMATS}")
    data = _EXPORTERS[fmt](df)
    mime, ext = _FORMAT_INFO[fmt]
    return data, mime, ext

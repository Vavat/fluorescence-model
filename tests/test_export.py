import io
import json

import numpy as np
import pandas as pd
import pytest

from fluorescence_model.export import EXPORT_FORMATS, build_export_table, export_bytes
from fluorescence_model.spectrum import DEFAULT_GRID_NM, Spectrum


def _tophat(center, half_width, peak=1.0):
    wl = np.arange(300, 901, 1.0)
    val = np.where(np.abs(wl - center) <= half_width, peak, 0.0)
    return Spectrum(wl, val)


def _base_table(**overrides):
    kwargs = dict(
        fluorophore_excitation=_tophat(480, 10, peak=0.8),
        fluorophore_emission=_tophat(520, 10, peak=0.9),
        source=_tophat(480, 10, peak=0.7),
    )
    kwargs.update(overrides)
    return build_export_table(**kwargs)


def test_wavelength_column_matches_default_grid():
    df = _base_table()
    assert np.allclose(df["Wavelength (nm)"].to_numpy(), DEFAULT_GRID_NM)


def test_required_curves_are_always_present():
    df = _base_table()
    for col in ("Fluorophore excitation", "Fluorophore emission", "Source spectrum"):
        assert col in df.columns


def test_optional_none_curves_are_omitted_not_nan_filled():
    df = _base_table()  # excitation_filter, dichroic, emission_filter, combined curves all left None
    for col in (
        "Excitation filter",
        "Dichroic (%T)",
        "Emission filter",
        "Excitation light at specimen",
        "Excitation light absorbed by fluorophore",
        "Emission light at camera",
        "Excitation leak at camera",
    ):
        assert col not in df.columns


def test_reference_curves_are_peak_normalized_in_export():
    df = _base_table(excitation_filter=_tophat(480, 10, peak=0.5))
    assert df["Fluorophore excitation"].max() == pytest.approx(1.0)
    assert df["Excitation filter"].max() == pytest.approx(1.0)


def test_combined_curves_are_not_normalized_in_export():
    df = _base_table(excitation_combined=_tophat(480, 10, peak=0.35))
    assert df["Excitation light at specimen"].max() == pytest.approx(0.35, abs=1e-6)


def test_all_ten_columns_present_when_everything_supplied():
    df = _base_table(
        excitation_filter=_tophat(480, 8, peak=0.9),
        dichroic=_tophat(500, 100, peak=0.95),
        emission_filter=_tophat(520, 8, peak=0.85),
        excitation_combined=_tophat(480, 8, peak=0.3),
        excitation_absorbed=_tophat(480, 8, peak=0.2),
        emission_combined=_tophat(520, 8, peak=0.4),
        excitation_leak=_tophat(480, 8, peak=0.05),
    )
    assert len(df.columns) == 11  # wavelength + 10 curves


@pytest.mark.parametrize("fmt", EXPORT_FORMATS)
def test_export_bytes_produces_nonempty_data_for_every_format(fmt):
    df = _base_table()
    data, mime, ext = export_bytes(df, fmt)
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert mime
    assert ext


def test_csv_round_trips_correctly():
    df = _base_table(excitation_filter=_tophat(480, 8, peak=0.9))
    data, _, ext = export_bytes(df, "CSV")
    assert ext == "csv"
    back = pd.read_csv(io.BytesIO(data))
    assert list(back.columns) == list(df.columns)
    assert np.allclose(back["Fluorophore excitation"].to_numpy(), df["Fluorophore excitation"].to_numpy())


def test_excel_round_trips_correctly():
    df = _base_table(dichroic=_tophat(500, 100, peak=0.95))
    data, _, ext = export_bytes(df, "Excel")
    assert ext == "xlsx"
    back = pd.read_excel(io.BytesIO(data))
    assert list(back.columns) == list(df.columns)
    assert np.allclose(back["Dichroic (%T)"].to_numpy(), df["Dichroic (%T)"].to_numpy())


def test_json_round_trips_correctly():
    df = _base_table(excitation_combined=_tophat(480, 8, peak=0.3))
    data, _, ext = export_bytes(df, "JSON")
    assert ext == "json"
    records = json.loads(data)
    assert isinstance(records, list)
    assert len(records) == len(df)
    assert set(records[0].keys()) == set(df.columns)
    # spot check one row's value against the source DataFrame
    row = df.iloc[100]
    assert records[100]["Excitation light at specimen"] == pytest.approx(row["Excitation light at specimen"])


def test_invalid_format_raises():
    df = _base_table()
    with pytest.raises(ValueError):
        export_bytes(df, "not-a-real-format")

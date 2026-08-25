import numpy as np
import pytest

from fluorescence_model import catalog
from fluorescence_model.spectrum import Spectrum


def _spec(label):
    return Spectrum(np.array([1.0, 2.0]), np.array([0.1, 0.2]), label=label)


def test_pick_primary_series_prefers_category_label():
    series = {"excitation": _spec("excitation"), "%T": _spec("%T")}
    assert catalog.pick_primary_series(series, "excitation").label == "excitation"


def test_pick_primary_series_falls_back_to_generic_T():
    series = {"%T": _spec("%T")}
    assert catalog.pick_primary_series(series, "emission").label == "%T"


def test_pick_primary_series_falls_back_to_first_when_nothing_matches():
    series = {"Value 1": _spec("Value 1")}
    assert catalog.pick_primary_series(series, "dichroic").label == "Value 1"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("FF01-475/35-25", "FF01-475-35-25"),  # real Thorlabs/Semrock-style part number with a slash
        ("Thorlabs", "Thorlabs"),
        ("  Edmund Optics  ", "Edmund-Optics"),
        ("", "unknown"),
        ('weird:name*chars?', "weird-name-chars"),
    ],
)
def test_safe_filename_part(raw, expected):
    assert catalog.safe_filename_part(raw) == expected


def test_register_and_list_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "FILTER_DIR", tmp_path)
    monkeypatch.setattr(catalog, "FILTER_CATALOG_PATH", tmp_path / "catalog.yaml")

    catalog.register_filter("Test Filter", "Thorlabs", "FF01-475/35-25", "excitation", "thorlabs_FF01-475-35-25_excitation.xlsx")
    entries = catalog.list_filters()
    assert len(entries) == 1
    assert entries[0].display_name == "Test Filter"
    assert entries[0].category == "excitation"

    ex_only = catalog.list_filters("excitation")
    assert len(ex_only) == 1
    assert catalog.list_filters("dichroic") == []


def test_register_filter_updates_in_place_on_same_filename_and_category(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "FILTER_DIR", tmp_path)
    monkeypatch.setattr(catalog, "FILTER_CATALOG_PATH", tmp_path / "catalog.yaml")

    catalog.register_filter("First name", "Thorlabs", "PART-1", "excitation", "shared.csv")
    catalog.register_filter("Second name (re-fetched)", "Thorlabs", "PART-1", "excitation", "shared.csv")

    entries = catalog.list_filters()
    assert len(entries) == 1  # updated in place, not duplicated
    assert entries[0].display_name == "Second name (re-fetched)"

    # same filename but a *different* category is a separate row (e.g. one
    # file backing both an excitation and an emission catalog entry)
    catalog.register_filter("Emission side", "Thorlabs", "PART-1", "emission", "shared.csv")
    assert len(catalog.list_filters()) == 2

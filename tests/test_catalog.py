import pytest

from fluorescence_model import catalog


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

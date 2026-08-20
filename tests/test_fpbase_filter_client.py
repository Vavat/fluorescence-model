import pytest

from fluorescence_model import catalog, fpbase_client


@pytest.fixture(autouse=True)
def isolated_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "FILTER_DIR", tmp_path)
    monkeypatch.setattr(catalog, "FILTER_CATALOG_PATH", tmp_path / "catalog.yaml")
    yield


@pytest.fixture(autouse=True)
def fake_filter_names(monkeypatch):
    names = (
        "chroma-et525-50m",
        "chroma-et470-40x",
        "chroma---419735",
        "omega-1000aelp",
    )
    monkeypatch.setattr(fpbase_client, "_all_filter_names", lambda: names)
    yield


def _fake_fpbase_module(subtype: str, data=None, manufacturer="Chroma", name="Chroma ET525/50m"):
    """Build a real fpbase.models.Filter (no network) and monkeypatch
    fpbase.get_filter to return it, so fetch_filter's own logic - resolving
    the slug, inferring category, writing the file, registering it - is
    exercised for real without hitting the network."""
    from fpbase.models import Filter, Spectrum as FPSpectrum

    data = data or [(400.0, 0.001), (500.0, 0.02), (525.0, 0.95), (550.0, 0.9), (600.0, 0.001)]
    spec = FPSpectrum(id=1, subtype=subtype, data=data)
    return Filter(id=1, name=name, manufacturer=manufacturer, spectrum=spec)


def test_search_filters_matches_ignoring_case_and_punctuation():
    assert "chroma-et525-50m" in fpbase_client.search_filters("ET525/50m")
    assert "chroma-et525-50m" in fpbase_client.search_filters("Chroma ET525-50M")


def test_resolve_exact_slug_passthrough():
    assert fpbase_client._resolve_filter_slug("chroma-et525-50m") == "chroma-et525-50m"


def test_resolve_ambiguous_query_raises():
    with pytest.raises(ValueError, match="multiple"):
        fpbase_client._resolve_filter_slug("chroma")


def test_resolve_no_match_raises():
    with pytest.raises(ValueError, match="No FPbase filter"):
        fpbase_client._resolve_filter_slug("totally-not-a-real-filter-xyz")


def test_fetch_filter_infers_dichroic_from_BS_subtype(monkeypatch):
    import fpbase

    fake = _fake_fpbase_module(subtype="BS", name="Chroma T500lpxr", manufacturer="Chroma")
    monkeypatch.setattr(fpbase, "get_filter", lambda slug: fake)

    result = fpbase_client.fetch_filter("chroma-et525-50m")  # category omitted - must auto-infer
    assert result.category == "dichroic"
    assert result.subtype == "BS"
    assert "Dichroic" in result.display_name

    entries = catalog.list_filters()
    assert len(entries) == 1
    assert entries[0].category == "dichroic"
    assert (catalog.FILTER_DIR / result.filename).exists()


def test_fetch_filter_bandpass_requires_explicit_category(monkeypatch):
    import fpbase

    fake = _fake_fpbase_module(subtype="BP")
    monkeypatch.setattr(fpbase, "get_filter", lambda slug: fake)

    with pytest.raises(ValueError, match="excitation.*or.*emission|category"):
        fpbase_client.fetch_filter("chroma-et525-50m")  # no category given, BP is ambiguous


def test_fetch_filter_bandpass_with_explicit_category(monkeypatch):
    import fpbase

    fake = _fake_fpbase_module(subtype="BP", name="Chroma ET525/50m")
    monkeypatch.setattr(fpbase, "get_filter", lambda slug: fake)

    result = fpbase_client.fetch_filter("chroma-et525-50m", category="emission")
    assert result.category == "emission"

    written = (catalog.FILTER_DIR / result.filename).read_text()
    assert "Emission Filter" in written.splitlines()[0]
    # values already 0-1 fractions - the clean CSV shouldn't rescale them
    assert "0.95" in written


def test_fetch_filter_rejects_invalid_category(monkeypatch):
    import fpbase

    fake = _fake_fpbase_module(subtype="BP")
    monkeypatch.setattr(fpbase, "get_filter", lambda slug: fake)

    with pytest.raises(ValueError):
        fpbase_client.fetch_filter("chroma-et525-50m", category="not-a-real-category")


def test_refetching_same_filter_updates_catalog_row_in_place(monkeypatch):
    import fpbase

    fake = _fake_fpbase_module(subtype="BS")
    monkeypatch.setattr(fpbase, "get_filter", lambda slug: fake)

    fpbase_client.fetch_filter("chroma-et525-50m")
    fpbase_client.fetch_filter("chroma-et525-50m")
    assert len(catalog.list_filters()) == 1

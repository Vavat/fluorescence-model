from fluorescence_model import channel_presets


def test_load_presets_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_presets, "PRESETS_PATH", tmp_path / "channel_presets.json")
    assert channel_presets.load_presets() == {}
    assert channel_presets.get_preset("Ch1") is None


def test_save_and_get_preset_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_presets, "PRESETS_PATH", tmp_path / "channel_presets.json")

    preset = channel_presets.ChannelPreset(
        fluorophore_name="EGFP",
        excitation_filter="Chroma ET470/40x",
        dichroic="Chroma T495lpxr",
        emission_filter="Chroma ET525/50m",
        source_type="LED",
        led_center_nm=470.0,
        led_fwhm_nm=20.0,
    )
    channel_presets.save_preset("Ch1", preset)

    loaded = channel_presets.get_preset("Ch1")
    assert loaded == preset
    assert channel_presets.get_preset("Ch2") is None


def test_save_preset_does_not_clobber_other_channels(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_presets, "PRESETS_PATH", tmp_path / "channel_presets.json")

    channel_presets.save_preset("Ch1", channel_presets.ChannelPreset(fluorophore_name="EGFP"))
    channel_presets.save_preset("Ch2", channel_presets.ChannelPreset(fluorophore_name="mScarlet"))

    presets = channel_presets.load_presets()
    assert set(presets) == {"Ch1", "Ch2"}
    assert presets["Ch1"].fluorophore_name == "EGFP"
    assert presets["Ch2"].fluorophore_name == "mScarlet"


def test_save_preset_overwrites_same_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_presets, "PRESETS_PATH", tmp_path / "channel_presets.json")

    channel_presets.save_preset("Ch1", channel_presets.ChannelPreset(fluorophore_name="EGFP"))
    channel_presets.save_preset("Ch1", channel_presets.ChannelPreset(fluorophore_name="mCherry"))

    presets = channel_presets.load_presets()
    assert len(presets) == 1
    assert presets["Ch1"].fluorophore_name == "mCherry"


def test_load_presets_ignores_unrecognised_fields(tmp_path, monkeypatch):
    path = tmp_path / "channel_presets.json"
    monkeypatch.setattr(channel_presets, "PRESETS_PATH", path)
    path.write_text('{"Ch1": {"fluorophore_name": "EGFP"}, "Ch2": {"bogus_field": 1}}')

    presets = channel_presets.load_presets()
    assert set(presets) == {"Ch1"}
    assert presets["Ch1"].fluorophore_name == "EGFP"

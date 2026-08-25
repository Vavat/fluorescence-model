"""Named presets (Ch1/Ch2/Ch3) bundling a fluorophore, excitation/dichroic/
emission filter picks, and an excitation source - lets a 3-channel scope's
sidebar be swapped between channels with one click, and remembered with a
"Save" button next to each. Persisted to a small JSON file so presets survive
a restart, the same way data/filters/catalog.yaml persists filter picks.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESETS_PATH = REPO_ROOT / "data" / "channel_presets.json"

CHANNEL_NAMES = ["Ch1", "Ch2", "Ch3"]


@dataclass
class ChannelPreset:
    fluorophore_name: Optional[str] = None
    excitation_filter: str = "None"
    dichroic: str = "None"
    emission_filter: str = "None"
    source_type: str = "LED"
    led_center_nm: float = 465.0
    led_fwhm_nm: float = 25.0
    laser_center_nm: float = 488.0
    laser_linewidth_nm: float = 1.0


def load_presets() -> dict[str, ChannelPreset]:
    if not PRESETS_PATH.exists():
        return {}
    try:
        raw = json.loads(PRESETS_PATH.read_text())
    except Exception:
        return {}
    presets = {}
    for name, fields in raw.items():
        try:
            presets[name] = ChannelPreset(**fields)
        except TypeError:
            continue  # ignore rows with unrecognised fields rather than crash the whole file
    return presets


def get_preset(name: str) -> Optional[ChannelPreset]:
    return load_presets().get(name)


def save_preset(name: str, preset: ChannelPreset) -> None:
    presets = load_presets()
    presets[name] = preset
    PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_PATH.write_text(json.dumps({n: asdict(p) for n, p in presets.items()}, indent=2))

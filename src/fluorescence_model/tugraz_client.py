"""On-demand, single-fluorophore fetch from fluorophores.tugraz.at.

IMPORTANT scope limit: this client only ever looks up ONE fluorophore at a
time, on explicit user request. fluorophores.tugraz.at's own disclaimer says
their intent is "to prevent third parties from taking advantage of the data
by downloading the entire database" - so this module must never iterate the
listing to bulk-fetch spectra. It fetches the public listing page once (a
normal, single page load - the same content a browser search shows, and the
only way to resolve a name to a substance id, since the listing has no
server-side search endpoint) and, for the one substance you asked for, its
one spectrum CSV.

As of this writing (2026-08-20), fluorophores.tugraz.at's substance detail
pages (`/substance/<id>`) return HTTP 500 site-wide - a bug on their end, not
something this client can work around. `fetch_fluorophore` raises a clear
TugrazUnavailable error in that case; pass `spectrum_csv_id` explicitly (if
you've obtained it some other way) to skip straight to the CSV download.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from .fpbase_client import DATA_DIR, slugify
from .spectrum import Spectrum

BASE_URL = "https://fluorophores.tugraz.at"
LISTING_URL = f"{BASE_URL}/substance/"
LISTING_CACHE = Path(__file__).resolve().parents[2] / "data" / "tugraz_listing_cache.json"
_TIMEOUT = 20


class TugrazUnavailable(RuntimeError):
    """Raised when fluorophores.tugraz.at can't currently serve what we need."""


@dataclass
class TugrazRecord:
    name: str
    slug: str
    substance_id: int
    excitation: Spectrum
    emission: Spectrum
    source_url: str
    retrieved: str
    credit: str = "Data courtesy of fluorophores.tugraz.at (fluorophores.org)"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "substance_id": self.substance_id,
            "excitation": self.excitation.to_dict(),
            "emission": self.emission.to_dict(),
            "source_url": self.source_url,
            "retrieved": self.retrieved,
            "credit": self.credit,
            "source": "fluorophores.tugraz.at",
        }


def _first_float(text: str) -> Optional[float]:
    # Some entries list multiple peaks (e.g. "509, 284" for multi-state
    # dyes/Qdots) - the summary metadata only needs the primary one.
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _fetch_listing(force_refresh: bool = False) -> list[dict]:
    """Fetch (and cache) the single public listing page mapping substance
    name -> id. One request regardless of how many lookups you do afterward.
    """
    if not force_refresh and LISTING_CACHE.exists():
        return json.loads(LISTING_CACHE.read_text())

    resp = requests.get(LISTING_URL, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise TugrazUnavailable(f"Listing page returned HTTP {resp.status_code}")

    rows = re.findall(
        r'<a href="(/substance/\d+)">\s*([^<]+?)\s*</a>.*?'
        r'<td class="excitationMax">\s*([^<]*)\s*</td>\s*'
        r'<td class="emissionMax">\s*([^<]*)\s*</td>',
        resp.text,
        re.DOTALL,
    )
    entries = []
    for href, name, ex_max, em_max in rows:
        entries.append(
            {
                "substance_id": int(href.rsplit("/", 1)[-1]),
                "name": name.strip(),
                "ex_max_nm": _first_float(ex_max),
                "em_max_nm": _first_float(em_max),
            }
        )
    if not entries:
        raise TugrazUnavailable("Could not parse any entries from the listing page - its HTML layout may have changed.")

    LISTING_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LISTING_CACHE.write_text(json.dumps(entries, indent=2))
    return entries


def find_substance(name: str) -> dict:
    """Resolve a fluorophore name to its tugraz substance id + summary
    metadata via a case-insensitive exact, then substring, match against the
    (cached) listing.
    """
    entries = _fetch_listing()
    lname = name.strip().lower()
    for e in entries:
        if e["name"].lower() == lname:
            return e
    candidates = [e for e in entries if lname in e["name"].lower()]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(c["name"] for c in candidates[:10])
        raise ValueError(f"{name!r} matches multiple tugraz entries: {names}. Be more specific.")
    raise ValueError(f"No fluorophores.tugraz.at entry found matching {name!r}.")


def _find_spectrum_csv_id(substance_id: int) -> int:
    url = f"{BASE_URL}/substance/{substance_id}"
    resp = requests.get(url, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise TugrazUnavailable(
            f"fluorophores.tugraz.at substance page {url} returned HTTP {resp.status_code} "
            "(their detail pages have been returning 500 site-wide as of 2026-08-20 - this is a "
            "bug on their end, not a local issue). Retry later, or pass spectrum_csv_id explicitly "
            "if you already know it."
        )
    match = re.search(r"/fluorescence/(\d+)\.csv", resp.text)
    if not match:
        raise TugrazUnavailable(f"No spectrum CSV link found on {url}.")
    return int(match.group(1))


def _parse_csv(text: str) -> tuple[Spectrum, Spectrum]:
    lines = [l for l in text.splitlines() if l.strip()]
    header = lines[0].split(";")
    ex_wl, ex_val, em_wl, em_val = [], [], [], []
    for line in lines[1:]:
        parts = line.split(";")
        if len(parts) < 4:
            continue
        a_wl, a_val, e_wl, e_val = parts[:4]
        if a_wl.strip():
            ex_wl.append(float(a_wl))
            ex_val.append(float(a_val))
        if e_wl.strip():
            em_wl.append(float(e_wl))
            em_val.append(float(e_val))
    if not ex_wl or not em_wl:
        raise ValueError(f"Could not parse both absorption and emission columns from CSV (header: {header})")
    excitation = Spectrum(ex_wl, ex_val, kind="excitation")
    emission = Spectrum(em_wl, em_val, kind="emission")
    return excitation, emission


def fetch_fluorophore(name: str, spectrum_csv_id: Optional[int] = None, save: bool = True) -> TugrazRecord:
    """Fetch ONE named fluorophore's spectrum from fluorophores.tugraz.at.

    If `spectrum_csv_id` isn't given, this resolves the name via the listing
    page then the substance detail page - the latter is currently broken on
    tugraz's end (HTTP 500), so pass `spectrum_csv_id` directly if you've
    found it some other way (e.g. once their site is fixed, or from TU Graz
    directly) to skip that step.
    """
    entry = find_substance(name)
    substance_id = entry["substance_id"]
    csv_id = spectrum_csv_id or _find_spectrum_csv_id(substance_id)

    csv_url = f"{BASE_URL}/fluorescence/{csv_id}.csv"
    resp = requests.get(csv_url, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise TugrazUnavailable(f"{csv_url} returned HTTP {resp.status_code}")

    excitation, emission = _parse_csv(resp.text)
    slug = slugify(entry["name"])
    excitation.label = f"{entry['name']} excitation"
    excitation.source = "fluorophores.tugraz.at"
    emission.label = f"{entry['name']} emission"
    emission.source = "fluorophores.tugraz.at"

    record = TugrazRecord(
        name=entry["name"],
        slug=slug,
        substance_id=substance_id,
        excitation=excitation,
        emission=emission,
        source_url=csv_url,
        retrieved=date.today().isoformat(),
    )
    if save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / f"{slug}.json").write_text(json.dumps(record.to_dict(), indent=2))
    return record

# Fluorescence Filter & Source Modeler

A local tool for picking excitation filters, dichroics, emission filters, and LED/laser sources for
a given fluorophore, by modeling spectral overlap through the optical path.

## What it does

- Pulls fluorophore excitation/emission spectra from [FPbase](https://www.fpbase.org) (fluorescent
  proteins + common dyes) and, on request, from
  [fluorophores.tugraz.at](https://fluorophores.tugraz.at) (organic dyes) - one dye at a time, never
  a bulk crawl (see [Data sources](#data-sources) below).
- Imports filter/dichroic transmission curves from data files you download from manufacturer product
  pages (Thorlabs, Edmund Optics, Semrock, Chroma, ...) - see [`data/filters/README.md`](data/filters/README.md).
- Models an LED or laser source from just a center wavelength and FWHM/linewidth.
- Plots everything overlaid and normalized, and computes relative excitation/emission efficiency
  scores plus bleed-through warnings for the combination you've picked.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
pip install -e .
streamlit run app.py
```

Streamlit opens the app in your browser. A handful of common fluorophores (EGFP, mCherry, DAPI,
Alexa Fluor 488/568/647, Cy3, Cy5) are bundled in `data/fluorophores/` so it's useful immediately;
add more from the sidebar. Filters start empty - add the ones you're actually considering via the
sidebar's "Import a filter data file" tool.

## Data sources

- **FPbase** (`src/fluorescence_model/fpbase_client.py`): uses the [`fpbase`](https://pypi.org/project/fpbase/)
  Python client (GraphQL under the hood). Fetches and caches locally as JSON.
- **fluorophores.tugraz.at** (`src/fluorescence_model/tugraz_client.py`): their own disclaimer asks
  that people not bulk-download the whole database, so this client only ever fetches one named
  fluorophore at a time, on explicit request from the UI - it never crawls their listing for bulk
  import. Their substance detail pages have been returning HTTP 500 site-wide since at least
  2026-08-20 (a bug on their end); the fetcher surfaces that clearly and lets you supply a spectrum
  CSV id manually as a fallback if you have one.
- **Filters/dichroics**: no manufacturer offers a bulk API, so these are downloaded one product page
  at a time by you and imported via the app - see `data/filters/README.md`.
- **Camera Bayer-mask QE curves**: not yet modeled - there's no standard bulk source for these either;
  a later addition once real sensor datasheet curves are available to plug in.

## Project layout

```
app.py                          Streamlit UI
src/fluorescence_model/
  spectrum.py                   Spectrum type + resampling/integration helpers
  fpbase_client.py               FPbase fetch + cache
  tugraz_client.py               fluorophores.tugraz.at single-lookup fetch + cache
  filter_import.py               manufacturer file sniffing/parsing
  sources.py                     LED/laser spectral models
  optics.py                      overlap-integral efficiency/bleed-through math
  catalog.py                     pick-list assembly for the UI
  plotting.py                    Plotly figure builder
data/fluorophores/               cached fluorophore spectra (JSON)
data/filters/                    filter data files + catalog.yaml
tests/                           pytest suite (parsers, optics math, source models)
```

## Testing

```bash
pytest
```

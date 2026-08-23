# Fluorescence Filter & Source Modeler

A local tool for picking excitation filters, dichroics, emission filters, and LED/laser sources for
a given fluorophore, by modeling spectral overlap through the optical path.

## What it does

- Pulls fluorophore excitation/emission spectra from [FPbase](https://www.fpbase.org) (fluorescent
  proteins + common dyes) and, on request, from
  [fluorophores.tugraz.at](https://fluorophores.tugraz.at) (organic dyes) - one dye at a time, never
  a bulk crawl (see [Data sources](#data-sources) below).
- Pulls filter/dichroic transmission curves from FPbase's aggregated filter catalog (real Chroma/
  Omega/Thorlabs parts, no download needed) where available, and otherwise imports them from data
  files you download from a manufacturer's product page - see
  [`data/filters/README.md`](data/filters/README.md).
- Models an LED or laser source from just a center wavelength and FWHM/linewidth.
- Plots everything overlaid, and computes relative excitation/emission efficiency scores plus
  bleed-through warnings for the combination you've picked.

## Deployment

This is a local Streamlit app - "deploying" it means running it on your own machine (or any machine
you can `pip install` on); there's no server component to stand up separately.

**Prerequisites**: Python 3.10+.

```powershell
git clone <this repo's URL>
cd fluorescence-model

python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# .venv\Scripts\activate.bat      # Windows cmd.exe, instead
# source .venv/bin/activate       # macOS/Linux, instead

pip install -r requirements.txt
pip install -e .                  # installs this repo's own package (src/fluorescence_model) in editable mode

pytest                            # optional - confirms the install works (should be all green)

streamlit run app.py
```

Streamlit prints a local URL (typically `http://localhost:8501`) and opens it in your browser
automatically. Leave the terminal running - closing it stops the app. To stop it yourself, press
`Ctrl+C` in that terminal.

**If you edit the code**: Streamlit auto-reloads on save, but only for `app.py` itself - editing any
other file (`plotting.py`, `optics.py`, etc.) requires a full restart (`Ctrl+C`, then `streamlit run
app.py` again) to take effect, since Python keeps already-imported modules cached in memory for the
life of the process.

A handful of common fluorophores (EGFP, mCherry, DAPI, Alexa Fluor 488/568/647, Cy3, Cy5) are bundled
in `data/fluorophores/` so the app is useful immediately; add more from the sidebar. Filters start
empty - add the ones you're actually considering via the sidebar's filter tools (see below).

## Using the app

### Sidebar

- **Fluorophore**: pick from what's already downloaded. **Add a fluorophore** fetches a new one -
  either by name from FPbase, or (one dye at a time, on request) from fluorophores.tugraz.at.
- **Filters** - three dropdowns (Excitation filter, Dichroic, Emission filter), each defaulting to
  "None" (pass-through). Populate them via:
  - **Import a filter data file**: upload a raw data file you've downloaded from a manufacturer's
    product page (xlsx/csv/txt) - the importer auto-detects the table inside it. See
    [`data/filters/README.md`](data/filters/README.md) for where to find these on Thorlabs/Edmund/
    Semrock/Chroma sites.
  - **Fetch a filter from FPbase**: look up a real commercial filter by (fuzzy) name/part number, no
    file needed, for whatever FPbase's aggregated catalog happens to have.
- **Excitation source**: choose **LED** or **Laser**, then set its center wavelength and
  FWHM/linewidth. For an LED, also choose the spectral shape model - "Gaussian in wavenumber"
  (recommended, matches the asymmetric shape real LEDs actually have) or a simpler two-sided
  exponential decay.
- **Curve visibility**: a multiselect of every curve the plot can draw - uncheck one to persistently
  hide it. This is the reliable way to hide a curve; clicking its entry directly in the plot's legend
  only hides it until the next change (Streamlit doesn't preserve that click across a rerun).

### Main panel

- **Linear/Log radio** (unlabeled, top left above the plot): switches the y-axis scale. Log reveals
  how deep a filter's out-of-band blocking actually goes (real filters commonly block down to 1e-4 to
  1e-6, invisible on a linear axis).
- **Show** (unlabeled, top right above the plot): a four-way switch limiting which curves are
  plotted, without changing your Curve visibility choices:
  - **Excitation only** / **Emission only** - just that side of the optical path (the dichroic stays
    shown in both, since it's relevant to each).
  - **All** - everything (default).
  - **Excitation leak** - just the curves behind the excitation-bleed warning (see below): the
    source, excitation filter, dichroic, emission filter, and the fluorophore's own emission (for
    context), plus the leak spectrum itself - so you can see at a glance how much stray excitation
    light would land in the same wavelengths as genuine emission.
- **The plot**: dashed lines are the illumination side (source, excitation filter, fluorophore
  excitation), solid lines are the detection side (fluorophore emission, emission filter). Each line
  is colored by its own characteristic wavelength - peak for most curves, the 50%-transmission
  crossing for the dichroic (a broad near-100% plateau, not a single peak, so peak_nm() wouldn't land
  on its physically meaningful cut-on/off edge). The filled curves show light that actually reaches
  the specimen/camera, as a true-color gradient across wavelength, deliberately not normalized so
  their height reflects real throughput loss: *Excitation light at specimen* (faint) and *Excitation
  light absorbed by fluorophore* (solid, drawn on top), *Emission light at camera*, and *Excitation
  leak at camera* (dashed, since it's excitation-origin light even though it ends up at the camera -
  overlay it against "Emission light at camera" to see whether a leak would land in the same
  wavelengths as your real signal).
- **Export**: pick a format (CSV, Excel, or JSON) and download the currently-plotted curves as one
  wavelength-indexed table - values match what's on screen (reference curves peak-normalized, the
  "light that actually gets there" curves at real relative magnitude).
- **Warnings**: appear automatically when excitation light is likely to bleed through to the
  detector (i.e. falls inside both the excitation and emission filter passbands), or when
  excitation/emission efficiency is close to zero for the chosen combination.

## Data sources

- **FPbase** (`src/fluorescence_model/fpbase_client.py`): uses the [`fpbase`](https://pypi.org/project/fpbase/)
  Python client (GraphQL under the hood). Fetches and caches locally as JSON.
- **fluorophores.tugraz.at** (`src/fluorescence_model/tugraz_client.py`): their own disclaimer asks
  that people not bulk-download the whole database, so this client only ever fetches one named
  fluorophore at a time, on explicit request from the UI - it never crawls their listing for bulk
  import. Their substance detail pages have been returning HTTP 500 site-wide since at least
  2026-08-20 (a bug on their end); the fetcher surfaces that clearly and lets you supply a spectrum
  CSV id manually as a fallback if you have one.
- **Filters/dichroics**: no manufacturer offers a bulk API, but FPbase also aggregates real
  commercial filter spectra (contributed via public microscope configs) - `fpbase_client.fetch_filter()`
  looks one up by (fuzzy) name and registers it directly, no file needed, for whatever FPbase happens
  to have (coverage is manufacturer-dependent: strong for Chroma/Omega, weak for Thorlabs, essentially
  none for Edmund Optics). Anything FPbase doesn't have is downloaded one product page at a time by
  you and imported via the app - see `data/filters/README.md`.
- **Camera Bayer-mask QE curves**: not yet modeled - there's no standard bulk source for these either;
  a later addition once real sensor datasheet curves are available to plug in.

## Project layout

```
app.py                          Streamlit UI
src/fluorescence_model/
  spectrum.py                   Spectrum type + resampling/integration/peak/crossing helpers
  fpbase_client.py               FPbase fetch + cache (fluorophores and filters)
  tugraz_client.py               fluorophores.tugraz.at single-lookup fetch + cache
  filter_import.py               manufacturer file sniffing/parsing
  sources.py                     LED/laser spectral models
  optics.py                      overlap-integral efficiency/bleed-through/leak math
  catalog.py                     pick-list assembly for the UI
  plotting.py                    Plotly figure builder (coloring scheme, gradients, show/hide)
  wavelength_color.py             wavelength -> perceived RGB color approximation
  export.py                       CSV/Excel/JSON export of the currently-plotted curves
data/fluorophores/               cached fluorophore spectra (JSON)
data/filters/                    filter data files + catalog.yaml
tests/                           pytest suite (parsers, optics math, source models, plotting, color)
```

## Testing

```bash
pytest
```

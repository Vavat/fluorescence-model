# Adding filter/dichroic data

## Option 1: check FPbase first

Before downloading anything, try the **"Fetch a filter from FPbase"** expander in the app's sidebar.
FPbase aggregates real commercial filter spectra contributed via public microscope configs - as of
2026-08 that's ~1100 Chroma parts, ~1300 Omega parts, and a couple dozen Thorlabs parts, all with
clean spectral data and no file download needed. Coverage is very manufacturer-dependent (Edmund
Optics has essentially none there), so this is a lookup against whatever FPbase happens to have, not
a guarantee - if it's not there, fall back to Option 2.

Search is fuzzy (ignores case/punctuation, so "ET525/50m" finds "Chroma ET525/50m"). A filter's
excitation/emission/dichroic role usually has to be picked manually in the Category dropdown - FPbase
only auto-detects dichroics, and only when a part is tagged as a beamsplitter (subtype "BS"); many
real dichroics are tagged "LP" (longpass) instead and still need the category set by hand.

## Option 2: manual download

There's no bulk API for filter manufacturers (Thorlabs, Edmund Optics, Semrock, Chroma, ...) -
each part's spectral data is a one-off download from its own product page. Some manufacturers don't
publish raw data at all (Edmund Optics, as of 2026-08, per their own confirmation) - in that case,
check FPbase (above), or ask the manufacturer directly. Add filters here as you need them, for parts
you actually own or are considering.

Other places worth checking, roughly in order of fit for fluorescence work specifically: Chroma's
[Spectra Viewer](https://www.chroma.com/spectra-viewer) (CSV/ASCII/XLSX export per their own release
notes), Semrock's [SearchLight](https://searchlight.idex-hs.com/) (txt/CSV export), and Omega's
[Curvomatic](https://www.omegafilters.com/curvomatic) (ASCII export) - none of these were verified by
actually driving the live tool (they're JS-rendered), so double check when you're there.

## Step by step

1. **Find the part's product page** on the manufacturer's site (e.g.
   `thorlabs.com/thorproduct.cfm?partnumber=FF01-475/35-25`, or the equivalent Edmund Optics /
   Semrock / Chroma page).
2. **Download its raw spectral data.** Look for a link near the transmission plot - common wording
   is "Click for Raw Data", "Plot and downloadable data", "Export data", or a small spreadsheet/CSV
   icon next to the graph. Save the file (xlsx, csv, or txt) - don't retype the numbers by hand.
3. **Register it via the app**: run `streamlit run app.py`, open the **"Import a filter data file"**
   expander in the sidebar, upload the file, fill in a display name / manufacturer / part number /
   category (excitation, emission, or dichroic), and click **Parse & register**. This copies the file
   into this folder and adds one row to `catalog.yaml` for you - no manual editing needed.

   Alternatively, drop the file into this folder yourself and add a matching row to `catalog.yaml`:

   ```yaml
   - display_name: "Thorlabs FF01-475/35-25 (475/35 BP)"
     manufacturer: Thorlabs
     part_number: FF01-475/35-25
     category: excitation   # excitation | emission | dichroic
     filename: thorlabs_FF01-475-35-25_excitation.xlsx
   ```

## Parsing notes

The importer (`src/fluorescence_model/filter_import.py`) auto-detects the data table in the file
regardless of exact header wording or leading description rows - it just needs a wavelength column
(150-2500 nm) alongside one or two numeric value columns (a %Transmission column, or %T + %R side by
side for dichroics). If a file fails to parse, open it and check that it has an actual data table
with a wavelength column - some product pages only show a plot image with no underlying data file,
in which case that part can't be modeled here without contacting the manufacturer for the raw curve.

For dichroics with only a %T curve published, the app derives an R = 1 - T approximation for the
reflected (excitation) path automatically - that's standard practice when a separate reflection curve
isn't provided, but note it in your own notes if precision near the cut-on/off edge matters for your
application.

# Adding filter/dichroic data

There's no bulk API for filter manufacturers (Thorlabs, Edmund Optics, Semrock, Chroma, ...) -
each part's spectral data is a one-off download from its own product page. Add filters here as you
need them, for parts you actually own or are considering.

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

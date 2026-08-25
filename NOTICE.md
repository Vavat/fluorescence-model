# Data attribution

This project's source code is MIT-licensed (see [`LICENSE`](LICENSE)). That license covers the
code only. The fluorophore and filter spectral data this tool bundles or fetches is measured data
from third-party sources, carries its own terms, and isn't something this project claims to own or
relicense. If you redistribute this repo (or a fork of it) including its `data/` directory, or a
copy of data fetched at runtime, carry these attributions forward.

## Fluorophore spectra

- **[FPbase](https://www.fpbase.org)** - fluorescent protein and common-dye excitation/emission
  spectra, fetched via [`fpbase_client.py`](src/fluorescence_model/fpbase_client.py) and cached
  under `data/fluorophores/`. FPbase is a community-editable, freely reusable database; if you
  publish work that relies on data pulled through this tool, cite:
  > Lambert, T.J. (2019) FPbase: a community-editable fluorescent protein database.
  > *Nature Methods* 16, 277-278. https://doi.org/10.1038/s41592-019-0352-8
- **[fluorophores.tugraz.at](https://fluorophores.tugraz.at)** (fluorophores.org) - organic dye
  spectra, fetched one dye at a time on explicit request via
  [`tugraz_client.py`](src/fluorescence_model/tugraz_client.py) (see that module's docstring for why
  it's deliberately never a bulk fetch - their own disclaimer asks that the database not be
  downloaded in bulk). Every record fetched this way is tagged with a `credit` field
  ("Data courtesy of fluorophores.tugraz.at (fluorophores.org)") and the retrieval date in its
  cached JSON - keep that intact if you pass the data on.

## Filter/dichroic spectra

- **Thorlabs** (`data/filters/thorlabs_*.csv`) - transmission curves measured and published by
  Thorlabs on their own product pages, downloaded and reformatted (not altered in substance) for use
  in this tool. See [`data/filters/README.md`](data/filters/README.md) for how these were obtained
  and how to add more.
- **FPbase's aggregated filter catalog** - real Chroma/Omega/Thorlabs/other-manufacturer filter
  spectra contributed to FPbase via public microscope configs, fetched via
  `fpbase_client.fetch_filter()`. Same FPbase citation as above applies.
- Any filter you import yourself via "Import a filter data file" carries whatever terms the
  manufacturer whose product page you downloaded it from applies to their published spec data.

## If in doubt

None of the above is a substitute for checking the original source's own terms yourself before
redistributing their data at scale - this note is a pointer to where each dataset came from, not a
legal opinion on what you're allowed to do with it.

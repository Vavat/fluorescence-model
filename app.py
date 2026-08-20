"""Streamlit UI: pick a fluorophore, excitation filter, dichroic, emission
filter, and an LED/laser source, and see the spectral overlap live.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from fluorescence_model import catalog, fpbase_client, optics, plotting, sources, tugraz_client
from fluorescence_model.filter_import import parse_filter_file

st.set_page_config(page_title="Fluorescence Filter/Source Modeler", layout="wide")
st.title("Fluorescence Filter & Source Modeler")
st.caption(
    "Model spectral overlap through an excitation/emission path to help pick filters, "
    "dichroics, and LED/laser sources for a given fluorophore."
)

# ---------------------------------------------------------------- sidebar --

with st.sidebar:
    st.header("Fluorophore")
    fluorophores = catalog.list_fluorophores()
    fluor_names = [f.name for f in fluorophores]
    selected_name = st.selectbox("Fluorophore", fluor_names, index=0 if fluor_names else None)
    selected_fluor = next((f for f in fluorophores if f.name == selected_name), None)

    with st.expander("Add a fluorophore"):
        st.markdown("**From FPbase** (fluorescent proteins + common dyes)")
        fpbase_name = st.text_input("Name on FPbase", key="fpbase_name", placeholder="e.g. mScarlet")
        if st.button("Fetch from FPbase", key="fpbase_fetch"):
            try:
                rec = fpbase_client.fetch_fluorophore(fpbase_name)
                st.success(f"Added {rec.name}. Reselect it above.")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"FPbase lookup failed: {e}")

        st.markdown("---")
        st.markdown("**From fluorophores.tugraz.at** (organic dyes) - one dye at a time, on request")
        tugraz_name = st.text_input("Exact/partial name on tugraz", key="tugraz_name", placeholder="e.g. Fluorescein")
        tugraz_csv_id = st.text_input(
            "Spectrum CSV id (optional manual override)",
            key="tugraz_csv_id",
            help="Their substance detail pages currently 500-error; if you already know the "
            "fluorescence/<id>.csv id for this dye (e.g. from TU Graz directly), enter it here "
            "to skip the (currently broken) automatic lookup.",
        )
        if st.button("Fetch from tugraz", key="tugraz_fetch"):
            try:
                csv_id = int(tugraz_csv_id) if tugraz_csv_id.strip() else None
                rec = tugraz_client.fetch_fluorophore(tugraz_name, spectrum_csv_id=csv_id)
                st.success(f"Added {rec.name} ({rec.credit}). Reselect it above.")
                st.cache_data.clear()
            except tugraz_client.TugrazUnavailable as e:
                st.error(f"tugraz unavailable: {e}")
            except Exception as e:
                st.error(f"tugraz lookup failed: {e}")

    st.header("Filters")
    ex_filters = catalog.list_filters("excitation")
    dichroics = catalog.list_filters("dichroic")
    em_filters = catalog.list_filters("emission")

    def _filter_picker(label, options):
        names = ["None"] + [f.display_name for f in options]
        choice = st.selectbox(label, names)
        return next((f for f in options if f.display_name == choice), None)

    selected_ex_filter = _filter_picker("Excitation filter", ex_filters)
    selected_dichroic = _filter_picker("Dichroic", dichroics)
    selected_em_filter = _filter_picker("Emission filter", em_filters)

    with st.expander("Import a filter data file"):
        st.markdown(
            "Download the raw transmission data (xlsx/csv/txt) from the manufacturer's product "
            "page (Thorlabs, Edmund Optics, Semrock, Chroma, ...) and upload it here. "
            "See `data/filters/README.md` for step-by-step instructions."
        )
        uploaded = st.file_uploader("Filter data file", type=["xlsx", "xls", "csv", "txt", "tsv", "dat"])
        f_display_name = st.text_input("Display name", key="f_display_name")
        f_manufacturer = st.text_input("Manufacturer", key="f_manufacturer")
        f_part_number = st.text_input("Part number", key="f_part_number")
        f_category = st.selectbox("Category", ["excitation", "emission", "dichroic"], key="f_category")
        if st.button("Parse & register"):
            if not uploaded or not f_display_name or not f_part_number:
                st.error("Provide a file, display name, and part number.")
            else:
                try:
                    parsed = parse_filter_file(uploaded, filename=uploaded.name)
                    safe_manufacturer = catalog.safe_filename_part(f_manufacturer or "unknown")
                    safe_part = catalog.safe_filename_part(f_part_number)
                    dest_name = f"{safe_manufacturer}_{safe_part}_{f_category}{Path(uploaded.name).suffix}"
                    dest_path = catalog.FILTER_DIR / dest_name
                    uploaded.seek(0)
                    dest_path.write_bytes(uploaded.read())
                    catalog.register_filter(f_display_name, f_manufacturer, f_part_number, f_category, dest_name)
                    st.success(f"Registered {f_display_name} ({', '.join(parsed.series)}). Reselect it above.")
                except Exception as e:
                    st.error(f"Could not parse this file: {e}")

    with st.expander("Fetch a filter from FPbase"):
        st.markdown(
            "FPbase aggregates real commercial filter spectra (Chroma, Omega, Thorlabs, and others) "
            "contributed via public microscope configs - no file download needed for anything already "
            "in there. Coverage varies a lot by manufacturer (Edmund Optics has essentially none)."
        )
        fp_filter_query = st.text_input(
            "Filter name or part number", key="fp_filter_query", placeholder="e.g. Chroma ET525/50m"
        )
        fp_filter_category = st.selectbox(
            "Category",
            ["excitation", "emission", "dichroic"],
            key="fp_filter_category",
            help="Only used if FPbase's own data doesn't already mark this as a dichroic/beamsplitter - "
            "a filter's excitation/emission role depends on how it's placed in a microscope, not the "
            "filter itself, so FPbase can't always infer it.",
        )
        if st.button("Search & fetch", key="fp_filter_fetch"):
            if not fp_filter_query.strip():
                st.error("Enter a filter name or part number.")
            else:
                try:
                    result = fpbase_client.fetch_filter(fp_filter_query, category=fp_filter_category)
                    st.success(f"Registered {result.display_name} (subtype {result.subtype}). Reselect it above.")
                except Exception as e:
                    st.error(str(e))

    st.header("Excitation source")
    source_type = st.radio("Type", ["LED", "Laser"], horizontal=True)
    if source_type == "LED":
        center_nm = st.number_input("Center wavelength (nm)", min_value=200.0, max_value=1200.0, value=470.0, step=1.0)
        fwhm_nm = st.number_input("FWHM (nm)", min_value=1.0, max_value=200.0, value=25.0, step=1.0)
        led_model = st.selectbox(
            "Spectral shape model",
            sources.LED_MODELS,
            format_func=lambda m: {
                "gaussian_wavenumber": "Gaussian in wavenumber (recommended - matches real LED asymmetry)",
                "two_sided_exp": "Two-sided exponential decay (simple, symmetric)",
            }[m],
        )
        source_spectrum = sources.led_spectrum(center_nm, fwhm_nm, model=led_model)
    else:
        center_nm = st.number_input("Center wavelength (nm)", min_value=200.0, max_value=1200.0, value=488.0, step=0.5)
        linewidth_nm = st.number_input("Linewidth (nm)", min_value=0.01, max_value=20.0, value=1.0, step=0.1)
        source_spectrum = sources.laser_spectrum(center_nm, linewidth_nm)

# ------------------------------------------------------------- main panel --

if selected_fluor is None:
    st.info("No fluorophores available yet - add one from FPbase or tugraz in the sidebar.")
    st.stop()

ex_filter_spec = None
if selected_ex_filter is not None:
    series = selected_ex_filter.load()
    ex_filter_spec = catalog.pick_primary_series(series, "excitation")

em_filter_spec = None
if selected_em_filter is not None:
    series = selected_em_filter.load()
    em_filter_spec = catalog.pick_primary_series(series, "emission")

dichroic_spec = None
if selected_dichroic is not None:
    series = selected_dichroic.load()
    dichroic_spec = catalog.pick_primary_series(series, "dichroic")

excitation_combined = optics.excitation_light_spectrum(source_spectrum, ex_filter_spec, dichroic_spec)
excitation_absorbed = optics.excitation_absorption_spectrum(
    source_spectrum, selected_fluor.excitation, ex_filter_spec, dichroic_spec
)
emission_combined = optics.emission_light_spectrum(selected_fluor.emission, dichroic_spec, em_filter_spec)

log_y = st.radio("Y-axis scale", ["Linear", "Log"], horizontal=True) == "Log"

fig = plotting.build_figure(
    fluorophore_excitation=selected_fluor.excitation,
    fluorophore_emission=selected_fluor.emission,
    source=source_spectrum,
    excitation_filter=ex_filter_spec,
    dichroic=dichroic_spec,
    emission_filter=em_filter_spec,
    excitation_combined=excitation_combined,
    excitation_absorbed=excitation_absorbed,
    emission_combined=emission_combined,
    log_y=log_y,
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Dashed = illumination side (source, excitation filter, fluorophore excitation); "
    "solid = detection side (fluorophore emission, emission filter, dichroic). The filled curves "
    "show light actually reaching the specimen/camera (unnormalized - their height reflects real "
    "throughput loss, not just shape): the excitation side has a 50%-opacity curve for light "
    "reaching the specimen and a 100%-opacity curve, drawn on top, for the subset of that light "
    "actually absorbed by the fluorophore. Both match the efficiency metrics below exactly."
)

result = optics.evaluate_path(
    fluorophore_excitation=selected_fluor.excitation,
    fluorophore_emission=selected_fluor.emission,
    source=source_spectrum,
    excitation_filter=ex_filter_spec,
    dichroic=dichroic_spec,
    emission_filter=em_filter_spec,
)

st.subheader("Relative figures of merit")
st.caption(
    "These compare candidate filter/source combinations for the *same* fluorophore - they are "
    "not absolute brightness/photon-flux predictions, since source spectra are relative models "
    "and filter/fluorophore curves are unitless fractions."
)
c1, c2, c3 = st.columns(3)
c1.metric("Excitation efficiency", f"{result.excitation_efficiency:.1%}")
c2.metric("Emission efficiency", f"{result.emission_efficiency:.1%}")
c3.metric("Overall relative score", f"{result.overall_score:.1%}")

for w in result.warnings:
    st.warning(w)

with st.expander("Fluorophore details"):
    st.write(f"**{selected_fluor.name}** - source: {selected_fluor.source}")
    st.write(f"Excitation peak: {selected_fluor.excitation.peak_nm():.0f} nm")
    st.write(f"Emission peak: {selected_fluor.emission.peak_nm():.0f} nm")

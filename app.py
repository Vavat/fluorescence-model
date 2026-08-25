"""Streamlit UI: pick a fluorophore, excitation filter, dichroic, emission
filter, and an LED/laser source, and see the spectral overlap live.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from fluorescence_model import catalog, export, fpbase_client, optics, plotting, sources, tugraz_client
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
    default_fluor_index = fluor_names.index("EGFP") if "EGFP" in fluor_names else (0 if fluor_names else None)
    selected_name = st.selectbox("Fluorophore", fluor_names, index=default_fluor_index)
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

    def _filter_picker(label, options, default_part_number=None):
        names = ["None"] + [f.display_name for f in options]
        default_index = 0
        if default_part_number is not None:
            default_entry = next((f for f in options if f.part_number == default_part_number), None)
            if default_entry is not None:
                default_index = names.index(default_entry.display_name)
        choice = st.selectbox(label, names, index=default_index)
        return next((f for f in options if f.display_name == choice), None)

    # Thorlabs' MDF05-GFP set (excitation/dichroic/emission) as the default
    # out-of-the-box filter combination, paired with EGFP and the 465nm LED
    # default below.
    selected_ex_filter = _filter_picker("Excitation filter", ex_filters, default_part_number="MDF05-GFP")
    selected_dichroic = _filter_picker("Dichroic", dichroics, default_part_number="MDF05-GFP")
    selected_em_filter = _filter_picker("Emission filter", em_filters, default_part_number="MDF05-GFP")

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
        center_nm = st.number_input("Center wavelength (nm)", min_value=200.0, max_value=1200.0, value=465.0, step=1.0)
        fwhm_nm = st.number_input("FWHM (nm)", min_value=1.0, max_value=200.0, value=25.0, step=1.0)
        source_spectrum = sources.led_spectrum(center_nm, fwhm_nm)
    else:
        center_nm = st.number_input("Center wavelength (nm)", min_value=200.0, max_value=1200.0, value=488.0, step=0.5)
        linewidth_nm = st.number_input("Linewidth (nm)", min_value=0.01, max_value=20.0, value=1.0, step=0.1)
        source_spectrum = sources.laser_spectrum(center_nm, linewidth_nm)

    with st.expander("Curve visibility"):
        # Backed by st.session_state via `key` - this, not the Plotly legend,
        # is what actually survives a rerun (see plotting.py's module
        # docstring for why Plotly's own uid/uirevision mechanism doesn't
        # work through st.plotly_chart). Clicking a trace's legend entry
        # directly still works for a quick one-off hide, it just won't stick
        # past the next rerun.
        st.multiselect(
            "Curves shown on the plot",
            options=plotting.CURVE_NAMES,
            default=plotting.CURVE_NAMES,
            key="shown_curves",
        )

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
excitation_leak = optics.excitation_leak_spectrum(source_spectrum, ex_filter_spec, em_filter_spec)

# Right-justify the "Show" radio group within its column - it's a plain
# st.radio (not st.segmented_control's larger buttons) specifically to stay
# small and match "Y-axis scale"'s own visual weight. Scoped to this one
# widget via its `st-key-<key>` class (a stable, documented Streamlit hook),
# not a global override.
st.markdown(
    """
    <style>
    div.st-key-side_filter [data-testid="stRadioGroup"] { justify-content: flex-end; }
    </style>
    """,
    unsafe_allow_html=True,
)

col_scale, col_side = st.columns([1, 2])
with col_scale:
    log_y = st.radio("Y-axis scale", ["Linear", "Log"], horizontal=True, label_visibility="collapsed") == "Log"
with col_side:
    side = st.radio(
        "Show",
        ["Excitation only", "All", "Emission only", "Excitation leak"],
        index=1,  # "All"
        horizontal=True,
        width="stretch",  # fills the column so the right-justify CSS above has room to push against
        key="side_filter",
        label_visibility="collapsed",
        help="Dichroic (%T) stays shown in every state. \"Excitation leak\" shows just the curves "
        "behind the excitation-bleed warning below, so you can see how much excitation light "
        "reaching the camera overlaps genuine emission.",
    )

hidden_names = set(plotting.CURVE_NAMES) - set(st.session_state.get("shown_curves", plotting.CURVE_NAMES))
hidden_names |= set(plotting.CURVE_NAMES) - plotting.SIDE_VISIBLE_CURVES[side]

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
    excitation_leak=excitation_leak,
    log_y=log_y,
    hidden_names=hidden_names,
)
st.plotly_chart(fig, use_container_width=True, key="spectral_overlay_chart")
st.caption(
    "Dashed = illumination side (source, excitation filter, fluorophore excitation); "
    "solid = detection side (fluorophore emission, emission filter, dichroic). Lines are colored by "
    "each curve's own characteristic wavelength - peak for most curves, the 50%-transmission "
    "crossing for the dichroic (a broad plateau, not a single peak). The filled curves show light "
    "actually reaching the specimen/camera as a true-color gradient across wavelength (unnormalized - "
    "their height reflects real throughput loss, not just shape): the excitation side has a faint "
    "15%-alpha curve for light reaching the specimen and a 100%-alpha curve, drawn on top, for the "
    "subset of that light actually absorbed by the fluorophore. \"Excitation leak at camera\" "
    "(source x excitation filter x emission filter - deliberately not the dichroic, since that light "
    "has to pass both filters regardless of how well any particular dichroic suppresses it; dashed "
    "since it's excitation-origin light even though it ends up at the camera) is the same quantity "
    "behind the excitation-bleed warning below. "
    "The switch above the plot limits it to one side, or to just the excitation-leak-relevant curves "
    "(the dichroic stays shown in every state); the sidebar's \"Curve visibility\" persistently hides "
    "an individual curve - clicking its legend entry directly only hides it until the next change, "
    "since Streamlit doesn't preserve Plotly legend state."
)

export_table = export.build_export_table(
    fluorophore_excitation=selected_fluor.excitation,
    fluorophore_emission=selected_fluor.emission,
    source=source_spectrum,
    excitation_filter=ex_filter_spec,
    dichroic=dichroic_spec,
    emission_filter=em_filter_spec,
    excitation_combined=excitation_combined,
    excitation_absorbed=excitation_absorbed,
    emission_combined=emission_combined,
    excitation_leak=excitation_leak,
)
col_export_format, col_export_button = st.columns([1, 3])
with col_export_format:
    export_format = st.selectbox(
        "Export format", export.EXPORT_FORMATS, label_visibility="collapsed"
    )
with col_export_button:
    export_data, export_mime, export_ext = export.export_bytes(export_table, export_format)
    st.download_button(
        f"Export spectra as {export_format}",
        data=export_data,
        file_name=f"fluorescence_spectra.{export_ext}",
        mime=export_mime,
    )
st.caption(
    "One row per wavelength (300-900nm), one column per curve currently plotted - values match what's "
    "on screen: reference curves peak-normalized, the four \"light that actually gets there\" curves "
    "at their real relative magnitude."
)

result = optics.evaluate_path(
    fluorophore_excitation=selected_fluor.excitation,
    fluorophore_emission=selected_fluor.emission,
    source=source_spectrum,
    excitation_filter=ex_filter_spec,
    dichroic=dichroic_spec,
    emission_filter=em_filter_spec,
)

for w in result.warnings:
    st.warning(w)

with st.expander("Fluorophore details"):
    st.write(f"**{selected_fluor.name}** - source: {selected_fluor.source}")
    st.write(f"Excitation peak: {selected_fluor.excitation.peak_nm():.0f} nm")
    st.write(f"Emission peak: {selected_fluor.emission.peak_nm():.0f} nm")

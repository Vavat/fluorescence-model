"""Builds the overlaid Plotly figure.

Raw spectra (fluorophore excitation/emission, source, filters, dichroic, and
eventually camera QE) are drawn as plain lines, peak-normalized to a common
0-1 scale so their shapes are directly comparable - dashed for anything on
the excitation/illumination side (source, excitation filter, fluorophore
excitation), solid for anything on the emission/detection side (fluorophore
emission, emission filter, dichroic %T, camera).

The computed combined curves are drawn as filled areas, deliberately NOT
normalized, so their height relative to the reference lines shows real
throughput loss:
- excitation_light (15% fill alpha): source x excitation filter x dichroic
  reflectance - the light that reaches the specimen.
- excitation_absorbed (100% fill alpha): the above, further weighted by the
  fluorophore's own excitation spectrum - the light that actually drives
  excitation. Always <= excitation_light point-by-point, drawn on top of it.
- emission_combined (50% fill alpha): fluorophore emission x dichroic
  transmission x emission filter - the light that reaches the camera.

Only the FILL is scaled by that alpha (via an rgba fillcolor) - each curve's
boundary LINE is always drawn fully opaque. This matters because
excitation_light and excitation_absorbed share the same color: whenever a
fluorophore's excitation efficiency is high across the source's band (the
common, well-matched case), excitation_absorbed nearly coincides with
excitation_light, and two same-colored fills that overlap are visually just
"more of that color" regardless of their stated opacity - orange-over-orange
is still orange. A crisp outline on excitation_light keeps its true extent
traceable even when the fill underneath is fully covered by the (also
orange) absorbed curve on top of it.

Every trace carries a stable `uid` and the figure sets a constant
`uirevision`, which is the standard Plotly.js recipe for preserving
legend-click state (and zoom/pan) across figure rebuilds - EXCEPT that
Streamlit's `st.plotly_chart` always strips trace `uid`s before they reach
the browser (it calls `plotly.io.to_json(fig, validate=False)`, and
`remove_uids` defaults to True there - see plotly/io/_json.py). Confirmed
empirically: even with `uirevision` set and the trace list unchanged between
reruns, a legend-hidden trace resets to visible on the next Streamlit rerun.
So `uid`/`uirevision` are kept here (harmless, and Streamlit's docs suggest
`uirevision` still helps preserve zoom/pan for some chart types) but are NOT
what makes show/hide persistent - that's `hidden_names` below, driven by
Streamlit `session_state` (via widget `key`s in app.py), which is the only
mechanism in this stack that's actually guaranteed to survive a rerun.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import plotly.graph_objects as go

from .spectrum import DEFAULT_GRID_NM, Spectrum

# Floor used only for display when the log-scale toggle is on - real zeros
# would otherwise vanish off a log axis. Never affects the underlying data
# or any efficiency/metric calculation, just what gets plotted.
_LOG_FLOOR = 1e-6

# Fill opacity for "Excitation light at specimen" - kept low so it reads as
# a faint backdrop behind "Excitation light absorbed by fluorophore" (drawn
# on top at full opacity) instead of competing with it.
_EXCITATION_AT_SPECIMEN_OPACITY = 0.15

# Constant uirevision so Plotly.js preserves user-driven state (legend
# show/hide clicks, zoom/pan) across figure rebuilds, keyed per-trace by the
# stable `uid` each trace is given below - see module docstring.
_UIREVISION = "fluorescence-model"

_COLORS = {
    "excitation": "#2ca02c",
    "emission": "#d62728",
    "source": "#ff7f0e",
    "excitation_filter": "#1f77b4",
    "emission_filter": "#9467bd",
    "dichroic": "#7f7f7f",
    "camera": "#8c564b",
    "excitation_combined": "#ff7f0e",
    "emission_combined": "#d62728",
}

def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# Dashed = excitation/illumination side, solid = emission/detection side.
_DASH = {
    "excitation": "dash",
    "source": "dash",
    "excitation_filter": "dash",
    "emission": "solid",
    "emission_filter": "solid",
    "dichroic": "solid",
    "camera": "solid",
}

# Every curve build_figure can draw, by its legend name, in display order.
# Exposed so app.py can build show/hide controls (e.g. a multiselect) without
# duplicating this list, and pass the result back in as `hidden_names`.
CURVE_NAMES = (
    "Fluorophore excitation",
    "Fluorophore emission",
    "Source spectrum",
    "Excitation filter",
    "Dichroic (%T)",
    "Emission filter",
    "Excitation light at specimen",
    "Excitation light absorbed by fluorophore",
    "Emission light at camera",
)


def build_figure(
    fluorophore_excitation: Optional[Spectrum] = None,
    fluorophore_emission: Optional[Spectrum] = None,
    source: Optional[Spectrum] = None,
    excitation_filter: Optional[Spectrum] = None,
    dichroic: Optional[Spectrum] = None,
    emission_filter: Optional[Spectrum] = None,
    excitation_combined: Optional[Spectrum] = None,
    excitation_absorbed: Optional[Spectrum] = None,
    emission_combined: Optional[Spectrum] = None,
    grid=DEFAULT_GRID_NM,
    log_y: bool = False,
    hidden_names: Optional[set] = None,
) -> go.Figure:
    """`hidden_names` (a subset of CURVE_NAMES) draws those traces
    legend-only (hidden but still listed, re-showable by clicking them) -
    intended to be driven by a Streamlit widget with a stable `key`, which is
    what actually makes this persist across reruns (see module docstring)."""
    fig = go.Figure()
    hidden_names = hidden_names or set()

    def _display_y(values: np.ndarray) -> np.ndarray:
        return np.clip(values, _LOG_FLOOR, None) if log_y else values

    def _visibility(name: str):
        return "legendonly" if name in hidden_names else True

    def add_line(spec: Optional[Spectrum], name: str, key: str):
        if spec is None:
            return
        norm = spec.normalize()
        fig.add_trace(
            go.Scatter(
                x=norm.wavelength_nm,
                y=_display_y(norm.value),
                name=name,
                mode="lines",
                line=dict(color=_COLORS[key], dash=_DASH[key]),
                opacity=0.9,
                uid=key,
                visible=_visibility(name),
            )
        )

    def add_filled(spec: Optional[Spectrum], name: str, key: str, uid: str, opacity: float = 0.5):
        if spec is None:
            return
        # `opacity` scales the FILL only (via an rgba fillcolor), while the
        # boundary line stays fully opaque. Two same-colored fills that
        # nearly coincide (e.g. "absorbed" sitting almost exactly on top of
        # "at specimen" whenever the fluorophore's excitation efficiency is
        # high) are visually indistinguishable as fills - orange-over-orange
        # is just orange - but the crisp outline still traces the wider
        # curve's true extent even where the fill underneath is covered.
        fig.add_trace(
            go.Scatter(
                x=spec.wavelength_nm,
                y=_display_y(spec.value),
                name=name,
                mode="lines",
                line=dict(color=_COLORS[key], width=1.5),
                fill="tozeroy",
                fillcolor=_rgba(_COLORS[key], opacity),
                uid=uid,
                visible=_visibility(name),
            )
        )

    add_line(fluorophore_excitation, "Fluorophore excitation", "excitation")
    add_line(fluorophore_emission, "Fluorophore emission", "emission")
    add_line(source, "Source spectrum", "source")
    add_line(excitation_filter, "Excitation filter", "excitation_filter")
    add_line(dichroic, "Dichroic (%T)", "dichroic")
    add_line(emission_filter, "Emission filter", "emission_filter")
    add_filled(
        excitation_combined,
        "Excitation light at specimen",
        "excitation_combined",
        uid="excitation_light_at_specimen",
        opacity=_EXCITATION_AT_SPECIMEN_OPACITY,
    )
    add_filled(
        excitation_absorbed,
        "Excitation light absorbed by fluorophore",
        "excitation_combined",
        uid="excitation_absorbed",
        opacity=1.0,
    )
    add_filled(
        emission_combined,
        "Emission light at camera",
        "emission_combined",
        uid="emission_light_at_camera",
        opacity=0.5,
    )

    yaxis: dict = dict(title="Normalized intensity / transmission", type="log" if log_y else "linear")
    if log_y:
        yaxis["exponentformat"] = "power"
    else:
        yaxis["range"] = [0, 1.05]

    fig.update_layout(
        xaxis=dict(title="Wavelength (nm)", range=[float(grid.min()), float(grid.max())]),
        yaxis=yaxis,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=40, r=20, t=40, b=40),
        template="plotly_white",
        height=560,
        # Preserve user legend show/hide clicks (and zoom/pan) across
        # rebuilds - see module docstring.
        uirevision=_UIREVISION,
    )
    return fig

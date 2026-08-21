"""Builds the overlaid Plotly figure.

Raw spectra (fluorophore excitation/emission, source, filters, dichroic, and
eventually camera QE) are drawn as plain lines, peak-normalized to a common
0-1 scale so their shapes are directly comparable - dashed for anything on
the excitation/illumination side (source, excitation filter, fluorophore
excitation), solid for anything on the emission/detection side (fluorophore
emission, emission filter, dichroic %T, camera).

The computed combined curves are drawn as solid filled areas, deliberately
NOT normalized, so their height relative to the reference lines shows real
throughput loss:
- excitation_light (15% opacity): source x excitation filter x dichroic
  reflectance - the light that reaches the specimen. Kept faint so it reads
  as backdrop and doesn't obscure excitation_absorbed drawn on top of it.
- excitation_absorbed (100% opacity): the above, further weighted by the
  fluorophore's own excitation spectrum - the light that actually drives
  excitation. Always <= excitation_light point-by-point, drawn on top of it
  at full opacity so the "absorbed" subset stands out within the "reaches
  the specimen" curve.
- emission_combined (50% opacity): fluorophore emission x dichroic
  transmission x emission filter - the light that reaches the camera.

Every trace carries a stable `uid` (its semantic role, e.g. "dichroic" or
"excitation_absorbed") rather than an order-derived one, and the figure sets
a constant `uirevision`. Together these tell Plotly.js to keep whatever
show/hide state the user has clicked in the legend for a given trace across
re-renders (e.g. picking a different fluorophore), instead of resetting
every trace to visible. A trace only reverts to its default visibility if it
disappears entirely (e.g. no dichroic selected) and later reappears.
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
) -> go.Figure:
    fig = go.Figure()

    def _display_y(values: np.ndarray) -> np.ndarray:
        return np.clip(values, _LOG_FLOOR, None) if log_y else values

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
                # Stable per-role id (not order-derived) so Plotly.js can
                # match this trace to its previous visibility state even
                # when other traces are added/removed around it.
                uid=key,
            )
        )

    def add_filled(spec: Optional[Spectrum], name: str, key: str, uid: str, opacity: float = 0.5):
        if spec is None:
            return
        fig.add_trace(
            go.Scatter(
                x=spec.wavelength_nm,
                y=_display_y(spec.value),
                name=name,
                mode="lines",
                line=dict(color=_COLORS[key], width=1),
                fill="tozeroy",
                fillcolor=_COLORS[key],
                opacity=opacity,
                uid=uid,
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

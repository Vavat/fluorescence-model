"""Builds the overlaid Plotly figure.

Coloring scheme (fixed, not a switch - this is the settled design):

- Fluorophore excitation, excitation filter, source: dashed lines, each
  colored by its OWN peak wavelength (see wavelength_color.py) - a curve
  peaking in the blue reads blue, one peaking in the red reads red.
- Fluorophore emission, emission filter: solid lines, same peak-wavelength
  coloring.
- Dichroic (%T): solid line, colored by the wavelength where it crosses 50%
  transmission (Spectrum.crossing_nm) rather than its peak - a dichroic is
  typically a broad near-100% plateau, not a single peak, so its physically
  meaningful characteristic wavelength is the cut-on/cut-off edge, not
  wherever peak_nm() happens to land in that plateau (possibly on ripple).
- The three computed "light that actually gets there" curves (excitation
  light at specimen, excitation light absorbed by fluorophore, emission
  light at camera) are filled areas with a horizontal color gradient
  following the true color of light at each wavelength (Plotly
  `fillgradient`), deliberately NOT normalized so their height shows real
  throughput loss. The gradient's start/stop are pinned to the plot's full
  x-axis range (not each curve's own narrower range) so a given wavelength
  reads as the same color on every curve, not rescaled per trace.

Alpha for the three gradient-filled curves is baked directly into their
colorscale stops (as an rgba alpha), not the trace's own `opacity`, and each
still gets a crisp, fully-opaque neutral outline:
- excitation light at specimen: 15% alpha (faint backdrop)
- excitation light absorbed by fluorophore: 100% alpha, drawn on top
- emission light at camera: 50% alpha

This matters because excitation-light-at-specimen and excitation-absorbed
are drawn with the exact same gradient - whenever a fluorophore's excitation
efficiency is high across the source's band (the common, well-matched case),
"absorbed" nearly coincides with "at specimen", and two overlapping fills of
the same color are visually indistinguishable regardless of their alpha. The
crisp outline keeps "at specimen"'s true extent traceable even where its
fill is fully covered by "absorbed" on top of it.

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
from .wavelength_color import wavelength_to_hex, wavelength_to_rgb

# Floor used only for display when the log-scale toggle is on - real zeros
# would otherwise vanish off a log axis. Never affects the underlying data
# or any efficiency/metric calculation, just what gets plotted.
_LOG_FLOOR = 1e-6

# Fallback color when a curve has no meaningful characteristic wavelength to
# color by (e.g. an all-zero spectrum) - shouldn't normally happen.
_FALLBACK_COLOR = "#333333"

# Fill alpha for each of the three gradient-filled combined curves.
_EXCITATION_AT_SPECIMEN_ALPHA = 0.15
_EXCITATION_ABSORBED_ALPHA = 1.0
_EMISSION_AT_CAMERA_ALPHA = 0.5

# Constant uirevision so Plotly.js preserves user-driven state (legend
# show/hide clicks, zoom/pan) across figure rebuilds - see module docstring.
_UIREVISION = "fluorescence-model"

# Every curve build_figure can draw, by its legend name, in display order.
# Exposed so app.py can build show/hide controls without duplicating this
# list, and pass the result back in as `hidden_names`.
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

# The illumination-side and detection-side curve names, for a coarse
# excitation-only/emission-only/both display filter (app.py) - "Dichroic
# (%T)" deliberately belongs to neither, since it's relevant to both sides
# and stays shown regardless of which side is selected.
EXCITATION_SIDE_CURVES = (
    "Fluorophore excitation",
    "Source spectrum",
    "Excitation filter",
    "Excitation light at specimen",
    "Excitation light absorbed by fluorophore",
)
EMISSION_SIDE_CURVES = (
    "Fluorophore emission",
    "Emission filter",
    "Emission light at camera",
)


def _wavelength_gradient_stops(wl_min: float, wl_max: float, alpha: float, n: int = 60) -> list:
    """Colorscale stops (t in [0,1] -> rgba string) tracing the true color of
    light from wl_min to wl_max, for use as a Plotly `fillgradient.colorscale`
    with `start=wl_min, stop=wl_max` so t maps directly to wavelength."""
    stops = []
    for i in range(n):
        t = i / (n - 1)
        wl = wl_min + t * (wl_max - wl_min)
        r, g, b = wavelength_to_rgb(wl)
        stops.append([t, f"rgba({r},{g},{b},{alpha})"])
    return stops


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
    grid_min, grid_max = float(grid.min()), float(grid.max())
    _gradient_cache: dict = {}

    def _display_y(values: np.ndarray) -> np.ndarray:
        return np.clip(values, _LOG_FLOOR, None) if log_y else values

    def _visibility(name: str):
        return "legendonly" if name in hidden_names else True

    def _gradient_stops(alpha: float) -> list:
        if alpha not in _gradient_cache:
            _gradient_cache[alpha] = _wavelength_gradient_stops(grid_min, grid_max, alpha)
        return _gradient_cache[alpha]

    def add_characteristic_colored_line(
        spec: Optional[Spectrum], name: str, dash: str, uid: str, color_wavelength_fn=Spectrum.peak_nm
    ):
        """A dashed/solid line colored by one characteristic wavelength of
        its own data - by default its peak, but e.g. the dichroic passes
        `Spectrum.crossing_nm` instead (see module docstring)."""
        if spec is None:
            return
        wl_for_color = color_wavelength_fn(spec)
        color = wavelength_to_hex(wl_for_color) if wl_for_color is not None else _FALLBACK_COLOR
        norm = spec.normalize()
        fig.add_trace(
            go.Scatter(
                x=norm.wavelength_nm,
                y=_display_y(norm.value),
                name=name,
                mode="lines",
                line=dict(color=color, dash=dash),
                opacity=0.9,
                uid=uid,
                visible=_visibility(name),
            )
        )

    def add_gradient_filled(spec: Optional[Spectrum], name: str, uid: str, dash: str, alpha: float):
        if spec is None:
            return
        fig.add_trace(
            go.Scatter(
                x=spec.wavelength_nm,
                y=_display_y(spec.value),
                name=name,
                mode="lines",
                line=dict(color="rgba(40,40,40,0.8)", width=1.5, dash=dash),
                fill="tozeroy",
                fillgradient=dict(
                    type="horizontal",
                    colorscale=_gradient_stops(alpha),
                    start=grid_min,
                    stop=grid_max,
                ),
                uid=uid,
                visible=_visibility(name),
            )
        )

    add_characteristic_colored_line(fluorophore_excitation, "Fluorophore excitation", "dash", "excitation")
    add_characteristic_colored_line(fluorophore_emission, "Fluorophore emission", "solid", "emission")
    add_characteristic_colored_line(source, "Source spectrum", "dash", "source")
    add_characteristic_colored_line(excitation_filter, "Excitation filter", "dash", "excitation_filter")
    add_characteristic_colored_line(
        dichroic, "Dichroic (%T)", "solid", "dichroic", color_wavelength_fn=Spectrum.crossing_nm
    )
    add_characteristic_colored_line(emission_filter, "Emission filter", "solid", "emission_filter")
    add_gradient_filled(
        excitation_combined,
        "Excitation light at specimen",
        uid="excitation_light_at_specimen",
        dash="dash",
        alpha=_EXCITATION_AT_SPECIMEN_ALPHA,
    )
    add_gradient_filled(
        excitation_absorbed,
        "Excitation light absorbed by fluorophore",
        uid="excitation_absorbed",
        dash="dash",
        alpha=_EXCITATION_ABSORBED_ALPHA,
    )
    add_gradient_filled(
        emission_combined,
        "Emission light at camera",
        uid="emission_light_at_camera",
        dash="solid",
        alpha=_EMISSION_AT_CAMERA_ALPHA,
    )

    yaxis: dict = dict(title="Normalized intensity / transmission", type="log" if log_y else "linear")
    if log_y:
        yaxis["exponentformat"] = "power"
    else:
        yaxis["range"] = [0, 1.05]

    fig.update_layout(
        xaxis=dict(title="Wavelength (nm)", range=[grid_min, grid_max]),
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

"""Builds the overlaid Plotly figure: fluorophore excitation/emission,
source spectrum, and filter/dichroic passbands, all peak-normalized to a
common 0-1 scale so their shapes are directly comparable."""

from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go

from .spectrum import DEFAULT_GRID_NM, Spectrum

_COLORS = {
    "excitation": "#2ca02c",
    "emission": "#d62728",
    "source": "#ff7f0e",
    "excitation_filter": "#1f77b4",
    "emission_filter": "#9467bd",
    "dichroic": "#7f7f7f",
}


def build_figure(
    fluorophore_excitation: Optional[Spectrum] = None,
    fluorophore_emission: Optional[Spectrum] = None,
    source: Optional[Spectrum] = None,
    excitation_filter: Optional[Spectrum] = None,
    dichroic: Optional[Spectrum] = None,
    emission_filter: Optional[Spectrum] = None,
    grid=DEFAULT_GRID_NM,
) -> go.Figure:
    fig = go.Figure()

    def add_line(spec: Optional[Spectrum], name: str, color: str, dash: str = "solid", fill: bool = False):
        if spec is None:
            return
        norm = spec.normalize()
        fig.add_trace(
            go.Scatter(
                x=norm.wavelength_nm,
                y=norm.value,
                name=name,
                mode="lines",
                line=dict(color=color, dash=dash),
                fill="tozeroy" if fill else None,
                opacity=0.85,
            )
        )

    def add_band(spec: Optional[Spectrum], name: str, color: str):
        if spec is None:
            return
        norm = spec.normalize()
        fig.add_trace(
            go.Scatter(
                x=norm.wavelength_nm,
                y=norm.value,
                name=name,
                mode="lines",
                line=dict(color=color, width=1),
                fill="tozeroy",
                fillcolor=color,
                opacity=0.25,
            )
        )

    add_line(fluorophore_excitation, "Fluorophore excitation", _COLORS["excitation"], dash="dash")
    add_line(fluorophore_emission, "Fluorophore emission", _COLORS["emission"], dash="solid")
    add_line(source, "Source spectrum", _COLORS["source"], fill=True)
    add_band(excitation_filter, "Excitation filter", _COLORS["excitation_filter"])
    add_band(dichroic, "Dichroic (%T)", _COLORS["dichroic"])
    add_band(emission_filter, "Emission filter", _COLORS["emission_filter"])

    fig.update_layout(
        xaxis_title="Wavelength (nm)",
        yaxis_title="Normalized intensity / transmission",
        yaxis=dict(range=[0, 1.05]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=40, r=20, t=40, b=40),
        template="plotly_white",
        height=520,
    )
    return fig

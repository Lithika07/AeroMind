"""Plotly figures for the dashboard. One palette: good / caution / bad, used everywhere."""
import pandas as pd
import plotly.graph_objects as go

STATUS_COLOURS = {"good": "#2e9e5b", "caution": "#e0a100", "bad": "#d64545"}
PLANNED_COLOUR = "#5b6b7f"
MAP_ZOOM = 15.5
STRIP_HEIGHT = 150
LINE_HEIGHT = 260


def _layout(fig: go.Figure, height: int, **extra) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.12),
                      **extra)
    return fig


def link_strip(strip: pd.DataFrame, dropouts: list, phases: list) -> go.Figure:
    """Link quality across the whole flight as a coloured bar, dropouts labelled."""
    fig = go.Figure()
    for quality, colour in STATUS_COLOURS.items():
        part = strip[strip["link"] == quality]
        fig.add_trace(go.Bar(x=[1.0] * len(part), base=part["t"], y=["link"] * len(part), orientation="h",
                             marker_color=colour, name=quality, hovertemplate="t=%{base:.0f} s<extra>" + quality + "</extra>"))
    for d in dropouts:
        near = f" near WP{d['near_wp']}" if d.get("near_wp") is not None else ""
        fig.add_annotation(x=d["t"], y="link", yshift=28, showarrow=True, arrowhead=2,
                           text=f"lost {d['duration_s']} s{near}")
    for p in phases:
        fig.add_vline(x=p["t_start"], line_width=1, line_dash="dot", line_color="#999")
    fig.update_xaxes(title="seconds from start of log")
    fig.update_yaxes(showticklabels=False)
    return _layout(fig, STRIP_HEIGHT, barmode="overlay", bargap=0, showlegend=True)


def track_map(track: pd.DataFrame, planned: pd.DataFrame, dropouts: list) -> go.Figure:
    fig = go.Figure()
    if not planned.empty:
        fig.add_trace(go.Scattermap(lat=planned["lat"], lon=planned["lon"], mode="lines+markers+text",
                                    line=dict(color=PLANNED_COLOUR, width=2), marker=dict(size=8),
                                    text=[f"WP{w}" for w in planned["wp"]], textposition="top right", name="planned"))
    for quality, colour in STATUS_COLOURS.items():
        part = track[track["link"] == quality]
        if not part.empty:
            fig.add_trace(go.Scattermap(lat=part["lat"], lon=part["lon"], mode="markers",
                                        marker=dict(size=5, color=colour), name=f"flown, link {quality}",
                                        hovertemplate="t=%{text:.0f} s<extra></extra>", text=part["t"]))
    pins = [d for d in dropouts if d.get("lat") is not None]
    if pins:
        fig.add_trace(go.Scattermap(lat=[d["lat"] for d in pins], lon=[d["lon"] for d in pins], mode="markers+text",
                                    marker=dict(size=14, color=STATUS_COLOURS["bad"]),
                                    text=[f"lost {d['duration_s']} s" for d in pins], textposition="bottom right",
                                    name="dropout"))
    centre = track if not track.empty else planned
    fig.update_layout(map=dict(style="open-street-map", zoom=MAP_ZOOM,
                               center=dict(lat=float(centre["lat"].mean()), lon=float(centre["lon"].mean()))))
    return _layout(fig, 520)


def lines(frame: pd.DataFrame, columns: list, title: str, unit: str, marks: list = ()) -> go.Figure:
    fig = go.Figure()
    for column in columns:
        fig.add_trace(go.Scatter(x=frame["t"], y=frame[column], mode="lines", name=column))
    for t in marks:
        fig.add_vline(x=t, line_color=STATUS_COLOURS["bad"], line_dash="dash")
    fig.update_xaxes(title="seconds from start of log")
    fig.update_yaxes(title=unit)
    return _layout(fig, LINE_HEIGHT, title=dict(text=title, x=0, font=dict(size=14)))


def trend(history: pd.DataFrame, column: str, title: str, highlight: str) -> go.Figure:
    colours = [STATUS_COLOURS["bad"] if run == highlight else PLANNED_COLOUR for run in history["run_id"]]
    fig = go.Figure(go.Bar(x=history["run_id"], y=history[column], marker_color=colours))
    return _layout(fig, 220, title=dict(text=title, x=0, font=dict(size=13)))

"""The Summary tab: how the flight went, how the link held up, what to improve, how risky the next one is."""
from pathlib import Path

import streamlit as st

from dashboard import charts, data

DOT = {"good": ":green[●]", "caution": ":orange[●]", "bad": ":red[●]"}
BANNER = {"Good": st.success, "Needs attention": st.warning, "Unsafe": st.error}
RISK_COLOUR = {"Low": "green", "Medium": "orange", "High": "red"}
WORSE_LABELS = {"xtrack_max_m": "cross-track", "battery_mah_per_km": "battery use", "vibration_max": "vibration",
                "wind_max_ms": "wind", "link_uptime_pct": "link uptime", "health_score": "health"}


def _fmt(value, unit="", digits=1):
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def key_numbers(state: dict) -> None:
    m = state["metrics"]
    numbers = [("Flight time", _fmt(m["flight"]["duration_s"], " s", 0)), ("Distance", _fmt(m["flight"]["distance_m"], " m", 0)),
               ("Max altitude", _fmt(m["flight"]["max_alt_m"], " m")), ("Max speed", _fmt(m["flight"]["max_speed_ms"], " m/s")),
               ("Battery at landing", _fmt(m["battery"]["remaining_end_pct"], " %", 0)),
               ("Link uptime", _fmt(m["link"]["uptime_pct"], " %")), ("Max cross-track", _fmt(m["tracking"]["xtrack_max_m"], " m", 2))]
    for column, (label, value) in zip(st.columns(len(numbers)), numbers):
        column.metric(label, value)
    worse = state["history"]["worse_than_usual"]
    if worse:
        st.caption("Worse than your usual: " + ", ".join(
            f"{WORSE_LABELS.get(w['metric'], w['metric'])} {w['value']} (usual {w['mean']} ± {w['std']})" for w in worse))


def improvements(state: dict) -> None:
    st.subheader("Top 3 improvements")
    for rec in state["agents"]["approved"]["advisor"]["recommendations"]:
        st.markdown(f"**{rec['rank']}. {rec['text']}**  \n{rec['reason']} — _{rec['evidence']}_")


def risk_box(state: dict) -> None:
    risk = state["agents"]["approved"]["risk"]
    st.subheader("Next-mission risk")
    colour = RISK_COLOUR[risk["risk_level"]]
    st.markdown(f"### :{colour}[{risk['risk_level']}] · {risk['risk_score']}/100")
    battery = risk["predicted_battery_pct"]
    st.markdown(f"Predicted battery at landing: **{_fmt(battery, ' %', 0)}** · confidence {risk['confidence']}")
    for factor in risk["factors"][:4]:
        st.markdown(f"- {factor}")
    if risk["adjustment"]:
        st.caption(f"Risk agent adjusted the rule score by {risk['adjustment']:+d}: {risk['adjustment_reason']}")


def downloads(out_dir: Path) -> None:
    files = [("report.html", "text/html"), ("mission_fixed.waypoints", "text/plain"), ("changelog.md", "text/markdown")]
    columns = st.columns(len(files))
    for column, (name, mime) in zip(columns, files):
        path = out_dir / name
        if path.exists():
            column.download_button(name, path.read_bytes(), file_name=name, mime=mime, width="stretch")
        else:
            column.button(name, disabled=True, width="stretch", help="not produced for this run")


def render(state: dict, flight, out_dir: Path) -> None:
    summary = state["agents"]["approved"]["flight_summary"]
    BANNER[summary["verdict"]](f"**{summary['verdict']}** · health {state['metrics']['health_score']}/100\n\n"
                               f"{summary['summary']}")
    key_numbers(state)
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Flight story")
        for line in summary["flight_story"]:
            st.markdown(f"{DOT[line['status']]} **{line['phase']}** — {line['text']}")
    with right:
        risk_box(state)
    st.subheader("Telemetry signal")
    if flight is None:
        st.info("The original logs are not on this machine, so the signal strip cannot be drawn.")
    else:
        st.plotly_chart(charts.link_strip(data.link_strip(flight), state["metrics"]["link"]["dropouts"],
                                          state["metrics"]["phases"]), width="stretch", key="summary_strip")
    improvements(state)
    st.subheader("Downloads")
    downloads(out_dir)

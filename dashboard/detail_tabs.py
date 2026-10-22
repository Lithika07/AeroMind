"""Track, Telemetry, Anomalies, Power & attitude, History, Agents and Ask tabs."""
import numpy as np
import pandas as pd
import streamlit as st

from dashboard import ask, charts, data
from dashboard.text import plain
from tools import memory

SNIPPET_S = 20.0
CAUSE_FOR_SIGNAL = {"current": "low_battery", "vibration": "vibration", "altitude_error": "wind_drift"}
NO_LOGS = "The original logs are not on this machine, so time series cannot be drawn."


def _marks(state):
    return [d["t"] for d in state["metrics"]["link"]["dropouts"]]


def track(state, flight) -> None:
    if flight is None:
        st.info(NO_LOGS)
        return
    st.plotly_chart(charts.track_map(data.track(flight), data.mission_points(flight.mission),
                                     state["metrics"]["link"]["dropouts"]), width="stretch", key="track_map")
    st.caption("Planned route in grey; flown path coloured by link quality; red pins where the link dropped. "
               "The simulated world is georeferenced at the SITL home, so the map tiles are not the disaster world.")
    fix = state.get("mission_fix")
    if fix:
        st.markdown(f"**Fixed mission:** {fix['length_before_m']} m → {fix['length_after_m']} m, "
                    f"{fix['waypoints_before']} → {fix['waypoints_after']} waypoints, "
                    f"{len(fix['applied'])} edit(s) applied, {len(fix['rejected'])} rejected.")


def telemetry(state, flight) -> None:
    link = state["metrics"]["link"]
    columns = st.columns(4)
    columns[0].metric("Uptime", f"{link['uptime_pct']} %")
    columns[1].metric("Dropouts", len(link["dropouts"]))
    columns[2].metric("Packet loss", f"{link['packet_loss_pct']} %")
    columns[3].metric("Position rate", f"{link['position_rate_hz']} Hz")
    if flight is None:
        st.info(NO_LOGS)
        return
    strip = data.link_strip(flight)
    st.plotly_chart(charts.link_strip(strip, link["dropouts"], state["metrics"]["phases"]), width="stretch",
                    key="telemetry_strip")
    st.plotly_chart(charts.lines(strip, ["rate"], "Messages received per second", "msg/s", _marks(state)),
                    width="stretch", key="telemetry_rate")
    if link["dropouts"]:
        st.markdown("**Heartbeat gaps (dropouts)**")
        st.dataframe(pd.DataFrame(link["dropouts"]), hide_index=True, width="stretch")
    if link["rssi"] is None:
        st.info("RSSI not reported: this log has no RADIO_STATUS (no telemetry radio, as in SITL). "
                "The panel fills in on logs from a real radio.")
    else:
        st.json(link["rssi"])
    with st.expander("Message rates"):
        st.dataframe(data.message_rates(flight), hide_index=True, width="stretch")


def anomalies(state, flight) -> None:
    found = state["metrics"]["anomalies"]
    if not found:
        st.success("No spikes in vibration, current or altitude error while airborne.")
        return
    causes = {c["category"]: c for c in state["agents"]["approved"].get("diagnosis", {}).get("causes", [])}
    for k, a in enumerate(found):
        cause = causes.get(CAUSE_FOR_SIGNAL.get(a["signal"]))
        linked = f" · linked cause {cause['id']}: {plain(cause['cause'])}" if cause else ""
        st.markdown(f"**t={a['t']} s · {a['signal']} = {a['value']}** (z {a['z']}){linked}")
        if flight is not None:
            message, column = {"current": ("SYS_STATUS", "current_battery"), "vibration": ("VIBRATION", "vibration_z"),
                               "altitude_error": ("NAV_CONTROLLER_OUTPUT", "alt_error")}[a["signal"]]
            frame = data.series(flight, message, {a["signal"]: lambda f, c=column: f[c] / (100.0 if c == "current_battery" else 1.0)})
            window = frame[(frame["t"] > a["t"] - SNIPPET_S) & (frame["t"] < a["t"] + SNIPPET_S)]
            st.plotly_chart(charts.lines(window, [a["signal"]], "", "", [a["t"]]), width="stretch", key=f"anomaly_{k}")


def power_attitude(state, flight) -> None:
    if flight is None:
        st.info(NO_LOGS)
        return
    status = data.series(flight, "SYS_STATUS", {"battery %": lambda f: f["battery_remaining"].where(f["battery_remaining"] >= 0),
                                                "voltage V": lambda f: f["voltage_battery"] / 1000.0,
                                                "current A": lambda f: f["current_battery"] / 100.0})
    attitude = data.series(flight, "ATTITUDE", {"roll deg": lambda f: np.degrees(f["roll"]),
                                                "pitch deg": lambda f: np.degrees(f["pitch"])})
    vibration = data.series(flight, "VIBRATION", {k: (lambda f, k=k: f[f"vibration_{k}"]) for k in "xyz"})
    marks = _marks(state)
    st.plotly_chart(charts.lines(status, ["battery %"], "Battery remaining", "%", marks), width="stretch", key="p_battery")
    st.plotly_chart(charts.lines(status, ["voltage V", "current A"], "Voltage and current", "", marks), width="stretch", key="p_power")
    st.plotly_chart(charts.lines(attitude, ["roll deg", "pitch deg"], "Attitude", "deg", marks), width="stretch", key="p_attitude")
    st.plotly_chart(charts.lines(vibration, list("xyz"), "Vibration", "m/s²", marks), width="stretch", key="p_vibration")


def history(state, history_path) -> None:
    entries = memory.load(history_path)
    if not entries:
        st.info("No flights stored yet.")
        return
    base = state["history"]["baselines"]
    entry = state["history_entry"]
    if base:
        rows = [{"metric": k, "this flight": entry.get(k), "your usual": round(v["mean"], 2), "± std": round(v["std"], 2),
                 "flights": v["n"]} for k, v in base.items()]
        st.markdown("**This flight against your baseline** (flagged beyond 2 standard deviations)")
        flagged = {w["metric"] for w in state["history"]["worse_than_usual"]}
        st.dataframe(pd.DataFrame(rows).style.apply(
            lambda r: ["background-color: #f6d5d5" if r["metric"] in flagged else ""] * len(r), axis=1),
            hide_index=True, width="stretch")
    else:
        st.info(f"Baselines need 3 earlier flights; {state['history']['flights']} stored before this one.")
    frame = pd.DataFrame([e.model_dump() for e in entries])
    left, right = st.columns(2)
    for k, (column, title) in enumerate((("health_score", "Health score"), ("xtrack_max_m", "Max cross-track (m)"),
                                         ("battery_mah_per_km", "Battery use (mAh/km)"), ("link_uptime_pct", "Link uptime (%)"))):
        (left if k % 2 == 0 else right).plotly_chart(charts.trend(frame, column, title, state["run_id"]),
                                                     width="stretch", key=f"trend_{column}")
    effective = state["history"]["fix_effectiveness"]
    if effective:
        st.markdown("**What worked before** (re-flown missions against their originals)")
        rows = [{"run": f["run_id"], "fixes": f["parent_run"], "edits": "; ".join(f["edits"]),
                 **{k: f"{v['before']} → {v['after']}" + (" ✓" if v["improved"] else "") for k, v in f["changes"].items()}}
                for f in effective]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if state["history"]["recurring"]:
        st.warning("Recurring issues (3 of the last 5 flights): " + ", ".join(state["history"]["recurring"]))


def agents(state) -> None:
    run = state["agents"]
    st.markdown(f"**Backend:** {run['backend']} {run.get('model') or ''} · {run['seconds']} s · "
                f"plan from **{run['plan']['source']}**" + (f" (LLM plan failed: {run['plan_error']})" if run["plan_error"] else ""))
    st.markdown("**Orchestrator plan**")
    st.dataframe(pd.DataFrame(run["plan"]["plan"]), hide_index=True, width="stretch")
    with st.expander("Manifest the plan was made from"):
        st.json(run["manifest"])
    v = run["verification"]
    st.markdown(f"**Verifier:** {v['rejected']} of {v['claims']} claims rejected "
                f"({100 * v['grounding_rate']:.0f} %); re-runs: {', '.join(r['agent'] for r in v['reruns']) or 'none'}")
    verdicts = pd.DataFrame(v["verdicts"])
    if not verdicts.empty:
        st.dataframe(verdicts.sort_values("status", ascending=False), hide_index=True, width="stretch")
    for name, result in run["agents"].items():
        with st.expander(f"{name} · {result['source']} · {result['seconds']} s"):
            if result["errors"]:
                st.caption("Errors before falling back: " + " | ".join(result["errors"]))
            st.json(result["output"])


def ask_tab(state, backend) -> None:
    key = f"chat_{state['run_id']}"
    history = st.session_state.setdefault(key, [])
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["text"] if turn["role"] == "assistant" and turn.get("trusted") else plain(turn["text"]))
    question = st.chat_input("Ask about this flight, e.g. why did the link drop?")
    if question:
        reply = ask.answer(question, state, backend)
        cites = f"\n\n_Sources: {plain(', '.join(reply['citations']))}_" if reply["citations"] else ""
        note = f"\n\n_{plain(reply['note'])}; answered from the approved results instead._" if reply["note"] else ""
        history += [{"role": "user", "text": question},
                    {"role": "assistant", "text": plain(reply["answer"]) + cites + note, "trusted": True}]
        st.rerun()

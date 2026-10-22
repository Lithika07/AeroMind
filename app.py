"""AeroMind dashboard.

    streamlit run app.py

Open a saved (cached) run, or upload a flight's files and analyse it. Saved runs replay from
outputs/<run_id>/state.json, so the dashboard works without network or an LLM.
"""
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import pipeline  # noqa: E402
from agents import llm  # noqa: E402
from dashboard import data, detail_tabs, summary_tab  # noqa: E402
from tools.ingest import IngestError  # noqa: E402

UPLOADS = pipeline.OUTPUTS / "_uploads"
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_UPLOAD_MB = 200
TABS = ["Summary", "Track", "Telemetry", "Anomalies", "Power & attitude", "History", "Agents", "Ask"]


@st.cache_resource(show_spinner=False)
def backend_for(choice: str):
    os.environ["AEROMIND_LLM"] = "" if choice == "auto" else choice
    return llm.get_backend()


@st.cache_resource(show_spinner="Reading the flight logs…", max_entries=8)
def flight_for(run_id: str, tlogs: tuple, mission: str):
    return data.load_flight({"tlogs": list(tlogs), "mission": mission})


def save_upload(folder: Path, upload, allowed: tuple) -> Path:
    name = Path(upload.name).name
    if not name.lower().endswith(allowed):
        raise IngestError(f"{name}: expected {' or '.join(allowed)}")
    if upload.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise IngestError(f"{name} is larger than {MAX_UPLOAD_MB} MB")
    path = folder / re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    path.write_bytes(upload.getbuffer())
    return path


def analyse_uploads(run_id, tlogs, mission, params, notes, backend) -> str:
    if not RUN_ID.match(run_id):
        raise IngestError("run name: letters, digits, - and _ only (max 40)")
    if not tlogs:
        raise IngestError("upload at least one .tlog file")
    folder = UPLOADS / run_id
    folder.mkdir(parents=True, exist_ok=True)
    tlog_paths = [save_upload(folder, f, (".tlog",)) for f in tlogs]
    mission_path = save_upload(folder, mission, (".waypoints", ".txt")) if mission else None
    params_path = save_upload(folder, params, (".param", ".parm")) if params else None
    pipeline.analyse_flight(run_id, tlog_paths, mission_path, params_path, notes or None, backend=backend)
    return run_id


def sidebar():
    st.sidebar.title("AeroMind")
    choice = st.sidebar.selectbox("Agents' LLM", ("auto", "anthropic", "ollama", "none"),
                                  help="auto: Claude if ANTHROPIC_API_KEY is set, else local Ollama, else rules only")
    backend = backend_for(choice)
    st.sidebar.caption(f"Using: {getattr(backend, 'name', 'rules only')} {getattr(backend, 'model', '') or ''}")
    runs = data.saved_runs(pipeline.OUTPUTS)
    with st.sidebar.form("analyse"):
        st.markdown("**Analyse a new flight**")
        tlogs = st.file_uploader("Telemetry log(s) .tlog", type=["tlog"], accept_multiple_files=True)
        mission = st.file_uploader("Mission .waypoints (recommended)", type=["waypoints", "txt"])
        params = st.file_uploader("Parameters .param (optional)", type=["param", "parm"])
        notes = st.text_area("Pilot notes (optional)", placeholder="felt it drifting on leg 3", max_chars=2000)
        run_id = st.text_input("Run name", value=f"upload_{len(runs) + 1}")
        submitted = st.form_submit_button("Analyse", type="primary", width="stretch")
    if submitted:
        try:
            with st.spinner("Computing metrics and running the agents…"):
                st.session_state["run"] = analyse_uploads(run_id, tlogs, mission, params, notes, backend)
            st.rerun()
        except (IngestError, ValueError, OSError) as error:
            st.sidebar.error(str(error))
    if runs:
        current = st.session_state.get("run", runs[0])
        st.session_state["run"] = st.sidebar.selectbox("Saved runs (use cached run)", runs,
                                                       index=runs.index(current) if current in runs else 0)
    return backend


def main() -> None:
    st.set_page_config(page_title="AeroMind", page_icon="🛩️", layout="wide")
    backend = sidebar()
    run_id = st.session_state.get("run")
    if not run_id:
        st.title("AeroMind")
        st.info("Upload a flight's files in the sidebar, or analyse the demo flights first: "
                "`python3 run.py --batch data/`")
        return
    state = data.load_state(pipeline.OUTPUTS, run_id)
    sources = state["sources"]
    flight = flight_for(run_id, tuple(sources["tlogs"]), sources.get("mission") or "")
    st.title(f"Flight {run_id}" + (f" · scenario {state['scenario']}" if state.get("scenario") else ""))
    if state.get("notes"):
        st.caption(f"Pilot notes: {state['notes']}")
    tabs = st.tabs(TABS)
    out_dir = pipeline.OUTPUTS / run_id
    with tabs[0]:
        summary_tab.render(state, flight, out_dir)
    with tabs[1]:
        detail_tabs.track(state, flight)
    with tabs[2]:
        detail_tabs.telemetry(state, flight)
    with tabs[3]:
        detail_tabs.anomalies(state, flight)
    with tabs[4]:
        detail_tabs.power_attitude(state, flight)
    with tabs[5]:
        detail_tabs.history(state, pipeline.HISTORY)
    with tabs[6]:
        detail_tabs.agents(state)
    with tabs[7]:
        detail_tabs.ask_tab(state, backend)


main()

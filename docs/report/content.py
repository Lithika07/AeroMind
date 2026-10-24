"""The text of the AeroMind project report. Numbers are read from the project's own outputs."""
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ASSETS = HERE / "assets"
CROPS = ASSETS / "crops"
RUNS = ("s0", "s1", "s2", "s3", "s4", "s1_fixed", "s2_fixed", "s4_fixed")
SIDEBAR_PX = 300
#: where the local LLM ran for the analyses in outputs/ (the timing figures depend on it)
INFERENCE_DEVICE = "the laptop's CPU (AMD Ryzen 5 7535HS)"
BACKGROUND = (14, 17, 23)


# -- data --------------------------------------------------------------------------------------------

def states() -> dict:
    return {r: json.loads((ROOT / "outputs" / r / "state.json").read_text()) for r in RUNS
            if (ROOT / "outputs" / r / "state.json").exists()}


def median_seconds(s: dict) -> float:
    times = sorted(st["seconds_total"] for st in s.values())
    return times[len(times) // 2]


def llm_share(s: dict) -> tuple:
    llm = sum(1 for st in s.values() for a in st["agents"]["agents"].values() if a["source"] == "llm")
    other = sum(1 for st in s.values() for a in st["agents"]["agents"].values() if a["source"] == "fallback")
    return llm, llm + other


def results_rows() -> list:
    """The success-metric rows of docs/RESULTS.md, as produced by `run.py --results`."""
    rows, inside = [], False
    for line in (ROOT / "docs" / "RESULTS.md").read_text().splitlines():
        if line.startswith("| metric"):
            inside = True
            continue
        if inside and line.startswith("|---"):
            continue
        if inside and line.startswith("|"):
            rows.append([c.strip() for c in line.strip("|").split("|")])
        elif inside:
            break
    return rows


def excerpt(path: str, start: str, count: int, skip_doc: bool = True) -> str:
    """`count` lines of a source file from the first line starting with `start` (stripped)."""
    lines = (ROOT / path).read_text().splitlines()
    first = next(k for k, line in enumerate(lines) if line.strip().startswith(start))
    chunk = lines[first:first + count]
    indent = min(len(l) - len(l.lstrip()) for l in chunk if l.strip())
    return "\n".join(l[indent:] for l in chunk)


def crop(name: str, keep_sidebar: bool = False) -> Path:
    """The screenshot without the sidebar and the empty space below the content."""
    CROPS.mkdir(parents=True, exist_ok=True)
    image = Image.open(ASSETS / name).convert("RGB")
    left = 0 if keep_sidebar else SIDEBAR_PX + 50
    width, height = image.size
    bottom = height
    pixels = image.load()
    for y in range(height - 1, 0, -4):
        row = [pixels[x, y] for x in range(left + 20, width - 20, 23)]
        if any(sum(abs(a - b) for a, b in zip(p, BACKGROUND)) > 30 for p in row):
            bottom = min(height, y + 30)
            break
    out = CROPS / name
    image.crop((left, 70, width - 40, bottom)).save(out)
    return out


# -- the report ------------------------------------------------------------------------------------------

def write(r) -> None:
    import chapters
    chapters.write(r, states(), front, references)


def front(r, s) -> None:
    r.h1("ACKNOWLEDGEMENT", numbered=False)
    r.p("We thank our faculty guide for the direction, feedback and patience given throughout this mini project, and "
        "the Department of Computer Science & Information Technology, Unitedworld Institute of Technology, Karnavati "
        "University, for including Agentic AI in the curriculum and for the laboratory and computing facilities that "
        "made the work possible.")
    r.p("The simulation work builds on the disaster-zone world and the Hexa-X airframe our team developed for the Smart "
        "India Hackathon 2026 (the Aero Sense project), and on open-source software from the ArduPilot, Gazebo and "
        "Python communities: ArduPilot SITL, MAVProxy and pymavlink, Gazebo Harmonic, Streamlit, Plotly, pandas, "
        "Pydantic and Ollama. We acknowledge the authors of the third-party simulation models listed in the "
        "references.")
    r.p("Finally, we thank every team member for their contribution to the design, implementation, testing and "
        "documentation of AeroMind.")

    r.h1("ABSTRACT", numbered=False)
    r.p("After a drone flight, the information needed to understand what happened is scattered across a telemetry log, "
        "a mission file, a parameter file and the pilot's memory, and reading it takes expertise. Most operators "
        "therefore never learn why a flight drifted, ran its battery low or lost its telemetry link, and repeat the "
        "same mistakes. This project presents **AeroMind**, a multi-agent Agentic AI system that analyses the files "
        "of one ArduPilot flight and produces a one-page verdict, a phase-by-phase story, a telemetry-link timeline, "
        "root causes, a next-mission risk score and a corrected mission file.")
    r.p("Deterministic Python tools convert MAVLink logs into verified metrics with Good/Caution/Bad statuses. An "
        "orchestrator builds a manifest, obtains a plan from a large language model (LLM), checks the plan against "
        "rules, and runs five specialist agents (Flight Summary, Telemetry Link, Diagnosis, Risk and Advisor) on a "
        "shared state. A deterministic Verifier rejects any claim not supported by the data and triggers one "
        "self-correction round. A flight history provides long-term memory: personal baselines, battery prediction "
        "and recurring issues. The system is built in Python with Pydantic, Streamlit and Plotly, and runs with "
        "Claude through the Anthropic API or a local Qwen2.5-3B model through Ollama.")
    xt = {k: s[k]["metrics"]["tracking"]["xtrack_max_m"] for k in ("s1", "s1_fixed")}
    r.p("Eight flights were flown in ArduPilot SITL in a Gazebo disaster world with injected faults and known ground "
        "truth. AeroMind's agents detected all four injected faults with the correct root cause, located both telemetry "
        "dropouts within 0.1 s of the truth, raised no false alarm on the baseline flight and ranked next-mission risk "
        "correctly. The mission they corrected for the undersized-battery scenario raised the battery at landing from "
        f"14 % to 25 %, and the speed fix reduced the wind-scenario cross-track error from {xt['s1']} m to "
        f"{xt['s1_fixed']} m. The work shows that LLM agents paired with deterministic verification produce useful, "
        "grounded flight analysis even with a small model running locally.")

    r.contents()
    r.lists()


def references(r) -> None:
    r.h1("REFERENCES", numbered=False)
    refs = [
        "S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan and Y. Cao, “ReAct: Synergizing Reasoning and Acting "
        "in Language Models,” in Proc. International Conference on Learning Representations (ICLR), 2023.",
        "Q. Wu, G. Bansal, J. Zhang, Y. Wu, B. Li, E. Zhu, L. Jiang, X. Zhang, S. Zhang, J. Liu, A. H. Awadallah, "
        "R. W. White, D. Burger and C. Wang, “AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent "
        "Conversation,” arXiv:2308.08155, 2023.",
        "S. Hong et al., “MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework,” in Proc. ICLR, 2024.",
        "N. Shinn, F. Cassano, A. Gopinath, K. Narasimhan and S. Yao, “Reflexion: Language Agents with Verbal "
        "Reinforcement Learning,” in Advances in Neural Information Processing Systems (NeurIPS), 2023.",
        "A. Madaan et al., “Self-Refine: Iterative Refinement with Self-Feedback,” in Advances in NeurIPS, 2023.",
        "Z. Ji et al., “Survey of Hallucination in Natural Language Generation,” ACM Computing Surveys, vol. 55, no. 12, "
        "2023.",
        "A. Koubâa, A. Allouch, M. Alajlan, Y. Javed, A. Belghith and M. Khalgui, “Micro Air Vehicle Link (MAVLink) in a "
        "Nutshell: A Survey,” IEEE Access, vol. 7, pp. 87658–87680, 2019.",
        "ArduPilot Dev Team, “ArduPilot Documentation: Copter, SITL, MAVProxy and Log Analysis,” ardupilot.org, 2026.",
        "ArduPilot Dev Team, “Mission Planner Documentation,” ardupilot.org/planner, 2026.",
        "ArduPilot, “UAV Log Viewer,” plot.ardupilot.org, 2026.",
        "L. Wang et al., “A Survey on Large Language Model based Autonomous Agents,” Frontiers of Computer Science, vol. "
        "18, no. 6, 2024.",
        "PX4 Autopilot, “Flight Review and Log Analysis,” docs.px4.io, 2026.",
        "Qwen Team, “Qwen2.5 Technical Report,” arXiv:2412.15115, 2024.",
        "Anthropic, “Claude API Documentation: Messages and Structured Outputs,” docs.anthropic.com, 2026.",
        "Ollama, “Ollama Documentation and API,” ollama.com and github.com/ollama/ollama, 2026.",
        "ArduPilot, “pymavlink” and “MAVProxy,” github.com/ArduPilot, 2026.",
        "Ministry of Civil Aviation, Government of India, “The Drone Rules, 2021,” Gazette of India, 2021.",
        "Open Robotics, “Gazebo Harmonic Documentation,” gazebosim.org, 2026.",
        "Pydantic, “Pydantic Documentation (v2),” docs.pydantic.dev, 2026.",
        "Snowflake Inc., “Streamlit Documentation,” docs.streamlit.io, 2026.",
        "Plotly Technologies Inc., “Plotly Python Graphing Library,” plotly.com/python, 2026.",
        "The pandas development team, “pandas,” pandas.pydata.org, 2026; Pallets, “Jinja,” jinja.palletsprojects.com, 2026.",
        "OpenStreetMap contributors, “OpenStreetMap,” openstreetmap.org (map tiles in the Track tab), 2026.",
        "Simulation assets: Aero Sense disaster world and Hexa-X airframe (the team's Smart India Hackathon 2026 project); "
        "tdf_gazebo models (MIT licence); darpa_subt_worlds models (MIT licence); ardupilot_gazebo plugin and meshes "
        "(LGPL-3.0).",
    ]
    for k, ref in enumerate(refs, start=1):
        para = r.p(f"[{k}] {ref}")
        para.paragraph_format.left_indent = docx_inches(0.4)
        para.paragraph_format.first_line_indent = docx_inches(-0.4)


def docx_inches(value):
    from docx.shared import Inches
    return Inches(value)



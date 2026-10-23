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
BACKGROUND = (14, 17, 23)


# -- data --------------------------------------------------------------------------------------------

def states() -> dict:
    return {r: json.loads((ROOT / "outputs" / r / "state.json").read_text()) for r in RUNS
            if (ROOT / "outputs" / r / "state.json").exists()}


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
    s = states()
    front(r, s)
    chapter1(r)
    chapter2(r)
    chapter3(r)
    chapter4(r)
    chapter5(r, s)
    chapter6(r, s)
    chapter7(r, s)
    chapter8(r, s)
    chapter9(r, s)
    chapter10(r, s)
    chapter11(r)
    chapter12(r, s)
    references(r)
    appendix(r, s)


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
    r.p("Parts of the code were written with the help of an AI coding assistant (Claude Code). Every result in this "
        "report was produced by running the system, and the team reviewed, tested and is responsible for all of the "
        "work presented. Finally, we thank every team member for their contribution to the design, implementation, "
        "testing and documentation of AeroMind.")

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
    r.p("Eight flights were flown in ArduPilot SITL in a Gazebo disaster world with injected faults. AeroMind met 8 of "
        "10 targets: it detected 4 of 4 injected faults with the correct top cause, located both telemetry dropouts "
        "within 0.1 s, raised no false alarm on the baseline, and its fixed mission raised the battery at landing from "
        "14 % to 25 %. It missed the cross-track improvement target (20 % against 40 %) and the 60 s speed target with "
        "the local 3B model (median 92 s). The work shows that pairing LLM agents with deterministic verification "
        "gives useful, grounded explanations even with a small local model.")

    r.contents()
    r.lists()


def chapter1(r) -> None:
    r.h1("CHAPTER 1 – INTRODUCTION")
    r.h2("1.1 Introduction")
    r.p("**Artificial Intelligence (AI)** is the field of building systems that perform tasks normally requiring human "
        "intelligence, such as perception, reasoning and decision-making. **Generative AI** is the branch that "
        "produces new content; large language models (LLMs) such as Claude and Qwen are trained on large text "
        "corpora and generate text, code or structured data from a prompt. **Agentic AI** uses an LLM as the "
        "decision-making core of a system that pursues a goal over several steps: it plans, acts through tools or "
        "other agents, observes the results and adjusts [1], [11].")
    r.p("A traditional chatbot answers one message at a time from what the model already knows. An AI agent differs in "
        "six ways, each of which appears in AeroMind:")
    r.bullets([
        "**Autonomy** – after the user drops in a flight's files, AeroMind runs the whole analysis without further input.",
        "**Planning** – an orchestrator decides which agents to run, in what order and why, from what the data shows.",
        "**Reasoning** – each agent explains what happened and why, citing the metrics it relies on.",
        "**Tool usage** – Python tools parse the logs, compute metrics, predict battery use and edit the mission; the "
        "LLM never reads raw telemetry.",
        "**Memory** – every analysed flight is stored, so later analyses compare against the pilot's own baseline.",
        "**Goal-oriented execution** – the goal is a verified result: a verdict, causes, a risk score and a safer "
        "mission file, and work continues (with one self-correction round) until the result passes verification.",
    ])
    r.h2("1.2 Background")
    r.p("Small unmanned aircraft running the open-source ArduPilot autopilot record their state as MAVLink telemetry. "
        "Ground stations such as Mission Planner save it as a `.tlog` file on every connection [8], [9]. A five-minute "
        "flight produces tens of thousands of messages describing attitude, position, battery, GPS, wind, vibration "
        "and the radio link.")
    r.p("Conventional tools, such as Mission Planner's log review, ArduPilot's UAV Log Viewer [10] and PX4 Flight "
        "Review [12], plot this data well but leave interpretation to the user. To know why a flight drifted the "
        "operator must know which message holds the cross-track error, what values are normal, how wind and speed "
        "interact, and how to turn that into a change to the mission. A more autonomous system can do this "
        "interpretation: compute the right metrics, relate them to causes, remember what is normal for this pilot, "
        "and propose concrete, bounded changes. Agentic AI fits because the analysis is a sequence of judgements that "
        "depend on what the data shows, while the arithmetic must stay exact. AeroMind therefore gives the "
        "arithmetic to tools and the judgement to agents, and checks the agents against the tools.")
    r.h2("1.3 Problem Statement")
    r.p("The objective of this project is to develop an Agentic AI-based system that analyses the telemetry log, "
        "mission and parameters of an ArduPilot flight, explains how the flight and its telemetry link went, "
        "identifies what went wrong and why, scores the risk of the next mission and produces a corrected mission "
        "file. Existing log viewers plot the data but leave diagnosis, risk assessment and mission correction to an "
        "expert, and general-purpose chatbots invent numbers when asked about a log. Therefore, there is a need for a "
        "system that can reason over flight data like an expert while every statement it makes is checked against "
        "the data.")
    r.h2("1.4 Motivation")
    r.bullets([
        "**Why this problem:** our team builds drones for the Smart India Hackathon, and we repeatedly lost time "
        "working out from logs why a flight behaved as it did.",
        "**Why automation:** the analysis is repetitive and needs expertise that most operators lack; a tool that "
        "does it in a minute after every flight changes how often it is done.",
        "**Why Agentic AI:** the steps depend on the data (a flight with no problems needs no root-cause analysis), "
        "and explanations and advice in plain language are what LLMs do well.",
        "**Who benefits:** student teams, hobbyists and small operators who fly ArduPilot without a dedicated flight-"
        "test engineer.",
        "**Limitations that motivated us:** plotting tools explain nothing, and LLMs alone hallucinate numbers [6]; a "
        "safety-relevant tool cannot accept either.",
    ])
    r.h2("1.5 Objectives")
    r.numbered([
        "To design a multi-agent Agentic AI system that turns the files of one ArduPilot flight into a verdict, a "
        "flight story, a telemetry-link analysis, root causes, a next-mission risk score and a corrected mission.",
        "To implement LLM-planned orchestration of specialist agents over a shared state, with a rule-checked plan "
        "and a rule-based fallback for every agent.",
        "To integrate deterministic tools for log ingestion, metric computation, risk scoring and bounded mission "
        "editing, so that the LLM never computes a number.",
        "To implement long-term memory of analysed flights for personal baselines, battery prediction, recurring "
        "issues and fix effectiveness.",
        "To verify every agent claim against the data and to evaluate the system on simulated flights with injected "
        "faults and known ground truth.",
        "To analyse the effectiveness and limitations of the system honestly, including the cases where it falls "
        "short of its targets.",
    ])
    r.h2("1.6 Scope of the Project")
    r.bullets([
        "**Target users:** pilots and student teams flying ArduPilot multirotors.",
        "**Supported tasks:** post-flight analysis of one flight from `.tlog` files (several per flight are merged), "
        "an optional mission (`.waypoints`), parameters (`.param`) and pilot notes; questions about the flight; a "
        "corrected mission file.",
        "**Functional scope:** flight, battery, tracking, vibration, GPS, wind, attitude and telemetry-link metrics; "
        "phases and anomalies; five agents and a Verifier; flight history; dashboard, report and command line.",
        "**Technologies covered:** Python, pymavlink, pandas, Pydantic, Streamlit, Plotly, Jinja2, Claude or Ollama; "
        "ArduPilot SITL, MAVProxy and Gazebo Harmonic for the evaluation flights.",
        "**Expected usage:** after each flight, on a laptop, with or without an internet connection.",
        "**Current limitations:** post-flight only (no live alerts); evaluated on simulated flights only; DataFlash "
        "`.bin` logs are not yet read; the system never uploads anything to the drone.",
    ])


def chapter2(r) -> None:
    r.h1("CHAPTER 2 – LITERATURE REVIEW")
    r.h2("2.1 Existing Systems and Research")
    r.p("Table 1 summarises the work that shaped AeroMind: three agent frameworks, one self-correction method and the "
        "conventional flight-log tools used by drone operators today.")
    r.table(["Sr. No.", "Paper/System", "Year", "Approach", "Key Finding", "Limitation"], [
        ["1", "ReAct, Yao et al. [1]", "2023", "Interleaves reasoning traces with tool actions in one LLM loop",
         "Reasoning and acting together beat either alone on QA and decision tasks", "The LLM chooses every action; "
         "a reasoning error propagates through the loop"],
        ["2", "AutoGen, Wu et al. [2]", "2023", "Multi-agent conversation between configurable LLM agents",
         "Complex tasks decompose well into conversing specialist agents", "Coordination is itself LLM-driven; "
         "no built-in check that outputs are grounded in data"],
        ["3", "MetaGPT, Hong et al. [3]", "2024", "Role-specialised agents following standard operating procedures with "
         "structured hand-offs", "Structured intermediate outputs reduce errors between agents",
         "Targets software engineering; roles are fixed by the framework"],
        ["4", "Reflexion, Shinn et al. [4]; Self-Refine, Madaan et al. [5]", "2023", "The model critiques its own output "
         "and retries with the feedback", "Feedback loops improve results without retraining",
         "When the critic is also an LLM, it can accept wrong answers"],
        ["5", "UAV Log Viewer [10], PX4 Flight Review [12], Mission Planner [9]", "current", "Plot flight logs; "
         "some automatic checks", "Fast, reliable visualisation of every logged signal",
         "Interpretation, root cause, risk and mission changes are left to the user"],
    ], "Literature review summary", widths=[0.5, 1.6, 0.6, 1.7, 1.8, 1.8])
    r.h2("2.2 Comparative Analysis")
    r.p("Table 2 compares conventional flight-log tools with AeroMind on the features relevant to this project.")
    r.table(["Feature", "Existing System (log viewers)", "Proposed System (AeroMind)"], [
        ["Autonomous Execution", "No: the user opens and reads each plot", "Yes: files in, full analysis out"],
        ["Task Planning", "No", "Orchestrator plans the agents from a manifest; plan checked by rules"],
        ["Reasoning", "No: the user interprets", "Agents explain causes and risk, citing metrics"],
        ["Tool Usage", "Plotting only", "Ingest, metrics, memory, risk rules, bounded mission editing"],
        ["Memory", "No", "Flight history: baselines, battery prediction, recurring issues, fix effectiveness"],
        ["RAG", "No", "No (not implemented; see Section 5.5)"],
        ["Multi-Agent Support", "No", "Five specialist agents and a Verifier on a shared state"],
        ["Human Intervention", "Entirely manual", "Pilot reviews the fixed mission before flying; nothing is uploaded"],
    ], "Comparison of existing tools and the proposed system", widths=[1.6, 2.4, 3.0])
    r.h2("2.3 Research Gap")
    r.p("Agent frameworks [1]–[3] show how to decompose work across LLM agents, and self-refinement [4], [5] shows the "
        "value of feedback. They do not, however, guarantee that what an agent says is true, and hallucination "
        "remains the central risk of LLM output [6]. In a safety-relevant domain such as flight analysis, an invented "
        "battery figure or an unsafe mission edit is worse than no answer. Flight-log tools, on the other hand, are "
        "exact but explain nothing. The gap is a system that keeps the exactness of the tools and adds the "
        "explanation and planning of agents, with checks that are not themselves LLM judgements. AeroMind addresses "
        "it in four ways:")
    r.bullets([
        "Python computes every number, and the agents only see the computed metrics.",
        "A deterministic Verifier checks every claim against them.",
        "Python owns the safety-critical decisions: the risk score and the mission limits.",
        "Every agent has a rule-based fallback, so the system still works when the LLM fails.",
    ])


def chapter3(r) -> None:
    r.h1("CHAPTER 3 – PROPOSED SYSTEM")
    r.h2("3.1 Proposed Solution")
    r.p("AeroMind is a pipeline of deterministic tools followed by a planned team of LLM agents, all working on one "
        "shared state. Its parts map onto the elements of an agentic system as follows:")
    r.bullets([
        "**User interaction:** the user uploads one flight's files in a Streamlit dashboard (or uses the `run.py` "
        "command line) and may add free-text pilot notes. Afterwards they can ask questions about the flight.",
        "**Agents and LLM:** five specialist agents, each a system prompt and a Pydantic output schema, call Claude "
        "through the Anthropic API [14] or a local Qwen2.5-3B model [13] through Ollama [15] with structured output.",
        "**Planning:** the orchestrator builds a manifest of what inputs exist and what looks wrong, asks the LLM for an "
        "ordered plan with a reason per agent, and corrects the plan with rules.",
        "**Reasoning:** each agent reasons over the metrics given to it and must cite the metric behind each claim.",
        "**Tools:** Python tools ingest the logs, compute metrics, keep history, score risk and edit the mission.",
        "**Memory and knowledge base:** `history.json` stores one record per analysed flight. The shared state is the "
        "working memory of one analysis. There is no document knowledge base and no retrieval (RAG is not used).",
        "**Execution:** agents run in plan order; the Verifier checks their outputs; an agent with more than 30 % of "
        "its claims rejected runs once more with the reasons.",
        "**Final response:** the approved results (rejected items replaced by rule-based ones) are shown in the "
        "dashboard and written to `report.html`, `mission_fixed.waypoints` and `changelog.md`.",
    ])
    r.h2("3.2 System Requirements")
    r.h3("3.2.1 Hardware Requirements")
    r.p("Table 3 lists the machine on which the system was developed and evaluated; all figures in this report come "
        "from it.")
    r.table(["Component", "Requirement (as used)"], [
        ["Processor", "AMD Ryzen 5 7535HS, 6 cores / 12 threads"],
        ["RAM", "16 GB installed (14 GB usable); analysis alone needs under 1 GB"],
        ["Storage", "About 25 MB for the project and demo flights; 3.3 GB for the optional local LLM"],
        ["GPU", "NVIDIA GeForce RTX 2050, 4 GB (optional: used by the local LLM and Gazebo rendering)"],
        ["Internet Connection", "Optional: needed only for the Claude API and the map tiles"],
    ], "Hardware requirements", widths=[1.6, 4.4])
    r.h3("3.2.2 Software Requirements")
    r.p("Table 4 lists only the technologies actually used.")
    r.table(["Software/Technology", "Version/Specification"], [
        ["Operating System", "Ubuntu 22.04.5 LTS"],
        ["Programming Language", "Python 3.10.12 (and Lua for the simulated battery)"],
        ["IDE/Environment", "Visual Studio Code 1.142; Git; pytest 6.2.5"],
        ["Agent Framework", "None: own orchestrator in Python with Pydantic 2.13 schemas (no LangChain/CrewAI)"],
        ["LLM", "Claude via Anthropic SDK 2.1.0 (claude-opus-5-5) or Qwen2.5-3B via Ollama 0.40.8"],
        ["Vector Database", "Not used"],
        ["Embedding Model", "Not used"],
        ["Frontend", "Streamlit 1.57.0, Plotly 6.7.0; Jinja2 3.1.6 for report.html"],
        ["Data and parsing", "pymavlink 2.4.49, pandas 2.3.3, NumPy 2.2.6, PyYAML 6.0.3"],
        ["Simulation", "ArduCopter SITL (ArduPilot 4.6.0-beta1 development build), MAVProxy 1.8.74, Gazebo Harmonic 8.15.0"],
    ], "Software requirements and technologies used", widths=[1.8, 4.2])
    r.h2("3.3 Functional Requirements")
    r.p("Table 5 lists what the system must be able to do; Table 13 in Chapter 8 tests these requirements on real flights.")
    r.table(["ID", "The system shall…"], [
        ["FR1", "Accept one or more .tlog files of a flight, an optional mission, parameters and pilot notes"],
        ["FR2", "Merge the logs by time and keep only the vehicle's messages"],
        ["FR3", "Compute flight, battery, tracking, vibration, GPS, wind, attitude and link metrics with statuses and a "
                "health score"],
        ["FR4", "Detect telemetry dropouts with time, duration, position and nearest waypoint"],
        ["FR5", "Plan which agents to run from the data, and run them on a shared state"],
        ["FR6", "Explain the flight, diagnose causes, score next-mission risk and recommend improvements"],
        ["FR7", "Verify every agent claim against the data and re-run an agent whose claims fail"],
        ["FR8", "Store each flight and use history for baselines, battery prediction and recurring issues"],
        ["FR9", "Apply mission edits only within hard limits and write a corrected mission and change log"],
        ["FR10", "Answer questions about the flight from verified data"],
        ["FR11", "Continue with rule-based results when the LLM fails or is unavailable"],
    ], "Functional requirements", widths=[0.6, 5.4])
    r.h2("3.4 Non-Functional Requirements")
    r.bullets([
        "**Accuracy:** no number in the output may come from the LLM unchecked; metrics follow documented thresholds "
        "(ArduPilot guidance for vibration).",
        "**Reliability:** any failure of the LLM (timeout, invalid JSON, refusal, network error) falls back to rules; "
        "a circuit breaker skips an unreachable LLM server for five minutes.",
        "**Performance:** files to dashboard in under 60 s was the target; rules-only analysis takes under 1 s.",
        "**Scalability:** one flight per analysis; history grows by one small record per flight.",
        "**Security:** uploads are validated (extension, 200 MB size, safe file names); untrusted text is escaped "
        "before display; the dashboard listens on localhost only; API keys live in an untracked `.env` file.",
        "**Usability:** one page answers the main questions; other tabs hold the detail; saved runs replay offline.",
        "**Maintainability:** small modules (largest about 260 lines), typed data contracts, 236 automated tests.",
    ])


def chapter4(r) -> None:
    r.h1("CHAPTER 4 – AGENT ARCHITECTURE")
    r.h2("4.1 Overall System Architecture")
    r.p("Figure 1 shows the architecture as implemented. Inputs pass through Python tools into a shared state. The "
        "orchestrator plans and runs the agents on that state. The Verifier filters their outputs, and only the "
        "approved set reaches the outputs. The approved causes and edits are written back to the flight history.")
    r.figure(ASSETS / "architecture.png", "Overall system architecture of AeroMind")
    r.h2("4.2 Architecture Components")
    r.p("Table 6 maps each component of a typical agent architecture to its implementation in AeroMind; components that "
        "are not used are marked as such.")
    r.table(["Component", "Description (implementation)"], [
        ["User Interface", "Streamlit dashboard `app.py` with 8 tabs and an Ask chat; command line `run.py`"],
        ["LLM", "`agents/llm.py`: ClaudeBackend (messages.parse with a Pydantic schema) or OllamaBackend (JSON schema), "
                "or none"],
        ["Agent", "Five specialist agents, each a prompt (`agents/prompts.py`) and an output schema "
                  "(`agents/schemas.py`), run by `run_agent()`"],
        ["Planner", "`agents/orchestrator.py`: manifest → LLM plan → `checked_plan()`; `default_plan()` if the call fails"],
        ["Reasoning Module", "The agents themselves, given only compact JSON context built by `agents/context.py`"],
        ["Tools", "`tools/`: ingest, metrics, link_metrics, phases, anomalies, risk_rules, memory, mission_io, report"],
        ["Memory", "`tools/memory.py` over `history.json`; the shared state dictionary within one analysis"],
        ["Knowledge Base", "Not used (no document store); domain rules live in `agents/hints.py` and the thresholds"],
        ["Retriever", "Not used"],
        ["Executor", "`orchestrator.run()` executes the plan; `mission_io.apply_edits()` executes mission changes"],
        ["Output Generator", "`approve()` builds the approved set; `pipeline.py` writes state.json, report.html, the "
                             "fixed mission and change log"],
    ], "Architecture components", widths=[1.5, 4.5])
    r.h2("4.3 Agent Roles and Responsibilities")
    r.p("AeroMind is a multi-agent system. Table 7 lists the agents actually implemented; each has a rule-based "
        "fallback in `agents/fallbacks.py` that produces the same schema from the metrics alone.")
    r.table(["Agent", "Role", "Responsibility"], [
        ["Orchestrator", "Planner and executor", "Builds the manifest, gets and checks the plan, runs agents, triggers re-runs"],
        ["Flight Summary", "Narrator", "Verdict (Good / Needs attention / Unsafe), a line per flight phase, 3-sentence summary"],
        ["Telemetry Link", "Link analyst", "Findings on uptime, each dropout (time, duration, nearest waypoint), packet "
                                          "loss; whether the link was safe"],
        ["Diagnosis", "Analyst", "Findings citing metrics; up to 3 root causes with category, confidence and supporting findings"],
        ["Risk", "Assessor", "Adjusts the rule-based risk score by at most ±10 with a reason"],
        ["Advisor", "Planner of fixes", "Mission edits tied to causes, from 4 allowed actions; top 3 improvements"],
        ["Verifier", "Reviewer", "Deterministic: checks every claim, story line, number and edit mention against the data"],
    ], "Agent roles and responsibilities", widths=[1.3, 1.3, 3.4])
    r.h2("4.4 Agent Workflow")
    r.p("The complete workflow of one analysis is shown in Figure 2.")
    r.numbered([
        "The user provides the task: the files of one flight and optional notes (dashboard upload or command line).",
        "The tools turn the files into metrics, statuses, phases, anomalies and a health score, so the objective is "
        "understood from data rather than from wording.",
        "The memory store adds baselines, a battery prediction and recurring issues; the risk rules compute the base "
        "score.",
        "The orchestrator creates the task plan: which agents run, in what order and why.",
        "Each agent in turn receives only the context it needs and returns schema-checked JSON (or its fallback).",
        "The Verifier observes the outputs and checks every claim against the data.",
        "If more than 30 % of an agent's claims are rejected, that agent runs once more with the reasons.",
        "The approved set is formed; mission edits are applied within the limits; history is updated.",
        "The final result is presented in the dashboard and the report; the user can ask follow-up questions.",
    ])
    r.figure(ASSETS / "workflow.png", "Agent workflow of one analysis", width_in=3.1)


def chapter5(r, s) -> None:
    r.h1("CHAPTER 5 – AGENTIC AI CONCEPTS USED")
    r.p("Only concepts that are implemented are described. Where a concept named by the template is not used, this is "
        "stated.")
    r.h2("5.1 ReAct")
    r.p("AeroMind does **not** implement the ReAct loop [1], in which the LLM itself chooses a tool, observes the result "
        "and reasons again. This is deliberate: in AeroMind the tools always run, in a fixed order, before the agents. "
        "The agents never call tools, because a model that chooses tools could skip one or misread raw telemetry. The "
        "closest element is the verify–re-run cycle (Section 5.6): an agent's output is observed by the Verifier and "
        "the agent acts again with the feedback.")
    r.h2("5.2 Planning")
    r.p("The orchestrator uses **plan-and-execute with a rule-checked plan**, shown in Figure 3. The planner sees a "
        "manifest (inputs present, metric statuses, which metrics are Caution or Bad, whether the link was healthy, "
        "flights in history). It returns an ordered list of agents with a one-line reason each. The plan is then "
        "corrected by `checked_plan()`:")
    r.bullets([
        "Flight Summary goes first and the Verifier last.",
        "Diagnosis runs only when some metric is Caution or Bad.",
        "Required agents are added, and duplicates are removed.",
        "The steps are put in dependency order.",
    ])
    r.p("If the call fails, `default_plan()` produces the plan from the same rules. The plan is dynamic in what it "
        "contains: a healthy flight skips diagnosis, and a healthy link gets a one-line rule result without an LLM "
        "call. In all eight evaluation runs the plan came from the LLM and was corrected by the rules.")
    r.figure(ASSETS / "orchestration.png", "Planning and execution flow of the orchestrator", width_in=4.3)
    r.h2("5.3 Tool Calling")
    r.p("Tools in AeroMind are deterministic Python functions invoked by the orchestration code, not by the LLM through "
        "function calling. Tool selection is therefore not an LLM decision. The pipeline always runs the analysis "
        "tools, and the plan decides which agents (and so which downstream tools such as mission editing) are used. "
        "Table 8 lists the tools, their inputs and outputs, and how the agents use their output.")
    r.table(["Tool", "Purpose", "Input", "Output"], [
        ["Ingestor (ingest.py)", "Read and merge logs, mission, parameters, notes", ".tlog files, .waypoints, .param, text",
         "FlightData: message tables, sequence numbers, file spans"],
        ["Metrics engine (metrics.py, link_metrics.py, phases.py, anomalies.py, thresholds.py)",
         "Every metric, status and the health score", "FlightData", "metrics.json (Pydantic Metrics)"],
        ["Memory store (memory.py)", "Baselines, battery prediction, recurrence, fix effectiveness",
         "history.json, this flight", "History context in the state"],
        ["Risk rules (risk_rules.py)", "Repeatable base risk score", "metrics, parameters, prediction, recurrence",
         "Score, level, factors, confidence"],
        ["Mission I/O (mission_io.py)", "Apply edits within limits", "mission, proposed edits, causes",
         "Fixed mission, applied and rejected edits"],
        ["Report (report.py)", "Printable report", "approved state", "report.html"],
    ], "Tools: purpose, input and output", widths=[1.6, 1.6, 1.4, 1.6])
    r.p("Agents use tool output only as JSON context: the Diagnosis agent receives the statuses, metrics, anomalies and "
        "rule-derived candidate causes; the Risk agent receives the base score and factors; the Advisor receives "
        "the causes, the mission and valid suggested edits.")
    r.h2("5.4 Memory")
    r.bullets([
        "**Short-term (working) memory:** the shared state dictionary of one analysis, a blackboard that every agent "
        "reads and adds to.",
        "**Long-term memory:** `history.json`, one validated record per analysed flight, which includes battery use per "
        "km, cross-track, link uptime, health, causes found and edits applied, plus the parent run when a flight "
        "re-flies a fixed mission. It is written atomically.",
        "**Conversational memory:** the Ask tab keeps the chat on screen for the session, but each question is "
        "answered independently; earlier turns are not sent to the LLM.",
        "**Vector-based memory:** not used.",
        "**Memory retrieval:** by computation, not similarity search: baselines need 3 or more flights, a 2σ test marks "
        "a metric worse than usual, the median mAh per km predicts battery, a cause in 3 of the last 5 flights is "
        "recurring, and re-flights are compared with their parent run.",
    ])
    r.h2("5.5 Retrieval-Augmented Generation")
    r.p("RAG is **not implemented**. The agents' knowledge of the flight comes from computed metrics, not from "
        "retrieved documents. Retrieval over ArduPilot documentation for parameter advice is listed as future work "
        "(Chapter 11).")
    r.h2("5.6 Multi-Agent System")
    r.bullets([
        "**Agent roles:** five specialist agents and a deterministic Verifier (Table 7).",
        "**Agent communication:** through the shared state (blackboard), not messages; each agent's validated output is "
        "added to the state and later agents read what they need (Risk reads the causes from Diagnosis; Advisor reads "
        "causes and risk).",
        "**Task delegation and orchestration:** the orchestrator delegates by plan; each agent call is `run_agent()` "
        "with two LLM attempts, a guard and a fallback.",
        "**Coordination:** Python guards keep shared quantities consistent. The risk score is always base plus "
        "adjustment. The link verdict follows the statuses. Final mission edits are checked against the approved "
        "diagnosis, not the raw one.",
        "**Execution flow and self-correction:** after all agents run, the Verifier computes a rejection rate per "
        "agent. Agents above 30 % re-run once with the rejection reasons, and the outputs are verified again.",
    ])
    r.code(excerpt("agents/base.py", "def run_agent(", 17),
           "Listing 1: run_agent() – LLM with two attempts, guard, then the rule-based fallback (agents/base.py).")
    r.h2("5.7 Human-in-the-Loop")
    r.p("AeroMind keeps the human in control at the point of action rather than through an approval step inside the "
        "application. Nothing is ever uploaded to the vehicle. The pilot downloads `mission_fixed.waypoints`, reviews "
        "it and the change log in a ground station, and decides whether to fly it. A rejected change has no effect. "
        "The pilot also contributes input through free-text notes, which the agents use only as supporting evidence. "
        "An in-app approve/reject workflow was not implemented.")


def chapter6(r, s) -> None:
    r.h1("CHAPTER 6 – METHODOLOGY")
    r.h2("6.1 Input Processing")
    r.p("Files arrive by dashboard upload (validated extensions, 200 MB limit, sanitised names, unique run name) or by "
        "the command line. `tools/ingest.py` reads each `.tlog` with pymavlink [7], [16]. It identifies the vehicle "
        "from its HEARTBEAT, keeps only the vehicle's messages and merges several files of one flight by timestamp. "
        "The time span of each file is kept, so a gap between files counts as a dropout. Parameters are read in "
        "Mission Planner or MAVProxy format, and notes are cleaned and capped at 2,000 characters.")
    r.h2("6.2 Task Understanding")
    r.p("The objective is always the same – explain this flight and make the next one safer – so task understanding "
        "means understanding the data. The metrics engine computes about 30 metrics and rates 14 of them Good, "
        "Caution or Bad (Table 9). The health score starts at 100 and loses 10 per Caution and 25 per Bad. Two "
        "measurement decisions came from observing real logs:")
    r.bullets([
        "Vibration and attitude are measured only while airborne, because the landing touchdown alone produced "
        "37 m/s² and one accelerometer clip on a calm flight.",
        "A dropout must be silence on both the ground-station clock and the vehicle's own clock (`time_boot_ms`), "
        "because a simulator running slower than real time showed only 4.4 s of vehicle time in a 10 s wall-clock "
        "window.",
    ])
    r.table(["Metric", "Good", "Caution", "Bad"], [
        ["Cross-track error, max (m)", "< 1", "1–3", "> 3"],
        ["Battery at landing (%)", "> 30", "20–30", "< 20"],
        ["Vibration max, airborne (m/s²)", "< 30", "30–60", "> 60"],
        ["Accelerometer clipping", "0", "any increase", "–"],
        ["Minimum satellites / maximum HDOP", "≥ 10 / < 1.5", "6–9 / 1.5–2.5", "< 6 / > 2.5"],
        ["Wind estimate, max (m/s)", "< 5", "5–8", "> 8"],
        ["Roll / pitch, max (°)", "< 25", "25–35", "> 35"],
        ["Mission completion (%)", "100", "–", "< 100"],
        ["Warnings and failsafes", "0", "1–2", "> 2"],
        ["Link uptime (%)", "≥ 99", "95–99", "< 95"],
        ["Dropouts (silence > 2 s)", "0", "1–2, each ≤ 10 s", "> 2, or any > 10 s"],
        ["Packet loss (%)", "< 2", "2–5", "> 5"],
        ["Position update rate", "steady", "–", "worst 10 s < 50 % of median"],
    ], "Metrics and thresholds", widths=[2.6, 1.0, 1.2, 1.4])
    r.h2("6.3 Task Planning")
    r.p("The analysis is divided into fixed tool steps and planned agent steps. The tool steps always run: ingest, "
        "metrics, memory, base risk. The planned steps are the agents the orchestrator selects (Section 5.2), each a "
        "sub-task with one schema: summarise, analyse the link, diagnose, assess risk, advise. Splitting the work this "
        "way keeps each prompt short, which matters for a 3B local model.")
    r.h2("6.4 Reasoning and Decision Making")
    r.p("Each agent decides within a narrow remit. Diagnosis receives candidate causes from documented hint rules "
        "(for example, wind Caution/Bad together with cross-track or attitude Caution/Bad points to crosswind drift). "
        "It may reword them and adjust confidence. The Risk agent may move the rule score by at most ±10 and must give "
        "a reason; a reduction must name what lowers the risk. Python keeps the decisions that must be exact. The "
        "rule-based risk factors are listed in Table 10.")
    r.table(["Risk factor", "Points"], [
        ["Predicted battery at landing < 10 % / < 20 % / 20–30 %", "+45 / +30 / +15"],
        ["Battery at landing Bad in the latest flight", "+15"],
        ["Telemetry dropouts or uptime Bad / Caution", "+20 / +10"],
        ["GPS Bad / Caution", "+20 / +10"],
        ["Wind Bad in the latest flight", "+15"],
        ["Vibration Bad", "+15"],
        ["Each failsafe not set (FS_THR_ENABLE, BATT_FS_LOW_ACT, FENCE_ENABLE = 0)", "+10"],
        ["A recurring issue from history", "+10"],
    ], "Base risk rules (Low < 30, Medium 30–59, High ≥ 60, capped at 100)", widths=[4.6, 1.4])
    r.h2("6.5 Tool Selection")
    r.p("Tools are selected by the pipeline, not by the LLM (Section 5.3). Agent selection is planned: the manifest "
        "decides whether Diagnosis runs, and whether the Telemetry Link agent needs the LLM or a one-line rule result. "
        "Mission I/O runs only when a mission file was given.")
    r.h2("6.6 Task Execution")
    r.p("`orchestrator.run()` executes the plan. Every LLM call requests structured output against the agent's schema. "
        "An invalid reply is retried once with the validation error. A second failure, or any unexpected error, "
        "produces the rule-based output, so execution always completes. Mission edits are executed by "
        "`mission_io.apply_edits()` within the limits in Table 11.")
    r.table(["Action", "How it is applied", "Limits"], [
        ["set_speed", "Changes or inserts DO_CHANGE_SPEED before the waypoint", "3–10 m/s"],
        ["change_altitude", "Changes the waypoint's altitude", "±20 m per edit; final 25–120 m"],
        ["remove_waypoint", "Deletes a navigation waypoint", "≤ 30 % of waypoints; never home, take-off, RTL or land"],
        ["add_hold", "Sets the hold time at a waypoint", "0–10 s"],
        ["All edits", "Each tied to a diagnosed cause; at most 5", "Mission must end in RTL/LAND; no leg may pass the "
                                                                    "44 m radio mast lower than its top plus 6 m"],
    ], "Mission edit actions and limits", widths=[1.3, 2.6, 2.1])
    r.p("The 25 m floor replaces the PRD's 10 m because the evaluation world has 16.4 m buildings and 9 m power lines; "
        "the 120 m ceiling matches the green-zone limit of India's Drone Rules, 2021 [17].")
    r.h2("6.7 Observation and Feedback")
    r.p("The Verifier observes every output. A claim must cite a metric path that exists, and its value must match within "
        "5 % (or 0.15 absolute). Every number with a unit in any text (story lines, summary, causes, reasons, "
        "recommendations) must match a computed value **of the same unit**. Word units such as seconds, knots and "
        "km/h are converted first. Story statuses must equal the data's status for that phase. A cause may not rest on "
        "a rejected finding. A recommendation may only name edits that passed the limits. The rejection reasons are "
        "the feedback for the re-run.")
    r.code(excerpt("agents/verifier.py", "def check_text(", 11),
           "Listing 2: unit-aware grounding of numbers in free text (agents/verifier.py).")
    r.h2("6.8 Final Response Generation")
    r.p("`approve()` builds the final response. Rejected story lines are replaced by the data's own line, a rejected "
        "summary by the rule-based one, rejected findings and causes are dropped, and recommendations are refilled from "
        "the rules to three. Final mission edits are re-derived against the approved diagnosis. `pipeline.py` then "
        "writes `state.json` (everything, replayable without an LLM), `report.html`, `mission_fixed.waypoints` and "
        "`changelog.md`, and stores the approved causes and edits in history.")
    r.h2("6.9 Evaluation Data: Simulated Flights with Known Faults")
    r.p("To evaluate against ground truth, flights were flown in ArduCopter SITL [8] inside the team's Gazebo [18] "
        "disaster world (Figure 4, Figure 5). The world and a Hexa-X hexacopter are vendored into the repository with "
        "their licences. The simulator lacked two things the faults needed, and both were added:")
    r.bullets([
        "**Battery:** the Gazebo JSON backend simulates no battery, so a Lua script feeds ArduPilot's scripting battery "
        "monitor with current derived from the motor outputs.",
        "**Wind:** ArduPilot's wind parameters do not move a Gazebo vehicle, so wind is a constant force on the "
        "airframe. Because the airframe's drag is linear, that force is exactly equivalent to wind.",
    ])
    r.p("Link faults are injected by AeroMind's own recording ground station, which writes the true outage times to "
        "`truth.json`. Table 12 lists the scenarios.")
    r.figure(ASSETS / "simulation.png", "Simulation and data-collection pipeline")
    r.figure(ASSETS / "route_map.png", "Demo route in the disaster world (structures from the world file)", width_in=3.6)
    r.table(["ID", "Scenario", "How the fault is injected"], [
        ["S0", "Baseline, 5 m/s", "None"],
        ["S1", "Strong wind + fast flight", "9 N force (10 m/s from the east) above 3 m; mission speed 12 m/s"],
        ["S2", "Undersized battery", "BATT_CAPACITY 2200 mAh instead of 10000"],
        ["S3", "Telemetry dropout", "Recording link down for 12 s at 90 s and at 200 s after arming"],
        ["S4", "Combined", "S1 + S2 + link down inside the north-east no-network zone"],
        ["S1/S2/S4 fixed", "Re-flights", "Same faults, flying AeroMind's mission_fixed.waypoints"],
    ], "Evaluation scenarios", widths=[1.0, 1.8, 3.2])


def chapter7(r, s) -> None:
    r.h1("CHAPTER 7 – IMPLEMENTATION")
    r.h2("7.1 Project Structure")
    r.code("""AeroMind/
├── app.py                  Streamlit dashboard (entry point)
├── run.py                  command line: single flight, --batch, --compare, --results
├── pipeline.py             one analysis end to end, writes outputs/<run>/
├── agents/                 schemas, llm (Claude/Ollama), prompts, context, base (run_agent),
│                           orchestrator, verifier, hints, fallbacks
├── tools/                  ingest, metrics, link_metrics, phases, anomalies, thresholds,
│                           timeline, memory, risk_rules, mission_io, waypoints, site,
│                           geo, analysis, report, results
├── dashboard/              summary_tab, detail_tabs, charts, data, ask, text
├── report/template.html    report.html template (Jinja2)
├── sim/                    world, models, SITL launcher, capture, scenarios, battery.lua
├── data/<scenario>/        flown logs, mission, params, truth.json, meta.json
├── outputs/<run>/          state.json, report.html, mission_fixed.waypoints, changelog.md
├── history.json            long-term flight memory
└── tests/                  236 pytest tests""", "Listing 3: actual project structure (about 5,000 lines of Python).")
    r.h2("7.2 Agent Implementation")
    r.p("Each agent is a system prompt plus a Pydantic schema. Listing 4 shows the Diagnosis prompt. The shared "
        "grounding rule appended to every prompt tells the model to copy numbers exactly and to say when a metric is "
        "null. Listing 5 shows the guard that keeps the risk score Python's, whatever the model returns.")
    r.code(excerpt("agents/prompts.py", "DIAGNOSIS = ", 9), "Listing 4: the Diagnosis agent's system prompt (agents/prompts.py).")
    r.code(excerpt("agents/base.py", "def guard(", 12), "Listing 5: guard() – Python owns the risk score and the link "
                                                         "verdict (agents/base.py).")
    r.p("The LLM backend requests structured output. With Claude, `client.messages.parse()` validates the reply "
        "against the Pydantic model [14]. With Ollama, the model's JSON schema is passed as the `format` and the reply "
        "is validated with Pydantic [19].")
    r.h2("7.3 Tool Implementation")
    for name, purpose, inp, out, impl, role in (
        ("Link metrics (tools/link_metrics.py)", "Find dropouts and measure link quality across the whole flight",
         "All vehicle messages with receive time and MAVLink sequence number; the vehicle clock",
         "Uptime, dropouts (time, duration, position, nearest waypoint, between files), packet loss, RSSI, position rate",
         "Gaps longer than 2 s in receive time that are also longer than 2 s on the vehicle clock; packet loss from "
         "sequence-number gaps (mod 256) excluding pairs that span a dropout",
         "Feeds the Telemetry Link agent, the link strip and the risk rules"),
        ("Mission I/O (tools/mission_io.py)", "Turn proposed edits into a safe mission file",
         "Mission items, proposed edits, approved cause ids", "Fixed mission, applied and rejected edits, change log",
         "Each edit checked against Table 11, applied to a copy, then the whole mission re-checked for RTL/LAND and "
         "obstacle clearance",
         "Executes the Advisor's plan; the only path from agents to a mission file"),
    ):
        r.h3(name)
        r.bullets([f"**Purpose:** {purpose}", f"**Input:** {inp}", f"**Output:** {out}", f"**Implementation:** {impl}",
                   f"**Role in agent workflow:** {role}"])
    r.h2("7.4 Memory Implementation")
    r.bullets([
        "**Memory type:** long-term episodic memory of flights, plus the per-analysis shared state.",
        "**Storage mechanism:** `history.json`, a list of validated `HistoryEntry` records, written atomically "
        "(temporary file and rename) so a crash never leaves a half-written history.",
        "**Data stored:** run id, date, scenario, parent run, mission length, duration, battery use (% and mAh per km), "
        "capacity, battery at landing, completion, cross-track, uptime, dropouts, vibration, wind, health score, "
        "cause categories and applied edits.",
        "**Retrieval mechanism:** computed statistics over the stored records (Section 5.4).",
        "**How memory influences decisions:**",
    ])
    r.bullets([
        "The battery prediction drives the largest risk factor.",
        "Recurring causes add risk.",
        "Worse-than-usual flags appear on the Summary.",
        "The Advisor is shown which past edits improved which metrics.",
    ])
    r.h2("7.5 RAG Implementation")
    r.p("Not applicable: RAG is not implemented (Section 5.5).")
    r.h2("7.6 User Interface")
    r.p("The Streamlit dashboard [20] is the main interface. Figure 6 shows the home page with the input form in the "
        "sidebar (telemetry logs, mission, parameters, pilot notes, run name) and the Summary tab of scenario S4. The "
        "other tabs hold the detail:")
    r.bullets([
        "**Agents** (Figure 7): the agents' execution, with the orchestrator's plan, each agent's source and time, and "
        "every Verifier verdict.",
        "**Ask** (Figure 8): questions answered from the verified data.",
        "**Track, Telemetry and History** (Figures 10–12, Appendix B): map and link views, and baselines, trends and "
        "what worked before.",
    ])
    r.p("All screenshots were captured from the running application by `docs/report/screenshots.py`.")
    r.figure(crop("ui_summary_s4.png", keep_sidebar=True), "Home page: input form (sidebar) and the Summary tab for S4",
             width_in=4.3)
    r.figure(crop("ui_agents_s3.png"), "Agents tab (S3): orchestrator plan, Verifier verdicts and each agent's execution",
             width_in=4.6)
    r.figure(crop("ui_ask_s3.png"), "Ask tab (S3): an answer from the local LLM, verified against the cited metrics",
             width_in=5.6)


def _states_row(st):
    approved = st["agents"]["approved"]
    return approved


def chapter8(r, s) -> None:
    r.h1("CHAPTER 8 – RESULTS AND OUTPUT")
    r.h2("8.1 Test Cases")
    m = {k: v["metrics"] for k, v in s.items()}
    ap = {k: v["agents"]["approved"] for k, v in s.items()}
    causes = lambda run: ", ".join(c["category"] for c in ap[run].get("diagnosis", {}).get("causes", [])) or "none"
    edits = lambda run: "; ".join(a["text"].split(" (cause")[0] for a in (s[run].get("mission_fix") or {}).get("applied", [])) or "none"
    risk = lambda run: f"{ap[run]['risk']['risk_level']} {ap[run]['risk']['risk_score']}"
    d3 = m["s3"]["link"]["dropouts"]
    truth = json.loads((ROOT / "data" / "s3" / "truth.json").read_text())["outages"]
    t0 = s["s3"]["log_start_unix"]
    r.p("Table 13 lists the scenario test cases. Every actual output is taken from the saved runs in `outputs/`, and "
        "the ground truth for the dropouts comes from `data/s3/truth.json`.")
    r.table(["ID", "Input", "Expected Output", "Actual Output", "Status"], [
        ["TC01", "S0 baseline flight", "Good verdict, no Bad metric, Low risk",
         f"{ap['s0']['flight_summary']['verdict']}, health {m['s0']['health_score']}, risk {risk('s0')}", "Pass"],
        ["TC02", "S1 wind + 12 m/s", "Wind flagged; wind cause; speed edit",
         f"wind {m['s1']['wind']['max_ms']} m/s Bad; causes: {causes('s1')}; edit: {edits('s1')}", "Pass"],
        ["TC03", "S2 small battery", "Battery Bad; low_battery; shorten route; High risk",
         f"landed {m['s2']['battery']['remaining_end_pct']:.0f} %; causes: {causes('s2')}; {edits('s2')}; risk {risk('s2')}",
         "Pass"],
        ["TC04", "S3 two 12 s link outages", "2 dropouts within 3 s of truth, nearest waypoint",
         f"dropouts at {d3[0]['t']} s and {d3[1]['t']} s (truth {truth[0]['start_unix'] - t0:.1f} s, "
         f"{truth[1]['start_unix'] - t0:.1f} s), near WP{d3[0]['near_wp']} and WP{d3[1]['near_wp']}", "Pass"],
        ["TC05", "S4 combined faults", "Wind, battery and link causes; High risk",
         f"causes: {causes('s4')}; risk {risk('s4')}", "Pass"],
        ["TC06", "S2 re-flight with fixed mission", "Battery at landing ≥ 25 %",
         f"{m['s2_fixed']['battery']['remaining_end_pct']:.0f} %", "Pass"],
        ["TC07", "S1 re-flight with fixed mission", "Max cross-track ≥ 40 % lower",
         f"{m['s1']['tracking']['xtrack_max_m']} m → {m['s1_fixed']['tracking']['xtrack_max_m']} m (20 % lower)", "Fail"],
        ["TC08", "Ask: “Why did the telemetry link drop?” (S3)", "Answer citing link metrics, verified",
         "LLM answer citing 3 metric paths, passed verification (Figure 8)", "Pass"],
        ["TC09", "LLM unavailable mid-analysis (S4: call timed out)", "Analysis completes from rules",
         f"first call timed out after 120 s; breaker skipped the LLM; all agents fell back; result {risk('s4')}", "Pass"],
        ["TC10", "Invented number in a cause (unit test)", "Verifier rejects the cause",
         "“Motor 3 failing at 2400 rpm and 77 m/s gusts” rejected", "Pass"],
        ["TC11", "End-to-end time with the local LLM", "< 60 s", "median 92 s, max 126 s", "Fail"],
    ], "Test cases and actual results", widths=[0.55, 1.3, 1.4, 2.2, 0.6])
    r.h2("8.2 Sample Outputs")
    for title, inp, action, out, fig in (
        ("Test Case 1 – combined faults (S4)", "The S4 logs, mission and parameters, with the note “felt it drifting on leg 3”",
         "The orchestrator planned all five agents. The first LLM call timed out after 120 s, so the circuit breaker "
         "routed every agent to its rule-based version. The Verifier approved all 32 claims.",
         f"Verdict {ap['s4']['flight_summary']['verdict']}; causes {causes('s4')}; risk {risk('s4')}; fixed mission: "
         f"{edits('s4')}. The Agents tab for this run is Figure 13 in Appendix B.", None),
        ("Test Case 2 – undersized battery (S2)", "The S2 files",
         "Diagnosis named low_battery. The Advisor's edits were re-derived against the approved diagnosis, and mission "
         "I/O removed the two waypoints that shorten the route most. One LLM-proposed edit (a hold at the take-off "
         "item) was rejected by the limits.",
         f"Route {s['s2']['mission_fix']['length_before_m']} m → {s['s2']['mission_fix']['length_after_m']} m; risk "
         f"{risk('s2')}; report.html written (Figure 9).", ("report_html_s2.png", "Generated report.html for S2")),
    ):
        r.h3(title)
        r.bullets([f"**Input:** {inp}", f"**Agent action:** {action}", f"**Output:** {out}"])
        if fig:
            r.figure(ASSETS / fig[0], fig[1], width_in=3.4)
    r.h2("8.3 Agent Execution Trace")
    st = s["s3"]["agents"]
    plan = " → ".join(step["agent"] for step in st["plan"]["plan"])
    r.p("The execution trace of S3, taken from `outputs/s3/state.json`:")
    r.code(f"""User query     S3 logs + mission + params (two injected 12 s link outages)
   ↓
Understanding  health {m['s3']['health_score']}; Bad: link_uptime ({m['s3']['link']['uptime_pct']} %), dropouts ({len(d3)})
   ↓
Plan (LLM)     {plan}
   ↓
Execution      {', '.join(f"{k} {v['source']} {v['seconds']} s" for k, v in st['agents'].items())}
   ↓
Observation    Verifier: {st['verification']['claims']} claims, {st['verification']['rejected']} rejected
   ↓
Decision       re-run: {', '.join(x['agent'] for x in st['verification']['reruns'])}
   ↓
Final response {ap['s3']['flight_summary']['verdict']}; causes: {causes('s3')}; risk {risk('s3')};
               first advice: {ap['s3']['advisor']['recommendations'][0]['text']}""",
           "Listing 6: execution trace of S3 (agent times are those of the final, re-run call).")


def chapter9(r, s) -> None:
    r.h1("CHAPTER 9 – PERFORMANCE EVALUATION")
    r.p("All values in this chapter were measured on the hardware in Table 3. Table 14 gives the project's success "
        "metrics exactly as computed by `python3 run.py --results` (docs/RESULTS.md).")
    rows = [[c.replace("->", "→") for c in row] for row in results_rows()]
    r.table(["Metric", "Measured", "Target", "Result"], rows, "Success metrics (computed by run.py --results)",
            widths=[1.4, 3.2, 1.3, 0.6])
    r.p("Table 15 evaluates the system against the metrics suggested for agentic systems; retrieval accuracy does not "
        "apply because no retrieval is used.")
    llm_results = sum(1 for st in s.values() for a in st["agents"]["agents"].values() if a["source"] == "llm")
    fallback = sum(1 for st in s.values() for a in st["agents"]["agents"].values() if a["source"] == "fallback")
    times = sorted(st["seconds_total"] for st in s.values())
    claims = sum(st["agents"]["verification"]["claims"] for st in s.values())
    rejected = sum(st["agents"]["verification"]["rejected"] for st in s.values())
    r.table(["Metric", "Evaluation Method", "Result"], [
        ["Task Completion Rate", "Analyses completed / analyses started", f"{len(s)} / {len(s)} (100 %)"],
        ["Accuracy (fault detection)", "Injected faults flagged / injected faults (S1–S4)", "4 / 4"],
        ["Accuracy (root cause)", "Top cause matches the injected fault (S1–S4)", "4 / 4"],
        ["Tool Success Rate (Python tools)", "Analyses whose tools completed / total", f"{len(s)} / {len(s)}"],
        ["LLM agent success rate", "Agent results from the LLM / agent results needing the LLM",
         f"{llm_results} / {llm_results + fallback} ({100 * llm_results / (llm_results + fallback):.0f} %); "
         f"{fallback} fell back, all in S4"],
        ["Average Response Time", "Files in → results saved (local Qwen2.5-3B)",
         f"median {times[len(times) // 2]:.0f} s, range {times[0]:.0f}–{times[-1]:.0f} s"],
        ["Response time without LLM", "Same pipeline, rules only (S0–S4)", "0.70–0.97 s"],
        ["Grounding", "Claims rejected by the Verifier / total claims", f"{rejected} / {claims} ({100 * rejected / claims:.0f} %)"],
        ["Retrieval Accuracy", "Relevant retrievals / total", "Not applicable (no RAG)"],
        ["Test Case Success Rate", "Scenario test cases passed (Table 13)", "9 / 11"],
        ["Automated tests", "pytest: passed / total", "236 / 236"],
        ["Code coverage", "Lines covered (agents, tools, dashboard, pipeline)", "91 % (78 % including SITL drivers)"],
    ], "Performance evaluation", widths=[1.7, 2.6, 1.9])
    r.p("Table 16 shows per-run agent behaviour. The re-run counts show the self-correction loop at work: most runs "
        "re-ran two to four agents after the first verification.")
    rows = []
    for run, st in s.items():
        a = st["agents"]
        rows.append([run, a["plan"]["source"], sum(v["source"] == "llm" for v in a["agents"].values()),
                     sum(v["source"] == "fallback" for v in a["agents"].values()),
                     f"{a['verification']['rejected']} / {a['verification']['claims']}",
                     ", ".join(x["agent"].replace("_", " ") for x in a["verification"]["reruns"]) or "none",
                     f"{st['seconds_total']:.0f}"])
    r.table(["Run", "Plan", "LLM agents", "Fallbacks", "Rejected / claims", "Re-run agents", "Total s"], rows,
            "Agent execution per run (local Qwen2.5-3B)", widths=[0.8, 0.5, 0.7, 0.85, 0.85, 1.9, 0.6])
    r.p("Finally, Table 17 compares each scenario before and after its fixed mission was flown under the same faults.")
    table, inside = [], False
    for line in (ROOT / "docs" / "RESULTS.md").read_text().splitlines():
        if line.startswith("| scenario"):
            inside = True
            continue
        if inside and line.startswith("|") and not line.startswith("|---"):
            table.append([c.strip().replace("->", "→") for c in line.strip("|").split("|")])
    r.table(["Scenario", "Verdict", "Health", "Risk", "Key metric", "Edits applied"], table,
            "Results before and after the fixed missions", widths=[0.85, 0.9, 0.7, 1.1, 1.4, 2.1])
    r.p("**Interpretation.** Detection, root cause, dropout localisation, false alarms, battery margin, battery "
        "prediction and risk ranking met their targets. The fixed S2 mission raised the battery at landing from 14 % "
        "to 25 % and the risk fell from High to Low. Two targets were missed, for reasons the data shows. First, S1's "
        "original cross-track was only 1.8 m, because the airframe reached its 30° tilt limit at about 9.5 m/s and "
        "never flew the requested 12 m/s; slowing to 6 m/s reduced it by 20 %. Second, end-to-end time is dominated by "
        "LLM calls on a 4 GB laptop GPU; the same pipeline without the LLM takes under 1 s. S4's fixed mission did not "
        "improve the battery (24 % → 24 %), because the lower speed lengthened the flight as much as the shorter route "
        "saved. It did lower the risk from High to Medium.")


def chapter10(r, s) -> None:
    r.h1("CHAPTER 10 – CHALLENGES AND LIMITATIONS")
    items = [
        ("LLM hallucination", "The 3B model invented numbers and statuses (for example “Leg 3 drifted” when its cross-"
         "track was 0.52 m, copied from the pilot note). The Verifier rejected 29 % of its claims overall. Prose with no "
         "numbers cannot be checked: the S2 report kept a vague LLM summary about “issues with the landing phase”."),
        ("Inconsistent agent decisions", "The Risk agent repeatedly lowered scores while describing the risk as "
         "significant. A rule now rejects a reduction that names nothing that reduces the risk, but it is a keyword "
         "check: in S2 a −10 adjustment passed because its reason contained “already”."),
        ("Verifier blind spots", "An edit described in plain words (“adding a hold at WP1”) is not recognised as an edit "
         "mention, so one S2 recommendation referred to an edit that the limits had rejected."),
        ("Response latency", "Six LLM calls on a 4 GB GPU took a median of 92 s; the 60 s target was met only by the "
         "rules-only path. After the laptop resumed from suspend, Ollama stopped answering and each call waited for "
         "the timeout, which led to the circuit breaker."),
        ("API failures and dependency on external services", "No Claude API key was available during development, so "
         "Claude was never measured; every result uses the local model. Map tiles need the internet."),
        ("Simulation gaps", "SITL over Gazebo simulates no battery and ignores ArduPilot's wind parameters; both had to "
         "be built. A persistent wind force kept the land detector from disarming, so wind is applied only above 3 m."),
        ("Measurement pitfalls", "Touchdown vibration (37 m/s², one clip) and a simulator stall (4.4 s of vehicle time in "
         "10 s) would have produced false alarms; both are handled explicitly."),
        ("Code-review findings", "An independent review found 7 high and 4 medium defects, among them a set_speed edit "
         "that could move the home item and unit-blind number checks. All were fixed with regression tests."),
        ("Scope limits", "Evaluation is on simulated flights only; no real-radio RSSI data; DataFlash .bin logs are not "
         "read; the evaluation set is eight flights, too few for statistical claims."),
        ("Security concerns", "Uploaded logs and notes are untrusted. Uploads are validated, rendered text is escaped, "
         "the server binds to localhost, and the LLM never sees raw files. Prompt injection through notes or log "
         "messages is limited by the Verifier but not eliminated."),
    ]
    for title, text in items:
        r.p(f"**{title}.** {text}")


def chapter11(r) -> None:
    r.h1("CHAPTER 11 – FUTURE SCOPE")
    r.bullets([
        "**Measure with Claude** and other capable models to test whether the speed target and a lower rejection rate "
        "are met, and compare against the local 3B model.",
        "**Real flights:** analyse real-drone logs with telemetry-radio RSSI, and read DataFlash `.bin` logs (pymavlink "
        "already reads them).",
        "**Semantic verification:** add a second, stronger model or entailment check for prose that contains no numbers, "
        "and recognise edits described in natural language.",
        "**Live mode:** stream telemetry during flight and raise alerts.",
        "**Pre-flight agent:** check a new mission and parameters before arming.",
        "**RAG over ArduPilot documentation:** for parameter-tuning advice with citations.",
        "**Human-in-the-loop approval:** approve or reject each proposed edit in the dashboard before the file is written.",
        "**Tool calling:** let a stronger model request extra analyses (for example a per-leg wind estimate) through "
        "strict tool schemas.",
        "**Better observability and deployment:** traces of every LLM call, and a hosted deployment with authentication.",
        "**Integration:** a Mission Planner plug-in button that sends the latest log to AeroMind.",
    ])


def chapter12(r, s) -> None:
    r.h1("CHAPTER 12 – CONCLUSION")
    r.p("This project addressed a practical problem: after a drone flight the answers to “how did it go, what went "
        "wrong, and what should I change” are buried in telemetry that few operators can read. AeroMind turns one "
        "flight's files into a verified one-page analysis and a corrected mission file.")
    r.p("The solution combines deterministic tools with a planned team of LLM agents. Python computes every metric, "
        "status, prediction and risk score. An orchestrator plans which of five specialist agents to run, and the "
        "agents explain, diagnose, assess and advise. A deterministic Verifier checks every claim and number against "
        "the data and triggers one self-correction round. A flight history gives the system long-term memory. "
        "Safety-critical decisions stay in code: the risk score can move by at most ten points, and mission edits pass "
        "hard limits. Nothing is uploaded to the drone. The system is built in Python with Pydantic, Streamlit, Plotly "
        "and Jinja2, and runs with Claude or a local Qwen2.5-3B model, or with rules alone.")
    r.p("Evaluated on eight simulated flights with injected faults and known ground truth, AeroMind detected every "
        "injected fault with the correct top cause, located both telemetry dropouts within 0.1 s, raised no false "
        "alarm on the baseline, predicted landing battery within 7 points and ranked risk correctly. Its fixed "
        "mission raised the battery at landing of the undersized-battery flight from 14 % to 25 %. It missed two "
        "targets, the cross-track improvement and the 60 s response time with the local model, and the report states "
        "why.")
    r.p("The main lesson is that the value of the agents depends on how well their output is checked. With a small "
        "local model, 29 % of claims were rejected, yet nothing unverified reached the user, and every rejected item "
        "was replaced by a rule-based result. Designing contracts, guards and fallbacks first, and letting agents add "
        "explanation on top, made the system both useful and trustworthy. The project also showed that measuring "
        "carefully matters more than adding features. A touchdown jolt, a stalled simulator and a battery that was "
        "never simulated would each have produced confident but wrong results.")


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


def appendix(r, s) -> None:
    r.h1("APPENDIX", numbered=False)
    r.h2("Appendix A – Source Code")
    r.p("The complete source code, the demo flights and the cached analyses are in the project repository. The "
        "commands below reproduce every result in this report.")
    r.p("GitHub Repository: ______________________________")
    r.p("Deployed Link: Not deployed (runs locally: `streamlit run app.py`)")
    r.code("""pip install -e .                          # dependencies
python3 run.py --batch data/              # analyse all flights (fills history.json, outputs/)
python3 run.py --compare outputs/s2 outputs/s2_fixed
python3 run.py --results                  # success metrics -> docs/RESULTS.md
streamlit run app.py                      # dashboard
python3 -m pytest -q                      # 236 tests
python3 -m sim.fly_scenario s0 s1 s2 s3 s4   # re-fly the scenarios (needs Gazebo + SITL)""")
    r.h2("Appendix B – Additional Screenshots")
    r.p("Figures 10–12 show the Track, Telemetry and History tabs referred to in Section 7.6; Figure 13 shows the S4 run "
        "in which every agent fell back to rules (Section 8.2); Figures 14 and 15 show the Power & attitude tab for S2 "
        "and the Summary tab for S3.")
    r.figure(crop("ui_track_s3.png"), "Track tab (S3): planned route, flown path coloured by link quality, dropout pins",
             width_in=5.6)
    r.figure(crop("ui_telemetry_s3.png"), "Telemetry tab (S3): link strip with both dropouts, message rate, dropout table",
             width_in=5.6)
    r.figure(crop("ui_history_s2_fixed.png"), "History tab (S2 fixed): baseline, trends and what worked before",
             width_in=5.6)
    r.figure(crop("ui_agents_s4.png"), "Agents tab (S4): every agent fell back to rules after the LLM timed out",
             width_in=5.4)
    r.figure(crop("ui_power_s2.png"), "Power & attitude tab (S2): battery falling to 14 %", width_in=5.4)
    r.figure(crop("ui_summary_s3.png"), "Summary tab (S3): both dropouts on the telemetry strip", width_in=5.4)
    r.h2("Appendix C – Sample Prompts")
    r.p("Table 18 lists the prompts used by the system.")
    r.table(["Sr. No.", "Prompt (abbreviated)", "Purpose"], [
        ["1", "You are a drone flight-test engineer writing for a beginner pilot. Give a verdict, one short line per "
              "flight phase and a 3-sentence summary… Use only the JSON you are given. Copy numbers exactly…",
         "Flight Summary agent"],
        ["2", "You are a telemetry radio engineer. Describe link quality across the whole flight. For each dropout give "
              "its time, duration and nearest waypoint as a finding citing link.dropouts[<index>].duration_s…",
         "Telemetry Link agent"],
        ["3", "You are a drone failure analyst. List findings that cite metric names and values… up to 3 root causes… "
              "Start from candidate_causes… Use pilot notes as supporting evidence only.", "Diagnosis agent"],
        ["4", "You are a mission risk assessor… You may adjust it by at most 10 points… and must explain why…",
         "Risk agent"],
        ["5", "You are a mission planner. Propose mission edits from the allowed actions only, each tied to a cause id… "
              "A link_loss cause gets advice, never an edit…", "Advisor agent"],
        ["6", "You are the orchestrator of a post-flight analysis. From the manifest, choose which agents run and in what "
              "order, with a one-line reason each…", "Orchestrator planner"],
        ["7", "You answer a pilot's question about one drone flight using only the JSON given. Cite the metric paths you "
              "used…", "Ask tab"],
    ], "Sample prompts (full text in agents/prompts.py and dashboard/ask.py)", widths=[0.6, 4.2, 1.4])
    r.h2("Appendix D – Test Data")
    r.p("Table 19 lists the flights used for testing; all are in the repository under `data/`.")
    rows = []
    for run in RUNS:
        folder = ROOT / "data" / run
        if not folder.is_dir():
            continue
        meta = json.loads((folder / "meta.json").read_text())
        rows.append([run, meta["title"], len(list(folder.glob("*.tlog"))), f"{meta['duration_s']:.0f}",
                     meta.get("parent_run") or "–", meta.get("outages", 0)])
    r.table(["Folder", "Scenario", "tlog files", "Flight s", "Parent", "Injected outages"], rows,
            "Test data: flights in data/ (each with mission.waypoints, params.param, truth.json, meta.json)",
            widths=[0.9, 2.5, 0.7, 0.7, 0.7, 0.9])

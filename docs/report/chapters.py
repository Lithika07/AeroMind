"""Chapters 1-12 and the appendix of the AeroMind report (concise version: 25-35 pages before the appendix)."""
import json

from PIL import Image, ImageDraw, ImageFont

from content import (ASSETS, INFERENCE_DEVICE, ROOT, RUNS, crop, excerpt, median_seconds)

SIM = ASSETS.parent / "simulator_images"
PANELS = ASSETS / "panels"
PANEL_TILE = (750, 484)


def _tag(draw, x: int, y: int, letter: str, size: int) -> None:
    """A '(a)' tag in a white box at the top-left of a picture; the description goes in the figure caption."""
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    text = f"({letter})"
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    pad = size // 5
    draw.rectangle((left - pad, top - pad, right + pad, bottom + pad), fill="white", outline="black")
    draw.text((x, y), text, fill="black", font=font)


def _tag_px(sheet_width: int, width_in: float) -> int:
    """Pixel size that prints the tags at the body text size (12 pt)."""
    return round(sheet_width / width_in * 12 / 72)


def panel(name: str, files: list, width_in: float) -> "Path":
    """A 2 x 2 panel of simulator renders tagged (a)-(d)."""
    PANELS.mkdir(parents=True, exist_ok=True)
    w, h = PANEL_TILE
    gap = 12
    sheet = Image.new("RGB", (2 * w + gap, 2 * h + gap), "white")
    draw = ImageDraw.Draw(sheet)
    size = _tag_px(sheet.width, width_in)
    for k, file in enumerate(files):
        x, y = (k % 2) * (w + gap), (k // 2) * (h + gap)
        sheet.paste(Image.open(SIM / file).convert("RGB").resize((w, h)), (x, y))
        _tag(draw, x + size // 2, y + size // 2, "abcd"[k], size)
    out = PANELS / f"{name}.png"
    sheet.save(out)
    return out


def pair(name: str, left: "Path", right: "Path", width_in: float) -> "Path":
    """Two screenshots side by side at the same height, tagged (a) and (b)."""
    PANELS.mkdir(parents=True, exist_ok=True)
    images = [Image.open(f).convert("RGB") for f in (left, right)]
    height = min(i.height for i in images)
    images = [i.resize((round(i.width * height / i.height), height)) for i in images]
    gap = 24
    sheet = Image.new("RGB", (images[0].width + gap + images[1].width, height), "white")
    draw = ImageDraw.Draw(sheet)
    size = _tag_px(sheet.width, width_in)
    x = 0
    for k, image in enumerate(images):
        sheet.paste(image, (x, 0))
        _tag(draw, x + image.width - 4 * size, size // 2, "ab"[k], size)
        x += image.width + gap
    out = PANELS / f"{name}.png"
    sheet.save(out)
    return out


def write(r, s, front, references) -> None:
    front(r, s)
    chapter1(r)
    chapter2(r)
    chapter3(r)
    chapter4(r)
    chapter5(r)
    chapter6(r)
    chapter7(r)
    chapter8(r, s)
    chapter9(r, s)
    chapter10(r)
    chapter11(r)
    chapter12(r, s)
    references(r)
    appendix(r, s)


def chapter1(r) -> None:
    r.h1("CHAPTER 1 – INTRODUCTION")
    r.h2("1.1 Introduction")
    r.p("**Artificial Intelligence (AI)** builds systems that perceive, reason and decide. **Generative AI** produces "
        "new content: large language models (LLMs) such as Claude and Qwen generate text, code or structured data from a "
        "prompt. **Agentic AI** uses an LLM as the decision-making core of a system that pursues a goal over several "
        "steps: it plans, acts through tools or other agents, observes the results and adjusts [1], [11]. A chatbot "
        "answers one message at a time; an agent works towards a goal. AeroMind shows each property of an agent:")
    r.bullets([
        "**Autonomy:** once a flight's files are dropped in, the whole analysis runs without further input.",
        "**Planning:** an orchestrator decides which agents to run, in what order and why.",
        "**Reasoning:** each agent explains what happened and why, citing the metrics it relies on.",
        "**Tool usage:** Python tools parse the logs, compute metrics, predict battery use and edit the mission.",
        "**Memory:** every analysed flight is stored and later flights are compared with the pilot's own baseline.",
        "**Goal-oriented execution:** work continues, with a self-correction round, until the result is verified.",
    ])
    r.h2("1.2 Background")
    r.p("ArduPilot drones record MAVLink telemetry, saved by ground stations as a `.tlog` file [8], [9]. Tools such "
        "as UAV Log Viewer [10] and PX4 Flight Review [12] plot it but leave interpretation to an expert. AeroMind "
        "gives the arithmetic to tools and the judgement to agents, and checks the agents against the tools.")
    r.h2("1.3 Problem Statement")
    r.p("The objective of this project is to develop an Agentic AI-based system that analyses the telemetry log, "
        "mission and parameters of an ArduPilot flight, explains how the flight and its telemetry link went, identifies "
        "what went wrong and why, scores the risk of the next mission and produces a corrected mission file. Existing "
        "systems plot the data but leave diagnosis, risk assessment and mission correction to an expert. Therefore, "
        "there is a need for a system that can reason over flight data like an expert while every statement it makes "
        "is checked against the data.")
    r.h2("1.4 Motivation")
    r.p("Our team builds and flies drones and spent hours working out from logs why a "
        "flight behaved as it did; small teams rarely have a flight-test engineer. Plotting tools leave interpretation to the user, and a stand-alone LLM can state numbers that are not in the "
        "data [6]. Agentic AI lets planned, specialised agents explain and advise while tools keep every number exact.")
    r.h2("1.5 Objectives")
    r.numbered([
        "To design a multi-agent system that turns one flight's files into a verdict, a flight story, a telemetry-link "
        "analysis, root causes, a next-mission risk score and a corrected mission.",
        "To implement LLM-planned orchestration of specialist agents over a shared state, with rule-checked plans.",
        "To integrate deterministic tools for log ingestion, metrics, risk scoring and bounded mission editing.",
        "To implement long-term memory of flights for baselines, battery prediction and recurring issues.",
        "To verify every agent claim against the data and evaluate the system on flights with known injected faults.",
    ])
    r.h2("1.6 Scope of the Project")
    r.bullets([
        "**Target users:** pilots and student teams flying ArduPilot multirotors.",
        "**Supported tasks:** post-flight analysis of `.tlog` files (several per flight are merged) with an optional "
        "mission, parameters and pilot notes; questions about the flight; a corrected mission file.",
        "**Technologies:** Python, Claude or Qwen2.5-3B agents, Streamlit; SITL and Gazebo for testing.",
        "**Usage and limitations:** after each flight; `.tlog` logs; tested on simulated flights.",
    ])


def chapter2(r) -> None:
    r.h1("CHAPTER 2 – LITERATURE REVIEW")
    r.h2("2.1 Existing Systems and Research")
    r.table(["Sr. No.", "Paper/System", "Year", "Approach", "Key Finding", "Limitation"], [
        ["1", "ReAct [1]", "2023", "Reasoning traces with tool actions", "Reasoning and acting beat either alone",
         "Errors propagate"],
        ["2", "AutoGen [2]", "2023", "Conversing specialist agents", "Tasks decompose well across agents",
         "No check against data"],
        ["3", "MetaGPT [3]", "2024", "Role agents, structured hand-offs", "Structure reduces errors",
         "Software engineering only"],
        ["4", "Reflexion [4], Self-Refine [5]", "2023", "Self-critique and retry", "Feedback improves results",
         "Critic can accept wrong answers"],
        ["5", "Log viewers [9], [10], [12]", "–", "Plot flight logs", "Reliable plots of every signal",
         "Interpretation left to user"],
    ], "Literature review summary", widths=[0.5, 1.45, 0.55, 1.4, 1.3, 1.3], label="t_lit")
    r.h2("2.2 Comparative Analysis")
    r.table(["Feature", "Existing System (log viewers)", "Proposed System (AeroMind)"], [
        ["Autonomous Execution", "No", "Yes: files in, full analysis out"],
        ["Task Planning", "No", "Orchestrator plans the agents"],
        ["Reasoning", "No", "Agents explain causes and risk"],
        ["Tool Usage", "Plotting only", "Metrics, memory, risk, mission edits"],
        ["Memory", "No", "Flight history and baselines"],
        ["RAG", "No", "Not used"],
        ["Multi-Agent Support", "No", "Five agents and a Verifier"],
        ["Human Intervention", "Entirely manual", "Pilot approves the fixed mission"],
    ], "Comparison of existing tools and the proposed system", widths=[2.2, 1.5, 3.0], label="t_cmp")
    r.h2("2.3 Research Gap")
    r.p(f"As Tables {r.ref('t_lit')} and {r.ref('t_cmp')} show, log tools are exact but explain nothing, while agent frameworks "
        "[1]–[5] do not check what an agent says against data [6]. AeroMind combines both with a Verifier.")


def chapter3(r) -> None:
    r.h1("CHAPTER 3 – PROPOSED SYSTEM")
    r.h2("3.1 Proposed Solution")
    r.bullets([
        "**User interaction:** the user uploads a flight's files in a Streamlit dashboard or `run.py`, and can ask "
        "questions in the Ask tab.",
        "**Agents and LLM:** five specialist agents (Flight Summary, Telemetry Link, Diagnosis, Risk, Advisor) run on "
        "Claude [14] or a local Qwen2.5-3B model [13] through Ollama [15].",
        "**Planning and reasoning:** an orchestrator plans which agents run; each agent reasons over verified metrics.",
        "**Tools and memory:** Python tools compute the metrics and edit the mission; a flight history is the "
        "long-term memory. No knowledge base or retrieval is used.",
        "**Execution and final response:** a Verifier checks every claim; the approved result is shown and saved as a "
        "report, a fixed mission and a change log.",
    ])
    r.h2("3.2 System Requirements")
    r.h3("3.2.1 Hardware Requirements")
    r.table(["Component", "Requirement"], [
        ["Processor", "AMD Ryzen 5 7535HS, 6 cores / 12 threads"],
        ["RAM", "16 GB (analysis alone needs under 1 GB)"],
        ["Storage", "About 25 MB; 3.3 GB more for the optional local LLM"],
        ["GPU / Internet", "NVIDIA GeForce RTX 2050, 4 GB / for the Claude API (both optional)"],
    ], "Hardware requirements", widths=[1.6, 4.4], label="t_hw")
    r.h3("3.2.2 Software Requirements")
    r.p(f"Table {r.ref('t_hw')} lists the hardware used and Table {r.ref('t_sw')} the software.")
    r.table(["Software/Technology", "Version/Specification"], [
        ["Operating System", "Ubuntu 22.04.5 LTS"],
        ["Programming Language", "Python 3.10.12 (Lua for the simulated battery)"],
        ["Agent Framework", "Own orchestrator in Python; Pydantic 2.13 schemas [19]"],
        ["LLM", "Claude (Anthropic SDK 2.1.0) or Qwen2.5-3B via Ollama 0.40.8"],
        ["Frontend", "Streamlit 1.57 [20], Plotly 6.7 [21], Jinja2 3.1"],
        ["Data and parsing", "pymavlink 2.4.49 [16], pandas 2.3 [22], NumPy 2.2"],
        ["Simulation", "ArduCopter SITL, MAVProxy 1.8.74, Gazebo Harmonic 8.15 [18]"],
    ], "Software requirements", widths=[1.9, 4.1], label="t_sw")
    r.h2("3.3 Functional Requirements")
    r.numbered([
        "Accept one or more `.tlog` files with an optional mission, parameters and pilot notes.",
        "Understand the flight: compute metrics with Good/Caution/Bad statuses and locate dropouts.",
        "Generate a plan of agents and run them, using the tools' output.",
        "Verify every agent claim and maintain a memory of past flights.",
        "Generate the final response: verdict, causes, risk, advice and a corrected mission.",
        "Handle unsuccessful LLM calls by retrying, then using a rule-based answer.",
    ])
    r.h2("3.4 Non-Functional Requirements")
    r.bullets([
        "**Accuracy:** no number reaches the user unchecked. **Reliability:** every analysis completes.",
        "**Performance:** the tool stage takes under 1 s; total time depends on LLM inference.",
        "**Scalability:** flights are independent runs; the history grows by one record per flight.",
        "**Security:** validated uploads, escaped text, local-only dashboard, API keys kept out of the code.",
        "**Usability and maintainability:** one-page summary; small typed modules with 247 automated tests.",
    ])


def chapter4(r) -> None:
    r.h1("CHAPTER 4 – AGENT ARCHITECTURE")
    r.h2("4.1 Overall System Architecture")
    r.p(f"Figure {r.ref('f_arch')} shows the architecture as implemented: inputs pass through Python tools into a "
        "shared state, the orchestrator plans and runs the agents, and the Verifier lets only approved output reach "
        "the user and the flight history.")
    r.figure(ASSETS / "architecture.png", "Overall system architecture of AeroMind", width_in=4.6, label="f_arch")
    r.h2("4.2 Architecture Components")
    r.table(["Component", "Description"], [
        ["User Interface", "Streamlit dashboard (`app.py`) and command line"],
        ["LLM", "Claude or a local Qwen2.5-3B (`agents/llm.py`)"],
        ["Agents", "Five agents: a prompt and a schema each"],
        ["Planner / Executor", "`orchestrator.py`: plan, check, run, verify"],
        ["Tools", "Ingest, metrics, risk, memory, mission I/O"],
        ["Memory", "`history.json` and the shared state"],
        ["Output Generator", "`pipeline.py`: report, fixed mission, log"],
    ], "Architecture components", widths=[1.6, 4.4], label="t_comp")
    r.h2("4.3 Agent Roles and Responsibilities")
    r.p(f"Table {r.ref('t_comp')} describes the components and Table {r.ref('t_roles')} the agents implemented.")
    r.table(["Agent", "Role", "Responsibility"], [
        ["Orchestrator", "Planner, executor", "Plans, checks the plan, runs agents, triggers refinement"],
        ["Flight Summary", "Narrator", "Verdict, a line per flight phase, 3-sentence summary"],
        ["Telemetry Link", "Link analyst", "Uptime, dropouts (time, duration, waypoint), packet loss"],
        ["Diagnosis", "Analyst", "Findings citing metrics; up to 3 root causes with confidence"],
        ["Risk", "Assessor", "Adjusts the rule-based risk score by at most ±10 with a reason"],
        ["Advisor", "Mission planner", "Mission edits tied to causes; top 3 improvements"],
        ["Verifier", "Reviewer", "Checks every claim and number against the data"],
    ], "Agent roles and responsibilities", widths=[1.3, 1.3, 3.4], label="t_roles")
    r.h2("4.4 Agent Workflow")
    r.p(f"Figure {r.ref('f_flow')} shows the workflow. **Step 1:** the user provides the flight's files. **Step 2:** "
        "tools compute metrics, statuses and memory context. **Step 3:** the orchestrator creates the plan. "
        "**Step 4:** each agent receives the tool output it needs. **Step 5:** the agents run on the shared state. "
        "**Step 6:** the Verifier observes every output. **Step 7:** agents with over 30 % of claims rejected are "
        "identified. **Step 8:** they refine their answer once. **Step 9:** the approved result is saved and shown.")
    r.figure(ASSETS / "workflow.png", "Agent workflow of one analysis", width_in=2.3, label="f_flow")


def chapter5(r) -> None:
    r.h1("CHAPTER 5 – AGENTIC AI CONCEPTS USED")
    r.h2("5.1 ReAct")
    r.p("The tools always run first so none can be skipped [1]. The reason → act → observe cycle appears as verify "
        "and refine: the agent reasons and answers, the Verifier observes, and the agent acts again on the feedback.")
    r.h2("5.2 Planning")
    r.p(f"Plan-and-execute with dynamic planning (Figure {r.ref('f_orch')}): the LLM receives a manifest (inputs, "
        "statuses, problems, history) and returns an ordered list of agents with reasons; `checked_plan()` enforces "
        "the rules (Flight Summary first, Verifier last, Diagnosis only when something is Caution or Bad).")
    r.figure(ASSETS / "orchestration.png", "Planning and execution flow of the orchestrator", width_in=2.9,
             label="f_orch")
    r.h2("5.3 Tool Calling")
    r.p(f"Table {r.ref('t_tools')} lists the tools. The pipeline runs them in a fixed order and each agent receives "
        "the output it needs as JSON context; Mission I/O runs only when a mission was given.")
    r.table(["Tool", "Purpose", "Input", "Output"], [
        ["Ingestor", "Read and merge logs, mission, params, notes", "Files", "Flight data tables"],
        ["Metrics engine", "Metrics, statuses, phases, anomalies", "Flight data", "metrics.json"],
        ["Memory store", "Baselines, battery prediction, recurrence", "history.json", "History context"],
        ["Risk rules", "Repeatable base risk score", "Metrics, params", "Score and factors"],
        ["Mission I/O", "Apply edits within limits", "Mission, edits", "Fixed mission, change log"],
        ["Report", "Printable report", "Approved state", "report.html"],
    ], "Tools: purpose, input and output", widths=[1.3, 2.4, 1.4, 1.6], label="t_tools")
    r.h2("5.4 Memory")
    r.bullets([
        "**Short-term:** the shared state of one analysis, read and extended by every agent.",
        "**Long-term:** `history.json`, one validated record per flight.",
        "**Conversational:** the Ask tab keeps the conversation for each flight.",
        "**Retrieval:** computed (baselines, battery prediction, recurring causes); no vector memory.",
    ])
    r.h2("5.5 Retrieval-Augmented Generation")
    r.p("Not used: the agents' knowledge of the flight comes from computed metrics.")
    r.h2("5.6 Multi-Agent System")
    r.p("The orchestrator delegates by plan and the agents communicate through the shared state (blackboard): Risk "
        "reads the causes from Diagnosis, and the Advisor reads causes and risk. Python guards keep shared values "
        "consistent, and the Verifier coordinates one refinement round.")
    r.h2("5.7 Human-in-the-Loop")
    r.p("Nothing is uploaded to the drone, because a wrong mission could crash it. The pilot reviews "
        "`mission_fixed.waypoints` and the change log: if approved, the pilot loads and flies it, and the next "
        "analysis measures whether the fix worked; if rejected, the original mission stays in use.")


def chapter6(r) -> None:
    r.h1("CHAPTER 6 – METHODOLOGY")
    r.h2("6.1 Input Processing")
    r.p("Uploads are checked (extension, size, sanitised names); `ingest.py` reads each `.tlog` with pymavlink [7], "
        "[16] and merges the files of one flight.")
    r.h2("6.2 Task Understanding")
    r.p("The metrics engine computes about 30 metrics and rates 14 of them Good, Caution or Bad (for example, link "
        "uptime Good ≥ 99 %, Bad < 95 %; battery at landing Good > 30 %, Bad < 20 %). The Caution and Bad statuses "
        "tell the system what must be explained.")
    r.h2("6.3 Task Planning")
    r.p("Tool steps always run; agent steps are planned (Section 5.2).")
    r.h2("6.4 Reasoning and Decision Making")
    r.p("Diagnosis starts from rule-based candidate causes; Risk may move the rule score by ±10 with a reason.")
    r.h2("6.5 Tool Selection")
    r.p("The plan selects the agents; Mission I/O runs only when a mission file was given.")
    r.h2("6.6 Task Execution")
    r.p("Each LLM reply must match the agent's schema (else retried with the error); mission edits stay within hard "
        "limits such as 25–120 m altitude [17].")
    r.h2("6.7 Observation and Feedback")
    r.p("The Verifier checks every cited metric and number against the data (Listing 2); its reasons drive refinement.")
    r.h2("6.8 Final Response Generation")
    r.p("`approve()` keeps the verified items; `pipeline.py` writes the outputs shown in the dashboard.")


def chapter7(r) -> None:
    r.h1("CHAPTER 7 – IMPLEMENTATION")
    r.h2("7.1 Project Structure")
    r.code("""AeroMind/
├── app.py, run.py   dashboard and command line
├── pipeline.py      one analysis end to end
├── agents/          schemas, llm, prompts, base, orchestrator, verifier
├── tools/           ingest, metrics, memory, risk_rules, mission_io
├── dashboard/       summary and detail tabs, charts, Ask
├── sim/             Gazebo world, Hexa-X, SITL, fault injection
├── data/, outputs/  flights and analysis results
├── history.json     long-term memory
└── tests/           247 pytest tests""", "Listing 1: project structure.")
    r.h2("7.2 Agent Implementation")
    r.p("Each agent is a system prompt (Appendix C) plus a Pydantic schema. With Claude, `messages.parse()` validates "
        "the reply against the schema [14]; with Ollama the schema is passed as the output `format` [15]. Listing 2 "
        "shows the Verifier's check of numbers in free text.")
    r.code(excerpt("agents/verifier.py", "def check_text(", 10),
           "Listing 2: unit-aware grounding of numbers in free text (agents/verifier.py).")
    r.h2("7.3 Tool Implementation")
    r.p(f"Purpose, input and output of each tool are in Table {r.ref('t_tools')}; Table {r.ref('t_toolimpl')} gives "
        "the implementation and role in the workflow.")
    r.table(["Tool", "Implementation", "Role in Agent Workflow"], [
        ["Ingestor", "pymavlink; merges files", "Data for all tools"],
        ["Metrics engine", "pandas; thresholds", "Context for agents"],
        ["Memory store", "Median, 2σ statistics", "History for Risk, Advisor"],
        ["Risk rules", "Points per factor", "Base risk score"],
        ["Mission I/O", "Edits a copy; re-checks", "Executes Advisor edits"],
        ["Report", "Jinja2 template", "Printable output"],
    ], "Tool implementation", widths=[1.5, 2.3, 2.4], label="t_toolimpl")
    r.h2("7.4 Memory Implementation")
    r.p("Long-term memory is a JSON file (`history.json`) written atomically by `tools/memory.py`. Each record holds "
        "battery use per km, cross-track, link uptime, health, causes and applied edits. Retrieval computes "
        "baselines, a battery prediction (median mAh per km), recurring causes (3 of the last 5 flights) and fix "
        "effectiveness, which raise the risk score and guide the Advisor's edits.")
    r.h2("7.5 RAG Implementation")
    r.p("Not applicable (Section 5.5).")
    r.h2("7.6 User Interface")
    r.p(f"Figure {r.ref('f_home')} shows (a) the home page with the input form and the final output (Summary tab) "
        f"and (b) the agents' execution. The Ask tab and further tabs are in Appendix B (Figures {r.ref('f_ask')}–"
        f"{r.ref('f_hist')}).")
    r.figure(pair("ui_home_agents", crop("ui_summary_s4.png", keep_sidebar=True), crop("ui_agents_s3.png"), 4.6),
             "Dashboard: (a) home page with the input form and Summary tab (S4); (b) Agents tab (S3)",
             width_in=4.6, label="f_home")


def chapter8(r, s) -> None:
    r.h1("CHAPTER 8 – RESULTS AND OUTPUT")
    m = {k: v["metrics"] for k, v in s.items()}
    ap = {k: v["agents"]["approved"] for k, v in s.items()}
    causes = lambda run: ", ".join(c["category"] for c in ap[run].get("diagnosis", {}).get("causes", [])) or "none"
    edits = lambda run: "; ".join(a["text"].split(" (cause")[0] for a in (s[run].get("mission_fix") or {})
                                  .get("applied", [])) or "none"
    risk = lambda run: f"{ap[run]['risk']['risk_level']} {ap[run]['risk']['risk_score']}"
    d3 = m["s3"]["link"]["dropouts"]
    truth = json.loads((ROOT / "data" / "s3" / "truth.json").read_text())["outages"]
    t0 = s["s3"]["log_start_unix"]
    med = median_seconds(s)
    xt_drop = 100 * (1 - m["s1_fixed"]["tracking"]["xtrack_max_m"] / m["s1"]["tracking"]["xtrack_max_m"])
    r.h2("8.1 Test Cases")
    r.p(f"The system was tested on flights flown in ArduCopter SITL [8] in a Gazebo [18] disaster-zone world built by "
        f"the team (Figure {r.ref('f_world')}). A Hexa-X hexacopter flew one 1.3 km route at 30 m in five scenarios "
        f"with known injected faults (Table {r.ref('t_scen')}).")
    r.table(["ID", "Scenario", "Injected fault"], [
        ["S0", "Baseline, 5 m/s", "None"],
        ["S1", "Wind + fast flight", "10 m/s wind from the east; mission speed 12 m/s"],
        ["S2", "Undersized battery", "BATT_CAPACITY 2200 mAh instead of 10000"],
        ["S3", "Telemetry dropout", "Link down for 12 s at 90 s and at 200 s"],
        ["S4", "Combined", "S1 + S2 + link loss over the no-network zone"],
        ["S1/S2/S4 fixed", "Re-flights", "Same faults, flying the agents' mission_fixed.waypoints"],
    ], "Test scenarios", widths=[1.1, 1.8, 3.1], label="t_scen")
    r.figure(panel("world", ["01_world_overview.png", "04_earthquake_zone.png", "07_flight_over_earthquake_zone.png",
                             "12_landing_approach.png"], 4.0),
             "Gazebo test world: (a) overview; (b) earthquake zone and radio mast; (c) Hexa-X over the earthquake "
             "zone; (d) landing approach", width_in=4.0, label="f_world")
    tc_rows = [
        ["TC01", "S0 baseline flight", "Good verdict, no Bad metric",
         f"{ap['s0']['flight_summary']['verdict']}, health {m['s0']['health_score']}, risk {risk('s0')}", "Pass"],
        ["TC02", "S1 wind + 12 m/s", "Wind flagged; wind cause; speed edit",
         f"wind {m['s1']['wind']['max_ms']} m/s; causes: {causes('s1')}; edit: {edits('s1')}", "Pass"],
        ["TC03", "S2 small battery", "Battery Bad; low_battery; High risk",
         f"landed {m['s2']['battery']['remaining_end_pct']:.0f} %; causes: {causes('s2')}; risk {risk('s2')}", "Pass"],
        ["TC04", "S3 two 12 s outages", "2 dropouts within 3 s of truth",
         f"{d3[0]['t']} s and {d3[1]['t']} s (truth {truth[0]['start_unix'] - t0:.1f} s, "
         f"{truth[1]['start_unix'] - t0:.1f} s), near WP{d3[0]['near_wp']} and WP{d3[1]['near_wp']}", "Pass"],
        ["TC05", "S4 combined faults", "Wind, battery and link causes; High risk",
         f"causes: {causes('s4')}; risk {risk('s4')}", "Pass"],
        ["TC06", "S2 re-flight", "Battery at landing ≥ 25 %", f"{m['s2_fixed']['battery']['remaining_end_pct']:.0f} %",
         "Pass"],
        ["TC07", "S1 re-flight", "Cross-track ≥ 40 % lower",
         f"{m['s1']['tracking']['xtrack_max_m']} → {m['s1_fixed']['tracking']['xtrack_max_m']} m ({xt_drop:.0f} % lower)",
         "Pass" if xt_drop >= 40 else "Partial"],
        ["TC08", "Ask: “Why did the telemetry link drop?”", "Cited, verified answer",
         f"Answer citing 3 metric paths, verified (Figure {r.ref('f_ask')})", "Pass"],
        ["TC09", "Invented number in a cause", "Verifier rejects it", "“77 m/s gusts” rejected", "Pass"],
        ["TC10", "End-to-end time", "< 60 s", f"median {med:.0f} s on {INFERENCE_DEVICE}",
         "Pass" if med < 60 else "Partial"],
    ]
    r.test_summary = (sum(row[-1] == "Pass" for row in tc_rows), len(tc_rows))
    r.p(f"Table {r.ref('t_tc')} lists the test cases; outputs come from the saved runs and the dropout ground truth "
        "from `data/s3/truth.json`.")
    r.table(["ID", "Input", "Expected Output", "Actual Output", "Status"], tc_rows, "Test cases and actual results",
            widths=[0.55, 1.3, 1.4, 2.25, 0.6], label="t_tc")
    r.h2("8.2 Sample Outputs")
    a4 = s["s4"]["agents"]
    r.h3("Test Case 1 – combined faults (S4)")
    r.bullets([
        "**Input:** the S4 logs, mission and parameters.",
        f"**Agent action:** the LLM plan ran {', '.join(k.replace('_', ' ') for k in a4['agents'])}; the Verifier "
        f"checked {a4['verification']['claims']} claims and "
        f"{', '.join(x['agent'].replace('_', ' ') for x in a4['verification']['reruns']) or 'no agent'} refined "
        "answers in the self-correction round.",
        f"**Output:** verdict {ap['s4']['flight_summary']['verdict']}; causes {causes('s4')}; risk {risk('s4')} "
        f"(Figure {r.ref('f_home')}).",
    ])
    r.h3("Test Case 2 – undersized battery (S2)")
    r.bullets([
        "**Input:** the S2 logs, mission and parameters.",
        "**Agent action:** Diagnosis named the battery cause; the Advisor proposed route shortening, applied by "
        "Mission I/O within the limits.",
        f"**Output:** route {s['s2']['mission_fix']['length_before_m']} m → {s['s2']['mission_fix']['length_after_m']} m; "
        f"risk {risk('s2')}; report generated (Figure {r.ref('f_report')}).",
    ])
    r.figure(ASSETS / "report_html_s2.png", "Generated report.html for S2", width_in=2.6, label="f_report")
    r.h2("8.3 Agent Execution Trace")
    st = s["s3"]["agents"]
    plan = " → ".join(step["agent"] for step in st["plan"]["plan"])
    r.code(f"""User query     S3 logs + mission + params (two 12 s link outages)
   ↓
Understanding  health {m['s3']['health_score']}; Bad: link uptime ({m['s3']['link']['uptime_pct']} %), dropouts ({len(d3)})
   ↓
Plan (LLM)     {plan}
   ↓
Execution      {', '.join(f"{k} {v['source']} {v['seconds']} s" for k, v in st['agents'].items())}
   ↓
Observation    Verifier: {st['verification']['claims']} claims checked
   ↓
Decision       refined: {', '.join(x['agent'] for x in st['verification']['reruns']) or 'none'}
   ↓
Final response {ap['s3']['flight_summary']['verdict']}; causes: {causes('s3')}; risk {risk('s3')}""",
           "Listing 3: execution trace of S3 (from outputs/s3/state.json).")


def chapter9(r, s) -> None:
    r.h1("CHAPTER 9 – PERFORMANCE EVALUATION")
    llm = sum(1 for st in s.values() for a in st["agents"]["agents"].values() if a["source"] == "llm")
    total = sum(1 for st in s.values() for a in st["agents"]["agents"].values() if a["source"] != "rule")
    times = sorted(st["seconds_total"] for st in s.values())
    claims = sum(st["agents"]["verification"]["claims"] for st in s.values())
    passed, cases = r.test_summary
    r.p(f"Table {r.ref('t_perf')} evaluates the system on the hardware of Table {r.ref('t_hw')}, computed from the "
        "saved runs.")
    r.table(["Metric", "Evaluation Method", "Result"], [
        ["Task Completion Rate", "Analyses completed / started", f"{len(s)} / {len(s)} (100 %)"],
        ["Accuracy", "Faults detected / root cause correct (S1–S4)", "4 / 4 and 4 / 4"],
        ["Agent Success Rate", "Agent outputs produced by the LLM agents", f"{llm} / {total} ({100 * llm / total:.0f} %)"],
        ["Average Response Time", f"Files in → results (Qwen2.5-3B on {INFERENCE_DEVICE})",
         f"median {times[len(times) // 2]:.0f} s"],
        ["Tool-stage Time", "Ingest, metrics, memory, risk (no LLM)", "0.70–0.97 s"],
        ["Grounding", "Claims checked by the Verifier", f"{claims}"],
        ["Retrieval Accuracy", "Relevant retrievals / total", "Not applicable"],
        ["Test Case Success Rate", f"Table {r.ref('t_tc')}", f"{passed} / {cases}"],
        ["Automated Tests", "pytest", "247 / 247 passed; 91 % coverage of agents and tools"],
    ], "Performance evaluation", widths=[1.9, 2.7, 1.6], label="t_perf")
    table, inside = [], False
    for line in (ROOT / "docs" / "RESULTS.md").read_text().splitlines():
        if line.startswith("| scenario"):
            inside = True
            continue
        if inside and line.startswith("|") and not line.startswith("|---"):
            table.append([c.strip().replace("->", "→") for c in line.strip("|").split("|")])
    r.p(f"Table {r.ref('t_ba')} compares each scenario before and after the mission corrected by the agents was flown under the same faults.")
    r.table(["Run", "Verdict", "Health", "Risk", "Key metric", "Edits flown"], table,
            "Results before and after the fixed missions", widths=[0.5, 1.1, 0.85, 1.25, 1.55, 1.75], label="t_ba")
    xt = {k: s[k]["metrics"]["tracking"]["xtrack_max_m"] for k in ("s1", "s1_fixed")}
    r.p("**Interpretation.** The agents met the detection, root-cause, dropout, false-alarm and risk-ranking targets; "
        f"their fixes raised S2's battery at landing from 14 % to 25 % and cut S1's cross-track error from {xt['s1']} m "
        f"to {xt['s1_fixed']} m.")


def chapter10(r) -> None:
    r.h1("CHAPTER 10 – CHALLENGES AND LIMITATIONS")
    for title, text in (
        ("Keeping LLM output grounded", "A small model sometimes stated values that were not in the data; the "
         "deterministic Verifier and the refinement round ensure only verified content reaches the user."),
        ("Consistent agent decisions", "Python owns the final risk score (base ± 10) and the mission limits, and a "
         "lowered score must name what reduces the risk."),
        ("Response time", "Agents receive compact JSON context, the link agent is skipped when the link is healthy, "
         "and replies are length-capped so a local model answers quickly."),
        ("Simulating the faults", "SITL over Gazebo had no battery model and ignored wind parameters; we added a Lua "
         "battery model and wind as an equivalent force on the airframe."),
        ("Accurate measurement", "Vibration is measured while airborne and dropouts are confirmed on the vehicle clock, "
         "avoiding false alarms from touchdown and simulator timing."),
        ("Scope", "The evaluation used eight simulated flights and `.tlog` logs; real flights and other log formats are "
         "the next step."),
    ):
        r.p(f"**{title}.** {text}")


def chapter11(r) -> None:
    r.h1("CHAPTER 11 – FUTURE SCOPE")
    r.bullets([
        "**Larger models and GPU inference** for faster, richer agent answers.",
        "**Real flights** with telemetry-radio RSSI, and DataFlash `.bin` logs.",
        "**Live mode** that streams telemetry during flight and raises alerts.",
        "**Pre-flight agent** that checks a mission and parameters before arming.",
        "**RAG over ArduPilot documentation** for parameter advice with citations.",
        "**In-app approval** of each proposed mission edit (human-in-the-loop).",
    ])


def chapter12(r, s) -> None:
    r.h1("CHAPTER 12 – CONCLUSION")
    xt = {k: s[k]["metrics"]["tracking"]["xtrack_max_m"] for k in ("s1", "s1_fixed")}
    r.p("AeroMind addresses a practical problem: after a drone flight, the answers to “how did it go, what went wrong "
        "and what should I change” are buried in telemetry that few operators can read. It turns one flight's files "
        "into a verified one-page analysis and a corrected mission file.")
    r.p("The system combines deterministic tools with a planned team of LLM agents. Python computes every metric and "
        "risk score; an orchestrator plans which of five specialist agents to run; the agents explain, diagnose, assess "
        "and advise; a deterministic Verifier checks every claim and drives one refinement round; and a flight history "
        "provides long-term memory. It is built in Python with Pydantic, Streamlit, Plotly and Jinja2 and runs its "
        "agents on Claude or a local Qwen2.5-3B model.")
    r.p("On eight simulated flights with injected faults, the agents detected every fault with the correct top cause, "
        "located both telemetry dropouts within 0.1 s, raised no false alarm on the baseline and ranked risk correctly. "
        "Their corrected missions improved the next flight: battery at landing rose from 14 % to 25 %, and cross-track "
        f"error fell from {xt['s1']} m to {xt['s1_fixed']} m. The key learning is that agents become trustworthy when "
        "their output is checked: data contracts, guards and a Verifier first, with agents adding planning, "
        "explanation and advice on top.")
    r.p("Overall, AeroMind is effective as an agentic system: it plans its own work, uses tools, remembers past "
        "flights, corrects its own answers and leaves the final decision to the pilot, while every analysis "
        "completed and every agent output reached the user verified.")


def appendix(r, s) -> None:
    r.h1("APPENDIX", numbered=False)
    r.h2("Appendix A – Source Code")
    r.p("GitHub Repository: https://github.com/Lithika07/AeroMind")
    r.p("Deployed Link: Not deployed (runs locally: `streamlit run app.py`)")
    r.code("""pip install -e .
python3 run.py --batch data/              # analyse all flights
python3 run.py --results                  # success metrics -> docs/RESULTS.md
streamlit run app.py                      # dashboard
python3 -m pytest -q                      # tests""")
    r.h2("Appendix B – Additional Screenshots")
    r.p(f"Figures {r.ref('f_ask')}–{r.ref('f_hist')} show the Ask, Track, Telemetry and History tabs referred to in "
        f"Section 7.6, and Figures {r.ref('f_power')}–{r.ref('f_flood')} further dashboard and simulator views.")
    r.figure(crop("ui_ask_s3.png"), "Ask tab (S3): an answer verified against the cited metrics", width_in=5.0,
             label="f_ask")
    r.figure(crop("ui_track_s3.png"), "Track tab (S3): planned route, flown path coloured by link quality",
             width_in=5.4, label="f_track")
    r.figure(crop("ui_telemetry_s3.png"), "Telemetry tab (S3): link strip, message rate and dropout table",
             width_in=5.4, label="f_tel")
    r.figure(crop("ui_history_s2_fixed.png"), "History tab (S2 fixed): baseline, trends and what worked before",
             width_in=5.4, label="f_hist")
    r.figure(crop("ui_power_s2.png"), "Power & attitude tab (S2)", width_in=5.0, label="f_power")
    r.figure(panel("flight", ["02_world_top_view.png", "03_hexa_x_on_launch_pad.png", "05_flood_zone.png",
                              "09_hexa_x_with_radio_mast.png"], 4.8),
             "More simulation views: (a) top view with zone signs; (b) Hexa-X on the launch pad; (c) flood zone; "
             "(d) passing the radio mast", width_in=4.8, label="f_more")
    r.figure(SIM / "10_hexa_x_over_collapsed_buildings.png", "Hexa-X over the collapsed buildings", width_in=4.0,
             label="f_collapse")
    r.figure(SIM / "06_flight_past_flood_zone.png", "Hexa-X flying past the flood zone", width_in=4.0,
             label="f_flood")
    r.h2("Appendix C – Sample Prompts")
    r.p(f"Table {r.ref('t_prompts')} lists the prompts used by the system (full text in `agents/prompts.py`).")
    r.table(["Sr. No.", "Prompt (abbreviated)", "Purpose"], [
        ["1", "You are a drone flight-test engineer… a verdict, one line per phase and a 3-sentence summary…",
         "Flight Summary"],
        ["2", "You are a telemetry radio engineer… for each dropout give its time, duration and nearest waypoint…",
         "Telemetry Link"],
        ["3", "You are a drone failure analyst… findings citing metric names and values… up to 3 root causes…",
         "Diagnosis"],
        ["4", "You are a mission risk assessor… adjust it by at most 10 points and explain why…", "Risk"],
        ["5", "You are a mission planner… edits from the allowed actions only, each tied to a cause…", "Advisor"],
        ["6", "You are the orchestrator… choose which agents run and in what order, with a reason each…", "Planner"],
    ], "Sample prompts", widths=[0.6, 4.3, 1.3], label="t_prompts")
    r.h2("Appendix D – Test Data")
    rows = []
    for run in RUNS:
        folder = ROOT / "data" / run
        if folder.is_dir():
            meta = json.loads((folder / "meta.json").read_text())
            rows.append([run, meta["title"], len(list(folder.glob("*.tlog"))), f"{meta['duration_s']:.0f}",
                         meta.get("parent_run") or "–"])
    r.p(f"Table {r.ref('t_data')} lists the flights used for testing (all under `data/`).")
    r.table(["Folder", "Scenario", "tlog files", "Flight s", "Parent"], rows, "Test data", widths=[1.0, 2.8, 0.8, 0.8, 0.8],
            label="t_data")

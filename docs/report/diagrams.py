"""Diagrams for the project report, drawn from the actual implementation.

    python3 docs/report/diagrams.py        # writes PNGs to docs/report/assets/

Graphviz (dot) for the architecture and flows; matplotlib for the route map, whose structures,
zones, mast and route are read from the project's own world file and scenario table.
"""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ASSETS = Path(__file__).resolve().parent / "assets"
DPI = "200"
FONT = "Times-Roman"

COMMON = f"""
  graph [fontname="{FONT}", fontsize=12, rankdir=TB, nodesep=0.35, ranksep=0.4, bgcolor=white, pad=0.2];
  node  [fontname="{FONT}", fontsize=12, shape=box, style="rounded,filled", fillcolor="#f4f6f8", color="#5b6b7f"];
  edge  [fontname="{FONT}", fontsize=10, color="#5b6b7f"];
"""

ARCHITECTURE = """digraph G {""" + COMMON + """
  rankdir=TB; newrank=true; ranksep=0.45;
  subgraph cluster_in { label="Inputs"; style="dashed"; color="#9aa8b8";
    tlog [label=".tlog file(s)\\n(MAVLink telemetry)"]; wpf [label="mission.waypoints"]; par [label="params.param"]; notes [label="pilot notes"]; }
  ingest [label="Ingestor  (tools/ingest.py)"];
  metrics [label="Metrics engine\\nmetrics · link_metrics · phases · anomalies · thresholds"];
  hist [label="history.json\\n(long-term memory)", shape=cylinder, fillcolor="#e8eef6"];
  memory [label="Memory store\\n(tools/memory.py)"];
  risk [label="Risk rules\\n(tools/risk_rules.py)"];
  state [label="Shared state (blackboard)\\nmetrics · history context · base risk", shape=note, fillcolor="#fff6dc"];
  orch [label="Orchestrator: manifest → LLM plan → rule check", fillcolor="#e3f1e8"];
  llm [label="LLM backend\\nClaude API · Ollama qwen2.5:3b", shape=component, fillcolor="#eee8f6"];
  subgraph cluster_agents { label="Agents, run in plan order on the shared state"; style="dashed"; color="#9aa8b8";
    fs [label="Flight Summary"]; tl [label="Telemetry Link"]; dg [label="Diagnosis"]; rk [label="Risk"]; ad [label="Advisor"];
    {rank=same; fs; tl; dg; rk; ad;} fs -> tl -> dg -> rk -> ad [style=invis]; }
  ver [label="Verifier (deterministic checks)", fillcolor="#fbe3e3"];
  approved [label="Approved set", shape=note, fillcolor="#fff6dc"];
  mio [label="Mission I/O\\n(hard limits)"];
  subgraph cluster_out { label="Outputs"; style="dashed"; color="#9aa8b8";
    dash [label="Streamlit dashboard\\n(8 tabs, Ask)"]; rep [label="report.html"]; fix [label="mission_fixed.waypoints\\nchangelog.md"]; }
  {tlog wpf par notes} -> ingest -> metrics -> state;
  {rank=same; memory; state; risk;}
  hist -> memory [dir=both]; memory -> state; risk -> state [dir=both];
  state -> orch; {rank=same; orch; llm;} orch -> llm [dir=both, style=dotted, label="plan; agent calls"];
  orch -> {fs tl dg rk ad};
  {fs tl dg rk ad} -> ver;
  ver -> orch [xlabel="re-run once if > 30 % rejected", style=dashed, color="#d64545", fontcolor="#d64545", constraint=false];
  ver -> approved; approved -> {dash rep}; approved -> mio -> fix;
  approved -> hist [label="causes, edits", style=dashed, constraint=false];
}"""

WORKFLOW = """digraph G {""" + COMMON + """
  s1 [label="1. User uploads a flight's files\\n(dashboard) or runs run.py"];
  s2 [label="2. Ingest: merge tlogs, vehicle messages only;\\nread mission, parameters, notes"];
  s3 [label="3. Compute metrics, statuses, health score;\\nphases, anomalies, link dropouts"];
  s4 [label="4. Memory: baselines, battery prediction,\\nrecurring issues; base risk score"];
  s5 [label="5. Orchestrator builds the manifest\\nand gets a plan (LLM, then rule check)"];
  s6 [label="6. Agents run in plan order on the shared state\\n(each: prompt + JSON schema → output)"];
  s7 [label="7. Verifier checks every claim\\nagainst the computed data"];
  d1 [label="> 30 % of an agent's\\nclaims rejected?", shape=diamond, fillcolor="#fff6dc"];
  s8 [label="8. Re-run that agent once\\nwith the rejection reasons"];
  s9 [label="9. Approved set: rejected items\\nreplaced by rule-based results"];
  s10 [label="10. Mission I/O applies edits within limits;\\nstate.json, report.html, fixed mission, history"];
  s11 [label="11. Dashboard shows the result;\\nAsk answers questions from it"];
  s1 -> s2 -> s3 -> s4 -> s5 -> s6 -> s7 -> d1;
  d1 -> s8 [label="yes"]; s8 -> s7 [label="verify again"]; d1 -> s9 [label="no"];
  s9 -> s10 -> s11;
}"""

ORCHESTRATION = """digraph G {""" + COMMON + """
  man [label="Manifest\\ninputs present · statuses · problems\\nlink all good? · flights in history"];
  call [label="One LLM call\\n(PLANNER prompt, Plan schema)"];
  ok [label="Call succeeded?", shape=diamond, fillcolor="#fff6dc"];
  chk [label="checked_plan(): summary first, verifier last,\\ndiagnosis only with problems, required agents added,\\nduplicates removed, dependency order"];
  def [label="default_plan(): rule-based plan"];
  run [label="For each step: run_agent()\\nLLM (2 attempts) → guard() → or fallback()"];
  tlr [label="Link all good:\\none-line rule result, no LLM call", fillcolor="#e3f1e8"];
  ver [label="verify() → rejection rate per agent"];
  rr [label="Re-run agents above 30 %\\nwith feedback; verify again"];
  ap [label="approve(): drop rejected items,\\nrefill from rules, final edits checked\\nagainst the approved diagnosis"];
  man -> call -> ok; ok -> chk [label="yes"]; ok -> def [label="no"];
  {chk def} -> run; run -> tlr [style=dashed, label="telemetry_link"]; run -> ver -> rr -> ap;
}"""

SIMULATION = """digraph G {""" + COMMON + """
  rankdir=LR;
  gz [label="Gazebo Harmonic\\ndisaster world + Hexa-X\\n(ApplyLinkWrench = wind)"];
  sitl [label="ArduCopter SITL\\n(JSON backend)\\nbattery.lua · EKF3 drag fusion"];
  mp [label="MAVProxy"];
  cap [label="capture.py\\n(recording ground station)\\nlink faults: timed · zone · loss"];
  fly [label="fly_scenario.py\\nparams · mission upload ·\\narm · AUTO · wind on/off"];
  qgc [label="any GCS (optional)"];
  data [label="data/<scenario>/\\n*.tlog · mission · params\\ntruth.json · meta.json", shape=folder, fillcolor="#e8eef6"];
  gz -> sitl [dir=both, label="JSON / UDP 9002"]; sitl -> mp [label="TCP 5760"];
  mp -> cap [label="UDP 14560"]; mp -> fly [label="UDP 14562", dir=both]; mp -> qgc [label="UDP 14550"];
  cap -> data; fly -> data;
}"""


def dot(name: str, source: str) -> None:
    out = ASSETS / f"{name}.png"
    subprocess.run(["dot", "-Tpng", f"-Gdpi={DPI}", "-o", str(out)], input=source.encode(), check=True)
    print("wrote", out.name)


def route_map() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from sim import scenarios, world, zones

    plt.rcParams["font.family"] = "serif"
    root = ET.parse(world.DEFAULT_WORLD).getroot().find("world")
    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=200)
    xs, ys = [], []
    for include in root.iter("include"):
        uri, pose = include.findtext("uri") or "", include.findtext("pose")
        if not pose or not re.search(r"building|collapsed|tower", uri):
            continue
        x, y = (float(v) for v in pose.split()[:2])
        xs.append(x)
        ys.append(y)
    ax.scatter(xs, ys, s=14, marker="s", color="#9aa8b8", label="structures (from the world file)", zorder=1)
    for name, (area, lost) in zones.ZONES.items():
        if zones.NETWORK in lost:
            ax.add_patch(Rectangle((area.min_x, area.min_y), area.max_x - area.min_x, area.max_y - area.min_y,
                                   fill=True, alpha=0.15, color="#d64545", zorder=0))
            ax.text(area.min_x + 2, area.max_y + 3, f"no network: {name}", fontsize=7, color="#a33")
    route = scenarios.load_route()
    pad = world.spawn_pose(world.DEFAULT_WORLD)[:2]
    pts = [pad] + list(route.waypoints) + [pad]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color="#2e6fb7", lw=1.6, ms=4, label="demo route, 30 m", zorder=3)
    for k, (x, y) in enumerate(route.waypoints):
        ax.annotate(f"WP{k + 3}", (x, y), textcoords="offset points", xytext=(5, 4), fontsize=8, color="#2e6fb7")
    ax.scatter([pad[0]], [pad[1]], marker="^", s=80, color="#2e9e5b", label="pad (home)", zorder=4)
    ax.scatter([-40], [60], marker="X", s=90, color="#d64545", label="radio mast, 44 m", zorder=4)
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=7)
    fig.tight_layout()
    fig.savefig(ASSETS / "route_map.png")
    print("wrote route_map.png")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    dot("architecture", ARCHITECTURE)
    dot("workflow", WORKFLOW)
    dot("orchestration", ORCHESTRATION)
    dot("simulation", SIMULATION)
    route_map()
    return 0


if __name__ == "__main__":
    sys.exit(main())

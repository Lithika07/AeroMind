"""The orchestrator: manifest -> plan -> run -> verify -> self-correct (PRD "Intelligent orchestrator").

The plan comes from one short LLM call and is checked against the rules here; if the call fails, or
the plan breaks a rule, the rule-based plan runs. Agents share one state (a blackboard) and each adds
its output. If the Verifier rejects more than 30 % of an agent's claims, that agent runs once more
with the rejection reasons. Only Verifier-approved content reaches the approved set.
"""
import time

from agents import fallbacks, prompts, verifier
from tools import mission_io
from agents.base import AgentResult, run_agent
from agents.llm import LLMError
from agents.schemas import (AdvisorOut, DiagnosisOut, FlightSummaryOut, Plan, PlanStep, RiskOut, TelemetryLinkOut)

RERUN_ABOVE = 0.3
ORDER = ("flight_summary", "telemetry_link", "diagnosis", "risk", "advisor", "verifier")
LINK_KEYS = ("link_uptime", "dropouts", "packet_loss", "position_rate")


def manifest(state: dict) -> dict:
    status = state["metrics"]["status"]
    return {
        "inputs": {"tlog_files": len(state["sources"]["tlogs"]), "mission": bool(state["sources"]["mission"]),
                   "params": bool(state["sources"]["params"]), "pilot_notes": bool(state.get("notes"))},
        "statuses": status,
        "problems": sorted(k for k, v in status.items() if v != "good"),
        "link_all_good": all(status.get(k, "good") == "good" for k in LINK_KEYS),
        "history_flights": state["history"]["flights"],
        "dropouts": len(state["metrics"]["link"]["dropouts"]),
    }


def default_plan(man: dict) -> Plan:
    steps = [PlanStep(agent="flight_summary", reason="always first")]
    steps.append(PlanStep(agent="telemetry_link", reason="link healthy: one-line result" if man["link_all_good"]
                          else f"{man['dropouts']} dropout(s); link metrics need analysis"))
    if man["problems"]:
        steps.append(PlanStep(agent="diagnosis", reason=f"{len(man['problems'])} metric(s) caution/bad: "
                              f"{', '.join(man['problems'][:4])}"))
    steps.append(PlanStep(agent="risk", reason=f"history has {man['history_flights']} flight(s)"
                          + ("; confidence low" if man["history_flights"] < 3 else "")))
    steps.append(PlanStep(agent="advisor", reason="mission file present: edits allowed" if man["inputs"]["mission"]
                          else "no mission file: advice only"))
    steps.append(PlanStep(agent="verifier", reason="always last"))
    return Plan(plan=steps, source="default")


def checked_plan(plan: Plan, man: dict) -> Plan:
    """The LLM plan made to follow the rules: summary first, verifier last, diagnosis only with problems,
    every required agent present, no duplicates, in the dependency order."""
    reasons = {}
    for step in plan.plan:
        reasons.setdefault(step.agent, step.reason)
    required = {"flight_summary", "telemetry_link", "risk", "advisor", "verifier"}
    if man["problems"]:
        required.add("diagnosis")
    else:
        reasons.pop("diagnosis", None)
    fallback_reasons = {s.agent: s.reason for s in default_plan(man).plan}
    steps = [PlanStep(agent=a, reason=reasons.get(a) or f"{fallback_reasons[a]} (added by rule)")
             for a in ORDER if a in required]
    return Plan(plan=steps, source="llm")


def plan_for(state: dict, backend) -> tuple:
    man = manifest(state)
    if backend is None:
        return default_plan(man), man, None
    try:
        proposal = backend.complete(prompts.PLANNER, verifier_safe_json(man), Plan)
        return checked_plan(proposal, man), man, None
    except (LLMError, ValueError) as error:
        return default_plan(man), man, str(error)[:300]


def verifier_safe_json(data: dict) -> str:
    import json
    return json.dumps(data, separators=(",", ":"))


def _fallback_for(name: str, state: dict, outputs: dict, mission):
    if name == "flight_summary":
        return lambda: fallbacks.flight_summary(state)
    if name == "telemetry_link":
        return lambda: fallbacks.telemetry_link(state)
    if name == "diagnosis":
        return lambda: fallbacks.diagnosis(state)
    if name == "risk":
        return lambda: fallbacks.risk(state)
    if name == "advisor":
        diagnosis = DiagnosisOut.model_validate(outputs.get("diagnosis") or {"findings": [], "causes": []})
        return lambda: fallbacks.advisor(state, mission, diagnosis)
    raise ValueError(name)


def _run(name, state, outputs, backend, mission, link_all_good, feedback=None) -> AgentResult:
    if name == "telemetry_link" and link_all_good:
        return AgentResult(name, fallbacks.telemetry_link(state), "rule")
    return run_agent(name, state, outputs, backend, _fallback_for(name, state, outputs, mission), mission, feedback)


def _rejected(result, agent: str) -> dict:
    return {v.claim_id: v.reason for v in result.verdicts if v.agent == agent and v.status == "rejected"}


def approve(outputs: dict, check, state: dict, mission) -> dict:
    """The outputs with every rejected item removed, refilled from the rule-based fallbacks."""
    approved = {}
    if "flight_summary" in outputs:
        out, bad, rule = outputs["flight_summary"], _rejected(check, "flight_summary"), fallbacks.flight_summary(state)
        rule_story = {line.phase: line for line in rule.flight_story}
        story = [line if f"story[{k}]" not in bad else rule_story.get(line["phase"])
                 for k, line in enumerate(out["flight_story"])]
        approved["flight_summary"] = FlightSummaryOut(
            verdict=out["verdict"], summary=out["summary"] if "summary" not in bad else rule.summary,
            flight_story=[s for s in story if s is not None],
            claims=[c for c in out.get("claims", []) if c["id"] not in bad]).model_dump()
    if "telemetry_link" in outputs:
        out, bad = outputs["telemetry_link"], _rejected(check, "telemetry_link")
        findings = [f for f in out["link_findings"] if f["id"] not in bad] or \
            [f.model_dump() for f in fallbacks.telemetry_link(state).link_findings]
        approved["telemetry_link"] = TelemetryLinkOut(**{**out, "link_findings": findings}).model_dump()
    if "diagnosis" in outputs:
        out, bad = outputs["diagnosis"], _rejected(check, "diagnosis")
        causes = [c for c in out["causes"] if c["id"] not in bad]
        diagnosis = DiagnosisOut(findings=[f for f in out["findings"] if f["id"] not in bad], causes=causes) \
            if causes else fallbacks.diagnosis(state)
        approved["diagnosis"] = diagnosis.model_dump()
    if "risk" in outputs:
        out, bad = outputs["risk"], _rejected(check, "risk")
        approved["risk"] = (fallbacks.risk(state) if bad else RiskOut.model_validate(out)).model_dump()
    if "advisor" in outputs:
        out, bad = outputs["advisor"], _rejected(check, "advisor")
        kept = [r for r in out["recommendations"] if f"rec[{r['rank']}]" not in bad]
        diagnosis = DiagnosisOut.model_validate(approved.get("diagnosis") or {"findings": [], "causes": []})
        for rule_rec in fallbacks.advisor(state, mission, diagnosis).recommendations:
            if len(kept) >= 3:
                break
            if all(rule_rec.text != r["text"] for r in kept):
                kept.append(rule_rec.model_dump())
        recs = [{**r, "rank": k + 1} for k, r in enumerate(kept[:3])]
        approved["advisor"] = AdvisorOut(edits=out["edits"], recommendations=recs).model_dump()
    return approved


def edit_numbers(outputs: dict) -> list:
    advisor = outputs.get("advisor") or {}
    return [float(e["value"]) for e in advisor.get("edits", []) if e.get("value") is not None] + \
        [float(e["wp"]) for e in advisor.get("edits", [])] + [fallbacks.SAFE_SPEED_MS]


def check_edits(outputs: dict, results: dict, state: dict, mission) -> dict:
    """Keep the Advisor's edits that pass the mission limits; if none of an LLM's edits do and the
    rules have valid ones, use those. Returns what was dropped, for the Agents tab."""
    advisor = outputs.get("advisor")
    if not advisor or not mission:
        return {}
    diagnosis = outputs.get("diagnosis") or {"findings": [], "causes": []}
    cause_ids = {c["id"] for c in diagnosis["causes"]}
    advice_only = {c["id"] for c in diagnosis["causes"] if c["category"] == "link_loss"}
    edits = AdvisorOut.model_validate(advisor).edits
    _, applied, rejected = mission_io.apply_edits(mission, edits, cause_ids, advice_only)
    kept = [a["edit"] for a in applied]
    replaced = False
    if not kept and results["advisor"].source == "llm":
        rule = fallbacks.advisor(state, mission, DiagnosisOut.model_validate(diagnosis))
        _, rule_applied, _ = mission_io.apply_edits(mission, rule.edits, cause_ids, advice_only)
        kept, replaced = [a["edit"] for a in rule_applied], bool(rule_applied)
    outputs["advisor"] = {**advisor, "edits": kept}
    return {"dropped": rejected, "replaced_by_rules": replaced}


def run(state: dict, backend, mission=None) -> dict:
    started = time.monotonic()
    plan, man, plan_error = plan_for(state, backend)
    outputs, results = {}, {}
    for step in plan.plan:
        if step.agent == "verifier":
            continue
        result = _run(step.agent, state, outputs, backend, mission, man["link_all_good"])
        results[step.agent] = result
        outputs[step.agent] = result.output.model_dump()
    edit_check = check_edits(outputs, results, state, mission)
    check = verifier.verify(outputs, state, edit_numbers(outputs))
    rates = verifier.rejection_rates(check)
    reruns = []
    for agent, rate in rates.items():
        if rate > RERUN_ABOVE and results[agent].source == "llm":
            reasons = "; ".join(f"{k}: {v}" for k, v in _rejected(check, agent).items())
            result = _run(agent, state, outputs, backend, mission, man["link_all_good"], feedback=reasons)
            results[agent] = result
            outputs[agent] = result.output.model_dump()
            if agent == "advisor":
                edit_check = check_edits(outputs, results, state, mission)
            reruns.append({"agent": agent, "rejection_rate": rate, "feedback": reasons})
    if reruns:
        check = verifier.verify(outputs, state, edit_numbers(outputs))
        rates = verifier.rejection_rates(check)
    claims = len(check.verdicts)
    rejected = sum(v.status == "rejected" for v in check.verdicts)
    return {
        "manifest": man,
        "plan": plan.model_dump(),
        "plan_error": plan_error,
        "backend": getattr(backend, "name", "none"),
        "model": getattr(backend, "model", None),
        "agents": {name: r.as_dict() for name, r in results.items()},
        "verification": {"verdicts": [v.model_dump() for v in check.verdicts], "rejection_rates": rates,
                         "reruns": reruns, "claims": claims, "rejected": rejected,
                         "grounding_rate": round(rejected / claims, 3) if claims else 0.0},
        "edit_check": edit_check,
        "approved": approve(outputs, check, state, mission),
        "seconds": round(time.monotonic() - started, 1),
    }

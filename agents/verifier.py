"""The Verifier: every claim an agent makes must be backed by the computed data.

Checks are exact, not judged by a model: a claim must cite a metric that exists, and its value must
match; a number with a unit written in free text (story lines, summary, recommendations) must match
some value AeroMind computed or proposed. Whatever fails is rejected with its reason.
"""
import re

from agents.schemas import ClaimVerdict, VerifierOut

PATH_PART = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")
BARE_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?")   # not part of an id like F5 or WP3
NUMBER_WITH_UNIT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(m/s|%|°|deg|s\b|m\b|km\b|mAh)")
REL_TOLERANCE = 0.05
ABS_TOLERANCE = 0.15


def resolve(data, path: str):
    """(found, value) for a dotted path like link.dropouts[0].duration_s."""
    current = data
    for part in path.split("."):
        match = PATH_PART.fullmatch(part)
        if not match or not isinstance(current, dict) or match.group(1) not in current:
            return False, None
        current = current[match.group(1)]
        if match.group(2) is not None:
            index = int(match.group(2))
            if not isinstance(current, list) or index >= len(current):
                return False, None
            current = current[index]
    return True, current


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(REL_TOLERANCE * abs(b), ABS_TOLERANCE)


def numbers(data) -> list:
    """Every number in a nested structure (and list lengths, which claims count)."""
    if isinstance(data, bool) or data is None:
        return []
    if isinstance(data, (int, float)):
        return [float(data)]
    if isinstance(data, dict):
        return [n for v in data.values() for n in numbers(v)]
    if isinstance(data, list):
        return [float(len(data))] + [n for v in data for n in numbers(v)]
    return []


def evidence(state: dict) -> dict:
    """What a claim may cite: the metrics, plus the parameters flown."""
    return {**state["metrics"], "params": state.get("params") or {}}


def derived(metrics: dict) -> list:
    """Numbers computed from the metrics that agents may quote: phase and leg durations."""
    spans = [p["t_end"] - p["t_start"] for p in metrics["phases"]]
    spans += [leg["t_end"] - leg["t_start"] for leg in metrics["tracking"]["legs"]]
    return [round(v, 1) for v in spans]


def check_claim(claim: dict, metrics: dict) -> str:
    """'' if the claim is supported, else the reason it is not."""
    if not claim.get("metric"):
        return "" if not NUMBER_WITH_UNIT.search(claim["text"]) else "states a number without citing a metric"
    found, actual = resolve(metrics, claim["metric"])
    if not found:
        return f"metric {claim['metric']} does not exist"
    value = claim.get("value")
    if value is None or isinstance(value, str):
        return ""
    if isinstance(actual, list):
        actual = len(actual)
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return f"metric {claim['metric']} is not a number"
    return "" if close(float(value), float(actual)) else f"value {value} does not match {claim['metric']} = {actual}"


MAX_SUMMARY_SENTENCES = 3
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def check_text(text: str, known: list, require_number: bool = False) -> str:
    found = NUMBER_WITH_UNIT.findall(text)
    if require_number and not BARE_NUMBER.search(text):
        return "gives no number from the flight data as evidence"
    for raw, unit in found:
        value = float(raw)
        if not any(close(value, k) for k in known):
            return f"'{raw} {unit}' is not in the flight data"
    return ""


EDIT_MENTION = re.compile(r"(set_speed|change_altitude|remove_waypoint|add_hold).*?WP\s?(\d+)")


def check_edit_mentions(text: str, kept: set) -> str:
    """A recommendation may only name a mission edit that passed the mission limits."""
    for action, seq in EDIT_MENTION.findall(text):
        if (action, int(seq)) not in kept:
            return f"proposes {action} at WP{seq}, which failed the mission limits"
    return ""


#: A lower score must say what lowers the risk; "the risk is significant" is a reason to raise it.
MITIGATION_WORDS = ("mitigat", "overstat", "already", "fixed", "resolved", "improv", "shorter", "lower than",
                    "less than", "no longer", "safer", "within limit", "not recur", "margin is", "enough")


def check_adjustment(risk: dict) -> str:
    reason = risk["adjustment_reason"].lower()
    if risk["adjustment"] < 0 and not any(word in reason for word in MITIGATION_WORDS):
        return "lowers the risk without naming anything that reduces it"
    return ""


def _verdict(agent, claim_id, reason) -> ClaimVerdict:
    return ClaimVerdict(agent=agent, claim_id=claim_id, status="rejected" if reason else "supported",
                        reason=reason or "matches the data")


def verify(outputs: dict, state: dict, extra_numbers: list = ()) -> VerifierOut:
    """Verdicts for every claim and every number in the agents' outputs."""
    metrics = evidence(state)
    known = (numbers(metrics) + derived(state["metrics"]) + numbers(state.get("risk_base"))
             + numbers(state.get("history")) + list(extra_numbers))
    verdicts = []
    summary = outputs.get("flight_summary")
    if summary:
        sentences = len(SENTENCE_END.findall(summary["summary"].strip() + " "))
        too_long = f"{sentences} sentences; the summary must be 3" if sentences > MAX_SUMMARY_SENTENCES else ""
        verdicts.append(_verdict("flight_summary", "summary", too_long or check_text(summary["summary"], known)))
        statuses = {line.phase: line.status for line in phase_statuses(state)}
        for k, line in enumerate(summary["flight_story"]):
            expected = statuses.get(line["phase"])
            reason = (f"phase {line['phase']} is not in this flight" if expected is None else
                      f"status {line['status']} disagrees with the data ({expected})" if line["status"] != expected
                      else check_text(line["text"], known))
            verdicts.append(_verdict("flight_summary", f"story[{k}]", reason))
        for claim in summary.get("claims", []):
            verdicts.append(_verdict("flight_summary", claim["id"], check_claim(claim, metrics)))
    link = outputs.get("telemetry_link")
    if link:
        for claim in link["link_findings"]:
            reason = check_claim(claim, metrics) or check_text(claim["text"], known)
            verdicts.append(_verdict("telemetry_link", claim["id"], reason))
    diagnosis = outputs.get("diagnosis")
    if diagnosis:
        finding_ids = {f["id"] for f in diagnosis["findings"]}
        for claim in diagnosis["findings"]:
            verdicts.append(_verdict("diagnosis", claim["id"], check_claim(claim, metrics)))
        for cause in diagnosis["causes"]:
            missing = [f for f in cause["findings"] if f not in finding_ids]
            reason = f"cites unknown findings {missing}" if missing else ("" if cause["findings"] else "cites no finding")
            verdicts.append(_verdict("diagnosis", cause["id"], reason))
    risk = outputs.get("risk")
    if risk:
        verdicts.append(_verdict("risk", "adjustment_reason",
                                 check_adjustment(risk) or check_text(risk["adjustment_reason"], known)))
    advisor = outputs.get("advisor")
    if advisor:
        kept = {(e["action"], e["wp"]) for e in advisor["edits"]}
        for rec in advisor["recommendations"]:
            reason = (check_edit_mentions(rec["text"], kept) or check_text(rec["text"], known)
                      or check_text(rec["evidence"], known, require_number=True))
            verdicts.append(_verdict("advisor", f"rec[{rec['rank']}]", reason))
    return VerifierOut(verdicts=verdicts)


def phase_statuses(state: dict) -> list:
    from agents.fallbacks import story
    return story(state["metrics"])


def rejection_rates(result: VerifierOut) -> dict:
    totals, rejected = {}, {}
    for v in result.verdicts:
        totals[v.agent] = totals.get(v.agent, 0) + 1
        rejected[v.agent] = rejected.get(v.agent, 0) + (v.status == "rejected")
    return {agent: round(rejected[agent] / totals[agent], 2) for agent in totals}

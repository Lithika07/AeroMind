"""Ask about this flight: answered from the metrics and the approved agent outputs, never from the
raw log. An LLM answer must cite metric paths that exist and quote only numbers in the data; one
that does not is replaced by an answer assembled from the approved results."""
import json

from pydantic import BaseModel

from agents import verifier

MAX_QUESTION_CHARS = 500
SYSTEM = ("You answer a pilot's question about one drone flight using only the JSON given. Cite the metric "
          "paths you used (dotted, e.g. link.dropouts[0].duration_s) in `citations`. Copy numbers exactly; "
          "if the data does not answer the question, say so. Two or three sentences.")


class AskOut(BaseModel):
    answer: str
    citations: list[str]


TOPICS = (
    (("link", "signal", "dropout", "telemetry", "radio", "connection"), "telemetry_link"),
    (("battery", "power", "voltage", "current", "energy"), "battery"),
    (("wind", "drift", "track", "cross", "speed"), "tracking"),
    (("risk", "next", "safe"), "risk"),
    (("fix", "improve", "recommend", "change", "should"), "advisor"),
)


def _context(state: dict) -> dict:
    m = state["metrics"]
    approved = state["agents"]["approved"]
    return {"metrics": {k: m[k] for k in ("flight", "battery", "tracking", "wind", "attitude", "gps", "link",
                                          "status", "health_score", "events")},
            "verdict": approved["flight_summary"]["verdict"], "summary": approved["flight_summary"]["summary"],
            "causes": approved.get("diagnosis", {}).get("causes", []), "risk": approved["risk"],
            "recommendations": approved["advisor"]["recommendations"], "pilot_notes": state.get("notes")}


def _check(answer: AskOut, state: dict) -> str:
    data = verifier.evidence(state)
    bad = [c for c in answer.citations if not verifier.resolve(data, c)[0]]
    if bad:
        return f"citations that do not exist: {bad}"
    if not answer.citations:
        return "no metric cited"
    # numbers in the answer must come from the metrics it cites, not from anywhere in the flight
    known = verifier.merge(*(verifier.pools_at(data, c) for c in answer.citations))
    return verifier.check_text(answer.answer, known)


def rule_answer(question: str, state: dict) -> dict:
    m = state["metrics"]
    approved = state["agents"]["approved"]
    q = question.lower()
    topic = next((t for words, t in TOPICS if any(w in q for w in words)), "summary")
    causes = approved.get("diagnosis", {}).get("causes", [])
    if topic == "telemetry_link":
        findings = approved["telemetry_link"]["link_findings"]
        return {"answer": " ".join(f["text"] + "." for f in findings),
                "citations": [f["metric"] for f in findings if f.get("metric")]}
    if topic == "battery":
        b = m["battery"]
        cause = next((c["cause"] for c in causes if c["category"] == "low_battery"), None)
        text = (f"The battery went from {b['remaining_start_pct']:.0f} % to {b['remaining_end_pct']:.0f} %, "
                f"{b['used_pct_per_km']} % per km.") if b["remaining_end_pct"] is not None else "Battery was not reported."
        return {"answer": f"{text} {cause + '.' if cause else ''}".strip(),
                "citations": ["battery.remaining_end_pct", "battery.used_pct_per_km"]}
    if topic == "tracking":
        cause = next((c["cause"] for c in causes if c["category"] in ("wind_drift", "speed_too_high")), None)
        text = f"Cross-track error peaked at {m['tracking']['xtrack_max_m']} m with wind up to {m['wind']['max_ms']} m/s."
        return {"answer": f"{text} {cause + '.' if cause else ''}".strip(),
                "citations": ["tracking.xtrack_max_m", "wind.max_ms"]}
    if topic == "risk":
        r = approved["risk"]
        return {"answer": f"Next-mission risk is {r['risk_level']} ({r['risk_score']}): {'; '.join(r['factors']) or 'no risk factors'}.",
                "citations": []}
    if topic == "advisor":
        return {"answer": " ".join(f"{r['rank']}. {r['text']}." for r in approved["advisor"]["recommendations"]),
                "citations": []}
    return {"answer": approved["flight_summary"]["summary"], "citations": ["health_score"]}


def answer(question: str, state: dict, backend) -> dict:
    question = " ".join(question.split())[:MAX_QUESTION_CHARS]
    note = None
    if backend is not None:
        user = json.dumps({"question": question, "flight": _context(state)}, separators=(",", ":"), default=str)
        for _ in range(2):
            try:
                reply = backend.complete(SYSTEM, user, AskOut)
            except Exception as error:  # LLMError or anything unexpected: answer from the rules
                note = f"LLM unavailable: {str(error)[:200]}"
                break
            problem = _check(reply, state)
            if not problem:
                return {**reply.model_dump(), "source": "llm", "verified": True, "note": None}
            note = f"LLM answer rejected ({problem})"
            user += f"\nYour previous answer was rejected: {problem}. Answer again from the data."
    return {**rule_answer(question, state), "source": "rules", "verified": True, "note": note}

"""run_agent: one LLM call with a JSON schema, one retry on a bad answer, then the rule-based fallback.

Afterwards a guard puts back what Python owns: the risk score is base + adjustment, the link verdict
follows the link statuses, and there are no mission edits without a mission.
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, ValidationError

from agents import context, prompts
from agents.llm import LLMError
from agents.schemas import AGENT_OUTPUTS
from tools import risk_rules

ATTEMPTS = 2


@dataclass(frozen=True)
class AgentResult:
    name: str
    output: BaseModel
    source: str                     # "llm", "fallback" or "rule"
    seconds: float = 0.0
    errors: tuple = ()
    feedback: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"output": self.output.model_dump(), "source": self.source, "seconds": self.seconds,
                "errors": list(self.errors), "feedback": self.feedback}


def guard(name: str, output: BaseModel, state: dict, has_mission: bool) -> BaseModel:
    if name == "risk":
        base = state["risk_base"]
        score = max(0, min(risk_rules.MAX_SCORE, base["score"] + output.adjustment))
        return output.model_copy(update={
            "risk_score": score, "risk_level": risk_rules.level(score), "factors": [f["factor"] for f in base["factors"]],
            "predicted_battery_pct": state["history"]["battery_prediction"]["predicted_end_pct"],
            "confidence": base["confidence"]})
    if name == "telemetry_link":
        from agents import hints
        verdict = hints.worst(state["metrics"]["status"], "dropouts", "link_uptime", "packet_loss", "position_rate")
        return output.model_copy(update={"link_verdict": verdict, "safe_for_mission": verdict != "bad"})
    if name == "advisor" and not has_mission:
        return output.model_copy(update={"edits": []})
    if name == "flight_summary":
        from agents.fallbacks import verdict
        levels = ["Good", "Needs attention", "Unsafe"]
        rule = verdict(state["metrics"])
        if levels.index(output.verdict) < levels.index(rule) or levels.index(output.verdict) - levels.index(rule) > 1:
            return output.model_copy(update={"verdict": rule})   # never milder than the data, at most one step harsher
    return output


def run_agent(name: str, state: dict, outputs: dict, backend, fallback, mission=None,
              feedback: Optional[str] = None) -> AgentResult:
    """The agent's output: from the LLM when it answers validly, otherwise from `fallback()`."""
    started = time.monotonic()
    errors = []
    if backend is not None:
        user = context.to_prompt(context.build(name, state, outputs, mission))
        if feedback:
            user += f"\nYour previous answer was rejected by the verifier: {feedback}. Fix exactly these points."
        for _ in range(ATTEMPTS):
            try:
                answer = backend.complete(prompts.SYSTEM_PROMPTS[name], user, AGENT_OUTPUTS[name])
                output = guard(name, answer, state, bool(mission))
                return AgentResult(name, output, "llm", round(time.monotonic() - started, 2), tuple(errors), feedback)
            except (LLMError, ValidationError) as error:
                errors.append(str(error)[:300])
            except Exception as error:  # an unexpected backend failure must not stop the analysis
                errors.append(f"{type(error).__name__}: {str(error)[:280]}")
                break
                user += f"\nYour previous reply was invalid: {str(error)[:300]}. Reply again with valid JSON."
    output = guard(name, fallback(), state, bool(mission))
    return AgentResult(name, output, "fallback", round(time.monotonic() - started, 2), tuple(errors), feedback)

import pytest

from dashboard import ask
from tests.agents.conftest import FakeBackend


@pytest.fixture(scope="module")
def s3_state(states):
    state, mission = states.get("s3") or pytest.skip("s3 not flown")
    from agents import orchestrator
    return {**state, "agents": orchestrator.run(state, None, mission)}


@pytest.mark.parametrize("question, expect", [
    ("why did the link drop?", "Link lost"),
    ("how was the battery?", "battery went from"),
    ("what should I change?", "1. "),
    ("how risky is the next mission", "risk is"),
    ("tell me about it", "The flight lasted"),
])
def test_rule_answers_by_topic(s3_state, question, expect):
    reply = ask.answer(question, s3_state, None)
    assert expect in reply["answer"] and reply["source"] == "rules"


def test_llm_answer_with_valid_citation_is_used(s3_state):
    uptime = s3_state["metrics"]["link"]["uptime_pct"]
    backend = FakeBackend({"AskOut": [{"answer": f"Uptime was {uptime} %.", "citations": ["link.uptime_pct"]}]})
    reply = ask.answer("link?", s3_state, backend)
    assert reply["source"] == "llm" and reply["citations"] == ["link.uptime_pct"]


def test_llm_answer_with_invented_numbers_falls_back_to_rules(s3_state):
    backend = FakeBackend({"AskOut": [{"answer": "The link was lost for 47 s.", "citations": ["link.uptime_pct"]}]})
    reply = ask.answer("why did the link drop?", s3_state, backend)
    assert reply["source"] == "rules" and "47 s" in reply["note"]


def test_llm_answer_citing_nothing_real_is_rejected(s3_state):
    backend = FakeBackend({"AskOut": [{"answer": "It was fine.", "citations": ["link.magic"]}]})
    assert ask.answer("link?", s3_state, backend)["source"] == "rules"

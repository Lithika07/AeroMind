from pathlib import Path

import pytest

from tools import analysis
from tools import waypoints as wp

DATA = Path(__file__).resolve().parents[2] / "data"


def flight_state(run: str, history: Path):
    folder = DATA / run
    if not folder.is_dir():
        pytest.skip(f"{run} not flown")
    state = analysis.analyse(run, sorted(folder.glob("*.tlog")), history, folder / "mission.waypoints",
                             folder / "params.param")
    return state, wp.load(folder / "mission.waypoints")


@pytest.fixture(scope="session")
def states(tmp_path_factory):
    """Real states for every flown scenario, analysed in order into one history."""
    history = tmp_path_factory.mktemp("history") / "history.json"
    found = {}
    for run in ("s0", "s1", "s2", "s3", "s4"):
        if (DATA / run).is_dir():
            found[run] = flight_state(run, history)
    if not found:
        pytest.skip("no flights in data/")
    return found


class FakeBackend:
    """Answers from a script: callables (agent name, output model) -> model instance, or exceptions."""
    name = "fake"
    model = "fake-1"

    def __init__(self, answers: dict):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.calls = []

    def complete(self, system, user, output):
        key = output.__name__
        self.calls.append((key, user))
        queue = self.answers.get(key)
        if not queue:
            from agents.llm import LLMError
            raise LLMError(f"no scripted answer for {key}")
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return output.model_validate(answer)

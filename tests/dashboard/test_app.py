"""Every tab of the dashboard renders on each saved run (skipped until runs are analysed)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNS = sorted(p.name for p in (ROOT / "outputs").glob("*") if (p / "state.json").exists())


@pytest.mark.skipif(not RUNS, reason="no analysed runs in outputs/")
@pytest.mark.parametrize("run", RUNS)
def test_every_tab_renders(run):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.session_state["run"] = run
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert [t.label for t in at.tabs][:8] == ["Summary", "Track", "Telemetry", "Anomalies", "Power & attitude",
                                              "History", "Agents", "Ask"]

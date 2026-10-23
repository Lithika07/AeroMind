"""Capture the dashboard screenshots used in the project report, from the real running app.

    python3 docs/report/screenshots.py

Starts the Streamlit dashboard and a headless Chrome, drives Chrome over the DevTools protocol
(no Playwright needed) and writes PNGs to docs/report/assets/. Runs from outputs/ must exist.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent / "assets"
APP_PORT = 8601
CDP_PORT = 9333
CHROME = os.environ.get("CHROME", str(Path.home() / ".cache/ms-playwright/chromium-1223/chrome-linux64/chrome"))
WIDTH = 1440
TABS = ["Summary", "Track", "Telemetry", "Anomalies", "Power & attitude", "History", "Agents", "Ask"]


class Page:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=120, suppress_origin=True)
        self.next_id = 0

    def send(self, method: str, **params):
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def js(self, expression: str):
        return self.send("Runtime.evaluate", expression=expression, returnByValue=True).get("result", {}).get("value")

    def wait_for(self, expression: str, timeout: float = 90.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.js(expression):
                return
            time.sleep(0.5)
        raise TimeoutError(expression)

    def settle(self, timeout: float = 120.0) -> None:
        """Until Streamlit has stopped running the script (its status widget shows 'Running')."""
        time.sleep(1.5)
        self.wait_for("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout)
        time.sleep(1.5)

    def shot(self, name: str, height: int) -> None:
        self.send("Emulation.setDeviceMetricsOverride", width=WIDTH, height=height, deviceScaleFactor=1, mobile=False)
        time.sleep(2.0)
        data = self.send("Page.captureScreenshot", format="png")["data"]
        (ASSETS / name).write_bytes(base64.b64decode(data))
        print("wrote", name)


def open_run(page: Page, run: str, tab: str) -> None:
    page.send("Page.navigate", url=f"http://127.0.0.1:{APP_PORT}/?run={run}")
    page.wait_for("document.querySelectorAll('button[role=tab]').length >= 8")
    page.settle()
    index = TABS.index(tab)
    page.js(f"document.querySelectorAll('button[role=tab]')[{index}].click()")
    page.settle()
    time.sleep(3.0)          # plotly / map tiles


def ask(page: Page, question: str) -> None:
    page.js("document.querySelector('[data-testid=\"stChatInputTextArea\"]').focus()")
    page.send("Input.insertText", text=question)
    for kind in ("keyDown", "keyUp"):
        page.send("Input.dispatchKeyEvent", type=kind, key="Enter", code="Enter", windowsVirtualKeyCode=13)
    page.wait_for("document.querySelectorAll('[data-testid=\"stChatMessage\"]').length >= 2", timeout=240)
    page.settle(240)


SHOTS = [  # (run, tab, file, viewport height)
    ("s4", "Summary", "ui_summary_s4.png", 1900),
    ("s3", "Summary", "ui_summary_s3.png", 1900),
    ("s3", "Track", "ui_track_s3.png", 1100),
    ("s3", "Telemetry", "ui_telemetry_s3.png", 1500),
    ("s1", "Anomalies", "ui_anomalies_s1.png", 900),
    ("s2", "Power & attitude", "ui_power_s2.png", 1500),
    ("s2_fixed", "History", "ui_history_s2_fixed.png", 1700),
    ("s4", "Agents", "ui_agents_s4.png", 1700),
    ("s3", "Agents", "ui_agents_s3.png", 1700),
]


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="aeromind-chrome-")
    app = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
                            "--server.port", str(APP_PORT)], cwd=ROOT, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={CDP_PORT}", "--hide-scrollbars",
                               f"--user-data-dir={profile}", f"--window-size={WIDTH},1200", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/_stcore/health", timeout=1)
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=1))
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("dashboard or Chrome did not start")
        page = Page(next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page"))
        page.send("Page.enable")
        for run, tab, name, height in SHOTS:
            open_run(page, run, tab)
            page.shot(name, height)
        open_run(page, "s3", "Ask")
        ask(page, "Why did the telemetry link drop?")
        page.shot("ui_ask_s3.png", 1000)
        report = ROOT / "outputs" / "s2" / "report.html"
        page.send("Page.navigate", url=report.as_uri())
        time.sleep(3)
        page.shot("report_html_s2.png", 2300)
        return 0
    finally:
        chrome.terminate()
        app.terminate()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

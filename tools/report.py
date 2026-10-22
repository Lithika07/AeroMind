"""report.html: the analysis as one printable page (PRD "Report"), from a state and its flight."""
import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "report"
VERDICT_STATUS = {"Good": "good", "Needs attention": "caution", "Unsafe": "bad"}
STRIP_WIDTH, STRIP_HEIGHT = 900, 34


def strip_svg(strip, dropouts: list) -> str:
    """The link-quality strip as inline SVG: one rectangle per second, dropouts labelled."""
    if strip is None or strip.empty:
        return ""
    t0, t1 = float(strip["t"].min()), float(strip["t"].max()) + 1.0
    scale = STRIP_WIDTH / max(1.0, t1 - t0)
    colours = {"good": "#2e9e5b", "caution": "#e0a100", "bad": "#d64545"}
    rects = [f'<rect x="{(row.t - t0) * scale:.1f}" y="14" width="{max(scale, 0.6):.1f}" height="{STRIP_HEIGHT - 14}" '
             f'fill="{colours[row.link]}"/>' for row in strip.itertuples()]
    labels = [f'<text x="{(d["t"] - t0) * scale:.1f}" y="11" font-size="10" fill="currentColor">'
              f'lost {d["duration_s"]} s{" near WP" + str(d["near_wp"]) if d.get("near_wp") is not None else ""}</text>'
              for d in dropouts]
    return (f'<svg viewBox="0 0 {STRIP_WIDTH} {STRIP_HEIGHT}" role="img" aria-label="link quality across the flight">'
            + "".join(rects + labels) + "</svg>")


def _fmt(value, unit="", digits=1):
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def render(state: dict, strip=None) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    m = state["metrics"]
    approved = state["agents"]["approved"]
    numbers = [("Flight time", _fmt(m["flight"]["duration_s"], " s", 0)), ("Distance", _fmt(m["flight"]["distance_m"], " m", 0)),
               ("Max altitude", _fmt(m["flight"]["max_alt_m"], " m")), ("Max speed", _fmt(m["flight"]["max_speed_ms"], " m/s")),
               ("Battery at landing", _fmt(m["battery"]["remaining_end_pct"], " %", 0)),
               ("Link uptime", _fmt(m["link"]["uptime_pct"], " %")), ("Max cross-track", _fmt(m["tracking"]["xtrack_max_m"], " m", 2))]
    summary = approved["flight_summary"]
    return env.get_template("template.html").render(
        run_id=state["run_id"], scenario=state.get("scenario"), notes=state.get("notes"),
        date=state["history_entry"]["date"].replace("T", " "), tlog_count=len(state["sources"]["tlogs"]),
        m=m, summary=summary, verdict_status=VERDICT_STATUS[summary["verdict"]], numbers=numbers,
        worse=state["history"]["worse_than_usual"], strip_svg=strip_svg(strip, m["link"]["dropouts"]),
        causes=approved.get("diagnosis", {}).get("causes", []), recommendations=approved["advisor"]["recommendations"],
        risk=approved["risk"], fix=state.get("mission_fix"), agents=state["agents"],
        generated=datetime.datetime.now().isoformat(timespec="seconds"))

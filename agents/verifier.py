"""The Verifier: every claim an agent makes must be backed by the computed data.

Checks are exact, not judged by a model:
- a claim must cite a metric that exists, and its value must match it;
- every number with a unit in any text an agent writes must match a computed value with the same
  unit (a speed only against speeds, a percentage only against percentages), so a plausible-looking
  invented number does not pass because some unrelated value happens to be close;
- a cause stands only on findings that were themselves supported.
Whatever fails is rejected with its reason.
"""
import re

from agents.schemas import ClaimVerdict, VerifierOut

PATH_PART = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")
BARE_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?")   # not part of an id like F5 or WP3
NUMBER_WITH_UNIT = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(m/s²|m/s/s|m/s|km/h|kph|mps|knots?|kn\b|percent|%|°|degrees|deg\b|seconds?|secs?\b|"
    r"s\b|minutes?|mins?\b|metres?|meters?|km\b|m\b|volts?|V\b|Hz|mAh)", re.IGNORECASE)
#: text unit -> (unit family, factor to the family's unit)
UNITS = {"m/s²": ("m/s2", 1), "m/s/s": ("m/s2", 1), "m/s": ("m/s", 1), "mps": ("m/s", 1), "km/h": ("m/s", 1 / 3.6),
         "kph": ("m/s", 1 / 3.6), "knot": ("m/s", 0.5144), "knots": ("m/s", 0.5144), "kn": ("m/s", 0.5144),
         "percent": ("%", 1), "%": ("%", 1), "°": ("deg", 1), "degrees": ("deg", 1), "deg": ("deg", 1),
         "s": ("s", 1), "sec": ("s", 1), "secs": ("s", 1), "second": ("s", 1), "seconds": ("s", 1),
         "min": ("s", 60), "mins": ("s", 60), "minute": ("s", 60), "minutes": ("s", 60),
         "m": ("m", 1), "metre": ("m", 1), "metres": ("m", 1), "meter": ("m", 1), "meters": ("m", 1),
         "km": ("m", 1000), "v": ("V", 1), "volt": ("V", 1), "volts": ("V", 1), "hz": ("Hz", 1), "mah": ("mAh", 1)}
REL_TOLERANCE = 0.05
ABS_TOLERANCE = 0.15
MAX_SUMMARY_SENTENCES = 3
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
EDIT_MENTION = re.compile(r"(set_speed|change_altitude|remove_waypoint|add_hold).*?WP\s?(\d+)")
#: the same edits in plain words: (pattern, action)
PLAIN_EDITS = (
    (re.compile(r"\b(?:remov|delet|skip|drop)\w*\s+(?:the\s+)?(?:waypoints?\s+)?WP\s?(\d+)", re.I), "remove_waypoint"),
    (re.compile(r"\bhold\b[^.;]*?\b(?:at|on)\s+WP\s?(\d+)", re.I), "add_hold"),
    (re.compile(r"\b(?:altitude|climb|descend)\w*[^.;]*?\b(?:at|of|for)\s+WP\s?(\d+)", re.I), "change_altitude"),
)
#: A lower score must say what lowers the risk; "the risk is significant" is a reason to raise it.
MITIGATION_WORDS = ("mitigat", "overstat", "already", "fixed", "resolved", "improv", "shorter", "lower than",
                    "less than", "no longer", "safer", "within limit", "not recur", "margin is", "enough")


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


PERCENT_TOLERANCE = 0.6       # a percentage may be rounded to a whole number, no more


def close(a: float, b: float, unit: str = None) -> bool:
    if unit == "%":
        return abs(a - b) <= PERCENT_TOLERANCE
    return abs(a - b) <= max(REL_TOLERANCE * abs(b), ABS_TOLERANCE)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def unit_of(key: str):
    """The unit family of a metric from its name (xtrack_max_m -> m, uptime_pct -> %)."""
    k = key.lower()
    if "pct" in k:
        return "%"
    if "mah" in k:
        return "mAh"
    if k in ("max_x", "max_y", "max_z", "vibration_max"):
        return "m/s2"
    if k.endswith("_ms") or k in ("groundspeed", "speed"):
        return "m/s"
    if k.endswith("_deg"):
        return "deg"
    if k in ("t", "t_start", "t_end", "seconds") or k.endswith("_s"):
        return "s"
    if k.endswith("_m") or k == "alt":
        return "m"
    if k.endswith("_v"):
        return "V"
    if k.endswith("_hz"):
        return "Hz"
    return None


def pools(data, unit=None, into=None) -> dict:
    """unit family -> every value of that unit in a nested structure (list lengths are not values)."""
    into = {} if into is None else into
    if is_number(data) and unit:
        into.setdefault(unit, []).append(float(data))
    elif isinstance(data, dict):
        for key, value in data.items():
            pools(value, unit_of(str(key)) or unit, into)
    elif isinstance(data, list):
        for value in data:
            pools(value, unit, into)
    return into


def merge(*parts: dict) -> dict:
    merged = {}
    for part in parts:
        for unit, values in part.items():
            merged.setdefault(unit, []).extend(values)
    return merged


def pools_at(data, path: str) -> dict:
    """The values under one cited path, keyed by unit."""
    found, value = resolve(data, path)
    if not found:
        return {}
    leaf = PATH_PART.fullmatch(path.split(".")[-1]).group(1)
    return pools({leaf: value})


def numbers(data) -> list:
    """Every number in a nested structure, any unit."""
    if is_number(data):
        return [float(data)]
    if isinstance(data, dict):
        return [n for v in data.values() for n in numbers(v)]
    if isinstance(data, list):
        return [n for v in data for n in numbers(v)]
    return []


def evidence(state: dict) -> dict:
    """What a claim may cite: the metrics, plus the parameters flown."""
    return {**state["metrics"], "params": state.get("params") or {}}


def derived(metrics: dict) -> dict:
    """Values computed from the metrics that agents may quote: phase and leg durations."""
    spans = [p["t_end"] - p["t_start"] for p in metrics["phases"]]
    spans += [leg["t_end"] - leg["t_start"] for leg in metrics["tracking"]["legs"]]
    return {"s": [round(v, 1) for v in spans]}


def check_text(text: str, known: dict, require_number: bool = False, where: str = "the flight data") -> str:
    """'' if every number with a unit in `text` matches a known value of that unit."""
    if require_number and not BARE_NUMBER.search(text):
        return "gives no number from the flight data as evidence"
    for raw, unit in NUMBER_WITH_UNIT.findall(text):
        family, factor = UNITS.get(unit.lower(), UNITS.get(unit, (None, 1)))
        value = float(raw) * factor
        if family is None or not any(close(value, k, family) for k in known.get(family, [])):
            return f"'{raw} {unit}' is not in {where}"
    return ""


def check_claim(claim: dict, data: dict, known: dict) -> str:
    """'' if the claim is supported, else the reason it is not."""
    if not claim.get("metric"):
        return "" if not NUMBER_WITH_UNIT.search(claim["text"]) else "states a number without citing a metric"
    found, actual = resolve(data, claim["metric"])
    if not found:
        return f"metric {claim['metric']} does not exist"
    value = claim.get("value")
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            if is_number(actual):
                return f"gives text '{value}' for numeric metric {claim['metric']}"
            value = None
    if value is not None:
        if isinstance(actual, list):
            actual = len(actual)
        if not is_number(actual):
            return f"metric {claim['metric']} is not a number"
        if not close(float(value), float(actual)):
            return f"value {value} does not match {claim['metric']} = {actual}"
    return check_text(claim["text"], known)


def check_edit_mentions(text: str, kept: set) -> str:
    """A recommendation may only name a mission edit that passed the mission limits."""
    mentions = [(action, int(seq)) for action, seq in EDIT_MENTION.findall(text)]
    mentions += [(action, int(seq)) for pattern, action in PLAIN_EDITS for seq in pattern.findall(text)]
    for action, seq in mentions:
        if (action, seq) not in kept:
            return f"proposes {action} at WP{seq}, which is not among the edits that passed the mission limits"
    return ""


#: topic -> (words that name it, status keys that measure it)
TOPICS = {
    "vibration": (("vibration", "vibrations", "clipping"), ("vibration", "clipping")),
    "GPS": (("gps", "satellite", "satellites", "hdop"), ("gps_sats", "gps_hdop")),
    "wind": (("wind", "gust", "gusts"), ("wind",)),
    "battery": (("battery",), ("battery_end",)),
    "telemetry link": (("link", "telemetry", "dropout", "dropouts", "signal", "connection"),
                       ("link_uptime", "dropouts", "packet_loss")),
    "tracking": (("cross-track", "drift", "drifted", "off track"), ("xtrack_max_m",)),
    "attitude": (("roll", "pitch", "tilt", "attitude"), ("attitude",)),
}
PROBLEM_WORDS = re.compile(r"\b(poor|weak|excessive|significant|issues?|problems?|faults?|unstable|failures?|critical|"
                           r"degraded|lost|dropped|unsafe|abnormal)\b", re.I)


def check_topics(text: str, status: dict) -> str:
    """A sentence may not present a topic as a problem when every metric of that topic is Good."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if not PROBLEM_WORDS.search(sentence):
            continue
        for topic, (words, keys) in TOPICS.items():
            measured = [status[k] for k in keys if k in status]
            if measured and all(v == "good" for v in measured) and any(re.search(rf"\b{re.escape(w)}\b", lower)
                                                                       for w in words):
                return f"presents {topic} as a problem, but its metrics are all Good"
    return ""


def check_adjustment(risk: dict) -> str:
    reason = risk["adjustment_reason"].lower()
    if risk["adjustment"] < 0 and not any(word in reason for word in MITIGATION_WORDS):
        return "lowers the risk without naming anything that reduces it"
    return ""


def phase_statuses(state: dict) -> list:
    from agents.fallbacks import story
    return story(state["metrics"])


def _verdict(agent, claim_id, reason) -> ClaimVerdict:
    return ClaimVerdict(agent=agent, claim_id=claim_id, status="rejected" if reason else "supported",
                        reason=reason or "matches the data")


def _summary(summary: dict, state: dict, data: dict, known: dict) -> list:
    sentences = len(SENTENCE_END.findall(summary["summary"].strip() + " "))
    too_long = f"{sentences} sentences; the summary must be 3" if sentences > MAX_SUMMARY_SENTENCES else ""
    status = state["metrics"]["status"]
    verdicts = [_verdict("flight_summary", "summary", too_long or check_topics(summary["summary"], status)
                         or check_text(summary["summary"], known))]
    statuses = {line.phase: line.status for line in phase_statuses(state)}
    for k, line in enumerate(summary["flight_story"]):
        expected = statuses.get(line["phase"])
        reason = (f"phase {line['phase']} is not in this flight" if expected is None else
                  f"status {line['status']} disagrees with the data ({expected})" if line["status"] != expected
                  else check_text(line["text"], known))
        verdicts.append(_verdict("flight_summary", f"story[{k}]", reason))
    verdicts += [_verdict("flight_summary", c["id"], check_claim(c, data, known)) for c in summary.get("claims", [])]
    return verdicts


MAX_CAUSES = 3


def expected_causes(state: dict) -> list:
    """The cause categories the data supports (deterministic hint rules), strongest first."""
    from agents import hints
    return [c[0] for c in hints.causes(state["metrics"], state.get("params"))][:MAX_CAUSES]


def _diagnosis(diagnosis: dict, data: dict, known: dict, state: dict) -> list:
    verdicts, supported = [], set()
    for claim in diagnosis["findings"]:
        reason = check_claim(claim, data, known)
        supported |= {claim["id"]} if not reason else set()
        verdicts.append(_verdict("diagnosis", claim["id"], reason))
    finding_ids = {f["id"] for f in diagnosis["findings"]}
    for cause in diagnosis["causes"]:
        missing = [f for f in cause["findings"] if f not in finding_ids]
        unsupported = [f for f in cause["findings"] if f in finding_ids and f not in supported]
        reason = (f"cites unknown findings {missing}" if missing else
                  f"rests on rejected findings {unsupported}" if unsupported else
                  "cites no finding" if not cause["findings"] else check_text(cause["cause"], known))
        verdicts.append(_verdict("diagnosis", cause["id"], reason))
    named = {c["category"] for c in diagnosis["causes"]}
    missing = [c for c in expected_causes(state) if c not in named]
    if missing:
        verdicts.append(_verdict("diagnosis", "coverage", f"omits causes the data shows: {', '.join(missing)}"))
    return verdicts


def verify(outputs: dict, state: dict, extra: dict = None) -> VerifierOut:
    """Verdicts for every claim and every number in the agents' outputs. `extra`: unit -> values
    AeroMind itself proposed (the Advisor's edit values)."""
    data = evidence(state)
    known = merge(pools(data), derived(state["metrics"]), pools(state.get("risk_base") or {}),
                  pools(state.get("history") or {}), extra or {})
    verdicts = []
    if outputs.get("flight_summary"):
        verdicts += _summary(outputs["flight_summary"], state, data, known)
    if outputs.get("telemetry_link"):
        verdicts += [_verdict("telemetry_link", c["id"], check_claim(c, data, known))
                     for c in outputs["telemetry_link"]["link_findings"]]
    if outputs.get("diagnosis"):
        verdicts += _diagnosis(outputs["diagnosis"], data, known, state)
    risk = outputs.get("risk")
    if risk:
        verdicts.append(_verdict("risk", "adjustment_reason",
                                 check_adjustment(risk) or check_text(risk["adjustment_reason"], known)))
    advisor = outputs.get("advisor")
    if advisor:
        kept = {(e["action"], e["wp"]) for e in advisor["edits"]}
        for rec in advisor["recommendations"]:
            status = state["metrics"]["status"]
            reason = (check_edit_mentions(rec["text"], kept) or check_edit_mentions(rec["reason"], kept)
                      or check_topics(rec["text"] + " " + rec["reason"], status) or check_text(rec["text"], known)
                      or check_text(rec["reason"], known) or check_text(rec["evidence"], known, require_number=True))
            verdicts.append(_verdict("advisor", f"rec[{rec['rank']}]", reason))
    return VerifierOut(verdicts=verdicts)


def rejection_rates(result: VerifierOut) -> dict:
    totals, rejected = {}, {}
    for v in result.verdicts:
        totals[v.agent] = totals.get(v.agent, 0) + 1
        rejected[v.agent] = rejected.get(v.agent, 0) + (v.status == "rejected")
    return {agent: round(rejected[agent] / totals[agent], 2) for agent in totals}

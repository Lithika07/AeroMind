"""Data contracts shared by the tools, the agents and the dashboard (PRD "Data contracts").

Every part reads and writes these shapes, so each can be built and tested on its own. A metric
that could not be computed is None (null in JSON), never a guess.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["good", "caution", "bad"]
#: Length caps on agent free text. Constrained decoding enforces them, so a small model cannot loop inside
#: a string until its output is cut off (a 5,440-character "3-sentence" summary did exactly that).
SHORT_TEXT = 300
SUMMARY_TEXT = 800
Verdict = Literal["Good", "Needs attention", "Unsafe"]
RiskLevel = Literal["Low", "Medium", "High"]
AGENT_NAMES = ("flight_summary", "telemetry_link", "diagnosis", "risk", "advisor", "verifier")
AgentName = Literal["flight_summary", "telemetry_link", "diagnosis", "risk", "advisor", "verifier"]
CAUSE_CATEGORIES = ("wind_drift", "speed_too_high", "low_battery", "link_loss", "gps_weak", "vibration",
                    "setup", "other")
CauseCategory = Literal["wind_drift", "speed_too_high", "low_battery", "link_loss", "gps_weak", "vibration",
                        "setup", "other"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# -- metrics.json (Metrics engine) ---------------------------------------------------------------

class FlightInfo(Contract):
    duration_s: Optional[float] = None
    distance_m: Optional[float] = None
    max_alt_m: Optional[float] = None
    max_speed_ms: Optional[float] = None


class BatteryInfo(Contract):
    remaining_start_pct: Optional[float] = None
    remaining_end_pct: Optional[float] = None
    used_pct: Optional[float] = None
    used_pct_per_km: Optional[float] = None
    min_voltage_v: Optional[float] = None


class Leg(Contract):
    leg: int
    to_wp: int
    t_start: float
    t_end: float
    xtrack_max_m: Optional[float] = None
    speed_ms: Optional[float] = None


class Tracking(Contract):
    xtrack_max_m: Optional[float] = None
    legs: list[Leg] = []
    waypoints_planned: Optional[int] = None
    waypoints_reached: Optional[int] = None
    mission_completion_pct: Optional[float] = None


class Vibration(Contract):
    max_x: Optional[float] = None
    max_y: Optional[float] = None
    max_z: Optional[float] = None
    clip_total: Optional[int] = None


class Gps(Contract):
    min_sats: Optional[int] = None
    max_hdop: Optional[float] = None


class WindInfo(Contract):
    max_ms: Optional[float] = None
    mean_ms: Optional[float] = None
    from_deg: Optional[float] = None
    source: Optional[Literal["WIND", "attitude"]] = None


class AttitudeInfo(Contract):
    max_roll_deg: Optional[float] = None
    max_pitch_deg: Optional[float] = None


class Dropout(Contract):
    t: float                       # seconds from the start of the log
    duration_s: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    near_wp: Optional[int] = None
    between_files: bool = False    # the gap between two .tlog files of one flight


class Rssi(Contract):
    rssi_min: Optional[float] = None
    rssi_mean: Optional[float] = None
    remrssi_min: Optional[float] = None
    noise_max: Optional[float] = None
    rc_rssi_min: Optional[float] = None


class LinkInfo(Contract):
    uptime_pct: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    dropouts: list[Dropout] = []
    rssi: Optional[Rssi] = None
    position_rate_hz: Optional[float] = None
    position_rate_min_ratio: Optional[float] = None   # worst 10 s window / median


class Phase(Contract):
    name: str
    t_start: float
    t_end: float
    kind: Literal["ground", "takeoff", "leg", "rtl", "land", "other"] = "other"


class Anomaly(Contract):
    t: float
    signal: str
    value: float
    z: float


class Event(Contract):
    t: float
    text: str
    severity: Optional[int] = None
    kind: Literal["statustext", "mode", "failsafe"] = "statustext"


class Metrics(Contract):
    flight: FlightInfo = FlightInfo()
    battery: BatteryInfo = BatteryInfo()
    tracking: Tracking = Tracking()
    vibration: Vibration = Vibration()
    gps: Gps = Gps()
    wind: WindInfo = WindInfo()
    attitude: AttitudeInfo = AttitudeInfo()
    link: LinkInfo = LinkInfo()
    phases: list[Phase] = []
    anomalies: list[Anomaly] = []
    events: list[Event] = []
    warnings: Optional[int] = None
    status: dict[str, Status] = {}
    health_score: int = Field(ge=0, le=100, default=100)


# -- agent outputs -------------------------------------------------------------------------------

class Claim(Contract):
    """A statement an agent makes about the flight, citing the metric that backs it."""
    id: str
    text: str = Field(max_length=SHORT_TEXT)
    metric: Optional[str] = None             # dotted path into metrics.json, e.g. link.dropouts[0].duration_s
    value: Optional[float | str] = None      # the value the claim relies on


class StoryLine(Contract):
    phase: str
    status: Status
    text: str = Field(max_length=SHORT_TEXT)


class FlightSummaryOut(Contract):
    verdict: Verdict
    summary: str = Field(max_length=SUMMARY_TEXT)
    flight_story: list[StoryLine]
    claims: list[Claim] = []


class TelemetryLinkOut(Contract):
    link_verdict: Status
    safe_for_mission: bool
    link_findings: list[Claim]


class Cause(Contract):
    id: str
    cause: str = Field(max_length=SHORT_TEXT)
    category: CauseCategory
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[str]


class DiagnosisOut(Contract):
    findings: list[Claim]
    causes: list[Cause] = Field(max_length=3)


class RiskOut(Contract):
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    adjustment: int = Field(ge=-10, le=10)
    adjustment_reason: str = Field(max_length=SUMMARY_TEXT)
    factors: list[str]
    predicted_battery_pct: Optional[float] = None
    confidence: Literal["low", "normal"]


class Edit(Contract):
    action: Literal["set_speed", "change_altitude", "remove_waypoint", "add_hold"]
    wp: int                                  # mission sequence number the edit applies to
    value: Optional[float] = None            # m/s, metres (delta), or seconds
    cause: str


class Recommendation(Contract):
    rank: int = Field(ge=1, le=3)
    text: str = Field(max_length=SHORT_TEXT)
    reason: str = Field(max_length=SHORT_TEXT)
    evidence: str = Field(max_length=SHORT_TEXT)


class AdvisorOut(Contract):
    edits: list[Edit] = Field(max_length=5)
    recommendations: list[Recommendation] = Field(max_length=3)


class ClaimVerdict(Contract):
    agent: AgentName
    claim_id: str
    status: Literal["supported", "rejected"]
    reason: str


class VerifierOut(Contract):
    verdicts: list[ClaimVerdict]


AGENT_OUTPUTS = {
    "flight_summary": FlightSummaryOut,
    "telemetry_link": TelemetryLinkOut,
    "diagnosis": DiagnosisOut,
    "risk": RiskOut,
    "advisor": AdvisorOut,
    "verifier": VerifierOut,
}


# -- orchestrator plan ---------------------------------------------------------------------------

class PlanStep(Contract):
    agent: AgentName
    reason: str


class Plan(Contract):
    plan: list[PlanStep]
    source: Literal["llm", "default"] = "llm"


# -- history.json (Memory store) -----------------------------------------------------------------

class HistoryEntry(Contract):
    run_id: str
    date: str
    scenario: Optional[str] = None
    parent_run: Optional[str] = None
    mission_length_m: Optional[float] = None
    duration_s: Optional[float] = None
    battery_used_pct: Optional[float] = None
    battery_pct_per_km: Optional[float] = None
    battery_capacity_mah: Optional[float] = None
    battery_mah_per_km: Optional[float] = None
    battery_end_pct: Optional[float] = None
    mission_completion_pct: Optional[float] = None
    xtrack_max_m: Optional[float] = None
    link_uptime_pct: Optional[float] = None
    dropouts: Optional[int] = None
    vibration_max: Optional[float] = None
    wind_max_ms: Optional[float] = None
    health_score: Optional[int] = None
    causes: list[str] = []
    edits_applied: list[str] = []

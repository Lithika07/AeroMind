"""Every metric for one flight, its status and the health score (PRD "Metrics engine").

Flight-wide figures use the armed window (first arm to last disarm). Vibration, clipping and
attitude use only the airborne part: the landing touchdown jolts the IMU (37 m/s^2 and one clip on
a calm SITL landing), which says nothing about how the airframe flew.
"""
import math

import numpy as np

from agents.schemas import (AttitudeInfo, BatteryInfo, Event, FlightInfo, Gps, Leg, Metrics, Tracking,
                            Vibration, WindInfo)
from tools import anomalies, link_metrics, phases, thresholds, timeline
from tools import geo
from tools import waypoints as wp

DEG_E7 = 1e7
BATTERY_UNKNOWN = -1
GPS_3D_FIX = 3
HDOP_UNKNOWN = 65535
WARNING_SEVERITY = 4               # STATUSTEXT severity <= 4: emergency .. warning
FAILSAFE_MODES = {"RTL", "SMART_RTL", "LAND", "BRAKE"}
DISTANCE_SAMPLE_S = 1.0
#: Seconds after each phase starts (take-off, a turn onto a leg, the RTL climb) when changes in
#: current and altitude error are expected, so the anomaly detector does not look there.
TRANSIENT_S = 10.0


def _round(value, digits=1):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else round(float(value), digits)


def flight_info(flight, window) -> FlightInfo:
    position = timeline.in_window(flight.frame("GLOBAL_POSITION_INT"), window)
    vfr = timeline.in_window(flight.frame("VFR_HUD"), window)
    distance = None
    if len(position) > 1:
        sampled = position.iloc[::max(1, int(len(position) / max(1.0, (window[1] - window[0]) / DISTANCE_SAMPLE_S)))]
        lats, lons = sampled["lat"].to_numpy() / DEG_E7, sampled["lon"].to_numpy() / DEG_E7
        distance = sum(geo.distance_m(lats[i], lons[i], lats[i + 1], lons[i + 1]) for i in range(len(lats) - 1))
    return FlightInfo(duration_s=_round(window[1] - window[0]), distance_m=_round(distance, 0),
                      max_alt_m=_round(position["relative_alt"].max() / 1000.0) if not position.empty else None,
                      max_speed_ms=_round(vfr["groundspeed"].max()) if not vfr.empty else None)


def battery_info(flight, window, distance_m) -> BatteryInfo:
    status = flight.frame("SYS_STATUS")
    known = status[status["battery_remaining"] != BATTERY_UNKNOWN] if not status.empty else status
    during = timeline.in_window(known, window)
    if during.empty:
        return BatteryInfo()
    start = float(during["battery_remaining"].iloc[0])
    after = known[known["t"] >= window[1]]
    end = float((after if not after.empty else during)["battery_remaining"].iloc[0 if not after.empty else -1])
    used = start - end
    volts = during["voltage_battery"][during["voltage_battery"] > 0] / 1000.0
    per_km = used / (distance_m / 1000.0) if distance_m else None
    return BatteryInfo(remaining_start_pct=start, remaining_end_pct=end, used_pct=used,
                       used_pct_per_km=_round(per_km), min_voltage_v=_round(volts.min(), 2) if not volts.empty else None)


def _reached(flight, nav_seqs: set) -> set:
    reached = set(flight.frame("MISSION_ITEM_REACHED").get("seq", []))
    current = flight.frame("MISSION_CURRENT")
    if not current.empty:
        highest = int(current["seq"].max())
        reached |= {seq for seq in nav_seqs if seq < highest}
    return {int(s) for s in reached} & nav_seqs if nav_seqs else {int(s) for s in reached}


def tracking(flight, flight_phases) -> Tracking:
    nav = flight.frame("NAV_CONTROLLER_OUTPUT")
    vfr = flight.frame("VFR_HUD")
    legs = []
    for phase in (p for p in flight_phases if p.kind == "leg"):
        window = (phase.t_start + flight.t0, phase.t_end + flight.t0)
        xtrack = timeline.in_window(nav, window)["xtrack_error"].abs()
        speed = timeline.in_window(vfr, window)["groundspeed"]
        to_wp = int(phase.name.split("WP")[-1].rstrip(")"))
        legs.append(Leg(leg=len(legs) + 1, to_wp=to_wp, t_start=phase.t_start, t_end=phase.t_end,
                        xtrack_max_m=_round(xtrack.max(), 2) if not xtrack.empty else None,
                        speed_ms=_round(speed.mean()) if not speed.empty else None))
    xtracks = [leg.xtrack_max_m for leg in legs if leg.xtrack_max_m is not None]
    planned = reached = completion = None
    if flight.mission:
        nav_seqs = {item.seq for item in wp.nav_waypoints(flight.mission)}
        planned = len(nav_seqs)
        reached = len(_reached(flight, nav_seqs))
        completion = round(100.0 * reached / planned, 1) if planned else None
    return Tracking(xtrack_max_m=max(xtracks) if xtracks else None, legs=legs, waypoints_planned=planned,
                    waypoints_reached=reached, mission_completion_pct=completion)


def vibration(flight, airborne) -> Vibration:
    vib = timeline.during(flight.frame("VIBRATION"), airborne)
    if vib.empty:
        return Vibration()
    clips = vib[["clipping_0", "clipping_1", "clipping_2"]]
    return Vibration(max_x=_round(vib["vibration_x"].max()), max_y=_round(vib["vibration_y"].max()),
                     max_z=_round(vib["vibration_z"].max()), clip_total=int((clips.iloc[-1] - clips.iloc[0]).sum()))


def gps(flight, window) -> Gps:
    raw = timeline.in_window(flight.frame("GPS_RAW_INT"), window)
    fixed = raw[raw["fix_type"] >= GPS_3D_FIX] if not raw.empty else raw
    if fixed.empty:
        return Gps()
    hdop = fixed["eph"][fixed["eph"] != HDOP_UNKNOWN] / 100.0
    return Gps(min_sats=int(fixed["satellites_visible"].min()), max_hdop=_round(hdop.max(), 2) if not hdop.empty else None)


def wind(flight, airborne) -> WindInfo:
    rows = timeline.during(flight.frame("WIND"), airborne)
    if rows.empty:
        return WindInfo()
    peak = rows.loc[rows["speed"].idxmax()]
    return WindInfo(max_ms=_round(peak["speed"]), mean_ms=_round(rows["speed"].mean()),
                    from_deg=_round(peak["direction"] % 360.0, 0), source="WIND")


def attitude(flight, airborne) -> AttitudeInfo:
    rows = timeline.during(flight.frame("ATTITUDE"), airborne)
    if rows.empty:
        return AttitudeInfo()
    return AttitudeInfo(max_roll_deg=_round(np.degrees(rows["roll"].abs().max())),
                        max_pitch_deg=_round(np.degrees(rows["pitch"].abs().max())))


def events(flight, window) -> tuple:
    """(events, warning count): STATUSTEXT while armed, and mode changes after the mission started."""
    found, warning_count = [], 0
    for row in timeline.in_window(flight.frame("STATUSTEXT"), window).itertuples():
        found.append(Event(t=round(row.t - flight.t0, 1), text=row.text, severity=int(row.severity)))
        if row.severity <= WARNING_SEVERITY:
            warning_count += 1
    states = timeline.in_window(timeline.heartbeat_states(flight.frame("HEARTBEAT")), window)
    previous = None
    seen_auto = False
    for row in states.itertuples():
        if previous is not None and row.mode != previous:
            failsafe = seen_auto and row.mode in FAILSAFE_MODES
            found.append(Event(t=round(row.t - flight.t0, 1), text=f"Mode {previous} -> {row.mode}",
                               kind="failsafe" if failsafe else "mode"))
            warning_count += int(failsafe)
        seen_auto = seen_auto or row.mode == "AUTO"
        previous = row.mode
    return sorted(found, key=lambda e: e.t), warning_count


def steady(flight, airborne: list, flight_phases: list) -> list:
    cuts = [(p.t_start + flight.t0, p.t_start + flight.t0 + TRANSIENT_S) for p in flight_phases]
    return timeline.subtract(airborne, cuts)


def compute(flight) -> Metrics:
    window = timeline.armed_window(flight.frame("HEARTBEAT"))
    if window is None:
        return Metrics(events=[Event(t=0.0, text="Vehicle never armed in this log", kind="statustext")])
    airborne = timeline.airborne_intervals(flight.frame("GLOBAL_POSITION_INT"), window)
    flight_phases = phases.split(flight)
    info = flight_info(flight, window)
    found_events, warning_count = events(flight, window)
    body = dict(flight=info, battery=battery_info(flight, window, info.distance_m),
                tracking=tracking(flight, flight_phases), vibration=vibration(flight, airborne), gps=gps(flight, window),
                wind=wind(flight, airborne), attitude=attitude(flight, airborne),
                link=link_metrics.compute(flight, window), phases=flight_phases,
                anomalies=anomalies.detect(flight, steady(flight, airborne, flight_phases)),
                events=found_events, warnings=warning_count)
    statuses = thresholds.statuses(Metrics(**body).model_dump())
    return Metrics(**body, status=statuses, health_score=thresholds.health_score(statuses))

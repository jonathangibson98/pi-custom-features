"""A weekly work schedule for each person (Work Hours Tracker). Standard library only.

Stored in /data/schedule.json as {"person.jon": {"mon": {"start": "06:30", "end": "17:00"}, "tue": ..., "sat": null}}
A day with no entry (or null) is a day off the schedule. An end time at or before the start means the shift runs
past midnight (night shift). Days off from the Days off list cancel the shift that day.
"""
import re
from datetime import date, timedelta

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _t(v):
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(v or "").strip())
    return "%02d:%s" % (int(m.group(1)), m.group(2)) if m else None


def clean(raw):
    """{person_id: {day: {"start", "end"} or None}}, dropping anything unusable."""
    out = {}
    for pid, week in (raw if isinstance(raw, dict) else {}).items():
        if not re.fullmatch(r"person\.[a-z0-9_]+", str(pid)) or not isinstance(week, dict):
            continue
        w = {}
        for d in DAYS:
            sh = week.get(d)
            st, en = (_t(sh.get("start")), _t(sh.get("end"))) if isinstance(sh, dict) else (None, None)
            w[d] = {"start": st, "end": en} if st and en else None
        out[str(pid)] = w
    return out


def mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def hours(sh):
    if not sh:
        return 0.0
    a, b = mins(sh["start"]), mins(sh["end"])
    if b <= a:
        b += 24 * 60
    return round((b - a) / 60, 2)


def label(t):
    h, m = t.split(":")
    h = int(h)
    return "%d:%s %s" % (h % 12 or 12, m, "AM" if h < 12 else "PM")


def shift_text(sh):
    return "%s to %s" % (label(sh["start"]), label(sh["end"])) if sh else "off"


def week_text(week):
    """'Mon to Fri 6:30 AM to 5:00 PM; Sat, Sun off': days with the same shift are grouped."""
    if not week or not any(week.get(d) for d in DAYS):
        return "No schedule set"
    groups, order = {}, []
    for i, d in enumerate(DAYS):
        k = shift_text(week.get(d))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(i)
    parts = []
    for k in order:
        idx = groups[k]
        runs, start = [], idx[0]
        for a, b in zip(idx, idx[1:] + [None]):
            if b != a + 1:
                runs.append((start, a))
                start = b
        names = ", ".join(SHORT[a] if a == b else "%s to %s" % (SHORT[a], SHORT[b]) if b - a > 1 else "%s, %s" % (SHORT[a], SHORT[b]) for a, b in runs)
        parts.append("%s %s" % (names, k))
    return "; ".join(parts)


def shift_on(week, d):
    return (week or {}).get(DAYS[d.weekday()])


def stats(week, today, off_days, week_hours, now_minutes, period_start, period_end):
    """What the summary entity says about the schedule. off_days: {date: [reasons]} (past and future)."""
    def sched(d):
        sh = shift_on(week, d)
        return None if (not sh or d in off_days) else sh

    ws = today - timedelta(days=today.weekday())
    week_total = sum(hours(sched(ws + timedelta(days=i))) for i in range(7))
    so_far = sum(hours(sched(ws + timedelta(days=i))) for i in range(today.weekday()))
    td = sched(today)
    if td and now_minutes >= mins(td["end"]) and mins(td["end"]) > mins(td["start"]):
        so_far += hours(td)  # today's shift is over
    left = sum(hours(sched(today + timedelta(days=i))) for i in range(1, 7 - today.weekday()))
    if td and not (now_minutes >= mins(td["end"]) and mins(td["end"]) > mins(td["start"])):
        left += hours(td)
    period_total = 0.0
    d = period_start
    while d <= period_end:
        period_total += hours(sched(d))
        d += timedelta(days=1)

    nxt = None
    upcoming = []
    for i in range(0, 14):
        d = today + timedelta(days=i)
        sh = shift_on(week, d)
        if d in off_days:
            status, reason = "day off", ", ".join(off_days[d])
        elif sh:
            status, reason = "work", ""
        else:
            status, reason = "off", ""
        if i < 7:
            upcoming.append({"date": d.isoformat(), "weekday": LONG[d.weekday()], "status": status,
                             "start": sh["start"] if sh and status == "work" else None,
                             "end": sh["end"] if sh and status == "work" else None,
                             "reason": reason or None})
        if status == "work" and nxt is None and (i > 0 or not (now_minutes >= mins(sh["end"]) and mins(sh["end"]) > mins(sh["start"]))):
            nxt = {"date": d.isoformat(), "weekday": LONG[d.weekday()], "start": sh["start"], "end": sh["end"],
                   "hours": hours(sh), "days_until": i}
    return {
        "has_schedule": any((week or {}).get(d) for d in DAYS),
        "schedule_text": week_text(week),
        "schedule": {LONG[i]: ({"start": week[DAYS[i]]["start"], "end": week[DAYS[i]]["end"], "hours": hours(week[DAYS[i]])}
                               if week and week.get(DAYS[i]) else "off") for i in range(7)},
        "scheduled_today": ({"start": td["start"], "end": td["end"], "hours": hours(td)} if td else None),
        "working_today": bool(td),
        "next_shift": nxt,
        "next_7_days": upcoming,
        "scheduled_hours_this_week": round(week_total, 2),
        "scheduled_hours_so_far_this_week": round(so_far, 2),
        "scheduled_hours_left_this_week": round(left, 2),
        "hours_vs_schedule_this_week": round(week_hours - so_far, 2),
        "scheduled_hours_this_period": round(period_total, 2),
    }

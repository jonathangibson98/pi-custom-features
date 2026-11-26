"""Days off (holidays, vacation, sick days) for Work Hours Tracker. Standard library only.

Stored in /data/days_off.json as
  {"calendar": "calendar.xyz" or "", "items": [item, ...]}
and each item is
  {"id": "ab12cd34", "name": "Thanksgiving", "date": "2026-11-26", "end": "2026-11-27" (optional, last day, inclusive),
   "yearly": true/false, "people": ["person.jon"] (empty = everybody)}

A day also counts as off when the optional calendar has an ALL-DAY event on it (timed events are ignored, so a
dentist appointment does not make you "off"). The calendar applies to everybody.
"""
import re
import uuid
from datetime import date, timedelta

MAX_ITEMS = 400
MAX_DAYS = 120       # longest single block (a long vacation)
UPCOMING = 10        # how many upcoming days off go in the sensor attributes
LOOKAHEAD = 400      # days


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def clean_item(raw):
    """One cleaned day-off item, or None when it has no usable date."""
    if not isinstance(raw, dict):
        return None
    start = _d(raw.get("date"))
    if not start:
        return None
    end = _d(raw.get("end")) or start
    if end < start:
        end = start
    if (end - start).days >= MAX_DAYS:
        end = start + timedelta(days=MAX_DAYS - 1)
    iid = str(raw.get("id") or "")
    if not re.fullmatch(r"[a-z0-9]{6,16}", iid):
        iid = uuid.uuid4().hex[:8]
    people = []
    for p in raw.get("people") or []:
        p = str(p)
        if re.fullmatch(r"person\.[a-z0-9_]+", p) and p not in people:
            people.append(p)
    return {"id": iid, "name": (str(raw.get("name") or "").strip()[:80] or "Day off"),
            "date": start.isoformat(), "end": end.isoformat() if end != start else "",
            "yearly": bool(raw.get("yearly")), "people": people}


def clean(raw):
    raw = raw if isinstance(raw, dict) else {}
    cal = str(raw.get("calendar") or "").strip().lower()
    if not re.fullmatch(r"calendar\.[a-z0-9_]+", cal):
        cal = ""
    items = [i for i in (clean_item(x) for x in (raw.get("items") or [])[:MAX_ITEMS]) if i]
    items.sort(key=lambda i: (i["date"], i["name"]))
    return {"calendar": cal, "items": items}


def _shift_year(d, year):
    try:
        return d.replace(year=year)
    except ValueError:  # Feb 29 in a year without one
        return d.replace(year=year, day=28)


def occurrences(item, a, b):
    """Every (first_day, last_day) block of the item that touches a..b (inclusive)."""
    s, e = _d(item["date"]), _d(item.get("end")) or _d(item["date"])
    span = e - s
    if not item.get("yearly"):
        return [(s, e)] if s <= b and e >= a else []
    out = []
    for y in range(a.year - 1, b.year + 1):
        ys = _shift_year(s, y)
        ye = ys + span
        if ys <= b and ye >= a:
            out.append((ys, ye))
    return out


def days_for(person_id, items, a, b, cal_events=()):
    """{date: [names]} of the days in a..b that are off for this person."""
    out = {}

    def put(first, last, name):
        d = max(first, a)
        while d <= min(last, b):
            names = out.setdefault(d, [])
            if name not in names:
                names.append(name)
            d += timedelta(days=1)

    for it in items:
        if it["people"] and person_id not in it["people"]:
            continue
        for first, last in occurrences(it, a, b):
            put(first, last, it["name"])
    for first, last, name in cal_events:
        put(first, last, name)
    return out


def calendar_blocks(events):
    """All-day events from Home Assistant's /api/calendars response as (first, last, name). The end is exclusive there."""
    out = []
    for ev in events or []:
        st, en = ev.get("start"), ev.get("end")
        if not (isinstance(st, dict) and "date" in st):
            continue  # a timed event
        first = _d(st.get("date"))
        if not first:
            continue
        last = (_d(en.get("date")) - timedelta(days=1)) if isinstance(en, dict) and _d(en.get("date")) else first
        out.append((first, max(first, last), str(ev.get("summary") or "Day off")[:80]))
    return out


def status(person_id, items, today, cal_events=()):
    """What the sensor shows: off today?, why, and the next days off."""
    days = days_for(person_id, items, today, today + timedelta(days=LOOKAHEAD), cal_events)
    upcoming = []  # consecutive days with the same reason are one block (a week of vacation is one entry)
    for d in sorted(days):
        if d <= today:
            continue
        name = ", ".join(days[d])
        last = upcoming[-1] if upcoming else None
        if last and last["name"] == name and _d(last["end"]) + timedelta(days=1) == d:
            last["end"] = d.isoformat()
            last["days"] += 1
        else:
            upcoming.append({"date": d.isoformat(), "end": d.isoformat(), "days": 1, "name": name, "days_until": (d - today).days})
    upcoming = upcoming[:UPCOMING]
    nxt = upcoming[0] if upcoming else None
    return {"off_today": today in days, "today_name": ", ".join(days.get(today, [])),
            "next_date": nxt["date"] if nxt else "", "next_name": nxt["name"] if nxt else "",
            "days_until": nxt["days_until"] if nxt else None, "upcoming": upcoming}


def prompt_text(person_id, items, today, cal_events=()):
    """A few plain lines for the AI: is today off, and what is coming."""
    st = status(person_id, items, today, cal_events)
    lines = ["Today is a day off: " + st["today_name"] + "." if st["off_today"] else "Today is not a day off."]
    if st["upcoming"]:
        lines.append("Upcoming days off: " + "; ".join("%s (%s%s, in %d days)" % (u["name"], u["date"], " to " + u["end"] if u["days"] > 1 else "", u["days_until"])
                                                       for u in st["upcoming"]) + ".")
    return " ".join(lines)

import csv
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from flask import Flask, Response, jsonify, request, send_file

import addon_backup
import days_off
import schedule

try:
    import paho.mqtt.client as paho
except Exception:  # paho missing: MQTT is skipped, everything else still works
    paho = None

VERSION = "1.5.1"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = "http://supervisor/core/api"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

DATA_DIR = os.environ.get("WH_DATA_DIR", "/data")
with open(os.path.join(DATA_DIR, "options.json")) as f:
    OPTS = json.load(f)

FOLDER = OPTS.get("save_folder", "/homeassistant/work_hours").rstrip("/")
KEEP_DAYS = int(OPTS.get("keep_days", 365))
CHECK = int(OPTS.get("check_seconds", 30))
GRACE = int(OPTS.get("grace_minutes", 10))
MIN_MIN = int(OPTS.get("min_minutes", 5))
SEPARATE = bool(OPTS.get("separate_sensors", False))  # also keep the old "at work" and "day off" sensors

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

SETTINGS = os.path.join(DATA_DIR, "settings.json")
SESSIONS = os.path.join(DATA_DIR, "sessions.json")
HISTORY = os.path.join(DATA_DIR, "history.json")
ANCHOR = os.path.join(DATA_DIR, "anchor.json")
DAYS_OFF = os.path.join(DATA_DIR, "days_off.json")
SCHEDULE = os.path.join(DATA_DIR, "schedule.json")
MQTT_SLUGS = os.path.join(DATA_DIR, "mqtt_slugs.json")
# created before anything is read, so a queued restore is unpacked first. The hours CSVs in the save folder go too.
BACKUP = addon_backup.Backup("work_hours", "Work Hours Tracker", VERSION,
                             [("data", DATA_DIR, "replace", []), ("hours", FOLDER, "merge", [])], data_dir=DATA_DIR)
CSV_HEADER = ["date", "zone", "start", "end", "hours"]

AVAIL = "work_hours/status"
DEVICE = {
    "identifiers": ["work_hours_tracker"],
    "name": "Work Hours Tracker",
    "manufacturer": "jonathangibson98",
    "model": "Work Hours Tracker",
    "sw_version": VERSION,
}

lock = threading.RLock()
_tz = None
mq = None
mq_state = {"ready": False, "resend": True}
mq_last = {}
mq_sig = None
name_cache = {}
cal_cache = {}
app = Flask(__name__)


# ---------- helpers ----------
def ha(path):
    r = requests.get(API + path, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def tz():
    global _tz
    if _tz is None:
        try:
            _tz = ZoneInfo(ha("/config")["time_zone"])
        except Exception:
            return ZoneInfo("UTC")
    return _tz


def now():
    return datetime.now(tz())


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load_schedule():
    return schedule.clean(load_json(SCHEDULE, {}))


def load_days_off():
    return days_off.clean(load_json(DAYS_OFF, {}))


def calendar_events(entity):
    """All-day events of the optional days-off calendar, as (first, last, name). Cached for 10 minutes."""
    if not entity:
        return []
    hit = cal_cache.get(entity)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        t = now().astimezone(timezone.utc)
        a = (t - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        b = (t + timedelta(days=days_off.LOOKAHEAD)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = days_off.calendar_blocks(ha("/calendars/%s?start=%s&end=%s" % (entity, quote(a), quote(b))))
    except Exception as e:  # noqa: BLE001
        print("Days-off calendar failed:", entity, e, flush=True)
        out = hit[1] if hit else []
    cal_cache[entity] = (time.time(), out)
    return out


def snap_anchor(raw, start_idx, today):
    """ISO date of a pay period start, moved back onto the start weekday."""
    a = None
    if raw:
        try:
            a = date.fromisoformat(str(raw))
        except ValueError:
            a = None
    if a is None:
        a = today
    return (a - timedelta(days=(a.weekday() - start_idx) % 7)).isoformat()


def clean_period(per, today):
    day = per.get("start_day")
    if day not in DAY_NAMES:
        day = "Thursday"
    try:
        weeks = min(8, max(1, int(per.get("weeks", 1))))
    except (TypeError, ValueError):
        weeks = 1
    try:
        hist = min(100, max(1, int(per.get("history", 26))))
    except (TypeError, ValueError):
        hist = 26
    anchor = snap_anchor(per.get("anchor"), DAY_NAMES.index(day), today)
    return {"start_day": day, "weeks": weeks, "anchor": anchor, "history": hist}


def load_settings():
    """Settings shape:
    {"people": [{"id", "file", "name", "zones": [zone ids],
                 "period": {"start_day", "weeks", "anchor", "history"}}]}
    Older versions are migrated here: 1.0.0 had one shared zone list, and
    1.2.0 / 1.3.0 had one pay period for everybody."""
    s = load_json(SETTINGS, {"people": []})
    people = s.get("people", [])
    changed = False
    if people and isinstance(people[0], str):
        zones = s.get("zones", [])
        people = [{"id": p, "file": p.split(".", 1)[1], "zones": list(zones)} for p in people]
        changed = True
    base = s.get("period")
    if base is None:
        base = {
            "start_day": OPTS.get("period_start_day") or "Thursday",
            "weeks": OPTS.get("period_weeks") or 1,
            "anchor": OPTS.get("period_anchor_date") or load_json(ANCHOR, {}).get("anchor") or "",
            "history": OPTS.get("history_periods") or 26,
        }
    elif people:
        changed = True  # the shared period is being copied onto each person
    today = now().date()
    out = []
    for p in people:
        per = p.get("period")
        cleaned = clean_period(per if per is not None else base, today)
        if per != cleaned:
            changed = True
        out.append({**p, "period": cleaned})
    if changed:
        save_json(SETTINGS, {"people": out})
    return {"people": out}


def file_path(name):
    return os.path.join(FOLDER, name + ".csv")


def read_rows(name):
    rows = []
    try:
        with open(file_path(name), newline="") as f:
            for r in csv.DictReader(f):
                try:
                    float(r["hours"])
                    rows.append(r)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    except Exception as e:
        print("Read error:", e, flush=True)
    return rows


def sum_range(rows, a, b):
    """Total hours for rows dated a..b inclusive (date objects)."""
    lo, hi = a.isoformat(), b.isoformat()
    return sum(float(r["hours"]) for r in rows if lo <= r["date"] <= hi)


def log_session(name, zone, start, end):
    """Write one finished visit to the person's file (split at midnight)."""
    if (end - start).total_seconds() < MIN_MIN * 60:
        return
    rows = []
    cur = start
    while cur < end:
        midnight = datetime.combine(
            cur.date() + timedelta(days=1), datetime.min.time(), tzinfo=cur.tzinfo
        )
        seg_end = min(end, midnight)
        hrs = (seg_end - cur).total_seconds() / 3600
        end_label = "24:00" if seg_end == midnight else seg_end.strftime("%H:%M")
        rows.append([cur.date().isoformat(), zone, cur.strftime("%H:%M"), end_label, f"{hrs:.2f}"])
        cur = seg_end
    os.makedirs(FOLDER, exist_ok=True)
    p = file_path(name)
    new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CSV_HEADER)
        w.writerows(rows)


def cleanup():
    """Delete rows older than keep_days. 0 = keep forever."""
    if KEEP_DAYS <= 0 or not os.path.isdir(FOLDER):
        return
    try:
        snapshot_history()
    except Exception as e:
        print("History snapshot failed:", e, flush=True)
    cutoff = (now().date() - timedelta(days=KEEP_DAYS)).isoformat()
    for name in os.listdir(FOLDER):
        if not name.endswith(".csv"):
            continue
        p = os.path.join(FOLDER, name)
        try:
            with open(p, newline="") as f:
                rows = list(csv.reader(f))
            if not rows or rows[0] != CSV_HEADER:
                continue  # not one of our files, leave it alone
            kept = [rows[0]] + [r for r in rows[1:] if r and r[0] >= cutoff]
            if len(kept) != len(rows):
                tmp = p + ".tmp"
                with open(tmp, "w", newline="") as f:
                    csv.writer(f).writerows(kept)
                os.replace(tmp, p)
                print(f"Cleaned {len(rows) - len(kept)} old rows from {name}", flush=True)
        except Exception as e:
            print("Cleanup error:", e, flush=True)


# ---------- pay periods ----------
def period_bounds(per, today, back=0):
    """(start, end) dates of the pay period `back` periods before the current one."""
    a = date.fromisoformat(per["anchor"])
    length = 7 * per["weeks"]
    idx = (today - a).days // length
    start = a + timedelta(days=(idx - back) * length)
    return start, start + timedelta(days=length - 1)


def summarize(per, rows, sess, t):
    today = t.date()
    ps, pe = period_bounds(per, today)
    ws = today - timedelta(days=today.weekday())
    td = sum_range(rows, today, today)
    wk = sum_range(rows, ws, ws + timedelta(days=6))
    total = sum_range(rows, ps, pe)
    live = None
    if sess:
        start = datetime.fromisoformat(sess["start"])

        def part(d):
            mid = datetime.combine(d, datetime.min.time(), tzinfo=t.tzinfo)
            return max(0, (t - max(start, mid)).total_seconds() / 3600)

        td += part(today)
        wk += part(ws)
        total += part(ps)
        live = {"zone": sess["zone"], "since": start}
    return {
        "today": td,
        "week": wk,
        "period": total,
        "period_start": ps,
        "period_end": pe,
        "period_label": f"{ps:%a %b} {ps.day} – {pe:%a %b} {pe.day}",
        "live": live,
    }


def build_history(pid, rows, today, hist, per):
    """Totals for finished pay periods. Kept after old CSV rows are cleaned up."""
    store = hist.setdefault(pid, {})
    n = per["history"]
    cutoff = today - timedelta(days=KEEP_DAYS) if KEEP_DAYS > 0 else None
    for k in range(1, n + 1):
        a, b = period_bounds(per, today, k)
        if cutoff is None or a >= cutoff:  # whole period still has its rows
            h = sum_range(rows, a, b)
            key = a.isoformat()
            if h > 0 or key in store:
                store[key] = {"start": key, "end": b.isoformat(), "hours": round(h, 2)}
    items = sorted(store.values(), key=lambda x: x["start"], reverse=True)[:n]
    hist[pid] = {i["start"]: i for i in items}
    return items


def snapshot_history():
    """Before old rows are deleted, record the totals of every period they touch."""
    today = now().date()
    with lock:
        s = load_settings()
        hist = load_json(HISTORY, {})
    for p in s["people"]:
        per = p["period"]
        rows = read_rows(p["file"])
        store = hist.setdefault(p["id"], {})
        for k in range(1, per["history"] + 1):
            a, b = period_bounds(per, today, k)
            h = round(sum_range(rows, a, b), 2)
            key = a.isoformat()
            if h > 0:
                # max(): rows may already be partly deleted, so never go down
                best = max(h, store.get(key, {}).get("hours", 0))
                store[key] = {"start": key, "end": b.isoformat(), "hours": best}
        items = sorted(store.values(), key=lambda x: x["start"], reverse=True)[: per["history"]]
        hist[p["id"]] = {i["start"]: i for i in items}
    with lock:
        save_json(HISTORY, hist)


# ---------- tracking ----------
def tick():
    with lock:
        s = load_settings()
        sessions = load_json(SESSIONS, {})

    cfg = {p["id"]: p for p in s["people"]}
    zone_cache = {}

    def zone_name(zid):
        if zid not in zone_cache:
            try:
                st = ha(f"/states/{zid}")
                zone_cache[zid] = st["attributes"].get("friendly_name", zid).lower()
            except Exception as e:
                print("Zone lookup failed:", zid, e, flush=True)
                zone_cache[zid] = None
        return zone_cache[zid]

    t = now()

    # people removed from tracking: close their open visit
    for pid in list(sessions):
        if pid not in cfg:
            sess = sessions[pid]
            end = datetime.fromisoformat(sess["left_at"]) if sess.get("left_at") else t
            try:
                log_session(
                    sess.get("file", pid.split(".", 1)[1]),
                    sess["zone"],
                    datetime.fromisoformat(sess["start"]),
                    end,
                )
                del sessions[pid]
            except Exception as e:
                print("Write failed:", e, flush=True)

    for pid, person in cfg.items():
        try:
            state = ha(f"/states/{pid}")["state"]
        except Exception as e:
            print("Person lookup failed:", pid, e, flush=True)
            continue
        if state in ("unavailable", "unknown"):
            continue

        names = [n for n in (zone_name(z) for z in person.get("zones", [])) if n]
        cur = state if state.lower() in names else None

        sess = sessions.get(pid)
        if sess:
            if cur == sess["zone"]:
                sess["left_at"] = None
            else:
                if not sess.get("left_at"):
                    sess["left_at"] = t.isoformat()
                left = datetime.fromisoformat(sess["left_at"])
                if cur is not None or (t - left).total_seconds() >= GRACE * 60:
                    try:
                        log_session(
                            sess.get("file", person["file"]),
                            sess["zone"],
                            datetime.fromisoformat(sess["start"]),
                            left,
                        )
                        del sessions[pid]
                    except Exception as e:
                        print("Write failed (will retry):", e, flush=True)
                        continue
        if pid not in sessions and cur:
            sessions[pid] = {
                "zone": cur,
                "start": t.isoformat(),
                "left_at": None,
                "file": person["file"],
            }

    with lock:
        save_json(SESSIONS, sessions)


# ---------- MQTT ----------
def mqtt_creds():
    host = (OPTS.get("mqtt_host") or "").strip()
    if host:
        return {
            "host": host,
            "port": int(OPTS.get("mqtt_port") or 1883),
            "username": OPTS.get("mqtt_username") or None,
            "password": OPTS.get("mqtt_password") or None,
        }
    r = requests.get("http://supervisor/services/mqtt", headers=HEADERS, timeout=10)
    r.raise_for_status()
    d = r.json()["data"]
    return {
        "host": d["host"],
        "port": int(d["port"]),
        "username": d.get("username"),
        "password": d.get("password"),
        "ssl": d.get("ssl"),
    }


def _on_connect(client, userdata, *args):
    rc = args[1] if len(args) > 1 else 0
    failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
    if failed:
        print("MQTT connect refused:", rc, flush=True)
        return
    client.publish(AVAIL, "online", qos=1, retain=True)
    mq_state["ready"] = True
    mq_state["resend"] = True
    print("MQTT connected", flush=True)


def _on_disconnect(client, userdata, *args):
    mq_state["ready"] = False
    print("MQTT disconnected", flush=True)


def mqtt_start():
    global mq
    if paho is None:
        print("MQTT library missing, skipping MQTT sensors", flush=True)
        mq = False
        return
    creds = mqtt_creds()
    try:
        c = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="work_hours_tracker")
    except AttributeError:
        c = paho.Client(client_id="work_hours_tracker")
    if creds.get("username"):
        c.username_pw_set(creds["username"], creds.get("password"))
    if creds.get("ssl"):
        c.tls_set()
    c.will_set(AVAIL, "offline", qos=1, retain=True)
    c.on_connect = _on_connect
    c.on_disconnect = _on_disconnect
    c.connect_async(creds["host"], creds["port"], 60)
    c.loop_start()
    mq = c


def mq_pub(topic, payload):
    mq.publish(topic, payload, qos=1, retain=True)


def slug_of(p):
    return re.sub(r"[^a-z0-9_]+", "_", p["file"].lower()).strip("_") or p["id"].split(".", 1)[1]


def display_name(p):
    if p.get("name"):
        return p["name"]
    pid = p["id"]
    if pid not in name_cache:
        try:
            name_cache[pid] = ha(f"/states/{pid}")["attributes"].get("friendly_name") or ""
        except Exception:
            name_cache[pid] = ""
    return name_cache[pid] or p["file"].replace("_", " ")


def discovery_topics(slug):
    base = "homeassistant"
    return (
        f"{base}/sensor/work_hours/{slug}_hours/config",
        f"{base}/binary_sensor/work_hours/{slug}_at_work/config",
        f"{base}/binary_sensor/work_hours/{slug}_day_off/config",
    )


def _hm(v):
    """'08:30' -> minutes since midnight (24:00 = 1440), or None."""
    try:
        h, m = str(v).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _hm_text(mins):
    mins = int(round(mins))
    return "%d:%02d %s" % ((mins // 60) % 12 or 12, mins % 60, "AM" if (mins // 60) % 24 < 12 else "PM")


def _median(vals):
    vals = sorted(vals)
    return vals[len(vals) // 2] if vals else None


def person_stats(rows, sm, last_hours, per, today, off, hist):
    """Everything worth knowing about one person's hours, as small plain values for the summary entity."""
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    totals = {d: sum(float(r["hours"]) for r in rs) for d, rs in by_day.items()}
    a30 = (today - timedelta(days=29)).isoformat()
    recent = {d: h for d, h in totals.items() if d >= a30}
    ps, pe = sm["period_start"].isoformat(), sm["period_end"].isoformat()
    in_period = {d: h for d, h in totals.items() if ps <= d <= pe}
    starts = [m for d, rs in by_day.items() if d >= a30 for m in [min((_hm(r["start"]) for r in rs if _hm(r["start"]) is not None), default=None)] if m is not None]
    ends = [m for d, rs in by_day.items() if d >= a30 for m in [max((_hm(r["end"]) for r in rs if _hm(r["end"]) is not None), default=None)] if m is not None]
    longest = max(recent.items(), key=lambda kv: kv[1], default=None)
    worked_dates = sorted(totals)
    live = sm["live"]
    out = {
        "today_hours": round(sm["today"], 2), "week_hours": round(sm["week"], 2),
        "week_overtime_hours": round(max(0.0, sm["week"] - 40), 2),
        "period_hours": round(sm["period"], 2), "last_period_hours": last_hours,
        "period_label": sm["period_label"], "period_start": ps, "period_end": pe,
        "period_days_left": (sm["period_end"] - today).days + 1, "pay_period_weeks": per["weeks"], "pay_period_starts_on": per["start_day"],
        "period_days_worked": len(in_period),
        "period_avg_hours_per_day_worked": round(sum(in_period.values()) / len(in_period), 2) if in_period else 0,
        "last_30_days_hours": round(sum(recent.values()), 2), "last_30_days_days_worked": len(recent),
        "last_30_days_avg_hours_per_day_worked": round(sum(recent.values()) / len(recent), 2) if recent else 0,
        "longest_day_last_30_days": {"date": longest[0], "hours": round(longest[1], 2)} if longest else None,
        "typical_start": _hm_text(_median(starts)) if starts else None,
        "typical_end": _hm_text(_median(ends)) if ends else None,
        "last_worked_date": worked_dates[-1] if worked_dates else None,
        "clocked_in": bool(live), "current_zone": live["zone"] if live else None,
        "clocked_in_since": live["since"].isoformat() if live else None,
        "day_off_today": off["off_today"], "day_off_reason": off["today_name"] or None,
        "next_day_off": off["next_date"] or None, "next_day_off_name": off["next_name"] or None,
        "days_until_next_day_off": off["days_until"],
        "previous_periods": [{"start": h["start"], "end": h["end"], "hours": h["hours"]} for h in (hist or [])[:8]],
    }
    return out


def work_status(st):
    """The one-line answer to 'what is up with work right now'."""
    if st["clocked_in"]:
        return "At work" + (" (%s)" % st["current_zone"] if st["current_zone"] else "")
    if st["day_off_today"]:
        return "Day off" + (" (%s)" % st["day_off_reason"] if st["day_off_reason"] else "")
    if st.get("has_schedule"):
        sh = st.get("scheduled_today")
        if sh:
            return "Scheduled today %s to %s" % (schedule.label(sh["start"]), schedule.label(sh["end"]))
        return "Not scheduled today"
    return "Not at work"


def stats_line(name, st):
    """One plain sentence about a person, for the summary's text attribute."""
    bits = []
    if st.get("has_schedule"):
        bits.append("schedule: " + st["schedule_text"])
        if st["day_off_today"]:
            pass
        elif st["scheduled_today"]:
            bits.append("scheduled today %s to %s" % (schedule.label(st["scheduled_today"]["start"]), schedule.label(st["scheduled_today"]["end"])))
        else:
            bits.append("not scheduled today")
        if st["next_shift"] and not (st["scheduled_today"] and st["next_shift"]["days_until"] == 0):
            ns = st["next_shift"]
            bits.append("next shift %s %s %s to %s" % (ns["weekday"], ns["date"], schedule.label(ns["start"]), schedule.label(ns["end"])))
    bits += ["clocked in at %s" % st["current_zone"] if st["clocked_in"] else "not clocked in",
            "%.1f h today" % st["today_hours"], "%.1f h this week" % st["week_hours"],
            "%.1f h this pay period (%d days left)" % (st["period_hours"], st["period_days_left"])]
    if st["week_overtime_hours"]:
        bits.append("%.1f h overtime this week" % st["week_overtime_hours"])
    if st["day_off_today"]:
        bits.append("off today" + (" (%s)" % st["day_off_reason"] if st["day_off_reason"] else ""))
    elif st["next_day_off"]:
        bits.append("next day off %s on %s" % (st["next_day_off_name"] or "", st["next_day_off"]))
    return "%s: %s" % (name, ", ".join(bits))


def publish_mqtt():
    global mq_sig
    if not mq or not mq_state["ready"]:
        return

    with lock:
        s = load_settings()
        sessions = load_json(SESSIONS, {})
        hist = load_json(HISTORY, {})
    t = now()
    today = t.date()

    people = [(slug_of(p), p, display_name(p)) for p in s["people"]]
    off_cfg = load_days_off()
    off_cal = calendar_events(off_cfg["calendar"])

    # discovery: (re)announce sensors, and remove ones for people no longer tracked
    sig = json.dumps([(sl, nm) for sl, _, nm in people])
    if mq_state["resend"] or sig != mq_sig:
        for slug, p, name in people:
            sensor_topic, bin_topic, off_topic = discovery_topics(slug)
            mq_pub(sensor_topic, json.dumps({
                "name": f"{name} work hours",
                "unique_id": f"work_hours_{slug}_hours",
                "state_topic": f"work_hours/{slug}/state",
                "json_attributes_topic": f"work_hours/{slug}/attributes",
                "availability_topic": AVAIL,
                "unit_of_measurement": "h",
                "device_class": "duration",
                "suggested_display_precision": 2,
                "icon": "mdi:briefcase-clock",
                "device": DEVICE,
            }))
            mq_pub(bin_topic, json.dumps({
                "name": f"{name} at work",
                "unique_id": f"work_hours_{slug}_at_work",
                "state_topic": f"work_hours/{slug}/at_work",
                "availability_topic": AVAIL,
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": "mdi:hard-hat",
                "device": DEVICE,
            }) if SEPARATE else "")  # empty retained payload removes the entity: everything is in the one sensor's attributes now
            mq_pub(off_topic, json.dumps({
                "name": f"{name} day off",
                "unique_id": f"work_hours_{slug}_day_off",
                "state_topic": f"work_hours/{slug}/day_off",
                "json_attributes_topic": f"work_hours/{slug}/day_off_attributes",
                "availability_topic": AVAIL,
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": "mdi:beach",
                "device": DEVICE,
            }) if SEPARATE else "")
        mq_pub("homeassistant/sensor/work_hours/summary/config", json.dumps({
            "name": "Work Hours Summary",
            "unique_id": "work_hours_summary",
            "state_topic": "work_hours/summary/state",
            "json_attributes_topic": "work_hours/summary/attributes",
            "availability_topic": AVAIL,
            "icon": "mdi:briefcase-clock-outline",
            "device": DEVICE,
        }))
        old = set(load_json(MQTT_SLUGS, []))
        now_slugs = {sl for sl, _, _ in people}
        for gone in old - now_slugs:
            for topic in discovery_topics(gone):
                mq_pub(topic, "")  # empty retained payload deletes the entity
        save_json(MQTT_SLUGS, sorted(now_slugs))
        mq_sig = sig
        mq_last.clear()
        mq_state["resend"] = False

    changed_hist = False
    summary = {}
    sched_all = load_schedule()
    for slug, p, name in people:
        per = p["period"]
        rows = read_rows(p["file"])
        sm = summarize(per, rows, sessions.get(p["id"]), t)
        before = json.dumps(hist.get(p["id"]), sort_keys=True)
        history = build_history(p["id"], rows, today, hist, per)
        if json.dumps(hist.get(p["id"]), sort_keys=True) != before:
            changed_hist = True

        prev_start, _ = period_bounds(per, today, 1)
        last_hours = next((h["hours"] for h in history if h["start"] == prev_start.isoformat()), 0)
        live = sm["live"]
        off = days_off.status(p["id"], off_cfg["items"], today, off_cal)
        summary[name] = person_stats(rows, sm, last_hours, per, today, off, history)
        wk0 = min(sm["period_start"], today - timedelta(days=today.weekday()))
        off_map = days_off.days_for(p["id"], off_cfg["items"], wk0, today + timedelta(days=14), off_cal)
        summary[name].update(schedule.stats(sched_all.get(p["id"]), today, off_map, summary[name]["week_hours"],
                                            t.hour * 60 + t.minute, sm["period_start"], sm["period_end"]))
        attrs = {
            "person": name,
            "day_off_today": off["off_today"],
            "next_day_off": off["next_date"] or None,
            "period_label": sm["period_label"],
            "period_start": sm["period_start"].isoformat(),
            "period_end": sm["period_end"].isoformat(),
            "period_length_days": 7 * per["weeks"],
            "days_left": (sm["period_end"] - today).days + 1,
            "today_hours": round(sm["today"], 2),
            "week_hours": round(sm["week"], 2),
            "last_period_hours": last_hours,
            "clocked_in": bool(live),
            "current_zone": live["zone"] if live else None,
            "clocked_in_since": live["since"].isoformat() if live else None,
            "file": file_path(p["file"]),
            "history": history,
        }
        st_all = summary[name]
        for k, v in st_all.items():   # every statistic, the schedule and the days off: one sensor shows everything
            attrs.setdefault(k, v)
        attrs["status"] = work_status(st_all)
        attrs["text"] = stats_line(name, st_all)
        topics = {
            f"work_hours/{slug}/state": f"{round(sm['period'], 2):.2f}",
            f"work_hours/{slug}/attributes": json.dumps(attrs, ensure_ascii=False),
            f"work_hours/{slug}/at_work": "ON" if live else "OFF",
            f"work_hours/{slug}/day_off": "ON" if off["off_today"] else "OFF",
            f"work_hours/{slug}/day_off_attributes": json.dumps({
                "person": name, "reason": off["today_name"] or None, "next_date": off["next_date"] or None,
                "next_name": off["next_name"] or None, "days_until_next": off["days_until"],
                "upcoming": off["upcoming"]}, ensure_ascii=False),
        }
        if not SEPARATE:  # the old separate sensors are gone: nothing to send for them
            for t_ in (f"work_hours/{slug}/at_work", f"work_hours/{slug}/day_off", f"work_hours/{slug}/day_off_attributes"):
                topics.pop(t_, None)
        for topic, payload in topics.items():
            if mq_last.get(topic) != payload:
                mq_pub(topic, payload)
                mq_last[topic] = payload

    clocked = [n for n, st in summary.items() if st["clocked_in"]]
    off_now = [n for n, st in summary.items() if st["day_off_today"]]
    sum_attrs = {
        "people": summary, "people_names": list(summary),
        "clocked_in_now": clocked, "off_today": off_now,
        "total_hours_today": round(sum(st["today_hours"] for st in summary.values()), 2),
        "total_hours_this_week": round(sum(st["week_hours"] for st in summary.values()), 2),
        "text": "\n".join(stats_line(n, st) for n, st in summary.items()),
        "updated": t.isoformat(timespec="seconds"),
    }
    sum_topics = {"work_hours/summary/state": str(len(clocked)),
                  "work_hours/summary/attributes": json.dumps(sum_attrs, ensure_ascii=False)}
    for topic, payload in sum_topics.items():
        if mq_last.get(topic) != payload:
            mq_pub(topic, payload)
            mq_last[topic] = payload

    if changed_hist:
        with lock:
            save_json(HISTORY, hist)


def worker():
    global mq
    last_clean = 0
    last_mq_try = 0
    while True:
        try:
            tick()
        except Exception as e:
            print("Tick error:", e, flush=True)
        if mq is None and time.time() - last_mq_try > 300:
            last_mq_try = time.time()
            try:
                mqtt_start()
            except Exception as e:
                print("MQTT not available yet:", e, flush=True)
        try:
            publish_mqtt()
        except Exception as e:
            print("MQTT publish error:", e, flush=True)
        if time.time() - last_clean > 6 * 3600:
            cleanup()
            last_clean = time.time()
        time.sleep(CHECK)


# ---------- web UI ----------
@app.get("/")
def index():
    return send_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))


@app.post("/api/ai")
def api_ai():
    """Answer a question about someone's logged hours (Home Assistant AI Task)."""
    import ha_ai
    b = request.get_json(force=True, silent=True) or {}
    pid, q = str(b.get("id") or ""), str(b.get("question") or "").strip()[:500]
    with lock:
        s = load_settings()
    p = next((x for x in s["people"] if x["id"] == pid), None)
    if not p:
        return jsonify({"ok": False, "error": "Unknown person"})
    rows = read_rows(p["file"])
    days = {}
    for r in rows:
        days.setdefault(r["date"], []).append(r)
    recent = sorted(days)[-120:]
    lines = ["%s (%s): %.2f h, %s" % (d, date.fromisoformat(d).strftime("%a"), sum(float(r["hours"]) for r in days[d]),
             ", ".join("%s %s-%s" % (r["zone"], r["start"], r["end"]) for r in days[d])) for d in recent]
    t = now()
    off_cfg = load_days_off()
    off_line = days_off.prompt_text(pid, off_cfg["items"], t.date(), calendar_events(off_cfg["calendar"]))
    try:
        text = ha_ai.ask(("Today is %s. " + off_line.replace("%", "%%") + " Below is one person's work log from a home time tracker (date: total hours, visits). "
                         "Their pay period: %s, %d week(s). Answer the question in plain words with the numbers, short. If no "
                         "question, give a quick summary: this week vs usual, longest days, typical start and end times, "
                         "overtime (over 40 h a week).\n\nQuestion: %s\n\n%s")
                         % (t.strftime("%A %Y-%m-%d"), p["period"]["start_day"], p["period"]["weeks"], q or "(none)",
                            "\n".join(lines) or "No hours logged yet."), OPTS.get("ai_task_entity") or "", "Work hours")
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": True, "text": text})


@app.get("/api/state")
def api_state():
    with lock:
        s = load_settings()
        sessions = load_json(SESSIONS, {})

    err = None
    people, zones, cals = [], [], []
    try:
        for e in ha("/states"):
            eid = e["entity_id"]
            nm = e["attributes"].get("friendly_name", eid)
            if eid.startswith("person."):
                people.append({"id": eid, "name": nm})
            elif eid.startswith("zone."):
                zones.append({"id": eid, "name": nm})
            elif eid.startswith("calendar."):
                cals.append({"id": eid, "name": nm})
    except Exception as ex:
        err = f"Can't reach Home Assistant: {ex}"

    names = {p["id"]: p["name"] for p in people}
    zone_names = {z["id"]: z["name"] for z in zones}
    t = now()

    off_cfg = load_days_off()
    off_cal = calendar_events(off_cfg["calendar"])
    status = []
    for p in s["people"]:
        pid = p["id"]
        rows = read_rows(p["file"])
        sm = summarize(p["period"], rows, sessions.get(pid), t)
        live = None
        if sm["live"]:
            live = {"zone": sm["live"]["zone"], "since": sm["live"]["since"].strftime("%b %d, %I:%M %p")}
        status.append({
            "id": pid,
            "name": names.get(pid, pid),
            "zones": [zone_names.get(z, z) for z in p.get("zones", [])],
            "today": round(sm["today"], 2),
            "week": round(sm["week"], 2),
            "period": round(sm["period"], 2),
            "period_label": sm["period_label"],
            "live": live,
            "file": file_path(p["file"]),
            "recent": rows[-8:][::-1],
            "day_off": days_off.status(pid, off_cfg["items"], t.date(), off_cal),
        })

    mqtt_text = "off"
    if mq:
        mqtt_text = "connected" if mq_state["ready"] else "connecting..."
    elif mq is False:
        mqtt_text = "library missing"

    return jsonify({
        "error": err,
        "people": people,
        "zones": zones,
        "settings": s,
        "default_period": clean_period({}, t.date()),
        "status": status,
        "days_off": off_cfg,
        "schedule": load_schedule(),
        "calendars": cals,
        "info": {
            "folder": FOLDER,
            "keep_days": KEEP_DAYS,
            "grace": GRACE,
            "min": MIN_MIN,
            "mqtt": mqtt_text,
        },
    })


@app.post("/api/settings")
def api_settings():
    data = request.get_json(force=True) or {}
    with lock:
        today = now().date()
        old = {p["id"]: p for p in load_settings()["people"]}
        out, used = [], set()
        for item in data.get("people", []):
            pid = str(item.get("id", ""))
            if not re.fullmatch(r"person\.[a-z0-9_]+", pid):
                continue
            zones = []
            for z in item.get("zones", []):
                if re.fullmatch(r"zone\.[a-z0-9_]+", str(z)) and z not in zones:
                    zones.append(z)
            try:
                nm = ha(f"/states/{pid}")["attributes"].get("friendly_name", "")
            except Exception:
                nm = old.get(pid, {}).get("name", "")
            if pid in old:
                fname = old[pid]["file"]  # keep the same file once it exists
            else:
                fname = re.sub(r"[^A-Za-z0-9_-]+", "_", nm).strip("_") or pid.split(".", 1)[1]
            base, n = fname, 2
            while fname.lower() in used:
                fname = f"{base}_{n}"
                n += 1
            used.add(fname.lower())
            period = clean_period(item.get("period") or old.get(pid, {}).get("period") or {}, today)
            out.append({
                "id": pid,
                "file": fname,
                "name": nm or fname.replace("_", " "),
                "zones": zones,
                "period": period,
            })
        save_json(SETTINGS, {"people": out})
    return jsonify({"ok": True})


@app.post("/api/schedule")
def api_schedule():
    data = schedule.clean(request.get_json(force=True, silent=True) or {})
    with lock:
        save_json(SCHEDULE, data)
    return jsonify({"ok": True, "schedule": data})


@app.post("/api/days_off")
def api_days_off():
    data = days_off.clean(request.get_json(force=True, silent=True) or {})
    with lock:
        save_json(DAYS_OFF, data)
    cal_cache.clear()
    return jsonify({"ok": True, "days_off": data})


# ---------- backups (shared module, see addon_backup.py) ----------
@app.route("/backups", defaults={"sub": ""}, methods=["GET", "POST"])
@app.route("/backups/<path:sub>", methods=["GET", "POST"])
def backups(sub):
    st, ct, body, hdr = BACKUP.handle(request.method, sub, request.args, request.get_data(), request.remote_addr)
    return Response(body, status=st, content_type=ct, headers=hdr)


if __name__ == "__main__":
    BACKUP.start()
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8099, threaded=True)

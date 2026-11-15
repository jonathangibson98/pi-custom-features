"""Sleep Tracker: decides whether each chosen person is asleep from several signals at once.

Each person has weighted signals (phone charging, Sleep Focus, phone still, bedroom lights off, TV off, no motion...).
The share of the weight that currently agrees is the "confidence". Someone falls asleep when the confidence stays at or
above the fall-asleep level for the settle time (the start is dated back to when it first got there), and wakes when it
stays below the wake level for the wake time, or straight away when a "must be true" signal stops being true.
Short wake-ups (bathroom trips) inside the wake grace are counted as interruptions of the same night.
Results are published as MQTT entities, with buttons to mark someone asleep or awake by hand.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request, send_file

try:
    import paho.mqtt.client as paho
except Exception:  # paho missing: MQTT is skipped, the web UI still works
    paho = None

VERSION = "1.0.0"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = os.environ.get("ST_HA_API", "http://supervisor/core/api")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

DATA_DIR = os.environ.get("ST_DATA_DIR", "/data")
with open(os.path.join(DATA_DIR, "options.json")) as f:
    OPTS = json.load(f)

CHECK = int(OPTS.get("check_seconds", 30))
KEEP_DAYS = int(OPTS.get("keep_days", 90))

SETTINGS = os.path.join(DATA_DIR, "settings.json")
LIVE = os.path.join(DATA_DIR, "live.json")
HISTORY = os.path.join(DATA_DIR, "history.json")
MQTT_SLUGS = os.path.join(DATA_DIR, "mqtt_slugs.json")

AVAIL = "sleep_tracker/status"
DEVICE = {"identifiers": ["sleep_tracker"], "name": "Sleep Tracker", "manufacturer": "jonathangibson98",
          "model": "Sleep Tracker", "sw_version": VERSION}
MODES = ("is", "is_not", "below", "above", "quiet")
STATUS_TEXT = {"awake": "Awake", "settling": "Falling asleep", "asleep": "Asleep", "away": "Away", "off": "Not tracking"}

PERSON_DEFAULTS = {"night_from": "20:00", "night_to": "12:00", "home_only": True, "naps": False,
                   "fall_level": 70, "wake_level": 40, "settle_minutes": 15, "wake_minutes": 5,
                   "wake_grace": 20, "min_sleep": 20, "enabled": True}

lock = threading.RLock()
app = Flask(__name__)
_tz = None
mq = None
mq_state = {"ready": False, "resend": True}
mq_last = {}
mq_sig = None
LAST = {}  # person id -> latest evaluation, for the UI


# ---------- small helpers ----------
def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def ha(path, method="GET", body=None):
    r = requests.request(method, API + path, headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def tz():
    global _tz
    if _tz is None:
        try:
            _tz = ZoneInfo(ha("/config").get("time_zone") or "UTC")
        except Exception:
            return ZoneInfo("UTC")
    return _tz


def now():
    return datetime.now(tz())


def iso(t):
    return t.isoformat(timespec="seconds") if t else None


def parse(s):
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=tz())
    except ValueError:
        return None


def hm(s, default):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(s or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return default
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2)))


def in_night(p, t):
    a, b = p["night_from"], p["night_to"]
    x = t.strftime("%H:%M")
    return (a <= x < b) if a < b else (x >= a or x < b)


def slug_of(pid):
    return re.sub(r"[^a-z0-9_]+", "_", pid.split(".", 1)[-1].lower()).strip("_") or "person"


def clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return default


# ---------- settings ----------
def clean_signal(s):
    if not isinstance(s, dict):
        return None
    ents = [e for e in (s.get("entities") or [])
            if isinstance(e, str) and re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", e)]
    ents = list(dict.fromkeys(ents))[:20]
    if not ents:
        return None
    mode = s.get("mode") if s.get("mode") in MODES else "is"
    vals = s.get("values")
    if isinstance(vals, str):
        vals = [v.strip() for v in vals.split(",")]
    vals = [str(v).strip()[:60] for v in (vals or []) if str(v).strip()][:12]
    return {"label": str(s.get("label") or ents[0])[:60], "entities": ents,
            "need": "any" if s.get("need") == "any" else "all", "mode": mode,
            "attribute": str(s.get("attribute") or "").strip()[:60], "values": vals,
            "number": float(s.get("number") or 0) if mode in ("below", "above") else 0,
            "minutes": clamp(s.get("minutes"), 0, 600, 10), "weight": clamp(s.get("weight"), 1, 5, 1),
            "required": bool(s.get("required"))}


def clean_person(p, old=None):
    pid = str(p.get("id") or "")
    if not re.fullmatch(r"person\.[a-z0-9_]+", pid):
        return None
    out = dict(PERSON_DEFAULTS)
    out.update(old or {})
    out["id"] = pid
    out["name"] = str(p.get("name") or (old or {}).get("name") or pid.split(".", 1)[1].replace("_", " ").title())[:40]
    out["night_from"] = hm(p.get("night_from"), out["night_from"])
    out["night_to"] = hm(p.get("night_to"), out["night_to"])
    for k in ("home_only", "naps", "enabled"):
        if k in p:
            out[k] = bool(p[k])
    for k, lo, hi in (("fall_level", 10, 100), ("wake_level", 0, 95), ("settle_minutes", 0, 120),
                      ("wake_minutes", 0, 120), ("wake_grace", 0, 180), ("min_sleep", 0, 600)):
        if k in p:
            out[k] = clamp(p[k], lo, hi, out[k])
    if out["wake_level"] >= out["fall_level"]:
        out["wake_level"] = max(0, out["fall_level"] - 10)
    if "signals" in p:
        out["signals"] = [x for x in (clean_signal(s) for s in (p.get("signals") or [])) if x][:20]
    out.setdefault("signals", [])
    return out


def load_settings():
    s = load_json(SETTINGS, {"people": []})
    s.setdefault("people", [])
    return s


# ---------- judging the signals ----------
def value_of(sig, st):
    if sig["attribute"]:
        v = (st.get("attributes") or {}).get(sig["attribute"])
        return None if v is None else str(v)
    return str(st.get("state"))


def match_one(sig, st, t):
    """True / False, or None when the entity can't tell (missing, unavailable)."""
    if not st or st.get("state") in ("unavailable", "unknown", None):
        return None
    m = sig["mode"]
    if m == "quiet":
        ch = parse(st.get("last_changed"))
        return bool(ch) and (t - ch).total_seconds() >= sig["minutes"] * 60
    v = value_of(sig, st)
    if v is None:
        return None
    if m in ("is", "is_not"):
        hit = v.strip().lower() in [x.lower() for x in sig["values"]]
        return hit if m == "is" else not hit
    try:
        n = float(v)
    except ValueError:
        return None
    return n < sig["number"] if m == "below" else n > sig["number"]


def judge(p, states, t):
    """Confidence 0-100 from the signals that can tell, plus whether every 'must be true' signal is true."""
    rows, got, total, req_ok = [], 0, 0, True
    for sig in p["signals"]:
        vals = [match_one(sig, states.get(e), t) for e in sig["entities"]]
        vals = [v for v in vals if v is not None]
        ok = None if not vals else (all(vals) if sig["need"] == "all" else any(vals))
        if ok is not None:
            total += sig["weight"]
            got += sig["weight"] if ok else 0
            if sig["required"] and not ok:
                req_ok = False
        rows.append({"label": sig["label"], "ok": ok, "weight": sig["weight"], "required": sig["required"]})
    score = round(100 * got / total) if total else 0
    return score, req_ok, rows


def blank_live():
    return {"status": "awake", "since": None, "cand": None, "low": None, "session": None, "pending": None,
            "hold_until": None}


def session_record(p, sess):
    start, end = parse(sess["start"]), parse(sess["end"])
    gaps = sum((parse(b) - parse(a)).total_seconds() for a, b in sess.get("gaps", []))
    in_bed = (end - start).total_seconds()
    return {"start": sess["start"], "end": sess["end"], "minutes": round(max(0, in_bed - gaps) / 60),
            "in_bed_minutes": round(in_bed / 60), "interruptions": sess.get("interruptions", 0),
            "awake_minutes": round(gaps / 60), "nap": not in_night(p, start)}


def finish(p, lv, hist):
    """The wake grace is over: the session is final."""
    pend = lv.get("pending")
    lv["pending"] = None
    if not pend:
        return
    rec = session_record(p, pend)
    if rec["minutes"] >= p["min_sleep"]:
        hist.setdefault(p["id"], []).append(rec)


def fall_asleep(p, lv, start, hist, manual=False):
    pend = lv.get("pending")
    if pend and (start - parse(pend["end"])).total_seconds() <= p["wake_grace"] * 60:
        pend["gaps"].append([pend["end"], iso(start)])  # back to sleep after a short wake-up: same night
        pend["interruptions"] = pend.get("interruptions", 0) + 1
        pend.pop("end", None)
        lv["session"], lv["pending"] = pend, None
    else:
        finish(p, lv, hist)
        lv["session"] = {"start": iso(start), "gaps": [], "interruptions": 0, "manual": manual}
    lv.update(status="asleep", since=iso(start), cand=None, low=None, hold_until=None)


def wake_up(p, lv, end, hold=0):
    sess = lv.get("session")
    if sess:
        sess["end"] = iso(end)
        lv["pending"] = sess
    lv.update(status="awake", since=iso(end), session=None, cand=None, low=None,
              hold_until=iso(end + timedelta(minutes=hold)) if hold else None)


def step(p, lv, st_person, states, t, hist):
    """Move one person's state along. Returns the evaluation shown in the UI and published."""
    score, req_ok, rows = judge(p, states, t)
    home = (st_person or {}).get("state") == "home" if p["home_only"] else True
    pend = lv.get("pending")
    if pend and lv["status"] != "asleep":
        grace = p["wake_grace"] * 60
        cand = parse(lv.get("cand"))
        back_down = cand and (cand - parse(pend["end"])).total_seconds() <= grace  # lying back down in time: wait for it
        if (t - parse(pend["end"])).total_seconds() > grace and not back_down:
            finish(p, lv, hist)
    if not p.get("enabled", True):
        if lv["status"] == "asleep":
            wake_up(p, lv, t)
        lv["status"] = "off"
    elif not home:
        if lv["status"] == "asleep":
            wake_up(p, lv, t)
        if lv["status"] != "away":
            lv.update(status="away", since=iso(t), cand=None, low=None)
    elif lv["status"] == "asleep":
        if not req_ok and not (lv.get("session") or {}).get("manual"):
            wake_up(p, lv, t)  # a must-be-true signal stopped: awake now
        elif score < p["wake_level"]:
            lv["low"] = lv.get("low") or iso(t)
            if (t - parse(lv["low"])).total_seconds() >= p["wake_minutes"] * 60:
                wake_up(p, lv, parse(lv["low"]))
        else:
            lv["low"] = None
            if req_ok and (lv.get("session") or {}).get("manual"):
                lv["session"]["manual"] = False  # the signals agree now, so normal rules apply from here
    else:
        held = lv.get("hold_until") and t < parse(lv["hold_until"])
        sleepy = score >= p["fall_level"] and req_ok and not held
        cand = parse(lv.get("cand")) or t
        if sleepy and (p["naps"] or in_night(p, cand)):
            lv["cand"] = iso(cand)
            if (t - cand).total_seconds() >= p["settle_minutes"] * 60:
                fall_asleep(p, lv, cand, hist)
            elif lv["status"] != "settling":
                lv.update(status="settling", since=iso(cand))
        else:
            if lv["status"] != "awake":
                lv.update(status="awake", since=iso(t))
            lv["cand"] = None
    return {"score": score, "required_ok": req_ok, "signals": rows, "home": home}


# ---------- summaries ----------
def nights(pid, hist):
    return [r for r in hist.get(pid, []) if not r.get("nap")]


def summary(p, lv, hist, t):
    done = [r for r in hist.get(p["id"], []) if isinstance(r, dict) and parse(r.get("start")) and parse(r.get("end"))]
    pend = lv.get("pending")
    if pend:
        rec = session_record(p, pend)
        if rec["minutes"] >= p["min_sleep"]:
            done.append(dict(rec, provisional=True))
    main = [r for r in done if not r["nap"] and r["minutes"] >= p["min_sleep"]]
    last = main[-1] if main else None
    week = [r for r in main if parse(r["end"]) >= t - timedelta(days=7)]
    naps_today = [r for r in done if r["nap"] and parse(r["end"]).date() == t.date()]
    cur = lv.get("session")
    asleep_for = None
    if lv["status"] == "asleep" and cur:
        asleep_for = round((t - parse(cur["start"])).total_seconds() / 60)
    return {"last": last, "avg_week": round(sum(r["minutes"] for r in week) / len(week)) if week else None,
            "nights_week": len(week), "naps_today": sum(r["minutes"] for r in naps_today),
            "asleep_for": asleep_for, "recent": done[-14:][::-1]}


def nice_time(s):
    t = parse(s)
    if not t:
        return None
    t = t.astimezone(tz())
    return "%d:%02d %s" % ((t.hour % 12) or 12, t.minute, "AM" if t.hour < 12 else "PM")


def day_label(s):
    t = parse(s).astimezone(tz())
    return "%s %d" % (t.strftime("%a %b"), t.day)


# ---------- MQTT ----------
def mqtt_creds():
    host = (OPTS.get("mqtt_host") or "").strip()
    if host:
        return {"host": host, "port": int(OPTS.get("mqtt_port") or 1883),
                "username": OPTS.get("mqtt_username") or None, "password": OPTS.get("mqtt_password") or None}
    r = requests.get("http://supervisor/services/mqtt", headers=HEADERS, timeout=10)
    r.raise_for_status()
    d = r.json()["data"]
    return {"host": d["host"], "port": int(d["port"]), "username": d.get("username"),
            "password": d.get("password"), "ssl": d.get("ssl")}


def _on_connect(client, userdata, *args):
    rc = args[1] if len(args) > 1 else 0
    if (rc.is_failure if hasattr(rc, "is_failure") else rc != 0):
        print("MQTT connect refused:", rc, flush=True)
        return
    client.publish(AVAIL, "online", qos=1, retain=True)
    client.subscribe("sleep_tracker/+/set")
    mq_state.update(ready=True, resend=True)
    print("MQTT connected", flush=True)


def _on_disconnect(client, userdata, *args):
    mq_state["ready"] = False
    print("MQTT disconnected", flush=True)


def _on_message(client, userdata, msg):
    m = re.fullmatch(r"sleep_tracker/([a-z0-9_]+)/set", msg.topic)
    what = msg.payload.decode(errors="ignore").strip().lower()
    if not m or what not in ("asleep", "awake"):
        return
    p = next((x for x in load_settings()["people"] if slug_of(x["id"]) == m.group(1)), None)
    if p:
        manual(p["id"], what)


def mqtt_start():
    global mq
    if paho is None:
        print("MQTT library missing, skipping MQTT entities", flush=True)
        mq = False
        return
    creds = mqtt_creds()
    try:
        c = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="sleep_tracker")
    except AttributeError:
        c = paho.Client(client_id="sleep_tracker")
    if creds.get("username"):
        c.username_pw_set(creds["username"], creds.get("password"))
    if creds.get("ssl"):
        c.tls_set()
    c.will_set(AVAIL, "offline", qos=1, retain=True)
    c.on_connect, c.on_disconnect, c.on_message = _on_connect, _on_disconnect, _on_message
    c.reconnect_delay_set(5, 120)
    c.connect_async(creds["host"], creds["port"], 60)
    c.loop_start()
    mq = c


def pub(topic, payload):
    if mq_last.get(topic) != payload:
        mq.publish(topic, payload, qos=1, retain=True)
        mq_last[topic] = payload


def disc_topics(slug):
    b = "homeassistant"
    return {"asleep": f"{b}/binary_sensor/sleep_tracker/{slug}_asleep/config",
            "status": f"{b}/sensor/sleep_tracker/{slug}_status/config",
            "confidence": f"{b}/sensor/sleep_tracker/{slug}_confidence/config",
            "last": f"{b}/sensor/sleep_tracker/{slug}_last_sleep/config",
            "btn_asleep": f"{b}/button/sleep_tracker/{slug}_mark_asleep/config",
            "btn_awake": f"{b}/button/sleep_tracker/{slug}_mark_awake/config"}


def announce(people):
    """MQTT discovery for every tracked person, removing entities of people no longer tracked."""
    for p in people:
        sl, nm = slug_of(p["id"]), p["name"]
        base = {"availability_topic": AVAIL, "device": DEVICE}
        t = disc_topics(sl)
        mq.publish(t["asleep"], json.dumps(dict(base, name=f"{nm} asleep", unique_id=f"sleep_tracker_{sl}_asleep",
            object_id=f"{sl}_asleep", state_topic=f"sleep_tracker/{sl}/asleep", payload_on="ON", payload_off="OFF",
            json_attributes_topic=f"sleep_tracker/{sl}/attributes", icon="mdi:sleep")), qos=1, retain=True)
        mq.publish(t["status"], json.dumps(dict(base, name=f"{nm} sleep status", unique_id=f"sleep_tracker_{sl}_status",
            object_id=f"{sl}_sleep_status", state_topic=f"sleep_tracker/{sl}/status", icon="mdi:bed-clock")),
            qos=1, retain=True)
        mq.publish(t["confidence"], json.dumps(dict(base, name=f"{nm} sleep confidence",
            unique_id=f"sleep_tracker_{sl}_confidence", object_id=f"{sl}_sleep_confidence",
            state_topic=f"sleep_tracker/{sl}/confidence", unit_of_measurement="%", state_class="measurement",
            icon="mdi:gauge")), qos=1, retain=True)
        mq.publish(t["last"], json.dumps(dict(base, name=f"{nm} last sleep", unique_id=f"sleep_tracker_{sl}_last_sleep",
            object_id=f"{sl}_last_sleep", state_topic=f"sleep_tracker/{sl}/last_sleep", unit_of_measurement="h",
            device_class="duration", suggested_display_precision=1,
            json_attributes_topic=f"sleep_tracker/{sl}/last_sleep_attributes", icon="mdi:power-sleep")),
            qos=1, retain=True)
        for key, what, icon in (("btn_asleep", "asleep", "mdi:sleep"), ("btn_awake", "awake", "mdi:weather-sunny")):
            mq.publish(t[key], json.dumps(dict(base, name=f"{nm} mark {what}", unique_id=f"sleep_tracker_{sl}_mark_{what}",
                object_id=f"{sl}_mark_{what}", command_topic=f"sleep_tracker/{sl}/set", payload_press=what,
                icon=icon)), qos=1, retain=True)
    mq.publish("homeassistant/binary_sensor/sleep_tracker/everyone_asleep/config", json.dumps({
        "name": "Everyone asleep", "unique_id": "sleep_tracker_everyone_asleep", "object_id": "everyone_asleep",
        "state_topic": "sleep_tracker/everyone_asleep", "payload_on": "ON", "payload_off": "OFF",
        "json_attributes_topic": "sleep_tracker/everyone_attributes", "availability_topic": AVAIL,
        "icon": "mdi:home-sound-out", "device": DEVICE}), qos=1, retain=True)
    old, now_slugs = set(load_json(MQTT_SLUGS, [])), {slug_of(p["id"]) for p in people}
    for gone in old - now_slugs:
        for topic in disc_topics(gone).values():
            mq.publish(topic, "", qos=1, retain=True)  # empty retained config removes the entity
    save_json(MQTT_SLUGS, sorted(now_slugs))


def publish(people, lives, evals, hist, t):
    global mq_sig
    if not mq or not mq_state["ready"]:
        return
    sig = json.dumps([(p["id"], p["name"]) for p in people])
    if mq_state["resend"] or sig != mq_sig:
        announce(people)
        mq_sig, mq_state["resend"] = sig, False
        mq_last.clear()
    home_asleep, home_people = [], []
    for p in people:
        sl, lv, ev = slug_of(p["id"]), lives[p["id"]], evals[p["id"]]
        sm = summary(p, lv, hist, t)
        if lv["status"] not in ("away", "off"):
            home_people.append(p["name"])
            if lv["status"] == "asleep":
                home_asleep.append(p["name"])
        cur = lv.get("session") or {}
        attrs = {"status": STATUS_TEXT.get(lv["status"], lv["status"]), "since": lv.get("since"),
                 "confidence": ev["score"], "home": ev["home"],
                 "fell_asleep": cur.get("start") if lv["status"] == "asleep" else None,
                 "asleep_minutes": sm["asleep_for"], "interruptions_tonight": cur.get("interruptions", 0),
                 "signals": {r["label"]: r["ok"] for r in ev["signals"]}}
        last = sm["last"]
        lattrs = {"went_to_sleep": last and last["start"], "woke_up": last and last["end"],
                  "went_to_sleep_time": last and nice_time(last["start"]), "woke_up_time": last and nice_time(last["end"]),
                  "minutes": last and last["minutes"], "in_bed_minutes": last and last["in_bed_minutes"],
                  "interruptions": last and last["interruptions"], "awake_minutes": last and last["awake_minutes"],
                  "still_settling": bool(last and last.get("provisional")),
                  "average_7_nights_hours": round(sm["avg_week"] / 60, 2) if sm["avg_week"] else None,
                  "nights_counted": sm["nights_week"], "naps_today_minutes": sm["naps_today"],
                  "history": [{"date": parse(r["end"]).date().isoformat(), "hours": round(r["minutes"] / 60, 2),
                               "from": nice_time(r["start"]), "to": nice_time(r["end"]), "nap": r["nap"]}
                              for r in sm["recent"]]}
        pub(f"sleep_tracker/{sl}/asleep", "ON" if lv["status"] == "asleep" else "OFF")
        pub(f"sleep_tracker/{sl}/status", STATUS_TEXT.get(lv["status"], lv["status"]))
        pub(f"sleep_tracker/{sl}/confidence", str(ev["score"]))
        pub(f"sleep_tracker/{sl}/attributes", json.dumps(attrs, ensure_ascii=False))
        pub(f"sleep_tracker/{sl}/last_sleep", "%.2f" % (last["minutes"] / 60) if last else "0")
        pub(f"sleep_tracker/{sl}/last_sleep_attributes", json.dumps(lattrs, ensure_ascii=False))
    everyone = bool(home_people) and len(home_asleep) == len(home_people)
    pub("sleep_tracker/everyone_asleep", "ON" if everyone else "OFF")
    pub("sleep_tracker/everyone_attributes", json.dumps({"home": home_people, "asleep": home_asleep,
        "awake": [n for n in home_people if n not in home_asleep]}))


# ---------- the loop ----------
def tick():
    t = now()
    people = load_settings()["people"]
    if not people:
        return
    states = {s["entity_id"]: s for s in ha("/states")}
    evals = {}
    with lock:
        lives, hist = load_json(LIVE, {}), load_json(HISTORY, {})  # read under the lock: a button press may change them
        before = json.dumps(lives, sort_keys=True), json.dumps(hist, sort_keys=True)
        for p in people:
            lv = lives.setdefault(p["id"], blank_live())
            evals[p["id"]] = step(p, lv, states.get(p["id"]), states, t, hist)
            LAST[p["id"]] = dict(evals[p["id"]], at=iso(t))
        for gone in set(lives) - {p["id"] for p in people}:
            lives.pop(gone)
        cutoff = t - timedelta(days=KEEP_DAYS)
        if KEEP_DAYS:
            for pid in list(hist):
                hist[pid] = [r for r in hist[pid] if isinstance(r, dict) and (parse(r.get("end")) or cutoff) >= cutoff]
        if json.dumps(lives, sort_keys=True) != before[0]:
            save_json(LIVE, lives)
        if json.dumps(hist, sort_keys=True) != before[1]:
            save_json(HISTORY, hist)
    try:
        publish(people, lives, evals, hist, t)
    except Exception as e:
        print("MQTT publish error:", e, flush=True)


def manual(pid, what):
    """'Mark asleep' starts a night now; 'mark awake' ends it and ignores the signals for 30 minutes."""
    t = now()
    with lock:
        p = next((x for x in load_settings()["people"] if x["id"] == pid), None)
        if not p:
            return False
        lives, hist = load_json(LIVE, {}), load_json(HISTORY, {})
        lv = lives.setdefault(pid, blank_live())
        if what == "asleep" and lv["status"] != "asleep":
            fall_asleep(p, lv, t, hist, manual=True)
        elif what == "awake":
            if lv["status"] == "asleep":
                wake_up(p, lv, t, hold=30)
            else:
                lv.update(status="awake", since=iso(t), cand=None, hold_until=iso(t + timedelta(minutes=30)))
        save_json(LIVE, lives)
        save_json(HISTORY, hist)
    print(f"{p['name']} marked {what} by hand", flush=True)
    return True


def worker():
    last_try = 0
    while True:
        if mq is None and time.time() - last_try > 300:
            last_try = time.time()
            try:
                mqtt_start()
            except Exception as e:
                print("MQTT not available yet:", e, flush=True)
        try:
            tick()
        except Exception as e:
            print("Check failed:", e, flush=True)
        time.sleep(CHECK)


# ---------- suggestions ----------
def suggest(pid, area):
    """Signals that make sense for this person, from their phone(s) and the bedroom area."""
    states = {s["entity_id"]: s for s in ha("/states")}
    person = states.get(pid) or {}
    out = []
    phones = [d.split(".", 1)[1] for d in (person.get("attributes") or {}).get("device_trackers", [])]
    for base in phones:
        nm = (states.get("device_tracker." + base, {}).get("attributes") or {}).get("friendly_name") or base
        if f"sensor.{base}_battery_state" in states:
            out.append({"label": f"{nm} charging", "entities": [f"sensor.{base}_battery_state"], "mode": "is",
                        "values": ["Charging", "Full", "charging", "full"], "weight": 2})
        if f"binary_sensor.{base}_focus" in states:
            out.append({"label": f"{nm} Focus on", "entities": [f"binary_sensor.{base}_focus"], "mode": "is",
                        "values": ["on"], "weight": 3})
        if f"sensor.{base}_activity" in states:
            out.append({"label": f"{nm} not moving", "entities": [f"sensor.{base}_activity"], "mode": "is",
                        "values": ["Stationary", "still"], "weight": 1})
        if f"sensor.{base}_sleep_confidence" in states:
            out.append({"label": f"{nm} sleep confidence", "entities": [f"sensor.{base}_sleep_confidence"],
                        "mode": "above", "number": 70, "weight": 3})
        if f"binary_sensor.{base}_interactive" in states:
            out.append({"label": f"{nm} screen off", "entities": [f"binary_sensor.{base}_interactive"],
                        "mode": "is", "values": ["off"], "weight": 2})
    if area:
        try:
            ents = json.loads(ha("/template", "POST", {"template": "{{ area_entities(%s) | tojson }}" % json.dumps(area)}))
        except Exception:
            ents = []
        lights = [e for e in ents if e.startswith("light.")]
        tvs = [e for e in ents if e.startswith("media_player.")]
        motion = [e for e in ents if e.startswith("binary_sensor.") and
                  (states.get(e, {}).get("attributes") or {}).get("device_class") in ("motion", "occupancy")]
        if lights:
            out.append({"label": f"{area} lights off", "entities": lights, "need": "all", "mode": "is",
                        "values": ["off"], "weight": 2, "required": True})
        if tvs:
            out.append({"label": f"{area} TV / speakers not playing", "entities": tvs, "need": "all",
                        "mode": "is_not", "values": ["playing"], "weight": 1})
        if motion:
            out.append({"label": f"No motion in {area} for 10 min", "entities": motion, "need": "all",
                        "mode": "quiet", "minutes": 10, "weight": 1})
    return [x for x in (clean_signal(s) for s in out) if x]


# ---------- web UI ----------
@app.get("/")
def index():
    return send_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))


@app.get("/api/state")
def api_state():
    t = now()
    with lock:
        s, lives, hist = load_settings(), load_json(LIVE, {}), load_json(HISTORY, {})
    err, people, ents, areas = None, [], [], []
    try:
        for e in ha("/states"):
            eid = e["entity_id"]
            nm = (e.get("attributes") or {}).get("friendly_name", eid)
            if eid.startswith("person."):
                people.append({"id": eid, "name": nm})
            ents.append({"id": eid, "name": nm, "state": e.get("state")})
        areas = json.loads(ha("/template", "POST", {"template": "{{ areas() | map('area_name') | list | tojson }}"}))
    except Exception as ex:
        err = f"Can't reach Home Assistant: {ex}"
    status = []
    for p in s["people"]:
        lv = lives.get(p["id"], blank_live())
        sm = summary(p, lv, hist, t)
        status.append({"id": p["id"], "status": lv["status"], "status_text": STATUS_TEXT.get(lv["status"]),
                       "since": nice_time(lv.get("since")), "eval": LAST.get(p["id"]),
                       "interruptions": (lv.get("session") or {}).get("interruptions", 0),
                       "held": bool(lv.get("hold_until") and t < parse(lv["hold_until"])),
                       "summary": dict(sm, last=sm["last"] and dict(sm["last"], from_t=nice_time(sm["last"]["start"]),
                                                                  to_t=nice_time(sm["last"]["end"])), recent=[dict(r, from_t=nice_time(r["start"]), to_t=nice_time(r["end"]),
                                                        day=day_label(r["end"])) for r in sm["recent"]])})
    mqtt = "connected" if mq and mq_state["ready"] else ("connecting..." if mq else ("library missing" if mq is False else "off"))
    return jsonify({"error": err, "people": people, "entities": ents, "areas": areas, "settings": s,
                    "status": status, "defaults": PERSON_DEFAULTS, "info": {"mqtt": mqtt, "check": CHECK,
                    "keep_days": KEEP_DAYS, "version": VERSION}})


@app.post("/api/settings")
def api_settings():
    data = request.get_json(force=True) or {}
    with lock:
        old = {p["id"]: p for p in load_settings()["people"]}
        out, seen = [], set()
        for item in data.get("people", []):
            p = clean_person(item, old.get(str(item.get("id"))))
            if p and p["id"] not in seen:
                seen.add(p["id"])
                out.append(p)
        save_json(SETTINGS, {"people": out})
    threading.Thread(target=lambda: tick_safe(), daemon=True).start()
    return jsonify({"ok": True, "people": out})


def tick_safe():
    try:
        tick()
    except Exception as e:
        print("Check failed:", e, flush=True)


@app.post("/api/suggest")
def api_suggest():
    d = request.get_json(force=True) or {}
    try:
        return jsonify({"ok": True, "signals": suggest(str(d.get("id") or ""), str(d.get("area") or "").strip())})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.post("/api/mark")
def api_mark():
    d = request.get_json(force=True) or {}
    what = d.get("what")
    if what not in ("asleep", "awake") or not manual(str(d.get("id") or ""), what):
        return jsonify({"ok": False, "error": "Unknown person"})
    tick_safe()
    return jsonify({"ok": True})


@app.post("/api/forget")
def api_forget():
    """Delete one saved sleep (a wrong detection)."""
    d = request.get_json(force=True) or {}
    with lock:
        hist = load_json(HISTORY, {})
        rows = hist.get(str(d.get("id")), [])
        hist[str(d.get("id"))] = [r for r in rows if r["start"] != d.get("start")]
        save_json(HISTORY, hist)
    tick_safe()
    return jsonify({"ok": True})


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("ST_PORT", 8099)), threaded=True)

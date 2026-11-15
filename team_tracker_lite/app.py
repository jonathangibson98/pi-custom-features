#!/usr/bin/env python3
"""Team Tracker Lite - ONE sensor, any team, picked from a web menu.

Pulls game data from ESPN's public API for the single team you mark as
"tracking" and publishes it to Home Assistant over MQTT as one sensor with
the same state values (PRE / IN / POST / NOT_FOUND) and attribute names the
Team Tracker integration uses, so existing cards keep working.
"""
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt
from zoneinfo import ZoneInfo

VERSION = "0.3.2"
# Settings live in the add-on's config folder (/addon_configs/<id>_team_tracker_lite/data on the host).
DATA = os.environ.get("TTL_DATA", "/config/data")
SETTINGS_FILE = os.path.join(DATA, "settings.json")
OPTIONS_FILE = os.environ.get("TTL_OPTIONS", "/data/options.json")  # written by Supervisor
HERE = os.path.dirname(os.path.abspath(__file__))
ALLOW_ANY = os.environ.get("TTL_ALLOW_ANY") == "1"  # local testing only

ESPN = "https://site.api.espn.com/apis/site/v2/sports"
UA = {"User-Agent": "TeamTrackerLite/0.1 (home-assistant add-on)"}
POST_HOLD_HOURS = 18  # keep showing the final score this long after a game

# id: (menu label, sport path, league path, ESPN "groups" filter for college)
LEAGUES = {
    "NFL": ("NFL", "football", "nfl", None),
    "NBA": ("NBA", "basketball", "nba", None),
    "MLB": ("MLB", "baseball", "mlb", None),
    "NHL": ("NHL", "hockey", "nhl", None),
    "WNBA": ("WNBA", "basketball", "wnba", None),
    "NCAAF": ("College Football (FBS)", "football", "college-football", "80"),
    "NCAAM": ("College Basketball (Men)", "basketball", "mens-college-basketball", "50"),
    "NCAAW": ("College Basketball (Women)", "basketball", "womens-college-basketball", "50"),
    "MLS": ("MLS", "soccer", "usa.1", None),
    "NWSL": ("NWSL", "soccer", "usa.nwsl", None),
    "EPL": ("English Premier League", "soccer", "eng.1", None),
    "LIGA": ("Spanish LaLiga", "soccer", "esp.1", None),
    "BUND": ("German Bundesliga", "soccer", "ger.1", None),
    "SERA": ("Italian Serie A", "soccer", "ita.1", None),
    "LIG1": ("French Ligue 1", "soccer", "fra.1", None),
    "CL": ("Champions League", "soccer", "uefa.champions", None),
}

# MQTT topics
T_AVAIL = "team_tracker_lite/status"
T_STATE = "team_tracker_lite/state"
T_ATTR = "team_tracker_lite/attributes"
T_SEL_SET = "team_tracker_lite/select/set"
T_SEL_STATE = "team_tracker_lite/select/state"
D_SENSOR = "homeassistant/sensor/team_tracker_lite/config"
D_SELECT = "homeassistant/select/team_tracker_lite/config"

LOCK = threading.RLock()
WAKE = threading.Event()
OPTS = {}
S = {}
LAST = {"state": "NOT_FOUND", "attributes": {"api_message": "Starting up"}, "at": None}
TEAM_CACHE = {}
CLIENT = None
MQTT_OK = False
PREV = None  # (active team key, state) - used to log only real state changes
LOCAL_TZ = timezone.utc
TZ_NAME = "UTC"
CAL = {"built_at": None, "events": 0, "teams": 0, "error": None, "poke": None, "reason": None}
CAL_REQUEST = threading.Event()
CAL_REASON = ""
ADDON_HOST = None
GAME_HOURS = {"football": 3.5, "basketball": 2.5, "baseball": 3.0, "hockey": 2.5, "soccer": 2.0}
LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
LOG_LEVEL = LEVELS["info"]


def log(level, *a):
    if LEVELS.get(level, 20) >= LOG_LEVEL:
        print(time.strftime("%H:%M:%S"), f"[{level.upper()}]", *a, flush=True)


# ---------------------------------------------------------------- settings
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_settings():
    s = load_json(SETTINGS_FILE, {})
    s.setdefault("sensor_name", "Team Tracker")
    s.setdefault("favorites", [])
    s.setdefault("active", None)
    s["idle_minutes"] = clamp(s.get("idle_minutes"), 1, 60, 10)
    s["live_seconds"] = clamp(s.get("live_seconds"), 5, 120, 15)
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(s.get("calendar_time") or "")):
        s["calendar_time"] = "04:00"
    s.setdefault("calendar_entity", "calendar.team_games")
    s.setdefault("live_game", None)
    return s


def clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def init_storage():
    """Make sure the settings folder exists and is writable; fall back to /data if not."""
    global DATA, SETTINGS_FILE
    try:
        os.makedirs(DATA, exist_ok=True)
        probe = os.path.join(DATA, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        log("warning", f"Cannot write to {DATA} ({e}); falling back to /data. "
                       "Settings will not appear in addon_configs.")
        DATA = "/data"
        SETTINGS_FILE = os.path.join(DATA, "settings.json")
        os.makedirs(DATA, exist_ok=True)


def save_settings():
    os.makedirs(DATA, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(S, f, indent=2)
    os.replace(tmp, SETTINGS_FILE)
    log("debug", "Settings saved to", SETTINGS_FILE)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "team_tracker"


def live_label():
    lg = S.get("live_game")
    return f"Live game: {lg['label']}" if lg else None


def active_fav():
    with LOCK:
        if S["active"] == "LIVE" and S.get("live_game"):
            lg = S["live_game"]
            return {**lg, "key": "LIVE", "live": True, "label": live_label()}
        for f in S["favorites"]:
            if f["key"] == S["active"]:
                return dict(f)
    return None


# -------------------------------------------------------------------- ESPN
def http_json(url, timeout=15):
    log("debug", "GET", url)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_teams(lid):
    cached = TEAM_CACHE.get(lid)
    if cached and time.time() - cached[0] < 6 * 3600:
        return cached[1]
    _, sport, lg, groups = LEAGUES[lid]
    q = {"limit": "1000"}
    if groups:
        q["groups"] = groups
    d = http_json(f"{ESPN}/{sport}/{lg}/teams?{urllib.parse.urlencode(q)}")
    out = []
    for item in d["sports"][0]["leagues"][0]["teams"]:
        t = item["team"]
        out.append({
            "id": str(t["id"]),
            "abbr": t.get("abbreviation", ""),
            "name": t.get("displayName") or t.get("name", ""),
            "logo": ((t.get("logos") or [{}])[0]).get("href", ""),
        })
    out.sort(key=lambda x: x["name"])
    TEAM_CACHE.clear()  # only ever hold one league in RAM
    TEAM_CACHE[lid] = (time.time(), out)
    return out


def fetch_schedule(lid, tid):
    _, sport, lg, _g = LEAGUES[lid]
    base = f"{ESPN}/{sport}/{lg}/teams/{tid}/schedule"
    events = {}
    for suffix in ("", "?seasontype=3"):  # regular/current + postseason
        try:
            d = http_json(base + suffix)
        except Exception:
            if suffix == "":
                raise
            continue
        for e in d.get("events") or []:
            events[str(e.get("id"))] = e
    return list(events.values())


def fetch_scoreboard_event(lid, eid):
    _, sport, lg, groups = LEAGUES[lid]
    q = {"limit": "400"}
    if groups:
        q["groups"] = groups
    d = http_json(f"{ESPN}/{sport}/{lg}/scoreboard?{urllib.parse.urlencode(q)}")
    for e in d.get("events") or []:
        if str(e.get("id")) == str(eid):
            return e
    return None


# ----------------------------------------------------------- data shaping
def parse_dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def comp_of(e):
    return (e.get("competitions") or [{}])[0]


def status_of(e):
    return comp_of(e).get("status") or e.get("status") or {}


def state_of(e):
    return (status_of(e).get("type") or {}).get("state")


def num(v):
    if isinstance(v, dict):
        v = v.get("displayValue", v.get("value"))
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def cid(c):
    return str(c.get("id") or (c.get("team") or {}).get("id"))


def record_of(c):
    for key in ("records", "record"):
        lst = c.get(key) or []
        for r in lst:
            if r.get("type") == "total":
                return r.get("summary") or r.get("displayValue")
        if lst:
            return lst[0].get("summary") or lst[0].get("displayValue")
    return None


def tv_of(comp):
    names = []
    for b in comp.get("broadcasts") or []:
        if isinstance(b.get("names"), list):
            names += b["names"]
        elif isinstance(b.get("media"), dict):
            names.append(b["media"].get("shortName") or "")
    names = [n for n in names if n]
    return ", ".join(names) or None


def humanize(delta):
    secs = int(delta.total_seconds())
    if secs < 0:
        return None
    if secs < 3600:
        return f"in {max(1, secs // 60)} minutes"
    if secs < 86400:
        h = secs // 3600
        return f"in {h} hour{'s' if h != 1 else ''}"
    d = round(secs / 86400)
    return "tomorrow" if d <= 1 else f"in {d} days"


def side(p, c, a):
    c = c or {}
    t = c.get("team") or {}
    rk = (c.get("curatedRank") or {}).get("current")
    a[p + "_abbr"] = t.get("abbreviation")
    a[p + "_id"] = cid(c) if c else None
    a[p + "_name"] = t.get("name") or t.get("nickname") or t.get("shortDisplayName")
    a[p + "_long_name"] = t.get("displayName")
    a[p + "_record"] = record_of(c)
    a[p + "_rank"] = rk if isinstance(rk, int) and 0 < rk <= 25 else None
    a[p + "_homeaway"] = c.get("homeAway")
    a[p + "_logo"] = t.get("logo") or ((t.get("logos") or [{}])[0]).get("href")
    a[p + "_colors"] = ["#" + x for x in (t.get("color"), t.get("alternateColor")) if x]
    a[p + "_score"] = num(c.get("score"))
    a[p + "_winner"] = c.get("winner")


def build(event, tid, lid):
    comp = comp_of(event)
    cs = comp.get("competitors") or []
    me = next((c for c in cs if cid(c) == str(tid)), None)
    if not me:
        return None
    op = next((c for c in cs if c is not me), None)
    st = status_of(event)
    stype = st.get("type") or {}
    state = {"pre": "PRE", "in": "IN", "post": "POST"}.get(stype.get("state"), "NOT_FOUND")
    label, sport, lg, _g = LEAGUES[lid]
    now = datetime.now(timezone.utc)
    when = parse_dt(event.get("date") or comp.get("date"))
    venue = comp.get("venue") or {}
    addr = venue.get("address") or {}
    sit = comp.get("situation") or {}
    odds = (comp.get("odds") or [{}])[0]

    a = {
        "sport": sport,
        "sport_path": sport,
        "league": label,
        "league_id": lid,
        "league_path": lg,
        "event_name": event.get("name"),
        "date": when.isoformat() if when else None,
        "kickoff_in": humanize(when - now) if when and state == "PRE" else None,
        "venue": venue.get("fullName"),
        "location": ", ".join(x for x in (addr.get("city"), addr.get("state")) if x) or None,
        "tv_network": tv_of(comp),
        "odds": odds.get("details") if state == "PRE" else None,
        "overunder": odds.get("overUnder") if state == "PRE" else None,
        "quarter": st.get("period") if state == "IN" else None,
        "clock": st.get("displayClock") if state == "IN" else None,
        "status_detail": stype.get("shortDetail") or stype.get("detail"),
        "last_play": (sit.get("lastPlay") or {}).get("text") if state == "IN" else None,
        "down_distance_text": sit.get("downDistanceText") if state == "IN" else None,
        "possession": sit.get("possession") if state == "IN" else None,
        "outs": sit.get("outs") if state == "IN" else None,
        "balls": sit.get("balls") if state == "IN" else None,
        "strikes": sit.get("strikes") if state == "IN" else None,
        "on_first": bool(sit.get("onFirst")) if state == "IN" and "onFirst" in sit else None,
        "on_second": bool(sit.get("onSecond")) if state == "IN" and "onSecond" in sit else None,
        "on_third": bool(sit.get("onThird")) if state == "IN" and "onThird" in sit else None,
        "event_url": next((l.get("href") for l in event.get("links") or []
                           if "summary" in (l.get("rel") or [])), None),
        "last_update": now.isoformat(),
        "api_message": "ok",
    }
    side("team", me, a)
    side("opponent", op, a)
    return state, a


def pick_event(events, now):
    good = []
    for e in events:
        stp = status_of(e).get("type") or {}
        if stp.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            continue
        d = parse_dt(e.get("date") or comp_of(e).get("date"))
        if d:
            good.append((d, stp.get("state"), e))
    live = [g for g in good if g[1] == "in"]
    if live:
        return live[0][2]
    pre = sorted((g for g in good if g[1] == "pre"), key=lambda g: g[0])
    post = sorted((g for g in good if g[1] == "post"), key=lambda g: g[0], reverse=True)
    soon = bool(pre) and (pre[0][0] - now) < timedelta(minutes=90)
    if post and not soon and (now - post[0][0]) < timedelta(hours=POST_HOLD_HOURS):
        return post[0][2]
    if pre:
        return pre[0][2]
    if post:
        return post[0][2]
    return None


# ------------------------------------------------------------ live games
def fetch_live_games(lid):
    """Games in this league that are in progress right now (from the scoreboard)."""
    _, sport, lg, groups = LEAGUES[lid]
    q = {"limit": "400"}
    if groups:
        q["groups"] = groups
    d = http_json(f"{ESPN}/{sport}/{lg}/scoreboard?{urllib.parse.urlencode(q)}")
    out = []
    for e in d.get("events") or []:
        if state_of(e) != "in":
            continue
        st = status_of(e)
        teams = []
        for c in comp_of(e).get("competitors") or []:
            t = c.get("team") or {}
            teams.append({"id": cid(c), "abbr": t.get("abbreviation") or "?",
                          "name": t.get("displayName") or t.get("name") or "?",
                          "score": num(c.get("score")), "home": c.get("homeAway") == "home",
                          "logo": t.get("logo") or ((t.get("logos") or [{}])[0]).get("href", "")})
        teams.sort(key=lambda x: x["home"])  # away first, home second
        out.append({"event_id": str(e.get("id")), "name": e.get("shortName") or e.get("name"),
                    "detail": (st.get("type") or {}).get("shortDetail"), "teams": teams})
    return out


def poll_live_game(fav, IDLE, LIVE):
    lid, eid, tid = fav["league"], fav["event_id"], fav["team_id"]
    ev = fetch_scoreboard_event(lid, eid)
    if ev:
        built = build(ev, tid, lid)
        if built:
            built[1]["tracking_mode"] = "live_game"
            publish_sensor(*built)
            return LIVE if built[0] == "IN" else (IDLE if built[0] == "POST" else min(IDLE, 60))
    with LOCK:
        keep = LAST["state"] == "POST" and LAST["attributes"].get("team_id") == tid
    if keep:  # game finished and dropped off the scoreboard: keep showing the final score
        return IDLE
    publish_sensor("NOT_FOUND", {"team_name": fav.get("name"), "team_abbr": fav.get("abbr"),
                                 "team_logo": fav.get("logo"), "league_id": lid, "tracking_mode": "live_game",
                                 "api_message": "That game is no longer on the scoreboard. Pick another live game in the panel.",
                                 "last_update": datetime.now(timezone.utc).isoformat()})
    return IDLE


# ----------------------------------------------------------------- calendar
def cal_file():
    return os.path.join(DATA, "team_games.ics")


def cal_meta_file():
    return os.path.join(DATA, "calendar_status.json")


def supervisor_call(method, path, payload=None, timeout=15):
    tok = os.environ.get("SUPERVISOR_TOKEN")
    if not tok:
        raise RuntimeError("not running under the Supervisor")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://supervisor" + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body.decode()) if body else None


def init_timezone():
    global LOCAL_TZ, TZ_NAME
    name = None
    try:
        name = (supervisor_call("GET", "/core/api/config") or {}).get("time_zone")
    except Exception as e:
        log("debug", "Could not read time zone from Home Assistant:", e)
    name = name or os.environ.get("TZ")
    try:
        LOCAL_TZ, TZ_NAME = ZoneInfo(name), name
    except Exception:
        LOCAL_TZ, TZ_NAME = timezone.utc, "UTC"
        log("warning", "Could not determine your time zone, using UTC for the daily calendar update time")
    log("info", "Time zone:", TZ_NAME)


def addon_host():
    global ADDON_HOST
    if not ADDON_HOST:
        try:
            ADDON_HOST = supervisor_call("GET", "/addons/self/info")["data"]["hostname"]
        except Exception:
            ADDON_HOST = socket.gethostname()
    return ADDON_HOST


def seconds_until(hhmm):
    now = datetime.now(LOCAL_TZ)
    h, m = (int(x) for x in hhmm.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return max(1.0, (t - now).total_seconds())


def ics_esc(t):
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def fold(line):
    out, cur, limit = [], b"", 75
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > limit:
            out.append(cur.decode("utf-8"))
            cur, limit = b"", 74
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def ics_wrap(vevents):
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Team Tracker Lite//EN", "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH", "X-WR-CALNAME:Team Tracker Games"]
    return "\r\n".join(fold(l) for l in head + vevents + ["END:VCALENDAR"]) + "\r\n"


def make_vevent(e, lid, stamp):
    """Turn one ESPN schedule event into the lines of an iCalendar VEVENT (or None)."""
    comp = comp_of(e)
    stp = status_of(e).get("type") or {}
    if stp.get("name") == "STATUS_CANCELED" or not e.get("id"):
        return None
    when = parse_dt(e.get("date") or comp.get("date"))
    if not when:
        return None
    label, sport, _lg, _g = LEAGUES[lid]
    cs = comp.get("competitors") or []
    home = next((c for c in cs if c.get("homeAway") == "home"), None)
    away = next((c for c in cs if c.get("homeAway") == "away"), None)
    ab = lambda c: ((c or {}).get("team") or {}).get("abbreviation") or "TBD"
    full = lambda c: ((c or {}).get("team") or {}).get("displayName") or ab(c)
    title = f"{ab(away)} @ {ab(home)}" if home and away else (e.get("shortName") or e.get("name") or "Game")
    desc, extra = [], ""
    if home and away:
        desc.append(f"{full(away)} at {full(home)}")
    desc.append(label)
    if stp.get("name") == "STATUS_POSTPONED":
        extra = " (Postponed)"
        desc.append("Postponed")
    elif stp.get("state") == "post" and home and away:
        a_s, h_s = num(away.get("score")), num(home.get("score"))
        if a_s is not None and h_s is not None:
            extra = f" (Final {a_s}-{h_s})"
            desc.append(f"Final: {ab(away)} {a_s}, {ab(home)} {h_s}")
    tv = tv_of(comp)
    if tv:
        desc.append("TV: " + tv)
    venue = comp.get("venue") or {}
    addr = venue.get("address") or {}
    where = ", ".join(x for x in (venue.get("fullName"), addr.get("city"), addr.get("state")) if x)

    lines = ["BEGIN:VEVENT", f"UID:{lid}-{e['id']}@team-tracker-lite", f"DTSTAMP:{stamp}"]
    if comp.get("timeValid") is False or e.get("timeValid") is False:  # time TBD -> all-day
        day = when.astimezone(ZoneInfo("America/New_York")).date()
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    else:
        end = when + timedelta(hours=GAME_HOURS.get(sport, 3.0))
        lines += [f"DTSTART:{when.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
                  f"DTEND:{end.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"]
    lines.append("SUMMARY:" + ics_esc(f"{lid}: {title}{extra}"))
    if where:
        lines.append("LOCATION:" + ics_esc(where))
    lines.append("DESCRIPTION:" + ics_esc("\n".join(desc)))
    lines.append("END:VEVENT")
    return lines


def poke_calendar_entity():
    with LOCK:
        entity = (S.get("calendar_entity") or "").strip()
    if not entity:
        return "Skipped (no calendar entity set)"
    try:
        supervisor_call("POST", "/core/api/services/homeassistant/update_entity", {"entity_id": entity})
        return f"Asked Home Assistant to refresh {entity}"
    except urllib.error.HTTPError as e:
        return f"Home Assistant refused the refresh for {entity} (HTTP {e.code}). Is the entity name right?"
    except Exception as e:
        return f"Could not reach Home Assistant to refresh {entity}: {e}"


def save_cal_meta():
    try:
        with open(cal_meta_file(), "w", encoding="utf-8") as f:
            json.dump(CAL, f)
    except OSError as e:
        log("warning", "Could not save calendar status:", e)


def build_calendar(reason):
    """Fetch every saved team's season schedule and rebuild the .ics. All-or-nothing: if any team
    fails, the previous good calendar is kept and a retry is scheduled."""
    with LOCK:
        favs = [dict(f) for f in S["favorites"]]
    log("info", f"Updating calendar ({reason}) for {len(favs)} team(s)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seen, vevents, errors = set(), [], []
    for f in favs:
        try:
            events = fetch_schedule(f["league"], f["team_id"])
        except Exception as e:
            errors.append(f"{f['name']}: {e}")
            continue
        for ev in events:
            uid = f"{f['league']}-{ev.get('id')}"
            if uid in seen:  # two tracked teams playing each other -> one entry
                continue
            v = make_vevent(ev, f["league"], stamp)
            if v:
                seen.add(uid)
                vevents.append(v)
        log("debug", f"{f['name']}: {len(events)} schedule events")
        del events
    if errors:
        CAL.update(error="; ".join(errors)[:300], reason=reason)
        save_cal_meta()
        log("warning", "Calendar not updated, keeping the previous one:", CAL["error"])
        return False
    text = ics_wrap([l for v in vevents for l in v])
    os.makedirs(DATA, exist_ok=True)
    tmp = cal_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, cal_file())
    CAL.update(built_at=datetime.now(timezone.utc).isoformat(), events=len(vevents), teams=len(favs),
               error=None, reason=reason, poke=poke_calendar_entity())
    save_cal_meta()
    log("info", f"Calendar updated: {len(vevents)} games from {len(favs)} team(s). {CAL['poke']}")
    return True


def request_calendar(reason):
    global CAL_REASON
    CAL_REASON = reason
    CAL_REQUEST.set()


def calendar_loop():
    time.sleep(10)
    if not os.path.exists(cal_file()):
        request_calendar("startup")
    retry = None
    while True:
        with LOCK:
            at = S["calendar_time"]
        triggered = CAL_REQUEST.wait(retry or seconds_until(at))
        reason = "scheduled"
        if triggered:
            reason = CAL_REASON
            CAL_REQUEST.clear()
            if reason == "time":  # only the daily time changed: just recompute the wait
                retry = None
                continue
            if reason == "teams":  # wait until the user stops adding/removing teams
                while CAL_REQUEST.wait(20):
                    CAL_REQUEST.clear()
        try:
            ok = build_calendar(reason)
        except Exception as e:
            log("error", "Calendar update failed:", e)
            CAL.update(error=str(e)[:300])
            ok = False
        retry = None if ok else 1800


class ICSHandler(BaseHTTPRequestHandler):
    """Serves the calendar feed on port 8100 (read-only, no secrets in it)."""
    server_version = "TeamTrackerLiteICS/1"

    def log_message(self, fmt, *a):
        log("debug", "ics", fmt % a)

    def do_GET(self):
        path = "/" + urllib.parse.urlparse(self.path).path.strip("/")
        if path not in ("/", "/calendar.ics", "/team_games.ics"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            with open(cal_file(), "rb") as f:
                body = f.read()
        except OSError:
            body = ics_wrap([]).encode("utf-8")  # valid empty calendar until the first build finishes
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def calendar_info():
    return {**CAL, "url": f"http://{addon_host()}:8100/calendar.ics", "tz": TZ_NAME}


# -------------------------------------------------------------------- MQTT
def mqtt_settings():
    host = (OPTS.get("mqtt_host") or "").strip()
    if host:
        return (host, int(OPTS.get("mqtt_port") or 1883),
                OPTS.get("mqtt_username") or None, OPTS.get("mqtt_password") or None)
    tok = os.environ.get("SUPERVISOR_TOKEN")
    if tok:
        try:
            req = urllib.request.Request("http://supervisor/services/mqtt",
                                         headers={"Authorization": "Bearer " + tok})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read().decode())["data"]
            return d["host"], int(d["port"]), d.get("username"), d.get("password")
        except Exception as e:
            log("warning", "Supervisor MQTT lookup failed:", e)
    return None


def pub(topic, payload, retain=True):
    if CLIENT and MQTT_OK:
        CLIENT.publish(topic, payload, qos=1, retain=retain)


def publish_discovery():
    with LOCK:
        name = S["sensor_name"]
        labels = [f["label"] for f in S["favorites"]] + ([live_label()] if S.get("live_game") else [])
    device = {"identifiers": ["team_tracker_lite"], "name": "Team Tracker Lite",
              "manufacturer": "Home-built", "model": "Team Tracker Lite"}
    pub(D_SENSOR, json.dumps({
        "name": name,
        "unique_id": "team_tracker_lite_main",
        "default_entity_id": "sensor." + slug(name),
        "state_topic": T_STATE,
        "json_attributes_topic": T_ATTR,
        "availability_topic": T_AVAIL,
        "icon": "mdi:scoreboard",
        "device": device,
    }))
    if OPTS.get("publish_team_selector") and labels:
        pub(D_SELECT, json.dumps({
            "name": name + " Team",
            "unique_id": "team_tracker_lite_select",
            "default_entity_id": "select." + slug(name) + "_team",
            "command_topic": T_SEL_SET,
            "state_topic": T_SEL_STATE,
            "availability_topic": T_AVAIL,
            "options": labels,
            "icon": "mdi:swap-horizontal",
            "device": device,
        }))
        publish_select_state()
        # Home Assistant rebuilds the select when its options change and can drop a state
        # that arrives during the rebuild, so it falls back to the old choice. Say it again.
        for delay in (2, 6):
            t = threading.Timer(delay, publish_select_state)
            t.daemon = True
            t.start()
    else:
        pub(D_SELECT, "")  # removes the select if it was ever created


def publish_select_state():
    f = active_fav()
    if f:
        pub(T_SEL_STATE, f["label"])


def publish_sensor(state, attrs):
    global PREV
    with LOCK:
        LAST.update(state=state, attributes=attrs, at=datetime.now(timezone.utc).isoformat())
        tag = (S.get("active"), state)
    if tag != PREV:
        PREV = tag
        log("info", f"Sensor is now {state}: {attrs.get('team_abbr') or attrs.get('team_name') or '-'} "
                    f"vs {attrs.get('opponent_abbr') or '-'} ({attrs.get('api_message')})")
    else:
        log("debug", f"Sensor {state}: {attrs.get('team_score')}-{attrs.get('opponent_score')}")
    pub(T_STATE, state)
    pub(T_ATTR, json.dumps(attrs, default=str))
    if OPTS.get("publish_team_selector"):
        publish_select_state()


def on_connect(client, userdata, flags, reason_code, properties=None):
    global MQTT_OK
    if reason_code.is_failure:
        log("error", "MQTT connect failed:", reason_code)
        return
    MQTT_OK = True
    log("info", "MQTT connected")
    pub(T_AVAIL, "online")
    publish_discovery()
    client.subscribe(T_SEL_SET)
    with LOCK:
        st, at = LAST["state"], LAST["attributes"]
    pub(T_STATE, st)
    pub(T_ATTR, json.dumps(at, default=str))


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    global MQTT_OK
    MQTT_OK = False
    log("warning", "MQTT disconnected:", reason_code)


def on_message(client, userdata, msg):
    if msg.topic != T_SEL_SET:
        return
    label = msg.payload.decode("utf-8", "ignore")
    with LOCK:
        if S.get("live_game") and label == live_label():
            S["active"] = "LIVE"
            save_settings()
        else:
            for f in S["favorites"]:
                if f["label"] == label:
                    S["active"] = f["key"]
                    save_settings()
                    break
            else:
                return
    publish_select_state()
    WAKE.set()


def mqtt_start():
    global CLIENT
    cfg = mqtt_settings()
    if not cfg:
        log("error", "No MQTT broker configured - set mqtt_host in the add-on Configuration tab")
        return
    host, port, user, pw = cfg
    log("info", f"MQTT broker: {host}:{port}")
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="team_tracker_lite")
    if user:
        c.username_pw_set(user, pw)
    c.will_set(T_AVAIL, "offline", qos=1, retain=True)
    c.on_connect, c.on_disconnect, c.on_message = on_connect, on_disconnect, on_message
    c.on_log = lambda cl, ud, lvl, buf: log("debug", "paho:", buf)
    c.reconnect_delay_set(min_delay=2, max_delay=60)
    CLIENT = c
    c.connect_async(host, port, keepalive=60)
    c.loop_start()


# ------------------------------------------------------------------ polling
def poll_once():
    with LOCK:
        IDLE, LIVE = S["idle_minutes"] * 60, S["live_seconds"]
    fav = active_fav()
    if not fav:
        publish_sensor("NOT_FOUND", {"api_message": "No team selected. Open the Team Tracker panel and pick one."})
        return IDLE
    if fav.get("live"):
        return poll_live_game(fav, IDLE, LIVE)
    lid, tid = fav["league"], fav["team_id"]
    now = datetime.now(timezone.utc)
    events = fetch_schedule(lid, tid)
    ev = pick_event(events, now)
    if not ev:
        publish_sensor("NOT_FOUND", {"team_name": fav["name"], "team_abbr": fav["abbr"],
                                     "team_logo": fav["logo"], "league_id": lid,
                                     "api_message": "No games found for this team right now",
                                     "last_update": now.isoformat()})
        return IDLE

    st = state_of(ev)
    when = parse_dt(ev.get("date") or comp_of(ev).get("date"))
    wait = IDLE
    hot = st == "in" or (st == "pre" and when and timedelta(hours=-3) < (when - now) <= timedelta(minutes=10))
    if hot:
        wait = LIVE
        try:
            fresh = fetch_scoreboard_event(lid, ev.get("id"))
            if fresh:
                ev = fresh
                if state_of(fresh) == "post":
                    wait = 120
        except Exception as e:
            log("warning", "Live scoreboard fetch failed, using schedule data:", e)
    elif st == "pre" and when:
        secs = (when - now).total_seconds() - 600
        wait = int(min(IDLE, max(LIVE, secs)))

    built = build(ev, tid, lid)
    if not built:
        publish_sensor("NOT_FOUND", {"api_message": "Team not found in the game data", "last_update": now.isoformat()})
        return IDLE
    built[1]["tracking_mode"] = "team"
    publish_sensor(*built)
    return wait


def poll_loop():
    while True:
        WAKE.clear()
        try:
            wait = poll_once()
        except Exception as e:
            log("error", "Poll failed:", e)
            publish_sensor("NOT_FOUND", {"api_message": f"ESPN request failed: {e}"})
            wait = 60
        log("debug", f"Next check in {wait}s")
        WAKE.wait(wait)


# --------------------------------------------------------------- web server
class Handler(BaseHTTPRequestHandler):
    server_version = "TeamTrackerLite/0.1"

    def log_message(self, fmt, *a):
        log("debug", "http", fmt % a)

    def send_body(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def allowed(self):
        if ALLOW_ANY or self.client_address[0] in ("172.30.32.2", "127.0.0.1"):
            return True
        self.send_body(403, {"error": "forbidden"})
        return False

    def state_payload(self):
        with LOCK:
            return {"settings": json.loads(json.dumps(S)), "sensor": dict(LAST),
                    "mqtt": MQTT_OK, "selector": bool(OPTS.get("publish_team_selector")),
                    "calendar": calendar_info()}

    def do_GET(self):
        if not self.allowed():
            return
        u = urllib.parse.urlparse(self.path)
        p = "/" + u.path.strip("/")
        qs = urllib.parse.parse_qs(u.query)
        if p in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send_body(200, f.read(), "text/html; charset=utf-8")
        if p == "/api/leagues":
            return self.send_body(200, [{"id": k, "label": v[0]} for k, v in LEAGUES.items()])
        if p == "/api/teams":
            lid = (qs.get("league") or [""])[0]
            if lid not in LEAGUES:
                return self.send_body(400, {"error": "unknown league"})
            try:
                return self.send_body(200, get_teams(lid))
            except Exception as e:
                return self.send_body(502, {"error": f"ESPN request failed: {e}"})
        if p == "/api/live":
            lid = (qs.get("league") or [""])[0]
            if lid not in LEAGUES:
                return self.send_body(400, {"error": "unknown league"})
            try:
                return self.send_body(200, fetch_live_games(lid))
            except Exception as e:
                return self.send_body(502, {"error": f"ESPN request failed: {e}"})
        if p == "/api/state":
            return self.send_body(200, self.state_payload())
        self.send_body(404, {"error": "not found"})

    def do_POST(self):
        if not self.allowed():
            return
        p = "/" + urllib.parse.urlparse(self.path).path.strip("/")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self.send_body(400, {"error": "bad json"})

        with LOCK:
            before = [f["key"] for f in S["favorites"]]
        if p == "/api/favorites":
            lid, tid = body.get("league"), str(body.get("team_id") or "")
            if lid not in LEAGUES or not tid:
                return self.send_body(400, {"error": "league and team_id required"})
            key = f"{lid}:{tid}"
            name = str(body.get("name") or tid)[:80]
            with LOCK:
                if not any(f["key"] == key for f in S["favorites"]):
                    S["favorites"].append({
                        "key": key, "league": lid, "team_id": tid,
                        "abbr": str(body.get("abbr") or "")[:10], "name": name,
                        "logo": str(body.get("logo") or "")[:300], "label": f"{lid} {name}",
                    })
                    log("info", f"Added team: {name} ({lid})")
                if not S["active"]:
                    S["active"] = key
                save_settings()
        elif p == "/api/active":
            with LOCK:
                if not (any(f["key"] == body.get("key") for f in S["favorites"])
                        or (body.get("key") == "LIVE" and S.get("live_game"))):
                    return self.send_body(400, {"error": "unknown team"})
                S["active"] = body["key"]
                save_settings()
            log("info", "Now tracking", body["key"])
        elif p == "/api/remove":
            with LOCK:
                S["favorites"] = [f for f in S["favorites"] if f["key"] != body.get("key")]
                if S["active"] == body.get("key"):
                    S["active"] = S["favorites"][0]["key"] if S["favorites"] else None
                save_settings()
            log("info", "Removed team", body.get("key"))
        elif p == "/api/name":
            name = str(body.get("name") or "").strip()[:60]
            if not name:
                return self.send_body(400, {"error": "name required"})
            with LOCK:
                S["sensor_name"] = name
                save_settings()
            log("info", "Sensor renamed to", name)
        elif p == "/api/rates":
            with LOCK:
                S["idle_minutes"] = clamp(body.get("idle_minutes"), 1, 60, S["idle_minutes"])
                S["live_seconds"] = clamp(body.get("live_seconds"), 5, 120, S["live_seconds"])
                save_settings()
            log("info", f"Refresh speed: every {S['idle_minutes']} min idle, {S['live_seconds']}s during games")
        elif p == "/api/livegame":
            lid, eid, tid = body.get("league"), str(body.get("event_id") or ""), str(body.get("team_id") or "")
            if lid not in LEAGUES or not eid or not tid:
                return self.send_body(400, {"error": "league, event_id and team_id required"})
            try:
                ev = fetch_scoreboard_event(lid, eid)
            except Exception as e:
                return self.send_body(502, {"error": f"ESPN request failed: {e}"})
            built = build(ev, tid, lid) if ev else None
            if not built:
                return self.send_body(404, {"error": "That game isn't on the scoreboard any more (it may have just ended)."})
            a = built[1]
            with LOCK:
                S["live_game"] = {"league": lid, "event_id": eid, "team_id": tid,
                                  "abbr": a.get("team_abbr") or "", "name": a.get("team_long_name") or "",
                                  "logo": a.get("team_logo") or "",
                                  "label": f"{a.get('team_abbr')} vs {a.get('opponent_abbr')} ({lid})"}
                S["active"] = "LIVE"
                save_settings()
            log("info", "Tracking live game:", S["live_game"]["label"])
        elif p == "/api/livegame/clear":
            with LOCK:
                S["live_game"] = None
                if S["active"] == "LIVE":
                    S["active"] = S["favorites"][0]["key"] if S["favorites"] else None
                save_settings()
            log("info", "Live game slot cleared")
        elif p == "/api/calendar":
            with LOCK:
                new_t = str(body.get("calendar_time") or S["calendar_time"])
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", new_t):
                    return self.send_body(400, {"error": "time must look like 04:00"})
                changed = new_t != S["calendar_time"]
                S["calendar_time"] = new_t
                if "calendar_entity" in body:
                    S["calendar_entity"] = str(body.get("calendar_entity") or "").strip()[:100]
                save_settings()
            log("info", f"Calendar updates daily at {S['calendar_time']} ({TZ_NAME}); entity: {S['calendar_entity'] or 'none'}")
            if changed:
                request_calendar("time")
        elif p == "/api/calendar/refresh":
            request_calendar("manual")
        elif p == "/api/refresh":
            pass
        else:
            return self.send_body(404, {"error": "not found"})

        with LOCK:
            after = [f["key"] for f in S["favorites"]]
        if after != before:
            request_calendar("teams")
        publish_discovery()
        WAKE.set()
        self.send_body(200, self.state_payload())


def main():
    global OPTS, S, LOG_LEVEL
    OPTS = load_json(OPTIONS_FILE, {})
    LOG_LEVEL = LEVELS.get(str(OPTS.get("log_level") or "info").lower(), 20)
    init_storage()
    S = load_settings()
    init_timezone()
    CAL.update(load_json(cal_meta_file(), {}))
    log("info", f"Team Tracker Lite {VERSION} starting (log level: {OPTS.get('log_level') or 'info'})")
    log("info", f"Settings file: {SETTINGS_FILE} ({len(S['favorites'])} saved teams)")
    log("info", f"Refresh: every {S['idle_minutes']} min idle, {S['live_seconds']}s during games")
    mqtt_start()
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=calendar_loop, daemon=True).start()
    threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", 8100), ICSHandler).serve_forever, daemon=True).start()
    log("info", f"Calendar feed on port 8100, updates daily at {S['calendar_time']}")
    log("info", "Web UI on port 8099")
    ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()


if __name__ == "__main__":
    main()

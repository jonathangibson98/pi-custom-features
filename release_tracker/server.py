import datetime as dt
import json
import os
import re
import threading
import time
import uuid
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt
import requests
from flask import Flask, jsonify, request, send_from_directory

DATA = "/data"
TRACK_FILE = f"{DATA}/tracked.json"
SET_FILE = f"{DATA}/settings.json"
DISC_FILE = f"{DATA}/discovered_people.json"
SUP = "http://supervisor"
SUP_HEADERS = {"Authorization": "Bearer " + os.environ.get("SUPERVISOR_TOKEN", "")}
TMDB = "https://api.themoviedb.org/3"

# Everything that can be tracked. TMDB, IGDB and custom ids are stored as given; MusicBrainz ids are text.
TYPES = ("movie", "tv", "game", "album", "artist", "person", "custom")
INT_TYPES = ("movie", "tv", "game", "person")
CATS = ["Tech release", "Merch drop", "Music", "Celebrity", "Event", "Sale / deal", "Other"]
TYPE_LABEL = {
    "movie": "Movie", "tv": "TV", "game": "Game",
    "album": "Album", "artist": "Artist", "person": "Celebrity",
}

DEFAULTS = {
    "tmdb_key": "",
    "region": "US",
    "refresh_hours": 6,
    "window_days": 60,
    "people": ["Jon", "MJ"],
    "mqtt_host": "",
    "mqtt_port": 1883,
    "mqtt_user": "",
    "mqtt_pass": "",
    "igdb_id": "",
    "igdb_secret": "",
    "backup_dir": "release_tracker",
    "backup_every": "off",
    "backup_keep": 10,
    "backup_keys": False,
}
MQTT_KEYS = {"mqtt_host", "mqtt_port", "mqtt_user", "mqtt_pass"}
REFRESH_KEYS = {"tmdb_key", "region", "igdb_id", "igdb_secret", "window_days"}
SECRETS = ("tmdb_key", "mqtt_pass", "igdb_secret")

lock = threading.RLock()
app = Flask(__name__, static_folder="static")


# ---------- storage ----------
def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    with lock:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)


def settings():
    s = dict(DEFAULTS)
    s.update(load(SET_FILE, {}))
    return s


def get_tz():
    try:
        r = requests.get(f"{SUP}/info", headers=SUP_HEADERS, timeout=10)
        return ZoneInfo(r.json()["data"]["timezone"])
    except Exception:
        return ZoneInfo("America/New_York")


TZ = get_tz()


def today():
    return dt.datetime.now(TZ).date()


def norm_id(kind, v):
    return int(v) if kind in INT_TYPES else str(v)


def same(t, kind, tid):
    return t.get("type") == kind and str(t.get("id")) == str(tid)


# ---------- TMDB ----------
def tmdb(path, **params):
    key = settings()["tmdb_key"].strip()
    if not key:
        raise RuntimeError("Add your TMDB key in Settings first")
    headers = {}
    if key.startswith("eyJ"):  # v4 read-access token
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
    r = requests.get(f"{TMDB}{path}", params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


# ---------- IGDB (video games) ----------
IGDB = "https://api.igdb.com/v4"
IGDB_IMG = "https://images.igdb.com/igdb/image/upload/t_cover_big/"
GAME_FIELDS = (
    "name,cover.image_id,game_type.type,first_release_date,"
    "release_dates.date,release_dates.date_format,release_dates.human"
)
MAIN_KINDS = ("Main Game", "Game", "Remake", "Remaster", "Port", "Expanded Game")
_igdb_tok = {"token": None, "exp": 0, "creds": None}


def games_ready(s=None):
    s = s or settings()
    return bool(s["igdb_id"].strip() and s["igdb_secret"].strip())


def igdb_token(force=False):
    s = settings()
    cid, sec = s["igdb_id"].strip(), s["igdb_secret"].strip()
    if not cid or not sec:
        raise RuntimeError("Add your Twitch Client ID and Secret in Settings first")
    t = _igdb_tok
    if not force and t["token"] and t["creds"] == (cid, sec) and time.time() < t["exp"]:
        return cid, t["token"]
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={"client_id": cid, "client_secret": sec, "grant_type": "client_credentials"},
        timeout=15,
    )
    if r.status_code in (400, 401, 403):
        raise RuntimeError("Twitch rejected the Client ID or Secret. Check them in Settings.")
    r.raise_for_status()
    j = r.json()
    t.update(token=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 300, creds=(cid, sec))
    return cid, t["token"]


def igdb(endpoint, query):
    for attempt in (0, 1):
        cid, token = igdb_token(force=attempt == 1)
        r = requests.post(
            f"{IGDB}/{endpoint}",
            data=query,
            headers={"Client-ID": cid, "Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 401 and attempt == 0:
            continue  # token expired, get a fresh one and retry once
        r.raise_for_status()
        return r.json()


def utc_date(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()


def game_dates(g):
    """Exact dates (ISO strings) for one game, plus a vague text like 'Q2 2027' if that is all we have."""
    exact, vague = [], []
    for rd in g.get("release_dates") or []:
        ts = rd.get("date")
        if not ts:
            continue
        if rd.get("date_format", 0) == 0:
            exact.append(utc_date(ts))
        elif rd.get("human") and rd["human"] != "TBD":
            vague.append((ts, rd["human"]))
    if not exact and not vague and g.get("first_release_date"):
        exact.append(utc_date(g["first_release_date"]))
    return exact, (sorted(vague)[0][1] if vague else None)


def fetch_game(item):
    gid = int(item["id"])
    rows = igdb("games", f"fields {GAME_FIELDS},dlcs,expansions,standalone_expansions; where id = {gid};")
    if not rows:
        raise RuntimeError("Game not found on IGDB")
    g = rows[0]
    kind = (g.get("game_type") or {}).get("type") or "Game"
    kid_ids = sorted(set((g.get("dlcs") or []) + (g.get("expansions") or []) + (g.get("standalone_expansions") or [])))
    kids = []
    if kid_ids:
        ids = ",".join(str(i) for i in kid_ids[:100])
        kids = igdb("games", f"fields {GAME_FIELDS}; where id = ({ids}); limit 100;")

    pieces = [(g, "Release" if kind in MAIN_KINDS else f"{kind} release")]
    for k in kids:
        kk = (k.get("game_type") or {}).get("type") or "DLC"
        pieces.append((k, f"{kk}: {k.get('name')}"))

    now = today().isoformat()
    upcoming_ev, vague_ev, past_ev = [], [], []
    for game, label in pieces:
        exact, vague = game_dates(game)
        future = [d for d in exact if d >= now]
        if future:
            upcoming_ev.append((min(future), label))
        elif vague:
            vague_ev.append(f"{label} - expected {vague}")
        elif exact:
            past_ev.append((max(exact), label))
    upcoming_ev.sort()

    cover = (g.get("cover") or {}).get("image_id")
    info = {
        "title": g.get("name"),
        "poster": (IGDB_IMG + cover + ".jpg") if cover else None,
        "status": kind,
        "all_dates": [{"date": d, "label": l} for d, l in upcoming_ev],
    }
    if upcoming_ev:
        info["next_date"], info["label"] = upcoming_ev[0]
    elif vague_ev:
        info["next_date"], info["label"] = None, vague_ev[0]
    elif past_ev:
        info["next_date"], info["label"] = None, f"Already out ({max(past_ev)[0]})"
    else:
        info["next_date"], info["label"] = None, "No date announced yet"
    return info


def search_games(q):
    q = q.replace('"', " ").replace("\\", " ")
    rows = igdb(
        "games",
        f'search "{q}"; fields name,cover.image_id,first_release_date,game_type.type; '
        "where version_parent = null; limit 15;",
    )
    out = []
    for r in rows:
        cover = (r.get("cover") or {}).get("image_id")
        out.append({
            "id": r["id"], "type": "game", "title": r.get("name"),
            "kind": (r.get("game_type") or {}).get("type") or "Game",
            "year": utc_date(r["first_release_date"])[:4] if r.get("first_release_date") else "",
            "poster": (IGDB_IMG + cover + ".jpg") if cover else None,
            "overview": "",
        })
    return out


# ---------- MusicBrainz (albums and artists, free, no key) ----------
MB = "https://musicbrainz.org/ws/2"
MB_UA = "ReleaseTrackerHA/1.5 (Home Assistant add-on; https://github.com/jonathangibson98/my-home-assistant-apps)"
CAA = "https://coverartarchive.org/release-group/{}/front-250"
_mb_gate = threading.Lock()
_mb_last = [0.0]


def mb(path, **params):
    """One MusicBrainz call. They allow about one request per second, so calls wait their turn."""
    params["fmt"] = "json"
    with _mb_gate:
        wait = 1.1 - (time.time() - _mb_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(f"{MB}{path}", params=params, headers={"User-Agent": MB_UA, "Accept": "application/json"}, timeout=20)
        finally:
            _mb_last[0] = time.time()
    if r.status_code in (429, 503):
        raise RuntimeError("MusicBrainz is busy right now. Try again in a minute.")
    r.raise_for_status()
    return r.json()


def lucene(q, fields):
    """Turn what the person typed into a safe MusicBrainz search: every word must match one of the fields."""
    words = re.sub(r"[^\w\s]|_", " ", q.lower()).split()[:8]
    return " AND ".join("(" + " OR ".join(f"{f}:{w}" for f in fields) + ")" for w in words)


def mb_when(d, now):
    """Sort a MusicBrainz date (full, month only, or year only) into exact / vague / past."""
    d = (d or "").strip()
    if len(d) == 10:
        return ("exact", d) if d >= now else ("past", d)
    if len(d) == 7:
        return ("vague", d) if d >= now[:7] else ("past", d)
    if len(d) == 4:
        return ("vague", d) if d > now[:4] else ("past", d)
    return None


def pretty_vague(d):
    if len(d) == 7:
        try:
            return dt.date(int(d[:4]), int(d[5:7]), 1).strftime("%B %Y")
        except ValueError:
            return d
    return d


def credit_name(rec):
    return "".join((a.get("name") or "") + (a.get("joinphrase") or "") for a in rec.get("artist-credit") or [])


def fetch_album(item):
    d = mb(f"/release-group/{item['id']}", inc="artist-credits")
    artist = credit_name(d)
    kind = d.get("primary-type") or "Album"
    now = today().isoformat()
    info = {
        "title": f"{artist} - {d.get('title')}" if artist else d.get("title"),
        "poster": CAA.format(item["id"]), "status": kind, "all_dates": [],
    }
    w = mb_when(d.get("first-release-date"), now)
    if w and w[0] == "exact":
        info["next_date"], info["label"] = w[1], f"{kind} release"
        info["all_dates"] = [{"date": w[1], "label": f"{kind} release"}]
    elif w and w[0] == "vague":
        info["next_date"], info["label"] = None, f"{kind} - expected {pretty_vague(w[1])}"
    elif w:
        info["next_date"], info["label"] = None, f"Already out ({w[1]})"
    else:
        info["next_date"], info["label"] = None, "No date announced yet"
    return info


def artist_groups(mbid):
    out, offset = [], 0
    while offset < 300:
        d = mb("/release-group", artist=mbid, limit=100, offset=offset)
        out += d.get("release-groups") or []
        offset += 100
        if offset >= int(d.get("release-group-count") or 0):
            break
    return out


def fetch_artist(item):
    now = today().isoformat()
    exact, vague = [], []
    for rg in artist_groups(item["id"]):
        if rg.get("primary-type") in ("Broadcast", "Other"):
            continue
        w = mb_when(rg.get("first-release-date"), now)
        if not w or w[0] == "past":
            continue
        label = f"{rg.get('primary-type') or 'Release'}: {rg.get('title')}"
        (exact if w[0] == "exact" else vague).append((w[1], label))
    exact.sort()
    vague.sort()
    info = {
        "title": item.get("title"), "poster": item.get("poster"), "status": "Artist",
        "all_dates": [{"date": d, "label": l} for d, l in exact[:10]],
    }
    if exact:
        info["next_date"], info["label"] = exact[0]
    elif vague:
        info["next_date"], info["label"] = None, f"{vague[0][1]} - expected {pretty_vague(vague[0][0])}"
    else:
        info["next_date"], info["label"] = None, "Nothing announced yet"
    return info


def search_music(q):
    qa = lucene(q, ["artist"])
    if not qa:
        return []
    out = []
    for a in mb("/artist", query=qa, limit=5).get("artists") or []:
        bits = [a.get("disambiguation"), a.get("type"), a.get("country")]
        out.append({
            "id": a["id"], "type": "artist", "title": a.get("name"), "kind": "Artist", "year": "",
            "poster": None, "overview": (" - ".join(b for b in bits if b) + ". Follow for new releases.")[:140],
        })
    for r in mb("/release-group", query=lucene(q, ["releasegroup", "artist"]), limit=10).get("release-groups") or []:
        artist = credit_name(r)
        out.append({
            "id": r["id"], "type": "album", "kind": r.get("primary-type") or "Album",
            "title": f"{artist} - {r.get('title')}" if artist else r.get("title"),
            "year": (r.get("first-release-date") or "")[:4], "poster": CAA.format(r["id"]), "overview": "",
        })
    return out


# ---------- celebrities (TMDB people) ----------
def search_people(q):
    res = tmdb("/search/person", query=q, include_adult="false")
    out = []
    for r in res.get("results", [])[:12]:
        known = [k.get("title") or k.get("name") for k in r.get("known_for") or []]
        known = [k for k in known if k][:3]
        text = r.get("known_for_department") or ""
        if known:
            text += (". " if text else "") + "Known for " + ", ".join(known)
        out.append({
            "id": r["id"], "type": "person", "title": r.get("name"), "kind": "Celebrity",
            "year": "", "poster": r.get("profile_path"), "overview": text[:140],
        })
    return out


def fetch_person(item):
    d = tmdb(f"/person/{item['id']}", append_to_response="combined_credits")
    now = today().isoformat()
    cred = d.get("combined_credits") or {}
    seen, events = set(), []
    for c in (cred.get("cast") or []) + (cred.get("crew") or []):
        mt = c.get("media_type")
        if mt not in ("movie", "tv"):
            continue
        day = (c.get("release_date") or c.get("first_air_date") or "")[:10]
        if len(day) != 10 or day < now:
            continue
        key = (mt, c.get("id"))
        if key in seen:
            continue
        seen.add(key)
        name = c.get("title") or c.get("name") or "Untitled"
        role = c.get("character") or c.get("job")
        label = ("Movie: " if mt == "movie" else "TV: ") + name + (f" ({role})" if role else "")
        events.append((day, label))
    events.sort()
    info = {
        "title": d.get("name") or item.get("title"), "poster": d.get("profile_path") or item.get("poster"),
        "status": d.get("known_for_department"),
        "all_dates": [{"date": a, "label": b} for a, b in events[:15]],
    }
    if events:
        info["next_date"], info["label"] = events[0]
    else:
        info["next_date"], info["label"] = None, "Nothing announced yet"
    return info


# ---------- custom items (tech, merch drops, events, anything) ----------
def fetch_custom(item):
    cat = item.get("category") or "Other"
    day = item.get("date") or ""
    info = {
        "title": item.get("title"), "poster": item.get("poster"), "status": cat,
        "time": item.get("time") or "", "all_dates": [],
    }
    if not day:
        info["next_date"], info["label"] = None, "Date not announced yet"
    elif day >= today().isoformat():
        info["next_date"], info["label"] = day, cat
        info["all_dates"] = [{"date": day, "label": cat}]
    else:
        info["next_date"], info["label"] = None, f"Date passed ({day})"
    return info


def clean_url(v):
    v = str(v or "").strip()
    if not v:
        return ""
    if not re.match(r"^https?://", v, re.I) or len(v) > 500:
        raise RuntimeError("Links have to start with http:// or https://")
    return v


def clean_custom(b):
    title = " ".join(str(b.get("title") or "").split())[:100]
    if not title:
        raise RuntimeError("Type a name first")
    cat = b.get("category")
    day = str(b.get("date") or "").strip()
    if day:
        try:
            dt.date.fromisoformat(day)
        except ValueError:
            raise RuntimeError("That date does not look right")
    return {
        "title": title,
        "category": cat if cat in CATS else "Other",
        "date": day,
        "time": " ".join(str(b.get("time") or "").split())[:20],
        "notes": " ".join(str(b.get("notes") or "").split())[:300],
        "url": clean_url(b.get("url")),
        "poster": clean_url(b.get("image")) or None,
    }


MOVIE_TYPES = {2: "In theaters", 3: "In theaters", 4: "Digital release", 5: "Physical release"}


def fetch_info(item):
    kind = item["type"]
    if kind == "game":
        return fetch_game(item)
    if kind == "custom":
        return fetch_custom(item)
    if kind == "album":
        return fetch_album(item)
    if kind == "artist":
        return fetch_artist(item)
    if kind == "person":
        return fetch_person(item)
    s = settings()
    now = today().isoformat()
    if kind == "movie":
        d = tmdb(f"/movie/{item['id']}", append_to_response="release_dates")
        found = {}
        for c in d.get("release_dates", {}).get("results", []):
            if c.get("iso_3166_1") != s["region"]:
                continue
            for rd in c.get("release_dates", []):
                label = MOVIE_TYPES.get(rd.get("type"))
                day = (rd.get("release_date") or "")[:10]
                if label and day and (label not in found or day < found[label]):
                    found[label] = day
        if not found and d.get("release_date"):
            found["Release"] = d["release_date"]
        events = sorted((day, label) for label, day in found.items())
        future = [e for e in events if e[0] >= now]
        info = {
            "title": d.get("title"),
            "poster": d.get("poster_path"),
            "status": d.get("status"),
            "all_dates": [{"date": a, "label": b} for a, b in events],
        }
        if future:
            info["next_date"], info["label"] = future[0]
        elif events:
            info["next_date"], info["label"] = None, f"Already out ({events[-1][0]})"
        else:
            info["next_date"], info["label"] = None, "No date announced yet"
        return info

    d = tmdb(f"/tv/{item['id']}")
    n = d.get("next_episode_to_air")
    info = {"title": d.get("name"), "poster": d.get("poster_path"), "status": d.get("status")}
    if n and n.get("air_date"):
        if n.get("episode_number") == 1:
            label = f"Season {n.get('season_number')} premiere"
        else:
            label = f"S{n.get('season_number')}E{n.get('episode_number')}"
            if n.get("name"):
                label += f" - {n['name']}"
        info["next_date"], info["label"] = n["air_date"], label
    else:
        info["next_date"] = None
        info["label"] = {
            "Returning Series": "No date announced yet",
            "Ended": "Ended",
            "Canceled": "Canceled",
            "In Production": "In production",
            "Planned": "Planned",
        }.get(d.get("status"), d.get("status") or "Unknown")
    return info


def refresh_all():
    tracked = load(TRACK_FILE, [])
    results = {}
    for it in tracked:
        try:
            results[(it["type"], str(it["id"]))] = (fetch_info(it), None)
        except Exception as e:
            results[(it["type"], str(it["id"]))] = (None, str(e))
    with lock:
        current = load(TRACK_FILE, [])
        for it in current:
            res = results.get((it["type"], str(it["id"])))
            if res:
                if res[0]:
                    it["info"] = res[0]
                it["error"] = res[1]
        save(TRACK_FILE, current)
    publish()


# ---------- derived data ----------
def days_until(date_str):
    return (dt.date.fromisoformat(date_str) - today()).days


def upcoming():
    rows = []
    for it in load(TRACK_FILE, []):
        info = it.get("info") or {}
        nd = info.get("next_date")
        if not nd:
            continue
        d = days_until(nd)
        if d < 0:
            continue
        rows.append(
            {
                "title": info.get("title") or it["title"],
                "type": it.get("category") or "Other" if it["type"] == "custom" else TYPE_LABEL.get(it["type"], "TV"),
                "date": nd,
                "days_until": d,
                "label": info.get("label"),
                "time": info.get("time") or "",
                "note": it.get("notes") or "",
                "people": it.get("people", []),
            }
        )
    rows.sort(key=lambda r: (r["date"], r["title"]))
    return rows


# ---------- MQTT ----------
client = None
_sent = {}
T_STATUS = "release_tracker/status"
T = {"releases": "release_tracker/releases"}
DEVICE = {
    "identifiers": ["release_tracker"],
    "name": "Release Tracker",
    "manufacturer": "Jon",
    "model": "Release Tracker add-on",
}


def mqtt_conf():
    s = settings()
    if s["mqtt_host"]:
        return s["mqtt_host"], int(s["mqtt_port"] or 1883), s["mqtt_user"], s["mqtt_pass"]
    try:
        r = requests.get(f"{SUP}/services/mqtt", headers=SUP_HEADERS, timeout=10)
        r.raise_for_status()
        d = r.json()["data"]
        return d["host"], int(d["port"]), d.get("username"), d.get("password")
    except Exception as e:
        print(f"[mqtt] no broker info from Home Assistant: {e}", flush=True)
        return None


def pub(topic, payload):
    if client is None:
        return
    text = payload if isinstance(payload, str) else json.dumps(payload)
    if _sent.get(topic) == text:
        return
    _sent[topic] = text
    client.publish(topic, text, retain=True)


def send_discovery(c):
    cfg = {
        "name": "Releases", "icon": "mdi:calendar-star",
        "unique_id": "release_tracker_releases",
        "state_topic": T["releases"], "value_template": "{{ value_json.state }}",
        "unit_of_measurement": "releases",
        "json_attributes_topic": T["releases"],
        "json_attributes_template": "{{ value_json.attributes | tojson }}",
        "device": DEVICE, "availability_topic": T_STATUS,
    }
    c.publish("homeassistant/sensor/release_tracker/releases/config", json.dumps(cfg), retain=True)
    cleanup_legacy(c)


def cleanup_legacy(c):
    """Remove the many sensors older versions created, so only the one release sensor is left."""
    for comp, key in (("sensor", "next"), ("sensor", "upcoming"), ("binary_sensor", "today"), ("sensor", "games")):
        c.publish(f"homeassistant/{comp}/release_tracker/{key}/config", "", retain=True)
    for key in ("next", "upcoming", "today", "games"):
        c.publish(f"release_tracker/{key}", "", retain=True)
    for sl in load(DISC_FILE, []):
        c.publish(f"homeassistant/sensor/release_tracker/p_{sl}_upcoming/config", "", retain=True)
        c.publish(f"homeassistant/binary_sensor/release_tracker/p_{sl}_today/config", "", retain=True)
        c.publish(f"homeassistant/sensor/release_tracker/p_{sl}_games/config", "", retain=True)
        for key in ("upcoming", "today", "games"):
            c.publish(f"release_tracker/person/{sl}/{key}", "", retain=True)
    try:
        os.remove(DISC_FILE)
    except OSError:
        pass


def slug(name):
    out = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")
    return out or "person"


def people_list():
    people = {}
    for p in settings().get("people", []):
        p = str(p).strip()
        if p and slug(p) not in people:
            people[slug(p)] = p
    return people


def publish():
    s = settings()
    w = int(s["window_days"])
    rows = upcoming()
    soon = [r for r in rows if r["days_until"] <= w]
    now = [r for r in rows if r["days_until"] == 0]
    n = rows[0] if rows else {}
    people = people_list()
    pub(T["releases"], {"state": len(soon), "attributes": {
        "window_days": w,
        "tracked_count": len(load(TRACK_FILE, [])),
        "items": soon[:30],
        "next_title": n.get("title"), "next_date": n.get("date"), "next_days_until": n.get("days_until"),
        "next_label": n.get("label"), "next_type": n.get("type"),
        "today_count": len(now), "today": [r["title"] for r in now],
        "by_type": {t: sum(1 for r in soon if r["type"] == t) for t in sorted({r["type"] for r in soon})},
        "by_person": {name: [r["title"] for r in soon if name in r["people"]] for name in people.values()}}})


def on_connect(c, userdata, flags, reason_code, properties=None):
    print(f"[mqtt] connected: {reason_code}", flush=True)
    _sent.clear()
    send_discovery(c)
    c.publish(T_STATUS, "online", retain=True)
    publish()


def connect_mqtt():
    global client
    if client is not None:
        try:
            client.publish(T_STATUS, "offline", retain=True)
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        client = None
    conf = mqtt_conf()
    if not conf:
        return
    host, port, user, pw = conf
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="release_tracker_addon")
    if user:
        c.username_pw_set(user, pw)
    c.will_set(T_STATUS, "offline", retain=True)
    c.on_connect = on_connect
    client = c
    try:
        c.connect_async(host, port, 60)
        c.loop_start()
    except Exception as e:
        print(f"[mqtt] connect failed: {e}", flush=True)


# ---------- backups (saved into the Home Assistant share folder) ----------
SHARE = "/share"
BK_FILE = f"{DATA}/backup_state.json"
BK_AUTO = re.compile(r"^release-tracker-\d{8}-\d{6}\.json$")
BK_ANY = re.compile(r"^release-tracker-(prerestore-)?\d{8}-\d{6}\.json$")
BK_EVERY = {"daily": 24, "weekly": 168}


def norm_backup_dir(raw):
    """Folder under /share, as a clean relative path. Refuses anything that escapes /share."""
    p = str(raw or "").strip().replace("\\", "/")
    if p == SHARE or p.startswith(SHARE + "/"):
        p = p[len(SHARE):]
    p = p.strip("/")
    root = os.path.realpath(SHARE)
    full = os.path.realpath(os.path.join(SHARE, p))
    if full != root and not full.startswith(root + os.sep):
        raise RuntimeError("The backup folder has to be inside the share folder")
    return p


def backup_folder(s=None):
    return os.path.join(SHARE, norm_backup_dir((s or settings())["backup_dir"]))


def make_backup(tag=""):
    s = settings()
    folder = backup_folder(s)
    now = dt.datetime.now(TZ)
    name = f"release-tracker-{tag + '-' if tag else ''}{now.strftime('%Y%m%d-%H%M%S')}.json"
    keys = bool(s.get("backup_keys"))
    payload = {
        "app": "release_tracker",
        "format": 1,
        "created": now.isoformat(timespec="seconds"),
        "settings": {k: v for k, v in s.items() if not k.startswith("backup_") and (keys or k not in SECRETS)},
        "tracked": load(TRACK_FILE, []),
    }
    try:
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, name + ".tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, os.path.join(folder, name))
        if not tag:  # keep only the newest N regular backups; safety copies are never pruned
            mine = sorted(n for n in os.listdir(folder) if BK_AUTO.match(n))
            for old in mine[:-max(1, int(s["backup_keep"]))]:
                try:
                    os.remove(os.path.join(folder, old))
                except OSError:
                    pass
    except OSError as e:
        raise RuntimeError(f"Could not write to {folder}: {e.strerror or e}")
    return name


def run_backup(tag=""):
    st = load(BK_FILE, {})
    if not tag:
        st["attempt"] = time.time()
    try:
        name = make_backup(tag)
    except Exception as e:
        if not tag:
            st["error"] = str(e)
            save(BK_FILE, st)
        raise
    if not tag:
        st.update(ts=time.time(), file=name, error=None)
        save(BK_FILE, st)
    return name


def auto_backup(s):
    hours = BK_EVERY.get(s["backup_every"])
    if not hours:
        return
    st, now = load(BK_FILE, {}), time.time()
    if now - st.get("ts", 0) >= hours * 3600 and now - st.get("attempt", 0) >= 3600:
        try:
            print(f"[backup] saved {run_backup()}", flush=True)
        except Exception as e:
            print(f"[backup] {e}", flush=True)


def list_backups():
    folder, out = backup_folder(), []
    try:
        for n in os.listdir(folder):
            if BK_ANY.match(n):
                st = os.stat(os.path.join(folder, n))
                out.append({"name": n, "size": st.st_size, "time": st.st_mtime, "safety": "-prerestore-" in n})
    except FileNotFoundError:
        pass
    out.sort(key=lambda b: b["time"], reverse=True)
    return out


def restore_backup(name):
    if not BK_ANY.match(name or ""):
        raise RuntimeError("That is not a Release Tracker backup file")
    try:
        with open(os.path.join(backup_folder(), name)) as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise RuntimeError("Could not read that backup file")
    tracked = data.get("tracked") if isinstance(data, dict) else None
    if data.get("app") != "release_tracker" or not isinstance(tracked, list):
        raise RuntimeError("That file is not a Release Tracker backup")
    clean = [t for t in tracked if isinstance(t, dict) and t.get("id") is not None and t.get("type") in TYPES]
    run_backup("prerestore")  # safety copy of what is there now
    with lock:
        s = settings()
        for k, v in (data.get("settings") or {}).items():
            if k in DEFAULTS and not k.startswith("backup_"):
                s[k] = v  # keys and passwords only come back if the backup included them
        s["people"] = clean_people(s["people"])
        save(SET_FILE, s)
        save(TRACK_FILE, clean)
    threading.Thread(target=connect_mqtt, daemon=True).start()
    threading.Thread(target=refresh_all, daemon=True).start()
    return len(clean)


# ---------- background worker ----------
def worker():
    last = 0
    while True:
        try:
            s = settings()
            if client is None:
                connect_mqtt()
            due = time.time() - last >= max(1, float(s["refresh_hours"])) * 3600
            if due:
                refresh_all()
                last = time.time()
            else:
                publish()  # keeps "days until" correct at midnight
        except Exception as e:
            print(f"[worker] {e}", flush=True)
        try:
            auto_backup(settings())
        except Exception as e:
            print(f"[backup] {e}", flush=True)
        time.sleep(60)


# ---------- web API ----------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/state")
def api_state():
    s = settings()
    tracked = load(TRACK_FILE, [])
    for it in tracked:
        if it["type"] == "custom":
            it["info"] = fetch_custom(it)  # no lookup needed, so it is always current
        nd = (it.get("info") or {}).get("next_date")
        it["days_until"] = days_until(nd) if nd else None
    safe = {k: v for k, v in s.items() if k not in SECRETS}
    safe["has_key"] = bool(s["tmdb_key"])
    safe["has_mqtt_pass"] = bool(s["mqtt_pass"])
    safe["has_games_key"] = games_ready(s)
    safe["has_igdb_secret"] = bool(s["igdb_secret"])
    return jsonify({"settings": safe, "tracked": tracked, "mqtt": client is not None, "cats": CATS})


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    kind = request.args.get("kind")
    finders = {"games": search_games, "music": search_music, "people": search_people}
    if kind in finders:
        try:
            return jsonify(finders[kind](q))
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    try:
        res = tmdb("/search/multi", query=q, include_adult="false")
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    out = []
    for r in res.get("results", []):
        if r.get("media_type") not in ("movie", "tv"):
            continue
        out.append({
            "id": r["id"], "type": r["media_type"],
            "title": r.get("title") or r.get("name"),
            "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
            "poster": r.get("poster_path"),
            "overview": (r.get("overview") or "")[:140],
        })
    return jsonify(out[:12])


def clean_people(v):
    if isinstance(v, str):
        v = v.split(",")
    return [str(p).strip() for p in (v or []) if str(p).strip()]


@app.route("/api/track/<media_type>/<tid>/people", methods=["PUT"])
def api_set_people(media_type, tid):
    people = clean_people(request.get_json(force=True).get("people"))
    with lock:
        tracked = load(TRACK_FILE, [])
        for t in tracked:
            if same(t, media_type, tid):
                t["people"] = people
        save(TRACK_FILE, tracked)
    publish()
    return jsonify({"ok": True})


@app.route("/api/track", methods=["POST"])
def api_track():
    b = request.get_json(force=True)
    kind = b.get("type")
    if kind not in TYPES or kind == "custom":
        return jsonify({"error": "Unknown type"}), 400
    try:
        item = {"id": norm_id(kind, b["id"]), "type": kind, "title": b.get("title", ""), "poster": b.get("poster"),
                "people": clean_people(b.get("people"))}
    except (KeyError, ValueError):
        return jsonify({"error": "That result has no usable id"}), 400
    with lock:
        tracked = load(TRACK_FILE, [])
        for t in tracked:
            if same(t, kind, item["id"]):
                t["people"] = sorted(set(t.get("people", [])) | set(item["people"]))
                save(TRACK_FILE, tracked)
                publish()
                return jsonify({"ok": True})
        try:
            item["info"] = fetch_info(item)
        except Exception as e:
            item["error"] = str(e)
        tracked.append(item)
        save(TRACK_FILE, tracked)
    publish()
    return jsonify({"ok": True})


@app.route("/api/custom", methods=["POST"])
def api_custom_add():
    b = request.get_json(force=True) or {}
    try:
        item = clean_custom(b)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    item.update(id=uuid.uuid4().hex[:12], type="custom", people=clean_people(b.get("people")))
    item["info"] = fetch_custom(item)
    with lock:
        tracked = load(TRACK_FILE, [])
        tracked.append(item)
        save(TRACK_FILE, tracked)
    publish()
    return jsonify({"ok": True})


@app.route("/api/custom/<cid>", methods=["PUT"])
def api_custom_edit(cid):
    try:
        fields = clean_custom(request.get_json(force=True) or {})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    with lock:
        tracked = load(TRACK_FILE, [])
        for t in tracked:
            if same(t, "custom", cid):
                t.update(fields)
                t["info"] = fetch_custom(t)
                save(TRACK_FILE, tracked)
                break
        else:
            return jsonify({"error": "That item is not in your list anymore"}), 404
    publish()
    return jsonify({"ok": True})


@app.route("/api/track/<media_type>/<tid>", methods=["DELETE"])
def api_untrack(media_type, tid):
    with lock:
        tracked = [t for t in load(TRACK_FILE, []) if not same(t, media_type, tid)]
        save(TRACK_FILE, tracked)
    publish()
    return jsonify({"ok": True})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    refresh_all()
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    b = request.get_json(force=True)
    old = settings()
    s = dict(old)
    try:
        for k in DEFAULTS:
            if k not in b:
                continue
            if k in SECRETS and not str(b[k]).strip():
                continue  # blank = keep the saved one
            v = b[k]
            if k == "people":
                v = clean_people(v)
            elif k == "backup_dir":
                v = norm_backup_dir(v)
            elif k == "backup_every":
                v = v if v in ("off", "daily", "weekly") else "off"
            elif k == "backup_keep":
                v = min(100, max(1, int(v or 10)))
            elif k == "backup_keys":
                v = bool(v)
            s[k] = v
    except (RuntimeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    save(SET_FILE, s)
    changed = {k for k in DEFAULTS if s[k] != old[k]}
    if changed & MQTT_KEYS:
        threading.Thread(target=connect_mqtt, daemon=True).start()
    if changed & REFRESH_KEYS:
        threading.Thread(target=refresh_all, daemon=True).start()
    else:
        threading.Thread(target=publish, daemon=True).start()
    return jsonify({"ok": True})


# ---------- people ----------
def clean_name(v):
    return " ".join(str(v or "").replace(",", " ").split())[:30]


@app.route("/api/people", methods=["POST"])
def api_people_add():
    name = clean_name((request.get_json(force=True) or {}).get("name"))
    if not name:
        return jsonify({"error": "Type a name first"}), 400
    with lock:
        s = settings()
        people = clean_people(s["people"])
        if slug(name) in {slug(p) for p in people}:
            return jsonify({"error": f"{name} is already on the list"}), 400
        s["people"] = people + [name]
        save(SET_FILE, s)
    publish()
    return jsonify({"ok": True})


@app.route("/api/people", methods=["PUT"])
def api_people_rename():
    b = request.get_json(force=True) or {}
    old, new = str(b.get("old", "")), clean_name(b.get("new"))
    if not new:
        return jsonify({"error": "Type a name first"}), 400
    with lock:
        s = settings()
        people = clean_people(s["people"])
        if old not in people:
            return jsonify({"error": "That person is not on the list"}), 404
        if any(p != old and slug(p) == slug(new) for p in people):
            return jsonify({"error": f"{new} is already on the list"}), 400
        s["people"] = [new if p == old else p for p in people]
        save(SET_FILE, s)
        tracked = load(TRACK_FILE, [])
        for t in tracked:  # tags follow the new name
            t["people"] = list(dict.fromkeys(new if p == old else p for p in t.get("people", [])))
        save(TRACK_FILE, tracked)
    publish()
    return jsonify({"ok": True})


@app.route("/api/people/remove", methods=["POST"])
def api_people_remove():
    name = str((request.get_json(force=True) or {}).get("name", ""))
    with lock:
        s = settings()
        s["people"] = [p for p in clean_people(s["people"]) if p != name]
        save(SET_FILE, s)
        tracked = load(TRACK_FILE, [])
        for t in tracked:
            t["people"] = [p for p in t.get("people", []) if p != name]
        save(TRACK_FILE, tracked)
    publish()
    return jsonify({"ok": True})


# ---------- backup endpoints ----------
@app.route("/api/backups")
def api_backups():
    s = settings()
    out = {"files": [], "last": load(BK_FILE, {}), "share_ok": os.path.isdir(SHARE), "error": None}
    try:
        rel = norm_backup_dir(s["backup_dir"])
        out["folder"] = "/share/" + rel if rel else "/share"
        out["files"] = list_backups()
    except Exception as e:
        out["folder"], out["error"] = "/share", str(e)
    return jsonify(out)


@app.route("/api/backups", methods=["POST"])
def api_backup_now():
    try:
        return jsonify({"ok": True, "file": run_backup()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/backups/restore", methods=["POST"])
def api_backup_restore():
    try:
        n = restore_backup(str((request.get_json(force=True) or {}).get("file", "")))
        return jsonify({"ok": True, "count": n})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8099, threaded=True)

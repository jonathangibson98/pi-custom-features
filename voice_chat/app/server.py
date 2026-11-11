#!/usr/bin/env python3
"""Voice Chat 2.2 - hands-free voice conversation with a Home Assistant AI agent.

Runs two ways from the same code:
  * Home Assistant add-on (Supervisor token, ingress, /data/options.json)
  * Standalone Docker (HA_URL + HA_TOKEN, settings from VC_* environment variables)

Browser mic -> (HA speech-to-text) -> HA conversation agent -> HA text-to-speech
-> media player(s) and/or the browser itself.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import ssl
import subprocess
import time
import uuid
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("voice_chat")

APP_DIR = Path(__file__).parent
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
ADDON = bool(SUPERVISOR_TOKEN)
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
HA_BASE = "http://supervisor/core" if ADDON else os.environ.get("HA_URL", "http://homeassistant:8123").rstrip("/")
HA_TOKEN = SUPERVISOR_TOKEN or os.environ.get("HA_TOKEN", "")
HA_API = HA_BASE + "/api"
INGRESS_IP = "172.30.32.2" if ADDON else ""  # Home Assistant's ingress proxy

# name: (type, default). Env overrides use VC_<NAME>, e.g. VC_MEDIA_PLAYER.
DEFAULTS = {
    "conversation_agent": (str, "conversation.home_assistant"),
    "media_player": (str, ""),
    "tts_entity": (str, ""),
    "stt_entity": (str, ""),
    "language": (str, ""),
    "hands_free": (bool, True),
    "silence_ms": (int, 1200),
    "volume": (float, 0.0),
    "password": (str, ""),
    "certfile": (str, "fullchain.pem"),
    "keyfile": (str, "privkey.pem"),
    # 2.0
    "wake_word": (str, ""),
    "stop_words": (str, "stop listening,goodbye,never mind,cancel"),
    "sensitivity": (str, "normal"),  # low | normal | high
    "chimes": (bool, True),
    "idle_timeout_s": (int, 120),
    "browser_playback": (bool, True),
    "save_history": (bool, True),
    "history_limit": (int, 100),
    # 2.1 - household context (who is who, nicknames, places, music...)
    "context_enabled": (bool, True),
    "context_entity": (str, "sensor.combined_info"),
    "context_attributes": (str, "household_text,friends_text,notable_people,places"),
    "context_skip_agents": (str, "conversation.home_assistant"),
    "context_max_chars": (int, 40000),
    "speaker_name": (str, ""),
}


def load_options() -> dict:
    raw = {}
    path = DATA_DIR / "options.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text())
        except ValueError:
            log.warning("Could not read %s", path)
    out = {}
    for key, (kind, default) in DEFAULTS.items():
        value = os.environ.get("VC_" + key.upper(), raw.get(key, default))
        if value is None:
            value = default
        try:
            if kind is bool:
                value = value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
            elif kind is int:
                value = int(float(value))
            elif kind is float:
                value = float(value)
            else:
                value = str(value).strip()
        except (TypeError, ValueError):
            value = default
        out[key] = value
    return out


OPTIONS = load_options()
SESSION: ClientSession | None = None
_lang_cache: str | None = None
AUDIO: dict[str, tuple[float, bytes, str]] = {}  # id -> (expires, bytes, mime)


class HAError(Exception):
    pass


def opt(key: str) -> str:
    return str(OPTIONS.get(key) or "").strip()


async def ha(method: str, path: str, *, headers=None, raw=False, **kwargs):
    h = {"Authorization": f"Bearer {HA_TOKEN}"}
    if headers:
        h.update(headers)
    try:
        async with SESSION.request(method, HA_API + path, headers=h, **kwargs) as r:
            if raw:
                if r.status >= 400:
                    raise HAError(f"Home Assistant returned {r.status} for {path}")
                return await r.read(), r.headers.get("Content-Type", "audio/mpeg")
            text = await r.text()
            if r.status >= 400:
                raise HAError(f"Home Assistant returned {r.status} for {path}: {text[:300]}")
            return json.loads(text) if text else None
    except asyncio.TimeoutError:
        raise HAError(f"Home Assistant timed out on {path}")
    except ClientError as e:
        raise HAError(f"Could not reach Home Assistant: {e}")


async def language() -> str:
    global _lang_cache
    if opt("language"):
        return opt("language")
    if not _lang_cache:
        cfg = await ha("GET", "/config")
        _lang_cache = (cfg or {}).get("language", "en")
    return _lang_cache


def clean_for_tts(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`#>~|]+", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def reply_text(result) -> str:
    try:
        return result["response"]["speech"]["plain"]["speech"] or ""
    except (KeyError, TypeError):
        return ""


ENTITY = {"media_player": re.compile(r"media_player\.[a-z0-9_]+"),
          "conversation": re.compile(r"conversation\.[a-z0-9_]+")}


def chosen_speakers(request, body=None) -> list[str]:
    """Speakers picked on the page (one or several), else the configured one.
    The special value 'browser' means: play in this browser instead."""
    body = body or {}
    values = body.get("speakers")
    if values is None:
        values = [body.get("media_player") or request.query.get("mp") or ""]
    out = []
    for v in values if isinstance(values, list) else [values]:
        v = str(v).strip()
        if v == "browser" and OPTIONS["browser_playback"]:
            out.append(v)
        elif ENTITY["media_player"].fullmatch(v) and v not in out:
            out.append(v)
    return out or ([opt("media_player")] if opt("media_player") else [])


def chosen_agent(body) -> str:
    v = str((body or {}).get("agent") or "").strip()
    return v if ENTITY["conversation"].fullmatch(v) else opt("conversation_agent")


async def tts_to_player(message: str, mp: str) -> None:
    volume = OPTIONS["volume"]
    if volume > 0:
        await ha("POST", "/services/media_player/volume_set",
                 json={"entity_id": mp, "volume_level": volume})
    data = {"entity_id": opt("tts_entity"), "media_player_entity_id": mp,
            "message": message, "cache": False}
    if opt("language"):
        data["language"] = opt("language")
    await ha("POST", "/services/tts/speak", json=data)


async def tts_to_browser(message: str) -> str:
    """Render speech through HA and keep the audio so the browser can play it."""
    payload = {"engine_id": opt("tts_entity"), "message": message,
               "language": await language(), "cache": False}
    info = await ha("POST", "/tts_get_url", json=payload)
    path = (info or {}).get("path") or ""
    if not path.startswith("/"):
        raise HAError("Home Assistant did not return a TTS audio path.")
    audio, mime = await ha("GET", path.removeprefix("/api"), raw=True)
    now = time.time()
    for k in [k for k, v in AUDIO.items() if v[0] < now]:
        AUDIO.pop(k, None)
    key = uuid.uuid4().hex
    AUDIO[key] = (now + 600, audio, mime)
    return key


async def speak(text: str, speakers: list[str]) -> dict:
    message = clean_for_tts(text)
    out = {"audio": None}
    if not message or not speakers:
        return out
    jobs = []
    for sp in speakers:
        if sp == "browser":
            jobs.append(tts_to_browser(message))
        else:
            jobs.append(tts_to_player(message, sp))
    results = await asyncio.gather(*jobs, return_exceptions=True)
    for sp, res in zip(speakers, results):
        if isinstance(res, Exception):
            if len(speakers) == 1:
                raise res
            log.warning("Speaking on %s failed: %s", sp, res)
        elif sp == "browser":
            out["audio"] = res
    return out


async def wait_playback(mp: str) -> None:
    """Block until the media player has started and then finished playing."""
    start = time.monotonic()
    started = False
    while True:
        elapsed = time.monotonic() - start
        if elapsed > 180:
            return
        try:
            state = ((await ha("GET", f"/states/{mp}")) or {}).get("state")
        except HAError:
            return
        if state in ("playing", "buffering"):
            started = True
        elif started:
            return
        elif elapsed > 10:
            return
        await asyncio.sleep(0.4)


# ------------------------------------------------------------- household context
#
# Reads your combined info sensor (sensor.combined_info) and hands it to the AI
# agent with the first message of a conversation, so it knows who Jon, MJ, Von,
# Justin... are when you mention them. The text is NOT stored in chat history and
# NOT shown on the page.

CONTEXT_CACHE: dict = {"ts": 0.0, "text": "", "facts": ""}
CONV_SEEN: dict[str, float] = {}  # conversation_id -> last time we talked in it
CONTEXT_RESEND_S = 240  # Home Assistant forgets a conversation after ~5 idle minutes
CONTEXT_CACHE_S = 60


def render(value, depth: int = 0) -> str:
    """Turn a sensor attribute (text, list or dict) into plain indented text."""
    pad = "  " * depth
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                if v:
                    lines += [f"{pad}{k}:", render(v, depth + 1)]
            elif v not in (None, ""):
                lines.append(f"{pad}{k}: {v}")
        return "\n".join(lines)
    if isinstance(value, list):
        out = []
        for v in value:
            if isinstance(v, (dict, list)):
                out += [f"{pad}-", render(v, depth + 1)]
            else:
                out.append(f"{pad}- {v}")
        return "\n".join(out)
    return f"{pad}{value}"


def context_agent_ok(agent: str) -> bool:
    """The built-in Home Assistant agent matches fixed sentences, so extra text would break it."""
    skip = {a.strip() for a in opt("context_skip_agents").split(",") if a.strip()}
    return agent not in skip


async def load_context() -> str:
    if not OPTIONS["context_enabled"] or not opt("context_entity"):
        return ""
    now = time.time()
    if CONTEXT_CACHE["text"] and now - CONTEXT_CACHE["ts"] < CONTEXT_CACHE_S:
        return CONTEXT_CACHE["text"]
    try:
        state = await ha("GET", f"/states/{opt('context_entity')}")
    except HAError as e:
        log.warning("Household context unavailable: %s", e)
        return CONTEXT_CACHE["text"]  # an old copy beats none
    attrs = (state or {}).get("attributes") or {}
    sections = []
    for name in (a.strip() for a in opt("context_attributes").split(",") if a.strip()):
        value = attrs.get(name)
        if value in (None, "", [], {}):
            log.warning("Context attribute %r not found on %s", name, opt("context_entity"))
            continue
        title = name.removesuffix("_text").replace("_", " ").upper()
        sections.append(f"=== {title} ===\n{render(value)}")
    text = "\n\n".join(sections)
    limit = OPTIONS["context_max_chars"]
    if limit > 0 and len(text) > limit:
        log.warning("Household context is %d characters, cutting it to %d", len(text), limit)
        text = text[:limit].rsplit("\n", 1)[0]
    CONTEXT_CACHE.update(ts=now, text=text, facts=str((state or {}).get("state") or ""))
    log.info("Household context loaded: %d characters (%s)", len(text), CONTEXT_CACHE["facts"])
    return text


def with_context(background: str, live: str, message: str) -> str:
    parts = []
    if background:
        who = f"The person talking to you right now is {opt('speaker_name')}. " if opt("speaker_name") else ""
        parts.append(
            "[Background on the household and their friends, loaded automatically. "
            "Use it quietly so you know who people are: names, nicknames, relationships, "
            "jobs, places and music taste. "
            f"{who}"
            "Do not read it back or mention it unless asked.]\n"
            f"{background}\n"
            "[End of background]")
    if live:
        parts.append(
            "[Live info from Home Assistant, current right now. Use it to answer questions about "
            "where people are or what is going on, and prefer it over older details. "
            "Do not read it back unless asked.]\n"
            f"{live}\n"
            "[End of live info]")
    return "\n\n".join(parts + [message])


def context_due(conv_id: str) -> bool:
    last = CONV_SEEN.get(conv_id or "", 0)
    return time.time() - last > CONTEXT_RESEND_S


def remember_conversation(conv_id, live_hash: str = "") -> None:
    if not conv_id:
        return
    now = time.time()
    CONV_SEEN[conv_id] = now
    if live_hash:
        CONV_LIVE[conv_id] = live_hash
    for k in [k for k, t in CONV_SEEN.items() if now - t > 3600]:
        CONV_SEEN.pop(k, None)
        CONV_LIVE.pop(k, None)


# ------------------------------------------------------------- live entities
#
# Entities you pick on the page (Live info button). Their current values are read
# fresh from Home Assistant and sent with your message, but only when they changed
# since the last time the AI was told in that conversation.

LIVE_FILE = DATA_DIR / "live_entities.json"
ENTITY_ID = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")
LIVE_SKIP_ATTRS = {"friendly_name", "icon", "entity_picture", "supported_features", "attribution",
                   "editable", "restored", "device_class", "state_class"}
LIVE_ENTITY_CHARS = 4000
LIVE_TOTAL_CHARS = 15000
LIVE_MAX_ITEMS = 40
DEFAULT_LIVE = [{"entity_id": "sensor.everybodys_locations", "label": "Where everyone is right now",
                 "attributes": ""}]
CONV_LIVE: dict[str, str] = {}  # conversation_id -> hash of the live info the AI last saw


def clean_live_items(raw) -> list[dict]:
    out, seen = [], set()
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        eid = str(it.get("entity_id") or "").strip().lower()
        if not ENTITY_ID.fullmatch(eid) or eid in seen:
            continue
        seen.add(eid)
        out.append({"entity_id": eid,
                    "label": str(it.get("label") or "").strip()[:80],
                    "attributes": str(it.get("attributes") or "").strip()[:300]})
        if len(out) >= LIVE_MAX_ITEMS:
            break
    return out


def load_live_items() -> list[dict]:
    if LIVE_FILE.is_file():
        try:
            return clean_live_items(json.loads(LIVE_FILE.read_text()))
        except ValueError:
            log.warning("Could not read %s", LIVE_FILE)
    return [dict(i) for i in DEFAULT_LIVE]


def save_live_items(items: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_FILE.write_text(json.dumps(items, indent=1))


def format_live(item: dict, state) -> str:
    eid = item["entity_id"]
    attrs = (state or {}).get("attributes") or {}
    label = item.get("label") or attrs.get("friendly_name") or eid
    head = f"{label} ({eid}):"
    if not state:
        return f"{head}\n  not found in Home Assistant"
    wanted = [a.strip() for a in (item.get("attributes") or "").split(",") if a.strip()]
    lines = []
    if wanted:
        for a in wanted:
            if a == "state":
                lines.append(f"  state: {state.get('state')}")
            elif a in attrs:
                lines.append(render({a: attrs[a]}, 1))
    else:
        lines.append(f"  state: {state.get('state')}")
        lines += [render({k: v}, 1) for k, v in attrs.items()
                  if k not in LIVE_SKIP_ATTRS and v not in (None, "", [], {})]
    text = head + "\n" + "\n".join(l for l in lines if l)
    if len(text) > LIVE_ENTITY_CHARS:
        text = text[:LIVE_ENTITY_CHARS].rsplit("\n", 1)[0] + "\n  (cut, too long)"
    return text


async def load_live() -> str:
    items = load_live_items()
    if not items:
        return ""

    async def one(item):
        try:
            return await ha("GET", f"/states/{item['entity_id']}")
        except HAError:
            return None

    states = await asyncio.gather(*(one(i) for i in items))
    text = "\n\n".join(format_live(i, st) for i, st in zip(items, states))
    if len(text) > LIVE_TOTAL_CHARS:
        text = text[:LIVE_TOTAL_CHARS].rsplit("\n", 1)[0]
    return text


# ------------------------------------------------------------- history

def history_dir() -> Path:
    d = DATA_DIR / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chat_path(chat_id: str) -> Path | None:
    return history_dir() / f"{chat_id}.json" if re.fullmatch(r"[a-f0-9]{8,32}", chat_id or "") else None


def load_chat(chat_id: str) -> dict | None:
    p = chat_path(chat_id)
    if p and p.is_file():
        try:
            return json.loads(p.read_text())
        except ValueError:
            return None
    return None


def record_exchange(chat_id: str, agent: str, conversation_id, user: str, reply: str) -> None:
    p = chat_path(chat_id)
    if not p or not OPTIONS["save_history"]:
        return
    chat = load_chat(chat_id) or {"id": chat_id, "title": user[:60], "created": time.time(), "messages": []}
    now = time.time()
    chat.update(updated=now, agent=agent, conversation_id=conversation_id)
    chat["messages"] += [{"role": "me", "text": user, "ts": now}, {"role": "ai", "text": reply, "ts": now}]
    p.write_text(json.dumps(chat))
    files = sorted(history_dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for old in files[max(10, OPTIONS["history_limit"]):]:
        old.unlink(missing_ok=True)


# ------------------------------------------------------------- status

async def compute_status() -> dict:
    states = await ha("GET", "/states")
    by_id = {s["entity_id"]: s for s in states}

    def available(domain: str) -> str:
        return ", ".join(sorted(i for i in by_id if i.startswith(domain + "."))) or "none found"

    def name(entity_id: str) -> str:
        if not entity_id:
            return "not set"
        return by_id.get(entity_id, {}).get("attributes", {}).get("friendly_name") or entity_id

    def listing(domain: str):
        return sorted(({"entity_id": i, "name": name(i)} for i in by_id if i.startswith(domain + ".")),
                      key=lambda x: x["name"].lower())

    problems = []
    for key, domain in (("conversation_agent", "conversation"), ("media_player", "media_player"),
                        ("tts_entity", "tts")):
        value = opt(key)
        if not value:
            if key == "media_player" and OPTIONS["browser_playback"]:
                continue  # "This device" works without a speaker
            problems.append(f"Set “{key}” in the configuration. Available: {available(domain)}")
        elif value not in by_id:
            problems.append(f"“{value}” ({key}) doesn’t exist. Available: {available(domain)}")
    stt = opt("stt_entity")
    if stt and stt not in by_id:
        problems.append(f"“{stt}” (stt_entity) doesn’t exist. Available: {available('stt')}")

    ctx_entity = opt("context_entity")
    if OPTIONS["context_enabled"] and ctx_entity and ctx_entity not in by_id:
        problems.append(f"“{ctx_entity}” (context_entity) doesn’t exist, so the AI won’t know your household. "
                        "Set context_entity to your combined info sensor or turn off context_enabled.")

    return {
        "problems": problems,
        "context": {"enabled": bool(OPTIONS["context_enabled"] and ctx_entity and ctx_entity in by_id),
                    "entity": ctx_entity},
        "context_skip_agents": [a.strip() for a in opt("context_skip_agents").split(",") if a.strip()],
        "version": "2.2.0",
        "media_player": opt("media_player"),
        "conversation_agent": opt("conversation_agent"),
        "speakers": listing("media_player"),
        "agents": listing("conversation"),
        "stt_entity": stt,
        "hands_free": OPTIONS["hands_free"],
        "silence_ms": OPTIONS["silence_ms"],
        "wake_word": opt("wake_word"),
        "stop_words": [w.strip().lower() for w in opt("stop_words").split(",") if w.strip()],
        "sensitivity": opt("sensitivity") if opt("sensitivity") in ("low", "normal", "high") else "normal",
        "chimes": OPTIONS["chimes"],
        "idle_timeout_s": OPTIONS["idle_timeout_s"],
        "browser_playback": OPTIONS["browser_playback"],
        "save_history": OPTIONS["save_history"],
        "language": await language(),
        "names": {"conversation_agent": name(opt("conversation_agent")),
                  "media_player": name(opt("media_player"))},
    }


# ------------------------------------------------------------- routes

async def index(request):
    return web.FileResponse(APP_DIR / "index.html", headers={"Cache-Control": "no-store"})


async def status(request):
    return web.json_response(await compute_status())


async def stt(request):
    entity = opt("stt_entity")
    if not entity:
        raise HAError("No stt_entity is set in the configuration.")
    audio = await request.read()
    lang = await language()
    header = ("format=wav; codec=pcm; sample_rate=16000; bit_rate=16; channel=1; "
              f"language={lang}")
    result = await ha("POST", f"/stt/{entity}", data=audio, headers={"X-Speech-Content": header})
    if not result or result.get("result") != "success":
        raise HAError("Speech recognition failed. Check the language option matches your STT engine.")
    return web.json_response({"text": result.get("text", "")})


async def chat(request):
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        return web.json_response({"error": "Empty message"}, status=400)
    agent = chosen_agent(body)
    sent_id = body.get("conversation_id") or ""
    send_text, eligible, live, live_hash = text, False, "", ""
    # Give the AI the household background on the first message (and again if Home
    # Assistant forgot the conversation after a few quiet minutes). Live entity values
    # go along whenever they differ from what the AI was last told.
    if body.get("context", True) and context_agent_ok(agent):
        eligible = True
        first = context_due(sent_id)
        background = await load_context() if first else ""
        live = await load_live()
        live_hash = hashlib.md5(live.encode()).hexdigest() if live else ""
        if not first and CONV_LIVE.get(sent_id) == live_hash:
            live = ""  # unchanged since the AI last saw it
        if background or live:
            send_text = with_context(background, live, text)
    payload = {"text": send_text, "language": await language(), "agent_id": agent}
    if sent_id:
        payload["conversation_id"] = sent_id
    result = await ha("POST", "/conversation/process", json=payload)
    reply = reply_text(result) or "I didn’t get a reply from the agent."
    conv_id = (result or {}).get("conversation_id")
    if eligible:
        remember_conversation(conv_id, live_hash if live else "")
    log.info("You: %s | Agent: %s", text, reply[:120])
    record_exchange(str(body.get("chat_id") or ""), agent, conv_id, text, reply)
    out = {"text": reply, "conversation_id": conv_id, "audio": None}
    if body.get("speak", True):
        out["audio"] = (await speak(reply, chosen_speakers(request, body)))["audio"]
    return web.json_response(out)


async def wait(request):
    for sp in chosen_speakers(request):
        if sp != "browser":
            await wait_playback(sp)
    return web.json_response({"ok": True})


async def stop(request):
    for sp in chosen_speakers(request):
        if sp != "browser":
            await ha("POST", "/services/media_player/media_stop", json={"entity_id": sp})
    return web.json_response({"ok": True})


async def audio(request):
    item = AUDIO.get(request.match_info["key"])
    if not item or item[0] < time.time():
        raise web.HTTPNotFound()
    return web.Response(body=item[1], content_type=item[2].split(";")[0], headers={"Cache-Control": "no-store"})


async def live_get(request):
    return web.json_response({"items": load_live_items()})


async def live_save(request):
    body = await request.json()
    items = clean_live_items(body.get("items"))
    save_live_items(items)
    CONV_LIVE.clear()  # tell the AI the new list at the next message
    return web.json_response({"items": items})


async def live_preview(request):
    return web.json_response({"text": await load_live() or "Nothing selected yet."})


async def entity_search(request):
    q = request.query.get("q", "").strip().lower()
    if len(q) < 2:
        return web.json_response({"items": []})
    states = await ha("GET", "/states") or []
    out = []
    for st in states:
        eid = st["entity_id"]
        name = (st.get("attributes") or {}).get("friendly_name") or eid
        if q in eid.lower() or q in str(name).lower():
            out.append({"entity_id": eid, "name": str(name), "state": str(st.get("state"))[:40]})
    out.sort(key=lambda x: (not x["entity_id"].lower().startswith(q), x["entity_id"]))
    return web.json_response({"items": out[:25]})


async def history_list(request):
    items = []
    for f in history_dir().glob("*.json"):
        try:
            c = json.loads(f.read_text())
        except ValueError:
            continue
        items.append({"id": c["id"], "title": c.get("title") or "Chat", "updated": c.get("updated", 0),
                      "count": len(c.get("messages", [])) // 2})
    items.sort(key=lambda x: x["updated"], reverse=True)
    return web.json_response({"items": items})


async def history_get(request):
    chat_obj = load_chat(request.match_info["id"])
    if not chat_obj:
        raise web.HTTPNotFound()
    return web.json_response(chat_obj)


async def history_delete(request):
    p = chat_path(request.match_info["id"])
    if p:
        p.unlink(missing_ok=True)
    return web.json_response({"ok": True})


async def history_export(request):
    c = load_chat(request.match_info["id"])
    if not c:
        raise web.HTTPNotFound()
    lines = [f"# {c.get('title') or 'Voice chat'}", ""]
    for m in c["messages"]:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(m["ts"]))
        lines.append(f"**{'You' if m['role'] == 'me' else 'AI'}** ({stamp}): {m['text']}")
        lines.append("")
    return web.Response(text="\n".join(lines), content_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="voice-chat-{c["id"]}.md"'})


@web.middleware
async def guard(request, handler):
    # Ingress traffic is already authenticated by Home Assistant. Anything else
    # (direct HTTPS page, standalone Docker) must send the password on every API call.
    if request.path.startswith("/api/") and request.remote != INGRESS_IP:
        token = request.headers.get("X-Voice-Token") or request.query.get("token", "")
        password = opt("password")
        if not password or not hmac.compare_digest(token.encode(), password.encode()):
            return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        return await handler(request)
    except HAError as e:
        log.warning("%s", e)
        return web.json_response({"error": str(e)}, status=502)
    except web.HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("Unhandled error")
        return web.json_response({"error": f"Unexpected error: {e}"}, status=500)


# ------------------------------------------------------------- startup

def make_ssl_context() -> ssl.SSLContext:
    cert = Path("/ssl") / opt("certfile")
    key = Path("/ssl") / opt("keyfile")
    if cert.is_file() and key.is_file():
        log.info("HTTPS uses certificate %s", cert)
    else:
        cert, key = DATA_DIR / "selfsigned.crt", DATA_DIR / "selfsigned.key"
        if not cert.is_file():
            log.info("No certificate in /ssl, generating a self-signed one")
            subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                 "-keyout", str(key), "-out", str(cert), "-subj", "/CN=voice-chat.local",
                 "-addext", "subjectAltName=DNS:voice-chat.local,DNS:localhost,IP:127.0.0.1"],
                check=True, capture_output=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    return ctx


def ensure_password() -> None:
    """Standalone Docker has no ingress, so a password is always required."""
    if ADDON or OPTIONS["password"]:
        return
    pw_file = DATA_DIR / "password.txt"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not pw_file.is_file():
        pw_file.write_text(secrets.token_urlsafe(12))
    OPTIONS["password"] = pw_file.read_text().strip()
    log.warning("No VC_PASSWORD set. Generated one, saved in %s: %s", pw_file, OPTIONS["password"])


async def main():
    global SESSION
    ensure_password()
    SESSION = ClientSession(timeout=ClientTimeout(total=300))
    app = web.Application(middlewares=[guard], client_max_size=16 * 1024 * 1024)
    app.add_routes([
        web.get("/", index),
        web.get("/api/status", status),
        web.post("/api/stt", stt),
        web.post("/api/chat", chat),
        web.post("/api/wait", wait),
        web.post("/api/stop", stop),
        web.get("/api/audio/{key}", audio),
        web.get("/api/live", live_get),
        web.post("/api/live", live_save),
        web.get("/api/live/preview", live_preview),
        web.get("/api/entities", entity_search),
        web.get("/api/history", history_list),
        web.get("/api/history/{id}", history_get),
        web.delete("/api/history/{id}", history_delete),
        web.get("/api/history/{id}/export", history_export),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8099).start()
    if opt("password"):
        await web.TCPSite(runner, "0.0.0.0", 8443, ssl_context=make_ssl_context()).start()
        log.info("HTTPS page listening on port 8443")
    else:
        log.info("Direct HTTPS page is off. Set a password in Configuration to turn it on.")
    log.info("Voice Chat 2.2 ready (%s mode)", "add-on" if ADDON else "standalone")
    try:
        for problem in (await compute_status())["problems"]:
            log.warning("Config problem: %s", problem)
    except HAError as e:
        log.warning("Startup check skipped: %s", e)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

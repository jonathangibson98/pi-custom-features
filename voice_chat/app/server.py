#!/usr/bin/env python3
"""Voice Chat 2.0 - hands-free voice conversation with a Home Assistant AI agent.

Runs two ways from the same code:
  * Home Assistant add-on (Supervisor token, ingress, /data/options.json)
  * Standalone Docker (HA_URL + HA_TOKEN, settings from VC_* environment variables)

Browser mic -> (HA speech-to-text) -> HA conversation agent -> HA text-to-speech
-> media player(s) and/or the browser itself.
"""
import asyncio
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

    return {
        "problems": problems,
        "version": "2.0.0",
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
    payload = {"text": text, "language": await language(), "agent_id": agent}
    if body.get("conversation_id"):
        payload["conversation_id"] = body["conversation_id"]
    result = await ha("POST", "/conversation/process", json=payload)
    reply = reply_text(result) or "I didn’t get a reply from the agent."
    conv_id = (result or {}).get("conversation_id")
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
    log.info("Voice Chat 2.0 ready (%s mode)", "add-on" if ADDON else "standalone")
    try:
        for problem in (await compute_status())["problems"]:
            log.warning("Config problem: %s", problem)
    except HAError as e:
        log.warning("Startup check skipped: %s", e)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

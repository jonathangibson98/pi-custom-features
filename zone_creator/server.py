import asyncio
import json
import os
import re
import time

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA = "http://supervisor/core"
WS = "ws://supervisor/core/websocket"
UA = "HA-Zone-Creator/1.0 (Home Assistant add-on)"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

try:
    with open("/data/options.json") as f:
        OPTS = json.load(f)
except Exception:
    OPTS = {}

AI_ENTITY = (OPTS.get("ai_task_entity") or "").strip()
DEFAULT_RADIUS = int(OPTS.get("default_radius") or 100)

_geo_lock = asyncio.Lock()
_last_geo = 0.0


async def ws_call(msg):
    """Run one Home Assistant websocket command and return the reply."""
    async with ClientSession(timeout=ClientTimeout(total=20)) as s:
        async with s.ws_connect(WS) as ws:
            await ws.receive_json()  # auth_required
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            r = await ws.receive_json()
            if r.get("type") != "auth_ok":
                raise RuntimeError("Home Assistant auth failed")
            msg["id"] = 1
            await ws.send_json(msg)
            while True:
                m = await ws.receive()
                if m.type != WSMsgType.TEXT:
                    raise RuntimeError("Websocket closed early")
                data = json.loads(m.data)
                if data.get("id") == 1:
                    return data


async def index(request):
    return web.FileResponse("/app/index.html")


async def config(request):
    return web.json_response({"ai": bool(AI_ENTITY), "default_radius": DEFAULT_RADIUS})


async def search(request):
    global _last_geo
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response([])
    # Nominatim policy: max 1 request per second
    async with _geo_lock:
        wait = 1.1 - (time.time() - _last_geo)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_geo = time.time()
        params = {"q": q, "format": "jsonv2", "addressdetails": "1", "limit": "6"}
        try:
            async with ClientSession(timeout=ClientTimeout(total=15)) as s:
                async with s.get(
                    "https://nominatim.openstreetmap.org/search",
                    params=params,
                    headers={"User-Agent": UA},
                ) as r:
                    data = await r.json()
        except Exception as e:
            return web.json_response({"error": f"Search failed: {e}"}, status=502)
    out = [
        {
            "display_name": d.get("display_name", ""),
            "name": d.get("name", ""),
            "category": d.get("category", ""),
            "type": d.get("type", ""),
            "lat": float(d["lat"]),
            "lon": float(d["lon"]),
        }
        for d in data
    ]
    return web.json_response(out)


async def suggest(request):
    if not AI_ENTITY:
        return web.json_response({"error": "AI not configured"}, status=400)
    d = await request.json()
    try:
        r = await ws_call({"type": "zone/list"})
        existing = [f'{z["name"]} ({z.get("icon") or "no icon"})' for z in r.get("result", [])]
    except Exception:
        existing = []

    prompt = (
        "You help name Home Assistant zones.\n"
        f"Place: {d.get('display_name', '')}\n"
        f"OSM name: {d.get('name', '')}\n"
        f"OSM category/type: {d.get('category', '')}/{d.get('type', '')}\n"
        f"Existing zones (match this naming style): {', '.join(existing) or 'none'}\n\n"
        "Pick a SHORT zone name (1-3 words, what a person would actually call this place, "
        "e.g. 'Work', 'Gym', 'Mom's House', 'Walmart') and ONE common Material Design Icons "
        "icon in the form mdi:icon-name (e.g. mdi:home, mdi:dumbbell, mdi:cart, mdi:briefcase, "
        "mdi:silverware-fork-knife). Reply with ONLY this JSON, nothing else:\n"
        '{"name": "...", "icon": "mdi:..."}'
    )
    body = {
        "entity_id": AI_ENTITY,
        "task_name": "zone naming",
        "instructions": prompt,
    }
    try:
        async with ClientSession(timeout=ClientTimeout(total=90)) as s:
            async with s.post(
                f"{HA}/api/services/ai_task/generate_data?return_response",
                headers=AUTH,
                json=body,
            ) as resp:
                if resp.status != 200:
                    return web.json_response(
                        {"error": f"AI call failed ({resp.status}): {(await resp.text())[:200]}"},
                        status=502,
                    )
                res = await resp.json()
        text = res.get("service_response", {}).get("data", "")
        if not isinstance(text, str):
            text = json.dumps(text)
        m = re.search(r"\{.*?\}", text, re.S)
        parsed = json.loads(m.group(0))
        name = str(parsed.get("name", "")).strip()[:60]
        icon = str(parsed.get("icon", "")).strip()
        if not re.fullmatch(r"mdi:[a-z0-9-]+", icon):
            icon = ""
        return web.json_response({"name": name, "icon": icon})
    except Exception as e:
        return web.json_response({"error": f"Couldn't read AI answer: {e}"}, status=502)


async def create(request):
    d = await request.json()
    try:
        name = str(d["name"]).strip()
        payload = {
            "type": "zone/create",
            "name": name,
            "latitude": float(d["latitude"]),
            "longitude": float(d["longitude"]),
            "radius": float(d.get("radius") or DEFAULT_RADIUS),
            "passive": bool(d.get("passive", False)),
        }
        if d.get("icon"):
            payload["icon"] = str(d["icon"]).strip()
        if not name:
            raise ValueError("Name is required")
    except Exception as e:
        return web.json_response({"error": f"Bad input: {e}"}, status=400)
    try:
        r = await ws_call(payload)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)
    if not r.get("success"):
        return web.json_response({"error": r.get("error", {}).get("message", "HA refused it")}, status=400)
    return web.json_response({"ok": True, "zone": r.get("result")})


app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/api/config", config)
app.router.add_get("/api/search", search)
app.router.add_post("/api/suggest", suggest)
app.router.add_post("/api/create", create)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8099)

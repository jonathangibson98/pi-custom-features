#!/usr/bin/env python3
"""Party Lights: music-synced lights, light shows and party games for Home Assistant, in one add-on.

- Music sync: lights take the colors of the album art of whatever is playing (was the media_lights_sync AppDaemon app)
- Album art sensor: brightness, main color, palette and a readable text color for the current art (was art_color)
- Light shows: color loop, rainbow wave, disco, chase, pulse to a beat, breathe, strobe, fire, police, lightning,
  sparkle, static, with color themes (party, holidays, team colors, the album art, your own, or AI-made)
- Party extras: power hour, shot caller, New Year style countdown, birthday blast, the drop, an AI hype MC
- Every control is also a Home Assistant entity over MQTT (switch, select, numbers, buttons, sensors)

Everything is set up on the web page; settings live in /data/settings.json.
"""
import asyncio
import colorsys
import io
import json
import logging
import os
import random
import re
import time
import urllib.request
from datetime import datetime, timedelta

import aiohttp
from aiohttp import web
from PIL import Image

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

import ha_ai

DATA = os.environ.get("DATA_DIR", "/data")
WWW = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(DATA, "settings.json")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = os.environ.get("HA_API", "http://supervisor/core/api")
WS = os.environ.get("HA_WS", "ws://supervisor/core/websocket")
BASE = "party_lights"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("party")

try:
    OPTS = json.load(open(os.path.join(DATA, "options.json")))
except Exception:  # noqa: BLE001
    OPTS = {}

THEMES = {
    "party": ["#ff2bd6", "#7b2cff", "#00e5ff", "#ffe600", "#ff6a00"],
    "rainbow": ["#ff0000", "#ff8000", "#ffff00", "#00ff00", "#00c0ff", "#4000ff", "#c000ff"],
    "neon": ["#39ff14", "#ff073a", "#00f0ff", "#fe019a", "#ffd300"],
    "chill": ["#3a86ff", "#8338ec", "#06d6a0", "#118ab2"],
    "sunset": ["#ff4e50", "#fc913a", "#f9d423", "#ff2e63", "#a8329a"],
    "ocean": ["#0077b6", "#00b4d8", "#90e0ef", "#023e8a", "#48cae4"],
    "christmas": ["#ff0000", "#00c000", "#ffffff", "#ffd700"],
    "halloween": ["#ff6a00", "#7b00ff", "#39ff14", "#ff3d00"],
    "july4": ["#ff0000", "#ffffff", "#0040ff"],
    "valentine": ["#ff1a75", "#ff4d4d", "#ff99cc", "#cc0066"],
    "stpatricks": ["#00b140", "#7cfc00", "#ffd700", "#ffffff"],
    "newyear": ["#ffd700", "#c0c0c0", "#ffffff", "#ff2bd6"],
    "birthday": ["#ff4fd8", "#ffd23f", "#3ec1ff", "#7cff6b", "#ff8a3d"],
    "fire": ["#ff3000", "#ff6a00", "#ff9a00", "#ffbf00"],
    "police": ["#ff0000", "#0030ff"],
}
THEME_NAMES = {"party": "Party", "rainbow": "Rainbow", "neon": "Neon", "chill": "Chill", "sunset": "Sunset", "ocean": "Ocean",
               "christmas": "Christmas", "halloween": "Halloween", "july4": "4th of July", "valentine": "Valentine's",
               "stpatricks": "St. Patrick's", "newyear": "New Year's", "birthday": "Birthday", "album": "Album art",
               "team": "Team colors", "custom": "My colors", "ai": "AI theme"}
EFFECTS = {
    "off": "Off", "music": "Music sync", "static": "Static colors", "color_loop": "Color loop", "rainbow_wave": "Rainbow wave",
    "disco": "Disco", "chase": "Chase", "pulse": "Pulse to the beat", "breathe": "Breathe", "strobe": "Strobe",
    "sparkle": "Sparkle", "fire": "Fire", "police": "Police", "lightning": "Lightning storm",
}
DEFAULTS = {
    "lights": [],                    # every light the party uses (light shows, extras)
    "music": {"media_players": [], "lights": [], "saturate": True, "brightness": 0, "transition": 2,
              "same_color": False, "condition_entity": "", "condition_state": "", "always": False},
    "art": {"enabled": True, "media_player": "", "entity_id": "sensor.music_art_brightness", "name": "Music Art Brightness"},
    "show": {"effect": "off", "theme": "party", "speed": 5, "brightness": 80, "custom": ["#ff2bd6", "#00e5ff", "#ffe600"],
             "bpm": 120, "team_sensor": ""},
    "ai_theme": {"name": "", "colors": [], "note": ""},
    "restore": True,
    "announce": {"tts": "", "speakers": [], "language": ""},
    "people": {"exclude": []},
    "power_hour": {"minutes": 60, "phrase": "Drink!", "announce": True, "next_track": "", "theme": "party"},
    "shots": {"min_minutes": 10, "max_minutes": 25, "phrases": ["{name}, take a shot!", "{name}, it's your turn. Drink up!",
                                                                    "Shots for {name}!", "Everybody point at {name}. Drink!"]},
    "countdown": {"time": "00:00", "message": "Happy New Year!", "theme": "newyear", "announce_minute": True},
    "hype": {"every_minutes": 15, "style": "party DJ hyping the crowd"},
    "birthday": {"name": "", "message": "Happy birthday {name}! Make some noise!"},
    "speed_limit": 0.5,              # fastest seconds between light commands (protects slow bulbs)
}


def deep_merge(base, over):
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings():
    try:
        return deep_merge(DEFAULTS, json.load(open(SETTINGS)))
    except Exception:  # noqa: BLE001
        return json.loads(json.dumps(DEFAULTS))


def save_settings(s):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, SETTINGS)


def hex_rgb(h):
    h = str(h).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return [255, 255, 255]


def rgb_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c[:3])


def saturate(c):
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in c))
    r, g, b = colorsys.hls_to_rgb(h, 0.5, max(0.65, s))
    return [int(r * 255), int(g * 255), int(b * 255)]


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


# ---------------------------------------------------------------- Home Assistant
class HA:
    def __init__(self):
        self.http = None
        self.states = {}
        self.listeners = []  # fn(entity_id, old, new)
        self.ok = False

    async def start(self):
        self.http = aiohttp.ClientSession(headers={"Authorization": "Bearer " + TOKEN})
        asyncio.create_task(self.ws_loop())

    async def call(self, domain, service, data, response=False):
        try:
            async with self.http.post("%s/services/%s/%s%s" % (API, domain, service, "?return_response" if response else ""),
                                      json=data, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status >= 400:
                    log.warning("%s.%s failed (%d): %s", domain, service, r.status, (await r.text())[:200])
                    return None
                return await r.json(content_type=None) if response else True
        except Exception as e:  # noqa: BLE001
            log.warning("%s.%s failed: %s", domain, service, e)
            return None

    async def fetch_states(self):
        try:
            async with self.http.get(API + "/states", timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    self.states = {s["entity_id"]: s for s in await r.json()}
                    self.ok = True
        except Exception as e:  # noqa: BLE001
            log.warning("Couldn't read states: %s", e)

    async def get_bytes(self, url):
        if url.startswith("/"):
            url = API[:-4] + url
        async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            r.raise_for_status()
            return await r.read()

    async def ws_loop(self):
        while True:
            try:
                await self.fetch_states()
                async with self.http.ws_connect(WS, heartbeat=30) as ws:
                    await ws.receive_json()
                    await ws.send_json({"type": "auth", "access_token": TOKEN})
                    if (await ws.receive_json()).get("type") != "auth_ok":
                        raise RuntimeError("websocket login refused")
                    await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
                    log.info("Connected to Home Assistant")
                    async for m in ws:
                        if m.type != aiohttp.WSMsgType.TEXT:
                            break
                        d = json.loads(m.data)
                        if d.get("type") != "event":
                            continue
                        ev = d["event"]["data"]
                        eid, old, new = ev.get("entity_id"), ev.get("old_state"), ev.get("new_state")
                        if new:
                            self.states[eid] = new
                        else:
                            self.states.pop(eid, None)
                        for fn in self.listeners:
                            try:
                                fn(eid, old, new)
                            except Exception as e:  # noqa: BLE001
                                log.warning("Listener failed: %s", e)
            except Exception as e:  # noqa: BLE001
                self.ok = False
                log.warning("Home Assistant connection lost (%s), retrying in 10 s", e)
            await asyncio.sleep(10)

    def state(self, eid):
        return (self.states.get(eid) or {}).get("state")

    def attr(self, eid, a, default=None):
        return ((self.states.get(eid) or {}).get("attributes") or {}).get(a, default)


ha = HA()


# ---------------------------------------------------------------- the party
class Party:
    def __init__(self):
        self.s = load_settings()
        self.on = False
        self.loop = None
        self.show_task = None
        self.extras = {}             # name -> task
        self.extra_info = {}         # name -> text for the page
        self.art = {"palette": [], "brightness": None, "color": None, "text_color": None, "url": None, "title": ""}
        self.last_art_url = {}
        self.status = "Ready"
        self.events = []             # recent things that happened, for the page
        self.mq = None
        self.last_cmd = 0.0

    # ---- helpers
    def note(self, text):
        log.info(text)
        self.events.insert(0, {"t": time.time(), "text": text})
        del self.events[40:]

    def lights(self):
        return [x for x in self.s["lights"] if x.startswith("light.")]

    def palette(self, theme=None):
        theme = theme or self.s["show"]["theme"]
        if theme == "album" and self.art["palette"]:
            return [rgb_hex(saturate(hex_rgb(c))) for c in self.art["palette"]]
        if theme == "custom" and self.s["show"]["custom"]:
            return self.s["show"]["custom"]
        if theme == "ai" and self.s["ai_theme"]["colors"]:
            return self.s["ai_theme"]["colors"]
        if theme == "team":
            sens = self.s["show"].get("team_sensor") or ""
            cols = [c for c in (ha.attr(sens, "team_colors") or []) + (ha.attr(sens, "opponent_colors") or []) if c]
            if cols:
                return ["#" + str(c).lstrip("#") for c in cols]
        return THEMES.get(theme) or THEMES["party"]

    def bri(self, pct=None):
        return max(1, min(255, round(255 * (pct if pct is not None else self.s["show"]["brightness"]) / 100)))

    def step_seconds(self):
        sp = max(1, min(10, int(self.s["show"]["speed"])))
        return max(float(self.s.get("speed_limit") or 0.5), 6.0 * (0.62 ** (sp - 1)))

    async def light(self, entities, rgb=None, brightness=None, transition=None, off=False, flash=None):
        if not entities:
            return
        data = {"entity_id": entities if isinstance(entities, list) else [entities]}
        if transition is not None:
            data["transition"] = transition
        if off:
            await ha.call("light", "turn_off", data)
            return
        if rgb is not None:
            data["rgb_color"] = list(rgb)
        if brightness is not None:
            data["brightness"] = int(brightness)
        if flash:
            data["flash"] = flash
        await ha.call("light", "turn_on", data)

    async def say(self, text):
        a = self.s["announce"]
        if not (a.get("tts") and a.get("speakers")):
            self.note("Would say (set up announcements to hear it): " + text)
            return
        data = {"entity_id": a["tts"], "media_player_entity_id": a["speakers"], "message": text, "cache": False}
        if a.get("language"):
            data["language"] = a["language"]
        await ha.call("tts", "speak", data)
        self.note("Said: " + text)

    def people_home(self):
        ex = {x.lower() for x in self.s["people"]["exclude"]}
        out = []
        for eid, st in ha.states.items():
            if eid.startswith("person.") and st.get("state") == "home":
                name = (st.get("attributes") or {}).get("friendly_name") or eid[7:]
                if name.lower() not in ex and eid[7:].lower() not in ex:
                    out.append(name)
        return out

    # ---- party mode on / off
    async def set_on(self, on):
        if on == self.on:
            return
        self.on = on
        lights = sorted(set(self.lights() + self.s["music"]["lights"]))
        if on:
            if self.s["restore"] and lights:
                await ha.call("scene", "create", {"scene_id": "party_lights_before", "snapshot_entities": lights})
            self.note("Party mode on 🎉")
            if self.s["show"]["effect"] == "off":
                self.s["show"]["effect"] = "music" if self.s["music"]["media_players"] else "disco"
            await self.start_show()
        else:
            for name in list(self.extras):
                self.stop_extra(name)
            await self.stop_show()
            if self.s["restore"] and lights:
                await ha.call("scene", "turn_on", {"entity_id": "scene.party_lights_before", "transition": 2})
            self.note("Party mode off, lights put back")
        self.publish()

    # ---- light shows
    async def stop_show(self):
        if self.show_task:
            self.show_task.cancel()
            self.show_task = None

    async def start_show(self):
        await self.stop_show()
        eff = self.s["show"]["effect"]
        if not self.on or eff in ("off", "music"):
            if eff == "music" and self.on:
                await self.music_now()
            self.publish()
            return
        self.show_task = asyncio.create_task(self.run_show(eff))
        self.publish()

    async def run_show(self, eff):
        L = self.lights()
        if not L:
            self.note("Pick the party lights first (Setup)")
            return
        n, i, t0 = len(L), 0, time.time()
        try:
            while True:
                pal = [hex_rgb(c) for c in self.palette()]
                step = self.step_seconds()
                b = self.bri()
                if eff == "static":
                    for k, e in enumerate(L):
                        await self.light(e, pal[k % len(pal)], b, transition=1)
                    return
                if eff == "color_loop":
                    h = (time.time() - t0) / (step * 12) % 1
                    await self.light(L, [int(v * 255) for v in colorsys.hsv_to_rgb(h, 1, 1)], b, transition=step)
                elif eff == "rainbow_wave":
                    base = (time.time() - t0) / (step * 12)
                    for k, e in enumerate(L):
                        await self.light(e, [int(v * 255) for v in colorsys.hsv_to_rgb((base + k / n) % 1, 1, 1)], b, transition=step)
                elif eff == "disco":
                    for e in L:
                        await self.light(e, random.choice(pal), b, transition=min(0.3, step / 2))
                elif eff == "chase":
                    for k, e in enumerate(L):
                        await self.light(e, pal[(k + i) % len(pal)], b, transition=step * 0.6)
                elif eff == "pulse":
                    step = max(float(self.s.get("speed_limit") or 0.5), 60.0 / max(40, min(200, int(self.s["show"]["bpm"]))))
                    c = pal[(i // 2) % len(pal)]
                    await self.light(L, c, b if i % 2 == 0 else max(1, b // 6), transition=0)
                elif eff == "breathe":
                    c = pal[(i // 2) % len(pal)]
                    step = max(step, 2.5)
                    await self.light(L, c, b if i % 2 == 0 else max(1, b // 10), transition=step)
                elif eff == "strobe":
                    step = max(float(self.s.get("speed_limit") or 0.5), 0.5)
                    if i % 2 == 0:
                        await self.light(L, [255, 255, 255], 255, transition=0)
                    else:
                        await self.light(L, off=True, transition=0)
                elif eff == "sparkle":
                    base = pal[(i // 8) % len(pal)]
                    for e in L:
                        if random.random() < 0.3:
                            await self.light(e, [255, 255, 255], 255, transition=0)
                        else:
                            await self.light(e, base, max(1, b // 3), transition=step / 2)
                elif eff == "fire":
                    fire = [hex_rgb(c) for c in THEMES["fire"]]
                    for e in L:
                        await self.light(e, random.choice(fire), int(b * random.uniform(0.35, 1)), transition=step / 2)
                    step = max(float(self.s.get("speed_limit") or 0.5), step / 2)
                elif eff == "police":
                    half = max(1, n // 2)
                    a, c = ([255, 0, 0], [0, 48, 255]) if i % 2 == 0 else ([0, 48, 255], [255, 0, 0])
                    await self.light(L[:half], a, 255, transition=0)
                    if L[half:]:
                        await self.light(L[half:], c, 255, transition=0)
                    step = max(float(self.s.get("speed_limit") or 0.5), step / 2)
                elif eff == "lightning":
                    if random.random() < 0.25:
                        await self.light(L, [230, 240, 255], 255, transition=0)
                        await asyncio.sleep(0.25)
                    await self.light(L, [20, 30, 90], max(1, b // 8), transition=0.4)
                    step = random.uniform(1.0, 5.0)
                i += 1
                await asyncio.sleep(step)
        except asyncio.CancelledError:
            pass

    async def flash(self, theme=None, times=3):
        L = sorted(set(self.lights() + self.s["music"]["lights"]))
        pal = [hex_rgb(c) for c in self.palette(theme)]
        was = self.show_task is not None
        await self.stop_show()
        for k in range(times):
            await self.light(L, pal[k % len(pal)], 255, transition=0)
            await asyncio.sleep(0.6)
            await self.light(L, pal[(k + 1) % len(pal)], 40, transition=0)
            await asyncio.sleep(0.6)
        if was or self.s["show"]["effect"] == "music":
            await self.start_show()

    # ---- music sync + album art
    def on_state(self, eid, old, new):
        m = self.s["music"]
        if eid in m["media_players"] or eid == self.s["art"]["media_player"]:
            a = (new or {}).get("attributes") or {}
            url = a.get("entity_picture_local") or a.get("entity_picture")
            if url and url != self.last_art_url.get(eid):
                self.last_art_url[eid] = url
                asyncio.ensure_future(self.new_art(eid, url, a))  # listeners run on the event loop
        if eid == m.get("condition_entity") and m.get("condition_state") and old and new and old.get("state") != new.get("state"):
            if self.music_allowed():
                asyncio.ensure_future(self.music_now())

    def music_allowed(self):
        m = self.s["music"]
        if m.get("condition_entity") and m.get("condition_state"):
            if str(ha.state(m["condition_entity"])) != str(m["condition_state"]):
                return False
            return True  # the mode helper says so, even without party mode
        return m.get("always") or (self.on and self.s["show"]["effect"] == "music")

    async def new_art(self, player, url, attrs):
        try:
            raw = await ha.get_bytes(url)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((200, 200))
        except Exception as e:  # noqa: BLE001
            log.warning("Couldn't read the album art from %s: %s", player, e)
            return
        n = max(5, len(self.s["music"]["lights"]))
        pal = im.quantize(colors=n, method=Image.Quantize.FASTOCTREE).getpalette()[:n * 3]
        colors = [pal[i:i + 3] for i in range(0, len(pal), 3)]
        small = im.resize((32, 32))
        px = list(small.getdata())
        bright = round(sum(lum(p) for p in px) / len(px))
        counts = {}
        for p in px:
            k = tuple(v // 32 for v in p)
            counts[k] = counts.get(k, 0) + 1
        main = max(counts, key=counts.get)
        main_rgb = [v * 32 + 16 for v in main]
        self.art = {"palette": [rgb_hex(c) for c in colors], "brightness": bright, "color": rgb_hex(main_rgb),
                    "text_color": "#000000" if bright > 140 else "#ffffff", "url": url, "player": player,
                    "title": " - ".join(x for x in (attrs.get("media_artist"), attrs.get("media_title")) if x)}
        self.publish_art()
        if player in self.s["music"]["media_players"] and self.music_allowed():
            await self.apply_music(colors)
        if self.s["show"]["theme"] == "album" and self.show_task:
            pass  # the running show reads the new palette on its next step

    async def apply_music(self, colors):
        m = self.s["music"]
        L = m["lights"] or self.lights()
        if not L:
            return
        usable = [c for c in colors if lum(c) > 18] or colors
        if m["saturate"]:
            usable = [saturate(c) for c in usable]
        b = self.bri(m["brightness"]) if m.get("brightness") else None
        tr = float(m.get("transition") or 0)
        if m.get("same_color"):
            await self.light(L, usable[0], b, transition=tr)
        else:
            for k, e in enumerate(L):
                await self.light(e, usable[k % len(usable)], b, transition=tr)

    async def music_now(self):
        for p in self.s["music"]["media_players"]:
            a = ha.attr(p, "entity_picture_local") or ha.attr(p, "entity_picture")
            if a:
                self.last_art_url.pop(p, None)
                await self.new_art(p, a, (ha.states.get(p) or {}).get("attributes") or {})
                return

    # ---- extras
    def stop_extra(self, name):
        t = self.extras.pop(name, None)
        if t:
            t.cancel()
        self.extra_info.pop(name, None)
        self.publish()

    def start_extra(self, name, coro):
        self.stop_extra(name)
        self.extras[name] = asyncio.create_task(self._guard(name, coro))
        self.publish()

    async def _guard(self, name, coro):
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            self.note("%s stopped: %s" % (name, e))
        finally:
            if self.extras.get(name) is asyncio.current_task():
                self.extras.pop(name, None)
                self.extra_info.pop(name, None)
                self.publish()

    async def power_hour(self):
        ph = self.s["power_hour"]
        total = max(1, int(ph["minutes"]))
        self.note("Power hour started: %d minutes" % total)
        if ph["announce"]:
            await self.say("Power hour starts now! %d minutes, %d shots. Let's go!" % (total, total))
        for k in range(1, total + 1):
            for left in range(60, 0, -1):
                self.extra_info["power_hour"] = "Shot %d of %d in %d s" % (k, total, left)
                if left % 10 == 0:
                    self.publish()
                await asyncio.sleep(1)
            if ph.get("next_track"):
                await ha.call("media_player", "media_next_track", {"entity_id": ph["next_track"]})
            asyncio.ensure_future(self.flash(ph.get("theme"), 2))
            if ph["announce"]:
                await self.say(("Last one! " if k == total else "") + ph["phrase"])
        await self.say("Power hour complete! Legends, all of you.")
        self.note("Power hour done")

    async def shot_caller(self):
        sh = self.s["shots"]
        while True:
            wait = random.uniform(max(1, sh["min_minutes"]), max(sh["min_minutes"], sh["max_minutes"])) * 60
            until = time.time() + wait
            while time.time() < until:
                self.extra_info["shots"] = "Next call in %d min" % max(1, round((until - time.time()) / 60))
                self.publish()
                await asyncio.sleep(min(30, max(1, until - time.time())))
            people = self.people_home() or ["Everybody"]
            who = random.choice(people)
            asyncio.ensure_future(self.flash(None, 2))
            await self.say(random.choice(sh["phrases"] or ["{name}, take a shot!"]).replace("{name}", who))

    async def countdown(self):
        cd = self.s["countdown"]
        hh, mm = (int(x) for x in (cd["time"] or "00:00").split(":")[:2])
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        said_minute = False
        while True:
            left = (target - datetime.now()).total_seconds()
            self.extra_info["countdown"] = "%d:%02d:%02d to go" % (left // 3600, left % 3600 // 60, left % 60) if left > 0 else "Now!"
            if left <= 60 and not said_minute and cd.get("announce_minute"):
                said_minute = True
                asyncio.ensure_future(self.say("One minute to go!"))
            if left <= 10:
                break
            if int(left) % 15 == 0:
                self.publish()
            await asyncio.sleep(1)
        await self.stop_show()
        L = sorted(set(self.lights() + self.s["music"]["lights"]))
        for s_left in range(10, 0, -1):
            self.extra_info["countdown"] = str(s_left)
            self.publish()
            await self.light(L, [255, int(255 * s_left / 10), 0], self.bri(100 - s_left * 8), transition=0)
            await asyncio.sleep(max(0, (target - datetime.now()).total_seconds() - (s_left - 1)))
        self.extra_info["countdown"] = "🎉"
        asyncio.ensure_future(self.say(cd["message"]))
        pal = [hex_rgb(c) for c in self.palette(cd.get("theme") or "newyear")]
        end = time.time() + 45
        while time.time() < end:
            for e in L:
                await self.light(e, random.choice(pal), 255, transition=0)
            await asyncio.sleep(max(0.5, float(self.s.get("speed_limit") or 0.5)))
        self.note("Countdown finished")
        await self.start_show()

    async def hype_mc(self):
        h = self.s["hype"]
        while True:
            await asyncio.sleep(max(3, int(h["every_minutes"])) * 60)
            song = self.art.get("title") or ""
            people = self.people_home()
            try:
                line = await asyncio.get_running_loop().run_in_executor(None, ha_ai.ask,
                    "You are a %s at a house party. Write ONE short line (under 25 words) to say over the speakers right now. "
                    "Now playing: %s. People here: %s. Be fun, no swearing, no made-up facts about the people. Plain text only."
                    % (h["style"], song or "unknown", ", ".join(people) or "unknown"), OPTS.get("ai_task_entity") or "", "Party hype")
            except Exception as e:  # noqa: BLE001
                self.note("Hype MC: " + str(e))
                continue
            await self.say(line.strip().strip('"'))

    async def birthday(self):
        b = self.s["birthday"]
        name = b.get("name") or "the birthday star"
        await self.stop_show()
        L = sorted(set(self.lights() + self.s["music"]["lights"]))
        asyncio.ensure_future(self.say(b["message"].replace("{name}", name)))
        pal = [hex_rgb(c) for c in THEMES["birthday"]]
        end, i = time.time() + 30, 0
        while time.time() < end:
            for k, e in enumerate(L):
                await self.light(e, pal[(k + i) % len(pal)], 255, transition=0.3)
            i += 1
            await asyncio.sleep(max(0.6, float(self.s.get("speed_limit") or 0.5)))
        await self.start_show()

    async def drop(self):
        """Build-up then drop: lights dim and speed up, a beat of darkness, then go wild."""
        await self.stop_show()
        L = sorted(set(self.lights() + self.s["music"]["lights"]))
        pal = [hex_rgb(c) for c in self.palette()]
        delay = 1.2
        for k in range(10):
            await self.light(L, pal[k % len(pal)], int(40 + k * 20), transition=0)
            await asyncio.sleep(max(float(self.s.get("speed_limit") or 0.5), delay))
            delay *= 0.8
        await self.light(L, off=True, transition=0)
        await asyncio.sleep(1)
        end = time.time() + 20
        while time.time() < end:
            for e in L:
                await self.light(e, random.choice(pal), 255, transition=0)
            await asyncio.sleep(max(0.5, float(self.s.get("speed_limit") or 0.5)))
        await self.start_show()

    async def blackout(self):
        await self.stop_show()
        await self.light(sorted(set(self.lights() + self.s["music"]["lights"])), off=True, transition=0)
        self.note("Blackout")

    async def ai_theme(self, vibe):
        out = await asyncio.get_running_loop().run_in_executor(None, ha_ai.ask_json,
            "Design party lighting for this vibe: %s. Reply ONLY with JSON {\"name\": \"short name\", \"colors\": [\"#rrggbb\", ...4 to 6 "
            "saturated colors that look good on RGB smart bulbs, no near-white or near-black], \"effect\": one of %s, \"speed\": 1-10, "
            "\"note\": \"one short sentence\"}." % (vibe, ", ".join(k for k in EFFECTS if k not in ("off", "music", "strobe"))),
            OPTS.get("ai_task_entity") or "", "Party theme")
        cols = [c for c in out.get("colors", []) if re.fullmatch(r"#[0-9a-fA-F]{6}", str(c))][:8]
        if not cols:
            raise RuntimeError("The AI didn't send colors back. Try again.")
        self.s["ai_theme"] = {"name": str(out.get("name") or vibe)[:40], "colors": cols, "note": str(out.get("note") or "")[:200]}
        self.s["show"]["theme"] = "ai"
        if out.get("effect") in EFFECTS and out["effect"] not in ("off", "music", "strobe"):
            self.s["show"]["effect"] = out["effect"]
        try:
            self.s["show"]["speed"] = max(1, min(10, int(out.get("speed") or self.s["show"]["speed"])))
        except (TypeError, ValueError):
            pass
        save_settings(self.s)
        if self.on:
            await self.start_show()
        self.note("AI theme: %s" % self.s["ai_theme"]["name"])
        return self.s["ai_theme"]

    # ---- MQTT entities
    def device(self):
        return {"identifiers": [BASE], "name": "Party Lights", "manufacturer": "Party Lights add-on", "model": "Party controller"}

    def mqtt_start(self):
        if mqtt is None:
            return
        host, port, user, pw = (OPTS.get("mqtt_host") or "").strip(), int(OPTS.get("mqtt_port") or 1883), OPTS.get("mqtt_username") or "", OPTS.get("mqtt_password") or ""
        if not host:
            try:
                req = urllib.request.Request("http://supervisor/services/mqtt", headers={"Authorization": "Bearer " + TOKEN})
                d = json.load(urllib.request.urlopen(req, timeout=10)).get("data") or {}
                host, port, user, pw = d.get("host"), int(d.get("port") or 1883), d.get("username") or "", d.get("password") or ""
            except Exception as e:  # noqa: BLE001
                log.info("No MQTT broker found (%s): the page still works, the Home Assistant controls don't", e)
                return
        try:
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="party_lights")
        except AttributeError:
            c = mqtt.Client(client_id="party_lights")
        if user:
            c.username_pw_set(user, pw)
        c.will_set(BASE + "/status", "offline", retain=True)
        c.on_connect = lambda cl, *a: self.loop.call_soon_threadsafe(self.mqtt_connected)
        c.on_message = lambda cl, u, msg: asyncio.run_coroutine_threadsafe(self.mqtt_cmd(msg.topic, msg.payload.decode("utf-8", "replace")), self.loop)
        c.connect_async(host, port, 60)
        c.loop_start()
        self.mq = c

    def mqtt_connected(self):
        c, dev, base = self.mq, self.device(), BASE
        av = {"availability_topic": base + "/status", "device": dev}
        ents = [
            ("switch", "party_mode", {"name": "Party mode", "icon": "mdi:party-popper", "command_topic": base + "/party/set", "state_topic": base + "/party/state"}),
            ("select", "party_effect", {"name": "Party effect", "icon": "mdi:led-strip-variant", "options": list(EFFECTS.values()), "command_topic": base + "/effect/set", "state_topic": base + "/effect/state"}),
            ("select", "party_theme", {"name": "Party colors", "icon": "mdi:palette", "options": list(THEME_NAMES.values()), "command_topic": base + "/theme/set", "state_topic": base + "/theme/state"}),
            ("number", "party_speed", {"name": "Party speed", "icon": "mdi:speedometer", "min": 1, "max": 10, "step": 1, "command_topic": base + "/speed/set", "state_topic": base + "/speed/state"}),
            ("number", "party_brightness", {"name": "Party brightness", "icon": "mdi:brightness-6", "min": 5, "max": 100, "step": 5, "unit_of_measurement": "%", "command_topic": base + "/brightness/set", "state_topic": base + "/brightness/state"}),
            ("number", "party_bpm", {"name": "Party beat", "icon": "mdi:metronome", "min": 60, "max": 180, "step": 1, "unit_of_measurement": "BPM", "command_topic": base + "/bpm/set", "state_topic": base + "/bpm/state"}),
            ("switch", "party_power_hour", {"name": "Power hour", "icon": "mdi:beer", "command_topic": base + "/power_hour/set", "state_topic": base + "/power_hour/state"}),
            ("switch", "party_shot_caller", {"name": "Shot caller", "icon": "mdi:glass-wine", "command_topic": base + "/shots/set", "state_topic": base + "/shots/state"}),
            ("switch", "party_countdown", {"name": "Party countdown", "icon": "mdi:timer-sand", "command_topic": base + "/countdown/set", "state_topic": base + "/countdown/state"}),
            ("switch", "party_hype_mc", {"name": "AI hype MC", "icon": "mdi:microphone-variant", "command_topic": base + "/hype/set", "state_topic": base + "/hype/state"}),
            ("button", "party_flash", {"name": "Party flash", "icon": "mdi:flash", "command_topic": base + "/flash/press"}),
            ("button", "party_drop", {"name": "Drop the beat", "icon": "mdi:arrow-collapse-down", "command_topic": base + "/drop/press"}),
            ("button", "party_birthday", {"name": "Birthday blast", "icon": "mdi:cake-variant", "command_topic": base + "/birthday/press"}),
            ("button", "party_blackout", {"name": "Blackout", "icon": "mdi:lightbulb-off", "command_topic": base + "/blackout/press"}),
            ("sensor", "party_status", {"name": "Party status", "icon": "mdi:party-popper", "state_topic": base + "/status_text", "json_attributes_topic": base + "/status_attrs"}),
        ]
        for kind, oid, cfg in ents:
            c.publish("homeassistant/%s/%s/%s/config" % (kind, base, oid),
                      json.dumps(dict(cfg, unique_id=base + "_" + oid, default_entity_id="%s.%s" % (kind, oid), **av)), retain=True)
        c.subscribe(base + "/+/set")
        c.subscribe(base + "/+/press")
        c.publish(base + "/status", "online", retain=True)
        self.publish_art_config()
        self.publish()
        self.publish_art()

    def publish_art_config(self):
        if not self.mq or not self.s["art"]["enabled"]:
            return
        a = self.s["art"]
        eid = a.get("entity_id") or "sensor.music_art_brightness"
        self.mq.publish("homeassistant/sensor/%s/art/config" % BASE, json.dumps({
            "name": a.get("name") or "Music Art Brightness", "unique_id": BASE + "_art_brightness", "default_entity_id": eid,
            "icon": "mdi:image-filter-hdr", "state_topic": BASE + "/art/state", "json_attributes_topic": BASE + "/art/attrs",
            "availability_topic": BASE + "/status", "device": self.device(), "state_class": "measurement"}), retain=True)

    def publish_art(self):
        if not self.mq or not self.s["art"]["enabled"] or self.art["brightness"] is None:
            return
        self.mq.publish(BASE + "/art/state", str(self.art["brightness"]), retain=True)
        self.mq.publish(BASE + "/art/attrs", json.dumps({k: self.art.get(k) for k in ("color", "palette", "text_color", "title", "player")}), retain=True)

    def publish(self):
        if not self.mq:
            return
        s, base, p = self.s["show"], BASE, self.mq.publish
        p(base + "/party/state", "ON" if self.on else "OFF", retain=True)
        p(base + "/effect/state", EFFECTS.get(s["effect"], "Off"), retain=True)
        p(base + "/theme/state", THEME_NAMES.get(s["theme"], "Party"), retain=True)
        p(base + "/speed/state", str(s["speed"]), retain=True)
        p(base + "/brightness/state", str(s["brightness"]), retain=True)
        p(base + "/bpm/state", str(s["bpm"]), retain=True)
        for name, topic in (("power_hour", "power_hour"), ("shots", "shots"), ("countdown", "countdown"), ("hype", "hype")):
            p(base + "/%s/state" % topic, "ON" if name in self.extras else "OFF", retain=True)
        p(base + "/status_text", ("Party: " + EFFECTS.get(s["effect"], "")) if self.on else "Off", retain=True)
        p(base + "/status_attrs", json.dumps({"extras": self.extra_info, "theme": THEME_NAMES.get(s["theme"]),
                                              "now_playing": self.art.get("title"), "last": self.events[0]["text"] if self.events else ""}), retain=True)

    async def mqtt_cmd(self, topic, payload):
        key = topic.split("/")[1]
        on = payload.upper() in ("ON", "1", "TRUE", "PRESS")
        if key == "party":
            await self.set_on(on)
        elif key == "effect":
            k = next((k for k, v in EFFECTS.items() if v == payload), None)
            if k:
                await self.apply({"show": {"effect": k}})
        elif key == "theme":
            k = next((k for k, v in THEME_NAMES.items() if v == payload), None)
            if k:
                await self.apply({"show": {"theme": k}})
        elif key in ("speed", "brightness", "bpm"):
            try:
                await self.apply({"show": {key: int(float(payload))}})
            except ValueError:
                pass
        elif key in ("power_hour", "shots", "countdown", "hype"):
            await self.toggle_extra(key, on)
        elif key == "flash":
            asyncio.ensure_future(self.flash())
        elif key == "drop":
            asyncio.ensure_future(self.drop())
        elif key == "birthday":
            asyncio.ensure_future(self.birthday())
        elif key == "blackout":
            asyncio.ensure_future(self.blackout())

    async def toggle_extra(self, key, on):
        if not on:
            self.stop_extra(key)
            if key == "countdown":
                await self.start_show()
            return
        fn = {"power_hour": self.power_hour, "shots": self.shot_caller, "countdown": self.countdown, "hype": self.hype_mc}[key]
        self.start_extra(key, fn())

    async def apply(self, patch):
        old_show = dict(self.s["show"])
        self.s = deep_merge(self.s, patch)
        save_settings(self.s)
        if "art" in patch:
            self.publish_art_config()
        sh = self.s["show"]
        if (sh["effect"], sh["theme"]) != (old_show["effect"], old_show["theme"]) or "lights" in patch:
            if self.on:
                await self.start_show()
        self.publish()

    def view(self):
        return {"on": self.on, "settings": self.s, "effects": EFFECTS, "themes": THEME_NAMES,
                "palettes": {k: self.palette(k) for k in THEME_NAMES}, "art": self.art, "extras": self.extra_info,
                "running": sorted(self.extras), "events": self.events[:15], "ha_ok": ha.ok, "mqtt": bool(self.mq and self.mq.is_connected()),
                "people_home": self.people_home()}


party = Party()


# ---------------------------------------------------------------- web
INGRESS = "172.30.32.2"


@web.middleware
async def ingress_only(request, handler):
    if not os.environ.get("DEV") and request.remote != INGRESS:
        return web.json_response({"error": "ingress only"}, status=403)
    return await handler(request)


async def index(request):
    return web.Response(text=open(os.path.join(WWW, "index.html"), encoding="utf-8").read(), content_type="text/html",
                        headers={"Cache-Control": "no-store"})


async def state(request):
    return web.json_response(party.view())


async def entities(request):
    out = {}
    for eid, s in ha.states.items():
        d = eid.split(".")[0]
        if d in ("light", "media_player", "tts", "select", "input_select", "input_boolean", "sensor", "switch", "person"):
            out.setdefault(d, []).append({"id": eid, "name": (s.get("attributes") or {}).get("friendly_name") or eid,
                                          "state": s.get("state")})
    for v in out.values():
        v.sort(key=lambda x: x["name"].lower())
    return web.json_response(out)


async def settings_post(request):
    b = await request.json()
    allowed = {k: v for k, v in b.items() if k in DEFAULTS}
    await party.apply(allowed)
    return web.json_response(party.view())


async def action(request):
    b = await request.json()
    a = b.get("action")
    try:
        if a == "party":
            await party.set_on(bool(b.get("on")))
        elif a == "effect":
            await party.apply({"show": {"effect": b.get("effect")}})
            if not party.on and b.get("effect") not in ("off",):
                await party.set_on(True)
        elif a in ("power_hour", "shots", "countdown", "hype"):
            await party.toggle_extra(a, bool(b.get("on")))
        elif a in ("flash", "drop", "birthday", "blackout"):
            asyncio.ensure_future(getattr(party, a)())
        elif a == "music_now":
            await party.music_now()
        elif a == "say":
            await party.say(str(b.get("text") or "Testing, one two three!")[:300])
        elif a == "ai_theme":
            return web.json_response({"ok": True, "theme": await party.ai_theme(str(b.get("vibe") or "")[:300]), "state": party.view()})
        else:
            return web.json_response({"ok": False, "error": "Unknown action"})
    except Exception as e:  # noqa: BLE001
        return web.json_response({"ok": False, "error": str(e)})
    return web.json_response({"ok": True, "state": party.view()})


async def on_startup(app):
    party.loop = asyncio.get_running_loop()
    await ha.start()
    ha.listeners.append(party.on_state)
    party.mqtt_start()
    log.info("Party Lights ready")


def main():
    app = web.Application(middlewares=[ingress_only])
    app.on_startup.append(on_startup)
    app.add_routes([web.get("/", index), web.get("/api/state", state), web.get("/api/entities", entities),
                    web.post("/api/settings", settings_post), web.post("/api/action", action)])
    web.run_app(app, host="0.0.0.0", port=8099, access_log=None, print=None)


if __name__ == "__main__":
    main()

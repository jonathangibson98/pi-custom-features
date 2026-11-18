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
import math
import sys
import threading
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
    "aurora": ["#00ff9c", "#00c3ff", "#7a00ff", "#b400ff", "#00ffd5"],
    "candy": ["#ff2d55", "#ffffff"],
    "tropical": ["#ff6f61", "#ffb400", "#00c9a7", "#ff3e9a", "#00a6ff"],
}
THEME_NAMES = {"party": "Party", "rainbow": "Rainbow", "neon": "Neon", "chill": "Chill", "sunset": "Sunset", "ocean": "Ocean",
               "christmas": "Christmas", "halloween": "Halloween", "july4": "4th of July", "valentine": "Valentine's",
               "stpatricks": "St. Patrick's", "newyear": "New Year's", "birthday": "Birthday", "album": "Album art",
               "team": "Team colors", "custom": "My colors", "ai": "AI theme", "aurora": "Aurora", "candy": "Candy cane",
               "tropical": "Tropical"}
EFFECTS = {
    "off": "Off", "music": "Music sync", "static": "Static colors", "color_loop": "Color loop", "rainbow_wave": "Rainbow wave",
    "disco": "Disco", "chase": "Chase", "pulse": "Pulse to the beat", "breathe": "Breathe", "strobe": "Strobe",
    "sparkle": "Sparkle", "fire": "Fire", "police": "Police", "lightning": "Lightning storm",
    "twinkle": "Twinkle", "comet": "Comet", "ping_pong": "Ping pong", "heartbeat": "Heartbeat", "aurora": "Aurora",
    "ocean": "Ocean waves", "alternate": "Alternate", "fireworks": "Fireworks", "spotlight": "Spotlight", "glitch": "Glitch",
    "lava": "Lava lamp", "shuffle": "Shuffle shows",
}
EFFECT_ICONS = {
    "off": "⏻", "music": "🎵", "static": "🎨", "color_loop": "🔄", "rainbow_wave": "🌈", "disco": "🪩", "chase": "🏃", "pulse": "💓",
    "breathe": "🌬️", "strobe": "⚡", "sparkle": "✨", "fire": "🔥", "police": "🚨", "lightning": "🌩️", "twinkle": "⭐", "comet": "☄️",
    "ping_pong": "🏓", "heartbeat": "❤️", "aurora": "🌌", "ocean": "🌊", "alternate": "🍬", "fireworks": "🎆", "spotlight": "🔦",
    "glitch": "👾", "lava": "🫧", "shuffle": "🔀",
}
SHUFFLE_POOL = ["color_loop", "rainbow_wave", "disco", "chase", "breathe", "sparkle", "twinkle", "comet", "ping_pong", "aurora",
                "ocean", "alternate", "fireworks", "spotlight", "lava"]
# Games and extras. kind: "loop" runs until stopped (a switch), "once" is a single round (a button).
GAMES = {
    "power_hour": ("🍺", "Power hour", "loop"), "shots": ("🥃", "Shot caller", "loop"), "countdown": ("⏳", "Countdown", "loop"),
    "hype": ("🎤", "AI hype MC", "loop"), "freeze": ("🧊", "Freeze dance", "loop"), "red_green": ("🚦", "Red light, green light", "loop"),
    "never": ("🙊", "Never have I ever", "loop"), "truth_dare": ("😈", "Truth or dare", "loop"), "trivia": ("🧠", "Party trivia", "loop"),
    "name_tune": ("🎧", "Name that tune", "loop"), "rules": ("📜", "Rule maker", "loop"), "welcome": ("👋", "Welcome arrivals", "loop"),
    "last_call": ("🌙", "Last call", "loop"), "hot_potato": ("🥔", "Hot potato", "once"), "roulette": ("🎯", "Light roulette", "once"),
    "cheers": ("🥂", "Cheers!", "once"), "dance_battle": ("🕺", "Dance battle", "once"),
    "flash": ("💥", "Flash", "once"), "drop": ("⬇️", "Drop the beat", "once"), "birthday": ("🎂", "Birthday blast", "once"),
    "blackout": ("🌑", "Blackout", "once"),
}
GAME_IDS = {"shots": "shot_caller", "hype": "hype_mc"}   # keep the 1.0 entity IDs
GAME_MDI = {"power_hour": "mdi:beer", "shots": "mdi:glass-wine", "countdown": "mdi:timer-sand", "hype": "mdi:microphone-variant",
            "freeze": "mdi:snowflake", "red_green": "mdi:traffic-light", "never": "mdi:hand-back-left", "truth_dare": "mdi:emoticon-devil",
            "trivia": "mdi:head-question", "name_tune": "mdi:music-circle", "rules": "mdi:script-text", "welcome": "mdi:human-greeting",
            "last_call": "mdi:weather-night", "hot_potato": "mdi:fire", "roulette": "mdi:bullseye-arrow", "cheers": "mdi:glass-cocktail",
            "dance_battle": "mdi:dance-ballroom", "flash": "mdi:flash", "drop": "mdi:arrow-collapse-down", "birthday": "mdi:cake-variant",
            "blackout": "mdi:lightbulb-off"}
NEVER = ["Never have I ever sung karaoke in public.", "Never have I ever fallen asleep at a party.", "Never have I ever lied about my age.",
         "Never have I ever sent a text to the wrong person.", "Never have I ever ghosted someone.", "Never have I ever cried at a movie.",
         "Never have I ever been kicked out of a bar.", "Never have I ever gotten a tattoo I regret.", "Never have I ever eaten food off the floor.",
         "Never have I ever pretended to know a song.", "Never have I ever stalked an ex online.", "Never have I ever called in sick to stay home.",
         "Never have I ever broken something and hidden it.", "Never have I ever danced on a table.", "Never have I ever forgotten a friend's birthday."]
TRUTHS = ["What's the most embarrassing song on your playlist?", "Who here would you call to help hide a body?", "What's your worst date story?",
          "What's the dumbest thing you've done for money?", "What's a secret talent nobody here knows about?", "Who was your first crush?",
          "What's the last lie you told?", "What's your guilty pleasure TV show?"]
DARES = ["Do your best impression of someone here.", "Dance with no music for 20 seconds.", "Let the group pick your next song.",
         "Talk in an accent until your next turn.", "Show the last photo on your phone.", "Do 10 push-ups right now.",
         "Sing the chorus of the song that's playing.", "Speak only in rhymes for the next 2 minutes."]
TRIVIA = [("What planet is known as the red planet?", "Mars"), ("How many legs does a spider have?", "Eight"),
          ("What's the largest ocean on Earth?", "The Pacific"), ("Which country gave us pizza?", "Italy"),
          ("What's the tallest animal?", "The giraffe"), ("How many strings does a standard guitar have?", "Six"),
          ("What's the capital of Japan?", "Tokyo"), ("Which metal is liquid at room temperature?", "Mercury")]
RULES = ["Anyone who says 'drink' has to drink.", "No pointing. Pointers drink.", "You must cheers before every sip.",
         "Left hand only for your drink.", "Anyone who checks their phone takes a sip.", "Last person to touch their nose drinks.",
         "No first names. Use nicknames only.", "Every time the song changes, swap seats."]
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
    "shuffle_minutes": 3,
    "mode_entity": "",               # a select / input_select whose option picks the mode (Off = party over)
    "freeze": {"min_seconds": 20, "max_seconds": 60, "freeze_seconds": 8, "pause_music": ""},
    "red_green": {"min_seconds": 4, "max_seconds": 12},
    "prompts": {"every_minutes": 5, "use_ai": True},
    "trivia": {"every_minutes": 6, "answer_after": 20, "use_ai": True, "topic": ""},
    "name_tune": {"every_minutes": 8, "seconds": 15, "player": ""},
    "rules": {"every_minutes": 15, "use_ai": True},
    "welcome": {"message": "Welcome to the party, {name}!", "use_ai": False},
    "last_call": {"time": "01:30", "end_party": True, "minutes_warning": 15},
    "hot_potato": {"min_seconds": 15, "max_seconds": 45},
    "cheers": {"message": "Everybody raise your glass. Cheers!"},
    "dance_battle": {"seconds": 30},
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

    async def ws_cmd(self, msg):
        """One websocket command (helper creation and the like)."""
        async with self.http.ws_connect(WS) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            await ws.receive_json()
            await ws.send_json(dict(msg, id=1))
            while True:
                r = await ws.receive_json(timeout=20)
                if r.get("id") == 1:
                    return r

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
        self.music_last, self.music_used = {}, []
        self.status = "Ready"
        self.events = []             # recent things that happened, for the page
        self.slug = ""
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
        self.sync_helper()
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
        if eff == "shuffle":
            try:
                while True:
                    pick = random.choice(SHUFFLE_POOL)
                    self.extra_info["shuffle"] = EFFECTS[pick]
                    self.publish()
                    inner = asyncio.ensure_future(self.run_show(pick))
                    try:
                        await asyncio.sleep(max(1, float(self.s.get("shuffle_minutes") or 3)) * 60)
                    finally:
                        inner.cancel()
            except asyncio.CancelledError:
                self.extra_info.pop("shuffle", None)
                return
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
                elif eff == "twinkle":
                    for e in L:
                        if random.random() < 0.35:
                            await self.light(e, random.choice(pal), random.choice([b, max(1, b // 8)]), transition=step)
                elif eff == "comet":
                    head = i % n
                    for k, e in enumerate(L):
                        dist = (head - k) % n
                        await self.light(e, pal[(i // n) % len(pal)], b if dist == 0 else max(1, b // (3 * dist + 1)) if dist < 3 else 1, transition=step / 2)
                elif eff == "ping_pong":
                    pos = i % (2 * n - 2) if n > 1 else 0
                    pos = pos if pos < n else 2 * n - 2 - pos
                    for k, e in enumerate(L):
                        await self.light(e, pal[i % len(pal)] if k == pos else pal[(i + 1) % len(pal)], b if k == pos else max(1, b // 10), transition=0)
                elif eff == "heartbeat":
                    c = pal[(i // 4) % len(pal)]
                    phase = i % 4
                    await self.light(L, c, b if phase in (0, 2) else max(1, b // 8), transition=0)
                    step = max(float(self.s.get("speed_limit") or 0.5), [0.25, 0.25, 0.25, 1.2][phase] * 10 / max(1, int(self.s["show"]["speed"])) * 0.5)
                elif eff == "aurora":
                    ap = [hex_rgb(c) for c in (self.palette() if self.s["show"]["theme"] not in ("party",) else THEMES["aurora"])]
                    for k, e in enumerate(L):
                        await self.light(e, ap[(i + k) % len(ap)], int(b * (0.4 + 0.6 * abs(math.sin((time.time() - t0) / 6 + k)))), transition=max(step, 3))
                    step = max(step, 3)
                elif eff == "ocean":
                    for k, e in enumerate(L):
                        wave = 0.5 + 0.5 * math.sin((time.time() - t0) / 3 + k * 0.9)
                        await self.light(e, [0, int(80 + 120 * wave), int(160 + 95 * wave)], int(b * (0.25 + 0.75 * wave)), transition=max(step, 1.5))
                    step = max(step, 1.5)
                elif eff == "alternate":
                    for k, e in enumerate(L):
                        await self.light(e, pal[(k + i) % 2 % len(pal)], b, transition=0)
                elif eff == "fireworks":
                    if random.random() < 0.6:
                        e = random.choice(L)
                        await self.light(e, random.choice(pal), 255, transition=0)
                        await asyncio.sleep(0.4)
                        await self.light(e, random.choice(pal), 1, transition=2)
                    step = random.uniform(0.6, 2.0)
                elif eff == "spotlight":
                    for k, e in enumerate(L):
                        await self.light(e, [255, 244, 220] if k == i % n else pal[k % len(pal)], 255 if k == i % n else max(1, b // 6), transition=step * 0.5)
                elif eff == "glitch":
                    e = random.choice(L)
                    await self.light(e, random.choice(pal + [[255, 255, 255]]), random.choice([255, 30, 120]), transition=0)
                    step = random.uniform(max(float(self.s.get("speed_limit") or 0.5), 0.3), 1.6)
                elif eff == "lava":
                    for k, e in enumerate(L):
                        await self.light(e, pal[int((time.time() - t0) / 8 + k) % len(pal)], int(b * random.uniform(0.5, 1)), transition=max(step * 2, 5))
                    step = max(step * 2, 5)
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
    def watched_players(self):
        """Players music sync follows: the ones picked, else the album-art player, else whatever is playing."""
        m = self.s["music"]
        if m["media_players"]:
            return list(m["media_players"])
        if self.s["art"].get("media_player"):
            return [self.s["art"]["media_player"]]
        return [e for e, st in ha.states.items() if e.startswith("media_player.") and st.get("state") == "playing"]

    def music_status(self):
        """Plain-words answer to 'why aren't my lights following the music?'."""
        m, follow = self.s["music"], self.watched_players()
        lights = m["lights"] or self.lights()
        playing = [p for p in follow if ha.state(p) == "playing"]
        cond = m.get("condition_entity") and m.get("condition_state")
        checks = [
            {"ok": bool(follow), "text": ("Following " + ", ".join(ha.attr(p, "friendly_name") or p for p in follow)) if follow
             else "No music player picked, and nothing is playing"},
            {"ok": bool(playing), "text": "Playing now" if playing else "Nothing is playing on it"},
            {"ok": bool(lights), "text": ("Lights: " + ", ".join(ha.attr(e, "friendly_name") or e for e in lights)) if lights else "No lights picked"},
        ]
        if cond:
            now = ha.state(m["condition_entity"])
            checks.append({"ok": str(now) == str(m["condition_state"]), "text": "%s is %s (needs %s)" % (
                ha.attr(m["condition_entity"], "friendly_name") or m["condition_entity"], now, m["condition_state"])})
        else:
            checks.append({"ok": self.music_allowed(), "text": "Always on" if m.get("always") else
                           ("Party is on in Music sync" if self.music_allowed() else "Turns on when the party is on in Music sync mode")})
        ok = all(c["ok"] for c in checks)
        last = self.music_last
        return {"ok": ok, "checks": checks, "last": last,
                "summary": "Syncing ✓" if ok else next(c["text"] for c in checks if not c["ok"])}

    def on_state(self, eid, old, new):
        m = self.s["music"]
        follow = self.watched_players()
        if not follow and eid.startswith("media_player.") and (new or {}).get("state") == "playing":
            follow = [eid]
        if eid in follow or eid == self.s["art"]["media_player"]:
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
        if (player in self.watched_players() or not self.watched_players()) and self.music_allowed():
            await self.apply_music(colors)
            self.music_last = {"time": time.time(), "player": ha.attr(player, "friendly_name") or player, "title": self.art["title"],
                               "colors": [rgb_hex(c) for c in self.music_used]}
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
            vivid = max(usable, key=lambda c: (max(c) - min(c)) * max(c))  # the most colorful, not the darkest
            self.music_used = [vivid]
            await self.light(L, vivid, b, transition=tr)
            return
        self.music_used = usable[:len(L)]
        for k, e in enumerate(L):
            await self.light(e, usable[k % len(usable)], b, transition=tr)

    async def music_now(self):
        follow = sorted(self.watched_players(), key=lambda p: ha.state(p) != "playing")
        for p in follow:
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

    # ---- more games
    def all_lights(self):
        return sorted(set(self.lights() + self.s["music"]["lights"]))

    async def ai_line(self, prompt, fallback, task="Party game"):
        try:
            out = await asyncio.get_running_loop().run_in_executor(None, ha_ai.ask, prompt + " Plain text only, no quotes, keep it fun and friendly.",
                                                                     OPTS.get("ai_task_entity") or "", task)
            out = (out or "").strip().strip('"')
            if out and not out.startswith(("{", "[")):
                return out
        except Exception as e:  # noqa: BLE001
            log.info("AI unavailable for %s (%s), using a built-in one", task, e)
        return random.choice(fallback)

    async def wait_info(self, key, seconds, label):
        end = time.time() + seconds
        while time.time() < end:
            left = int(end - time.time())
            self.extra_info[key] = label % (left // 60, left % 60) if "%d:%02d" in label else label
            if left % 10 == 0:
                self.publish()
            await asyncio.sleep(min(1, max(0.1, end - time.time())))

    async def freeze_dance(self):
        f = self.s["freeze"]
        while True:
            await self.wait_info("freeze", random.uniform(f["min_seconds"], max(f["min_seconds"], f["max_seconds"])), "Dancing… freeze coming")
            await self.stop_show()
            if f.get("pause_music"):
                await ha.call("media_player", "media_pause", {"entity_id": f["pause_music"]})
            await self.light(self.all_lights(), [120, 200, 255], 255, transition=0)
            await self.say("Freeze!")
            await self.wait_info("freeze", f["freeze_seconds"], "FROZEN! Anyone moving is out")
            if f.get("pause_music"):
                await ha.call("media_player", "media_play", {"entity_id": f["pause_music"]})
            await self.say("Dance!")
            await self.start_show()

    async def red_green(self):
        rg = self.s["red_green"]
        await self.stop_show()
        L = self.all_lights()
        try:
            while True:
                await self.light(L, [0, 255, 60], 255, transition=0)
                await self.say("Green light!")
                await self.wait_info("red_green", random.uniform(rg["min_seconds"], max(rg["min_seconds"], rg["max_seconds"])), "🟢 Go!")
                await self.light(L, [255, 0, 0], 255, transition=0)
                await self.say("Red light!")
                await self.wait_info("red_green", random.uniform(3, 6), "🔴 Stop!")
        finally:
            asyncio.ensure_future(self.start_show())

    async def prompts(self, key):
        pr = self.s["prompts"]
        while True:
            people = self.people_home()
            if key == "never":
                line = await self.ai_line("Write one new 'Never have I ever...' statement for a house party of adults.", NEVER, "Never have I ever") \
                    if pr["use_ai"] else random.choice(NEVER)
                asyncio.ensure_future(self.flash(None, 1))
                await self.say(line + " If you have, drink!")
            else:
                who = random.choice(people) if people else "Somebody"
                truth = random.random() < 0.5
                if pr["use_ai"]:
                    line = await self.ai_line("Write one %s for a friendly house party game, for %s." % ("truth question" if truth else "fun, safe dare", who),
                                              TRUTHS if truth else DARES, "Truth or dare")
                else:
                    line = random.choice(TRUTHS if truth else DARES)
                asyncio.ensure_future(self.flash(None, 1))
                await self.say("%s, %s! %s" % (who, "truth" if truth else "dare", line))
            self.extra_info[key] = "Last: " + line[:60]
            await self.wait_info(key, max(1, pr["every_minutes"]) * 60, self.extra_info[key])

    async def trivia(self):
        t = self.s["trivia"]
        while True:
            q, a = random.choice(TRIVIA)
            if t["use_ai"]:
                try:
                    out = await asyncio.get_running_loop().run_in_executor(None, ha_ai.ask_json,
                        "Write one fun party trivia question%s with a short answer. Reply ONLY with JSON {\"q\": \"question\", \"a\": \"answer\"}."
                        % ((" about " + t["topic"]) if t.get("topic") else ""), OPTS.get("ai_task_entity") or "", "Party trivia")
                    q, a = str(out.get("q") or q), str(out.get("a") or a)
                except Exception as e:  # noqa: BLE001
                    log.info("Trivia AI unavailable: %s", e)
            asyncio.ensure_future(self.flash(None, 1))
            await self.say("Trivia time! " + q)
            await self.wait_info("trivia", max(5, t["answer_after"]), "Q: " + q[:70])
            await self.say("The answer is: " + a)
            self.extra_info["trivia"] = "A: " + a[:60]
            await self.wait_info("trivia", max(1, t["every_minutes"]) * 60, self.extra_info["trivia"])

    async def name_tune(self):
        nt = self.s["name_tune"]
        while True:
            await self.wait_info("name_tune", max(1, nt["every_minutes"]) * 60, "Next round soon")
            player = nt.get("player") or (self.s["music"]["media_players"] or [""])[0]
            title, artist = ha.attr(player, "media_title"), ha.attr(player, "media_artist")
            if not title:
                continue
            await self.say("Name that tune! First to shout the artist wins.")
            asyncio.ensure_future(self.flash(None, 2))
            await self.wait_info("name_tune", max(5, nt["seconds"]), "Guess the artist!")
            await self.say("It's %s by %s!" % (title, artist or "someone"))

    async def rule_maker(self):
        r = self.s["rules"]
        while True:
            rule = await self.ai_line("Invent one short, funny house party rule for a drinking game (like Kings Cup rules).", RULES, "Rule maker") \
                if r["use_ai"] else random.choice(RULES)
            asyncio.ensure_future(self.flash(None, 2))
            await self.say("New rule! " + rule)
            self.extra_info["rules"] = "Rule: " + rule[:60]
            await self.wait_info("rules", max(1, r["every_minutes"]) * 60, self.extra_info["rules"])

    async def welcome(self):
        self.extra_info["welcome"] = "Watching the front door"
        self.publish()
        seen = set(self.people_home())
        while True:
            await asyncio.sleep(5)
            now = set(self.people_home())
            for who in now - seen:
                w = self.s["welcome"]
                line = w["message"].replace("{name}", who)
                if w.get("use_ai"):
                    line = await self.ai_line("Write one short, warm, funny line welcoming %s as they arrive at a house party." % who, [line], "Welcome")
                asyncio.ensure_future(self.flash("birthday", 2))
                await self.say(line)
                self.note("Welcomed " + who)
            seen = now

    async def last_call(self):
        lc = self.s["last_call"]
        hh, mm = (int(x) for x in (lc["time"] or "01:30").split(":")[:2])
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        warn = target - timedelta(minutes=max(0, int(lc["minutes_warning"])))
        if warn > now:
            await self.wait_info("last_call", (warn - now).total_seconds(), "Last call at %s" % lc["time"])
            await self.say("Last call! %d minutes left, get your last drinks." % lc["minutes_warning"])
            await self.light(self.all_lights(), [255, 160, 60], self.bri(40), transition=10)
        left = (target - datetime.now()).total_seconds()
        if left > 0:
            await self.wait_info("last_call", left, "Closing time soon")
        await self.say("That's the party, folks! Thanks for coming. Get home safe.")
        if lc.get("end_party"):
            asyncio.ensure_future(self.set_on(False))

    async def hot_potato(self):
        hp = self.s["hot_potato"]
        await self.stop_show()
        L = self.all_lights()
        await self.say("Hot potato! Pass it around before it blows!")
        total = random.uniform(hp["min_seconds"], max(hp["min_seconds"], hp["max_seconds"]))
        start = time.time()
        while time.time() - start < total:
            frac = (time.time() - start) / total
            await self.light(L, [255, int(200 * (1 - frac)), 0], 255 if int((time.time() - start) * (1 + frac * 6)) % 2 == 0 else 40, transition=0)
            self.extra_info["hot_potato"] = "Tick… tick…"
            await asyncio.sleep(max(float(self.s.get("speed_limit") or 0.5), 1.2 - frac))
        await self.light(L, [255, 0, 0], 255, transition=0)
        await self.say("Boom! Whoever's holding it drinks!")
        await asyncio.sleep(3)
        self.extra_info.pop("hot_potato", None)
        await self.start_show()

    async def roulette(self):
        await self.stop_show()
        L = self.all_lights()
        if not L:
            return
        await self.say("Spinning the light roulette!")
        delay, k = 0.5, random.randrange(len(L))
        for _ in range(random.randint(10, 18)):
            k = (k + 1) % len(L)
            await self.light(L, [40, 0, 60], 30, transition=0)
            await self.light(L[k], [255, 220, 0], 255, transition=0)
            await asyncio.sleep(max(float(self.s.get("speed_limit") or 0.5), delay))
            delay *= 1.12
        name = ha.attr(L[k], "friendly_name") or L[k]
        for _ in range(3):
            await self.light(L[k], [255, 255, 255], 255, transition=0)
            await asyncio.sleep(0.5)
            await self.light(L[k], [255, 0, 120], 255, transition=0)
            await asyncio.sleep(0.5)
        await self.say("It landed on %s! Whoever's closest to it drinks!" % name)
        await asyncio.sleep(4)
        await self.start_show()

    async def cheers(self):
        asyncio.ensure_future(self.flash("newyear", 3))
        await self.say(self.s["cheers"]["message"])

    async def dance_battle(self):
        people = self.people_home()
        if len(people) < 2:
            people = (people + ["Team one", "Team two"])[:2]
        a, b = random.sample(people, 2)
        L = self.all_lights()
        await self.stop_show()
        secs = max(10, int(self.s["dance_battle"]["seconds"]))
        await self.say("Dance battle! %s versus %s. %s, you're up first!" % (a, b, a))
        for who, col in ((a, [255, 0, 150]), (b, [0, 200, 255])):
            await self.light(L, col, 255, transition=0)
            await self.wait_info("dance_battle", secs, "%s is dancing!" % who)
            if who == a:
                await self.say("Time! %s, show us what you got!" % b)
        await self.say("Make some noise for %s!" % a)
        await asyncio.sleep(4)
        await self.say("And now for %s!" % b)
        await asyncio.sleep(4)
        await self.say("You decide the winner. Loser drinks!")
        self.extra_info.pop("dance_battle", None)
        await self.start_show()

    # ---- modes from outside the page: a helper entity, MQTT, or hassio.addon_stdin
    async def set_mode(self, key):
        """One way in for every 'pick a mode' control. 'off' ends the party."""
        if key == "off":
            self.s["show"]["effect"] = "off"
            save_settings(self.s)
            await self.set_on(False)
        elif key in EFFECTS:
            self.s["show"]["effect"] = key
            save_settings(self.s)
            if self.on:
                await self.start_show()
            else:
                await self.set_on(True)
        self.sync_helper()
        self.publish()

    def sync_helper(self):
        ent = self.s.get("mode_entity")
        if not ent:
            return
        want = EFFECTS.get(self.s["show"]["effect"] if self.on else "off", "Off")
        if ha.state(ent) == want:
            return
        domain = ent.split(".")[0]
        if want in (ha.attr(ent, "options") or []):
            asyncio.ensure_future(ha.call(domain, "select_option", {"entity_id": ent, "option": want}))

    def helper_changed(self, eid, old, new):
        if eid != self.s.get("mode_entity") or not new or (old and old.get("state") == new.get("state")):
            return
        label = str(new.get("state") or "")
        key = next((k for k, v in EFFECTS.items() if v.lower() == label.lower() or k == label.lower()), None)
        if key is None and label.lower() in ("on", "party", "party mode"):
            key = self.s["show"]["effect"] if self.s["show"]["effect"] != "off" else "disco"
        if key and not (key == "off" and not self.on) and not (self.on and key == self.s["show"]["effect"]):
            self.note("Mode from %s: %s" % (eid, label))
            asyncio.ensure_future(self.set_mode(key))

    async def create_helper(self):
        """Make input_select.party_lights_mode with every mode, and use it."""
        opts = list(EFFECTS.values())
        r = await ha.ws_cmd({"type": "input_select/create", "name": "Party Lights Mode", "icon": "mdi:party-popper", "options": opts})
        if not r.get("success"):
            raise RuntimeError((r.get("error") or {}).get("message") or "Home Assistant didn't make the helper")
        eid = "input_select." + str((r.get("result") or {}).get("id") or "party_lights_mode")
        self.s["mode_entity"] = eid
        save_settings(self.s)
        await asyncio.sleep(1)
        await ha.fetch_states()
        self.sync_helper()
        return eid

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
        loops = [n for _i, n, k in GAMES.values() if k == "loop"]
        quick = [n for _i, n, k in GAMES.values() if k == "once"]
        ents = [
            ("switch", "party_mode", {"name": "Party", "icon": "mdi:party-popper", "command_topic": base + "/party/set", "state_topic": base + "/party/state"}),
            ("select", "party_effect", {"name": "Light mode", "icon": "mdi:led-strip-variant", "options": list(EFFECTS.values()), "command_topic": base + "/effect/set", "state_topic": base + "/effect/state"}),
            ("select", "party_theme", {"name": "Colors", "icon": "mdi:palette", "options": list(THEME_NAMES.values()), "command_topic": base + "/theme/set", "state_topic": base + "/theme/state"}),
            ("number", "party_brightness", {"name": "Brightness", "icon": "mdi:brightness-6", "min": 5, "max": 100, "step": 5, "unit_of_measurement": "%", "command_topic": base + "/brightness/set", "state_topic": base + "/brightness/state"}),
            ("number", "party_speed", {"name": "Speed", "icon": "mdi:speedometer", "min": 1, "max": 10, "step": 1, "command_topic": base + "/speed/set", "state_topic": base + "/speed/state"}),
            ("select", "party_game", {"name": "Game", "icon": "mdi:dice-multiple", "options": ["None"] + loops, "command_topic": base + "/game/set", "state_topic": base + "/game/state"}),
            ("select", "party_quick_hit", {"name": "Quick hit", "icon": "mdi:flash", "options": ["Pick one…"] + quick, "command_topic": base + "/quick/set", "state_topic": base + "/quick/state"}),
            ("sensor", "party_status", {"name": "Status", "icon": "mdi:party-popper", "state_topic": base + "/status_text", "json_attributes_topic": base + "/status_attrs"}),
        ]
        # 1.1 made a switch or button per game; remove those so the device stays short
        for oid in ["party_bpm"] + ["party_" + GAME_IDS.get(k, k) for k in GAMES]:
            for kind in ("switch", "button", "number"):
                if kind == "number" and oid != "party_bpm":
                    continue
                c.publish("homeassistant/%s/%s/%s/config" % (kind, base, oid), "", retain=True)
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
        running = [GAMES[k][1] for k in GAMES if k in self.extras and GAMES[k][2] == "loop"]
        p(base + "/game/state", running[0] if running else "None", retain=True)
        p(base + "/quick/state", "Pick one…", retain=True)
        p(base + "/status_text", ("Party: " + EFFECTS.get(s["effect"], "")) if self.on else "Off", retain=True)
        p(base + "/status_attrs", json.dumps({"extras": self.extra_info, "theme": THEME_NAMES.get(s["theme"]), "games_running": running,
                                              "music_sync": self.music_status()["summary"],
                                              "now_playing": self.art.get("title"), "last": self.events[0]["text"] if self.events else ""}), retain=True)

    async def mqtt_cmd(self, topic, payload):
        key = topic.split("/")[1]
        on = payload.upper() in ("ON", "1", "TRUE", "PRESS")
        if key == "game":
            pick = next((k for k, (_i, n, kind) in GAMES.items() if n == payload and kind == "loop"), None)
            for k in [k for k in list(self.extras) if GAMES.get(k, ("", "", ""))[2] == "loop" and k != pick]:
                await self.toggle_extra(k, False)
            if pick and pick not in self.extras:
                await self.toggle_extra(pick, True)
            self.publish()
        elif key == "quick":
            pick = next((k for k, (_i, n, kind) in GAMES.items() if n == payload and kind == "once"), None)
            if pick:
                await self.run_game(pick)
            self.publish()
        elif key.startswith("g_"):
            await self.run_game(key[2:], on)
        elif key == "party":
            await self.set_on(on)
        elif key == "effect":
            k = next((k for k, v in EFFECTS.items() if v == payload), None)
            if k:
                await self.set_mode(k)
        elif key == "theme":
            k = next((k for k, v in THEME_NAMES.items() if v == payload), None)
            if k:
                await self.apply({"show": {"theme": k}})
        elif key in ("speed", "brightness", "bpm"):
            try:
                await self.apply({"show": {key: int(float(payload))}})
            except ValueError:
                pass


    LOOP_GAMES = property(lambda self: {
        "power_hour": self.power_hour, "shots": self.shot_caller, "countdown": self.countdown, "hype": self.hype_mc,
        "freeze": self.freeze_dance, "red_green": self.red_green, "never": lambda: self.prompts("never"),
        "truth_dare": lambda: self.prompts("truth_dare"), "trivia": self.trivia, "name_tune": self.name_tune,
        "rules": self.rule_maker, "welcome": self.welcome, "last_call": self.last_call})
    ONCE_GAMES = property(lambda self: {
        "hot_potato": self.hot_potato, "roulette": self.roulette, "cheers": self.cheers, "dance_battle": self.dance_battle,
        "flash": self.flash, "drop": self.drop, "birthday": self.birthday, "blackout": self.blackout})

    async def toggle_extra(self, key, on):
        if not on:
            self.stop_extra(key)
            if key in ("countdown", "freeze", "red_green"):
                await self.start_show()
            return
        if key in self.LOOP_GAMES:
            self.start_extra(key, self.LOOP_GAMES[key]())

    async def run_game(self, key, on=True):
        if key in self.LOOP_GAMES:
            await self.toggle_extra(key, on)
        elif key in self.ONCE_GAMES:
            self.note("%s %s" % (GAMES[key][0], GAMES[key][1]))
            asyncio.ensure_future(self.ONCE_GAMES[key]())

    async def apply(self, patch):
        old_show = dict(self.s["show"])
        self.s = deep_merge(self.s, patch)
        save_settings(self.s)
        if "art" in patch:
            self.publish_art_config()
        if "mode_entity" in patch:
            self.sync_helper()
        sh = self.s["show"]
        if (sh["effect"], sh["theme"]) != (old_show["effect"], old_show["theme"]) or "lights" in patch:
            if self.on:
                await self.start_show()
        self.publish()

    def view(self):
        return {"on": self.on, "settings": self.s, "effects": EFFECTS, "effect_icons": EFFECT_ICONS, "themes": THEME_NAMES,
                "games": {k: {"icon": v[0], "name": v[1], "kind": v[2]} for k, v in GAMES.items()},
                "palettes": {k: self.palette(k) for k in THEME_NAMES}, "art": self.art, "extras": self.extra_info,
                "running": sorted(self.extras), "events": self.events[:15], "ha_ok": ha.ok, "mqtt": bool(self.mq and self.mq.is_connected()),
                "people_home": self.people_home(), "slug": self.slug, "music_status": self.music_status(),
                "follow": self.watched_players()}


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
            item = {"id": eid, "name": (s.get("attributes") or {}).get("friendly_name") or eid, "state": s.get("state")}
            if d in ("select", "input_select"):
                item["options"] = (s.get("attributes") or {}).get("options") or []
            out.setdefault(d, []).append(item)
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
            await party.set_mode(str(b.get("effect") or "off"))
        elif a == "game":
            await party.run_game(str(b.get("game")), bool(b.get("on", True)))
        elif a == "create_helper":
            eid = await party.create_helper()
            return web.json_response({"ok": True, "entity": eid, "state": party.view()})
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


def stdin_listener(loop):
    """hassio.addon_stdin: send 'off', a mode ('disco', 'Rainbow wave'), 'party on', or 'game power_hour on'."""
    try:
        for raw in sys.stdin:
            line = raw.strip().strip('"').strip()
            if not line:
                continue
            low = line.lower()
            words = low.split()
            if words[:1] == ["party"]:
                fut = party.set_on(len(words) < 2 or words[1] in ("on", "start", "1", "true"))
            elif words[:1] == ["game"] and len(words) >= 2:
                fut = party.run_game(words[1], len(words) < 3 or words[2] in ("on", "start", "1", "true"))
            else:
                key = next((k for k, v in EFFECTS.items() if low in (k, v.lower(), k.replace("_", " "))), None)
                if not key:
                    log.warning("stdin: didn't understand %r", line)
                    continue
                fut = party.set_mode(key)
            log.info("stdin: %s", line)
            asyncio.run_coroutine_threadsafe(fut, loop)
    except Exception as e:  # noqa: BLE001
        log.warning("stdin listener stopped: %s", e)


async def on_startup(app):
    party.loop = asyncio.get_running_loop()
    await ha.start()
    ha.listeners.append(party.on_state)
    ha.listeners.append(party.helper_changed)
    threading.Thread(target=stdin_listener, args=(asyncio.get_running_loop(),), daemon=True).start()
    party.mqtt_start()
    try:
        async with ha.http.get(os.environ.get("SUPERVISOR_URL", "http://supervisor") + "/addons/self/info", timeout=aiohttp.ClientTimeout(total=8)) as r:
            party.slug = ((await r.json()).get("data") or {}).get("slug") or ""
    except Exception:  # noqa: BLE001
        party.slug = ""
    log.info("Party Lights ready")


def main():
    app = web.Application(middlewares=[ingress_only])
    app.on_startup.append(on_startup)
    app.add_routes([web.get("/", index), web.get("/api/state", state), web.get("/api/entities", entities),
                    web.post("/api/settings", settings_post), web.post("/api/action", action)])
    web.run_app(app, host="0.0.0.0", port=8099, access_log=None, print=None)


if __name__ == "__main__":
    main()

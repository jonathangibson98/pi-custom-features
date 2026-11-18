"""Dashboards section: open, edit, fix and build whole Home Assistant dashboards with AI, sized for the screen they show on.

Reads and writes dashboards over Home Assistant's websocket (lovelace/*). Every save keeps the previous version so it
can be undone. Unsaved drafts are previewed on a hidden "Creator preview" dashboard, so you see the real thing at the
real screen size (a TV for a cast dashboard, a tablet, a phone) before anything you use changes.
"""
import json
import logging
import re
import time
from pathlib import Path

import yaml
from aiohttp import web

log = logging.getLogger("ai_builder.dash")

PREVIEW = "creator-preview"  # hidden dashboard used to show drafts
KEEP = 25
ENT_RE = re.compile(r"\b(?:[a-z_]+)\.[a-z0-9_]+\b")
DOMAINS = ("sensor", "binary_sensor", "light", "switch", "media_player", "camera", "climate", "cover", "fan", "lock",
           "person", "device_tracker", "weather", "input_boolean", "input_select", "input_number", "input_text",
           "input_datetime", "input_button", "script", "automation", "scene", "sun", "zone", "vacuum", "alarm_control_panel",
           "button", "number", "select", "calendar", "todo", "image", "update", "timer", "counter", "group", "remote",
           "water_heater", "humidifier", "event", "text", "siren", "valve", "lawn_mower", "conversation", "ai_task", "tts")
CORE_CARDS = {"alarm-panel", "area", "button", "calendar", "conditional", "entities", "entity", "entity-filter", "gauge",
              "glance", "grid", "heading", "history-graph", "horizontal-stack", "humidifier", "iframe", "light", "logbook",
              "map", "markdown", "media-control", "picture", "picture-elements", "picture-entity", "picture-glance",
              "plant-status", "sensor", "shopping-list", "statistic", "statistics-graph", "thermostat", "tile", "todo-list",
              "vertical-stack", "weather-forecast", "energy-date-selection", "energy-usage-graph", "energy-distribution",
              "clock", "error", "section", "media-player"}
SCREENS = {  # name: (width, height, notes for the AI)
    "tv1080": (1920, 1080, "a 1080p TV seen from across the room (cast). No scrolling, no touch: big text, high contrast, nothing interactive needed."),
    "tv720": (1280, 720, "a cast TV / Chromecast that renders at 1280x720. No scrolling, no touch: big text, high contrast."),
    "hub": (1024, 600, "a Google Nest Hub (1024x600 touch screen). No scrolling, big touch targets."),
    "hubmax": (1280, 800, "a Google Nest Hub Max (1280x800 touch screen). No scrolling, big touch targets."),
    "tablet": (1180, 820, "a wall tablet in landscape (about 1180x820). Ideally no scrolling, touch friendly."),
    "phone": (390, 844, "a phone in portrait (390x844). One column, scrolling is fine, touch friendly."),
    "desktop": (1440, 900, "a desktop browser (1440x900)."),
}


class Dashboards:
    def __init__(self, data_dir, ws_call, ask_ai, ha, extract_json):
        self.hist = Path(data_dir) / "dash_history"
        self.my_file = Path(data_dir) / "my_screens.json"
        self.ws_call, self.ask_ai, self.ha, self.extract_json = ws_call, ask_ai, ha, extract_json

    # ---------------------------------------------------------------- helpers
    async def ws(self, app, msg):
        r = await self.ws_call(app, dict(msg))
        if not r.get("success"):
            err = r.get("error") or {}
            raise RuntimeError(err.get("message") or err.get("code") or "Home Assistant said no")
        return r.get("result")

    async def list_all(self, app):
        try:
            boards = await self.ws(app, {"type": "lovelace/dashboards/list"}) or []
        except RuntimeError:
            boards = []
        out = [{"url_path": "", "title": "Overview (default)", "mode": "storage", "icon": "mdi:view-dashboard"}]
        for b in boards:
            if b.get("url_path") == PREVIEW:
                continue
            out.append({"url_path": b.get("url_path"), "title": b.get("title") or b.get("url_path"), "mode": b.get("mode"),
                        "icon": b.get("icon"), "id": b.get("id"), "show_in_sidebar": b.get("show_in_sidebar")})
        return out

    async def get_config(self, app, url):
        msg = {"type": "lovelace/config", "force": True}
        if url:
            msg["url_path"] = url
        return await self.ws(app, msg)

    async def save_config(self, app, url, config):
        msg = {"type": "lovelace/config/save", "config": config}
        if url:
            msg["url_path"] = url
        await self.ws(app, msg)

    def keep_version(self, url, config, note):
        d = self.hist / (url or "_default")
        d.mkdir(parents=True, exist_ok=True)
        (d / ("%d.json" % int(time.time() * 1000))).write_text(json.dumps({"note": note, "config": config}))
        for old in sorted(d.glob("*.json"))[:-KEEP]:
            old.unlink(missing_ok=True)

    def versions(self, url):
        d = self.hist / (url or "_default")
        out = []
        for p in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
            try:
                note = json.loads(p.read_text()).get("note", "")
            except (OSError, ValueError):
                note = ""
            out.append({"id": p.stem, "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(int(p.stem) / 1000)), "note": note})
        return out

    async def resources(self, app):
        try:
            res = await self.ws(app, {"type": "lovelace/resources"}) or []
        except RuntimeError:
            return set()
        names = set()
        for r in res:
            m = re.search(r"/([a-z0-9-]+?)(?:\.min)?(?:-bundle)?\.js", str(r.get("url") or ""), re.I)
            if m:
                names.add(m.group(1).lower())
        return names

    @staticmethod
    def walk(x, fn):
        if isinstance(x, dict):
            fn(x)
            for v in x.values():
                Dashboards.walk(v, fn)
        elif isinstance(x, list):
            for v in x:
                Dashboards.walk(v, fn)

    def check(self, config, states, resources):
        """Problems you can see without asking the AI: missing entities, card types that aren't installed, crowded views."""
        known = {s["entity_id"] for s in states}
        missing, cards, custom_missing = set(), [], set()
        text = json.dumps(config)
        for m in ENT_RE.finditer(text):
            e = m.group(0)
            if e.split(".")[0] in DOMAINS and e not in known:
                missing.add(e)

        def card(d):
            t = d.get("type")
            if isinstance(t, str):
                cards.append(t)
                if t.startswith("custom:"):
                    n = t[7:].lower()
                    if resources and not any(n == r or n in r or r in n for r in resources):
                        custom_missing.add(t)
        self.walk(config, card)
        views = []
        for i, v in enumerate((config or {}).get("views") or []):
            n = [0]
            self.walk(v.get("cards") or [], lambda d: n.__setitem__(0, n[0] + (1 if "type" in d else 0)))
            self.walk(v.get("sections") or [], lambda d: n.__setitem__(0, n[0] + (1 if "type" in d else 0)))
            views.append({"index": i, "title": v.get("title") or v.get("path") or "View %d" % (i + 1),
                          "type": v.get("type") or "masonry", "cards": n[0], "path": v.get("path") or ""})
        return {"missing_entities": sorted(missing)[:60], "missing_card_types": sorted(custom_missing),
                "card_count": len(cards), "views": views}

    @staticmethod
    def brief(s):
        a = s.get("attributes") or {}
        bits = ["%s = %s" % (s["entity_id"], str(s.get("state"))[:60])]
        if a.get("friendly_name"):
            bits.append("(%s)" % a["friendly_name"])
        if a.get("unit_of_measurement"):
            bits.append(a["unit_of_measurement"])
        if a.get("device_class"):
            bits.append("[%s]" % a["device_class"])
        return " ".join(bits)

    def pick_entities(self, states, config, request, limit=220):
        used = set(ENT_RE.findall(json.dumps(config or {})))
        words = {w for w in re.findall(r"[a-z0-9]{3,}", (request or "").lower())} - {"the", "and", "with", "make", "add", "card", "cards", "dashboard", "view", "show", "use", "all", "for", "that", "this", "bigger", "smaller"}
        scored = []
        for s in states:
            e = s["entity_id"]
            name = (e + " " + str((s.get("attributes") or {}).get("friendly_name") or "")).lower()
            score = 100 if e in used else sum(3 for w in words if w in name)
            if score:
                scored.append((score, e, s))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [self.brief(s) for _, _, s in scored[:limit]]

    def prompt(self, request, config, screen, entities, resources, scope_note, problems):
        w, h, notes = SCREENS.get(screen.get("id"), (screen.get("w"), screen.get("h"), screen.get("notes") or ""))
        if screen.get("id") == "custom":
            w, h, notes = screen.get("w") or 1280, screen.get("h") or 720, screen.get("notes") or "a custom screen"
        p = [
            "You edit Home Assistant Lovelace dashboards. Reply with ONLY a JSON object: "
            '{"config": <the full new dashboard config as JSON>, "summary": "<one or two sentences>", "changes": ["<short item>", ...]}.',
            "",
            "SCREEN: %dx%d px, %s" % (w, h, notes),
            "- Everything on each view must fit that screen without scrolling unless the screen notes say scrolling is fine. "
            "Size cards, fonts and grid rows for it. Prefer the sections view (type: sections, with max_columns) or a panel "
            "view with a grid for fixed screens; use grid_options / layout_options (columns, rows) to size cards.",
            "- For a TV: large text, high contrast, no tiny icons or controls, nothing that needs a tap.",
            "",
            "RULES:",
            "- Keep everything the request doesn't ask to change exactly as it is (same cards, entities, styles, card_mod, order).",
            "- Use only entity IDs from the list below or already in the dashboard. Never invent entities.",
            "- Built-in card types are fine. Custom cards only if installed: %s." % (", ".join(sorted(resources)) or "none found"),
            "- Keep views' path values unchanged so links keep working.",
            "- Valid Lovelace only. Templates go in block strings.",
        ]
        if scope_note:
            p += ["", scope_note]
        if problems:
            p += ["", "KNOWN PROBLEMS TO FIX IF RELEVANT: " + problems]
        p += ["", "REQUEST: " + (request or "Tidy it up and make it fit the screen."), "",
              "ENTITIES YOU MAY USE (id = state (name) unit [class]):", "\n".join(entities) or "(none matched)", "",
              "CURRENT CONFIG (JSON):", json.dumps(config, ensure_ascii=False)]
        return "\n".join(p)

    # ---------------------------------------------------------------- my screens
    KINDS = {
        "tv": "a TV seen from across the room. No scrolling, no touch: big text, high contrast, nothing interactive needed.",
        "touch": "a touch screen on a wall or counter. No scrolling, big touch targets.",
        "scroll": "a screen where scrolling is fine, touch friendly.",
    }

    def my_load(self):
        try:
            data = json.loads(self.my_file.read_text())
            return [x for x in data if isinstance(x, dict) and x.get("id")]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _num(v):
        try:
            n = float(str(v).strip().lower().replace("px", ""))
            return int(round(n)) if n > 0 else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def size_of(cls, st):
        """Width and height from one entity: a 'WxH' state, or width/height attributes."""
        if not st:
            return None, None
        m = re.search(r"(\d{3,5})\s*[x×*]\s*(\d{3,5})", str(st.get("state") or ""))
        if m:
            return int(m.group(1)), int(m.group(2))
        a = st.get("attributes") or {}
        for wk, hk in (("width", "height"), ("browser_width", "browser_height"), ("screen_width", "screen_height"),
                       ("viewport_width", "viewport_height"), ("resolution_width", "resolution_height")):
            if cls._num(a.get(wk)) and cls._num(a.get(hk)):
                return cls._num(a.get(wk)), cls._num(a.get(hk))
        m = re.search(r"(\d{3,5})\s*[x×*]\s*(\d{3,5})", str(a.get("resolution") or a.get("screen_resolution") or ""))
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    def resolve(self, scr, by_id):
        """A saved screen with its live size from its entities (falls back to the typed size)."""
        out = dict(scr)
        w = h = None
        if scr.get("source") == "entities":
            if scr.get("res_entity"):
                w, h = self.size_of(by_id.get(scr["res_entity"]))
            if scr.get("w_entity"):
                w = self._num((by_id.get(scr["w_entity"]) or {}).get("state")) or w
            if scr.get("h_entity"):
                h = self._num((by_id.get(scr["h_entity"]) or {}).get("state")) or h
            out["live"] = bool(w and h)
        out["w"] = int(w or scr.get("w") or 1280)
        out["h"] = int(h or scr.get("h") or 720)
        out["notes"] = "%s (%s, %dx%d)" % (self.KINDS.get(scr.get("kind"), self.KINDS["tv"]), scr.get("name") or "my screen", out["w"], out["h"])
        return out

    async def mine(self, app):
        my = self.my_load()
        if not my:
            return []
        by_id = {}
        if any(x.get("source") == "entities" for x in my):
            st, states = await self.ha(app, "GET", "/states")
            by_id = {x["entity_id"]: x for x in states} if st == 200 and isinstance(states, list) else {}
        return [self.resolve(x, by_id) for x in my]

    async def r_screens(self, request):
        """Save the list of my screens."""
        b = await request.json()
        keep = []
        for x in (b.get("screens") or [])[:30]:
            if not isinstance(x, dict) or not str(x.get("name") or "").strip():
                continue
            keep.append({
                "id": re.sub(r"[^a-z0-9_]", "", str(x.get("id") or "")) or "my_%d" % (len(keep) + 1),
                "name": str(x["name"]).strip()[:60], "kind": x.get("kind") if x.get("kind") in self.KINDS else "tv",
                "source": "entities" if x.get("source") == "entities" else "typed",
                "w": self._num(x.get("w")) or 1280, "h": self._num(x.get("h")) or 720,
                "w_entity": str(x.get("w_entity") or ""), "h_entity": str(x.get("h_entity") or ""), "res_entity": str(x.get("res_entity") or ""),
            })
        self.my_file.write_text(json.dumps(keep, indent=1))
        return web.json_response({"ok": True, "mine": await self.mine(request.app)})

    async def r_size_entities(self, request):
        """Entities that could tell a screen's size: width/height sensors (Browser Mod, Fully Kiosk...) and WxH ones, paired up."""
        st, states = await self.ha(request.app, "GET", "/states")
        if st != 200 or not isinstance(states, list):
            return web.json_response({"ok": False, "error": "Couldn't read Home Assistant's entities."})
        singles, widths, heights = [], {}, {}
        for x in states:
            e, a = x["entity_id"], x.get("attributes") or {}
            if e.split(".")[0] not in ("sensor", "number", "input_number", "media_player", "text", "input_text"):
                continue
            name = str(a.get("friendly_name") or e)
            low = (e + " " + name).lower()
            w, h = self.size_of(x)
            if w and h:
                singles.append({"entity": e, "name": name, "w": w, "h": h})
                continue
            n = self._num(x.get("state"))
            if not n or n > 10000:
                continue
            base = re.sub(r"[ _]*(browser|screen|display|viewport|window)?[ _]*(width|height)\b", "", e.split(".", 1)[1])
            if re.search(r"width\b", low):
                widths[base] = {"entity": e, "name": name, "v": n}
            elif re.search(r"height\b", low):
                heights[base] = {"entity": e, "name": name, "v": n}
        pairs = [{"name": re.sub(r"(?i)\s*(browser|screen|display|viewport|window)?\s*width$", "", widths[k]["name"]).strip() or k,
                  "w_entity": widths[k]["entity"], "h_entity": heights[k]["entity"], "w": widths[k]["v"], "h": heights[k]["v"]}
                 for k in widths if k in heights]
        loose = [dict(v, dim="width") for k, v in widths.items() if k not in heights] + [dict(v, dim="height") for k, v in heights.items() if k not in widths]
        return web.json_response({"ok": True, "pairs": pairs, "singles": singles, "loose": loose})

    # ---------------------------------------------------------------- routes
    async def r_list(self, request):
        try:
            return web.json_response({"ok": True, "dashboards": await self.list_all(request.app),
                                      "screens": {k: {"w": v[0], "h": v[1], "notes": v[2]} for k, v in SCREENS.items()},
                                      "mine": await self.mine(request.app)})
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(e)})

    async def r_get(self, request):
        url = request.query.get("url", "")
        app = request.app
        try:
            cfg = await self.get_config(app, url)
        except RuntimeError as e:
            if "not found" in str(e).lower() or "config_not_found" in str(e).lower():
                return web.json_response({"ok": True, "config": {"views": []}, "auto": True,
                                          "note": "This dashboard is still auto-generated by Home Assistant. Saving here takes it over."})
            return web.json_response({"ok": False, "error": str(e)})
        st, states = await self.ha(app, "GET", "/states")
        res = await self.resources(app)
        return web.json_response({"ok": True, "config": cfg, "yaml": yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=120),
                                  "check": self.check(cfg, states if isinstance(states, list) else [], res),
                                  "versions": self.versions(url)})

    async def r_check(self, request):
        b = await request.json()
        app = request.app
        st, states = await self.ha(app, "GET", "/states")
        cfg = self.parse(b)
        return web.json_response({"ok": True, "check": self.check(cfg, states if isinstance(states, list) else [], await self.resources(app))})

    @staticmethod
    def parse(b):
        if isinstance(b.get("config"), dict):
            return b["config"]
        y = b.get("yaml")
        if isinstance(y, str):
            cfg = yaml.safe_load(y) or {}
            if not isinstance(cfg, dict):
                raise ValueError("The YAML must be a dashboard (it should start with views:)")
            return cfg
        raise ValueError("No dashboard sent")

    async def r_ai(self, request):
        """AI edit: the whole dashboard or one view, for a chosen screen."""
        b = await request.json()
        app = request.app
        try:
            cfg = self.parse(b)
        except (ValueError, yaml.YAMLError) as e:
            return web.json_response({"ok": False, "error": "The YAML has a problem: %s" % e})
        view = b.get("view")
        st, states = await self.ha(app, "GET", "/states")
        states = states if isinstance(states, list) else []
        res = await self.resources(app)
        target, scope = cfg, ""
        views = cfg.get("views") or []
        if isinstance(view, int) and 0 <= view < len(views):
            target = {"views": [views[view]]}
            scope = "SCOPE: you are given ONE view of a bigger dashboard. Return config with exactly one view in views."
        problems = []
        chk = self.check(target, states, res)
        if chk["missing_entities"]:
            problems.append("these entities don't exist: " + ", ".join(chk["missing_entities"][:20]))
        if chk["missing_card_types"]:
            problems.append("these card types aren't installed: " + ", ".join(chk["missing_card_types"]))
        if b.get("overflow"):
            problems.append("in the live preview the content overflowed the screen by %s px; shrink or rearrange so it fits" % b["overflow"])
        prompt = self.prompt(b.get("request") or "", target, b.get("screen") or {"id": "desktop"},
                             self.pick_entities(states, target, b.get("request")), res, scope, "; ".join(problems))
        try:
            raw = await self.ask_ai(app, prompt)
            out = self.extract_json(raw)
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": "The AI didn't send back a dashboard: %s" % e})
        new = out.get("config") if isinstance(out, dict) else None
        if isinstance(new, dict) and "views" not in new and "cards" in new:
            new = {"views": [new]}
        if not isinstance(new, dict) or not isinstance(new.get("views"), list):
            return web.json_response({"ok": False, "error": "The AI's answer wasn't a dashboard. Try again or reword it."})
        if target is not cfg:
            merged = json.loads(json.dumps(cfg))
            merged["views"][view] = (new["views"] or [views[view]])[0]
            new = merged
        return web.json_response({"ok": True, "config": new, "summary": out.get("summary") or "",
                                  "changes": out.get("changes") or [],
                                  "yaml": yaml.safe_dump(new, sort_keys=False, allow_unicode=True, width=120),
                                  "check": self.check(new, states, res)})

    async def r_build(self, request):
        """A brand-new dashboard from a description."""
        b = await request.json()
        app = request.app
        st, states = await self.ha(app, "GET", "/states")
        states = states if isinstance(states, list) else []
        res = await self.resources(app)
        req = (b.get("request") or "").strip()
        if not req:
            return web.json_response({"ok": False, "error": "Describe the dashboard first."})
        prompt = self.prompt("Build a NEW dashboard from scratch: " + req, {"views": []}, b.get("screen") or {"id": "desktop"},
                             self.pick_entities(states, {}, req, 300), res, "", "")
        try:
            out = self.extract_json(await self.ask_ai(app, prompt))
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": "The AI didn't send back a dashboard: %s" % e})
        new = out.get("config") if isinstance(out, dict) else None
        if not isinstance(new, dict) or not isinstance(new.get("views"), list):
            return web.json_response({"ok": False, "error": "The AI's answer wasn't a dashboard. Try again."})
        return web.json_response({"ok": True, "config": new, "summary": out.get("summary") or "", "changes": out.get("changes") or [],
                                  "yaml": yaml.safe_dump(new, sort_keys=False, allow_unicode=True, width=120),
                                  "check": self.check(new, states, res)})

    async def r_preview(self, request):
        """Put a draft on the hidden preview dashboard."""
        b = await request.json()
        app = request.app
        try:
            cfg = self.parse(b)
        except (ValueError, yaml.YAMLError) as e:
            return web.json_response({"ok": False, "error": str(e)})
        try:
            boards = await self.ws(app, {"type": "lovelace/dashboards/list"}) or []
            if not any(x.get("url_path") == PREVIEW for x in boards):
                await self.ws(app, {"type": "lovelace/dashboards/create", "url_path": PREVIEW, "title": "Creator preview",
                                    "icon": "mdi:eye-outline", "show_in_sidebar": False, "require_admin": True, "mode": "storage"})
            await self.save_config(app, PREVIEW, cfg)
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": "Couldn't make the preview: %s" % e})
        return web.json_response({"ok": True, "url": "/" + PREVIEW})

    async def r_save(self, request):
        b = await request.json()
        app = request.app
        url = b.get("url") or ""
        try:
            cfg = self.parse(b)
        except (ValueError, yaml.YAMLError) as e:
            return web.json_response({"ok": False, "error": "The YAML has a problem: %s" % e})
        if url == PREVIEW:
            return web.json_response({"ok": False, "error": "Pick a real dashboard to save to."})
        try:
            try:
                old = await self.get_config(app, url)
                self.keep_version(url, old, b.get("note") or "Before a save from Creator")
            except RuntimeError:
                pass
            await self.save_config(app, url, cfg)
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": "Home Assistant didn't save it: %s" % e})
        return web.json_response({"ok": True, "versions": self.versions(url)})

    async def r_create(self, request):
        b = await request.json()
        app = request.app
        title = str(b.get("title") or "").strip()[:60]
        url = re.sub(r"[^a-z0-9-]+", "-", (b.get("url") or title).lower()).strip("-")
        if "-" not in url:
            url = "dashboard-" + url if url else "dashboard-new"
        try:
            await self.ws(app, {"type": "lovelace/dashboards/create", "url_path": url, "title": title or url,
                                "icon": b.get("icon") or "mdi:view-dashboard", "show_in_sidebar": bool(b.get("sidebar", True)),
                                "require_admin": False, "mode": "storage"})
            if b.get("config") or b.get("yaml"):
                await self.save_config(app, url, self.parse(b))
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(e)})
        return web.json_response({"ok": True, "url": url})

    async def r_version(self, request):
        url = request.query.get("url", "")
        vid = re.sub(r"[^0-9]", "", request.query.get("id", ""))
        p = self.hist / (url or "_default") / (vid + ".json")
        try:
            cfg = json.loads(p.read_text())["config"]
        except (OSError, ValueError, KeyError):
            return web.json_response({"ok": False, "error": "That version is gone."})
        return web.json_response({"ok": True, "config": cfg, "yaml": yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=120)})

    def routes(self):
        return [
            web.get("/api/dash/list", self.r_list),
            web.get("/api/dash/get", self.r_get),
            web.get("/api/dash/version", self.r_version),
            web.post("/api/dash/check", self.r_check),
            web.post("/api/dash/ai", self.r_ai),
            web.post("/api/dash/build", self.r_build),
            web.post("/api/dash/preview", self.r_preview),
            web.post("/api/dash/save", self.r_save),
            web.post("/api/dash/create", self.r_create),
            web.post("/api/dash/screens", self.r_screens),
            web.get("/api/dash/size_entities", self.r_size_entities),
        ]

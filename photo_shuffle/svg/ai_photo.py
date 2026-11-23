"""AI photo tools for Photo Hub's Photo Editor.

Uses Home Assistant's AI Task entities:
  * ai_task.generate_image (with the photo attached) to edit a photo from a plain-English request
  * ai_task.generate_data to look at a photo and suggest editor slider values ("Auto adjust")

It borrows the SVG Maker's Home Assistant connection (token, websocket and media-folder lookup).
"""
import asyncio
import io
import json
import logging
import os
import re
import time
import uuid

import aiohttp
from aiohttp import web
from PIL import Image, ImageOps

import ai_logo
import svg_tool

log = logging.getLogger("photo_hub.ai")

PHOTO_DIR = ai_logo.PHOTO_DIR  # same /media folder the SVG Maker uses, so Home Assistant can read it
PHOTO_MEDIA_ID = ai_logo.PHOTO_MEDIA_ID
KEEP = 3600
MAX_SIDE = 2048
SLIDERS = ("brightness", "contrast", "saturation", "warmth", "fade", "sharpen", "vignette")

AUTO_PROMPT = (
    "You are a photo editor. Look at the attached photo and decide how to improve it with simple sliders. "
    "Reply with ONLY a JSON object, no other text, using these keys (whole numbers): "
    "brightness (-100 to 100), contrast (-100 to 100), saturation (-100 to 100), warmth (-100 to 100, "
    "positive is warmer), fade (0 to 100), sharpen (0 to 100), vignette (0 to 100), and note (one short "
    "sentence saying what you changed and why). Make natural, modest corrections; use 0 for anything "
    "that is already fine.%s"
)

ANALYZE_PROMPT = (
    "Look at the attached photo and describe what is in it. Reply with ONLY a JSON object, no other text, using "
    "these keys: filename (2 to 5 lowercase words naming what the photo shows, joined with hyphens, no extension, "
    "like 'dog-on-couch' or 'sunset-over-lake'; never a person's name), caption (one plain sentence), scene (a few "
    "words, like 'kitchen' or 'beach at sunset'), objects "
    "(array of up to 15 short names of the main things you can see), people_count (whole number of people visible, "
    "0 if none), people (array with one short description per visible person: what they are doing and wearing, "
    "never a name; do not try to work out who anyone is), text (array of any readable text in the photo, empty if "
    "none), tags (array of up to 10 lowercase search keywords).%s"
)


class AiPhoto:
    def __init__(self, ai, opts):
        self.ai = ai  # ai_logo.AiLogo: Home Assistant connection + media folder lookup
        self.image_entity = str(opts.get("photo_ai_image_entity") or "").strip()
        self.data_entity = str(opts.get("photo_ai_data_entity") or "").strip()
        self.lock = asyncio.Lock()
        self._entities = (0.0, [])

    # ---- Home Assistant helpers
    @property
    def base(self):
        api = self.ai.api
        return api[:-4] if api.endswith("/api") else api

    async def entities(self):
        """AI Task entities and what they can do (cached for a minute)."""
        if time.time() - self._entities[0] < 60:
            return self._entities[1]
        out = []
        try:
            async with self.ai.http.get(self.ai.api + "/states", headers=self.ai.hdr,
                                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                states = await r.json() if r.status == 200 else []
            for s in states:
                eid = s.get("entity_id", "")
                if not eid.startswith("ai_task."):
                    continue
                f = int((s.get("attributes") or {}).get("supported_features") or 0)
                out.append({"id": eid, "name": (s.get("attributes") or {}).get("friendly_name") or eid,
                            "data": bool(f & 1), "attachments": bool(f & 2), "images": bool(f & 4)})
        except Exception as e:  # noqa: BLE001
            log.warning("Could not list AI Task entities: %s", e)
        self._entities = (time.time(), out)
        return out

    async def pick(self, want, chosen=""):
        ents = await self.entities()
        if chosen and any(e["id"] == chosen for e in ents):
            return chosen
        await self.ai.resolve()  # picks up the household default AI Task when the configured one doesn't exist
        pref = self.image_entity if want == "images" else (self.data_entity or self.ai.entity)
        if want == "images" and not pref:
            pref = self.ai.entity  # the default AI Task, if it can make pictures
        if pref and any(e["id"] == pref and e[want] for e in ents):
            return pref
        for e in ents:
            if e[want] and e["attachments"]:
                return e["id"]
        if pref:
            return pref
        raise RuntimeError("No AI Task entity that can %s was found. Add one (Google Gemini, OpenAI or Anthropic "
                           "under Settings > Devices & services) and try again."
                           % ("make pictures" if want == "images" else "look at photos"))

    def save_photo(self, raw):
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        except Exception:
            raise ValueError("That isn't a picture I can open.")
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        if not svg_tool.ensure_dir(PHOTO_DIR):
            raise ValueError("Could not create %s. The add-on needs write access to the media folder." % PHOTO_DIR)
        cutoff = time.time() - KEEP
        try:
            for n in os.listdir(PHOTO_DIR):
                p = os.path.join(PHOTO_DIR, n)
                if n.startswith("edit_") and os.path.getmtime(p) < cutoff:
                    os.remove(p)
        except OSError:
            pass
        pid = "edit_" + uuid.uuid4().hex[:12]
        img.save(os.path.join(PHOTO_DIR, pid + ".jpg"), "JPEG", quality=92)
        return pid

    async def attach(self, pid):
        d = await self.ai.find_media_dir(pid)
        return [{"media_content_id": PHOTO_MEDIA_ID % (d, pid), "media_content_type": "image/jpeg"}]

    async def call(self, service, body, timeout):
        try:
            async with self.ai.http.post(self.ai.api + "/services/ai_task/" + service, json=body,
                                         params={"return_response": "true"}, headers=self.ai.hdr,
                                         timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                status, txt = r.status, await r.text()
        except asyncio.TimeoutError:
            raise RuntimeError("The AI took longer than %d seconds. Raise svg_ai_timeout in Configuration or try "
                               "a simpler request." % timeout)
        except aiohttp.ClientError as e:
            raise RuntimeError("Could not reach Home Assistant: %s" % e)
        try:
            data = json.loads(txt)
        except ValueError:
            data = {}
        if status != 200:
            msg = (data.get("message") if isinstance(data, dict) else None) or txt
            if "source directory" in str(msg).lower():
                self.ai.media_dir = None
            raise RuntimeError("The AI request failed (HTTP %d): %s" % (status, str(msg)[:300]))
        return (data.get("service_response") or {}) if isinstance(data, dict) else {}

    async def read_upload(self, request):
        fields, raw = {}, b""
        reader = await request.multipart()
        async for part in reader:
            if part.name == "photo":
                raw = await part.read(decode=False)
            else:
                fields[part.name] = (await part.text())[:2000]
        if not raw:
            raise ValueError("No photo was sent.")
        if len(raw) > 60 * 1024 * 1024:
            raise ValueError("That photo is too big (60 MB max).")
        return raw, fields

    # ---- routes
    async def settings(self, request):
        ents = await self.entities()
        img = data = ""
        try:
            img = await self.pick("images")
        except RuntimeError:
            pass
        try:
            data = await self.pick("data")
        except RuntimeError:
            pass
        return web.json_response({"entities": ents, "image_entity": img, "data_entity": data})

    async def edit(self, request):
        """Edit a photo from a request like 'make it sunset' and send back the new picture."""
        try:
            raw, f = await self.read_upload(request)
            ask = (f.get("instructions") or "").strip()
            if not ask:
                raise ValueError("Say what the AI should change.")
            pid = await asyncio.get_running_loop().run_in_executor(None, self.save_photo, raw)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        try:
            async with self.lock:
                eid = await self.pick("images", f.get("entity", ""))
                body = {"entity_id": eid, "task_name": "Photo Hub edit",
                        "instructions": "Edit the attached photo. " + ask + " Keep everything else about the photo "
                                        "the same (framing, subject, details) unless the request says otherwise. "
                                        "Return the full edited photo.",
                        "attachments": await self.attach(pid)}
                log.info("AI photo edit with %s: %s", eid, ask[:120])
                res = await self.call("generate_image", body, self.ai.timeout)
                url = res.get("url") or ""
                if not url:
                    raise RuntimeError("The AI didn't send a picture back. Try rewording the request.")
                async with self.ai.http.get(url if url.startswith("http") else self.base + url, headers=self.ai.hdr,
                                            timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status != 200:
                        raise RuntimeError("Couldn't download the AI's picture (HTTP %d)." % r.status)
                    img = await r.read()
                    ctype = r.headers.get("Content-Type", res.get("mime_type") or "image/png")
        except RuntimeError as e:
            log.warning("AI photo edit failed: %s", e)
            return web.json_response({"error": str(e)}, status=502)
        finally:
            try:
                os.remove(os.path.join(PHOTO_DIR, pid + ".jpg"))
            except OSError:
                pass
        return web.Response(body=img, content_type=ctype.split(";")[0],
                            headers={"X-Model": str(res.get("model") or eid)})

    async def auto(self, request):
        """Ask the AI which slider values would improve the photo."""
        try:
            raw, f = await self.read_upload(request)
            pid = await asyncio.get_running_loop().run_in_executor(None, self.save_photo, raw)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        goal = (f.get("goal") or "").strip()
        try:
            eid = await self.pick("data", f.get("entity", ""))
            res = await self.call("generate_data", {
                "entity_id": eid, "task_name": "Photo Hub auto adjust",
                "instructions": AUTO_PROMPT % ((" The person wants: " + goal) if goal else ""),
                "attachments": await self.attach(pid)}, min(self.ai.timeout, 120))
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=502)
        finally:
            try:
                os.remove(os.path.join(PHOTO_DIR, pid + ".jpg"))
            except OSError:
                pass
        out = res.get("data")
        if isinstance(out, str):
            m = re.search(r"\{.*\}", out, re.S)
            try:
                out = json.loads(m.group(0)) if m else {}
            except ValueError:
                out = {}
        if not isinstance(out, dict):
            out = {}
        vals = {}
        for k in SLIDERS:
            try:
                lo = -100 if k in ("brightness", "contrast", "saturation", "warmth") else 0
                vals[k] = max(lo, min(100, int(round(float(out.get(k, 0))))))
            except (TypeError, ValueError):
                vals[k] = 0
        return web.json_response({"values": vals, "note": str(out.get("note") or "")[:300]})

    @staticmethod
    def _strings(v, limit, size):
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        out = []
        for x in v:
            x = str(x).strip()[:size]
            if x and x not in out:
                out.append(x)
        return out[:limit]

    async def analyze(self, request):
        """Describe a photo: caption, scene, objects, people (described, never named) and tags."""
        try:
            raw, f = await self.read_upload(request)
            pid = await asyncio.get_running_loop().run_in_executor(None, self.save_photo, raw)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        note = (f.get("notes") or "").strip()
        eid = (f.get("entity") or "").strip()
        try:
            async with self.lock:
                eid = await self.pick("data", eid)
                for e in await self.entities():
                    if e["id"] == eid and not (e["data"] and e["attachments"]):
                        raise RuntimeError("%s can't look at photos. Pick an AI Task that supports attachments "
                                           "(Google Gemini, OpenAI or Anthropic)." % e["name"])
                log.info("Analyzing a photo with %s", eid)
                res = await self.call("generate_data", {
                    "entity_id": eid, "task_name": "Photo Hub analyze",
                    "instructions": ANALYZE_PROMPT % ((" Pay particular attention to: " + note) if note else ""),
                    "attachments": await self.attach(pid)}, min(self.ai.timeout, 240))
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=502)
        finally:
            try:
                os.remove(os.path.join(PHOTO_DIR, pid + ".jpg"))
            except OSError:
                pass
        out = res.get("data")
        if isinstance(out, str):
            m = re.search(r"\{.*\}", out, re.S)
            try:
                out = json.loads(m.group(0)) if m else {}
            except ValueError:
                out = {}
        if not isinstance(out, dict) or not out:
            return web.json_response({"error": "The AI answered, but not in a form I could read. Try again or pick "
                                               "another AI Task."}, status=502)
        try:
            count = max(0, int(out.get("people_count") or 0))
        except (TypeError, ValueError):
            count = 0
        people = self._strings(out.get("people"), 20, 200)
        fname = re.sub(r"[^a-z0-9]+", "-", str(out.get("filename") or "").lower()).strip("-")[:50].strip("-")
        return web.json_response({"entity": eid, "analysis": {
            "filename": fname,
            "caption": str(out.get("caption") or "").strip()[:400],
            "scene": str(out.get("scene") or "").strip()[:120],
            "objects": self._strings(out.get("objects"), 15, 60),
            "people_count": max(count, len(people)),
            "people": people,
            "text": self._strings(out.get("text"), 10, 200),
            "tags": [t.lower() for t in self._strings(out.get("tags"), 10, 40)],
        }})

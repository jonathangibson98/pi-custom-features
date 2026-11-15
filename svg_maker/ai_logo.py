"""AI logo maker for SVG Maker.

You describe a logo in plain English. The Home Assistant AI Task entity (ai_task.generate_data) draws it as SVG
markup. The markup is cleaned here (scripts, external links, bitmaps removed, size and ids tidied) before the page
shows it. Results go into the same cache as photo conversions, so the Save / Download buttons work unchanged.
Everything lives under /api/svg/ai/."""
import asyncio
import json
import logging
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET

import aiohttp
from aiohttp import web

try:
    from PIL import Image, ImageOps
except Exception:  # Pillow is always in this image; keep the module importable without it
    Image = ImageOps = None

import svg_tool

log = logging.getLogger("svg_maker.ai")

DEFAULTS = {
    "svg_ai_task_entity": "ai_task.gemini_pro_ai_task",
    "svg_ai_timeout": 180,
    "svg_ai_default_style": "flat",
    "svg_ai_default_count": 1,
    "ha_url": "http://homeassistant:8123",
    "ha_token": "",
}
AI_MARK = "SVG Maker AI"  # written into temp files so auto-delete only ever removes files this tool made
MAX_SVG_BYTES = 200_000

STYLES = {
    "auto": ("Let the AI choose", "Choose whichever style best suits the description."),
    "flat": ("Flat and bold", "Flat vector logo: solid shapes, bold colors, no gradients and no shadows."),
    "line": ("Line icon", "Minimal line icon: one consistent stroke width (about 20 on the 512 grid), round stroke "
                          "caps and joins, fill=\"none\" on outlines, very few filled areas."),
    "gradient": ("Modern gradient", "Modern logo with smooth linear or radial gradients defined in <defs>, soft "
                                    "highlights and clean shapes."),
    "badge": ("Badge / emblem", "Badge or emblem: a contained shape (circle, shield or ribbon) with the symbol "
                                "inside it, balanced and symmetric."),
    "mascot": ("Mascot / character", "Friendly mascot or character built from simple expressive shapes that stay "
                                     "readable at small sizes."),
    "geometric": ("Geometric", "Geometric logo built from circles, triangles, squares and arcs with tidy alignment "
                               "and a strong silhouette."),
    "sketch": ("Hand-drawn", "Hand-drawn feel: slightly organic paths, uneven stroke ends, warm and playful."),
}

# A reference photo for the AI is saved where Home Assistant's "local" media source can see it (/media), because
# ai_task.generate_data takes attachments as media-source ids. Photos are deleted after a day.
PHOTO_DIR = os.environ.get("SVG_AI_PHOTO_DIR", "/media/svg_maker/ai_photos")
PHOTO_MEDIA_ID = "media-source://media_source/local/svg_maker/ai_photos/%s.jpg"
PHOTO_KEEP_SECONDS = 86400
PHOTO_USES = {
    "logo": ("Turn it into a logo",
             "Turn the main subject of the attached photo into a logo or icon. Keep what makes it recognizable (its "
             "overall shape, pose, distinctive markings, features and main colors) but simplify it into bold, clean "
             "vector shapes. Leave out the background and small details."),
    "close": ("Stay close to the photo",
              "Redraw the attached photo as a clean vector illustration that stays as close to it as you can: the "
              "same subject, pose, proportions, features, markings and colors. More detail is fine, but keep it clean "
              "vector art, not a trace of every pixel. Leave out the background unless the request asks for it."),
    "inspire": ("Just inspiration",
                "Use the attached photo only as inspiration for subject, colors and mood. The design can differ from "
                "it as much as the request needs."),
}

DROP_TAGS = ("script", "foreignObject", "iframe", "object", "embed", "image", "audio", "video",
             "animate", "animateTransform", "animateMotion", "set")
SHAPES = ("circle", "rounded", "square", "none")


# ---------------------------------------------------------------- SVG cleanup
def extract_svg(text):
    t = str(text or "")
    low = t.lower()
    i, j = low.find("<svg"), low.rfind("</svg>")
    if i < 0 or j < i:
        raise ValueError("The AI did not return SVG code.")
    return t[i:j + 6]


def attr_num(tag, name):
    m = re.search(r'\s%s\s*=\s*"\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*"' % name, tag, re.I)
    return float(m.group(1)) if m else 0.0


def normalize_root(svg):
    """Give the root tag the xmlns, integer width/height and a viewBox starting at 0 0 (apply_shape needs that)."""
    m = re.search(r"<svg\b[^>]*>", svg, re.I)
    if not m or m.group(0).rstrip().endswith("/>"):
        raise ValueError("The drawing was empty.")
    tag = m.group(0)
    vb = re.search(r'viewBox\s*=\s*"([^"]*)"', tag, re.I)
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", vb.group(1))] if vb else []
    if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
        x0, y0, w, h = nums
    else:
        x0 = y0 = 0.0
        w, h = attr_num(tag, "width"), attr_num(tag, "height")
        if not (w > 0 and h > 0):
            w = h = 512.0
    wi, hi = max(1, round(w)), max(1, round(h))
    rest = re.sub(r'\s(?:width|height|viewBox|xmlns)\s*=\s*("[^"]*"|\'[^\']*\')', "", tag[4:-1], flags=re.I)
    if "xlink:" in svg and "xmlns:xlink" not in rest:
        rest += ' xmlns:xlink="http://www.w3.org/1999/xlink"'
    new = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d"%s>' % (wi, hi, wi, hi, rest)
    inner = svg[m.end():svg.rfind("</svg>")]
    if x0 or y0:
        inner = '<g transform="translate(%g %g)">%s</g>' % (-x0, -y0, inner)
    return new + inner + "</svg>"


def clean_svg(svg):
    """Return (safe svg, warnings). Raises ValueError with a reason the AI can be told about."""
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    for t in DROP_TAGS:
        svg = re.sub(r"<%s\b[^>]*/>" % t, "", svg, flags=re.I)
        svg = re.sub(r"<%s\b[^>]*>.*?</%s\s*>" % (t, t), "", svg, flags=re.I | re.S)
    svg = re.sub(r'\son\w+\s*=\s*("[^"]*"|\'[^\']*\')', "", svg, flags=re.I)
    svg = re.sub(r'\s(?:xlink:)?href\s*=\s*("(?!#)[^"]*"|\'(?!#)[^\']*\')', "", svg, flags=re.I)
    svg = re.sub(r"url\(\s*(['\"]?)(?!#)[^)]*\)", "none", svg, flags=re.I)
    svg = re.sub(r"@import[^;]*;", "", svg, flags=re.I)
    if re.search(r"<!(?!\[CDATA\[)", svg):
        raise ValueError("The SVG contained a declaration that is not allowed.")
    if not re.search(r"<(path|circle|ellipse|rect|line|polyline|polygon|text|use)\b", svg, re.I):
        raise ValueError("The drawing had no shapes in it.")
    svg = normalize_root(svg)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        raise ValueError("The SVG was not valid XML (%s)." % e)
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ValueError("The root element was not <svg>.")
    size = len(svg.encode("utf-8"))
    if size > MAX_SVG_BYTES:
        raise ValueError("The SVG was too big (%d KB). Make it simpler." % (size // 1024))
    warns = []
    if re.search(r"<text\b", svg, re.I):
        warns.append("It contains text, which uses whatever font is installed where the icon is shown. "
                     "Ask for \"no text\" if you want it to look identical everywhere.")
    if re.search(r"<style\b", svg, re.I):
        warns.append("It has a style block, so class names could clash with other icons on one page.")
    return svg, warns


def uniquify_ids(svg):
    """Gradient and clip ids must be unique per icon, or two icons on one dashboard fight over them."""
    ids = set(re.findall(r'(?<![\w:-])id="([^"]+)"', svg))
    if not ids:
        return svg
    suf = uuid.uuid4().hex[:6]
    for i in sorted(ids, key=len, reverse=True):
        e = re.escape(i)
        svg = re.sub(r'(?<![\w:-])id="%s"' % e, 'id="%s-%s"' % (i, suf), svg)
        svg = re.sub(r"url\(#%s\)" % e, "url(#%s-%s)" % (i, suf), svg)
        svg = re.sub(r'href="#%s"' % e, 'href="#%s-%s"' % (i, suf), svg)
    return svg


# ---------------------------------------------------------------- prompt
def build_prompt(req, style, colors, mode, idx, n, current, feedback, problem, photo_use=None):
    p = [
        "You are an expert logo and icon designer who writes clean SVG code.", "",
        "OUTPUT RULES:",
        "- Reply with ONLY the SVG code. Start with <svg and end with </svg>. No markdown fences and no explanation.",
        '- Use viewBox="0 0 512 512" and xmlns="http://www.w3.org/2000/svg". The design is square, centered and fills '
        "the canvas with about 32 units of margin.",
        "- Use only vector shapes: path, circle, ellipse, rect, line, polyline, polygon, g, defs, linearGradient, "
        "radialGradient, clipPath. No <image>, bitmaps, <script>, <style>, class attributes, filters, animation, "
        "external links or external fonts. Put fill and stroke directly on the shapes as attributes.",
        "- Leave the background transparent unless the request asks for one.",
        "- It must read well from 24 px up to large: a strong simple silhouette, no tiny details, no more than about "
        "6 colors, and as few paths as it takes.",
        "- Do not add letters or words unless the request asks for lettering. If it does, keep it short and use <text> "
        'with font-family="Arial, Helvetica, sans-serif" font-weight="700" text-anchor="middle".',
        "- Every id must be unique and the SVG must be well-formed XML (write & as &amp;).", "",
    ]
    if mode == "bw":
        p += ['COLOR: single color. Use ONLY fill="currentColor" and/or stroke="currentColor" (plus fill="none"), so '
              "Home Assistant can recolor the icon. Use opacity for lighter tones. No other colors.", ""]
    elif colors:
        p += ["COLOR PALETTE: " + colors, ""]
    else:
        p += ["COLOR: choose a pleasing palette that suits the subject.", ""]
    p += ["STYLE: " + STYLES.get(style, STYLES["auto"])[1], ""]
    if photo_use:
        p += ["REFERENCE PHOTO (attached): " + PHOTO_USES.get(photo_use, PHOTO_USES["logo"])[1],
              "Look at the photo carefully before drawing. The output is still only SVG code.", ""]
    if n > 1:
        p += ["This is design option %d of %d. Make its concept and composition clearly different from the "
              "other options." % (idx, n), ""]
    if current and feedback:
        p += ["CURRENT SVG:", current, "", "CHANGE REQUESTED: " + feedback,
              "Original request, for context: " + req,
              "Return the complete updated SVG and keep everything the person did not ask to change.", ""]
    else:
        p += ["WHAT THE PERSON WANTS: " + req, ""]
    if problem:
        p += ["Your last answer was rejected: %s Fix that and reply with only the SVG." % problem, ""]
    return "\n".join(p)


# ---------------------------------------------------------------- the tool
class AiLogo:
    def __init__(self, maker, opts):
        self.maker = maker
        o = {k: opts.get(k, d) for k, d in DEFAULTS.items()}
        self.entity = str(o["svg_ai_task_entity"] or DEFAULTS["svg_ai_task_entity"]).strip()
        try:
            self.timeout = max(30, min(600, int(o["svg_ai_timeout"])))
        except (TypeError, ValueError):
            self.timeout = 180
        style = str(o["svg_ai_default_style"])
        self.default_style = style if style in STYLES else "flat"
        try:
            self.default_count = max(1, min(3, int(o["svg_ai_default_count"])))
        except (TypeError, ValueError):
            self.default_count = 1
        token = str(o["ha_token"] or "").strip()
        if token:  # optional long-lived token: talk to Home Assistant directly instead of through the Supervisor
            self.api = str(o["ha_url"] or DEFAULTS["ha_url"]).strip().rstrip("/") + "/api"
        else:
            token = os.environ.get("SUPERVISOR_TOKEN", "")
            self.api = "http://supervisor/core/api"
        self.hdr = {"Authorization": "Bearer " + token}
        self.http = None
        self.lock = asyncio.Lock()  # the AI draws one logo at a time
        self.photos = {}  # photo id -> {"path", "palette", "time"}

    async def start(self):
        self.http = aiohttp.ClientSession()
        self.cleanup()
        log.info("AI logo maker: using %s (timeout %ds)", self.entity, self.timeout)

    async def close(self):
        if self.http:
            await self.http.close()

    def cleanup(self):
        """Auto-delete old AI temp files, using the same options as the photo temp files."""
        m = self.maker
        if not m.opt["svg_auto_delete_temp"] or not os.path.isdir(m.temp):
            return
        cutoff = time.time() - int(m.opt["svg_auto_delete_after_days"]) * 86400
        try:
            for n in os.listdir(m.temp):
                p = os.path.join(m.temp, n)
                if n.lower().endswith(".svg") and os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    with open(p, "rb") as f:
                        head = f.read(200)
                    if AI_MARK.encode() in head:
                        os.remove(p)
        except OSError as e:
            log.warning("AI temp cleanup problem: %s", e)

    async def ask(self, prompt, photo_id=None):
        body = {"entity_id": self.entity, "task_name": "SVG logo", "instructions": prompt}
        if photo_id:
            body["attachments"] = [{"media_content_id": PHOTO_MEDIA_ID % photo_id, "media_content_type": "image/jpeg"}]
        try:
            async with self.http.post(
                self.api + "/services/ai_task/generate_data",
                json=body,
                params={"return_response": "true"}, headers=self.hdr,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as r:
                status, txt = r.status, await r.text()
        except asyncio.TimeoutError:
            raise RuntimeError("The AI took longer than %d seconds. Raise svg_ai_timeout in the add-on "
                               "Configuration, or try a simpler idea." % self.timeout)
        except aiohttp.ClientError as e:
            raise RuntimeError("Could not reach Home Assistant: %s" % e)
        if status in (401, 403):
            raise RuntimeError("Home Assistant refused the add-on (HTTP %d). Restart the add-on so it gets its "
                               "access, or set ha_token in the Configuration." % status)
        try:
            data = json.loads(txt)
        except ValueError:
            data = {}
        if status != 200:
            msg = (data.get("message") if isinstance(data, dict) else None) or txt
            if photo_id:
                raise RuntimeError("The AI task call with your photo failed (HTTP %d): %s. If your AI Task entity can't "
                                   "look at images, remove the photo or use an AI Task that can (Google Gemini, OpenAI "
                                   "and Anthropic can). The photo must also be readable from Home Assistant's media "
                                   "folder (Media > My media > svg_maker)." % (status, str(msg)[:300]))
            raise RuntimeError("The AI task call failed (HTTP %d): %s" % (status, str(msg)[:300]))
        out = ((data.get("service_response") or {}) if isinstance(data, dict) else {}).get("data")
        if out is None:
            return ""
        return out if isinstance(out, str) else json.dumps(out)

    async def draw(self, req, style, colors, mode, idx, n, current, feedback, photo=None):
        problem = ""
        pid, use = (photo or (None, None))
        for attempt in range(2):
            text = await self.ask(build_prompt(req, style, colors, mode, idx, n, current, feedback, problem, use), pid)
            try:
                return clean_svg(extract_svg(text))
            except ValueError as e:
                problem = str(e)
                log.warning("AI answer rejected (attempt %d): %s", attempt + 1, problem)
        raise RuntimeError("The AI answered, but not with a usable SVG (%s). Try again or reword it." % problem)

    # ---- routes
    async def settings(self, request):
        found, err = None, None
        try:
            async with self.http.get(self.api + "/states/" + self.entity, headers=self.hdr,
                                     timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    found = True
                elif r.status == 404:
                    found = False
                else:
                    err = "Home Assistant answered HTTP %d when looking for %s." % (r.status, self.entity)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            err = "Could not reach Home Assistant: %s" % e
        return web.json_response({
            "entity": self.entity, "found": found, "error": err,
            "styles": [[k, v[0]] for k, v in STYLES.items()],
            "default_style": self.default_style, "default_count": self.default_count,
            "photo_uses": [[k, v[0]] for k, v in PHOTO_USES.items()], "photos": Image is not None,
        })

    # ---- reference photo
    def photo_cleanup(self):
        cutoff = time.time() - PHOTO_KEEP_SECONDS
        for pid in [k for k, v in self.photos.items() if v["time"] < cutoff]:
            self.photos.pop(pid, None)
        try:
            for n in os.listdir(PHOTO_DIR):
                p = os.path.join(PHOTO_DIR, n)
                if re.fullmatch(r"[0-9a-f]{16}\.jpg", n) and os.path.getmtime(p) < cutoff:
                    os.remove(p)
        except OSError:
            pass

    def photo_save(self, raw):
        """Shrink and save the reference photo. Returns (id, palette). Raises ValueError."""
        import io
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        except Exception:
            raise ValueError("That isn't an image this add-on can open. Try a JPG or PNG.")
        img.thumbnail((1024, 1024), Image.LANCZOS)
        if not svg_tool.ensure_dir(PHOTO_DIR):
            raise ValueError("Could not create %s. The add-on needs access to the media folder." % PHOTO_DIR)
        pid = uuid.uuid4().hex[:16]
        img.save(os.path.join(PHOTO_DIR, pid + ".jpg"), "JPEG", quality=88)
        small = img.copy()
        small.thumbnail((96, 96))
        q = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        pal, counts = q.getpalette() or [], sorted(q.getcolors() or [], reverse=True)
        palette, seen = [], []
        for _, i in counts:
            rgb = tuple(pal[i * 3:i * 3 + 3])
            if any(sum((a - b) ** 2 for a, b in zip(rgb, o)) < 45 ** 2 for o in seen):
                continue  # nearly the same as a color already listed
            seen.append(rgb)
            palette.append("#%02x%02x%02x" % rgb)
        self.photos[pid] = {"path": os.path.join(PHOTO_DIR, pid + ".jpg"), "palette": palette[:6], "time": time.time()}
        return pid, palette[:6]

    async def photo(self, request):
        if Image is None:
            return web.Response(text="Pillow is missing from this build.", status=500)
        try:
            reader = await request.multipart()
            raw = b""
            async for part in reader:
                if part.name == "photo":
                    raw = await part.read(decode=False)
        except Exception:
            raw = b""
        if not raw:
            return web.Response(text="No photo was sent.", status=400)
        if len(raw) > self.maker.max_upload_bytes:
            return web.Response(text="File too large.", status=413)
        self.photo_cleanup()
        try:
            pid, palette = await asyncio.get_running_loop().run_in_executor(None, self.photo_save, raw)
        except ValueError as e:
            return web.Response(text=str(e), status=400)
        log.info("Reference photo saved for the AI (%s)", pid)
        return web.json_response({"photo_id": pid, "palette": palette})

    async def generate(self, request):
        try:
            b = await request.json()
        except ValueError:
            b = {}
        b = b if isinstance(b, dict) else {}
        m = self.maker
        feedback = str(b.get("feedback") or "").strip()[:1000]
        cur = m.cache.get(str(b.get("current_id") or "")) if feedback else None
        if feedback and not (cur and cur.get("raw")):
            return web.Response(text="That logo is no longer in memory. Make it again, then change it.", status=404)
        pid = str(b.get("photo_id") or "") or (cur or {}).get("photo_id") or ""
        if pid and (pid not in self.photos or not os.path.isfile(self.photos[pid]["path"])):
            return web.Response(text="The photo is no longer here (photos are kept for a day). Add it again.", status=404)
        use = b.get("photo_use") if b.get("photo_use") in PHOTO_USES else ((cur or {}).get("photo_use") or "logo")
        req = str(b.get("prompt") or "").strip()[:1500] or (cur or {}).get("prompt", "")
        if not req and pid:
            req = "A logo of the subject in the attached photo."
        if not req:
            return web.Response(text="Describe the logo first, or add a photo.", status=400)
        style = b.get("style") if b.get("style") in STYLES else self.default_style
        mode = "bw" if b.get("mode") == "bw" else "color"
        shape = b.get("shape") if b.get("shape") in SHAPES else "none"
        colors = str(b.get("colors") or "").strip()[:200]
        try:
            n = max(1, min(3, int(b.get("of") or 1)))
            idx = max(1, min(n, int(b.get("index") or 1)))
        except (TypeError, ValueError):
            n, idx = 1, 1
        log.info("Drawing logo (style=%s, mode=%s, shape=%s, option %d/%d%s%s)", style, mode, shape, idx, n,
                 ", edit" if cur else "", ", photo: " + use if pid else "")
        t0 = time.time()
        try:
            async with self.lock:
                raw, warns = await self.draw(req, style, colors, mode, idx, n, cur["raw"] if cur else None, feedback,
                                             (pid, use) if pid else None)
        except RuntimeError as e:
            return web.Response(text=str(e), status=502)
        except Exception as e:  # noqa: BLE001 - report anything unexpected to the page
            log.exception("AI logo failed")
            return web.Response(text="Could not make that logo: %s" % e, status=500)
        if mode == "bw" and m.opt["svg_bw_follow_theme"]:
            raw = svg_tool.follow_theme(raw)
        if mode == "bw" and re.search(r'(?:fill|stroke)="#[0-9a-fA-F]{3,8}"', raw):
            warns.append("It is not strictly single color. Ask for a change like \"use only one color\".")
        final = uniquify_ids(svg_tool.apply_shape(raw, shape))
        words = re.findall(r"[A-Za-z0-9]+", req)[:4]
        base = "-".join(words).lower() or "ai-logo"
        if pid and not str(b.get("prompt") or "").strip() and not cur:
            base = "photo-logo"
        temp_file = None
        if svg_tool.ensure_dir(m.temp):
            try:
                temp_file = svg_tool.unique_path(m.temp, m.temp_stem(base), ".svg")
                with open(temp_file, "w", encoding="utf-8") as o:
                    o.write("<!-- %s -->\n%s" % (AI_MARK, final))
            except OSError as e:
                log.error("Could not auto-save temp file: %s", e)
                temp_file = None
        self.cleanup()
        cid = uuid.uuid4().hex[:12]
        m.cache[cid] = {"svg": final, "temp": temp_file, "base": base, "raw": raw, "prompt": req,
                        "photo_id": pid, "photo_use": use if pid else None}
        while len(m.cache) > 25:
            m.cache.popitem(last=False)
        log.info("Logo done in %.1fs (%d KB)", time.time() - t0, len(final) // 1024)
        return web.json_response({"id": cid, "svg": final, "name": base, "ai": True, "warnings": warns,
                                  "temp_file": temp_file, "temp_url": m.temp_url(temp_file)})

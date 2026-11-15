"""SVG Maker tool: turns photos into scalable SVG files. Ported from the standalone SVG Maker add-on
(Flask) to aiohttp so it runs inside Creator & AI Builder. Everything lives under /api/svg/."""
import asyncio
import io
import logging
import os
import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from aiohttp import web

try:  # heavy imports are optional so the rest of the add-on still starts if they are missing
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    import vtracer
    IMPORT_ERROR = None
except Exception as e:  # pragma: no cover
    IMPORT_ERROR = str(e)

log = logging.getLogger("ai_builder.svg")

DEFAULTS = {
    "svg_output_path": "/homeassistant/custom_icons",
    "svg_temp_path": "/homeassistant/www/svg_maker/temp_icons",
    "svg_auto_delete_temp": False, "svg_auto_delete_after_days": 7,
    "svg_filename_style": "original_timestamp", "svg_on_name_conflict": "rename",
    "svg_default_mode": "color", "svg_default_detail": 5, "svg_path_style": "spline",
    "svg_max_image_dimension": 1600, "svg_max_upload_mb": 25,
    "svg_icon_names": True, "svg_bw_follow_theme": True,
    "svg_crop_editor": True, "svg_auto_crop": True, "svg_crop_shape": "circle",
    "svg_crop_padding": 15, "svg_output_size": 512, "svg_auto_enhance": True,
}
BLOCKED = ("/proc", "/sys", "/dev", "/etc", "/bin", "/sbin", "/usr", "/lib",
           "/lib64", "/run", "/var", "/root", "/boot", "/app", "/static")
KNOWN = ("/homeassistant", "/share", "/media", "/backup", "/ssl", "/config",
         "/data", "/addon_configs", "/addons")


def clean_path(p, default, label):
    """Absolute folder in a mapped location; anything else falls back to the default."""
    p = str(p or "").strip()
    if not p.startswith("/"):
        log.error("%s must be an absolute path starting with /. Using default %s", label, default)
        return default
    n = os.path.normpath(p)
    if n == "/" or any(n == b or n.startswith(b + "/") for b in BLOCKED):
        log.error("%s %s is a protected system location. Using default %s", label, n, default)
        return default
    if not any(n == k or n.startswith(k + "/") for k in KNOWN):
        log.warning("%s %s is not inside a Home Assistant mapped folder. It may disappear when the add-on restarts.", label, n)
    return n


def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        open(probe, "w").close()
        os.remove(probe)
        return True
    except Exception as e:
        log.error("Cannot write to %s (%s)", path, e)
        return False


def safe_name(name):
    base = os.path.splitext(os.path.basename(name or "image"))[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "image"


def clean_user_name(name, fallback):
    name = re.sub(r"\.svg$", "", (name or "").strip(), flags=re.I)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or fallback


def unique_path(folder, stem, ext):
    p = os.path.join(folder, stem + ext)
    i = 1
    while os.path.exists(p):
        p = os.path.join(folder, f"{stem}-{i}{ext}")
        i += 1
    return p


def icon_name(name):
    """lowercase-with-hyphens, safe to use as a Home Assistant icon name"""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def follow_theme(svg):
    """B&W traces: swap hard black for currentColor so HA can recolor the icon."""
    return re.sub(r'fill="#(?:000000|000)"', 'fill="currentColor"', svg)


def apply_shape(svg, shape):
    """Make the SVG square and clip it to a circle or rounded square."""
    if shape not in ("circle", "rounded", "square"):
        return svg
    m = re.search(r"<svg[^>]*>", svg)
    if not m:
        return svg
    tag = m.group(0)
    w = re.search(r'width="(\d+)"', tag)
    h = re.search(r'height="(\d+)"', tag)
    if not (w and h):
        return svg
    w, h = int(w.group(1)), int(h.group(1))
    side = min(w, h)
    x0, y0 = (w - side) / 2, (h - side) / 2
    new = re.sub(r'\s(width|height|viewBox)="[^"]*"', "", tag)
    new = new[:-1] + f' width="{side}" height="{side}" viewBox="{x0:g} {y0:g} {side} {side}">'
    inner = ""
    close = ""
    if shape in ("circle", "rounded"):
        if shape == "circle":
            clip = f'<circle cx="{w/2:g}" cy="{h/2:g}" r="{side/2:g}"/>'
        else:
            clip = f'<rect x="{x0:g}" y="{y0:g}" width="{side}" height="{side}" rx="{side*0.18:g}"/>'
        cid = "c" + uuid.uuid4().hex[:8]  # unique so many icons on one page don't clash
        inner = f'<defs><clipPath id="{cid}">{clip}</clipPath></defs><g clip-path="url(#{cid})">'
        close = "</g>"
    out = svg.replace(tag, new + inner, 1)
    i = out.rfind("</svg>")
    return out[:i] + close + out[i:] if i >= 0 else out


def enhance_image(img, mode, detail):
    """Clean up a photo so it traces into big flat shapes instead of noise."""
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.MedianFilter(5 if max(img.size) <= 800 else 3))
    if mode == "bw":
        return ImageOps.autocontrast(ImageOps.grayscale(img)).convert("RGB")
    img = ImageEnhance.Color(img).enhance(1.25)
    return img.quantize(colors=2 + detail, method=Image.Quantize.MEDIANCUT,
                        dither=Image.Dither.NONE).convert("RGB")


TRACE_CODE = ("import sys, json, vtracer\n"
              "a = json.loads(sys.argv[1])\n"
              "vtracer.convert_image_to_svg_py(a.pop('src'), a.pop('dst'), **a)\n")


def trace(src, dst, **kw):
    """Run vtracer in its own process. A native crash (segfault, out of memory) then only fails this
    one conversion with a clear message instead of killing the whole add-on (which shows as 503)."""
    args = dict(kw, src=src, dst=dst)
    try:
        p = subprocess.run([sys.executable, "-c", TRACE_CODE, json.dumps(args)],
                           capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Tracing took over 5 minutes. Lower the detail or svg_output_size.")
    if p.returncode != 0:
        why = ("killed by signal %d (likely out of memory or a crash in vtracer)" % -p.returncode
               if p.returncode < 0 else (p.stderr.strip()[-300:] or "exit code %d" % p.returncode))
        raise RuntimeError("The tracer failed: " + why)


class SvgMaker:
    def __init__(self, opts):
        self.opt = dict(DEFAULTS)
        self.opt.update({k: v for k, v in opts.items() if k in DEFAULTS})
        self.out = clean_path(self.opt["svg_output_path"], DEFAULTS["svg_output_path"], "SVG save folder")
        self.temp = clean_path(self.opt["svg_temp_path"], DEFAULTS["svg_temp_path"], "SVG temp folder")
        self.cache = OrderedDict()  # id -> {svg, temp, base}
        self.pool = ThreadPoolExecutor(max_workers=1)  # one trace at a time, kind to a Raspberry Pi

    @property
    def max_upload_bytes(self):
        return int(self.opt["svg_max_upload_mb"]) * 1024 * 1024

    def start(self):
        if IMPORT_ERROR:
            log.error("SVG Maker is unavailable (%s). Rebuild the add-on.", IMPORT_ERROR)
        ensure_dir(self.out)
        ensure_dir(self.temp)
        self.cleanup_temp()
        log.info("SVG Maker: save folder %s | temp folder %s | auto-delete temp: %s",
                 self.out, self.temp, self.opt["svg_auto_delete_temp"])

    # ---- helpers
    def temp_url(self, path):
        base = "/homeassistant/www/"
        if path and path.startswith(base):
            return "/local/" + path[len(base):]
        return ""

    def cleanup_temp(self):
        if not self.opt["svg_auto_delete_temp"] or not os.path.isdir(self.temp):
            return
        cutoff = time.time() - int(self.opt["svg_auto_delete_after_days"]) * 86400
        removed = 0
        try:
            for n in os.listdir(self.temp):
                p = os.path.join(self.temp, n)
                if n.lower().endswith(".svg") and os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    with open(p, "rb") as f:
                        head = f.read(400)
                    if b"VTracer" in head:  # only ever delete files this tool made
                        os.remove(p)
                        removed += 1
            if removed:
                log.info("Auto-delete removed %d old temp file(s)", removed)
        except Exception as e:
            log.warning("Temp cleanup problem: %s", e)

    def temp_stem(self, base):
        ts = int(time.time())
        style = self.opt["svg_filename_style"]
        if style == "original":
            return base
        if style == "timestamp":
            return str(ts)
        return f"{base}_{ts}"

    # ---- the conversion itself (runs in a worker thread)
    def convert_sync(self, raw, filename, mode, detail, shape, enhance):
        opt = self.opt
        base = safe_name(filename)
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "in.png"), os.path.join(d, "out.svg")
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            log.debug("Original size %sx%s", *img.size)
            m = int(opt["svg_max_image_dimension"])
            img.thumbnail((m, m))
            if enhance:
                img = enhance_image(img, mode, detail)
                kw = dict(filter_speckle=max(3, round(max(img.size) / 90) + 6 - detail),
                          color_precision=8, layer_difference=8, corner_threshold=60,
                          length_threshold=8, path_precision=1)
            else:
                kw = dict(filter_speckle=max(1, 12 - detail),
                          color_precision=min(8, 3 + detail // 2),
                          layer_difference=max(8, 40 - detail * 3))
            img.save(src)
            trace(
                src, dst,
                colormode="binary" if mode == "bw" else "color",
                mode=opt["svg_path_style"], **kw)
            with open(dst, encoding="utf-8") as o:
                svg = apply_shape(o.read(), shape)
            if mode == "bw" and opt["svg_bw_follow_theme"]:
                svg = follow_theme(svg)
        temp_file = None
        if ensure_dir(self.temp):
            try:
                temp_file = unique_path(self.temp, self.temp_stem(base), ".svg")
                with open(temp_file, "w", encoding="utf-8") as o:
                    o.write(svg)
                log.info("Auto-saved to %s", temp_file)
            except Exception as e:
                log.error("Could not auto-save temp file: %s", e)
                temp_file = None
        self.cleanup_temp()
        return svg, base, temp_file

    # ---- routes
    async def settings(self, request):
        o = self.opt
        return web.json_response({
            "available": IMPORT_ERROR is None, "error": IMPORT_ERROR,
            "default_mode": o["svg_default_mode"],
            "default_detail": int(o["svg_default_detail"]),
            "output_path": self.out, "temp_path": self.temp,
            "max_upload_mb": int(o["svg_max_upload_mb"]),
            "crop_editor": bool(o["svg_crop_editor"]), "auto_crop": bool(o["svg_auto_crop"]),
            "crop_shape": o["svg_crop_shape"], "crop_padding": int(o["svg_crop_padding"]),
            "output_size": int(o["svg_output_size"]), "auto_enhance": bool(o["svg_auto_enhance"]),
            "icon_names": bool(o["svg_icon_names"]),
        })

    async def convert(self, request):
        if IMPORT_ERROR:
            return web.Response(text=f"SVG tools are not installed in this add-on build ({IMPORT_ERROR}). Rebuild the add-on.", status=500)
        form = await request.post()
        f = form.get("photo")
        if f is None or not hasattr(f, "file"):
            return web.Response(text="No file received", status=400)
        raw = f.file.read()
        if len(raw) > self.max_upload_bytes:
            return web.Response(text=f"File too large. Max is {self.opt['svg_max_upload_mb']} MB.", status=413)
        mode = form.get("mode") or self.opt["svg_default_mode"]
        mode = mode if mode in ("color", "bw") else "color"
        try:
            detail = max(1, min(10, int(form.get("detail", self.opt["svg_default_detail"]))))
        except (TypeError, ValueError):
            detail = int(self.opt["svg_default_detail"])
        shape = form.get("shape") or self.opt["svg_crop_shape"]
        enhance = form.get("enhance", "1" if self.opt["svg_auto_enhance"] else "0") == "1"
        log.info("Converting %s (mode=%s, detail=%s, shape=%s, enhance=%s)", f.filename, mode, detail, shape, enhance)
        t0 = time.time()
        try:
            svg, base, temp_file = await asyncio.get_running_loop().run_in_executor(
                self.pool, self.convert_sync, raw, f.filename, mode, detail, shape, enhance)
        except Exception as e:
            log.exception("Conversion failed")
            return web.Response(text=f"Could not convert that image: {e}", status=500)
        cid = uuid.uuid4().hex[:12]
        self.cache[cid] = {"svg": svg, "temp": temp_file, "base": base}
        while len(self.cache) > 25:
            self.cache.popitem(last=False)
        log.info("Done in %.1fs (%d KB SVG)", time.time() - t0, len(svg) // 1024)
        return web.json_response({"id": cid, "svg": svg, "name": base,
                                  "temp_file": temp_file, "temp_url": self.temp_url(temp_file)})

    async def save(self, request):
        try:
            data = await request.json()
        except ValueError:
            data = {}
        data = data if isinstance(data, dict) else {}
        item = self.cache.get(data.get("id"))
        if not item:
            return web.Response(text="That conversion expired. Convert the photo again.", status=404)
        if not ensure_dir(self.out):
            return web.Response(text=f"Cannot write to save folder {self.out}. Check the svg_output_path option and the log.", status=500)
        name = clean_user_name(data.get("name"), item["base"])
        if self.opt["svg_icon_names"]:
            name = icon_name(name) or "icon"
        dest = os.path.join(self.out, name + ".svg")
        if os.path.exists(dest) and self.opt["svg_on_name_conflict"] == "rename":
            dest = unique_path(self.out, name, ".svg")
        try:
            with open(dest, "w", encoding="utf-8") as o:
                o.write(item["svg"])
        except Exception as e:
            log.error("Save failed: %s", e)
            return web.Response(text=f"Save failed: {e}", status=500)
        if item["temp"] and os.path.exists(item["temp"]):
            try:
                os.remove(item["temp"])
            except Exception:
                pass
        item["temp"] = None
        log.info("Saved %s", dest)
        return web.json_response({"saved_path": dest, "file_name": os.path.basename(dest)})

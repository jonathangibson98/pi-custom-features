#!/usr/bin/env python3
"""SVG Maker - turns photos into scalable SVG files and draws logos with AI. Stand-alone Home Assistant add-on (ingress only)."""
import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

import addon_backup
import ai_logo
import svg_tool

DATA = Path(os.environ.get("DATA_DIR", "/data"))
WWW = Path(os.environ.get("WWW_DIR", "/app/www"))

try:
    OPTS = json.load(open(DATA / "options.json"))
except Exception:
    OPTS = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger().setLevel(getattr(logging, str(OPTS.get("log_level") or "info").upper(), logging.INFO))
log = logging.getLogger("svg_maker")

INGRESS_IP = "172.30.32.2"  # only the Home Assistant ingress gateway may talk to us


@web.middleware
async def ingress_only(request, handler):
    if not os.environ.get("DEV") and request.remote != INGRESS_IP:
        return web.json_response({"error": "ingress only"}, status=403)
    return await handler(request)


def file_route(name, ctype):
    async def handler(request):
        return web.Response(text=(WWW / name).read_text(encoding="utf-8"), content_type=ctype,
                            headers={"Cache-Control": "no-store"})
    return handler


# created before anything is read, so a queued restore is unpacked first. Your saved icons go too.
BACKUP = addon_backup.Backup("svg_maker", "SVG Maker", "1.3.0",
                             [("data", str(DATA), "replace", []),
                              ("icons", lambda o: o.get("svg_output_path") or "/homeassistant/custom_icons", "merge", [])],
                             data_dir=str(DATA))
svg = svg_tool.SvgMaker(OPTS)
ai = ai_logo.AiLogo(svg, OPTS)


async def on_startup(app):
    svg.start()
    await ai.start()
    asyncio.get_running_loop().run_in_executor(None, svg.self_test)  # logs whether the tracer works here
    BACKUP.start()
    log.info("SVG Maker ready")


async def on_cleanup(app):
    await ai.close()


# ---------- backups (shared module, see addon_backup.py) ----------
async def backups_route(request):
    body = await request.read() if request.method == "POST" else b""
    st, ct, data, hdr = await asyncio.get_running_loop().run_in_executor(
        None, BACKUP.handle, request.method, request.match_info.get("tail", ""), dict(request.query), body, request.remote)
    return web.Response(body=data, status=st, headers=dict(hdr, **{"Content-Type": ct}))


def main():
    app = web.Application(client_max_size=max(svg.max_upload_bytes, 100 * 1024 * 1024) + 1024 * 1024,
                          middlewares=[ingress_only])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.add_routes([
        web.get("/", file_route("index.html", "text/html")),
        web.get("/svg-crop.js", file_route("svg-crop.js", "application/javascript")),
        web.route("*", "/backups{tail:.*}", backups_route),
        web.get("/api/svg/settings", svg.settings),
        web.post("/api/svg/convert", svg.convert),
        web.post("/api/svg/save", svg.save),
        web.get("/api/svg/ai/settings", ai.settings),
        web.post("/api/svg/ai/generate", ai.generate),
        web.post("/api/svg/ai/photo", ai.photo),
    ])
    web.run_app(app, host="0.0.0.0", port=8099, access_log=None)


if __name__ == "__main__":
    main()

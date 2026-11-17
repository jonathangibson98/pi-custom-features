#!/usr/bin/env python3
"""SVG Maker engine inside Photo Hub: turns photos into SVG files, draws logos with AI and runs the
Photo Editor's AI tools. Photo Hub starts it on 127.0.0.1 and passes requests through to it."""
import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

import ai_logo
import ai_photo
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
PORT = int(os.environ.get("SVG_PORT", "8101"))

INGRESS_IP = "172.30.32.2"  # only the Home Assistant ingress gateway may talk to us


@web.middleware
async def ingress_only(request, handler):
    if request.remote not in ("127.0.0.1", "::1"):  # only Photo Hub itself
        return web.json_response({"error": "ingress only"}, status=403)
    return await handler(request)


def file_route(name, ctype):
    async def handler(request):
        return web.Response(text=(WWW / name).read_text(encoding="utf-8"), content_type=ctype,
                            headers={"Cache-Control": "no-store"})
    return handler


svg = svg_tool.SvgMaker(OPTS)
ai = ai_logo.AiLogo(svg, OPTS)
photo_ai = ai_photo.AiPhoto(ai, OPTS)


async def on_startup(app):
    svg.start()
    await ai.start()
    asyncio.get_running_loop().run_in_executor(None, svg.self_test)  # logs whether the tracer works here
    log.info("SVG Maker engine ready on port %d", PORT)


async def on_cleanup(app):
    await ai.close()


def main():
    app = web.Application(client_max_size=max(svg.max_upload_bytes, 100 * 1024 * 1024) + 1024 * 1024,
                          middlewares=[ingress_only])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.add_routes([
        web.get("/", file_route("index.html", "text/html")),
        web.get("/svg-crop.js", file_route("svg-crop.js", "application/javascript")),
        web.get("/api/svg/settings", svg.settings),
        web.post("/api/svg/convert", svg.convert),
        web.post("/api/svg/save", svg.save),
        web.get("/api/svg/ai/settings", ai.settings),
        web.post("/api/svg/ai/generate", ai.generate),
        web.post("/api/svg/ai/photo", ai.photo),
        web.get("/api/photo/ai/settings", photo_ai.settings),
        web.post("/api/photo/ai/edit", photo_ai.edit),
        web.post("/api/photo/ai/auto", photo_ai.auto),
    ])
    web.run_app(app, host="127.0.0.1", port=PORT, access_log=None, print=None)


if __name__ == "__main__":
    main()

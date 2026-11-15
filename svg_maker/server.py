#!/usr/bin/env python3
"""SVG Maker - turns photos into scalable SVG files. Stand-alone Home Assistant add-on (ingress only)."""
import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

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


async def on_startup(app):
    svg.start()
    asyncio.get_running_loop().run_in_executor(None, svg.self_test)  # logs whether the tracer works here
    log.info("SVG Maker ready")


svg = svg_tool.SvgMaker(OPTS)


def main():
    app = web.Application(client_max_size=svg.max_upload_bytes + 1024 * 1024, middlewares=[ingress_only])
    app.on_startup.append(on_startup)
    app.add_routes([
        web.get("/", file_route("index.html", "text/html")),
        web.get("/svg-crop.js", file_route("svg-crop.js", "application/javascript")),
        web.get("/api/svg/settings", svg.settings),
        web.post("/api/svg/convert", svg.convert),
        web.post("/api/svg/save", svg.save),
    ])
    web.run_app(app, host="0.0.0.0", port=8099, access_log=None)


if __name__ == "__main__":
    main()

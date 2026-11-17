"""Files section (was the File Reader add-on).

Every text file in a folder (and its subfolders) becomes a Home Assistant sensor over MQTT. Automations write to the
files over MQTT (file_reader/append/..., file_reader/overwrite/..., file_reader/write) or over a token-protected REST
API on port 8100. Topics, unique IDs and the device are exactly the old File Reader's, so existing sensors
(and their renamed entity IDs) carry over.
"""
import glob
import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

from aiohttp import web

try:
    import paho.mqtt.client as mqtt
except ImportError:  # the web UI still works, sensors don't
    mqtt = None

log = logging.getLogger("ai_builder.files")

DEFAULT_DIR = "/share/file_reader"
MAPPED_ROOTS = ("/share", "/media", "/homeassistant", "/config", "/data", "/addon_configs")
OLD_BACKUPS = "/share/addon_backups/file_reader"  # the old File Reader add-on's own backups
API_PORT = 8100
MAX_FILES = 500
MAX_ATTR_CHARS = 8000
MAX_EDIT_BYTES = 2 * 1024 * 1024
SKIP_NAMES = {"secrets.yaml"}
SKIP_SUFFIXES = (".pem", ".key", ".crt", ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm")
SKIP_DIRS = {"__pycache__", "node_modules"}
T_WRITE = "file_reader/write"
T_APPEND = "file_reader/append/"
T_OVERWRITE = "file_reader/overwrite/"


class Files:
    def __init__(self, opts, ask_ai=None):
        self.opts = opts
        self.ask_ai = ask_ai
        self.token = str(opts.get("files_api_token") or "").strip()
        try:
            self.scan_every = max(5, int(opts.get("files_scan_interval") or 30))
        except (TypeError, ValueError):
            self.scan_every = 30
        self.lock = threading.Lock()
        self.known = {}
        self.client = None
        self.connected = False
        self.mqtt_error = ""
        self.import_note = ""
        self.root = self._prepare()

    # ---------------------------------------------------------------- folder
    def _old_backup(self):
        zips = sorted(glob.glob(os.path.join(OLD_BACKUPS, "*.zip")), key=os.path.getmtime, reverse=True)
        return zips[0] if zips else None

    def _prepare(self):
        wanted = os.path.abspath(str(self.opts.get("files_path") or DEFAULT_DIR))
        if wanted == DEFAULT_DIR:
            # moving over from the old File Reader add-on: if it used a folder this add-on can see, keep using it
            z = self._old_backup()
            if z:
                try:
                    with zipfile.ZipFile(z) as zf:
                        old = os.path.abspath(json.loads(zf.read("options.json")).get("files_path") or "")
                    if old.startswith(("/share/", "/media/", "/homeassistant/")) and os.path.isdir(old):
                        log.info("Using the old File Reader folder %s", old)
                        wanted = old
                except Exception as e:  # noqa: BLE001
                    log.warning("Couldn't read the old File Reader backup %s: %s", z, e)
        if not wanted.startswith(MAPPED_ROOTS):
            log.warning("%s isn't in a mapped folder, files may be lost on rebuild.", wanted)
        try:
            os.makedirs(wanted, exist_ok=True)
            if not os.access(wanted, os.W_OK):
                raise PermissionError("not writable")
        except Exception as e:  # noqa: BLE001
            log.error("Can't use %s (%s). Using %s", wanted, e, "/data/files")
            wanted = "/data/files"
            os.makedirs(wanted, exist_ok=True)
        return os.path.realpath(wanted)

    def import_old(self, overwrite=False):
        """Copy the files out of the old File Reader add-on's newest backup (its /data/files was private to it)."""
        z = self._old_backup()
        if not z:
            return 0, "No backup from the old File Reader add-on was found in %s." % OLD_BACKUPS
        n = 0
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if not name.startswith("files/files/") or name.endswith("/"):
                    continue
                rel = name[len("files/files/"):]
                path = self.resolve(rel)
                if not path or (os.path.exists(path) and not overwrite):
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with zf.open(name) as src, open(path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                n += 1
        self.scan(force=True)
        return n, "Copied %d file(s) from %s." % (n, os.path.basename(z))

    def resolve(self, name):
        try:
            if not name or "\0" in name:
                return None
            parts = name.replace("\\", "/").split("/")
            for p in parts:
                if p in ("", ".", "..") or p.startswith(".") or p.lower() in SKIP_NAMES:
                    return None
            if parts[-1].lower().endswith(SKIP_SUFFIXES):
                return None
            path = os.path.realpath(os.path.join(self.root, *parts))
            if path == self.root or os.path.commonpath([self.root, path]) != self.root:
                return None
            return path
        except (ValueError, OSError):
            return None

    def rel(self, path):
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    @staticmethod
    def is_text(path):
        try:
            with open(path, "rb") as f:
                return b"\0" not in f.read(4096)
        except OSError:
            return False

    def list(self):
        out = []
        for dp, dns, fns in os.walk(self.root):
            dns[:] = sorted(d for d in dns if not d.startswith(".") and d not in SKIP_DIRS)
            for f in sorted(fns):
                rel = os.path.relpath(os.path.join(dp, f), self.root).replace(os.sep, "/")
                full = self.resolve(rel)
                if full and os.path.isfile(full) and self.is_text(full):
                    out.append(rel)
                    if len(out) >= MAX_FILES:
                        return out
        return out

    @staticmethod
    def tail(path):
        size = os.path.getsize(path)
        keep = MAX_ATTR_CHARS * 4
        with open(path, "rb") as f:
            if size > keep:
                f.seek(size - keep)
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        if size <= keep:
            return text, len(text.splitlines()), len(text) > MAX_ATTR_CHARS
        count, last = 0, b"\n"
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                count += chunk.count(b"\n")
                last = chunk[-1:]
        return text, count + (0 if last == b"\n" else 1), True

    def write(self, name, text, mode="append"):
        mode = (mode or "append").lower()
        mode = "overwrite" if mode in ("overwrite", "write", "replace") else mode
        if mode not in ("append", "overwrite"):
            raise ValueError("mode must be 'append' or 'overwrite'")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        path = self.resolve(name)
        if not path or os.path.isdir(path):
            raise ValueError("Invalid file name")
        with self.lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            had = os.path.exists(path) and os.path.getsize(path) > 0
            with open(path, "a" if mode == "append" else "w", encoding="utf-8") as f:
                f.write(("\n" + text) if (mode == "append" and had) else text)
        rel = self.rel(path)
        self.publish(rel)
        self.remember(rel)
        return rel

    def delete(self, name):
        path = self.resolve(name)
        if not (path and os.path.isfile(path)):
            return False
        os.remove(path)
        parent = os.path.dirname(path)
        while parent != self.root:
            try:
                os.rmdir(parent)
            except OSError:
                break
            parent = os.path.dirname(parent)
        rel = self.rel(path)
        self.clear(rel)
        self.known.pop(rel, None)
        return True

    # ---------------------------------------------------------------- MQTT (same topics and IDs as File Reader)
    @staticmethod
    def safe(rel):
        return re.sub(r"[^A-Za-z0-9_]", "_", rel.replace("/", "__"))

    def topics(self, rel):
        s = self.safe(rel)
        return (f"homeassistant/sensor/file_reader/{s}/config", f"file_reader/sensor/{s}/state",
                f"file_reader/sensor/{s}/attributes", s)

    def publish(self, rel):
        if not self.client:
            return
        path = self.resolve(rel)
        if not path or not os.path.isfile(path):
            return
        disc, state, attr, s = self.topics(rel)
        tail, lines_n, trunc = self.tail(path)
        lines = tail.splitlines()
        self.client.publish(disc, json.dumps({
            "name": f"File Reader {rel}", "unique_id": f"file_reader_{s}", "state_topic": state,
            "json_attributes_topic": attr, "device_class": "timestamp", "icon": "mdi:file-text",
            "device": {"identifiers": ["file_reader_addon"], "name": "File Reader Storage Engine",
                       "model": "File Reader MQTT Add-on", "manufacturer": "Home Assistant Add-on"}}), retain=True)
        self.client.publish(state, datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat(), retain=True)
        self.client.publish(attr, json.dumps({
            "path": rel, "last_line": (lines[-1] if lines else "")[:MAX_ATTR_CHARS],
            "content": tail[-MAX_ATTR_CHARS:] if trunc else tail, "line_count": lines_n, "truncated": trunc}), retain=True)

    def clear(self, rel):
        if self.client:
            for t in self.topics(rel)[:3]:
                self.client.publish(t, "", retain=True)

    def remember(self, rel):
        try:
            st = os.stat(os.path.join(self.root, *rel.split("/")))
            self.known[rel] = (st.st_mtime_ns, st.st_size)
        except OSError:
            pass

    def scan(self, force=False):
        current = {}
        for rel in self.list():
            try:
                st = os.stat(os.path.join(self.root, *rel.split("/")))
            except OSError:
                continue
            current[rel] = (st.st_mtime_ns, st.st_size)
            if force or self.known.get(rel) != current[rel]:
                try:
                    self.publish(rel)
                except Exception as e:  # noqa: BLE001
                    log.error("Couldn't sync %s: %s", rel, e)
        for rel in set(self.known) - set(current):
            self.clear(rel)
        self.known = current

    def _mqtt_login(self):
        host = str(self.opts.get("mqtt_host") or "").strip()
        port = int(self.opts.get("mqtt_port") or 1883)
        user = str(self.opts.get("mqtt_user") or "").strip()
        pw = str(self.opts.get("mqtt_password") or "")
        if host and user:
            return host, port, user, pw
        token = os.environ.get("SUPERVISOR_TOKEN")
        if token:
            try:
                req = urllib.request.Request("http://supervisor/services/mqtt", headers={"Authorization": "Bearer " + token})
                with urllib.request.urlopen(req, timeout=10) as r:
                    d = json.load(r).get("data") or {}
                if d.get("host"):
                    return d["host"], int(d.get("port") or 1883), d.get("username") or "", d.get("password") or ""
            except Exception as e:  # noqa: BLE001
                log.warning("Couldn't get the MQTT login from Home Assistant: %s", e)
        return host or "core-mosquitto", port, user, pw

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        if mqtt is None:
            self.mqtt_error = "paho-mqtt is missing from this build"
            return
        host, port, user, pw = self._mqtt_login()
        try:
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ai_builder_files")
        except AttributeError:
            c = mqtt.Client(client_id="ai_builder_files")
        if user:
            c.username_pw_set(user, pw)

        def on_connect(cl, ud, flags, rc, props=None):
            bad = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
            if bad:
                self.connected, self.mqtt_error = False, "MQTT refused the login: %s" % rc
                log.error(self.mqtt_error)
                return
            self.connected, self.mqtt_error = True, ""
            log.info("Files: connected to MQTT at %s:%s", host, port)
            cl.subscribe([(T_WRITE, 0), (T_APPEND + "#", 0), (T_OVERWRITE + "#", 0)])
            self.scan(force=True)

        def on_disconnect(cl, ud, *a):
            self.connected = False

        def on_message(cl, ud, msg):
            if msg.retain:
                return
            try:
                payload = msg.payload.decode("utf-8", errors="replace")
                t = msg.topic
                if t == T_WRITE:
                    d = json.loads(payload)
                    self.write(d.get("file") or d.get("filename") or d.get("path"), str(d.get("text", "")), d.get("mode", "append"))
                elif t.startswith(T_APPEND):
                    self.write(t[len(T_APPEND):], payload, "append")
                elif t.startswith(T_OVERWRITE):
                    self.write(t[len(T_OVERWRITE):], payload, "overwrite")
            except Exception as e:  # noqa: BLE001
                log.error("Bad file update on %s: %s", msg.topic, e)

        c.on_connect, c.on_disconnect, c.on_message = on_connect, on_disconnect, on_message
        c.reconnect_delay_set(1, 60)
        self.client = c
        try:
            c.connect_async(host, port, 60)
            c.loop_start()
        except Exception as e:  # noqa: BLE001
            self.mqtt_error = "MQTT setup failed: %s" % e
            log.error(self.mqtt_error)
        while True:
            time.sleep(self.scan_every)
            try:
                self.scan()
            except Exception as e:  # noqa: BLE001
                log.error("File scan failed: %s", e)

    # ---------------------------------------------------------------- web
    async def info(self, request):
        return web.json_response({"files_path": self.root, "mqtt_connected": self.connected, "mqtt_error": self.mqtt_error,
                                  "api_enabled": bool(self.token), "api_port": API_PORT,
                                  "old_backup": bool(self._old_backup()), "files": self.list()})

    async def read(self, request):
        path = self.resolve(request.match_info["name"])
        if not (path and os.path.isfile(path)):
            return web.json_response({"error": "File not found"}, status=404)
        if os.path.getsize(path) > MAX_EDIT_BYTES:
            return web.json_response({"error": "File is too large to open in the browser"}, status=413)
        with open(path, encoding="utf-8", errors="replace") as f:
            return web.json_response({"filename": self.rel(path), "content": f.read()})

    async def write_route(self, request):
        name = request.match_info["name"]
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            text, mode = data.get("text", ""), data.get("mode", "append")
        else:
            text, mode = await request.text(), request.query.get("mode", "append")
        try:
            rel = self.write(name, text, mode)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except OSError as e:
            return web.json_response({"error": "Could not write file: %s" % (e.strerror or e)}, status=400)
        return web.json_response({"status": "success", "filename": rel})

    async def delete_route(self, request):
        if self.delete(request.match_info["name"]):
            return web.json_response({"status": "deleted"})
        return web.json_response({"error": "File not found"}, status=404)

    async def list_route(self, request):
        return web.json_response({"files": self.list()})

    async def import_route(self, request):
        try:
            n, note = self.import_old()
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(e)})
        return web.json_response({"ok": True, "copied": n, "note": note})

    async def ai_route(self, request):
        """AI help for a file: summarize it, answer a question about it, or draft new text."""
        b = await request.json()
        action = b.get("action") or "summarize"
        content = str(b.get("content") or "")[-12000:]
        ask = str(b.get("ask") or "").strip()[:2000]
        name = str(b.get("file") or "")
        if action == "write":
            prompt = ("Write the text for a plain-text file named %r used as a Home Assistant sensor (the last line is "
                      "shown as its state, the whole text as an attribute). Request: %s\n\nCurrent text (may be empty):\n%s\n\n"
                      "Reply with ONLY the new file text, no quotes or markdown fences." % (name, ask or "tidy it up", content))
        elif action == "ask":
            prompt = "Here is the text file %r:\n\n%s\n\nAnswer this about it, short and plain: %s" % (name, content, ask)
        elif action == "automation":
            prompt = ("Write a Home Assistant automation or script in YAML that %s, for the text file %r managed by the "
                      "Files section of the Creator add-on. To add a line use action mqtt.publish with topic "
                      "file_reader/append/<file>; to replace it use topic file_reader/overwrite/<file>; never set retain. "
                      "The file's sensor exposes 'content' and 'last_line' attributes. Reply with ONLY the YAML."
                      % (ask or "logs something useful to it", name))
        else:
            prompt = ("Summarize this text file %r in 2 to 4 short sentences, then list anything odd (errors, gaps, "
                      "repeats). Plain text.\n\n%s" % (name, content))
        if not self.ask_ai:
            return web.json_response({"ok": False, "error": "AI isn't set up"})
        try:
            out = await self.ask_ai(request.app, prompt)
        except Exception as e:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(e)})
        out = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", (out or "").strip())
        return web.json_response({"ok": True, "text": out})

    def routes(self, prefix="/api/files"):
        return [
            web.get(prefix + "/info", self.info),
            web.get(prefix + "/list", self.list_route),
            web.post(prefix + "/import", self.import_route),
            web.post(prefix + "/ai", self.ai_route),
            web.get(prefix + "/file/{name:.+}", self.read),
            web.post(prefix + "/file/{name:.+}", self.write_route),
            web.put(prefix + "/file/{name:.+}", self.write_route),
            web.delete(prefix + "/file/{name:.+}", self.delete_route),
        ]

    # ---- REST API on port 8100, same paths as File Reader (/api/files, /api/file/<name>)
    async def start_api(self):
        if not self.token:
            log.info("Files REST API is off (set files_api_token to turn it on)")
            return None

        @web.middleware
        async def guard(request, handler):
            auth = request.headers.get("Authorization", "")
            given = auth[7:] if auth.lower().startswith("bearer ") else (
                request.headers.get("X-API-Token") or request.query.get("token") or "")
            if not hmac.compare_digest(given.encode(), self.token.encode()):
                return web.json_response({"error": "Invalid or missing token"}, status=401)
            return await handler(request)

        api = web.Application(middlewares=[guard], client_max_size=4 * 1024 * 1024)
        api.add_routes([
            web.get("/api/files", self.list_route),
            web.get("/api/file/{name:.+}", self.read),
            web.post("/api/file/{name:.+}", self.write_route),
            web.put("/api/file/{name:.+}", self.write_route),
            web.delete("/api/file/{name:.+}", self.delete_route),
        ])
        runner = web.AppRunner(api, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "0.0.0.0", API_PORT).start()
            log.info("Files REST API on port %d (token required)", API_PORT)
        except OSError as e:
            log.error("Couldn't open the Files REST API port %d: %s", API_PORT, e)
        return runner

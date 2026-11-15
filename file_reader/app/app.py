import os
import re
import json
import hmac
import shutil
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from flask import Flask, render_template, request, jsonify, Response, abort
from werkzeug.serving import make_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("file_reader")

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEGACY_DIR = "/data/files"
MAPPED_ROOTS = ("/data", "/share", "/media", "/homeassistant", "/config")

API_PORT = 8100                  # token protected REST port for automations and scripts
MAX_FILES = 500                  # safety limit for how many files are tracked
MAX_ATTR_CHARS = 8000            # keep MQTT attributes small enough for Home Assistant
MAX_EDIT_BYTES = 2 * 1024 * 1024 # biggest file the web editor will open
SKIP_NAMES = {"secrets.yaml"}    # never exposed, anywhere in the folder tree
SKIP_SUFFIXES = (".pem", ".key", ".crt", ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm")
SKIP_DIRS = {"__pycache__", "node_modules"}

API_TOKEN = os.getenv("API_TOKEN") or ""
_si = os.getenv("SCAN_INTERVAL") or "30"
SCAN_INTERVAL = int(_si) if _si.isdigit() and int(_si) >= 5 else 30

write_lock = threading.Lock()


# ---------------------------------------------------------------- storage
def prepare_dir():
    wanted = os.path.abspath(os.getenv("FILES_PATH") or LEGACY_DIR)
    if not wanted.startswith(MAPPED_ROOTS):
        log.warning("%s is not in a mapped folder, files may be lost on rebuild.", wanted)
    try:
        os.makedirs(wanted, exist_ok=True)
        if not os.access(wanted, os.W_OK):
            raise PermissionError("not writable")
        return wanted
    except Exception as e:
        log.error("Cannot use %s (%s). Falling back to %s", wanted, e, LEGACY_DIR)
        os.makedirs(LEGACY_DIR, exist_ok=True)
        return LEGACY_DIR


DATA_DIR = prepare_dir()


def migrate_legacy_files():
    """One-time copy of files from the old /data/files into a newly chosen folder."""
    marker = "/data/.migrated_to"
    if DATA_DIR == LEGACY_DIR or not os.path.isdir(LEGACY_DIR):
        return
    if os.path.exists(marker) and open(marker).read().strip() == DATA_DIR:
        return
    copied = 0
    for dp, _dns, fns in os.walk(LEGACY_DIR):
        for name in fns:
            src = os.path.join(dp, name)
            dst = os.path.join(DATA_DIR, os.path.relpath(src, LEGACY_DIR))
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
    try:
        with open(marker, "w") as f:
            f.write(DATA_DIR)
    except OSError:
        pass
    if copied:
        log.info("Copied %d existing file(s) from %s to %s", copied, LEGACY_DIR, DATA_DIR)


migrate_legacy_files()


def root_dir():
    return os.path.realpath(DATA_DIR)


def resolve(name):
    """Safe absolute path for a relative name like 'logs/door.txt', or None if not allowed."""
    try:
        if not name or "\0" in name:
            return None
        parts = name.replace("\\", "/").split("/")
        for p in parts:
            if p in ("", ".", "..") or p.startswith(".") or p.lower() in SKIP_NAMES:
                return None
        if parts[-1].lower().endswith(SKIP_SUFFIXES):
            return None
        root = root_dir()
        path = os.path.realpath(os.path.join(root, *parts))
        if path == root or os.path.commonpath([root, path]) != root:
            return None  # blocks ../ tricks and symlinks that point outside the folder
        return path
    except (ValueError, OSError):
        return None


def rel_name(path):
    return os.path.relpath(path, root_dir()).replace(os.sep, "/")


def is_text(path):
    try:
        with open(path, "rb") as f:
            return b"\0" not in f.read(4096)
    except OSError:
        return False


def list_files():
    """Every text file in the folder and all subfolders, as relative paths."""
    root, out = root_dir(), []
    if not os.path.isdir(root):
        return out
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if not d.startswith(".") and d not in SKIP_DIRS)
        for f in sorted(fns):
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            full = resolve(rel)
            if full and os.path.isfile(full) and is_text(full):
                out.append(rel)
                if len(out) >= MAX_FILES:
                    log.warning("More than %d files found, ignoring the rest.", MAX_FILES)
                    return out
    return out


def read_text(path, limit=None):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(limit) if limit else f.read()


def read_tail(path):
    """Return (tail_text, line_count, truncated) without loading huge files."""
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


def normalize_mode(mode):
    mode = (mode or "append").lower()
    if mode == "append":
        return "append"
    if mode in ("overwrite", "write", "replace"):
        return "overwrite"
    raise ValueError("mode must be 'append' or 'overwrite'")


def do_write(name, text, mode):
    """Create or update a file (folders are created automatically) and sync MQTT."""
    mode = normalize_mode(mode)
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    path = resolve(name)
    if not path or os.path.isdir(path):
        raise ValueError("Invalid file name")
    with write_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        had_content = os.path.exists(path) and os.path.getsize(path) > 0
        with open(path, "a" if mode == "append" else "w", encoding="utf-8") as f:
            f.write(("\n" + text) if (mode == "append" and had_content) else text)
    rel = rel_name(path)
    publish_mqtt_discovery(rel)
    remember(rel)
    return rel


def do_delete(name):
    path = resolve(name)
    if not (path and os.path.isfile(path)):
        return False
    os.remove(path)
    root, parent = root_dir(), os.path.dirname(path)
    while parent != root:  # tidy up empty folders
        try:
            os.rmdir(parent)
        except OSError:
            break
        parent = os.path.dirname(parent)
    clear_mqtt(rel_name(path))
    known.pop(rel_name(path), None)
    return True


# ---------------------------------------------------------------- MQTT
MQTT_HOST = os.getenv("MQTT_HOST") or "core-mosquitto"
_port = os.getenv("MQTT_PORT")
MQTT_PORT = int(_port) if _port and _port.isdigit() else 1883
MQTT_USER = os.getenv("MQTT_USER") or ""
MQTT_PASS = os.getenv("MQTT_PASS") or ""


def autodetect_mqtt():
    """The Mosquitto add-on refuses anonymous logins. When no username is set in the options,
    ask Home Assistant (Supervisor) for the broker login it provides to add-ons."""
    global MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS
    if MQTT_USER:
        log.info("Using the MQTT username from the add-on options.")
        return
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        log.warning("No MQTT username set and no Supervisor token, trying without a login.")
        return
    try:
        req = urllib.request.Request("http://supervisor/services/mqtt",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r).get("data") or {}
        if not data.get("username"):
            log.warning("Home Assistant returned no MQTT login, trying without one.")
            return
        MQTT_HOST = data.get("host") or MQTT_HOST
        MQTT_PORT = int(data.get("port") or MQTT_PORT)
        MQTT_USER = data["username"]
        MQTT_PASS = data.get("password") or ""
        log.info("Got MQTT login from Home Assistant (broker %s:%s, user %s).",
                 MQTT_HOST, MQTT_PORT, MQTT_USER)
    except Exception as e:
        log.error("Could not get the MQTT login from Home Assistant: %s. "
                  "Is the Mosquitto broker add-on installed and running?", e)


autodetect_mqtt()

T_WRITE = "file_reader/write"
T_APPEND = "file_reader/append/"
T_OVERWRITE = "file_reader/overwrite/"


def make_client():
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="file_reader_addon")
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client(client_id="file_reader_addon")


mqtt_client = make_client()
if MQTT_USER:
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)


def safe_name(rel):
    # top level files keep their old entity ids, folders become "__"
    return re.sub(r"[^A-Za-z0-9_]", "_", rel.replace("/", "__"))


def topics(rel):
    s = safe_name(rel)
    return (
        f"homeassistant/sensor/file_reader/{s}/config",
        f"file_reader/sensor/{s}/state",
        f"file_reader/sensor/{s}/attributes",
        s,
    )


def publish_mqtt_discovery(rel):
    path = resolve(rel)
    if not path or not os.path.isfile(path):
        return
    discovery_topic, state_topic, attr_topic, s = topics(rel)
    tail, line_count, truncated = read_tail(path)
    lines = tail.splitlines()

    payload = {
        "name": f"File Reader {rel}",
        "unique_id": f"file_reader_{s}",
        "state_topic": state_topic,
        "json_attributes_topic": attr_topic,
        "device_class": "timestamp",
        "icon": "mdi:file-text",
        "device": {
            "identifiers": ["file_reader_addon"],
            "name": "File Reader Storage Engine",
            "model": "File Reader MQTT Add-on",
            "manufacturer": "Home Assistant Add-on",
        },
    }
    mqtt_client.publish(discovery_topic, json.dumps(payload), retain=True)

    # The sensor state is the time the file content last changed.
    changed = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat()
    mqtt_client.publish(state_topic, changed, retain=True)

    last_line = lines[-1] if lines else ""
    attrs = {
        "path": rel,
        "last_line": last_line[:MAX_ATTR_CHARS],
        "content": tail[-MAX_ATTR_CHARS:] if truncated else tail,
        "line_count": line_count,
        "truncated": truncated,
    }
    mqtt_client.publish(attr_topic, json.dumps(attrs), retain=True)


def clear_mqtt(rel):
    for t in topics(rel)[:3]:
        mqtt_client.publish(t, "", retain=True)


# ---- keep sensors in sync with what is really on disk (also catches edits made outside the UI)
known = {}


def signature(rel):
    st = os.stat(os.path.join(root_dir(), *rel.split("/")))
    return (st.st_mtime_ns, st.st_size)


def remember(rel):
    try:
        known[rel] = signature(rel)
    except OSError:
        pass


def scan_once(force=False):
    current = {}
    for rel in list_files():
        try:
            sig = signature(rel)
        except OSError:
            continue
        current[rel] = sig
        if force or known.get(rel) != sig:
            try:
                publish_mqtt_discovery(rel)
            except Exception as e:
                log.error("Could not sync %s: %s", rel, e)
    for rel in set(known) - set(current):
        clear_mqtt(rel)
        log.info("File removed, cleared sensor: %s", rel)
    known.clear()
    known.update(current)


def scan_loop():
    while True:
        time.sleep(SCAN_INTERVAL)
        try:
            scan_once()
        except Exception as e:
            log.error("Scan failed: %s", e)


# ---- incoming MQTT commands from automations
def on_message(client, userdata, msg):
    if msg.retain:
        log.warning("Ignoring retained message on %s (don't use retain when sending updates).", msg.topic)
        return
    try:
        payload = msg.payload.decode("utf-8", errors="replace")
        t = msg.topic
        if t == T_WRITE:
            data = json.loads(payload)
            name = data.get("file") or data.get("filename") or data.get("path")
            rel = do_write(name, str(data.get("text", "")), data.get("mode", "append"))
        elif t.startswith(T_APPEND):
            rel = do_write(t[len(T_APPEND):], payload, "append")
        elif t.startswith(T_OVERWRITE):
            rel = do_write(t[len(T_OVERWRITE):], payload, "overwrite")
        else:
            return
        log.info("Updated %s via MQTT", rel)
    except Exception as e:
        log.error("Bad MQTT update on %s: %s", msg.topic, e)


def on_connect(client, userdata, flags, reason_code, properties=None):
    failed = reason_code.is_failure if hasattr(reason_code, "is_failure") else reason_code != 0
    if failed:
        log.error("MQTT connection refused: %s", reason_code)
        return
    log.info("Connected to MQTT broker at %s:%s", MQTT_HOST, MQTT_PORT)
    client.subscribe([(T_WRITE, 0), (T_APPEND + "#", 0), (T_OVERWRITE + "#", 0)])
    scan_once(force=True)


def on_disconnect(client, userdata, *args):
    log.warning("Disconnected from MQTT broker, will keep retrying.")


mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)


def start_background():
    try:
        mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, 60)  # retries until the broker is up
        mqtt_client.loop_start()
    except Exception as e:
        log.error("MQTT setup failed: %s", e)
    threading.Thread(target=scan_loop, daemon=True).start()
    try:
        srv = make_server("0.0.0.0", API_PORT, app, threaded=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info("REST API listening on port %d (%s)", API_PORT,
                 "token required" if API_TOKEN else "DISABLED until you set api_token")
    except OSError as e:
        log.error("Could not open REST API port %d: %s", API_PORT, e)


# ---------------------------------------------------------------- web
@app.before_request
def guard_api_port():
    """The sidebar page (ingress) is trusted. The extra REST port needs a token."""
    if request.environ.get("SERVER_PORT") != str(API_PORT):
        return None
    if not request.path.startswith("/api/"):
        abort(404)
    if not API_TOKEN:
        return jsonify({"error": "REST API is off. Set api_token in the add-on options."}), 403
    auth = request.headers.get("Authorization", "")
    given = auth[7:] if auth.lower().startswith("bearer ") else (
        request.headers.get("X-API-Token") or request.args.get("token") or "")
    if not hmac.compare_digest(given.encode(), API_TOKEN.encode()):
        return jsonify({"error": "Invalid or missing token"}), 401
    return None


def read_changelog():
    for p in ("/usr/src/app/CHANGELOG.md", os.path.join(BASE_DIR, "..", "CHANGELOG.md")):
        if os.path.exists(p):
            return read_text(p)
    return "No changelog found."


def current_version():
    m = re.search(r"^##\s+\[?v?(\d+(?:\.\d+)*)", read_changelog(), re.M)
    return m.group(1) if m else "unknown"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["GET"])
def info():
    return jsonify({"version": current_version(), "files_path": DATA_DIR,
                    "mqtt_connected": mqtt_client.is_connected(),
                    "api_enabled": bool(API_TOKEN), "api_port": API_PORT})


@app.route("/api/changelog", methods=["GET"])
def changelog():
    return Response(read_changelog(), mimetype="text/plain")


@app.route("/api/files", methods=["GET"])
def api_list_files():
    return jsonify({"files": list_files()})


@app.route("/api/file/<path:filename>", methods=["GET"])
def read_file(filename):
    path = resolve(filename)
    if not (path and os.path.isfile(path)):
        return jsonify({"error": "File not found"}), 404
    if os.path.getsize(path) > MAX_EDIT_BYTES:
        return jsonify({"error": "File is too large to open in the browser"}), 413
    return jsonify({"filename": rel_name(path), "content": read_text(path)})


@app.route("/api/file/<path:filename>", methods=["POST", "PUT"])
def write_file(filename):
    data = request.get_json(force=True, silent=True)
    if isinstance(data, dict):
        text, mode = data.get("text", ""), data.get("mode", "append")
    else:  # plain text body, handy for curl: --data "hello" ".../api/file/log.txt?mode=append"
        text, mode = request.get_data(as_text=True), request.args.get("mode", "append")
    try:
        rel = do_write(filename, text, mode)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:
        return jsonify({"error": f"Could not write file: {e.strerror or e}"}), 400
    return jsonify({"status": "success", "filename": rel})


@app.route("/api/file/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    if do_delete(filename):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "File not found"}), 404


if __name__ == "__main__":
    start_background()
    app.run(host="0.0.0.0", port=8099)

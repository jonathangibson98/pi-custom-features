#!/usr/bin/env python3
"""Creator & AI Builder - plain-English Home Assistant config builder, AI voice announcements and backups, in one add-on."""
import ast
import asyncio
import json
import logging
import os
import threading
import sys
import platform
import re
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import aiohttp
import yaml
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai_builder")

# Paths can be overridden with env vars so the add-on can be tested off-device.
DATA = Path(os.environ.get("DATA_DIR", "/data"))
WWW = Path(os.environ.get("WWW_DIR", "/app/www"))
CONF = Path(os.environ.get("HA_CONFIG_DIR", "/homeassistant"))

try:
    OPTS = json.load(open(DATA / "options.json"))
except Exception:
    OPTS = {}
logging.getLogger().setLevel(getattr(logging, str(OPTS.get("log_level") or "info").upper(), logging.INFO))

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = "http://supervisor/core/api"
WS_URL = "ws://supervisor/core/websocket"
USER_TOKEN = (OPTS.get("ha_token") or "").strip()
if USER_TOKEN:  # optional long-lived token: talk to Home Assistant directly instead of through the Supervisor
    _base = (OPTS.get("ha_url") or "http://homeassistant:8123").strip().rstrip("/")
    TOKEN = USER_TOKEN
    API = _base + "/api"
    WS_URL = re.sub(r"^http", "ws", _base) + "/api/websocket"
HDR = {"Authorization": f"Bearer {TOKEN}"}

ENTITY = OPTS.get("ai_task_entity") or "ai_task.google_ai_task"
CONFIGURED_ENTITY = ENTITY


def default_ai_task(states):
    """The household default AI Task picked in Personalized Info (select.default_ai_task), or ''."""
    for s in states:
        a = s.get("attributes") or {}
        if s.get("entity_id") in ("select.default_ai_task", "sensor.default_ai_task") or a.get("role") == "default_ai_task":
            v = s.get("state") if str(s.get("state", "")).startswith("ai_task.") else a.get("ai_task_entity")
            if str(v or "").startswith("ai_task."):
                return v
    return ""


async def resolve_entity(app):
    """Keep ENTITY pointing at a real AI Task: the configured one if it exists, else the household default, else the
    first one Home Assistant has. Checked at start and every 5 minutes."""
    global ENTITY
    while True:
        st, states = await ha(app, "GET", "/states")
        if st == 200 and isinstance(states, list):
            ids = [x["entity_id"] for x in states if x["entity_id"].startswith("ai_task.")]
            new = CONFIGURED_ENTITY if CONFIGURED_ENTITY in ids else (default_ai_task(states) or (ids[0] if ids else CONFIGURED_ENTITY))
            if new != ENTITY:
                log.info("AI Task: using %s%s", new, "" if new == CONFIGURED_ENTITY else " (%s isn't in Home Assistant)" % CONFIGURED_ENTITY)
                ENTITY = new
        await asyncio.sleep(300)
TIMEOUT = int(OPTS.get("request_timeout") or 180)


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


def resolve_template_file(value):
    """Path (relative to the HA config folder) where template entities are written."""
    rel = (value or "ai_builder/package.yaml").strip().strip("/")
    if rel.startswith("config/"):
        rel = rel[len("config/"):]
    parts = [p for p in rel.split("/") if p]
    if not parts or ".." in parts or not rel.lower().endswith((".yaml", ".yml")):
        log.warning("Bad template_file %r, using ai_builder/package.yaml", value)
        rel = "ai_builder/package.yaml"
    return rel


def resolve_dir(value, default):
    """An absolute folder under /addon_configs or the HA config folder."""
    v = (value or default).strip()
    if v.startswith("/config/"):
        v = v[len("/config/"):]
    p = Path(os.path.normpath(v if v.startswith("/") else str(CONF / v)))
    allowed = (Path("/addon_configs"), CONF)
    if not any(p == a or a in p.parents for a in allowed):
        log.warning("Folder %r is not allowed, using %s", value, default)
        p = Path(default)
    return p


TEMPLATE_REL = resolve_template_file(OPTS.get("template_file"))
AD_DEFAULT = "/addon_configs/a0d7b954_appdaemon/apps"
AD_DIR = resolve_dir(OPTS.get("appdaemon_apps_dir"), AD_DEFAULT)
PY_DIR = CONF / "pyscript"
PKG_FILE = CONF / TEMPLATE_REL
PKG_DIR = PKG_FILE.parent
STORE = DATA / "templates.json"
HIST = DATA / "history.json"
ANN_SETTINGS = DATA / "announcement_settings.json"
ANN_LIB = DATA / "announcements.json"  # saved announcements: the form state behind every script, so each one can be edited later
FACTS_LIB = DATA / "facts.json"  # saved facts: the form state behind every fact script
FACT_SETTINGS = DATA / "fact_settings.json"
BACKUP_DEFAULT = "/share/ai_builder_backups"
BACKUP_PATH = clean_path(OPTS.get("backup_path") or BACKUP_DEFAULT, BACKUP_DEFAULT, "backup_path")
BACKUP_KEEP = max(1, int(OPTS.get("backup_keep") or 20))
BACKUP_PREFIX = "ai_builder_backup"

HELPER_FIELDS = {
    "input_boolean": ["name", "icon", "initial"],
    "input_number": ["name", "icon", "min", "max", "step", "mode", "unit_of_measurement", "initial"],
    "input_select": ["name", "icon", "options", "initial"],
    "input_text": ["name", "icon", "min", "max", "mode", "pattern", "initial"],
    "input_datetime": ["name", "icon", "has_date", "has_time", "initial"],
    "counter": ["name", "icon", "initial", "step", "minimum", "maximum", "restore"],
    "timer": ["name", "icon", "duration", "restore"],
}
PRIORITY = {"helper": 0, "template": 1, "scene": 2, "script": 2, "pyscript": 3,
            "appdaemon": 3, "automation": 4, "blueprint": 5, "addon": 5}
EDIT_ID_KINDS = ("automation", "scene", "appdaemon", "pyscript", "addon")
TEXT_EXT = (".yaml", ".yml", ".json", ".py", ".sh", ".md", ".txt", ".html", ".js", ".css", ".cfg", ".toml", ".ini")
BACKUPS = DATA / "backups"
HOST_ARCH = {"aarch64": "aarch64", "arm64": "aarch64", "x86_64": "amd64", "amd64": "amd64"}.get(
    platform.machine().lower(), platform.machine())
GOOD_BASE = "ghcr.io/home-assistant/base:latest"
SCHEMA_RE = re.compile(r"^(str|password|email|url|bool|int|float|port|match|list|device|ssl)(\(.*\))?\??$")
MAP_RE = re.compile(r"^(homeassistant_config|addon_config|all_addon_configs|ssl|addons|backup|share|media)(:(rw|ro))?$")
ADDONS_DIR = Path(os.environ.get("ADDONS_DIR", "/addons"))

STOP = set(
    "the and for with that this when then from have has are was will into your you our out any all "
    "turn make create set can please want need would like should every each".split()
)
ENT_RE = re.compile(r"\b([a-z_]+)\.([a-z0-9_]+)\b")


# ---------------------------------------------------------------- helpers
def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))


def errmsg(data):
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or json.dumps(data))[:600]
    return str(data)[:600]


async def ha(app, method, path, body=None, params=None, timeout=30, raw=False):
    try:
        async with app["http"].request(
            method, API + path, json=body, params=params, headers=HDR,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as r:
            txt = await r.text()
            if raw:
                return r.status, txt
            try:
                return r.status, json.loads(txt)
            except ValueError:
                return r.status, txt
    except asyncio.TimeoutError:
        return 0, "Timed out waiting for Home Assistant"
    except aiohttp.ClientError as e:
        return 0, f"Could not reach Home Assistant: {e}"


async def ws_call(app, msg):
    async with app["http"].ws_connect(WS_URL) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": TOKEN})
        r = await ws.receive_json()
        if r.get("type") != "auth_ok":
            raise RuntimeError("WebSocket auth failed")
        msg["id"] = 1
        await ws.send_json(msg)
        while True:
            r = await ws.receive_json()
            if r.get("id") == 1:
                return r


def render_package(store):
    sensors, binaries = [], []
    for e in store.values():
        d = {"name": e["name"], "unique_id": e["unique_id"], "state": e["state"]}
        keys = ["device_class", "icon", "availability"]
        if e["platform"] == "sensor":
            keys += ["unit_of_measurement", "state_class"]
        for k in keys:
            if e.get(k):
                d[k] = e[k]
        if e.get("attributes"):
            d["attributes"] = e["attributes"]
        (binaries if e["platform"] == "binary_sensor" else sensors).append(d)
    block = {}
    if sensors:
        block["sensor"] = sensors
    if binaries:
        block["binary_sensor"] = binaries
    pkg = {"template": [block] if block else []}
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    header = "# Managed by the AI Builder add-on. Edits here get overwritten.\n"
    PKG_FILE.write_text(header + yaml.safe_dump(pkg, sort_keys=False, allow_unicode=True, width=1000))


def package_included():
    """True if configuration.yaml includes our file directly, or includes the folder it lives in."""
    try:
        text = (CONF / "configuration.yaml").read_text()
    except Exception:
        return False
    if TEMPLATE_REL in text:
        return True
    parts = TEMPLATE_REL.split("/")
    for i in range(1, len(parts)):
        folder = "/".join(parts[:i])
        if re.search(r"!include_dir_\w+\s+['\"]?" + re.escape(folder) + r"['\"]?\s*(?:#.*)?$", text, re.M):
            return True
    return False


def add_history(entry):
    h = load_json(HIST, [])
    h.insert(0, {**entry, "time": time.strftime("%Y-%m-%d %H:%M")})
    save_json(HIST, h[:40])


def inside(base, rel):
    rel = str(rel).replace("\\", "/").lstrip("/")
    p = (base / rel).resolve()
    b = base.resolve()
    if p != b and b not in p.parents:
        raise RuntimeError(f"Unsafe path: {rel}")
    return p


def safe_write(path, content, overwrite, mode=None):
    if path.exists() and not overwrite:
        raise FileExistsError(str(path))
    if path.exists():
        BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUPS / f"{time.strftime('%Y%m%d-%H%M%S')}_{str(path).strip('/').replace('/', '_')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mode:
        path.chmod(mode)


class BPLoader(yaml.SafeLoader):
    pass


BPLoader.add_constructor("!input", lambda l, n: l.construct_scalar(n))


def addon_files(cfg):
    f = cfg.get("files") or []
    if isinstance(f, dict):
        f = [{"path": k, "content": v} for k, v in f.items()]
    out = []
    for x in f:
        if isinstance(x, dict) and x.get("path"):
            out.append((str(x["path"]).replace("\\", "/").strip().lstrip("/"), str(x.get("content", ""))))
    return out


def py_error(code, label="Python"):
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"{label} syntax error on line {e.lineno}: {e.msg}"
    return None


def validate_item(it):
    """Return (error, notes) for code-style items. Used for preview and again before writing."""
    k, cfg, notes = it["kind"], it["config"], []
    edit = bool(it.get("edit_id"))
    if k == "appdaemon":
        code = str(cfg.get("code", ""))
        if not code.strip():
            return "No code was written.", notes
        e = py_error(code)
        if e:
            return e, notes
        tree = ast.parse(code)
        classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        if not classes:
            return "The code has no class.", notes
        if not edit:
            if not slug(cfg.get("name", "")):
                return "App needs a name.", notes
            if cfg.get("class") not in classes:
                return f"Class {cfg.get('class')!r} is not in the code (found: {', '.join(classes)}).", notes
        c = classes.get(cfg.get("class")) or next(iter(classes.values()))
        bases = [getattr(b, "attr", getattr(b, "id", "")) for b in c.bases]
        if "Hass" not in bases:
            notes.append("The class doesn't extend hass.Hass, so AppDaemon may not treat it as a Home Assistant app.")
        if "initialize" not in {n.name for n in c.body if isinstance(n, ast.FunctionDef)}:
            notes.append("The class has no initialize() method, so AppDaemon won't do anything with it.")
    elif k == "pyscript":
        code = str(cfg.get("code", ""))
        if not code.strip():
            return "No code was written.", notes
        e = py_error(code)
        if e:
            return e, notes
        if not edit and not slug(cfg.get("name", "")):
            return "Script needs a name.", notes
    elif k == "addon":
        files = addon_files(cfg)
        if not files:
            return "No files in the add-on.", notes
        if len(files) > 40 or sum(len(c) for _, c in files) > 300_000:
            return "That add-on is too big (40 files or 300 KB max).", notes
        for p, c in files:
            parts = p.split("/")
            base = parts[-1]
            if ".." in parts or not base:
                return f"Unsafe file path: {p}", notes
            if not (base == "Dockerfile" or base.lower().endswith(TEXT_EXT)):
                return f"File type not allowed: {p}", notes
            if base.endswith(".py"):
                e = py_error(c, p)
                if e:
                    return e, notes
        names = {p for p, _ in files}
        cf = next(((p, c) for p, c in files if p in ("config.yaml", "config.yml")), None)
        if cf:
            try:
                y = yaml.safe_load(cf[1])
            except yaml.YAMLError as e:
                return f"config.yaml is not valid YAML: {e}", notes
            if not isinstance(y, dict):
                return "config.yaml is not a mapping.", notes
            missing = [x for x in ("name", "version", "slug", "description") if x not in y]
            if missing:
                return "config.yaml is missing: " + ", ".join(missing), notes
            if not isinstance(y.get("version"), str):
                return "config.yaml: version must be a quoted string like \"1.0.0\".", notes
            for key, ok in (("startup", ("initialize", "system", "services", "application", "once")),
                            ("boot", ("auto", "manual", "manual_only"))):
                if key in y and y[key] not in ok:
                    return f"config.yaml: {key} must be one of {', '.join(ok)}.", notes
            opts, sch = y.get("options"), y.get("schema")
            if isinstance(opts, dict) and opts:
                if not isinstance(sch, dict):
                    return "config.yaml has options but no schema. Every option needs a schema entry.", notes
                miss = [k for k in opts if k not in sch]
                if miss:
                    return "config.yaml: these options are missing from schema: " + ", ".join(miss), notes
            if isinstance(sch, dict):
                for k, v in sch.items():
                    if isinstance(v, str) and not SCHEMA_RE.match(v):
                        return f"config.yaml: schema type {v!r} for {k} isn't valid (use str, int, float, bool, password, url, port, email, list(a|b), match(regex), add ? if optional).", notes
            if isinstance(y.get("map"), list):
                badmap = [x for x in y["map"] if not MAP_RE.match(str(x))]
                if badmap:
                    return "config.yaml: invalid map entries " + ", ".join(map(str, badmap)) + ". Valid: homeassistant_config, addon_config, all_addon_configs, ssl, addons, backup, share, media.", notes
            if isinstance(y.get("arch"), list) and HOST_ARCH not in y["arch"]:
                return f"config.yaml: arch must include {HOST_ARCH}, which is what this system runs.", notes
            dk = next((c for p, c in files if p == "Dockerfile"), "")
            if dk and not re.search(r"home-assistant/", dk) and "image" not in y:
                notes.append("The Dockerfile isn't built on a Home Assistant base image, so bashio and with-contenv won't exist.")
            if "Dockerfile" not in names and "image" not in y and not edit:
                notes.append("No Dockerfile and no image set. The add-on can't build.")
        elif not edit:
            return "The add-on has no config.yaml.", notes
    elif k == "blueprint":
        content = str(cfg.get("content", ""))
        try:
            y = yaml.load(content, Loader=BPLoader)
        except yaml.YAMLError as e:
            return f"Blueprint is not valid YAML: {e}", notes
        bp = (y or {}).get("blueprint") if isinstance(y, dict) else None
        if not isinstance(bp, dict) or not bp.get("name"):
            return "Blueprint needs a blueprint: section with a name.", notes
        if bp.get("domain") != cfg.get("domain", "automation"):
            return "The blueprint's domain doesn't match.", notes
    return None, notes


def fix_addon_files(files, edit=False):
    """Repair the known ways AI-written add-ons fail on this system. Returns (files, list of fixes). Idempotent."""
    fixes = []
    out = dict(files)

    for p in list(out):
        if p.lower() in ("build.yaml", "build.yml", "build.json"):
            del out[p]
            fixes.append("Removed build.yaml (legacy per-architecture build file that points at images that don't exist).")

    if "run.sh" in out:
        lines = out["run.sh"].split("\n")
        if not lines[0].startswith("#!/usr/bin/with-contenv bashio"):
            if lines[0].startswith("#!"):
                lines[0] = "#!/usr/bin/with-contenv bashio"
            else:
                lines.insert(0, "#!/usr/bin/with-contenv bashio")
            out["run.sh"] = "\n".join(lines)
            fixes.append("Set run.sh's first line to #!/usr/bin/with-contenv bashio so options and the Supervisor token are available.")

    if "Dockerfile" in out:
        d = orig = out["Dockerfile"]
        d = re.sub(r"ghcr\.io/home-assistant/(?:amd64|aarch64|armv7|armhf|i386|\{arch\})-base[\w.-]*(?::[\w.-]+)?", GOOD_BASE, d)
        if d != orig:
            fixes.append("Replaced a per-architecture base image with the multi-arch one (" + GOOD_BASE + "). The old one fails with 'no match for platform' on this system.")
        if "BUILD_FROM" not in d and re.search(r"^FROM\s+\S*home-assistant\S*", d, re.M):
            d = re.sub(r"^FROM\s+\S*home-assistant\S*", "ARG BUILD_FROM=" + GOOD_BASE + "\nFROM ${BUILD_FROM}", d, count=1, flags=re.M)
            fixes.append("Made the Dockerfile start from ${BUILD_FROM}.")
        d2 = re.sub(r"(pip3?\s+install)(?![^\n]*--break-system-packages)", r"\1 --break-system-packages", d)
        if d2 != d:
            d = d2
            fixes.append("Added --break-system-packages to pip install (Alpine blocks plain pip installs).")
        if "/run.sh" in d and "chmod" not in d:
            if re.search(r"^CMD", d, re.M):
                d = re.sub(r"^(CMD)", "RUN chmod a+x /run.sh\n\\1", d, count=1, flags=re.M)
            else:
                d = d.rstrip("\n") + "\nRUN chmod a+x /run.sh\n"
            fixes.append("Added RUN chmod a+x /run.sh.")
        out["Dockerfile"] = d

    cname = next((p for p in ("config.yaml", "config.yml") if p in out), None)
    if cname:
        c = orig = out[cname]
        c = re.sub(r"^version:\s*([0-9][0-9.]*)\s*$", r'version: "\1"', c, flags=re.M)
        c = re.sub(r"^(\s*-\s*)(?:config)((?::(?:rw|ro))?)\s*$", r"\1homeassistant_config\2", c, flags=re.M)
        c = re.sub(r"^(\s*-\s*)addon_configs((?::(?:rw|ro))?)\s*$", r"\1all_addon_configs\2", c, flags=re.M)
        if c != orig:
            fixes.append("Corrected config.yaml (quoted the version and/or fixed folder-map names to homeassistant_config / all_addon_configs).")
        try:
            y = yaml.safe_load(c) or {}
        except yaml.YAMLError:
            y = None
        if isinstance(y, dict):
            arch = y.get("arch")
            bad = (not isinstance(arch, list) or not arch or HOST_ARCH not in arch
                   or any(a in ("armv7", "armhf", "i386") for a in arch))
            if bad and not (edit and arch is None):
                new = "arch:\n  - aarch64\n  - amd64\n"
                if re.search(r"^arch:\s*\[.*\]\s*$", c, re.M):
                    c = re.sub(r"^arch:\s*\[.*\]\s*$", new.rstrip("\n"), c, count=1, flags=re.M)
                elif re.search(r"^arch:\s*\n(?:\s+-.*\n?)+", c, re.M):
                    c = re.sub(r"^arch:\s*\n(?:\s+-.*\n?)+", new, c, count=1, flags=re.M)
                else:
                    c = c.rstrip("\n") + "\n" + new
                fixes.append("Set arch to aarch64 and amd64 (old 32-bit architectures are gone, and your system must be listed).")
            if "run.sh" in out and y.get("init") is not False:
                if re.search(r"^init:.*$", c, re.M):
                    c = re.sub(r"^init:.*$", "init: false", c, count=1, flags=re.M)
                else:
                    c = c.rstrip("\n") + "\ninit: false\n"
                fixes.append("Added init: false (without it the add-on crashes at start with a pid 1 error).")
        out[cname] = c
    return list(out.items()), sorted(set(fixes), key=fixes.index)


def describe(it):
    c, k = it["config"], it["kind"]
    if k == "appdaemon":
        name = slug(c.get("name") or "app")
        out = []
        if not it.get("edit_id"):
            args = c.get("args") if isinstance(c.get("args"), dict) else {}
            out.append(f"# apps/ai_builder/{name}.yaml\n" + yaml.safe_dump(
                {name: {"module": name, "class": c.get("class"), **args}}, sort_keys=False, allow_unicode=True))
        out.append(f"# {it.get('edit_id') or 'apps/ai_builder/' + name + '.py'}\n" + str(c.get("code", "")))
        return "\n".join(out)
    if k == "pyscript":
        return f"# pyscript/{it.get('edit_id') or slug(c.get('name') or 'script') + '.py'}\n" + str(c.get("code", ""))
    if k == "addon":
        return "\n\n".join(f"# ===== {p} =====\n{x}" for p, x in addon_files(c))
    if k == "blueprint":
        return str(c.get("content", ""))
    return yaml.safe_dump(c, sort_keys=False, allow_unicode=True, width=100)


# ---------------------------------------------------------------- AI prompt
def tokens(text):
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) < 3 or w in STOP:
            continue
        out.add(w)
        if w.endswith("s") and len(w) > 3:
            out.add(w[:-1])
    return out


def build_context(states, services, text):
    toks = tokens(text)
    scored = []
    for s in states:
        eid = s["entity_id"]
        name = (s.get("attributes") or {}).get("friendly_name", "") or ""
        hay = f"{eid} {name}".lower()
        score = sum(1 for t in toks if t in hay)
        if score:
            scored.append((score, eid, name, str(s["state"])[:30]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    relevant = [f"{e} | {n} | {st}" for _, e, n, st in scored[:70]]

    always_domains = {"person", "zone", "input_boolean", "input_number", "input_select",
                      "input_text", "input_datetime", "timer", "counter", "ai_task"}
    always = []
    for s in states:
        if s["entity_id"].split(".")[0] in always_domains:
            n = (s.get("attributes") or {}).get("friendly_name", "") or ""
            always.append(f"{s['entity_id']} | {n} | {str(s['state'])[:30]}")
    domains = Counter(s["entity_id"].split(".")[0] for s in states)
    notify = sorted(k for k in services if k.startswith("notify."))
    return (
        "ENTITIES MOST RELEVANT TO THE REQUEST (entity_id | name | state):\n" + "\n".join(relevant or ["(none matched)"])
        + "\n\nPEOPLE, ZONES AND HELPERS:\n" + "\n".join(always[:80] or ["(none)"])
        + "\n\nNOTIFY SERVICES: " + ", ".join(notify[:40])
        + "\n\nENTITY COUNT BY DOMAIN: " + ", ".join(f"{d}={c}" for d, c in domains.most_common(30))
    )


RULES = """You are an expert Home Assistant configuration engineer. Home Assistant version: {version}. Temperature unit: {unit}. Time zone: {tz}.
The person asking is NOT a programmer, so write the summary in plain English.

Reply with ONE JSON object and nothing else (no markdown fences, no commentary):
{{
  "summary": "1-3 plain-English sentences describing what you built",
  "warnings": ["anything the person should know or double-check"],
  "items": [ {{"kind": "...", "summary": "what this item does", "id": "...", "config": {{...}} }} ]
}}

Item kinds and their config:
- "automation": modern syntax. Keys: alias, description, mode, triggers (each with "trigger": "state|numeric_state|time|time_pattern|sun|zone|event|template|..."), conditions (each with "condition": ...), actions (each with "action": "domain.service" or other action types like choose/if/delay/repeat/wait_for_trigger). Example:
  {{"alias":"Fan on when hot","description":"","mode":"single","triggers":[{{"trigger":"numeric_state","entity_id":"sensor.x","above":76}}],"conditions":[],"actions":[{{"action":"fan.turn_on","target":{{"entity_id":"fan.y"}}}}]}}
- "script": top-level "id" is a snake_case slug. config keys: alias, description, mode, sequence (list of actions).
- "template": a template sensor or binary sensor. config keys: platform ("sensor" or "binary_sensor"), name, unique_id (snake_case), state (a Jinja template string), and optionally unit_of_measurement, device_class, state_class (sensors only), icon, availability (template), attributes (object of name -> template string). Binary sensor state must render to true or false. Use filters like | float(0) and default values so it never errors.
- "helper": config keys: type (one of input_boolean, input_number, input_select, input_text, input_datetime, counter, timer), name, and the fields that type needs (input_number: min, max, step, mode, unit_of_measurement; input_select: options list; input_datetime: has_date, has_time; timer: duration like "00:05:00"; etc).
- "scene": config keys: name, optional icon, entities (object of entity_id -> state string, or -> object with state plus attributes such as brightness, color_temp, rgb_color, position). Only include entities that should change.
- "appdaemon": an AppDaemon 4 app. config keys: name (snake_case, used as the file and module name), class (CamelCase), args (object of settings passed to the app, optional), code (full Python source). Use `import appdaemon.plugins.hass.hassapi as hass`, `class X(hass.Hass)`, an `initialize(self)` method, and self.listen_state / run_daily / run_every / call_service / get_state / turn_on etc. Read settings from self.args.
- "pyscript": a pyscript file. config keys: name (snake_case), code (full Python source). Use pyscript features: @service, @state_trigger, @time_trigger, @event_trigger, state.get(), state.set(), task.sleep(), log.info(), and call services as plain functions like light.turn_on(entity_id="light.x"). No imports are needed for those.
- "blueprint": config keys: domain ("automation" or "script"), filename (snake_case), content (full blueprint YAML as a string, using !input for inputs).
- "addon": a Home Assistant add-on. config keys: slug (snake_case), files (list of {{"path": "config.yaml", "content": "..."}}). Always include config.yaml (name, version, slug, description, arch [aarch64, amd64], startup, boot, options, schema, and map/ingress/panel settings as needed), Dockerfile (ARG BUILD_FROM=ghcr.io/home-assistant/base:latest, FROM ${{BUILD_FROM}}, apk add what you need, COPY files, COPY run.sh /run.sh, RUN chmod a+x /run.sh, CMD ["/run.sh"]), run.sh (#!/usr/bin/with-contenv bashio, then exec the program), README.md, DOCS.md and CHANGELOG.md. IMPORTANT: when run.sh uses with-contenv, config.yaml MUST contain `init: false`. Options are read from /data/options.json. For a web UI use ingress: true with ingress_port, and use relative URLs in the page. Access Home Assistant with homeassistant_api: true and the SUPERVISOR_TOKEN env var against http://supervisor/core/api. No binary files.
- "answer": use when the person asked a question, the request is unclear, or it cannot be done. config: {{"text": "your answer"}}.

Rules:
- Code goes inside JSON strings, so escape newlines and quotes correctly. The JSON must parse.
- When editing existing code, return the FULL updated file (for add-ons, return every file you changed or added, in full), keep everything the person didn't ask to change, and for add-ons bump the version and add a CHANGELOG entry.
- A request can need several items (for example helpers + a template sensor + an automation). Return all of them in "items".
- Use ONLY entity_ids from the lists below. If something needed is missing, still write the config with your best guess and add a warning naming the missing entity.
- Only use real Home Assistant actions (services). Never invent any.
- Prefer built-in features over complicated templates. Keep it simple and reliable.
- Notifications: use a notify service from the list when one fits.
"""



KNOWHOW = """
VERIFIED FACTS ABOUT THIS SYSTEM (follow these exactly; they come from real failures):
Add-ons
- This system's CPU is @@ARCH@@. Never hard-code any architecture in an image name.
- The ONLY base image that works is ghcr.io/home-assistant/base:latest (multi-arch). Images named amd64-base, aarch64-base, armv7-base, or *-base-python do NOT work ("no match for platform"). Do not create build.yaml.
- Known-good Dockerfile:
  ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
  FROM ${BUILD_FROM}
  RUN apk add --no-cache python3 py3-aiohttp py3-yaml
  WORKDIR /app
  COPY main.py /app/
  COPY run.sh /run.sh
  RUN chmod a+x /run.sh
  CMD [ "/run.sh" ]
- Known-good run.sh: first line #!/usr/bin/with-contenv bashio, then: exec python3 -u /app/main.py. config.yaml MUST contain init: false.
- Install Python libraries with apk when possible (py3-flask, py3-aiohttp, py3-requests, py3-yaml, py3-paho-mqtt). If pip is unavoidable, use pip install --break-system-packages.
- config.yaml: version must be a quoted string. arch is [aarch64, amd64] only. startup is one of initialize, system, services, application, once. boot is auto, manual or manual_only.
- Valid map entries only: homeassistant_config (mounted at /homeassistant), addon_config (the add-on's own folder, at /config), all_addon_configs (at /addon_configs), ssl, addons, backup, share, media. Never use "config".
- Every key in options needs a matching schema entry. Schema types: str, int, float, bool, password, url, port, email, list(a|b), match(regex); add ? for optional. Options are read from /data/options.json. Persistent data lives in /data.
- Home Assistant API from inside an add-on: needs homeassistant_api: true, then http://supervisor/core/api with header Authorization: Bearer $SUPERVISOR_TOKEN. WebSocket: ws://supervisor/core/websocket. Supervisor API needs hassio_api: true.
- Web UI: ingress: true, ingress_port: 8099, listen on 0.0.0.0, use only relative URLs in the page (no leading slash), set panel_icon and panel_title.
Home Assistant templates and code
- A state is limited to 255 characters. Put long text in an attribute.
- There is no from_yaml filter. from_json and to_json exist.
- Always use defaults in templates (| float(0), | default('')).
- pyscript can only import modules if allow_all_imports is true in its config; prefer pyscript's built-ins.
- AppDaemon callbacks look like def cb(self, entity, attribute, old, new, **kwargs).
"""


def build_prompt(text, kind, ctx, existing, target, previous, feedback, cfg):
    p = RULES.format(
        version=cfg.get("version", "recent"),
        unit=(cfg.get("unit_system") or {}).get("temperature", "unknown"),
        tz=cfg.get("time_zone", "unknown"),
    )
    if kind and kind != "auto":
        p += f"\nThe person specifically wants this built as: {kind}.\n"
    p += KNOWHOW.replace("@@ARCH@@", HOST_ARCH) + "\n" + ctx + "\n"
    if existing is not None and target:
        p += (
            f"\nTHE PERSON IS EDITING AN EXISTING {target['kind'].upper()} (id: {target['id']}). Current config:\n"
            + json.dumps(existing, indent=1)
            + "\nApply their change and return the FULL updated config as a single item of the same kind. "
            "Keep everything they did not ask to change.\n"
        )
    p += f"\nREQUEST FROM THE PERSON:\n{text}\n"
    if previous:
        p += (
            "\nYOUR PREVIOUS ANSWER:\n" + json.dumps(previous, indent=1)
            + f"\n\nTHE PERSON'S FEEDBACK / THE PROBLEM TO FIX:\n{feedback}\n"
            "Return the complete corrected JSON object (all items), not just the changes.\n"
        )
    return p


def extract_json(t):
    t = (t or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        return json.loads(t[i : j + 1])
    raise ValueError("no JSON found")


async def ask_ai(app, prompt):
    st, data = await ha(
        app, "POST", "/services/ai_task/generate_data",
        {"entity_id": ENTITY, "task_name": "ha_builder", "instructions": prompt},
        params={"return_response": "true"}, timeout=TIMEOUT,
    )
    if st != 200:
        raise RuntimeError(f"AI task call failed: {errmsg(data)}")
    sr = data.get("service_response") if isinstance(data, dict) else None
    out = (sr or {}).get("data")
    if out is None:
        return ""
    return out if isinstance(out, str) else json.dumps(out)


# ---------------------------------------------------------------- checks
def find_unknown(config, known_ids, domains, services):
    found = set()

    def walk(x):
        if isinstance(x, str):
            for m in ENT_RE.finditer(x.replace("states.", "")):
                full = m.group(0)
                if m.group(1) in domains and full not in known_ids and full not in services:
                    found.add(full)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(config)
    return sorted(found)


def normalize(parsed, target):
    if isinstance(parsed, list):
        parsed = {"items": parsed}
    items = parsed.get("items")
    if items is None and "config" in parsed:
        items = [parsed]
    items = [i for i in (items or []) if isinstance(i, dict)]
    out, used_target = [], False
    for it in items:
        kind = str(it.get("kind", "")).lower().replace(" ", "_")
        if kind in ("template_sensor", "template_entity", "template_binary_sensor"):
            kind = "template"
        if kind not in PRIORITY and kind != "answer":
            kind = "answer"
        cfg = it.get("config") if isinstance(it.get("config"), dict) else {}
        item = {"kind": kind, "summary": it.get("summary", ""), "id": it.get("id"), "config": cfg}
        if target and not used_target and kind == target["kind"]:
            used_target = True
            if kind in EDIT_ID_KINDS:
                item["edit_id"] = target["id"]
            elif kind == "script":
                item["id"] = target["id"]
            elif kind == "template":
                cfg["unique_id"] = target["id"]
        out.append(item)
    return {"summary": parsed.get("summary", ""), "warnings": parsed.get("warnings") or [], "items": out}


async def enrich(app, result, states, services):
    known = {s["entity_id"] for s in states}
    domains = {e.split(".")[0] for e in known}
    for it in result["items"]:
        it["checks"] = {"unknown": [], "preview": None, "error": None}
        if it["kind"] == "answer":
            continue
        if it["kind"] == "addon":
            files, fixes = fix_addon_files(addon_files(it["config"]), bool(it.get("edit_id")))
            it["config"]["files"] = [{"path": p, "content": c} for p, c in files]
            it["checks"]["fixes"] = fixes
        it["yaml"] = describe(it)
        if it["kind"] not in ("addon", "blueprint"):
            it["checks"]["unknown"] = find_unknown(it["config"], known, domains, services)
        if it["kind"] in ("appdaemon", "pyscript", "addon", "blueprint"):
            err, notes = validate_item(it)
            it["checks"]["error"] = err
            it["checks"]["notes"] = notes
        if it["kind"] == "template" and it["config"].get("state"):
            st, txt = await ha(app, "POST", "/template", {"template": str(it["config"]["state"])}, raw=True)
            if st == 200:
                it["checks"]["preview"] = txt.strip()[:200]
            else:
                it["checks"]["error"] = txt.strip()[:400]
    return result


async def load_target(app, kind, tid):
    if kind == "automation":
        st, d = await ha(app, "GET", f"/config/automation/config/{tid}")
    elif kind == "script":
        st, d = await ha(app, "GET", f"/config/script/config/{tid}")
    elif kind == "template":
        d = load_json(STORE, {}).get(tid)
        return d if d else None
    elif kind == "scene":
        st, d = await ha(app, "GET", f"/config/scene/config/{tid}")
    elif kind == "appdaemon":
        p = inside(AD_DIR, tid)
        return {"file": tid, "code": p.read_text()}
    elif kind == "pyscript":
        return {"name": tid, "code": inside(PY_DIR, f"{tid}.py").read_text()}
    elif kind == "addon":
        base = inside(ADDONS_DIR, tid)
        files, total = [], 0
        for f in sorted(base.rglob("*")):
            if f.is_file() and (f.name == "Dockerfile" or f.suffix.lower() in TEXT_EXT) and "__pycache__" not in f.parts:
                txt = f.read_text(errors="replace")
                total += len(txt)
                if total > 150_000:
                    break
                files.append({"path": str(f.relative_to(base)), "content": txt})
        return {"slug": tid, "files": files}
    else:
        return None
    if st != 200:
        raise RuntimeError(f"Could not load that {kind} (it may be defined in YAML): {errmsg(d)}")
    return d


# ---------------------------------------------------------------- routes
def page(name):
    async def handler(request):
        return web.Response(text=(WWW / name).read_text(), content_type="text/html",
                            headers={"Cache-Control": "no-store"})
    return handler


def asset(name, ctype):
    async def handler(request):
        return web.Response(text=(WWW / name).read_text(encoding="utf-8"), content_type=ctype,
                            headers={"Cache-Control": "no-store"})
    return handler


INGRESS_IP = "172.30.32.2"  # only the Home Assistant ingress gateway may talk to us


@web.middleware
async def ingress_only(request, handler):
    if not os.environ.get("DEV") and request.remote != INGRESS_IP:
        return web.json_response({"error": "ingress only"}, status=403)
    return await handler(request)


async def status(request):
    app = request.app
    st, states = await ha(app, "GET", "/states")
    st2, cfg = await ha(app, "GET", "/config")
    ai_ok = isinstance(states, list) and any(s["entity_id"] == ENTITY for s in states)
    return web.json_response({
        "entity": ENTITY,
        "entity_found": ai_ok,
        "ha_ok": st == 200,
        "version": cfg.get("version") if isinstance(cfg, dict) else None,
        "package_included": package_included(),
        "template_file": TEMPLATE_REL,
        "appdaemon_dir": str(AD_DIR),
        "appdaemon_found": AD_DIR.parent.exists(),
        "pyscript_found": PY_DIR.exists(),
    })


async def generate(request):
    app = request.app
    b = await request.json()
    text = (b.get("request") or "").strip()
    feedback = (b.get("feedback") or "").strip()
    if not text:
        return web.json_response({"error": "Type what you want first."})
    target = b.get("target") or None
    previous = b.get("previous") or None

    st, states = await ha(app, "GET", "/states")
    if st != 200 or not isinstance(states, list):
        return web.json_response({"error": f"Could not read Home Assistant states: {errmsg(states)}"})
    st, svc = await ha(app, "GET", "/services")
    services = set()
    if isinstance(svc, list):
        for d in svc:
            for s in (d.get("services") or {}):
                services.add(f"{d['domain']}.{s}")
    st, cfg = await ha(app, "GET", "/config")
    cfg = cfg if isinstance(cfg, dict) else {}

    existing = None
    if target:
        try:
            existing = await load_target(app, target["kind"], target["id"])
        except Exception as e:
            return web.json_response({"error": f"Could not load that to edit: {e}"})

    ctx = build_context(states, services, text + " " + feedback) + made_context()
    prompt = build_prompt(text, b.get("kind", "auto"), ctx, existing, target, previous, feedback, cfg)

    parsed, last_raw = None, ""
    for attempt in range(2):
        try:
            last_raw = await ask_ai(app, prompt if attempt == 0 else
                                    prompt + "\n\nYour last reply was not valid JSON. Reply with ONLY the JSON object.")
            parsed = extract_json(last_raw)
            break
        except ValueError:
            log.warning("AI reply was not JSON (attempt %s)", attempt + 1)
        except Exception as e:
            return web.json_response({"error": str(e)})
    if parsed is None:
        return web.json_response({"error": "The AI answered, but not in a usable format. Try again or reword it.",
                                  "raw": last_raw[:1500]})
    result = normalize(parsed, target)
    if not result["items"]:
        return web.json_response({"error": "The AI didn't return anything to build.", "raw": last_raw[:1500]})
    result = await enrich(app, result, states, services)
    return web.json_response(result)


async def create_automation(app, it):
    cfg = dict(it["config"])
    aid = str(it.get("edit_id") or int(time.time() * 1000))
    cfg["id"] = aid
    cfg.setdefault("alias", "AI automation")
    cfg.setdefault("mode", "single")
    st, d = await ha(app, "POST", f"/config/automation/config/{aid}", cfg)
    if st != 200:
        raise RuntimeError(errmsg(d))
    entity = None
    for _ in range(4):
        await asyncio.sleep(1)
        _, states = await ha(app, "GET", "/states")
        for s in states if isinstance(states, list) else []:
            if s["entity_id"].startswith("automation.") and (s.get("attributes") or {}).get("id") == aid:
                entity = s["entity_id"]
        if entity:
            break
    return {"entity": entity, "name": cfg["alias"]}


async def create_script(app, it):
    cfg = dict(it["config"])
    cfg.pop("id", None)
    cfg.setdefault("alias", "AI script")
    sid = slug(it.get("id") or cfg["alias"])
    st, d = await ha(app, "POST", f"/config/script/config/{sid}", cfg)
    if st != 200:
        raise RuntimeError(errmsg(d))
    return {"entity": f"script.{sid}", "name": cfg["alias"]}


async def create_template(app, it):
    cfg = it["config"]
    platform = cfg.get("platform", "sensor")
    if platform not in ("sensor", "binary_sensor"):
        raise RuntimeError("Template platform must be sensor or binary_sensor")
    if not cfg.get("name") or not cfg.get("state"):
        raise RuntimeError("Template needs a name and a state template")
    uid = slug(cfg.get("unique_id") or cfg["name"])
    entry = {"platform": platform, "name": cfg["name"], "unique_id": uid, "state": str(cfg["state"])}
    for k in ("unit_of_measurement", "device_class", "state_class", "icon", "availability", "attributes"):
        if cfg.get(k):
            entry[k] = cfg[k]
    store = load_json(STORE, {})
    store[uid] = entry
    save_json(STORE, store)
    render_package(store)
    st, d = await ha(app, "POST", "/services/template/reload", {})
    if st != 200:
        raise RuntimeError(f"Saved, but template reload failed: {errmsg(d)}")
    return {"entity": f"{platform}.{slug(cfg['name'])}", "name": cfg["name"], "needs_setup": not package_included()}


async def create_helper(app, it):
    cfg = it["config"]
    t = cfg.get("type")
    if t not in HELPER_FIELDS:
        raise RuntimeError(f"Unsupported helper type: {t}")
    fields = {k: cfg[k] for k in HELPER_FIELDS[t] if k in cfg}
    if "name" not in fields:
        raise RuntimeError("Helper needs a name")
    r = await ws_call(app, {"type": f"{t}/create", **fields})
    if not r.get("success"):
        raise RuntimeError((r.get("error") or {}).get("message", "Helper creation failed"))
    hid = (r.get("result") or {}).get("id") or slug(fields["name"])
    return {"entity": f"{t}.{hid}", "name": fields["name"]}


async def create_scene(app, it):
    cfg = it["config"]
    if not cfg.get("name") or not isinstance(cfg.get("entities"), dict) or not cfg["entities"]:
        raise RuntimeError("A scene needs a name and at least one entity")
    sid = str(it.get("edit_id") or int(time.time() * 1000))
    body = {"id": sid, "name": cfg["name"], "entities": cfg["entities"]}
    if cfg.get("icon"):
        body["icon"] = cfg["icon"]
    st, d = await ha(app, "POST", f"/config/scene/config/{sid}", body)
    if st != 200:
        raise RuntimeError(errmsg(d))
    return {"entity": f"scene.{slug(cfg['name'])}", "name": cfg["name"]}


async def create_appdaemon(app, it):
    err, _ = validate_item(it)
    if err:
        raise RuntimeError(err)
    if not AD_DIR.parent.exists():
        raise RuntimeError(f"AppDaemon folder not found at {AD_DIR}. Set appdaemon_apps_dir in this add-on's Configuration tab.")
    cfg, ow = it["config"], bool(it.get("overwrite"))
    if it.get("edit_id"):
        p = inside(AD_DIR, it["edit_id"])
        safe_write(p, str(cfg["code"]), True)
        return {"name": p.stem, "note": "AppDaemon reloads the app on its own. Check the AppDaemon log."}
    name = slug(cfg["name"])
    sub = AD_DIR / "ai_builder"
    py, yml = sub / f"{name}.py", sub / f"{name}.yaml"
    for other in AD_DIR.rglob(f"{name}.py"):
        if other != py:
            raise RuntimeError(f"A module named {name} already exists at {other}. Use a different name.")
    if (py.exists() or yml.exists()) and not ow:
        raise FileExistsError(str(py))
    args = cfg.get("args") if isinstance(cfg.get("args"), dict) else {}
    entry = {name: {"module": name, "class": cfg["class"], **{k: v for k, v in args.items() if k not in ("module", "class")}}}
    safe_write(py, str(cfg["code"]), ow)
    safe_write(yml, yaml.safe_dump(entry, sort_keys=False, allow_unicode=True), ow)
    return {"name": name, "note": f"Wrote apps/ai_builder/{name}.py and .yaml. AppDaemon picks it up automatically. Check the AppDaemon log."}


async def create_pyscript(app, it):
    err, _ = validate_item(it)
    if err:
        raise RuntimeError(err)
    if not PY_DIR.exists():
        raise RuntimeError("No /config/pyscript folder. Install the Pyscript integration first.")
    cfg = it["config"]
    name = it.get("edit_id") or slug(cfg["name"])
    safe_write(inside(PY_DIR, f"{name}.py"), str(cfg["code"]), bool(it.get("overwrite") or it.get("edit_id")))
    st, _ = await ha(app, "POST", "/services/pyscript/reload", {})
    note = f"Wrote pyscript/{name}.py." + ("" if st == 200 else " Couldn't call pyscript.reload; reload it yourself.")
    return {"name": name, "note": note}


async def create_addon(app, it):
    cfg = it["config"]
    files, _ = fix_addon_files(addon_files(cfg), bool(it.get("edit_id")))
    cfg["files"] = [{"path": p, "content": c} for p, c in files]
    err, _ = validate_item(it)
    if err:
        raise RuntimeError(err)
    folder = it.get("edit_id") or slug(cfg.get("slug") or "")
    if not folder:
        cf = next((c for p, c in files if p in ("config.yaml", "config.yml")), "")
        folder = slug((yaml.safe_load(cf) or {}).get("slug", "")) if cf else ""
    if not folder:
        raise RuntimeError("The add-on needs a slug")
    base = inside(ADDONS_DIR, folder)
    ow = bool(it.get("overwrite") or it.get("edit_id"))
    if base.exists() and not ow:
        raise FileExistsError(str(base))
    for p, c in files:
        safe_write(inside(base, p), c, True, 0o755 if p.endswith(".sh") else None)
    return {"name": folder, "note": f"Wrote /addons/{folder}. Now open the add-on store (called Apps in newer versions), use the menu, Check for updates, then find it under Local add-ons."}


async def create_blueprint(app, it):
    err, _ = validate_item(it)
    if err:
        raise RuntimeError(err)
    cfg = it["config"]
    domain = cfg.get("domain", "automation")
    fname = slug(cfg.get("filename") or "blueprint")
    safe_write(CONF / "blueprints" / domain / "ai_builder" / f"{fname}.yaml", str(cfg["content"]), bool(it.get("overwrite")))
    return {"name": fname, "note": f"Saved. Find it under Settings, Automations, Blueprints (domain: {domain})."}


async def create(request):
    app = request.app
    b = await request.json()
    it = b.get("item") or {}
    kind = it.get("kind")
    it["overwrite"] = bool(b.get("overwrite"))
    fn = {"automation": create_automation, "script": create_script, "template": create_template,
          "helper": create_helper, "scene": create_scene, "appdaemon": create_appdaemon,
          "pyscript": create_pyscript, "addon": create_addon, "blueprint": create_blueprint}.get(kind)
    if not fn:
        return web.json_response({"ok": False, "error": "Nothing to create for this item."})
    try:
        res = await fn(app, it)
    except FileExistsError as e:
        return web.json_response({"ok": False, "exists": True,
                                  "error": f"{e} already exists."})
    except Exception as e:
        log.exception("create failed")
        return web.json_response({"ok": False, "error": str(e)})
    add_history({"kind": kind, "name": res.get("name"), "entity": res.get("entity")})
    return web.json_response({"ok": True, **res})


async def targets(request):
    app = request.app
    _, states = await ha(app, "GET", "/states")
    out = []
    for s in states if isinstance(states, list) else []:
        d, _, rest = s["entity_id"].partition(".")
        a = s.get("attributes") or {}
        name = a.get("friendly_name") or s["entity_id"]
        if d == "automation" and a.get("id"):
            out.append({"kind": "automation", "id": a["id"], "name": name})
        elif d == "script":
            out.append({"kind": "script", "id": rest, "name": name})
        elif d == "scene" and a.get("id"):
            out.append({"kind": "scene", "id": str(a["id"]), "name": name})
    for uid, e in load_json(STORE, {}).items():
        out.append({"kind": "template", "id": uid, "name": e["name"]})
    try:
        for f in sorted(AD_DIR.rglob("*.py")):
            if "__pycache__" not in f.parts:
                rel = str(f.relative_to(AD_DIR))
                out.append({"kind": "appdaemon", "id": rel, "name": rel})
    except OSError:
        pass
    try:
        for f in sorted(PY_DIR.glob("*.py")):
            out.append({"kind": "pyscript", "id": f.stem, "name": f.name})
    except OSError:
        pass
    try:
        for d in sorted(ADDONS_DIR.iterdir()):
            if d.is_dir() and ((d / "config.yaml").exists() or (d / "config.yml").exists()):
                out.append({"kind": "addon", "id": d.name, "name": d.name})
    except OSError:
        pass
    out.sort(key=lambda x: (x["kind"], x["name"].lower()))
    return web.json_response(out)


async def mine(request):
    """What the Builder made, with the names Home Assistant shows now (so a rename made in HA shows up here too),
    plus everything made in the other tabs."""
    app = request.app
    store = load_json(STORE, {})
    hist = load_json(HIST, [])
    st, states = await ha(app, "GET", "/states")
    ok = st == 200 and isinstance(states, list)
    by_ent = {s["entity_id"]: s for s in states} if ok else {}
    reg = {e.get("entity_id"): e for e in await registry_entities(app)} if ok else {}
    changed = False
    for x in hist:
        e = str(x.get("entity") or "")
        s_ = by_ent.get(e)
        x["exists"] = bool(s_) if ok else None
        if not s_:
            continue
        d, _, obj = e.partition(".")
        a = s_.get("attributes") or {}
        live = str(a.get("friendly_name") or "").strip()
        if live and live != x.get("name"):
            x["name"], changed = live, True
        if d in ("automation", "scene"):
            x["cfg_id"] = str(a.get("id") or "")
        elif d == "script":
            x["cfg_id"] = str((reg.get(e) or {}).get("unique_id") or obj)
        elif d in HELPER_FIELDS:
            x["cfg_id"] = str((reg.get(e) or {}).get("unique_id") or obj)
        x["kind_ha"] = d
    if changed:  # keep the names HA has, so the list is right even when HA can't be reached later
        save_json(HIST, [{k: v for k, v in x.items() if k not in ("exists", "cfg_id", "kind_ha")} for x in hist])
    return web.json_response({
        "templates": [{"id": k, "name": v["name"], "platform": v["platform"]} for k, v in store.items()],
        "history": hist, "made": made_index(), "ha_ok": ok,
    })


async def delete_template(request):
    app = request.app
    b = await request.json()
    store = load_json(STORE, {})
    store.pop(b.get("id"), None)
    save_json(STORE, store)
    render_package(store)
    await ha(app, "POST", "/services/template/reload", {})
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- announcement maker
# Ported from the standalone Announcement Maker add-on. Everything lives under /api/ann/.
ANN_DEFAULTS = {
    "ai_task_entity": "", "helper_ai_task_entity": "", "tts_entity": "", "speaker": "", "alexa_targets": [],
    "notify_targets": [], "music_players": [], "talking_flag": "", "personality_select": "", "household_context": "",
    "combined_info_entity": "", "combined_info_attribute": "", "locations_entity": "", "weather_entity": "",
    "inside_temp_entity": "", "news_entity": "", "calendar_entities": [], "todo_entity": "", "trash_entity": "",
    "custom_sources": [], "sources": None, "default_volume": 70, "default_length": 1000,
    "hype_style": "Be funny and hype us up. Boost our confidence. PG-13 language, no insults.",
    "roast_style": "Roast us super aggressively. Rated-R, heavy profanity, funny not hurtful.",
    "sweet_style": "Be super sweet and warm to everyone. Playful teasing only, never mean.",
    "personalities": None,  # list of {"name", "style"}; built from the three legacy styles above on first run
}
ANN_PERSONA_DEFAULT = "Default"
ANN_PERSONA_DEFAULT_STYLE = "Sound natural and friendly. No special personality, character, jokes or slang. Just clear and helpful."
ANN_PERSONA_LEGACY = [("Hype", "hype_style"), ("Roast", "roast_style"), ("Sweetie Pie", "sweet_style")]
ANN_ID_RE = re.compile(r"^[a-z0-9_]{1,60}$")
ANN_ENT_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
ANN_TEST_ID = "announcement_maker_test"
ANN_TEST = {"status": "idle"}
ANN_TASKS = set()


def clean_personalities(raw):
    """A tidy list of {name, style}. Names are unique, "Default" always exists and always comes first."""
    out, seen = [], set()
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        name = re.sub(r"\s+", " ", str(p.get("name") or "")).strip()[:40]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "style": str(p.get("style") or "").strip()[:2000] or ANN_PERSONA_DEFAULT_STYLE})
    base = next((p for p in out if p["name"].lower() == ANN_PERSONA_DEFAULT.lower()), None)
    if base:
        out.remove(base)
        base["name"] = ANN_PERSONA_DEFAULT
    else:
        base = {"name": ANN_PERSONA_DEFAULT, "style": ANN_PERSONA_DEFAULT_STYLE}
    return [base] + out


def ann_settings():
    s = dict(ANN_DEFAULTS)
    s.update({k: v for k, v in OPTS.items() if k in ANN_DEFAULTS})
    s.update({k: v for k, v in load_json(ANN_SETTINGS, {}).items() if k in ANN_DEFAULTS})
    raw = s.get("personalities")
    if not isinstance(raw, list):  # older install: keep whatever Hype / Roast / Sweetie Pie text was saved
        raw = [{"name": n, "style": s.get(k) or ANN_DEFAULTS[k]} for n, k in ANN_PERSONA_LEGACY]
    s["personalities"] = clean_personalities(raw)
    for _, k in ANN_PERSONA_LEGACY:
        s.pop(k, None)
    if OPTS.get("helper_ai_task_entity"):  # set in the add-on Configuration tab
        s["helper_ai_task_entity"] = OPTS["helper_ai_task_entity"]
    if not s.get("ai_task_entity"):  # share the Builder's AI task entity unless one was picked in Settings
        s["ai_task_entity"] = ENTITY
    return s


async def ann_body(request):
    try:
        b = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "bad json"}), content_type="application/json")
    return b if isinstance(b, dict) else {}


async def ha_text(app, method, path, body=None, params=None, timeout=20):
    return await ha(app, method, path, body, params, timeout, raw=True)


async def ann_run_test(app, cfg, mode):
    """Run the script once under a temporary id, record what the AI saw/said, then delete it."""
    global ANN_TEST
    try:
        if not isinstance(cfg, dict):
            ANN_TEST = {"status": "error", "error": "The script YAML is empty or not valid."}
            return
        seq = cfg.get("sequence") or []
        keys, last = [], -1
        for i, st in enumerate(seq):
            if isinstance(st, dict) and isinstance(st.get("variables"), dict):
                ks = [k for k in st["variables"] if k.startswith("src_")]
                if ks:
                    keys, last = ks, i
        if not keys:
            ANN_TEST = {"status": "error", "error": "Tick at least one data source first."}
            return
        if mode == "data":
            seq = seq[: last + 1]
        else:  # keep going when the AI answer is bad, so the test can show what came back
            seq = [x for x in seq if not (isinstance(x, dict) and str(x.get("alias", "")).startswith("Stop if the AI answer"))]
        res = {"sources": {k: "{{ %s }}" % k for k in keys}}
        if mode != "data":
            res.update({"speech": "{{ speech }}", "raw": "{{ announcement.data }}"})
            if any(isinstance(st, dict) and isinstance(st.get("variables"), dict) and "ann_fields" in st["variables"] for st in seq):
                res["fields"] = "{{ ann_fields }}"  # fields mode: show what would go on the card
        cfg["sequence"] = seq + [{"variables": {"test_result": res}},
                                 {"stop": "Test finished", "response_variable": "test_result"}]
        cfg["alias"] = "[TEST] " + str(cfg.get("alias", "announcement"))
        code, text = await ha_text(app, "POST", f"/config/script/config/{ANN_TEST_ID}", cfg)
        if code != 200:
            ANN_TEST = {"status": "error", "error": "HA refused the test script (%s): %s" % (code, str(text)[:400])}
            return
        await ha_text(app, "POST", "/services/script/reload", {})
        await asyncio.sleep(1.5)
        code, text = await ha_text(app, "POST", f"/services/script/{ANN_TEST_ID}", {},
                                   params={"return_response": "true"}, timeout=420)
        if code != 200:
            ANN_TEST = {"status": "error", "error": str(text)[:1500]}
            return
        r = json.loads(text).get("service_response") or {}
        if "sources" not in r and len(r) == 1 and isinstance(list(r.values())[0], dict):
            r = list(r.values())[0]
        ANN_TEST = dict(r, status="done")
    except Exception as e:
        log.exception("announcement test failed")
        ANN_TEST = {"status": "error", "error": str(e)}
    finally:
        await ha_text(app, "DELETE", f"/config/script/config/{ANN_TEST_ID}")
        await ha_text(app, "POST", "/services/script/reload", {})


def ann_parse_ai(data):
    """AI Task data may be a dict already or text that contains a JSON object."""
    if isinstance(data, dict):
        return data
    return json.loads(re.search(r"\{.*\}", str(data), re.S).group(0))


async def ann_ai_json(app, ai, task_name, prompt):
    """Ask the AI Task entity and return (parsed_json, error_message)."""
    code, data = await ha(app, "POST", "/services/ai_task/generate_data",
                          {"entity_id": ai, "task_name": task_name, "instructions": prompt},
                          params={"return_response": "true"}, timeout=90)
    if code != 200:
        return None, "AI Task failed (%s): %s" % (code, errmsg(data)[:200])
    try:
        return ann_parse_ai(data["service_response"]["data"]), None
    except Exception:
        return None, "The AI answer was not usable JSON. Try rewording."


async def ann_helper_instructions(app, body):
    idea, ai = str(body.get("idea", ""))[:1000], body.get("ai", "")
    srcs = [x for x in body.get("sources", []) if isinstance(x, dict) and re.match(r"^\w+$", str(x.get("id", "")))]
    if not (idea and ANN_ENT_RE.match(str(ai)) and str(ai).startswith("ai_task.")):
        return {"ok": False, "error": "Describe what you want and set an AI Task entity."}
    prompt = ("You help write voice announcement scripts for Home Assistant. Later, an AI will receive live data plus the "
              "instructions you write, and will write a spoken announcement.\nData sources available (id: label): %s\n"
              "Notes: calendar events are grouped under each calendar entity id (calendars: %s). Weather has current conditions "
              "plus a daily forecast for up to 7 days.\nUser's idea: %s\n"
              "Reply with ONLY JSON, no code fences: {\"name\": \"short script name\", \"sources\": [\"ids of sources needed\"], "
              "\"task\": \"clear instructions for the announcement writer, 1-5 sentences, including any conditions\"}"
              % ("; ".join("%s: %s" % (x["id"], x.get("label", "")) for x in srcs),
                 ", ".join(body.get("calendars", [])) or "none", idea))
    j, err = await ann_ai_json(app, ai, "Instruction helper", prompt)
    if err:
        return {"ok": False, "error": err}
    ids = {x["id"] for x in srcs}
    return {"ok": True, "name": str(j.get("name") or "")[:60], "task": str(j.get("task") or "")[:1500],
            "sources": [i for i in (j.get("sources") or []) if i in ids]}


async def ann_helper_source(app, body):
    ent, goal, ai = body.get("entity", ""), str(body.get("goal", ""))[:500], body.get("ai", "")
    if not (ANN_ENT_RE.match(str(ent)) and ANN_ENT_RE.match(str(ai)) and str(ai).startswith("ai_task.") and goal):
        return {"ok": False, "error": "Pick an entity, say what you want, and set an AI Task entity."}
    code, st = await ha(app, "GET", "/states/" + ent)
    if code != 200 or not isinstance(st, dict):
        return {"ok": False, "error": "Could not read %s (HA said %s)." % (ent, code)}
    attrs = st.get("attributes", {})
    prompt = ("You are helping set up a Home Assistant voice announcement. The user wants to pull info from one entity into it.\n"
              "Entity: %s\nState: %s\nAttributes (JSON, may be cut off): %s\nThe user wants: %s\n"
              "If one attribute holds what they want, give its exact name. If they need several or it is unclear, "
              "use an empty string, which includes the state and all attributes.\n"
              "Reply with ONLY JSON, no code fences: {\"label\": \"short name under 30 chars\", "
              "\"attribute\": \"exact attribute name or empty string\", \"note\": \"one sentence on what this will read\"}"
              % (ent, st.get("state"), json.dumps(attrs)[:3000], goal))
    j, err = await ann_ai_json(app, ai, "Source helper", prompt)
    if err:
        return {"ok": False, "error": err.replace("Try rewording.", "Try rewording what you want.")}
    attr = j.get("attribute") or ""
    if attr not in attrs or not re.match(r"^[\w .\-]+$", attr):
        attr = ""
    tmpl = ("{{ state_attr('%s', '%s') }}" % (ent, attr)) if attr else (
        "{{ states('%s') }} {{ states.%s.attributes | default('', true) }}" % (ent, ent))
    code, prev = await ha_text(app, "POST", "/template", {"template": tmpl})
    return {"ok": True, "label": str(j.get("label") or ent)[:40], "attribute": attr,
            "note": str(j.get("note") or "")[:200], "preview": str(prev)[:300] if code == 200 else "(could not render preview)"}


async def ann_options(request):
    return web.json_response(ann_settings())


async def ann_entities(request):
    app = request.app
    st, states = await ha(app, "GET", "/states")
    ents = []
    if st == 200 and isinstance(states, list):
        ents = [{"id": e["entity_id"], "name": (e.get("attributes") or {}).get("friendly_name") or e["entity_id"]}
                for e in states]
    st, svc = await ha(app, "GET", "/services")  # notify.mobile_app_* are services, not entities
    if st == 200 and isinstance(svc, list):
        for d in svc:
            if d.get("domain") == "notify":
                ents += [{"id": "notify." + n, "name": n.replace("_", " ") + " (service)", "svc": True}
                         for n in (d.get("services") or {}) if n not in ("send_message", "persistent_notification")]
    return web.json_response(sorted(ents, key=lambda e: e["id"]))


async def ann_save_settings(request):
    body = await ann_body(request)
    clean = {k: v for k, v in body.items() if k in ANN_DEFAULTS and k != "helper_ai_task_entity"}
    if "personalities" in clean:
        clean["personalities"] = clean_personalities(clean["personalities"])
    save_json(ANN_SETTINGS, clean)
    return web.json_response(ann_settings())


async def ann_registry_entity(app, unique_id, platform="input_select"):
    """entity_id of a freshly made helper, found by its storage id (it can differ from the name)."""
    for _ in range(6):
        r = await ws_call(app, {"type": "config/entity_registry/list"})
        for e in (r.get("result") or []) if r.get("success") else []:
            if e.get("platform") == platform and e.get("unique_id") == unique_id:
                return e["entity_id"]
        await asyncio.sleep(0.5)
    return platform + "." + unique_id


ANN_DROPDOWN_NAME = "AI Builder Personality"
ANN_DROPDOWN_ID = "input_select.ai_builder_personality"


async def ann_update_dropdown(app, ent, names):
    """Set the options of a dropdown made in Settings -> Helpers. Returns (ok, error)."""
    r = await ws_call(app, {"type": "config/entity_registry/get", "entity_id": ent})
    item = str(((r.get("result") or {}) if r.get("success") else {}).get("unique_id") or ent.split(".", 1)[1])
    r = await ws_call(app, {"type": "input_select/update", "input_select_id": item, "options": names})
    if r.get("success"):
        return True, ""
    return False, (r.get("error") or {}).get("message", "Home Assistant would not update it.")


async def ann_make_dropdown(app, names):
    """Make the personality dropdown by itself (a real UI helper, always editable). Returns (entity_id, error)."""
    st, state = await ha(app, "GET", "/states/" + ANN_DROPDOWN_ID)
    if st == 200 and isinstance(state, dict):  # one we made earlier: reuse it if it can still be edited
        ok, _err = await ann_update_dropdown(app, ANN_DROPDOWN_ID, names)
        if ok:
            return ANN_DROPDOWN_ID, ""
    r = await ws_call(app, {"type": "input_select/create", "name": ANN_DROPDOWN_NAME, "icon": "mdi:account-voice",
                            "options": names, "initial": ANN_PERSONA_DEFAULT})
    if not r.get("success"):
        return "", (r.get("error") or {}).get("message", "Home Assistant would not create it.")
    return await ann_registry_entity(app, (r.get("result") or {}).get("id") or "ai_builder_personality"), ""


async def ann_dropdown_sync(request):
    """Create the personality dropdown (input_select) in Home Assistant, or make its options match the list.
    If the picked dropdown is written in configuration.yaml (so it can't be edited) or is gone, a new editable one is made
    and used instead, so there is never an error to fix by hand."""
    app = request.app
    body = await ann_body(request)
    s = ann_settings()
    names = [p["name"] for p in s["personalities"]]
    ent = str(s.get("personality_select") or "").strip()

    def switch(new_ent):
        saved = load_json(ANN_SETTINGS, {})
        saved["personality_select"] = new_ent
        save_json(ANN_SETTINGS, saved)

    try:
        if not ent:
            if not body.get("create"):
                return web.json_response({"ok": False, "error": "No dropdown is picked yet. Use Create the dropdown for me."})
            new_ent, err = await ann_make_dropdown(app, names)
            if not new_ent:
                return web.json_response({"ok": False, "error": err})
            switch(new_ent)
            return web.json_response({"ok": True, "created": True, "entity": new_ent, "settings": ann_settings(),
                                      "message": "Created %s with %d personalities. It is now your Personality dropdown." % (new_ent, len(names))})
        if not ANN_ENT_RE.match(ent) or not ent.startswith("input_select."):
            return web.json_response({"ok": False, "error": "%s is not an input_select." % ent})
        st, state = await ha(app, "GET", "/states/" + ent)
        gone = st != 200 or not isinstance(state, dict)
        if not gone and (state.get("attributes") or {}).get("options") == names:
            return web.json_response({"ok": True, "unchanged": True, "entity": ent, "settings": ann_settings(), "message": "The dropdown already matches."})
        if not gone:
            ok, err = await ann_update_dropdown(app, ent, names)
            if ok:
                if state.get("state") not in names:  # the one it was on is gone, so land on Default
                    await ha(app, "POST", "/services/input_select/select_option", {"entity_id": ent, "option": ANN_PERSONA_DEFAULT})
                return web.json_response({"ok": True, "entity": ent, "settings": ann_settings(), "message": "Updated %s: %s." % (ent, ", ".join(names))})
        # Missing, or written in configuration.yaml so it can't be edited: make a new editable one and use it.
        new_ent, err2 = await ann_make_dropdown(app, names)
        if not new_ent:
            return web.json_response({"ok": False, "error": err2})
        switch(new_ent)
        why = "%s no longer exists" % ent if gone else "%s was written in configuration.yaml, so it can't be edited" % ent
        return web.json_response({"ok": True, "created": True, "entity": new_ent, "settings": ann_settings(),
                                  "message": "%s. I made %s for you (it updates by itself) and switched to it. If a dashboard card or automation used %s, point it at %s." % (why, new_ent, ent, new_ent)})
    except Exception as e:  # noqa: BLE001 - report anything that goes wrong talking to Home Assistant
        return web.json_response({"ok": False, "error": "Could not reach Home Assistant: %s" % e})


async def ann_card_switch(request):
    """Make an input_boolean (a real UI helper, always editable) that shows or hides a dashboard card."""
    app = request.app
    body = await ann_body(request)
    name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()[:60] or "Show card"
    ent = "input_boolean." + (slug(name) or "show_card")
    try:
        st, state = await ha(app, "GET", "/states/" + ent)
        if st == 200 and isinstance(state, dict):  # already there: just use it
            return web.json_response({"ok": True, "entity": ent, "existed": True,
                                      "message": "%s already exists, so it is now picked." % ent})
        r = await ws_call(app, {"type": "input_boolean/create", "name": name, "icon": "mdi:card-text-outline"})
        if not r.get("success"):
            return web.json_response({"ok": False, "error": (r.get("error") or {}).get("message", "Home Assistant would not create it.")})
        ent = await ann_registry_entity(app, (r.get("result") or {}).get("id") or (slug(name) or "show_card"), "input_boolean")
        return web.json_response({"ok": True, "entity": ent, "message": "Made %s and picked it. Point your dashboard card at it." % ent})
    except Exception as e:  # noqa: BLE001 - report anything that goes wrong talking to Home Assistant
        return web.json_response({"ok": False, "error": "Could not reach Home Assistant: %s" % e})


async def ann_test_status(request):
    return web.json_response(ANN_TEST)


async def ann_test_start(request):
    global ANN_TEST
    body = await ann_body(request)
    if ANN_TEST.get("status") == "running":
        return web.json_response({"ok": False, "error": "A test is already running."})
    try:
        cfg = yaml.safe_load(body.get("yaml", ""))
    except yaml.YAMLError as e:
        return web.json_response({"error": "YAML problem: %s" % e}, status=400)
    mode = body.get("mode") if body.get("mode") in ("data", "text", "full") else "text"
    ANN_TEST = {"status": "running", "mode": mode}
    t = asyncio.create_task(ann_run_test(request.app, cfg, mode))
    ANN_TASKS.add(t)  # keep a reference so the task is not garbage collected mid-run
    t.add_done_callback(ANN_TASKS.discard)
    return web.json_response({"ok": True})


async def ann_helper(request):
    body = await ann_body(request)
    if body.get("mode") == "instructions":
        return web.json_response(await ann_helper_instructions(request.app, body))
    return web.json_response(await ann_helper_source(request.app, body))


async def ann_script_id(body):
    sid = str(body.get("id", ""))
    if not ANN_ID_RE.match(sid):
        raise web.HTTPBadRequest(text=json.dumps({"error": "script id must be lowercase letters, numbers, underscores"}),
                                 content_type="application/json")
    return sid


ANN_MARK = "Made with Announcement Maker"
ANN_AUTO_SUFFIX = "_auto"  # the optional schedule automation for a script is <script id>_auto


def ann_library():
    lib = load_json(ANN_LIB, {})
    return lib if isinstance(lib, dict) else {}


def clean_ann_state(state):
    """Keep only a plain JSON object of sensible size; the browser rebuilds the script from it."""
    if not isinstance(state, dict) or len(json.dumps(state)) > 200_000:
        return None
    return state


def ann_store(sid, name, state, pushed=False):
    lib = ann_library()
    now = time.strftime("%Y-%m-%d %H:%M")
    old = lib.get(sid, {})
    lib[sid] = {"id": sid, "name": str(name or old.get("name") or sid)[:80],
                "state": state if state is not None else old.get("state") or {},
                "updated": now, "pushed_at": now if pushed else old.get("pushed_at"),
                "ha_name": str(name or sid)[:80] if pushed else old.get("ha_name")}  # the name HA had when we last wrote it
    save_json(ANN_LIB, lib)
    return lib[sid]


async def ann_push(request):
    """Create or update the script, and its optional schedule automation (<script id>_auto, which calls the script).
    A schedule that is switched off removes the automation, but only one this tool made. If the request has no
    auto_yaml at all, the automation is left alone."""
    app = request.app
    body = await ann_body(request)
    sid = await ann_script_id(body)
    aid = sid + ANN_AUTO_SUFFIX
    try:
        cfg = yaml.safe_load(body.get("yaml", ""))
        acfg = yaml.safe_load(body["auto_yaml"]) if body.get("auto_yaml") else None
    except yaml.YAMLError as e:
        return web.json_response({"error": "YAML problem: %s" % e}, status=400)
    if not isinstance(cfg, dict):
        return web.json_response({"ok": False, "detail": "The script YAML is empty or not valid."})
    if acfg is not None:
        if not isinstance(acfg, dict):
            return web.json_response({"ok": False, "detail": "The schedule YAML is not valid."})
        bad = fact_auto_problem(acfg)
        if bad:
            return web.json_response({"ok": False, "detail": bad})
        acfg["description"] = ANN_MARK  # so a later push or delete knows this automation is ours
    code, text = await ha_text(app, "POST", f"/config/script/config/{sid}", cfg)
    if code != 200:
        return web.json_response({"ok": False, "detail": "HA said %s: %s" % (code, str(text)[:300])})
    await ha_text(app, "POST", "/services/script/reload", {})
    auto = "none"
    if acfg is not None:
        code, text = await ha_text(app, "POST", f"/config/automation/config/{aid}", acfg)
        if code != 200:
            return web.json_response({"ok": False, "detail": "The script was pushed, but HA refused the schedule (%s): %s" % (code, str(text)[:300])})
        await ha_text(app, "POST", "/services/automation/reload", {})
        auto = "pushed"
    elif "auto_yaml" in body:  # schedule switched off: remove the automation, but only one this tool made
        code, old = await ha(app, "GET", f"/config/automation/config/{aid}", timeout=10)
        if code == 200 and isinstance(old, dict) and old.get("description") == ANN_MARK:
            code, text = await ha_text(app, "DELETE", f"/config/automation/config/{aid}")
            if code == 200:
                await ha_text(app, "POST", "/services/automation/reload", {})
                auto = "removed"
    name = str(cfg.get("alias") or sid)
    if body.get("new"):  # the editor says so the first time a script is created
        add_history({"kind": "announcement", "name": name, "entity": f"script.{sid}"})
    state = clean_ann_state(body.get("state"))
    replaced = ""
    rid = str(body.get("replace_auto") or "")
    if ANN_ID_RE.match(rid) and rid != aid:  # an imported automation this announcement now does the job of: turn it off, keep a copy
        code, old = await ha(app, "GET", f"/config/automation/config/{rid}", timeout=10)
        if code == 200 and isinstance(old, dict) and old.get("description") != ANN_MARK:
            fact_backup_automation(rid, old)
            st_, states = await ha(app, "GET", "/states")
            ent = next((e["entity_id"] for e in (states if st_ == 200 and isinstance(states, list) else [])
                        if e["entity_id"].startswith("automation.") and str((e.get("attributes") or {}).get("id")) == rid), "")
            if ent:
                await ha_text(app, "POST", "/services/automation/turn_off", {"entity_id": ent})
                replaced = ent
        if isinstance(state, dict):
            state["replacedDone"] = True
    if state is not None or sid in ann_library():
        ann_store(sid, name, state, pushed=True)
    id_note = await match_ids_after_push(app, name, sid, aid if auto == "pushed" else None) if body.get("match_id") else ""
    return web.json_response({"ok": True, "entity": f"script.{sid}", "auto": auto, "replaced": replaced, "id_note": id_note})


async def ann_found(app, skip):
    """Scripts in Home Assistant that this tool wrote earlier but that have no saved form yet."""
    st, states = await ha(app, "GET", "/states")
    ids = [s["entity_id"].split(".", 1)[1] for s in states if st == 200 and isinstance(states, list)
           and s["entity_id"].startswith("script.") and s["entity_id"].split(".", 1)[1] not in skip
           and ANN_ID_RE.match(s["entity_id"].split(".", 1)[1])][:200]
    sem = asyncio.Semaphore(8)

    async def one(i):
        async with sem:
            code, cfg = await ha(app, "GET", f"/config/script/config/{i}", timeout=10)
        if code == 200 and isinstance(cfg, dict) and cfg.get("description") == ANN_MARK:
            return {"id": i, "name": str(cfg.get("alias") or i)}
    return [x for x in await asyncio.gather(*(one(i) for i in ids)) if x]


async def ann_library_list(request):
    app = request.app
    lib = ann_library()
    st, states = await ha(app, "GET", "/states")
    ok = st == 200 and isinstance(states, list)
    reg = await registry_entities(app) if ok else []
    live = by_config_id(states if ok else [], reg, "script")
    autos = by_config_id(states if ok else [], reg, "automation")
    renamed = sync_lib_names(lib, live, ANN_LIB) if ok else []
    items = []
    for i, v in lib.items():
        a = autos.get(i + ANN_AUTO_SUFFIX)
        items.append({**v, "in_ha": i in live, "entity": (live.get(i) or {}).get("entity_id") or "script." + i,
                      "last_run": ((live.get(i) or {}).get("attributes") or {}).get("last_triggered"),
                      "auto_in_ha": a is not None, "auto_on": bool(a) and a.get("state") == "on"})
    items.sort(key=lambda x: str(x.get("updated") or ""), reverse=True)
    found = await ann_found(app, set(lib)) if st == 200 else []
    return web.json_response({"items": items, "found": found, "ha_ok": st == 200, "renamed": renamed})


async def ann_library_save(request):
    body = await ann_body(request)
    sid = await ann_script_id(body)
    state = clean_ann_state(body.get("state"))
    if state is None:
        return web.json_response({"ok": False, "error": "Nothing to save."})
    warn, note = await push_name_change(request.app, "ann", sid, body.get("name"), body.get("match_id"))
    out = {"ok": True, "item": ann_store(sid, body.get("name"), state), "id_note": note}
    if warn:
        out["name_warning"] = warn
    return web.json_response(out)


async def ann_library_delete(request):
    app = request.app
    body = await ann_body(request)
    sid = await ann_script_id(body)
    lib = ann_library()
    removed_script = False
    if body.get("delete_script"):
        code, cfg = await ha(app, "GET", f"/config/script/config/{sid}", timeout=10)
        if sid not in lib and not (code == 200 and isinstance(cfg, dict) and cfg.get("description") == ANN_MARK):
            return web.json_response({"ok": False, "error": "That script wasn't made here, so it won't be deleted."})
        if code == 200:
            code, text = await ha_text(app, "DELETE", f"/config/script/config/{sid}")
            if code != 200:
                return web.json_response({"ok": False, "error": "HA said %s: %s" % (code, str(text)[:300])})
            await ha_text(app, "POST", "/services/script/reload", {})
            removed_script = True
    code, old = await ha(app, "GET", f"/config/automation/config/{sid + ANN_AUTO_SUFFIX}", timeout=10)
    if code == 200 and isinstance(old, dict) and old.get("description") == ANN_MARK:  # its schedule, if this tool made one
        code, _t = await ha_text(app, "DELETE", f"/config/automation/config/{sid + ANN_AUTO_SUFFIX}")
        if code == 200:
            await ha_text(app, "POST", "/services/automation/reload", {})
    lib.pop(sid, None)
    save_json(ANN_LIB, lib)
    return web.json_response({"ok": True, "script_deleted": removed_script})


class _AnnDumper(yaml.SafeDumper):
    pass


_AnnDumper.add_representer(str, lambda d, v: d.represent_scalar(
    "tag:yaml.org,2002:str", v, style="|" if "\n" in v else None))  # multi-line text stays readable


def ann_dump(cfg):
    return yaml.dump(cfg, Dumper=_AnnDumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)


def ann_clean_id(x):
    x = re.sub(r"^script\.", "", str(x or "").strip().lower())
    return x if ANN_ID_RE.match(x) else ""


async def ann_import(request):
    """Take a script the user pasted (just the script, `my_id:` + script as it appears in scripts.yaml, or only the steps)
    and return it checked and tidied, so the editor can take it over."""
    body = await ann_body(request)
    text = str(body.get("yaml", ""))
    if not text.strip():
        return web.json_response({"ok": False, "error": "Paste your script first."})
    if len(text) > 150_000:
        return web.json_response({"ok": False, "error": "That script is too big to import."})
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return web.json_response({"ok": False, "error": "YAML problem: %s" % str(e)[:400]})
    sid = ""
    if isinstance(data, list):  # only the steps were pasted
        data = {"sequence": data}
    for _ in range(2):  # `script:` wrapper, then `my_id:` wrapper, as in scripts.yaml
        if isinstance(data, dict) and "sequence" not in data and data:
            kids = {k: v for k, v in data.items() if isinstance(v, dict)}
            if len(data) == 1 and data.get("script") is not None and isinstance(data["script"], dict):
                data = data["script"]
            elif len(kids) == 1 and len(data) == 1:
                sid, data = str(next(iter(kids))), next(iter(kids.values()))
            elif len(kids) > 1:
                return web.json_response({"ok": False, "error": "That has more than one script in it (%s). Paste one at a time." % ", ".join(list(kids)[:6])})
    if isinstance(data, dict) and isinstance(data.get("sequence"), dict):
        data["sequence"] = [data["sequence"]]
    if not isinstance(data, dict) or not isinstance(data.get("sequence"), list) or not data["sequence"]:
        return web.json_response({"ok": False, "error": "That does not look like a Home Assistant script. It needs a sequence: list of steps."})
    if not data.get("alias"):
        data = {"alias": sid.replace("_", " ").title() if sid else "Imported script", **data}
    return web.json_response({"ok": True, "id": ann_clean_id(sid), "alias": str(data["alias"]), "config": data, "yaml": ann_dump(data)})


async def ann_script_get(request):
    """The saved script config for one id, so a script made before the library existed can be opened for editing."""
    sid = str(request.query.get("id", ""))
    if not ANN_ID_RE.match(sid):
        return web.json_response({"ok": False, "error": "Bad script id."})
    code, cfg = await ha(request.app, "GET", f"/config/script/config/{sid}", timeout=10)
    if code != 200 or not isinstance(cfg, dict):
        return web.json_response({"ok": False, "error": "Could not load that script: %s" % errmsg(cfg)})
    return web.json_response({"ok": True, "config": cfg, "yaml": ann_dump(cfg)})


async def ann_run(request):
    body = await ann_body(request)
    sid = await ann_script_id(body)
    code, text = await ha_text(request.app, "POST", "/services/script/turn_on", {"entity_id": await script_entity(request.app, sid)})
    return web.json_response({"ok": code == 200, "detail": str(text)[:300]})


# ---------------------------------------------------------------- facts
# Scripts that ask the AI Task for a fact and publish it (MQTT file_reader by default). Same shape as announcements:
# every fact is saved in the add-on (FACTS_LIB) so it can be edited and pushed again, and an optional automation
# (id <script id>_auto) runs it on a schedule. Everything lives under /api/facts/. Data sources, the AI Task entity
# and the entity list are shared with Announcements.
FACT_DEFAULTS = {"mqtt_prefix": "file_reader/overwrite/", "last_entity": "", "last_attribute": "content",
                 "home_entities": [], "default_length": 180, "extra_rules": ""}
_fp = str(OPTS.get("facts_file_path") or "").strip()
FACTS_PATH_OPT = _fp if re.match(r"^[A-Za-z0-9_\-./]{1,120}$", _fp) else ""  # add-on option: where fact text files are saved
FACT_MARK = "Made with Fact Maker"
FACT_TEST_ID = "fact_maker_test"
FACT_TEST = {"status": "idle"}
FACT_TASKS = set()
FACT_AUTO_SUFFIX = "_auto"


def fact_settings():
    s = dict(FACT_DEFAULTS)
    s.update({k: v for k, v in load_json(FACT_SETTINGS, {}).items() if k in FACT_DEFAULTS})
    s["prefix_locked"] = bool(FACTS_PATH_OPT)
    if FACTS_PATH_OPT:  # set in the add-on Configuration tab, so it wins over the Facts settings
        s["mqtt_prefix"] = FACTS_PATH_OPT
    return s


def fact_clean_settings(body):
    s = dict(FACT_DEFAULTS)
    prefix = str(body.get("mqtt_prefix", s["mqtt_prefix"])).strip()
    s["mqtt_prefix"] = prefix if re.match(r"^[A-Za-z0-9_\-./]{0,120}$", prefix) else s["mqtt_prefix"]
    if FACTS_PATH_OPT:
        s["mqtt_prefix"] = FACTS_PATH_OPT
    for k in ("last_entity",):
        v = str(body.get(k, "")).strip()
        s[k] = v if (not v or ANN_ENT_RE.match(v)) else ""
    attr = str(body.get("last_attribute", "")).strip()
    s["last_attribute"] = attr if re.match(r"^[\w .\-]{0,60}$", attr) else "content"
    he = body.get("home_entities", [])
    s["home_entities"] = [x for x in he if isinstance(x, str) and ANN_ENT_RE.match(x)][:20] if isinstance(he, list) else []
    try:
        s["default_length"] = max(40, min(2000, int(body.get("default_length") or 180)))
    except (TypeError, ValueError):
        s["default_length"] = 180
    s["extra_rules"] = str(body.get("extra_rules", ""))[:2000]
    return s


def fact_library():
    lib = load_json(FACTS_LIB, {})
    return lib if isinstance(lib, dict) else {}


def fact_store(sid, name, state, pushed=False):
    lib = fact_library()
    now = time.strftime("%Y-%m-%d %H:%M")
    old = lib.get(sid, {})
    lib[sid] = {"id": sid, "name": str(name or old.get("name") or sid)[:80],
                "state": state if state is not None else old.get("state") or {},
                "updated": now, "pushed_at": now if pushed else old.get("pushed_at"),
                "ha_name": str(name or sid)[:80] if pushed else old.get("ha_name")}  # the name HA had when we last wrote it
    save_json(FACTS_LIB, lib)
    return lib[sid]


async def fact_options(request):
    return web.json_response(fact_settings())


async def fact_save_settings(request):
    body = await ann_body(request)
    save_json(FACT_SETTINGS, fact_clean_settings(body))
    return web.json_response(fact_settings())


async def fact_helper(request):
    """Turn a plain-English idea into instructions, random lists, output style and data sources."""
    body = await ann_body(request)
    idea, ai = str(body.get("idea", ""))[:1000], str(body.get("ai", ""))
    srcs = [x for x in body.get("sources", []) if isinstance(x, dict) and re.match(r"^\w+$", str(x.get("id", "")))]
    if not (idea and ANN_ENT_RE.match(ai) and ai.startswith("ai_task.")):
        return web.json_response({"ok": False, "error": "Describe the fact you want and set an AI Task entity."})
    prompt = (
        "You help set up a Home Assistant script that asks an AI for ONE short fact each time it runs, then saves it to a text file "
        "that a dashboard shows. Later the AI receives live data plus the instructions you write.\n"
        "Data sources available (id: label): %s\nUser's idea: %s\n"
        "To keep the facts varied, the script can pick random values from lists before asking. Each list has a short name made of "
        "lowercase letters and underscores (for example topic, angle, genre, decade) and 6 to 20 items. The AI is told each pick for the run.\n"
        "Output styles: \"plain\" (just the fact), \"titled\" (a title plus the fact, e.g. the artist name and a fact about them), "
        "\"list\" (several short lines), \"json\" (a data list of many items with named fields, for example today's notable birthdays with name, year and what they are known for; "
        "use it only when the user wants many items kept as structured data).\n"
        "Reply with ONLY JSON, no code fences: {\"name\": \"short script name\", \"task\": \"clear instructions for the fact writer, "
        "1-5 sentences\", \"picks\": [{\"name\": \"topic\", \"items\": [\"...\"]}], \"style\": \"plain|titled|list\", "
        "\"title_hint\": \"what the title should be, only for titled\", \"heading\": \"optional heading line shown above the fact, "
        "may use {{ fact_title }} for titled\", \"file\": \"suggested_file_name.txt\", \"sources\": [\"ids of data sources needed, usually none\"], "
        "\"length\": 180, \"list_key\": \"only for json: name of the list, e.g. birthdays\", \"count\": 10, "
        "\"fields\": [{\"key\": \"lowercase_name\", \"hint\": \"what it holds\", \"type\": \"text|number|yesno\"}] (only for json), "
        "\"sort_by\": \"field name or empty\", \"sort_dir\": \"asc|desc\", \"uses_date\": false (true when the list depends on today's date)}" % ("; ".join("%s: %s" % (x["id"], x.get("label", "")) for x in srcs) or "none", idea))
    j, err = await ann_ai_json(request.app, ai, "Fact helper", prompt)
    if err:
        return web.json_response({"ok": False, "error": err})
    ids = {x["id"] for x in srcs}
    picks = []
    for p in (j.get("picks") or [])[:5]:
        if isinstance(p, dict) and re.match(r"^[a-z][a-z0-9_]{0,24}$", str(p.get("name", ""))):
            items = [str(i).strip()[:120] for i in (p.get("items") or []) if str(i).strip()][:40]
            if items:
                picks.append({"name": p["name"], "items": "\n".join(items)})
    style = j.get("style") if j.get("style") in ("plain", "titled", "list", "json") else "plain"
    fields = []
    for f in (j.get("fields") or [])[:14]:
        if isinstance(f, dict):
            k = re.sub(r"[^a-z0-9_]+", "_", str(f.get("key") or "").lower()).strip("_")[:30]
            if k and all(k != x["key"] for x in fields):
                fields.append({"key": k, "hint": str(f.get("hint") or "")[:120], "type": f.get("type") if f.get("type") in ("text", "number", "yesno") else "text"})
    list_key = re.sub(r"[^a-z0-9_]+", "_", str(j.get("list_key") or "").lower()).strip("_")[:30] or "items"
    try:
        count = max(1, min(200, int(j.get("count") or 10)))
    except (TypeError, ValueError):
        count = 10
    sort_by = ",".join(x for x in (t.strip() for t in str(j.get("sort_by") or "").split(",")) if any(x == f["key"] for f in fields))
    fname = re.sub(r"[^A-Za-z0-9_\-.]", "", str(j.get("file") or ""))[:60]
    try:
        length = max(40, min(2000, int(j.get("length") or 180)))
    except (TypeError, ValueError):
        length = 180
    return web.json_response({
        "ok": True, "name": str(j.get("name") or "")[:60], "task": str(j.get("task") or "")[:1500], "picks": picks,
        "style": style, "title_hint": str(j.get("title_hint") or "")[:200], "heading": str(j.get("heading") or "")[:200],
        "file": fname, "length": length, "sources": [i for i in (j.get("sources") or []) if i in ids],
        "list_key": list_key, "count": count, "fields": fields if style == "json" else [], "sort_by": sort_by,
        "sort_dir": "asc" if j.get("sort_dir") == "asc" else "desc", "uses_date": bool(j.get("uses_date"))})


def fact_is_auto(state):
    """A fact that lives as one automation (an imported one, or a generated one made with 'asAuto')."""
    st = state if isinstance(state, dict) else {}
    return bool(st.get("autoOnly") or (st.get("asAuto") and st.get("raw") is None))


def fact_has_mark(cfg):
    return isinstance(cfg, dict) and cfg.get("description") == FACT_MARK


async def fact_run_test(app, cfg, mode):
    """Run the script once under a temporary id and report what it picked, what the AI saw and what it wrote."""
    global FACT_TEST
    try:
        if not isinstance(cfg, dict) or not isinstance(cfg.get("sequence"), list):
            FACT_TEST = {"status": "error", "error": "The script YAML is empty or not valid."}
            return
        seq = cfg["sequence"]
        ai_at = next((i for i, st in enumerate(seq) if isinstance(st, dict) and st.get("action") == "ai_task.generate_data"), None)
        if ai_at is None:
            FACT_TEST = {"status": "error", "error": "There is no ai_task.generate_data step to test."}
            return
        keys = []
        for st in seq:
            if isinstance(st, dict) and isinstance(st.get("variables"), dict):
                keys += [k for k in st["variables"] if k != "fact_parts" and k not in keys]
        if mode == "data":
            seq = seq[:ai_at]
            keys = [k for k in keys if not k.startswith("fact_")]
        else:
            if mode == "text":  # leave out the step that publishes, so nothing is written
                seq = [st for st in seq if not (isinstance(st, dict) and st.get("alias") == "Publish")]
        res = {"values": {k: "{{ %s }}" % k for k in keys}}
        if mode != "data":
            res["ai_raw"] = "{{ fact_raw.data | default('') }}"
        cfg["sequence"] = seq + [{"variables": {"test_result": res}},
                                 {"stop": "Test finished", "response_variable": "test_result"}]
        cfg["alias"] = "[TEST] " + str(cfg.get("alias", "fact"))
        code, text = await ha_text(app, "POST", f"/config/script/config/{FACT_TEST_ID}", cfg)
        if code != 200:
            FACT_TEST = {"status": "error", "error": "HA refused the test script (%s): %s" % (code, str(text)[:400])}
            return
        await ha_text(app, "POST", "/services/script/reload", {})
        await asyncio.sleep(1.5)
        code, text = await ha_text(app, "POST", f"/services/script/{FACT_TEST_ID}", {},
                                   params={"return_response": "true"}, timeout=420)
        if code != 200:
            FACT_TEST = {"status": "error", "error": str(text)[:1500]}
            return
        r = json.loads(text).get("service_response") or {}
        if "values" not in r and len(r) == 1 and isinstance(list(r.values())[0], dict):
            r = list(r.values())[0]
        FACT_TEST = dict(r, status="done", mode=mode)
    except Exception as e:
        log.exception("fact test failed")
        FACT_TEST = {"status": "error", "error": str(e)}
    finally:
        await ha_text(app, "DELETE", f"/config/script/config/{FACT_TEST_ID}")
        await ha_text(app, "POST", "/services/script/reload", {})


async def fact_test_status(request):
    return web.json_response(FACT_TEST)


async def fact_test_start(request):
    global FACT_TEST
    body = await ann_body(request)
    if FACT_TEST.get("status") == "running":
        return web.json_response({"ok": False, "error": "A test is already running."})
    try:
        cfg = yaml.safe_load(body.get("yaml", ""))
    except yaml.YAMLError as e:
        return web.json_response({"error": "YAML problem: %s" % e}, status=400)
    mode = body.get("mode") if body.get("mode") in ("data", "text", "full") else "text"
    FACT_TEST = {"status": "running", "mode": mode}
    t = asyncio.create_task(fact_run_test(request.app, cfg, mode))
    FACT_TASKS.add(t)
    t.add_done_callback(FACT_TASKS.discard)
    return web.json_response({"ok": True})


FACT_AUTO_BACKUPS = DATA / "automation_backups"


def fact_auto_id(body, sid):
    """The automation id to use: the user's own (taken over from Home Assistant) or <script id>_auto."""
    a = str(body.get("auto_id") or "").strip()
    return a if ANN_ID_RE.match(a) else sid + FACT_AUTO_SUFFIX


def fact_auto_problem(acfg):
    keys = set(acfg)
    if not ({"triggers", "trigger"} & keys):
        return "That automation has no triggers: list."
    if not ({"actions", "action"} & keys):
        return "That automation has no actions: list."
    return ""


def fact_backup_automation(aid, old):
    """Keep a copy of an automation the user wrote before a push replaces it."""
    try:
        FACT_AUTO_BACKUPS.mkdir(parents=True, exist_ok=True)
        (FACT_AUTO_BACKUPS / ("%s-%s.yaml" % (aid, time.strftime("%Y%m%d-%H%M%S")))).write_text(
            yaml.safe_dump(old, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except OSError:
        log.exception("could not back up automation %s", aid)


async def fact_push(request):
    """Create or update the script, and its automation: either the generated schedule, or the user's own automation
    kept exactly as written (auto_raw). Removes the generated schedule when none is sent; never removes a user's own."""
    app = request.app
    body = await ann_body(request)
    sid = await ann_script_id(body)
    aid = fact_auto_id(body, sid)
    own = bool(body.get("auto_raw"))
    auto_only = bool(body.get("auto_only"))
    if auto_only:
        return await fact_push_auto(app, body, sid)
    try:
        cfg = yaml.safe_load(body.get("yaml", ""))
        acfg = yaml.safe_load(body["auto_yaml"]) if body.get("auto_yaml") else None
    except yaml.YAMLError as e:
        return web.json_response({"error": "YAML problem: %s" % e}, status=400)
    if not isinstance(cfg, dict):
        return web.json_response({"ok": False, "detail": "The script YAML is empty or not valid."})
    if acfg is not None and not isinstance(acfg, dict):
        return web.json_response({"ok": False, "detail": "The automation YAML is not valid."})
    if acfg is not None and own:
        bad = fact_auto_problem(acfg)
        if bad:
            return web.json_response({"ok": False, "detail": bad})
    code, text = await ha_text(app, "POST", f"/config/script/config/{sid}", cfg)
    if code != 200:
        return web.json_response({"ok": False, "detail": "HA said %s: %s" % (code, str(text)[:300])})
    await ha_text(app, "POST", "/services/script/reload", {})
    auto = "none"
    if acfg is not None:
        if own:  # take over: keep a copy of what is there now, and keep the user's id inside the config if they have one
            code, old = await ha(app, "GET", f"/config/automation/config/{aid}", timeout=10)
            if code == 200 and isinstance(old, dict) and old != acfg:
                fact_backup_automation(aid, old)
        code, text = await ha_text(app, "POST", f"/config/automation/config/{aid}", acfg)
        if code != 200:
            return web.json_response({"ok": False, "detail": "The script was pushed, but HA refused the automation (%s): %s" % (code, str(text)[:300])})
        await ha_text(app, "POST", "/services/automation/reload", {})
        auto = "pushed"
    else:  # schedule switched off: remove the automation, but only one this tool made
        code, old = await ha(app, "GET", f"/config/automation/config/{aid}", timeout=10)
        if code == 200 and fact_has_mark(old):
            code, text = await ha_text(app, "DELETE", f"/config/automation/config/{aid}")
            if code == 200:
                await ha_text(app, "POST", "/services/automation/reload", {})
                auto = "removed"
    name = str(cfg.get("alias") or sid)
    if body.get("new"):
        add_history({"kind": "fact", "name": name, "entity": f"script.{sid}"})
    state = clean_ann_state(body.get("state"))
    if state is not None or sid in fact_library():
        fact_store(sid, name, state, pushed=True)
    id_note = ""
    if body.get("match_id"):
        own = str(body.get("auto_id") or "")
        id_note = await match_ids_after_push(app, name, sid, (own if ANN_ID_RE.match(own) else sid + FACT_AUTO_SUFFIX) if auto == "pushed" else None)
    return web.json_response({"ok": True, "entity": f"script.{sid}", "auto": auto, "id_note": id_note})


async def fact_push_auto(app, body, aid):
    """A fact that is only an automation (it asks the AI and publishes by itself, no script): push it exactly as written."""
    try:
        acfg = yaml.safe_load(body.get("auto_yaml") or "")
    except yaml.YAMLError as e:
        return web.json_response({"error": "YAML problem: %s" % e}, status=400)
    if not isinstance(acfg, dict):
        return web.json_response({"ok": False, "detail": "The automation YAML is empty or not valid."})
    bad = fact_auto_problem(acfg)
    if bad:
        return web.json_response({"ok": False, "detail": bad})
    code, old = await ha(app, "GET", f"/config/automation/config/{aid}", timeout=10)
    if code == 200 and isinstance(old, dict) and old != acfg and not fact_has_mark(old):
        fact_backup_automation(aid, old)
    code, text = await ha_text(app, "POST", f"/config/automation/config/{aid}", acfg)
    if code != 200:
        return web.json_response({"ok": False, "detail": "HA said %s: %s" % (code, str(text)[:300])})
    await ha_text(app, "POST", "/services/automation/reload", {})
    cleaned = False
    if body.get("cleanup_script"):  # a fact that used to be a script + schedule automation is now this one automation
        code, oldscript = await ha(app, "GET", f"/config/script/config/{aid}", timeout=10)
        if code == 200 and fact_has_mark(oldscript):
            code, _t = await ha_text(app, "DELETE", f"/config/script/config/{aid}")
            if code == 200:
                await ha_text(app, "POST", "/services/script/reload", {})
                cleaned = True
        code, oldauto = await ha(app, "GET", f"/config/automation/config/{aid + FACT_AUTO_SUFFIX}", timeout=10)
        if code == 200 and fact_has_mark(oldauto):
            code, _t = await ha_text(app, "DELETE", f"/config/automation/config/{aid + FACT_AUTO_SUFFIX}")
            if code == 200:
                await ha_text(app, "POST", "/services/automation/reload", {})
                cleaned = True
    name = str(acfg.get("alias") or aid)
    if body.get("new"):
        add_history({"kind": "fact", "name": name, "entity": "automation." + aid})
    state = clean_ann_state(body.get("state"))
    if state is not None or aid in fact_library():
        fact_store(aid, name, state, pushed=True)
    id_note = await match_ids_after_push(app, name, None, aid) if body.get("match_id") else ""
    return web.json_response({"ok": True, "entity": "automation." + aid, "auto": "pushed", "cleaned": cleaned, "id_note": id_note})


async def fact_import_auto(request):
    """Check an automation the user pasted (one automation, `- id:` list item as in automations.yaml, or under `automation:`)."""
    body = await ann_body(request)
    text = str(body.get("yaml", ""))
    if not text.strip():
        return web.json_response({"ok": False, "error": "Paste your automation first."})
    if len(text) > 150_000:
        return web.json_response({"ok": False, "error": "That automation is too big to import."})
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return web.json_response({"ok": False, "error": "YAML problem: %s" % str(e)[:400]})
    wrapped = False
    if isinstance(data, dict) and isinstance(data.get("automation"), (list, dict)) and len(data) == 1:
        data, wrapped = data["automation"], True
    if isinstance(data, list):
        if len(data) != 1 or not isinstance(data[0], dict):
            return web.json_response({"ok": False, "error": "That has more than one automation in it. Paste one at a time."})
        data, wrapped = data[0], True
    if not isinstance(data, dict):
        return web.json_response({"ok": False, "error": "That does not look like a Home Assistant automation."})
    bad = fact_auto_problem(data)
    if bad:
        return web.json_response({"ok": False, "error": bad})
    cid = str(data.get("id") or "")
    return web.json_response({"ok": True, "alias": str(data.get("alias") or "Imported automation")[:80],
                              "id": cid if ANN_ID_RE.match(cid) else "",
                              "yaml": ann_dump(data) if wrapped else text})


async def fact_automations(request):
    """Automations that already exist in Home Assistant, so one can be loaded into a fact."""
    st, states = await ha(request.app, "GET", "/states")
    out = []
    if st == 200 and isinstance(states, list):
        for e in states:
            if not e["entity_id"].startswith("automation."):
                continue
            a = e.get("attributes") or {}
            cid = str(a.get("id") or "")
            if ANN_ID_RE.match(cid):  # automations without a UI id (defined in YAML files) cannot be edited here
                out.append({"id": cid, "entity": e["entity_id"], "name": a.get("friendly_name") or cid, "state": e.get("state")})
    out.sort(key=lambda x: x["name"].lower())
    return web.json_response({"ok": st == 200, "items": out})


async def fact_automation_get(request):
    aid = str(request.query.get("id", ""))
    if not ANN_ID_RE.match(aid):
        return web.json_response({"ok": False, "error": "Bad automation id."})
    code, cfg = await ha(request.app, "GET", f"/config/automation/config/{aid}", timeout=10)
    if code != 200 or not isinstance(cfg, dict):
        return web.json_response({"ok": False, "error": "Could not load that automation: %s" % errmsg(cfg)})
    return web.json_response({"ok": True, "config": cfg, "yaml": ann_dump(cfg), "id": aid})


async def fact_library_list(request):
    app = request.app
    lib = fact_library()
    st, states = await ha(app, "GET", "/states")
    ok = st == 200 and isinstance(states, list)
    reg = await registry_entities(app) if ok else []
    live = by_config_id(states if ok else [], reg, "script")
    autos = by_config_id(states if ok else [], reg, "automation")
    renamed = sync_lib_names(lib, {i: (autos if fact_is_auto(v.get("state")) else live).get(i) for i, v in lib.items()}, FACTS_LIB, "facts") if ok else []
    items = []
    for i, v in lib.items():
        own_id = str(((v.get("state") or {}).get("autoId")) or "")
        a = autos.get(own_id if ANN_ID_RE.match(own_id) else i + FACT_AUTO_SUFFIX)
        if fact_is_auto(v.get("state")):
            a = autos.get(i)
            items.append({**v, "in_ha": a is not None, "last_run": ((a or {}).get("attributes") or {}).get("last_triggered"),
                          "auto_in_ha": a is not None, "auto_on": bool(a) and a.get("state") == "on"})
            continue
        items.append({**v, "in_ha": i in live, "last_run": ((live.get(i) or {}).get("attributes") or {}).get("last_triggered"),
                      "auto_in_ha": a is not None, "auto_on": bool(a) and a.get("state") == "on"})
    items.sort(key=lambda x: str(x.get("updated") or ""), reverse=True)
    return web.json_response({"items": items, "ha_ok": ok, "renamed": renamed})


async def fact_library_save(request):
    body = await ann_body(request)
    sid = await ann_script_id(body)
    state = clean_ann_state(body.get("state"))
    if state is None:
        return web.json_response({"ok": False, "error": "Nothing to save."})
    warn, note = await push_name_change(request.app, "facts", sid, body.get("name"), body.get("match_id"))
    out = {"ok": True, "item": fact_store(sid, body.get("name"), state), "id_note": note}
    if warn:
        out["name_warning"] = warn
    return web.json_response(out)


async def fact_library_delete(request):
    app = request.app
    body = await ann_body(request)
    sid = await ann_script_id(body)
    aid = sid + FACT_AUTO_SUFFIX
    lib = fact_library()
    removed = False
    st_ = lib.get(sid, {}).get("state") or {}
    if st_.get("autoOnly"):  # your own automation: only forget it here
        lib.pop(sid, None)
        save_json(FACTS_LIB, lib)
        return web.json_response({"ok": True, "script_deleted": False})
    if fact_is_auto(st_):  # a generated fact that is one automation: remove it from HA only if this tool made it
        removed = False
        if body.get("delete_script"):
            code, old = await ha(app, "GET", f"/config/automation/config/{sid}", timeout=10)
            if code == 200 and fact_has_mark(old):
                code, text = await ha_text(app, "DELETE", f"/config/automation/config/{sid}")
                if code != 200:
                    return web.json_response({"ok": False, "error": "HA said %s: %s" % (code, str(text)[:300])})
                await ha_text(app, "POST", "/services/automation/reload", {})
                removed = True
        lib.pop(sid, None)
        save_json(FACTS_LIB, lib)
        return web.json_response({"ok": True, "script_deleted": removed})
    if body.get("delete_script"):
        code, cfg = await ha(app, "GET", f"/config/script/config/{sid}", timeout=10)
        if sid not in lib and not (code == 200 and fact_has_mark(cfg)):
            return web.json_response({"ok": False, "error": "That script wasn't made here, so it won't be deleted."})
        if code == 200:
            code, text = await ha_text(app, "DELETE", f"/config/script/config/{sid}")
            if code != 200:
                return web.json_response({"ok": False, "error": "HA said %s: %s" % (code, str(text)[:300])})
            await ha_text(app, "POST", "/services/script/reload", {})
            removed = True
        code, old = await ha(app, "GET", f"/config/automation/config/{aid}", timeout=10)
        if code == 200 and fact_has_mark(old):
            await ha_text(app, "DELETE", f"/config/automation/config/{aid}")
            await ha_text(app, "POST", "/services/automation/reload", {})
    lib.pop(sid, None)
    save_json(FACTS_LIB, lib)
    return web.json_response({"ok": True, "script_deleted": removed})


async def fact_run(request):
    body = await ann_body(request)
    sid = await ann_script_id(body)
    if body.get("auto_only"):
        st, states = await ha(request.app, "GET", "/states")
        ent = next((e["entity_id"] for e in (states if st == 200 and isinstance(states, list) else [])
                    if e["entity_id"].startswith("automation.") and str((e.get("attributes") or {}).get("id")) == sid), "")
        if not ent:
            return web.json_response({"ok": False, "detail": "That automation is not in Home Assistant yet. Push it first."})
        code, text = await ha_text(request.app, "POST", "/services/automation/trigger", {"entity_id": ent, "skip_condition": True})
        return web.json_response({"ok": code == 200, "detail": str(text)[:300]})
    code, text = await ha_text(request.app, "POST", "/services/script/turn_on", {"entity_id": await script_entity(request.app, sid)})
    return web.json_response({"ok": code == 200, "detail": str(text)[:300]})


# ---------------------------------------------------------------- cards
# AI-assisted dashboard cards. The user describes a card and picks the entities it reads; the AI Task writes the Lovelace
# YAML in the same glass style as the Facts cards. Every card is saved in CARDS_LIB so it can be opened, changed with a
# plain-English note, previewed against live data (Home Assistant renders the template) and copied into a Manual card.
# The AI Task entity and entity list are shared with Announcements. Everything lives under /api/cards/.
CARDS_LIB = DATA / "cards.json"
CARD_ID_RE = re.compile(r"^[a-z0-9_]{1,60}$")
CARD_START, CARD_END = "---CARD START---", "---CARD END---"
CARD_ENT_RE = re.compile(
    r"""(?:['"]|entity(?:_id)?:[ \t]*|states\.)"""
    r"""((?:sensor|binary_sensor|input_boolean|input_text|input_number|input_select|input_datetime|weather|person|light|switch|"""
    r"""climate|media_player|calendar|todo|sun|zone|device_tracker|cover|fan|lock|camera|script|automation|scene|number|select|"""
    r"""button|update|counter|timer|schedule)\.[a-z0-9_]+)""")
CARD_STYLE_GLASS = """GLASS STYLE (the look the user already uses on every card): every card carries a <style> block that restyles ha-card:
ha-card {
  background: rgba(255, 255, 255, 0.06) !important;
  backdrop-filter: blur(28px) saturate(200%) !important;
  -webkit-backdrop-filter: blur(28px) saturate(200%) !important;
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
  border-radius: 20px !important;
  box-shadow: 0 8px 28px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.3) !important;
  color: rgba(255,255,255,0.9);
}
Use that exact recipe, then size the card with a fixed height and overflow: hidden !important. Body text is 18px, headers 20-25px, small dim text 13px at opacity 0.7."""
CARD_EXAMPLES = r"""EXAMPLE 1 - a scrolling news card that reads JSON from a sensor attribute (custom:html-template-card):
type: custom:html-template-card
title: "📰 News Roundup"
ignore_line_breaks: true
content: >
  {% set raw = state_attr('sensor.read_news_report', 'content') | replace('```json', '') | replace('```', '') | trim %}
  {% set data = raw | from_json %}
  {% set total_stories = data.categories | map(attribute='stories') | map('length') | sum %}
  {% set box_height = 630 %}
  {% set needs_scroll = total_stories * 55 > box_height %}
  {% set duration = total_stories * 6 %}
  <style>
    ha-card { background: rgba(255, 255, 255, 0.06) !important; backdrop-filter: blur(28px) saturate(200%) !important; -webkit-backdrop-filter: blur(28px) saturate(200%) !important; border: 1px solid rgba(255, 255, 255, 0.2) !important; border-radius: 20px !important; box-shadow: 0 8px 28px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.3) !important; color: rgba(255,255,255,0.9); height: 690px !important; overflow: hidden !important; }
    .scroll-wrap { position: relative; height: {{ box_height }}px; overflow: hidden; padding: 0 16px; box-sizing: border-box; }
    .scroll-content { width: 100%; font-size: 18px; line-height: 1.3; {% if needs_scroll %} position: absolute; top: 0; animation: scroll-up {{ duration }}s linear infinite; {% else %} position: static; {% endif %} }
    .cat-header { font-size: 20px; font-weight: bold; margin-top: 12px; margin-bottom: 4px; }
    @keyframes scroll-up { 0% { transform: translateY(0); } 5% { transform: translateY(0); } 95% { transform: translateY(-100%); } 100% { transform: translateY(-100%); } }
  </style>
  <div class="scroll-wrap"><div class="scroll-content">
    {% for cat in data.categories %}<div class="cat-header">{{ cat.category }}</div>
    {% for story in cat.stories %}<b>{{ story.headline }}</b><br>{{ story.summary }}<br><br>{% endfor %}{% endfor %}
  </div></div>

EXAMPLE 2 - a short markdown card styled with card_mod:
type: markdown
content: |-
  🎁 {{ states('input_text.birthday_person') }}

  {{ state_attr('sensor.read_birthdays', 'content') }}
card_mod:
  style: |
    ha-card {
      background: rgba(255, 255, 255, 0.06) !important;
      backdrop-filter: blur(28px) saturate(200%) !important;
      -webkit-backdrop-filter: blur(28px) saturate(200%) !important;
      border: 1px solid rgba(255, 255, 255, 0.2) !important;
      border-radius: 20px !important;
      padding: 4px;
      box-shadow: 0 8px 28px rgba(0, 0, 0, 0.4), inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
      color: rgba(255,255,255,0.9);
      font-size: 18px;
      line-height: 1.1;
    }

EXAMPLE 3 - a question-and-answer card: JSON {"title": ..., "body": ...} read from sensor.read_google_result, title shown at 24px on top, the body in a box that auto-scrolls only when the text is long (estimate lines from character count, then animate translateY like example 1)."""


def cards_library():
    lib = load_json(CARDS_LIB, {})
    return lib if isinstance(lib, dict) else {}


def cards_clean_state(state):
    """Keep only a plain JSON object of sensible size."""
    if not isinstance(state, dict) or len(json.dumps(state)) > 300_000:
        return None
    return state


def cards_store(cid, name, state):
    lib = cards_library()
    old = lib.get(cid, {})
    lib[cid] = {"id": cid, "name": str(name or old.get("name") or cid)[:80],
                "state": state if state is not None else old.get("state") or {},
                "updated": time.strftime("%Y-%m-%d %H:%M")}
    save_json(CARDS_LIB, lib)
    return lib[cid]


def cards_entity_brief(s):
    """What the AI is told about one entity: its state and its attributes, long values cut."""
    lines = ["%s (state: %s)" % (s.get("entity_id"), str(s.get("state"))[:200])]
    for k, v in list((s.get("attributes") or {}).items())[:25]:
        if k in ("icon", "supported_features", "attribution", "entity_picture"):
            continue
        t = v if isinstance(v, str) else json.dumps(v, default=str)
        lines.append("  attribute %s: %s" % (k, t[:1500] + (" ...(cut short)" if len(t) > 1500 else "")))
    return "\n".join(lines)


def cards_prompt(req, briefs, toggle, style, current, feedback, source=None):
    look = {"glass": CARD_STYLE_GLASS,
            "plain": "PLAIN STYLE: use normal Home Assistant look. Do not restyle ha-card and do not use card_mod or custom CSS unless the request needs it.",
            "any": "STYLE: pick whatever looks best, but keep it clean and readable on a dark dashboard."}[style]
    p = ["You write Home Assistant Lovelace dashboard cards. Reply with the card only, in the format shown at the bottom.", "",
         "RULES:",
         "- Output ONE card as YAML. Use a vertical-stack when the request needs several cards.",
         "- Prefer custom:html-template-card (HACS) for anything custom, markdown with card_mod for simple text, and built-in cards (entities, glance, gauge, button, tile) when they fit. The user already has html-template-card and card_mod installed.",
         "- Put templates in a literal block (content: | or content: >). Never put {% %} outside a block scalar.",
         "- Be defensive: use default values, check data exists before reading it, and strip ```json and ``` before from_json when a sensor attribute holds JSON that may be wrapped in code fences.",
         "- Only use entity ids that appear in the DATA below or that the user typed in the request. Never invent entity ids.",
         "- No external images, scripts, fonts or links. Use emoji for icons.",
         "- Do NOT wrap the card in a conditional card: the tool adds the show/hide switch by itself.",
         "- If the card scrolls or rotates, only animate when the content is taller than the box.",
         "- No markdown fences, no commentary outside the format below.", "", look, "",
         "REFERENCE CARDS the user already likes (copy their approach and look, not their entities):", CARD_EXAMPLES, ""]
    if briefs:
        p += ["DATA the card can read (live right now):", "\n".join(briefs), ""]
    else:
        p += ["No entities were picked. Use only entity ids the user typed in the request.", ""]
    if source:
        p += ["WHERE THE DATA COMES FROM: %s is written by the user's %s \"%s\". %s The file may be empty right now, so build for this shape "
              "and show a friendly placeholder when it is empty." % (source["sensor"] or "the sensor", source["kind"], source["name"], source["shape"]), ""]
    if toggle:
        p += ["The user will show or hide this card with %s. That is handled for you." % toggle, ""]
    if current and feedback:
        p += ["CURRENT CARD:", current, "", "CHANGE REQUESTED: " + feedback, "Return the whole updated card, keeping everything the user did not ask to change.", ""]
        if req:
            p += ["ORIGINAL REQUEST (for context): " + req, ""]
    else:
        p += ["WHAT THE USER WANTS: " + req, ""]
    p += ["FORMAT (exactly this):", "NAME: short card name", "NOTES: one or two plain sentences on what it does and anything to know",
          CARD_START, "<the card YAML>", CARD_END]
    return "\n".join(p)


def cards_parse(text):
    """(yaml, name, notes) from the AI's answer. Markers are used instead of code fences because card templates contain ``` themselves."""
    t = str(text or "")
    m = re.search(r"^NAME:[ \t]*(.+)$", t, re.M)
    name = m.group(1).strip()[:80] if m else ""
    m = re.search(r"^NOTES:[ \t]*(.+)$", t, re.M)
    notes = m.group(1).strip()[:600] if m else ""
    i, j = t.find(CARD_START), t.rfind(CARD_END)
    if i >= 0 and j > i:
        y = t[i + len(CARD_START):j]
    else:  # no markers: take everything after the NAME/NOTES lines and drop one outer code fence
        y = re.sub(r"^(?:NAME|NOTES):.*$", "", t, flags=re.M)
        y = re.sub(r"^\s*```(?:ya?ml)?[ \t]*\n", "", y)
        y = re.sub(r"\n```\s*$", "", y)
    return y.strip("\n").rstrip() + "\n", name, notes


def cards_check(y):
    """(parsed card, error). A card is a mapping with a type."""
    if not str(y or "").strip():
        return None, "The card is empty."
    try:
        cfg = yaml.safe_load(y)
    except yaml.YAMLError as e:
        return None, "That is not valid YAML: %s" % str(e)[:300]
    if not isinstance(cfg, dict) or not isinstance(cfg.get("type"), str):
        return None, "A card needs to start with a type: line."
    return cfg, ""


def cards_wrap(y, toggle):
    """Wrap a card so it only shows while an input_boolean is on (skipped if it already uses that switch)."""
    if toggle in y:
        return y
    body = "\n".join(("  " + l) if l.strip() else l for l in y.rstrip().split("\n"))
    return "type: conditional\nconditions:\n  - condition: state\n    entity: %s\n    state: 'on'\ncard:\n%s\n" % (toggle, body)


def cards_templates(cfg):
    """Every template Home Assistant can render for preview: html-template-card and markdown content."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            t = str(x.get("type") or "")
            if t in ("custom:html-template-card", "markdown") and isinstance(x.get("content"), str):
                out.append({"type": t, "title": str(x.get("title") or ""), "content": x["content"]})
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(cfg)
    return out


def cards_needs(cfg, y):
    """Custom cards and add-ons the card relies on, so the user knows what has to be installed (HACS)."""
    need = set()

    def walk(x):
        if isinstance(x, dict):
            t = str(x.get("type") or "")
            if t.startswith("custom:"):
                need.add(t)
            if "card_mod" in x:
                need.add("card_mod")
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(cfg)
    return sorted(need)


def cards_unknown(y, known):
    return sorted({m.group(1) for m in CARD_ENT_RE.finditer(y) if m.group(1) not in known})[:12]


async def cards_ai(app, ai, prompt):
    st, data = await ha(app, "POST", "/services/ai_task/generate_data",
                        {"entity_id": ai, "task_name": "Dashboard card", "instructions": prompt},
                        params={"return_response": "true"}, timeout=TIMEOUT)
    if st != 200:
        raise RuntimeError("AI task call failed: %s" % errmsg(data))
    out = ((data.get("service_response") or {}) if isinstance(data, dict) else {}).get("data")
    return "" if out is None else (out if isinstance(out, str) else json.dumps(out))


async def cards_generate(request):
    app = request.app
    b = await ann_body(request)
    req = str(b.get("request") or "").strip()[:4000]
    feedback = str(b.get("feedback") or "").strip()[:2000]
    current = str(b.get("yaml") or "").strip()[:60000]
    toggle = str(b.get("toggle") or "").strip()
    toggle = toggle if re.match(r"^input_boolean\.[a-z0-9_]+$", toggle) else ""
    style = b.get("style") if b.get("style") in ("glass", "plain", "any") else "glass"
    wanted = [e for e in (b.get("entities") or []) if isinstance(e, str) and ANN_ENT_RE.match(e)][:12]
    src = b.get("source") if isinstance(b.get("source"), dict) else None
    source = None
    if src and src.get("shape"):
        sen = str(src.get("sensor") or "")
        source = {"name": str(src.get("name") or "")[:80], "kind": "announcement" if src.get("kind") == "announcement" else "fact",
                  "sensor": sen if ANN_ENT_RE.match(sen) else "", "shape": str(src["shape"])[:1500]}
    if not (req or (current and feedback)):
        return web.json_response({"ok": False, "error": "Say what the card should show first."})
    ai = ann_settings().get("ai_task_entity") or ENTITY
    st, states = await ha(app, "GET", "/states")
    by_id = {s["entity_id"]: s for s in states} if st == 200 and isinstance(states, list) else {}
    briefs, used = [], 0
    for e in wanted:
        if e in by_id:
            t = cards_entity_brief(by_id[e])
            if used + len(t) > 14000:
                t = t[:max(0, 14000 - used)]
            used += len(t)
            briefs.append(t)
    try:
        out = await cards_ai(app, ai, cards_prompt(req, briefs, toggle, style, current, feedback, source))
        y, name, notes = cards_parse(out)
        cfg, err = cards_check(y)
        if err:  # one retry: tell the AI what was wrong with its own answer
            out = await cards_ai(app, ai, cards_prompt(req, briefs, toggle, style, y, "Your last answer was rejected: %s Fix it and return the whole card." % err, source))
            y, name2, notes2 = cards_parse(out)
            name, notes = name or name2, notes or notes2
            cfg, err = cards_check(y)
    except Exception as e:  # noqa: BLE001 - report anything that goes wrong talking to the AI
        return web.json_response({"ok": False, "error": str(e)[:500]})
    if err:
        return web.json_response({"ok": False, "error": "The AI's card was not usable. %s Try rewording, or tap Build again." % err, "raw": y[:6000]})
    if toggle:
        y = cards_wrap(y, toggle)
        cfg, _ = cards_check(y)
    known = set(by_id) | set(wanted)
    return web.json_response({"ok": True, "yaml": y, "name": name, "notes": notes,
                              "unknown": cards_unknown(y, known) if by_id else [], "needs": cards_needs(cfg, y)})


async def cards_check_route(request):
    """Validate YAML the user edited by hand, and say what it needs and which entities it uses that Home Assistant lacks."""
    b = await ann_body(request)
    y = str(b.get("yaml") or "")
    cfg, err = cards_check(y)
    if err:
        return web.json_response({"ok": False, "error": err})
    st, states = await ha(request.app, "GET", "/states")
    known = {s["entity_id"] for s in states} if st == 200 and isinstance(states, list) else None
    return web.json_response({"ok": True, "needs": cards_needs(cfg, y), "unknown": cards_unknown(y, known) if known else []})


async def cards_preview(request):
    """Let Home Assistant render the card's templates against live data, so errors show before the card is pasted."""
    app = request.app
    b = await ann_body(request)
    cfg, err = cards_check(str(b.get("yaml") or ""))
    if err:
        return web.json_response({"ok": False, "error": err})
    items = cards_templates(cfg)[:6]
    out = []
    for it in items:
        code, text = await ha_text(app, "POST", "/template", {"template": it["content"]}, timeout=25)
        row = {"type": it["type"], "title": it["title"]}
        if code == 200:
            row["html"] = str(text)[:300_000]
        else:
            row["error"] = str(text)[:800] or "Home Assistant could not render it."
        out.append(row)
    note = "" if items else "This card has no template to preview (it uses built-in card settings only), so check it on your dashboard."
    return web.json_response({"ok": True, "items": out, "note": note})


async def cards_library_list(request):
    items = sorted(cards_library().values(), key=lambda x: str(x.get("updated") or ""), reverse=True)
    return web.json_response({"items": items})


async def cards_library_save(request):
    b = await ann_body(request)
    state = cards_clean_state(b.get("state"))
    if state is None:
        return web.json_response({"ok": False, "error": "Nothing to save."})
    lib = cards_library()
    cid = str(b.get("id") or "")
    if not CARD_ID_RE.match(cid):
        base = (slug(b.get("name") or "card") or "card")[:55]
        cid, n = base, 2
        while cid in lib:
            cid = "%s_%d" % (base, n)
            n += 1
    return web.json_response({"ok": True, "item": cards_store(cid, b.get("name"), state)})


async def cards_library_delete(request):
    b = await ann_body(request)
    cid = str(b.get("id") or "")
    lib = cards_library()
    if cid not in lib:
        return web.json_response({"ok": False, "error": "That card is not in the list."})
    lib.pop(cid)
    save_json(CARDS_LIB, lib)
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- shared: everything this add-on made, names kept in step
async def registry_entities(app):
    """The entity registry (to find a script whose entity id was renamed in HA). Empty if it can't be read."""
    try:
        r = await ws_call(app, {"type": "config/entity_registry/list"})
        return (r.get("result") or []) if r.get("success") else []
    except Exception:  # noqa: BLE001 - the registry is a nice-to-have here
        return []


def by_config_id(states, reg, domain):
    """{config id: state} for scripts, automations or scenes. Survives an entity id that was changed in HA."""
    by_ent = {s["entity_id"]: s for s in states}
    out = {}
    for s in states:
        d, _, obj = s["entity_id"].partition(".")
        if d != domain:
            continue
        a = s.get("attributes") or {}
        if domain in ("automation", "scene"):
            if a.get("id"):
                out[str(a["id"])] = s
        else:
            out.setdefault(obj, s)
    if domain == "script":  # the registry knows the script's config id even after its entity id was changed
        for e in reg:
            if e.get("platform") == "script" and e.get("entity_id") in by_ent and e.get("unique_id"):
                out[str(e["unique_id"])] = by_ent[e["entity_id"]]
    return out


def set_alias_text(y, name):
    """Change the alias: line of a YAML text (a pasted script or automation) without touching anything else."""
    line = "alias: " + json.dumps(name, ensure_ascii=False)
    y = str(y or "")
    return re.sub(r"^alias:.*$", lambda m: line, y, count=1, flags=re.M) if re.search(r"^alias:", y, re.M) else line + "\n" + y


def pin_file(v, kind):
    """A file name left blank follows the item's name. Fix it to the current one before a rename, so the file
    (and the sensor that reads it, and every card on it) keeps working."""
    st_ = v.get("state") if isinstance(v.get("state"), dict) else {}
    old = st_.get("name") or v.get("name") or v.get("id") or ""
    if kind == "ann":
        t = st_.get("txt")
        if isinstance(t, dict) and t.get("on") and not str(t.get("file") or "").strip() and st_.get("raw") is None:
            t["file"] = (slug(old) or "announcement")[:54] + (".json" if t.get("mode") == "fields" else ".txt")
    elif kind == "facts" and not st_.get("autoOnly") and st_.get("raw") is None and not str(st_.get("file") or "").strip():
        st_["file"] = ((slug(old)[:54].rstrip("_")) or "fact") + ".txt"


def lib_rename(v, name, ha_too, kind="ann"):
    """Rename one saved item (announcement or fact) in the library, form and pasted YAML alike."""
    pin_file(v, kind)
    v["name"] = name[:80]
    st_ = v.get("state") if isinstance(v.get("state"), dict) else {}
    st_["name"] = name
    if isinstance(st_.get("raw"), str):
        st_["raw"] = set_alias_text(st_["raw"], name)
    if isinstance(st_.get("autoRaw"), str) and st_.get("autoOnly"):
        st_["autoRaw"] = set_alias_text(st_["autoRaw"], name)
    v["state"] = st_
    if ha_too:
        v["ha_name"] = name[:80]


def sync_lib_names(lib, live, path, kind="ann"):
    """Pick up names changed in Home Assistant. An item renamed in HA (its HA name moved away from the one we last wrote)
    takes the new name. A name changed here but not pushed yet is left alone."""
    changed = []
    before = json.dumps(lib, sort_keys=True)
    for i, v in lib.items():
        s = live.get(i)
        if not s:
            continue
        now = str((s.get("attributes") or {}).get("friendly_name") or "").strip()[:80]
        if not now or now.startswith("[TEST] "):
            continue
        last = v.get("ha_name")
        if last is None:  # saved before names were tracked: adopt HA's name only if nothing was edited here since the push
            if now != v.get("name") and v.get("pushed_at") and str(v.get("updated") or "") <= str(v.get("pushed_at")):
                changed.append({"id": i, "from": v.get("name"), "to": now})
                lib_rename(v, now, True, kind)
            else:
                v["ha_name"] = now
            continue
        if now != last:
            if now != v.get("name"):
                changed.append({"id": i, "from": v.get("name"), "to": now})
                lib_rename(v, now, True, kind)
            else:
                v["ha_name"] = now
    if json.dumps(lib, sort_keys=True) != before:
        save_json(path, lib)
    if changed:
        log.info("picked up %d name(s) changed in Home Assistant: %s", len(changed), ", ".join("%s -> %s" % (c["from"], c["to"]) for c in changed))
    return changed


RENAME_KINDS = ("script", "automation", "scene", "input_boolean", "input_number", "input_select", "input_text",
                "input_datetime", "counter", "timer")


async def ha_rename(app, kind, cid, name, entity=""):
    """Rename one thing in Home Assistant. Returns (ok, error). Scripts and automations change their alias, scenes their
    name, helpers their name. A name typed in HA's entity settings (the registry) is cleared so the new name shows."""
    if kind in ("script", "automation", "scene"):
        code, cfg = await ha(app, "GET", f"/config/{kind}/config/{cid}", timeout=10)
        if code != 200 or not isinstance(cfg, dict):
            return False, "Could not load %s %s (it may be written in a YAML file, which can't be changed from here)." % (kind, cid)
        cfg["name" if kind == "scene" else "alias"] = name
        code, text = await ha_text(app, "POST", f"/config/{kind}/config/{cid}", cfg)
        if code != 200:
            return False, "HA said %s: %s" % (code, str(text)[:300])
        await ha_text(app, "POST", f"/services/{kind}/reload", {})
    elif kind in HELPER_FIELDS:
        r = await ws_call(app, {"type": f"{kind}/update", f"{kind}_id": cid, "name": name})
        if not r.get("success"):  # a helper written in YAML: give the entity its own name instead
            if not entity:
                return False, (r.get("error") or {}).get("message", "Home Assistant would not rename it.")
            r = await ws_call(app, {"type": "config/entity_registry/update", "entity_id": entity, "name": name})
            return (True, "") if r.get("success") else (False, (r.get("error") or {}).get("message", "Home Assistant would not rename it."))
    else:
        return False, "Can't rename a %s." % kind
    if entity:  # a name set in the entity settings wins over the alias, so clear it
        try:
            r = await ws_call(app, {"type": "config/entity_registry/get", "entity_id": entity})
            if r.get("success") and (r.get("result") or {}).get("name"):
                await ws_call(app, {"type": "config/entity_registry/update", "entity_id": entity, "name": None})
        except Exception:  # noqa: BLE001 - the alias is already changed, this is a nice-to-have
            pass
    return True, ""


async def script_entity(app, sid):
    """The entity id of a script made here, even if its entity id was changed in Home Assistant."""
    for e in await registry_entities(app):
        if e.get("platform") == "script" and str(e.get("unique_id")) == sid and e.get("entity_id"):
            return e["entity_id"]
    return "script." + sid


async def match_entity_id(app, entity, name):
    """Change an entity's id so it follows its name (script.old_name -> script.new_name). Returns (new id or "", note).
    "" with an empty note means it already matches. The old id stops working everywhere in Home Assistant that used it."""
    dom, _, cur = str(entity or "").partition(".")
    base = re.sub(r"^_+|_+$", "", slug(name))[:60]
    if not dom or not base:
        return "", ""
    st, states = await ha(app, "GET", "/states")
    taken = {x["entity_id"] for x in states} if st == 200 and isinstance(states, list) else set()
    new, n = "%s.%s" % (dom, base), 2
    if new == entity:
        return "", ""
    while new in taken and new != entity:
        new, n = "%s.%s_%d" % (dom, base, n), n + 1
    r = await ws_call(app, {"type": "config/entity_registry/update", "entity_id": entity, "new_entity_id": new})
    if not r.get("success"):
        return "", "Could not change the entity id of %s: %s" % (entity, (r.get("error") or {}).get("message", "Home Assistant said no."))
    return new, "Entity id is now %s (was %s). Update anything that still uses the old one." % (new, entity)


async def rename_lib_item(app, lib_kind, cid, name, match_id=None, only_ids=False):
    """Give a saved announcement or fact its new name in Home Assistant (the script, or the automation for a fact that is
    one, plus the "<name> (auto)" schedule) and in the library. match_id: also change the entity id to match the name
    (None follows the match_entity_id option). Returns (ok, error, in_ha, note)."""
    if not ANN_ID_RE.match(cid):
        return False, "Bad id.", False, ""
    match_id = bool(OPTS.get("match_entity_id")) if match_id is None else bool(match_id)
    note = ""
    st, states = await ha(app, "GET", "/states")
    ok_states = st == 200 and isinstance(states, list)
    reg = await registry_entities(app) if ok_states else []
    scripts = by_config_id(states if ok_states else [], reg, "script")
    autos = by_config_id(states if ok_states else [], reg, "automation")
    path, mark = (ANN_LIB, ANN_MARK) if lib_kind == "ann" else (FACTS_LIB, FACT_MARK)
    lib = load_json(path, {})
    v = lib.get(cid) if isinstance(lib, dict) else None
    if not v:
        return False, "That is not saved here.", False, ""
    st_ = v.get("state") or {}
    one_auto = lib_kind == "facts" and fact_is_auto(st_)
    kind = "automation" if one_auto else "script"
    live = (autos if one_auto else scripts).get(cid)
    in_ha = False
    if live:
        if not only_ids:  # only_ids: the name is already right in Home Assistant, just make the entity ids follow it
            ok, err = await ha_rename(app, kind, cid, name, live.get("entity_id", ""))
            if not ok:
                return False, err, False, ""
        in_ha = True
        if match_id:
            _new, note = await match_entity_id(app, live.get("entity_id", ""), name)
        if not one_auto:  # its schedule automation, if this tool made it, follows: "<name> (auto)"
            aid = str(st_.get("autoId") or "") if lib_kind == "facts" else ""
            aid = aid if ANN_ID_RE.match(aid) else cid + (ANN_AUTO_SUFFIX if lib_kind == "ann" else FACT_AUTO_SUFFIX)
            code, acfg = await ha(app, "GET", f"/config/automation/config/{aid}", timeout=10)
            if code == 200 and isinstance(acfg, dict) and acfg.get("description") == mark:
                if not only_ids:
                    await ha_rename(app, "automation", aid, name + " (auto)", (autos.get(aid) or {}).get("entity_id", ""))
                if match_id and (autos.get(aid) or {}).get("entity_id"):
                    await match_entity_id(app, autos[aid]["entity_id"], name + " (auto)")
    lib = load_json(path, {})  # re-read: nothing else may have changed it while we talked to Home Assistant
    v = lib.get(cid)
    if v:
        lib_rename(v, name, in_ha, lib_kind)
        save_json(path, lib)
    h = load_json(HIST, [])
    for x in h:
        if x.get("entity") in ("script." + cid, "automation." + cid):
            x["name"] = name
    save_json(HIST, h)
    return True, "", in_ha, note


async def push_name_change(app, lib_kind, sid, new, match_id=None):
    """A name edited in the editor and only Saved (not pushed): if the item is already in Home Assistant, rename it there
    right away so both sides always show the same name. match_id: also make the entity id follow the name (even when the
    name itself did not change). Returns (warning text or "", note about the entity id or "")."""
    new = re.sub(r"\s+", " ", str(new or "")).strip()[:80]
    lib = ANN_LIB if lib_kind == "ann" else FACTS_LIB
    old = (load_json(lib, {}) or {}).get(sid)
    if not new or not old or not (old.get("pushed_at") or old.get("ha_name")):
        return "", ""
    same = new == old.get("name")
    if same and not match_id:
        return "", ""
    try:
        ok, err, _in_ha, note = await rename_lib_item(app, lib_kind, sid, new, match_id, only_ids=same)
    except Exception as e:  # noqa: BLE001 - the save itself must still go through
        log.warning("couldn't rename %s in Home Assistant: %s", sid, e)
        return "Saved here, but Home Assistant could not be renamed: %s" % e, ""
    return ("" if ok else "Saved here, but Home Assistant would not rename it: %s" % err), note


async def match_ids_after_push(app, name, script_id=None, auto_id=None):
    """After a push with the box ticked: the entity ids follow the name. Returns a note ("" if nothing changed)."""
    st, states = await ha(app, "GET", "/states")
    if not (st == 200 and isinstance(states, list)):
        return ""
    reg = await registry_entities(app)
    notes = []
    if script_id:
        s_ = by_config_id(states, reg, "script").get(script_id)
        if s_:
            notes.append((await match_entity_id(app, s_["entity_id"], name))[1])
    if auto_id:
        a_ = by_config_id(states, reg, "automation").get(auto_id)
        if a_:
            notes.append((await match_entity_id(app, a_["entity_id"], name + (" (auto)" if script_id else "")))[1])
    return " ".join(n for n in notes if n)


async def match_default(request):
    return web.json_response({"on": bool(OPTS.get("match_entity_id"))})


async def sync_names_once(app):
    """Pick up names changed in Home Assistant for every saved announcement and fact."""
    st, states = await ha(app, "GET", "/states")
    if not (st == 200 and isinstance(states, list)):
        return
    reg = await registry_entities(app)
    live = by_config_id(states, reg, "script")
    autos = by_config_id(states, reg, "automation")
    sync_lib_names(ann_library(), live, ANN_LIB)
    fl = fact_library()
    sync_lib_names(fl, {i: (autos if fact_is_auto(v.get("state")) else live).get(i) for i, v in fl.items()}, FACTS_LIB, "facts")


async def name_sync_loop(app):
    """Every half minute, so a rename made in Home Assistant shows up here without opening anything."""
    await asyncio.sleep(25)
    while True:
        try:
            await sync_names_once(app)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - try again next round
            log.warning("name sync: %s", e)
        await asyncio.sleep(30)


async def rename_route(request):
    """Rename something made here, in Home Assistant and in the add-on at the same time.
    lib=ann / facts / cards: a saved announcement, fact or card (by its id). Otherwise kind + id of a thing in HA."""
    app = request.app
    b = await ann_body(request)
    name = re.sub(r"\s+", " ", str(b.get("name") or "")).strip()[:80]
    lib_kind, cid = str(b.get("lib") or ""), str(b.get("id") or "")
    if not name:
        return web.json_response({"ok": False, "error": "Type a name."})
    st, states = await ha(app, "GET", "/states")
    ok_states = st == 200 and isinstance(states, list)
    reg = await registry_entities(app) if ok_states else []
    scripts = by_config_id(states if ok_states else [], reg, "script")
    autos = by_config_id(states if ok_states else [], reg, "automation")
    try:
        if lib_kind == "cards":
            lib = cards_library()
            if cid not in lib:
                return web.json_response({"ok": False, "error": "That card is not saved here."})
            lib[cid]["name"] = name
            if isinstance(lib[cid].get("state"), dict):
                lib[cid]["state"]["name"] = name
            save_json(CARDS_LIB, lib)
            return web.json_response({"ok": True, "name": name})
        if lib_kind in ("ann", "facts"):
            ok, err, in_ha, note = await rename_lib_item(app, lib_kind, cid, name, b.get("match_id"))
            if not ok:
                return web.json_response({"ok": False, "error": err})
            return web.json_response({"ok": True, "name": name, "in_ha": in_ha, "note": note})
        kind = str(b.get("kind") or "")
        if kind == "template":  # a template sensor this add-on manages: its name lives in our own file
            store = load_json(STORE, {})
            if cid not in store:
                return web.json_response({"ok": False, "error": "That template sensor is not managed here."})
            store[cid]["name"] = name
            save_json(STORE, store)
            render_package(store)
            await ha(app, "POST", "/services/template/reload", {})
            return web.json_response({"ok": True, "name": name})
        if kind not in RENAME_KINDS or not re.match(r"^[A-Za-z0-9_\-]{1,120}$", cid):
            return web.json_response({"ok": False, "error": "Can't rename that."})
        entity = str(b.get("entity") or "")
        ok, err = await ha_rename(app, kind, cid, name, entity if ANN_ENT_RE.match(entity) else "")
        if not ok:
            return web.json_response({"ok": False, "error": err})
        note = ""
        if (bool(OPTS.get("match_entity_id")) if b.get("match_id") is None else bool(b.get("match_id"))) and ANN_ENT_RE.match(entity):
            new_ent, note = await match_entity_id(app, entity, name)
            if new_ent:
                entity = new_ent
        h = load_json(HIST, [])
        for x in h:
            if entity and x.get("entity") == entity:
                x["name"] = name
        save_json(HIST, h)
        # it may also be a saved announcement or fact: keep that library in step
        for path in (ANN_LIB, FACTS_LIB):
            lib = load_json(path, {})
            if isinstance(lib, dict) and cid in lib and kind in ("script", "automation"):
                lib_rename(lib[cid], name, True, "ann" if path == ANN_LIB else "facts")
                save_json(path, lib)
        return web.json_response({"ok": True, "name": name, "note": note})
    except Exception as e:  # noqa: BLE001 - report anything that goes wrong talking to Home Assistant
        log.exception("rename failed")
        return web.json_response({"ok": False, "error": "Could not reach Home Assistant: %s" % e})


def ann_file_info(v):
    """For a saved announcement: the file and sensor it writes (if any) and what is in it."""
    st_ = v.get("state") or {}
    t = st_.get("txt") if isinstance(st_.get("txt"), dict) else {}
    if not t.get("on") or st_.get("raw") is not None:
        return None
    name = st_.get("name") or v.get("name") or v.get("id")
    fields = []
    if t.get("mode") == "fields":
        seen = set()
        for f in t.get("fields") or []:
            k = re.sub(r"[^a-z0-9_]+", "_", str((f or {}).get("key") or "").lower()).strip("_")[:40]
            if k and k not in seen and k != "notification":
                seen.add(k)
                fields.append({"key": k, "hint": str(f.get("hint") or ""), "as": f.get("as") if f.get("as") in ("title", "text", "small", "hide") else "text"})
    file = re.sub(r"[^A-Za-z0-9_\-./]", "", str(t.get("file") or "")) or ((slug(name) or "announcement")[:54] + (".json" if fields else ".txt"))
    sensor = str(t.get("sensor") or "").strip() or ("sensor.read_" + (re.sub(r"\.[^.]*$", "", file.split("/")[-1]) or "announcement"))
    say = t.get("say") if any(f["key"] == t.get("say") for f in fields) else (next((f["key"] for f in fields if f["as"] == "text"), fields[0]["key"] if fields else ""))
    role = {"title": "title", "text": "main text", "small": "small bottom line", "hide": "not shown"}
    if fields:
        shape = ("Its content attribute holds ONE JSON object written by the \"%s\" announcement, for example {%s}. Fields: %s. "
                 "Strip ```json and ``` then parse with from_json(default={}). If it is not JSON, show the raw text."
                 % (name, ", ".join('"%s": "..."' % f["key"] for f in fields),
                    "; ".join("%s = %s (show as %s)" % (f["key"], "the spoken announcement" if f["key"] == say else (f["hint"] or "short text"), role[f["as"]]) for f in fields)))
    else:
        shape = "Its content attribute holds the plain text of the last \"%s\" announcement (what it said out loud)." % name
    return {"file": file, "sensor": sensor, "fields": fields, "say": say, "shape": shape}


def fact_file_info(v):
    st_ = v.get("state") or {}
    if st_.get("autoOnly"):
        card = st_.get("card") or {}
        return {"sensor": card.get("sensor") or "", "shape": "It is the user's own automation, so its file format is unknown. Read the sensor's live attributes."} if card.get("sensor") else None
    name = st_.get("name") or v.get("name") or v.get("id")
    file = str(st_.get("file") or "").strip() or (slug(name) + ".txt")
    card = st_.get("card") or {}
    sensor = card.get("sensor") or st_.get("lastEntity") or ("sensor.read_" + re.sub(r"\.[^.]*$", "", file.split("/")[-1]))
    if st_.get("style") == "json":
        key = re.sub(r"[^A-Za-z0-9_]", "", str(st_.get("listKey") or "items")) or "items"
        fl = [f for f in (st_.get("fields") or []) if isinstance(f, dict) and f.get("key")]
        shape = ("Its content attribute holds JSON written by the \"%s\" fact: {\"%s\": [ {%s}, ... ]}, a list of items. Field meanings: %s. "
                 "Strip ```json and ``` then parse with from_json(default={})."
                 % (name, key, ", ".join('"%s": ...' % f["key"] for f in fl), "; ".join("%s = %s (%s)" % (f["key"], f.get("hint") or "", f.get("type") or "text") for f in fl)))
    else:
        shape = ("Its content attribute holds the text of the \"%s\" fact%s." % (name, ", with a first line starting with # that is its title" if st_.get("heading") or st_.get("style") == "titled" else ""))
    return {"file": file, "sensor": sensor, "fields": st_.get("fields") or [], "list_key": st_.get("listKey") or "", "shape": shape}


def made_index():
    """One list of everything made with this add-on, so every tab (and the Builder's AI) can see the others."""
    out = []
    for i, v in ann_library().items():
        st_ = v.get("state") or {}
        out.append({"kind": "announcement", "id": i, "name": v.get("name") or i, "entity": "script." + i,
                    "about": str(st_.get("task") or ("Your own script" if st_.get("raw") is not None else ""))[:200],
                    "pushed": bool(v.get("pushed_at")), "toggle": st_.get("cardSw") or "", "file": ann_file_info(v)})
    for i, v in fact_library().items():
        st_ = v.get("state") or {}
        one = fact_is_auto(st_)
        out.append({"kind": "fact", "id": i, "name": v.get("name") or i, "entity": ("automation." if one else "script.") + i,
                    "about": str(st_.get("task") or "")[:200], "pushed": bool(v.get("pushed_at")),
                    "toggle": (st_.get("card") or {}).get("toggle") or "", "file": fact_file_info(v)})
    for i, v in cards_library().items():
        st_ = v.get("state") or {}
        out.append({"kind": "card", "id": i, "name": v.get("name") or i, "entity": "", "about": str(st_.get("request") or "")[:200],
                    "toggle": st_.get("toggle") or "", "entities": st_.get("entities") or [], "from": st_.get("source") or None})
    return out


async def made_route(request):
    return web.json_response({"items": made_index(), "history": load_json(HIST, [])})


def made_context():
    """What the Builder's AI is told about things made in the other tabs, so a request can use them by name."""
    L = []
    for x in made_index():
        if x["kind"] == "card":
            continue
        line = "%s | %s | %s" % (x["entity"], x["name"], "voice announcement" if x["kind"] == "announcement" else "dashboard fact (AI writes a file)")
        if x.get("about"):
            line += " | " + x["about"][:120]
        if x.get("file"):
            line += " | writes the file read by %s" % x["file"]["sensor"]
        if x.get("toggle"):
            line += " | shows a card with %s" % x["toggle"]
        if not x.get("pushed"):
            line += " | (draft, not in Home Assistant yet)"
        L.append(line)
    if not L:
        return ""
    return ("\n\nMADE IN THIS ADD-ON'S OTHER TABS (run an announcement with script.turn_on or by calling the script; "
            "a fact script the same way; a fact automation with automation.trigger). entity | name | what it is:\n" + "\n".join(L[:60]))


# ---------------------------------------------------------------- import: turn a hand-made script or automation into the form
# A pasted (or picked) script or automation is read step by step and rebuilt as a normal Announcement or Fact, so it is
# edited with the same form as everything made here instead of as raw YAML. Data the prompt reads becomes data sources,
# speakers and phones become outputs, MQTT publishing becomes the file, triggers become the schedule. The AI Task only
# splits the prompt into the instructions and the voice. Anything that does not fit is listed, and the original is kept.
CONV_PRESTEP = {"weather.get_forecasts": "weather", "calendar.get_events": "calendar", "todo.get_items": "todo"}
CONV_KNOWN = ("ai_task.generate_data", "tts.speak", "notify.", "media_player.volume_set", "media_player.media_pause",
              "media_player.media_play", "media_player.media_play_pause", "input_boolean.turn_on", "input_boolean.turn_off",
              "mqtt.publish", "weather.get_forecasts", "calendar.get_events", "todo.get_items", "script.turn_on")
CONV_SKIP_VARS = {"current_time", "seed", "now", "trigger", "this"}


def conv_load(text):
    """(config, kind 'script'|'automation', id, error) from pasted YAML in any of the usual shapes."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, "", "", "YAML problem: %s" % str(e)[:400]
    cid = ""
    for _ in range(3):
        if isinstance(data, list):
            if len(data) == 1 and isinstance(data[0], dict) and ({"triggers", "trigger", "actions", "action", "sequence"} & set(data[0])):
                data = data[0]
            elif data and all(isinstance(x, dict) and ("action" in x or "service" in x or "variables" in x) for x in data):
                data = {"sequence": data}
            else:
                return None, "", "", "That has more than one script or automation in it. Paste one at a time."
        if isinstance(data, dict) and len(data) == 1 and isinstance(next(iter(data.values())), (dict, list)) \
                and not ({"triggers", "trigger", "actions", "action", "sequence"} & set(data)):
            k = next(iter(data))
            if k not in ("script", "automation"):
                cid = str(k)
            data = data[k]
    if not isinstance(data, dict):
        return None, "", "", "That does not look like a Home Assistant script or automation."
    if {"triggers", "trigger", "actions", "action"} & set(data) and "sequence" not in data:
        cid = str(data.get("id") or cid)
        return data, "automation", cid, ""
    if isinstance(data.get("sequence"), (list, dict)):
        return data, "script", cid, ""
    return None, "", "", "That needs a sequence: (script) or triggers: and actions: (automation)."


def conv_list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def conv_walk(steps, out, depth=0):
    """Every step, nested ones included (if / choose / parallel / sequence / repeat), in order."""
    for st in conv_list(steps):
        if not isinstance(st, dict):
            continue
        out.append((st, depth))
        for k in ("then", "else", "sequence", "parallel", "default"):
            if k in st and k != "sequence" or (k == "sequence" and "action" not in st and "service" not in st):
                conv_walk(st.get(k), out, depth + 1)
        for c in conv_list(st.get("choose")):
            if isinstance(c, dict):
                conv_walk(c.get("sequence"), out, depth + 1)
        if isinstance(st.get("repeat"), dict):
            conv_walk(st["repeat"].get("sequence"), out, depth + 1)
    return out


def conv_action(st):
    return str(st.get("action") or st.get("service") or "")


def conv_targets(st, key="entity_id"):
    t = st.get("target") if isinstance(st.get("target"), dict) else {}
    d = st.get("data") if isinstance(st.get("data"), dict) else {}
    v = t.get(key) or d.get(key) or st.get(key)
    return [str(x) for x in conv_list(v)]


def conv_secs(d):
    if isinstance(d, (int, float)):
        return int(d)
    if isinstance(d, str):
        p = [int(x) if x.isdigit() else 0 for x in d.split(":")]
        return sum(v * 60 ** i for i, v in enumerate(reversed(p)))
    if isinstance(d, dict):
        return int(d.get("hours", 0) or 0) * 3600 + int(d.get("minutes", 0) or 0) * 60 + int(d.get("seconds", 0) or 0)
    return 0


def conv_schedule(cfg, fact):
    """Triggers and conditions -> the form's schedule. Returns (auto, notes, all_mapped)."""
    a = {"on": False, "every": 0, "unit": "minutes" if fact else "hours", "at": "", "watch": "", "watchAttr": "", "watchFor": 0, "home": []}
    notes, ok = [], True
    for t in conv_list(cfg.get("triggers") or cfg.get("trigger")):
        if not isinstance(t, dict):
            continue
        kind = t.get("trigger") or t.get("platform")
        if kind == "time_pattern" and not a["every"]:
            m = re.match(r"^/(\d+)$", str(t.get("minutes", "")).strip())
            h = re.match(r"^/(\d+)$", str(t.get("hours", "")).strip())
            if h:
                a.update(every=int(h.group(1)), unit="hours")
                continue
            if m:
                a.update(every=int(m.group(1)), unit="minutes")
                continue
        if kind == "time" and not a["at"] and re.match(r"^\d{1,2}:\d{2}", str(t.get("at", ""))):
            a["at"] = str(t["at"])[:5].rjust(5, "0")
            continue
        if kind == "state" and not a["watch"]:
            ents = conv_list(t.get("entity_id"))
            if len(ents) == 1:
                a.update(watch=str(ents[0]), watchAttr=str(t.get("attribute") or ""), watchFor=conv_secs(t.get("for")))
                continue
        ok = False
        notes.append("A trigger the form can't hold was left out: %s" % json.dumps(t, default=str)[:160])
    home = []

    def cond(c):
        if not isinstance(c, dict):
            return False
        k = c.get("condition")
        if k == "or":
            return all(cond(x) for x in conv_list(c.get("conditions")))
        ents = [str(e) for e in conv_list(c.get("entity_id"))]
        if k == "state" and ents and str(c.get("state")) in ("home", "on", "True"):
            home.extend(ents)
            return True
        if k == "numeric_state" and ents and all(e.startswith("zone.") for e in ents) and c.get("above") in (0, "0"):
            home.extend(ents)
            return True
        return False
    for c in conv_list(cfg.get("conditions") or cfg.get("condition")):
        if not cond(c):
            ok = False
            notes.append("A condition the form can't hold was left out: %s" % json.dumps(c, default=str)[:160])
    a["home"] = list(dict.fromkeys(home))
    a["on"] = bool(a["every"] or a["at"] or a["watch"])
    return a, notes, ok


def conv_sources(variables, presteps, instructions, existing, fact):
    """Variables the prompt reads -> data sources (reusing ones that already exist), random lists (facts) and the
    'last fact' sensor. Returns (sources, picks, last, labels) where labels maps a variable name to its source label."""
    def used(name):
        return re.search(r"(\{\{|\{%)[^}]*\b" + re.escape(name) + r"\b", instructions) is not None
    srcs, picks, last, labels = [], [], None, {}

    def add(var, src):
        for s in existing:  # reuse a source that reads the same thing
            if s.get("type") == src["type"] and (
                    (src["type"] in ("weather", "todo", "news", "trash", "entity") and s.get("entity") == src.get("entity")
                     and str(s.get("attribute") or "") == str(src.get("attribute") or ""))
                    or (src["type"] == "calendar" and sorted(s.get("entities") or []) == sorted(src.get("entities") or []))
                    or (src["type"] == "template" and str(s.get("template") or "").strip() == str(src.get("template") or "").strip())):
                srcs.append({"var": var, "existing": s.get("id"), "label": s.get("label") or s.get("id")})
                labels[var] = s.get("label") or s.get("id")
                return
        srcs.append({"var": var, "new": src, "label": src["label"]})
        labels[var] = src["label"]

    done_pre = set()
    for var, tpl in variables.items():
        if var in CONV_SKIP_VARS or var.startswith("src_") or not used(var):
            continue
        t = str(tpl)
        pre = next((p for p in presteps if re.search(r"\b" + re.escape(p["var"]) + r"\b", t)), None)
        label = var.replace("_", " ").strip().title()[:40] or var
        m = re.match(r"^\s*\{\{\s*\[(.*)\]\s*\|\s*random\s*\}\}\s*$", t, re.S)
        if m and fact:
            try:
                items = ast.literal_eval("[" + m.group(1) + "]")
                picks.append({"name": re.sub(r"[^a-z0-9_]", "_", var.lower())[:24], "items": "\n".join(str(i) for i in items)})
                continue
            except (ValueError, SyntaxError):
                pass
        sa = re.match(r"^\s*\{\{\s*state_attr\(\s*['\"]([a-z_]+\.[a-z0-9_]+)['\"]\s*,\s*['\"]([\w .\-]+)['\"]\s*\)[^}]*\}\}\s*$", t)
        st = re.match(r"^\s*\{\{\s*states\(\s*['\"]([a-z_]+\.[a-z0-9_]+)['\"]\s*\)[^}]*\}\}\s*$", t)
        if fact and sa and sa.group(2) == "content" and last is None:  # the fact the file holds now: used to avoid repeats
            last = {"entity": sa.group(1), "attr": "content", "var": var}
            continue
        if pre:
            done_pre.add(pre["var"])
            add(var, dict(pre["src"], label=label))
        elif sa:
            add(var, {"type": "entity", "label": label, "entity": sa.group(1), "attribute": sa.group(2)})
        elif st:
            add(var, {"type": "entity", "label": label, "entity": st.group(1), "attribute": ""})
        else:
            add(var, {"type": "template", "label": label, "template": t.strip()})
    for p in presteps:  # a response the prompt reads directly, e.g. {{ forecast }}
        if p["var"] not in done_pre and used(p["var"]):
            add(p["var"], dict(p["src"], label=p["src"]["label"]))
    return srcs, picks, last, labels


async def conv_ai(app, target, instructions, branches, labels, extra):
    """Ask the AI Task to split the prompt into the form's fields. Returns (dict, error)."""
    ai = ann_settings().get("helper_ai_task_entity") or ann_settings().get("ai_task_entity") or ENTITY
    data = "; ".join("%s = %s" % (k, v) for k, v in labels.items()) or "none"
    common = ("You convert a hand-written Home Assistant %s into a form. The original prompt it sends to an AI is below. "
              "In the form, each data variable is given to the AI separately under its label, before the instructions, so the "
              "instructions must NOT contain the data placeholders any more: refer to the data by its label instead (for example "
              "'use the weather above'). Keep every rule, condition and detail the user wrote. Do not add new rules.\n"
              "Data variables and their labels: %s\n%s\nORIGINAL PROMPT:\n%s\n"
              % ("voice announcement" if target == "announcement" else "dashboard fact", data, extra, instructions[:8000]))
    if target == "announcement":
        more = ""
        if len(branches) > 1:
            more = ("The original has a different prompt per personality. For each, give only its voice and tone rules.\n"
                    + "\n".join("PERSONALITY %s:\n%s" % (k, v[:2500]) for k, v in branches.items()) + "\n")
        prompt = common + more + (
            "Reply with ONLY JSON, no code fences: {\"name\": \"short name\", \"task\": \"what the announcement should do: the "
            "instructions without the voice/tone part and without output-format rules\", \"style\": \"only the voice, tone, "
            "personality and language rules (empty if none)\", \"styles\": {\"personality name\": \"its voice rules\"} (only when "
            "there are several personalities), \"length\": max characters if the prompt says one else 0, \"fields\": [{\"key\": "
            "\"name\", \"hint\": \"what goes in it\"}] (only when the prompt asks the AI for JSON with keys other than speech and "
            "notification, else []), \"say\": \"the key of the field that is spoken, or empty\"}")
    else:
        prompt = common + (
            "Reply with ONLY JSON, no code fences: {\"name\": \"short name\", \"task\": \"what the fact should be about, without "
            "output-format rules\", \"style\": \"plain|titled|list|json\" (titled when the answer is 'Title ||| fact', json when it "
            "asks for a JSON list), \"title_hint\": \"what the title is, only for titled\", \"length\": max characters or 0, "
            "\"count\": number of lines or items or 0, \"swear\": \"none|mild|rated\", \"real\": true/false (must be real and "
            "verifiable), \"obscure\": true/false, \"skip\": \"famous examples it must avoid, or empty\", \"no_people\": true/false "
            "(keep the household out), \"avoid_last\": true/false (told not to repeat the previous fact), \"extra\": \"any other "
            "rules, word for word\", \"list_key\": \"only json: the list's key\", \"fields\": [{\"key\": \"name\", \"hint\": \"what it "
            "holds\", \"type\": \"text|number|yesno\"}] (only json), \"sort_by\": \"field or empty\", \"sort_dir\": \"asc|desc\", "
            "\"keep_if\": \"a template test on item p, or empty\", \"uses_date\": true/false}")
    j, err = await ann_ai_json(app, ai, "Import converter", prompt)
    return (j if isinstance(j, dict) else None), err


def conv_strip_vars(text, labels):
    """No AI: point the data placeholders at their labels so nothing is lost."""
    for var, label in labels.items():
        text = re.sub(r"\{\{\s*" + re.escape(var) + r"\s*\}\}", "(the %s above)" % label, text)
    text = re.sub(r"\{\{\s*(current_time|now\(\)[^}]*)\s*\}\}", "(the current time above)", text)
    return re.sub(r"\{\{\s*seed\s*\}\}", "", text).strip()


async def convert_route(request):
    app = request.app
    b = await ann_body(request)
    target = "fact" if b.get("target") == "fact" else "announcement"
    text = str(b.get("yaml") or "")
    if not text.strip():
        return web.json_response({"ok": False, "error": "Paste a script or automation first, or pick one."})
    if len(text) > 150_000:
        return web.json_response({"ok": False, "error": "That is too big to import."})
    cfg, kind, cid, err = conv_load(text)
    if err:
        return web.json_response({"ok": False, "error": err})
    notes, fact = [], target == "fact"
    s = ann_settings()
    existing = [x for x in (b.get("sources") or []) if isinstance(x, dict)]
    script_id = cid if kind == "script" else ""
    auto_id = cid if kind == "automation" else ""
    steps = cfg.get("sequence") if kind == "script" else (cfg.get("actions") or cfg.get("action"))
    sched_cfg = cfg if kind == "automation" else {}
    name_from = cfg
    # an automation that only runs one script: read that script's steps
    acts = [x for x in conv_list(steps) if isinstance(x, dict)]
    if kind == "automation" and len(acts) == 1:
        a0 = conv_action(acts[0])
        called = a0[7:] if a0.startswith("script.") and a0 != "script.turn_on" else (conv_targets(acts[0]) or [""])[0].replace("script.", "") if a0 == "script.turn_on" else ""
        if called and ANN_ID_RE.match(called):
            code, scfg = await ha(app, "GET", f"/config/script/config/{called}", timeout=10)
            if code == 200 and isinstance(scfg, dict):
                steps, script_id = scfg.get("sequence"), called
                name_from = scfg
                notes.append("This automation runs script.%s, so that script's steps were read too." % called)
    flat = conv_walk(steps, [])
    if b.get("auto_yaml"):  # facts: a script plus the automation that runs it
        acfg, akind, aid2, aerr = conv_load(str(b["auto_yaml"]))
        if acfg and akind == "automation":
            sched_cfg, auto_id = acfg, auto_id or aid2
    variables = {}
    for k, v in (cfg.get("variables") or {}).items() if isinstance(cfg.get("variables"), dict) else []:
        variables[k] = v
    presteps, ai_steps, branches, unknown = [], [], {}, []
    for st, _d in flat:
        if isinstance(st.get("variables"), dict):
            for k, v in st["variables"].items():
                if isinstance(v, str):
                    variables[k] = v
        act = conv_action(st)
        if act in CONV_PRESTEP and st.get("response_variable"):
            typ = CONV_PRESTEP[act]
            ents = conv_targets(st)
            src = {"type": typ, "label": TYPE_LABELS[typ]}
            if typ == "calendar":
                src.update(entities=ents, days=max(1, conv_secs((st.get("data") or {}).get("duration")) // 86400) or 7)
            else:
                src["entity"] = ents[0] if ents else ""
            presteps.append({"var": str(st["response_variable"]), "src": src})
        elif act == "ai_task.generate_data":
            ai_steps.append(st)
        elif act and not any(act == k or (k.endswith(".") and act.startswith(k)) for k in CONV_KNOWN):
            unknown.append(act)
    for st, _d in flat:  # a prompt per personality: choose on an input_select
        for c in conv_list(st.get("choose")):
            if not isinstance(c, dict):
                continue
            conds = conv_list(c.get("conditions"))
            ai_in = [x for x, _ in conv_walk(c.get("sequence"), []) if conv_action(x) == "ai_task.generate_data"]
            if conds and ai_in and isinstance(conds[0], dict) and conds[0].get("state") is not None:
                branches[str(conds[0]["state"])] = str((ai_in[0].get("data") or {}).get("instructions") or "")
    if not ai_steps:
        return web.json_response({"ok": False, "error": "There is no ai_task.generate_data step in it, so there is nothing to put in the form. Keep it as written instead."})
    main_ai = ai_steps[-1] if branches else ai_steps[0]
    aid_ = (main_ai.get("data") or {})
    instructions = str(aid_.get("instructions") or "")
    if branches:
        instructions = next(iter(branches.values())) or instructions
    srcs, picks, last, labels = conv_sources(variables, presteps, instructions + "\n".join(branches.values()), existing, fact)
    if unknown:
        notes.append("These steps are not part of the form and are left out when you push: %s." % ", ".join(sorted(set(unknown))[:12]))
    auto, snotes, all_ok = conv_schedule(sched_cfg, fact)
    notes += snotes
    publish = next((st for st, _ in flat if conv_action(st) == "mqtt.publish"), None)
    topic = str(((publish or {}).get("data") or {}).get("topic") or "")
    payload = str(((publish or {}).get("data") or {}).get("payload") or "")
    extra = ("The result is saved to a file with this payload template: %s\n" % payload[:600]) if publish else ""
    j, aerr = await conv_ai(app, target, instructions, branches, labels, extra)
    used_ai = j is not None
    if not used_ai:
        notes.append("The AI Task could not split the prompt (%s), so your prompt was kept as the instructions." % (aerr or "no answer"))
        j = {}
    name = str(name_from.get("alias") or cfg.get("alias") or j.get("name") or "Imported").strip()[:80]
    # the original, unwrapped, so "keep it exactly as written" pushes cleanly (an announcement can only keep a script)
    clean = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=1000)
    original = clean if (target == "fact" or kind == "script") else ""
    m = re.search(r"under (\d+) characters|(\d+) characters or less", instructions)
    length = int(j.get("length") or 0) or (int(m.group(1) or m.group(2)) if m else 0)
    task = str(j.get("task") or "").strip() or conv_strip_vars(instructions, labels)
    prefix = fact_settings().get("mqtt_prefix") or ""
    fpath = topic[len(prefix):] if prefix and topic.startswith(prefix) else topic
    if publish and prefix and not topic.startswith(prefix):
        notes.append("It published to %s, which is not under your file path setting (%s). Check the file name before you push." % (topic, prefix))
    if target == "announcement":
        flag = s.get("talking_flag") or ""
        outs, add_alexa, add_notify, vol, pause, card = [], [], [], None, False, {}
        for st, _ in flat:
            act = conv_action(st)
            d = st.get("data") if isinstance(st.get("data"), dict) else {}
            if act == "tts.speak":
                outs.append("tts")
                mp = conv_targets(st, "media_player_entity_id")
                if mp and s.get("speaker") and mp[0] != s.get("speaker"):
                    notes.append("It spoke on %s. The form uses your main speaker from Settings (%s)." % (mp[0], s.get("speaker")))
                if not s.get("speaker") and mp:
                    notes.append("Set %s as the main speaker in Settings." % mp[0])
            elif act == "notify.alexa_media":
                for t in conv_list(d.get("target")):
                    outs.append("a:" + str(t))
                    if str(t) not in (s.get("alexa_targets") or []):
                        add_alexa.append(str(t))
            elif act == "notify.send_message":
                for t in conv_targets(st):
                    outs.append("n:" + t)
                    if t not in (s.get("notify_targets") or []):
                        add_notify.append(t)
            elif act.startswith("notify.") and act != "notify.persistent_notification":
                outs.append("n:" + act)
                if act not in (s.get("notify_targets") or []):
                    add_notify.append(act)
            elif act == "media_player.volume_set" and isinstance(d.get("volume_level"), (int, float)):
                vol = float(d["volume_level"])
            elif act == "media_player.media_pause":
                pause = True
            elif act == "input_boolean.turn_on":
                e = (conv_targets(st) or [""])[0]
                if e and e != flag and not card:
                    card = {"cardSw": e, "cardWhen": "talk", "cardOff": False, "cardHold": 0}
            elif act == "input_boolean.turn_off" and card and card["cardSw"] in conv_targets(st):
                card["cardOff"] = True
        pers, use_pers, one = {}, False, ANN_PERSONA_DEFAULT
        style = str(j.get("style") or "").strip()
        known = {p["name"]: p["style"] for p in s["personalities"]}
        if branches:
            styles = j.get("styles") if isinstance(j.get("styles"), dict) else {}
            pers = {k: str(styles.get(k) or known.get(k) or "") for k in branches}
            use_pers = bool(s.get("personality_select"))
            if not use_pers:
                notes.append("It picks a personality from a dropdown. Set your Personality dropdown in Settings to use that.")
        elif not used_ai:  # the prompt itself still carries the voice
            pers = {ANN_PERSONA_DEFAULT: "Follow the voice and tone given in the task."}
        elif style:
            hit = next((n for n, v in known.items() if v.strip() == style), None)
            if hit:
                one = hit
            else:
                pers = {ANN_PERSONA_DEFAULT: style}
        fields = []
        for f in (j.get("fields") or [])[:12] if isinstance(j.get("fields"), list) else []:
            k = re.sub(r"[^a-z0-9_]+", "_", str((f or {}).get("key") or "").lower()).strip("_")[:40]
            if k and k not in ("notification",) and all(k != x["key"] for x in fields):
                fields.append({"key": k, "hint": str(f.get("hint") or "")[:200], "as": "title" if not fields else "text"})
        txt = None
        if publish:
            txt = {"on": True, "mode": "fields" if fields else "text", "fields": fields, "say": str(j.get("say") or ""),
                   "file": fpath, "sensor": "", "title": name, "emoji": "\U0001F4E2", "scroll": True, "cpl": 40, "height": 300}
        elif fields:
            notes.append("It asked the AI for JSON fields (%s). Turn on Save to a file to keep them for a card." % ", ".join(f["key"] for f in fields))
        state = {"name": name, "task": task, "outs": list(dict.fromkeys(outs)), "pause": pause, "usePers": use_pers, "one": one,
                 "pers": pers, "len": length or s.get("default_length") or 1000, "auto": auto, **card}
        if vol is not None:
            state["vol"] = vol
        if txt:
            state["txt"] = txt
        sid = script_id or ""
        replaces = auto_id if (kind == "automation" and auto["on"] and all_ok and auto_id != (sid + ANN_AUTO_SUFFIX)) else ""
        if kind == "automation" and not replaces and not script_id:
            notes.append("Your automation %s still runs its own steps. Turn it off in Home Assistant once the new one works, or it will run twice." % (auto_id or name))
        if replaces:
            state["replaces"] = replaces
            notes.append("When you push, your old automation %s is turned off (a copy is kept) so it does not run twice." % replaces)
        return web.json_response({"ok": True, "target": target, "id": sid, "name": name, "state": state, "sources": srcs,
                                  "settings_add": {"alexa_targets": list(dict.fromkeys(add_alexa)), "notify_targets": list(dict.fromkeys(add_notify))},
                                  "notes": notes, "used_ai": used_ai, "original": original, "kind": kind})
    # ---- fact
    style = j.get("style") if j.get("style") in ("plain", "titled", "list", "json") else ("json" if re.search(r"\bjson\b", instructions, re.I) else "plain")
    fields = []
    for f in (j.get("fields") or [])[:14] if isinstance(j.get("fields"), list) else []:
        k = re.sub(r"[^a-z0-9_]+", "_", str((f or {}).get("key") or "").lower()).strip("_")[:30]
        if k and all(k != x["key"] for x in fields):
            fields.append({"key": k, "hint": str(f.get("hint") or "")[:120], "type": f.get("type") if f.get("type") in ("text", "number", "yesno") else "text"})
    head = ""
    hm = re.match(r"^(.*?)\n*\{\{", payload, re.S)
    if hm and hm.group(1).strip() and style != "json":
        head = hm.group(1).strip()
    ai_ent = str(aid_.get("entity_id") or "")
    state = {"name": name, "task": task, "picks": picks, "seed": "seed" in variables, "style": style,
             "titleHint": str(j.get("title_hint") or ""), "heading": head, "len": length or 180,
             "count": int(j.get("count") or 0) or (10 if style == "json" else 5), "file": fpath,
             "swear": j.get("swear") if j.get("swear") in ("none", "mild", "rated") else "none",
             "real": bool(j.get("real", True)), "obscure": bool(j.get("obscure", False)), "skip": str(j.get("skip") or ""),
             "noPeople": bool(j.get("no_people", False)), "avoidLast": bool(last) or bool(j.get("avoid_last")),
             "lastEntity": (last or {}).get("entity", ""), "lastAttr": (last or {}).get("attr", ""),
             "extra": str(j.get("extra") or ""), "ai": ai_ent if ai_ent and ai_ent != s.get("ai_task_entity") else "",
             "auto": auto, "asAuto": True, "autoOnly": False, "raw": None, "autoRaw": "",
             "listKey": re.sub(r"[^a-z0-9_]+", "_", str(j.get("list_key") or "items").lower()).strip("_") or "items",
             "fields": fields, "sortBy": str(j.get("sort_by") or ""), "sortDir": "asc" if j.get("sort_dir") == "asc" else "desc",
             "keepIf": str(j.get("keep_if") or ""), "useDate": bool(j.get("uses_date"))}
    if not publish:
        notes.append("It does not save to a file over MQTT. The fact will publish to the file under Where it goes.")
    if kind == "automation" and not all_ok:
        notes.append("Some of its triggers or conditions don't fit the form (see above). Check When it runs before you push.")
    if kind == "script" or script_id:
        notes.append("Your script.%s stays in Home Assistant. Delete it once the new fact works." % script_id if script_id else "")
    return web.json_response({"ok": True, "target": target, "id": auto_id or script_id or "", "name": name, "state": state,
                              "sources": srcs, "settings_add": {}, "notes": [n for n in notes if n], "used_ai": used_ai, "original": original, "kind": kind})


TYPE_LABELS = {"weather": "Weather", "calendar": "Calendar", "todo": "To-do list"}


# ---------------------------------------------------------------- backup / import
# Saves this add-on's own data (template sensors it manages, "Made so far" history, announcement settings)
# to the folder (or single .json file) given in the backup_path option, and imports it back.
def backup_is_file():
    return BACKUP_PATH.lower().endswith(".json")


def backup_folder():
    return Path(BACKUP_PATH).parent if backup_is_file() else Path(BACKUP_PATH)


def collect_backup():
    return {"kind": "ai_builder_backup", "format": 1, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "data": {"templates": load_json(STORE, {}), "history": load_json(HIST, []),
                     "announcement_settings": load_json(ANN_SETTINGS, {}),
                     "announcements": ann_library(),
                     "fact_settings": load_json(FACT_SETTINGS, {}),
                     "facts": fact_library(),
                     "cards": cards_library()}}


def backup_cards(text):
    """The saved dashboard cards in a backup, or None for backups made before cards existed (an import then leaves yours alone)."""
    try:
        c = json.loads(text)["data"].get("cards")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not isinstance(c, dict):
        return None
    c = {k: v for k, v in c.items() if CARD_ID_RE.match(str(k)) and isinstance(v, dict) and isinstance(v.get("state"), dict)}
    for k, v in c.items():
        v["id"] = k
    return c


def parse_backup(text):
    """Validate a backup file and return (templates, history, announcement_settings, announcements, fact_settings, facts).
    Raises ValueError. announcements and facts are None for backups made before they existed, so an import leaves yours alone."""
    try:
        d = json.loads(text)
    except ValueError:
        raise ValueError("That file is not valid JSON.")
    if not isinstance(d, dict) or d.get("kind") != "ai_builder_backup" or not isinstance(d.get("data"), dict):
        raise ValueError("That file is not a Creator & AI Builder backup.")
    data = d["data"]
    templates = data.get("templates", {})
    if not isinstance(templates, dict):
        raise ValueError("The backup's template list is damaged.")
    for k, e in templates.items():
        if not (isinstance(e, dict) and all(isinstance(e.get(f), str) and e.get(f) for f in ("name", "unique_id", "state"))
                and e.get("platform") in ("sensor", "binary_sensor")
                and isinstance(e.get("attributes", {}) or {}, dict)):
            raise ValueError("The backup has a damaged template entry (%s)." % str(k)[:60])
    history = data.get("history", [])
    if not isinstance(history, list):
        raise ValueError("The backup's history is damaged.")
    history = [h for h in history if isinstance(h, dict)][:40]
    ann = data.get("announcement_settings", {})
    if not isinstance(ann, dict):
        raise ValueError("The backup's announcement settings are damaged.")
    ann = {k: v for k, v in ann.items() if k in ANN_DEFAULTS and k != "helper_ai_task_entity"}
    lib = data.get("announcements")
    if lib is not None:
        if not isinstance(lib, dict):
            raise ValueError("The backup's saved announcements are damaged.")
        lib = {k: v for k, v in lib.items() if ANN_ID_RE.match(str(k)) and isinstance(v, dict) and isinstance(v.get("state"), dict)}
        for k, v in lib.items():
            v["id"] = k
    fset = data.get("fact_settings")
    if fset is not None:
        if not isinstance(fset, dict):
            raise ValueError("The backup's fact settings are damaged.")
        fset = fact_clean_settings(fset)
    facts = data.get("facts")
    if facts is not None:
        if not isinstance(facts, dict):
            raise ValueError("The backup's saved facts are damaged.")
        facts = {k: v for k, v in facts.items() if ANN_ID_RE.match(str(k)) and isinstance(v, dict) and isinstance(v.get("state"), dict)}
        for k, v in facts.items():
            v["id"] = k
    return templates, history, ann, lib, fset, facts


def backup_candidates():
    folder = backup_folder()
    if not folder.is_dir():
        return []
    if backup_is_file():
        files = list(folder.glob(BACKUP_PREFIX + "_*.json"))
        if Path(BACKUP_PATH).is_file():
            files.append(Path(BACKUP_PATH))
    else:
        files = list(folder.glob("*.json"))
    return sorted({f for f in files if f.is_file()}, key=lambda f: f.stat().st_mtime, reverse=True)


def peek_backup(p):
    try:
        st = p.stat()
        if st.st_size > 32 * 1024 * 1024:
            return None
        raw = p.read_text(encoding="utf-8")
        templates, history, ann, lib, fset, facts = parse_backup(raw)
        cards = backup_cards(raw)
    except (OSError, ValueError):
        return None
    return {"file": p.name, "size": st.st_size, "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
            "templates": len(templates), "history": len(history), "announcements": bool(ann),
            "announcements_count": len(lib or {}), "facts_count": len(facts or {}), "cards_count": len(cards or {})}


def write_backup(tag=""):
    """Write a backup and return its path. tag="_pre-import" is the safety copy made before an import."""
    folder = backup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    fixed = Path(BACKUP_PATH) if backup_is_file() else None
    if fixed and not tag:
        dest = fixed
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = folder / f"{BACKUP_PREFIX}{tag}_{stamp}.json"
        n = 1
        while dest.exists():
            dest = folder / f"{BACKUP_PREFIX}{tag}_{stamp}-{n}.json"
            n += 1
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(json.dumps(collect_backup(), indent=2), encoding="utf-8")
    os.replace(tmp, dest)  # a half-written backup never replaces a good one
    olds = sorted((f for f in folder.glob(BACKUP_PREFIX + "_*.json") if f != fixed),
                  key=lambda f: f.stat().st_mtime, reverse=True)
    for f in olds[BACKUP_KEEP:]:
        try:
            f.unlink()
        except OSError:
            pass
    return dest


async def backup_info(request):
    files = [p for p in (peek_backup(f) for f in backup_candidates()) if p]
    return web.json_response({
        "path": BACKUP_PATH, "mode": "file" if backup_is_file() else "folder", "keep": BACKUP_KEEP,
        "files": files,
        "current": {"templates": len(load_json(STORE, {})), "history": len(load_json(HIST, [])), "announcements": len(ann_library()),
                    "facts": len(fact_library()), "cards": len(cards_library())},
    })


async def backup_save(request):
    try:
        dest = write_backup()
    except OSError as e:
        log.error("Backup failed: %s", e)
        return web.json_response({"ok": False, "error": "Could not write to %s (%s). Check the backup_path option." % (BACKUP_PATH, e)})
    log.info("Backup saved to %s", dest)
    return web.json_response({"ok": True, "file": dest.name, "path": str(dest)})


async def backup_import(request):
    app = request.app
    body = await ann_body(request)
    name = str(body.get("file") or "")
    if not name or name != os.path.basename(name) or not name.lower().endswith(".json"):
        return web.json_response({"ok": False, "error": "Pick a backup file from the list."})
    path = backup_folder() / name
    if not path.is_file():
        return web.json_response({"ok": False, "error": "%s was not found in %s." % (name, backup_folder())})
    try:
        raw = path.read_text(encoding="utf-8")
        templates, history, ann, lib, fset, facts = parse_backup(raw)
        cards = backup_cards(raw)
    except (OSError, ValueError) as e:
        return web.json_response({"ok": False, "error": str(e)})
    try:
        safety = write_backup("_pre-import")  # so an import can always be undone
    except OSError as e:
        return web.json_response({"ok": False, "error": "Could not save a safety copy first, so nothing was changed (%s)." % e})
    save_json(STORE, templates)
    save_json(HIST, history)
    save_json(ANN_SETTINGS, ann)
    if lib is not None:
        save_json(ANN_LIB, lib)
    if fset is not None:
        save_json(FACT_SETTINGS, fset)
    if facts is not None:
        save_json(FACTS_LIB, facts)
    if cards is not None:
        save_json(CARDS_LIB, cards)
    note = ""
    try:
        render_package(templates)
        await ha(app, "POST", "/services/template/reload", {})
    except Exception as e:
        log.warning("Import: could not rewrite the template file: %s", e)
        note = "Data restored, but the template file could not be rewritten (%s)." % e
    log.info("Imported backup %s (safety copy %s)", path, safety)
    return web.json_response({"ok": True, "file": name, "safety": safety.name, "note": note,
                              "templates": len(templates), "history": len(history), "announcements": bool(ann),
                              "announcements_count": len(lib if lib is not None else ann_library()),
                              "facts_count": len(facts if facts is not None else fact_library()),
                              "cards_count": len(cards if cards is not None else cards_library())})


def listen_stdin(on_backup, log_info, log_error):
    """Home Assistant's hassio.addon_stdin action writes to this add-on's stdin (stdin: true in config.yaml).
    Sending "backup" makes a backup now, so one script can back up every add-on at once."""
    def run():
        try:
            fd = sys.stdin.fileno()
            if os.isatty(fd):
                return
        except (OSError, ValueError, AttributeError):
            return
        tail = b""
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                return
            if not chunk:
                return  # nothing attached
            tail = (tail + chunk)[-64:]
            if b"backup" in tail.lower():
                tail = b""
                try:
                    log_info("Backup asked for by Home Assistant (hassio.addon_stdin): %s" % on_backup())
                except Exception as e:  # noqa: BLE001
                    log_error("That backup failed: %s" % e)
    threading.Thread(target=run, daemon=True).start()


import dashboards  # noqa: E402
import files_hub  # noqa: E402

FILES = files_hub.Files(OPTS, ask_ai)
DASH = dashboards.Dashboards(DATA, ws_call, ask_ai, ha, extract_json)


async def on_startup(app):
    listen_stdin(write_backup, log.info, log.error)
    app["http"] = aiohttp.ClientSession()
    try:
        if not FILES.list() and FILES._old_backup():  # first start after File Reader moved in here
            log.info("Files: %s", FILES.import_old()[1])
    except Exception as e:  # noqa: BLE001
        log.warning("Files: couldn't copy files from the old File Reader backup: %s", e)
    FILES.start()
    app["files_api"] = await FILES.start_api()
    app["resolver"] = asyncio.create_task(resolve_entity(app))
    app["name_sync"] = asyncio.create_task(name_sync_loop(app))
    render_package(load_json(STORE, {}))
    log.info("Creator & AI Builder ready - using %s, template file /config/%s, AppDaemon dir %s, backups %s", ENTITY, TEMPLATE_REL, AD_DIR, BACKUP_PATH)


async def on_cleanup(app):
    if app.get("name_sync"):
        app["name_sync"].cancel()
    if app.get("files_api"):
        await app["files_api"].cleanup()
    await app["http"].close()


def main():
    app = web.Application(client_max_size=4 * 1024 * 1024, middlewares=[ingress_only])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.add_routes([
        web.get("/", page("index.html")),
        web.get("/builder", page("builder.html")),
        web.get("/announcements", page("announcements.html")),
        web.get("/facts", page("facts.html")),
        web.get("/cards", page("cards.html")),
        web.get("/backup", page("backup.html")),
        web.get("/files", page("files.html")),
        web.get("/dashboards", page("dashboards.html")),
        web.get("/ui.css", asset("ui.css", "text/css")),
        web.get("/ui.js", asset("ui.js", "application/javascript")),
        web.get("/announcements.js", asset("announcements.js", "application/javascript")),
        web.get("/ann-file.js", asset("ann-file.js", "application/javascript")),
        web.get("/sources.js", asset("sources.js", "application/javascript")),
        web.get("/facts.js", asset("facts.js", "application/javascript")),
        web.get("/cards.js", asset("cards.js", "application/javascript")),
        web.get("/autoform.js", asset("autoform.js", "application/javascript")),
        web.get("/schedule.js", asset("schedule.js", "application/javascript")),
        web.get("/js-yaml.min.js", asset("js-yaml.min.js", "application/javascript")),
        *FILES.routes(),
        *DASH.routes(),
        web.get("/api/status", status),
        web.get("/api/match_default", match_default),
        web.get("/api/targets", targets),
        web.get("/api/mine", mine),
        web.get("/api/made", made_route),
        web.post("/api/rename", rename_route),
        web.post("/api/convert", convert_route),
        web.post("/api/generate", generate),
        web.post("/api/create", create),
        web.post("/api/delete_template", delete_template),
        # announcement maker
        web.get("/api/ann/options", ann_options),
        web.get("/api/ann/entities", ann_entities),
        web.get("/api/ann/test", ann_test_status),
        web.get("/api/ann/library", ann_library_list),
        web.get("/api/ann/script", ann_script_get),
        web.post("/api/ann/import", ann_import),
        web.post("/api/ann/library/save", ann_library_save),
        web.post("/api/ann/library/delete", ann_library_delete),
        web.post("/api/ann/settings", ann_save_settings),
        web.post("/api/ann/personality_dropdown", ann_dropdown_sync),
        web.post("/api/ann/test", ann_test_start),
        web.post("/api/ann/helper", ann_helper),
        web.post("/api/ann/push", ann_push),
        web.post("/api/ann/run", ann_run),
        web.post("/api/ann/card_switch", ann_card_switch),
        # facts
        web.get("/api/facts/options", fact_options),
        web.get("/api/facts/test", fact_test_status),
        web.get("/api/facts/library", fact_library_list),
        web.get("/api/facts/automations", fact_automations),
        web.get("/api/facts/automation", fact_automation_get),
        web.post("/api/facts/import_auto", fact_import_auto),
        web.post("/api/facts/library/save", fact_library_save),
        web.post("/api/facts/library/delete", fact_library_delete),
        web.post("/api/facts/settings", fact_save_settings),
        web.post("/api/facts/test", fact_test_start),
        web.post("/api/facts/helper", fact_helper),
        web.post("/api/facts/push", fact_push),
        web.post("/api/facts/run", fact_run),
        # dashboard cards
        web.get("/api/cards/library", cards_library_list),
        web.post("/api/cards/library/save", cards_library_save),
        web.post("/api/cards/library/delete", cards_library_delete),
        web.post("/api/cards/generate", cards_generate),
        web.post("/api/cards/check", cards_check_route),
        web.post("/api/cards/preview", cards_preview),
        # backup / import
        web.get("/api/backup", backup_info),
        web.post("/api/backup/save", backup_save),
        web.post("/api/backup/import", backup_import),
    ])
    web.run_app(app, host="0.0.0.0", port=8099, access_log=None)


if __name__ == "__main__":
    main()

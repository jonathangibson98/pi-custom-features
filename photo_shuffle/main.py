import collections
import io
import json
import logging
import os
import random
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt
import requests
from flask import Flask, Response, jsonify, request
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import addon_backup

DATA_DIR = os.environ.get("PS_DATA_DIR", "/data")
# created before anything is read, so a queued restore is unpacked first (thumbnails are rebuilt, so they're left out)
BACKUP = addon_backup.Backup("photo_shuffle", "Photo Hub", "4.1.0",
                             [("data", DATA_DIR, "replace", ["unsplash_thumbs"])], data_dir=DATA_DIR)
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- logging
class UILog(logging.Handler):
    """Keeps recent log lines so the web UI can show what the add-on is doing."""

    def __init__(self):
        super().__init__()
        self.buf = collections.deque(maxlen=300)

    def emit(self, record):
        self.buf.append({"t": int(record.created), "l": record.levelname, "m": record.getMessage()})


UI_LOG = UILog()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger().addHandler(UI_LOG)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
log = logging.getLogger("photo_hub")

# ---------------------------------------------------------------- options
OPTIONS = json.load(open(os.path.join(DATA_DIR, "options.json")))
MAX_DIM = int(OPTIONS.get("max_dimension", 1920))
QUALITY = int(OPTIONS.get("jpeg_quality", 85))

FORMAT_EXT = {
    "jpg": (".jpg", ".jpeg"),
    "png": (".png",),
    "webp": (".webp",),
    "gif": (".gif",),
    "bmp": (".bmp",),
    "tiff": (".tif", ".tiff"),
}
FORMATS = [f for f in (OPTIONS.get("formats") or []) if f in FORMAT_EXT]
if not FORMATS:
    FORMATS = ["jpg", "png", "webp"]
    log.warning("No picture formats selected, using jpg, png and webp")
EXTS = {e for f in FORMATS for e in FORMAT_EXT[f]}

ROOTS = []
for _p in OPTIONS.get("photo_paths") or []:
    _p = os.path.normpath(str(_p).strip())
    if _p.startswith("/") and _p not in ROOTS:
        ROOTS.append(_p)

# Photo Editor: where edited pictures are saved. It joins the photo paths so edits show up everywhere.
EDIT_DIR = os.path.normpath(str(OPTIONS.get("edit_output_path") or "/media/photo_hub/edited").strip())
try:
    os.makedirs(EDIT_DIR, exist_ok=True)
except OSError as _e:
    log.warning("Can't create the Photo Editor folder %s: %s", EDIT_DIR, _e)
if os.path.isdir(EDIT_DIR) and EDIT_DIR not in ROOTS:
    ROOTS.append(EDIT_DIR)

UNSPLASH_KEY = str(OPTIONS.get("unsplash_access_key") or "").strip()
try:
    UNSPLASH_MIN = max(5, min(1440, int(OPTIONS.get("unsplash_interval_minutes") or 60)))
except (TypeError, ValueError):
    UNSPLASH_MIN = 60
UNSPLASH_SIZE = OPTIONS.get("unsplash_image_size")
if UNSPLASH_SIZE not in ("full", "regular", "small"):
    UNSPLASH_SIZE = "regular"

DISCOVERY = "homeassistant"
BASE = "photo_shuffle"  # kept from the old Photo Shuffle add-on so existing entities carry over
STATUS_TOPIC = f"{BASE}/status"

# One shared Home Assistant device that holds every folder shuffle's image entity
DEVICE = {
    "identifiers": [BASE],
    "name": "Photo Shuffle",
    "manufacturer": "Photo Hub add-on",
    "model": "Folder shuffle",
}
STORE = os.path.join(DATA_DIR, "shuffles.json")
DEVICE_REV = 2  # 2 = every shuffle lives on the shared "Photo Shuffle" device

# Unsplash collections get their own shared device and topic space
UBASE = "photo_hub_unsplash"
UDEVICE = {
    "identifiers": [UBASE],
    "name": "Unsplash Photos",
    "manufacturer": "Photo Hub add-on",
    "model": "Unsplash collection",
}
UNSPLASH_API = "https://api.unsplash.com"
ORIENTATIONS = ("landscape", "portrait", "both")
USTORE = os.path.join(DATA_DIR, "unsplash.json")  # collections + which entities were announced
USTATE = os.path.join(DATA_DIR, "unsplash_state.json")  # last photo info + last full cycle time
THUMB_DIR = os.path.join(DATA_DIR, "unsplash_thumbs")
UKEY_RE = re.compile(r"^[a-z0-9_]+_(landscape|portrait)$")

stop = threading.Event()
CONNECTED = threading.Event()
REFRESH = threading.Event()  # set when the broker settings probably changed and must be fetched again
mq_state = {"status": "starting", "detail": ""}

ERR_MQTT = "MQTT is not connected"
MQTT_DOWN_LIMIT = 60  # seconds without a connection before the MQTT client is rebuilt from scratch
MQTT_BEAT_EVERY = 60  # seconds between connection health checks


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "shuffle"


def in_roots(path):
    rp = os.path.realpath(path)
    for r in ROOTS:
        rr = os.path.realpath(r)
        if rp == rr or rp.startswith(rr + os.sep):
            return True
    return False


def is_image(name):
    return not name.startswith(".") and os.path.splitext(name)[1].lower() in EXTS


def render(src):
    """src is a path or a file object. Return (full-size jpeg bytes, small preview jpeg bytes)."""
    with Image.open(src) as im:
        if im.format == "JPEG":
            im.draft("RGB", (MAX_DIM, MAX_DIM))
        if getattr(im, "is_animated", False):
            im.seek(0)
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY, optimize=True)
        th = im.copy()
        th.thumbnail((480, 480), Image.Resampling.LANCZOS)
        tb = io.BytesIO()
        th.save(tb, "JPEG", quality=70)
        return buf.getvalue(), tb.getvalue()


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- folder shuffle
class Shuffle:
    def __init__(self, sid, cfg):
        self.id = sid
        self.name = cfg["name"]
        self.path = cfg["path"]
        self.interval = int(cfg["interval"])
        self.recursive = bool(cfg["recursive"])
        self.enabled = bool(cfg["enabled"])
        self.lock = threading.Lock()
        self.deck = []
        self.last = None
        self.current = None
        self.thumb = None
        self.last_full = None
        self.changed_at = None
        self.next_at = None
        self.count = None
        self.error = None
        self.trigger = threading.Event()
        self.stop_ev = threading.Event()
        self.thread = None
        self.image_topic = f"{BASE}/{sid}/image"
        self.seq = 0
        self.cond = threading.Condition()

    def cfg(self):
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "interval": self.interval,
            "recursive": self.recursive,
            "enabled": self.enabled,
        }

    def view(self):
        d = self.cfg()
        d.update(
            count=self.count,
            current=self.current,
            changed_at=self.changed_at,
            next_at=self.next_at,
            error=self.error,
            has_image=self.thumb is not None,
        )
        return d

    def scan(self):
        files = []
        if not os.path.isdir(self.path):
            self.error = "Folder not found"
            self.count = 0
            return files
        if not in_roots(self.path):
            self.error = "Folder is outside the allowed photo paths"
            self.count = 0
            return files
        if self.recursive:
            for root, dirs, names in os.walk(self.path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files.extend(os.path.join(root, n) for n in names if is_image(n))
        else:
            with os.scandir(self.path) as it:
                files = [e.path for e in it if e.is_file() and is_image(e.name)]
        self.count = len(files)
        if not files:
            self.error = "No pictures found (formats: %s)" % ", ".join(FORMATS)
        return files

    def reset_deck(self):
        with self.lock:
            self.deck = []

    def pick(self):
        with self.lock:
            if not self.deck:
                self.deck = self.scan()
                random.shuffle(self.deck)
                if len(self.deck) > 1 and self.deck[-1] == self.last:
                    self.deck.insert(0, self.deck.pop())
            if not self.deck:
                return None
            self.last = self.deck.pop()
            return self.last

    def publish_next(self):
        for _ in range(5):
            path = self.pick()
            if not path:
                if self.error and self.error != getattr(self, "_logged_error", None):
                    log.warning("%s: %s (%s)", self.name, self.error, self.path)
                    self._logged_error = self.error
                return False
            try:
                full, thumb = render(path)
            except Exception as e:
                log.warning("%s: skipping %s (%s)", self.name, path, e)
                continue
            if not mgr.publish(self.image_topic, full):
                self.error = ERR_MQTT
                return False
            self.thumb = thumb
            self.last_full = full
            wall.offer("shuffle", self.id, full, self.name)
            self.changed_at = time.time()
            self.error = None
            self._logged_error = None
            try:
                self.current = os.path.relpath(path, self.path)
            except ValueError:
                self.current = os.path.basename(path)
            log.info("%s: now showing %s", self.name, self.current)
            return True
        self.error = "Could not read any of the pictures"
        return False

    def request_next(self, wait=15):
        """Pick a new photo right now. Returns once it has been published (or failed)."""
        with self.cond:
            before = self.seq
        self.trigger.set()
        with self.cond:
            self.cond.wait_for(lambda: self.seq != before, timeout=wait)

    def loop(self):
        while not self.stop_ev.is_set():
            forced = self.trigger.is_set()
            self.trigger.clear()
            if not CONNECTED.is_set():
                self.next_at = None
                CONNECTED.wait(3)
                # a Next press while MQTT was down must not hang the UI
                with self.cond:
                    self.seq += 1
                    self.cond.notify_all()
                continue
            retry = False
            if self.enabled or forced:
                try:
                    self.publish_next()
                except Exception:
                    log.exception("%s: unexpected error", self.name)
                # the connection dropped right as the photo was sent: try again soon, not after a full interval
                retry = self.error == ERR_MQTT
                with self.cond:
                    self.seq += 1
                    self.cond.notify_all()
            if self.stop_ev.is_set():
                break
            if self.enabled:
                wait = min(self.interval, 10) if retry else self.interval
                self.next_at = time.time() + wait
                self.trigger.wait(wait)
            else:
                self.next_at = None
                self.trigger.wait(3600)

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def halt(self):
        self.stop_ev.set()
        self.trigger.set()

    def discovery(self, client):
        image_cfg = {
            "name": self.name,
            "unique_id": f"{BASE}_{self.id}_image",
            "default_entity_id": f"image.{self.id}",
            "image_topic": self.image_topic,
            "content_type": "image/jpeg",
            "availability_topic": STATUS_TOPIC,
            "device": DEVICE,
        }
        client.publish(f"{DISCOVERY}/image/{BASE}_{self.id}/config", json.dumps(image_cfg), qos=1, retain=True)


# ---------------------------------------------------------------- shuffle manager
class Manager:
    def __init__(self):
        self.lock = threading.RLock()
        self.shuffles = {}
        self.removed = []
        self.device_rev = DEVICE_REV
        self.client = None

    # persistence
    def load(self):
        data = None
        try:
            with open(STORE) as f:
                data = json.load(f)
        except FileNotFoundError:
            legacy = OPTIONS.get("shuffles")
            if legacy:
                log.info("Importing %d shuffle(s) from the old configuration", len(legacy))
                data = {"shuffles": []}
                for item in legacy:
                    data["shuffles"].append(
                        {
                            "id": slugify(item["name"]),
                            "name": item["name"],
                            "path": item["path"],
                            "interval": item.get("interval", 60),
                            "recursive": item.get("recursive", True),
                            "enabled": True,
                        }
                    )
        except Exception as e:
            log.error("Could not read %s: %s", STORE, e)
        data = data or {}
        for c in data.get("shuffles", []):
            try:
                self.shuffles[c["id"]] = Shuffle(c["id"], c)
            except Exception as e:
                log.warning("Skipping bad shuffle entry: %s", e)
        self.removed = list(data.get("removed", []))
        # stores written before the shared device existed have no device_rev and need a one-time move
        self.device_rev = data.get("device_rev", 0 if self.shuffles else DEVICE_REV)
        self.save()

    def save(self):
        with self.lock:
            write_json(
                STORE,
                {"shuffles": [s.cfg() for s in self.shuffles.values()], "removed": self.removed, "device_rev": self.device_rev},
            )

    def all(self):
        with self.lock:
            return list(self.shuffles.values())

    def get(self, sid):
        with self.lock:
            return self.shuffles.get(sid)

    # mqtt helpers (shared with the Unsplash side)
    def publish(self, topic, payload, retain=True):
        """Send a message. Returns True only if it was really handed to a live connection."""
        client = self.client
        if client is None or not CONNECTED.is_set() or not client.is_connected():
            return False
        try:
            info = client.publish(topic, payload, qos=1, retain=retain)
        except Exception as e:
            log.warning("MQTT publish to %s failed: %s", topic, e)
            return False
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("MQTT publish to %s failed (code %s)", topic, info.rc)
            return False
        return True

    def purge_removed(self):
        if self.client is None or not CONNECTED.is_set():
            return
        with self.lock:
            for sid in self.removed:
                if sid in self.shuffles:
                    continue
                self.client.publish(f"{DISCOVERY}/image/{BASE}_{sid}/config", "", qos=1, retain=True)
                self.client.publish(f"{DISCOVERY}/button/{BASE}_{sid}_next/config", "", qos=1, retain=True)
                self.client.publish(f"{BASE}/{sid}/image", "", qos=1, retain=True)
                log.info("Removed Home Assistant entities for '%s'", sid)
            self.removed = []
            self.save()

    def announce(self, s):
        if self.client is not None and CONNECTED.is_set():
            s.discovery(self.client)

    # operations
    def validate(self, data, current=None):
        name = str(data.get("name", "")).strip()[:40]
        if not name:
            raise ValueError("Give the shuffle a name")
        for s in self.all():
            if s.name.lower() == name.lower() and (current is None or s.id != current.id):
                raise ValueError("A shuffle called '%s' already exists" % name)
        path = str(data.get("path", "")).strip()
        if not path.startswith("/"):
            raise ValueError("Choose a folder")
        path = os.path.normpath(path)
        if not ROOTS:
            raise ValueError("No photo paths are set. Add some in the add-on Configuration tab")
        if not in_roots(path):
            raise ValueError("Folder must be inside an allowed photo path: " + ", ".join(ROOTS))
        if not os.path.isdir(path):
            raise ValueError("That folder does not exist")
        try:
            interval = int(data.get("interval", 60))
        except (TypeError, ValueError):
            raise ValueError("Interval must be a number of seconds")
        if not 5 <= interval <= 86400:
            raise ValueError("Interval must be between 5 seconds and 24 hours")
        return {
            "name": name,
            "path": path,
            "interval": interval,
            "recursive": bool(data.get("recursive", True)),
            "enabled": bool(data.get("enabled", True)),
        }

    def add(self, data):
        cfg = self.validate(data)
        with self.lock:
            base = slugify(cfg["name"])
            sid, n = base, 2
            while sid in self.shuffles:
                sid, n = f"{base}_{n}", n + 1
            s = Shuffle(sid, cfg)
            self.shuffles[sid] = s
            if sid in self.removed:
                self.removed.remove(sid)
            self.save()
        self.announce(s)
        s.start()
        log.info("Added shuffle '%s' (%s)", s.name, s.path)
        return s

    def update(self, sid, data):
        s = self.get(sid)
        if s is None:
            raise KeyError(sid)
        cfg = self.validate({**s.cfg(), **data}, current=s)
        with self.lock:
            reset = (cfg["path"], cfg["recursive"]) != (s.path, s.recursive)
            renamed = cfg["name"] != s.name
            s.name, s.path = cfg["name"], cfg["path"]
            s.interval, s.recursive, s.enabled = cfg["interval"], cfg["recursive"], cfg["enabled"]
            self.save()
        if reset:
            s.reset_deck()
        if renamed:
            self.announce(s)
        if s.enabled or reset:
            s.trigger.set()
        log.info("Updated shuffle '%s'", s.name)
        return s

    def delete(self, sid):
        with self.lock:
            s = self.shuffles.pop(sid, None)
            if s is None:
                raise KeyError(sid)
            s.halt()
            if sid not in self.removed:
                self.removed.append(sid)
            self.save()
        log.info("Deleted shuffle '%s'", s.name)
        self.purge_removed()


mgr = Manager()


# ---------------------------------------------------------------- unsplash collections
class Unsplash:
    """Random Unsplash photos per collection. Every photo is published straight to MQTT as an
    image entity (no custom integration, no files in /share)."""

    def __init__(self):
        self.newest_photo = {}  # newest full-size photo per entity, for the add-on wallpaper
        self.lock = threading.RLock()
        self.collections = []  # [{id, name, search_terms, orientation}]
        self.published = []  # entity keys announced to Home Assistant (so stale ones can be removed)
        self.meta = {}  # entity key -> info about the latest photo
        self.errors = {}
        self.last_full = 0.0
        self.next_full = time.time() + 10
        self.pending = set()
        self.busy = False
        self.wake = threading.Event()
        self.warned_no_key = False

    # persistence
    def load(self):
        os.makedirs(THUMB_DIR, exist_ok=True)
        try:
            with open(USTORE) as f:
                data = json.load(f)
            self.collections = [c for c in data.get("collections", []) if isinstance(c, dict) and c.get("id")]
            self.published = list(data.get("published", []))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.error("Could not read %s: %s", USTORE, e)
        try:
            with open(USTATE) as f:
                data = json.load(f)
            self.meta = dict(data.get("meta", {}))
            self.last_full = float(data.get("last_full", 0))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.error("Could not read %s: %s", USTATE, e)
        # do not spend Unsplash requests on every restart: wait out the rest of the interval
        self.next_full = max(time.time() + 10, self.last_full + UNSPLASH_MIN * 60)
        # entities that never got a photo get one right away
        self.pending = {j["key"] for j in self.jobs() if not os.path.exists(self.thumb_path(j["key"]))}
        self.save()

    def save(self):
        with self.lock:
            write_json(USTORE, {"collections": self.collections, "published": self.published})

    def save_state(self):
        with self.lock:
            write_json(USTATE, {"meta": self.meta, "last_full": self.last_full})

    # helpers
    @staticmethod
    def thumb_path(key):
        return os.path.join(THUMB_DIR, key + ".jpg")

    @staticmethod
    def orients(c):
        return ["landscape", "portrait"] if c["orientation"] == "both" else [c["orientation"]]

    def jobs(self):
        """One job per collection and orientation. 'both' becomes two jobs."""
        with self.lock:
            out = []
            for c in self.collections:
                for o in self.orients(c):
                    out.append(
                        {
                            "key": f"{c['id']}_{o}",
                            "id": c["id"],
                            "name": c["name"],
                            "orientation": o,
                            "terms": list(c["search_terms"]),
                            "label": f"{c['name']} ({o})",
                        }
                    )
            return out

    @staticmethod
    def topics(key):
        return f"{UBASE}/{key}/image", f"{UBASE}/{key}/attributes"

    def get(self, cid):
        with self.lock:
            for c in self.collections:
                if c["id"] == cid:
                    return c
        return None

    # home assistant discovery
    def announce_job(self, client, j):
        image_topic, attr_topic = self.topics(j["key"])
        cfg = {
            "name": f"{j['name']} Photos {j['orientation'].title()}",
            "unique_id": f"{UBASE}_{j['key']}_image",
            "default_entity_id": f"image.{j['id']}_photos_{j['orientation']}",
            "image_topic": image_topic,
            "content_type": "image/jpeg",
            "json_attributes_topic": attr_topic,
            "availability_topic": STATUS_TOPIC,
            "device": UDEVICE,
        }
        client.publish(f"{DISCOVERY}/image/{UBASE}_{j['key']}/config", json.dumps(cfg), qos=1, retain=True)

    def sync_discovery(self, client):
        """Announce every current entity and remove the ones that no longer exist."""
        with self.lock:
            jobs = self.jobs()
            keys = [j["key"] for j in jobs]
            for j in jobs:
                self.announce_job(client, j)
            for key in self.published:
                if key in keys:
                    continue
                image_topic, attr_topic = self.topics(key)
                client.publish(f"{DISCOVERY}/image/{UBASE}_{key}/config", "", qos=1, retain=True)
                client.publish(image_topic, "", qos=1, retain=True)
                client.publish(attr_topic, "", qos=1, retain=True)
                log.info("Removed Home Assistant entity for '%s'", key)
            if self.published != keys:
                self.published = keys
                self.save()

    def sync_if_connected(self):
        if mgr.client is not None and CONNECTED.is_set():
            self.sync_discovery(mgr.client)

    # fetching
    def fetch(self, j):
        """Get one random photo for a job and publish it. Returns None on success or an error message."""
        if not CONNECTED.is_set():
            return ERR_MQTT  # do not burn an Unsplash request on a photo that cannot be delivered
        headers = {"Authorization": f"Client-ID {UNSPLASH_KEY}"}
        term = random.choice(j["terms"])
        log.info("%s: fetching '%s' from Unsplash", j["label"], term)
        resp = requests.get(
            f"{UNSPLASH_API}/photos/random",
            headers=headers,
            params={"query": term, "orientation": j["orientation"]},
            timeout=15,
        )
        if resp.status_code == 401:
            return "Unsplash says the Access Key is bad (401). Check the add-on Configuration tab."
        if resp.status_code == 403:
            return "Unsplash rate limit hit (403). Raise the interval or cut collections."
        if resp.status_code == 404:
            return "Unsplash found no photos for '%s'" % term
        if resp.status_code != 200:
            return "Unsplash error %s" % resp.status_code
        data = resp.json()
        img = requests.get(data["urls"][UNSPLASH_SIZE], timeout=60)
        if img.status_code != 200:
            return "Download failed (%s)" % img.status_code
        full, thumb = render(io.BytesIO(img.content))

        meta = {
            "search_term": term,
            "photographer": (data.get("user") or {}).get("name"),
            "photo_url": (data.get("links") or {}).get("html"),
            "fetched_at": time.time(),
        }
        image_topic, attr_topic = self.topics(j["key"])
        # attributes first so they are already in place when the new picture arrives
        mgr.publish(attr_topic, json.dumps({k: meta[k] for k in ("photographer", "photo_url", "search_term")}))
        if not mgr.publish(image_topic, full):
            return ERR_MQTT
        with open(self.thumb_path(j["key"]), "wb") as f:
            f.write(thumb)
        self.newest_photo[j["key"]] = full
        wall.offer("unsplash", j["key"], full, j["label"])
        with self.lock:
            self.meta[j["key"]] = meta
        self.save_state()
        try:  # Unsplash API rules ask for this ping when a photo is used
            requests.get(data["links"]["download_location"], headers=headers, timeout=10)
        except Exception:
            pass
        log.info("%s: new photo by %s (%d KB)", j["label"], meta["photographer"] or "unknown", len(full) // 1024)
        return None

    def request(self, keys):
        with self.lock:
            self.pending.update(keys)
        self.wake.set()

    def run(self):
        while not stop.is_set():
            if not CONNECTED.wait(3):
                continue
            with self.lock:
                pending = set(self.pending)
            full = time.time() >= self.next_full
            if not full and not pending:
                self.wake.wait(min(30, max(0.5, self.next_full - time.time())))
                self.wake.clear()
                continue
            with self.lock:
                self.pending -= pending
            if full:
                with self.lock:
                    self.last_full = time.time()
                    self.next_full = self.last_full + UNSPLASH_MIN * 60
                self.save_state()
            todo = [j for j in self.jobs() if full or j["key"] in pending]
            if not todo:
                continue
            if not UNSPLASH_KEY:
                for j in todo:
                    self.errors[j["key"]] = "No Unsplash Access Key set (add-on Configuration tab)."
                if not self.warned_no_key:
                    log.warning("No Unsplash Access Key set. Add it in the add-on Configuration tab and restart")
                    self.warned_no_key = True
                continue
            self.busy = True
            try:
                for n, j in enumerate(todo):
                    if stop.is_set():
                        break
                    try:
                        err = self.fetch(j)
                    except Exception as e:
                        log.warning("%s: %s", j["label"], e)
                        err = "Error: %s" % e
                    if err == ERR_MQTT:
                        # nothing is lost: these photos are fetched again as soon as MQTT is back
                        with self.lock:
                            self.pending.update(r["key"] for r in todo[n:])
                        log.warning("MQTT is down, the photos will be fetched again once it is back")
                        stop.wait(5)
                        break
                    if err:
                        log.warning("%s: %s", j["label"], err)
                        self.errors[j["key"]] = err
                        if "rate limit" in err:
                            for rest in todo[n + 1 :]:
                                self.errors[rest["key"]] = err
                            break
                    else:
                        self.errors.pop(j["key"], None)
                    stop.wait(2)
            finally:
                self.busy = False

    # operations
    def validate(self, data, current=None):
        name = str(data.get("name", "")).strip()[:40]
        if not re.sub(r"[^a-z0-9]+", "", name.lower()):
            raise ValueError("Give the collection a name (letters or numbers)")
        for c in self.collections:
            if c["name"].lower() == name.lower() and (current is None or c["id"] != current["id"]):
                raise ValueError("A collection called '%s' already exists" % name)
        terms = data.get("search_terms") or []
        if isinstance(terms, str):
            terms = terms.splitlines()
        terms = [str(t).strip()[:80] for t in terms if str(t).strip()][:20]
        if not terms:
            raise ValueError("Add at least one search term")
        orientation = data.get("orientation")
        if orientation not in ORIENTATIONS:
            raise ValueError("Choose Landscape, Portrait or Both")
        return {"name": name, "search_terms": terms, "orientation": orientation}

    def add(self, data):
        cfg = self.validate(data)
        with self.lock:
            if len(self.collections) >= 30:
                raise ValueError("That's a lot of collections. 30 max.")
            base = re.sub(r"[^a-z0-9]+", "_", cfg["name"].lower()).strip("_")
            ids = {c["id"] for c in self.collections}
            cid, n = base, 2
            while cid in ids:
                cid, n = f"{base}_{n}", n + 1
            c = {"id": cid, **cfg}
            self.collections.append(c)
            self.save()
            keys = [f"{cid}_{o}" for o in self.orients(c)]
        self.sync_if_connected()
        self.request(keys)
        log.info("Added Unsplash collection '%s'", c["name"])
        return c

    def update(self, cid, data):
        c = self.get(cid)
        if c is None:
            raise KeyError(cid)
        cfg = self.validate({**c, **data}, current=c)
        with self.lock:
            old_terms, old_keys = c["search_terms"], {f"{cid}_{o}" for o in self.orients(c)}
            c.update(cfg)
            new_keys = {f"{cid}_{o}" for o in self.orients(c)}
            for key in old_keys - new_keys:
                self.meta.pop(key, None)
                self.errors.pop(key, None)
                try:
                    os.remove(self.thumb_path(key))
                except OSError:
                    pass
            self.save()
            fetch_keys = new_keys if cfg["search_terms"] != old_terms else new_keys - old_keys
        self.save_state()
        self.sync_if_connected()  # also refreshes the entity name after a rename
        if fetch_keys:
            self.request(fetch_keys)
        log.info("Updated Unsplash collection '%s'", c["name"])
        return c

    def delete(self, cid):
        with self.lock:
            c = self.get(cid)
            if c is None:
                raise KeyError(cid)
            self.collections.remove(c)
            for o in ("landscape", "portrait"):
                key = f"{cid}_{o}"
                self.meta.pop(key, None)
                self.errors.pop(key, None)
                self.pending.discard(key)
                try:
                    os.remove(self.thumb_path(key))
                except OSError:
                    pass
            self.save()
        self.save_state()
        self.sync_if_connected()
        log.info("Deleted Unsplash collection '%s'", c["name"])

    def fetch_now(self, cid=None):
        keys = [j["key"] for j in self.jobs() if cid is None or j["id"] == cid]
        self.request(keys)
        return len(keys)

    def view(self):
        with self.lock:
            cols = []
            njobs = 0
            for c in self.collections:
                images = {}
                for o in self.orients(c):
                    key = f"{c['id']}_{o}"
                    njobs += 1
                    images[o] = {
                        "key": key,
                        "entity": f"image.{c['id']}_photos_{o}",
                        "has_image": os.path.exists(self.thumb_path(key)),
                        "meta": self.meta.get(key, {}),
                        "error": self.errors.get(key),
                    }
                cols.append({**c, "images": images})
            return {
                "has_key": bool(UNSPLASH_KEY),
                "interval_minutes": UNSPLASH_MIN,
                "image_size": UNSPLASH_SIZE,
                "busy": self.busy,
                "next_cycle": self.next_full,
                "per_hour": round(njobs * 60 / UNSPLASH_MIN, 1),
                "collections": cols,
            }


unsplash = Unsplash()


# ---------------------------------------------------------------- add-on wallpaper
# One wallpaper for the web UI of every add-on (their pages read /local/addon-wallpaper/wallpaper.json,
# which Home Assistant serves from /config/www). An add-on's own "wallpaper" option still wins.
WWW_DIR = os.environ.get("PS_WWW_DIR", "/homeassistant/www")
WALL_DIR = os.path.join(WWW_DIR, "addon-wallpaper")
WALL_IMG = os.path.join(WALL_DIR, "wallpaper.jpg")
WALL_JSON = os.path.join(WALL_DIR, "wallpaper.json")
WSTORE = os.path.join(DATA_DIR, "wallpaper.json")
WALL_ORIG = os.path.join(DATA_DIR, "wallpaper_original.jpg")  # the picture before darken/blur/etc.
ADJUST_KEYS = {"darken": (-100, 100), "blur": (0, 40), "saturation": (-100, 100), "contrast": (-100, 100), "warmth": (-100, 100)}


def clean_adjust(d):
    out = {}
    for k, (lo, hi) in ADJUST_KEYS.items():
        try:
            out[k] = max(lo, min(hi, int(round(float((d or {}).get(k, 0))))))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def apply_adjust(full, a):
    """darken (-100 lighten .. +100 darken), blur, saturation, contrast and warmth, applied to jpeg bytes."""
    if not any(a.values()):
        return full
    im = Image.open(io.BytesIO(full)).convert("RGB")
    if a["blur"]:
        im = im.filter(ImageFilter.GaussianBlur(a["blur"] * max(im.size) / 1600))
    if a["warmth"]:
        f = a["warmth"] / 100 * 0.14
        r, g, b = im.split()
        r = r.point(lambda v: max(0, min(255, int(v * (1 + f)))))
        b = b.point(lambda v: max(0, min(255, int(v * (1 - f)))))
        im = Image.merge("RGB", (r, g, b))
    if a["saturation"]:
        im = ImageEnhance.Color(im).enhance(1 + a["saturation"] / 100)
    if a["contrast"]:
        im = ImageEnhance.Contrast(im).enhance(1 + a["contrast"] / 100)
    if a["darken"] > 0:
        im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), a["darken"] / 100 * 0.85)
    elif a["darken"] < 0:
        im = Image.blend(im, Image.new("RGB", im.size, (255, 255, 255)), -a["darken"] / 100 * 0.7)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=QUALITY, optimize=True)
    return buf.getvalue()


class Wallpaper:
    """mode: off | image (a picked/uploaded photo) | shuffle (follows a folder shuffle) | unsplash (follows an entity)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.mode, self.source, self.label, self.updated, self.error = "off", "", "", 0.0, None
        self.adjust = clean_adjust({})

    def load(self):
        try:
            with open(WSTORE) as f:
                d = json.load(f)
            self.mode = d.get("mode", "off")
            self.source, self.label = d.get("source", ""), d.get("label", "")
            self.updated = float(d.get("updated", 0))
            self.adjust = clean_adjust(d.get("adjust"))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.error("Could not read %s: %s", WSTORE, e)

    def save(self):
        write_json(WSTORE, {"mode": self.mode, "source": self.source, "label": self.label, "updated": self.updated,
                           "adjust": self.adjust})

    def _publish(self):
        """Write the small file every add-on page reads."""
        os.makedirs(WALL_DIR, exist_ok=True)
        url = f"/local/addon-wallpaper/wallpaper.jpg?v={int(self.updated)}" if self.mode != "off" and os.path.exists(WALL_IMG) else ""
        write_json(WALL_JSON, {"url": url, "label": self.label if url else "", "updated": int(self.updated)})

    def write_image(self, full, label, keep_original=False):
        os.makedirs(WALL_DIR, exist_ok=True)
        if not keep_original:
            tmp = WALL_ORIG + ".tmp"
            with open(tmp, "wb") as f:
                f.write(full)
            os.replace(tmp, WALL_ORIG)
        tmp = WALL_IMG + ".tmp"
        with open(tmp, "wb") as f:
            f.write(apply_adjust(full, self.adjust))
        os.replace(tmp, WALL_IMG)
        self.updated, self.label, self.error = time.time(), label, None
        self._publish()
        self.save()
        log.info("Add-on wallpaper: %s", label)

    def offer(self, kind, source, full, label):
        """Called whenever a shuffle or Unsplash entity shows a new photo."""
        if self.mode == kind and self.source == source:
            try:
                with self.lock:
                    self.write_image(full, label)
            except OSError as e:
                self.error = f"Couldn't write the wallpaper: {e}"
                log.warning(self.error)

    def set_image(self, full, label):
        with self.lock:
            self.mode, self.source = "image", ""
            self.write_image(full, label)

    def follow(self, kind, source):
        if kind == "shuffle":
            s = mgr.get(source)
            if s is None:
                raise ValueError("That folder shuffle doesn't exist")
            label, full = s.name, s.last_full
            if full is None and s.last:
                full = render(s.last)[0]
        elif kind == "unsplash":
            jobs = {j["key"]: j for j in unsplash.jobs()}
            if source not in jobs:
                raise ValueError("That Unsplash collection doesn't exist")
            label, full = jobs[source]["label"], unsplash.newest_photo.get(source)
        else:
            raise ValueError("Unknown source")
        with self.lock:
            self.mode, self.source, self.label = kind, source, label
            if full is not None:
                self.write_image(full, label)
            else:  # no photo in memory yet: use the next one it shows
                self.save()
                self._publish()
        if full is None and kind == "unsplash":
            unsplash.request([source])
        elif full is None:
            mgr.get(source).request_next(wait=0)

    def set_adjust(self, d):
        """Darken / lighten / blur / etc. Re-made from the untouched original, so changes never stack up."""
        with self.lock:
            self.adjust = clean_adjust(d)
            src = WALL_ORIG if os.path.exists(WALL_ORIG) else (WALL_IMG if os.path.exists(WALL_IMG) else None)
            if self.mode != "off" and src:
                with open(src, "rb") as f:
                    full = f.read()
                if src == WALL_IMG:  # wallpaper from before this version: treat what's there as the original
                    with open(WALL_ORIG, "wb") as f:
                        f.write(full)
                self.write_image(full, self.label, keep_original=True)
            else:
                self.save()

    def off(self):
        with self.lock:
            self.mode, self.source, self.label = "off", "", ""
            self.save()
            self._publish()

    def view(self):
        return {"mode": self.mode, "source": self.source, "label": self.label, "updated": self.updated,
                "error": self.error, "has_image": self.mode != "off" and os.path.exists(WALL_IMG),
                "adjust": self.adjust, "has_original": os.path.exists(WALL_ORIG) or os.path.exists(WALL_IMG),
                "www_ok": os.access(WWW_DIR, os.W_OK)}


wall = Wallpaper()


# ---------------------------------------------------------------- mqtt
def mqtt_settings():
    if OPTIONS.get("mqtt_host"):
        return {
            "host": OPTIONS["mqtt_host"],
            "port": int(OPTIONS.get("mqtt_port") or 1883),
            "username": OPTIONS.get("mqtt_username") or None,
            "password": OPTIONS.get("mqtt_password") or None,
            "ssl": False,
        }
    req = urllib.request.Request(
        "http://supervisor/services/mqtt",
        headers={"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["data"]


def migrate_devices(c):
    """Home Assistant never moves an existing MQTT entity to another device.
    Remove each entity once, then announce it again on the shared device.
    Entity IDs are kept because the discovery payload sets default_entity_id."""
    shuffles = mgr.all()
    log.info(
        "Moving %d shuffle(s) onto the shared 'Photo Shuffle' device. Their entities are re-created once, entity IDs stay the same",
        len(shuffles),
    )
    for s in shuffles:
        c.publish(f"{DISCOVERY}/image/{BASE}_{s.id}/config", "", qos=1, retain=True)
        c.publish(f"{DISCOVERY}/button/{BASE}_{s.id}_next/config", "", qos=1, retain=True)
    if stop.wait(8) or not CONNECTED.is_set():
        log.warning("Device move interrupted, it will be retried on the next connect")
        return
    for s in mgr.all():
        s.discovery(c)
        s.trigger.set()  # publish a fresh picture so the new entity is not empty
    mgr.device_rev = DEVICE_REV
    mgr.save()
    log.info("Device move finished")


def mqtt_explain(rc):
    return {
        1: "wrong protocol version",
        2: "client id rejected",
        3: "broker unavailable",
        4: "bad username or password",
        5: "not authorised",
    }.get(rc, "code %s" % rc)


def new_client(cfg):
    # a fresh random id every time, so two copies of the add-on can never kick each other off the broker
    cid = "photo_hub_%s" % os.urandom(3).hex()
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=cid)
    except AttributeError:
        client = mqtt.Client(client_id=cid)
    if cfg.get("username"):
        client.username_pw_set(cfg["username"], cfg.get("password"))
    if cfg.get("ssl"):
        client.tls_set()
    client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    where = "%s:%s" % (cfg["host"], cfg["port"])

    def after_connect(c):
        # runs in its own thread: an error here must never be able to kill the MQTT network loop
        try:
            if mgr.device_rev < DEVICE_REV:
                threading.Thread(target=migrate_devices, args=(c,), daemon=True).start()
            else:
                for s in mgr.all():
                    s.discovery(c)
            mgr.purge_removed()
            unsplash.sync_discovery(c)
            unsplash.wake.set()
        except Exception:
            log.exception("Could not announce the entities to Home Assistant")

    def on_connect(c, userdata, flags, rc):
        try:
            if c is not mgr.client:
                return
            if rc != 0:
                why = mqtt_explain(rc)
                mq_state.update(status="error", detail="Broker refused the connection (%s)" % why)
                log.error("MQTT connect failed: %s", why)
                if rc in (4, 5):
                    REFRESH.set()  # the login probably changed, fetch the broker settings again
                return
            log.info("Connected to MQTT")
            mq_state.update(status="connected", detail=where)
            c.publish(STATUS_TOPIC, "online", qos=1, retain=True)
            CONNECTED.set()
            threading.Thread(target=after_connect, args=(c,), daemon=True).start()
        except Exception:
            log.exception("MQTT on_connect failed")

    def on_disconnect(c, userdata, rc):
        try:
            if c is not mgr.client:
                return  # an old client that was replaced on purpose
            CONNECTED.clear()
            mq_state.update(status="connecting", detail="Reconnecting to %s" % where)
            if rc != 0 and not stop.is_set():
                log.warning("Lost MQTT connection (code %s), reconnecting", rc)
        except Exception:
            log.exception("MQTT on_disconnect failed")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client


def stop_client(old):
    def _stop():
        try:
            old.disconnect()
        except Exception:
            pass
        try:
            old.loop_stop()
        except Exception:
            pass

    # in a thread so a stuck old connection can never block the new one
    threading.Thread(target=_stop, daemon=True).start()


def start_client(cfg):
    old = mgr.client
    CONNECTED.clear()
    mgr.client = None
    if old is not None:
        stop_client(old)
    client = new_client(cfg)
    mgr.client = client
    log.info("Using MQTT broker %s:%s", cfg["host"], cfg["port"])
    mq_state.update(status="connecting", detail="%s:%s" % (cfg["host"], cfg["port"]))
    client.connect_async(cfg["host"], int(cfg["port"]), 60)
    client.loop_start()
    return client


def heartbeat(client):
    """Send a message and make sure the broker really acknowledges it. Also keeps the entities 'available'."""
    try:
        info = client.publish(STATUS_TOPIC, "online", qos=1, retain=True)
        info.wait_for_publish(15)
        return info.is_published()
    except Exception:
        return False


def mqtt_worker():
    """Starts the MQTT client and keeps it alive. If the connection is lost and does not come back,
    the whole client is thrown away and rebuilt with freshly fetched broker settings, so the add-on
    never needs a manual restart."""
    client = None
    down_since = None
    last_beat = time.time()
    beat_fail = 0
    while not stop.is_set():
        need_new = client is None
        if client is not None:
            thread = getattr(client, "_thread", None)
            if thread is not None and not thread.is_alive() and not stop.is_set():
                log.warning("The MQTT network thread stopped, starting a fresh connection")
                need_new = True
            elif REFRESH.is_set():
                REFRESH.clear()
                log.info("Fetching the MQTT broker settings again")
                need_new = True
            elif client.is_connected():
                down_since = None
                if time.time() - last_beat >= MQTT_BEAT_EVERY:
                    last_beat = time.time()
                    if heartbeat(client):
                        beat_fail = 0
                    else:
                        beat_fail += 1
                        log.warning("The MQTT broker did not answer a health check (%d)", beat_fail)
                        if beat_fail >= 2:
                            need_new = True
            else:
                if down_since is None:
                    down_since = time.time()
                elif time.time() - down_since > MQTT_DOWN_LIMIT:
                    log.warning("MQTT has been down for %d seconds, starting a fresh connection", MQTT_DOWN_LIMIT)
                    need_new = True
        if need_new:
            try:
                cfg = mqtt_settings()
                client = start_client(cfg)
                down_since = None
                beat_fail = 0
                last_beat = time.time()
            except Exception as e:
                mq_state.update(status="error", detail="No MQTT broker found. Is the Mosquitto add-on running?")
                log.error("Could not get MQTT settings (%s). Retrying in 15s", e)
                stop.wait(15)
                continue
        stop.wait(5)


# ---------------------------------------------------------------- web ui
app = Flask(__name__)
INDEX = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()


@app.before_request
def only_ingress():
    if os.environ.get("PS_DEV"):
        return None
    if request.remote_addr not in ("172.30.32.2", "127.0.0.1"):
        return Response("Forbidden", 403)


# ---------- backups (shared module, see addon_backup.py) ----------
@app.route("/backups", defaults={"sub": ""}, methods=["GET", "POST"])
@app.route("/backups/<path:sub>", methods=["GET", "POST"])
def backups(sub):
    st, ct, body, hdr = BACKUP.handle(request.method, sub, request.args, request.get_data(), request.remote_addr)
    return Response(body, status=st, content_type=ct, headers=hdr)


def err(msg, code=400):
    return jsonify({"error": msg}), code


@app.get("/")
def index():
    return Response(INDEX, mimetype="text/html", headers={"Cache-Control": "no-store"})


@app.get("/api/state")
def api_state():
    return jsonify(
        {
            "now": time.time(),
            "mqtt": dict(mq_state),
            "formats": FORMATS,
            "max_dimension": MAX_DIM,
            "roots": [{"path": r, "exists": os.path.isdir(r)} for r in ROOTS],
            "shuffles": [s.view() for s in mgr.all()],
            "unsplash": unsplash.view(),
            "wallpaper": wall.view(),
            "editor": {"folder": EDIT_DIR, "writable": os.access(EDIT_DIR, os.W_OK)},
            "log": list(UI_LOG.buf)[-80:],
        }
    )


# folder shuffles
@app.post("/api/shuffles")
def api_add():
    try:
        s = mgr.add(request.get_json(silent=True) or {})
    except ValueError as e:
        return err(str(e))
    return jsonify(s.view())


@app.put("/api/shuffles/<sid>")
def api_update(sid):
    try:
        s = mgr.update(sid, request.get_json(silent=True) or {})
    except KeyError:
        return err("Not found", 404)
    except ValueError as e:
        return err(str(e))
    return jsonify(s.view())


@app.delete("/api/shuffles/<sid>")
def api_delete(sid):
    try:
        mgr.delete(sid)
    except KeyError:
        return err("Not found", 404)
    return jsonify({"ok": True})


@app.post("/api/shuffles/<sid>/next")
def api_next(sid):
    s = mgr.get(sid)
    if s is None:
        return err("Not found", 404)
    s.request_next()
    return jsonify({"ok": True})


@app.get("/api/shuffles/<sid>/thumb.jpg")
def api_thumb(sid):
    s = mgr.get(sid)
    if s is None or s.thumb is None:
        return Response(status=404)
    return Response(s.thumb, mimetype="image/jpeg", headers={"Cache-Control": "no-cache"})


# unsplash collections
@app.post("/api/unsplash/collections")
def api_u_add():
    try:
        c = unsplash.add(request.get_json(silent=True) or {})
    except ValueError as e:
        return err(str(e))
    return jsonify(c)


@app.put("/api/unsplash/collections/<cid>")
def api_u_update(cid):
    try:
        c = unsplash.update(cid, request.get_json(silent=True) or {})
    except KeyError:
        return err("Not found", 404)
    except ValueError as e:
        return err(str(e))
    return jsonify(c)


@app.delete("/api/unsplash/collections/<cid>")
def api_u_delete(cid):
    try:
        unsplash.delete(cid)
    except KeyError:
        return err("Not found", 404)
    return jsonify({"ok": True})


@app.post("/api/unsplash/collections/<cid>/fetch")
def api_u_fetch(cid):
    if unsplash.get(cid) is None:
        return err("Not found", 404)
    return jsonify({"ok": True, "fetching": unsplash.fetch_now(cid)})


@app.post("/api/unsplash/fetch")
def api_u_fetch_all():
    return jsonify({"ok": True, "fetching": unsplash.fetch_now()})


@app.get("/api/unsplash/thumb/<key>.jpg")
def api_u_thumb(key):
    if not UKEY_RE.match(key):
        return Response(status=404)
    try:
        with open(unsplash.thumb_path(key), "rb") as f:
            data = f.read()
    except OSError:
        return Response(status=404)
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-cache"})


# add-on wallpaper
@app.put("/api/wallpaper")
def api_wall_set():
    d = request.get_json(silent=True) or {}
    try:
        if d.get("mode") == "off":
            wall.off()
        elif d.get("mode") in ("shuffle", "unsplash"):
            wall.follow(d["mode"], str(d.get("source") or ""))
        elif d.get("mode") == "file":
            p = os.path.normpath(str(d.get("path") or ""))
            if not in_roots(p) or not os.path.isfile(p) or not is_image(p):
                return err("Pick a picture inside your photo paths")
            wall.set_image(render(p)[0], os.path.basename(p))
        else:
            return err("Unknown choice")
    except ValueError as e:
        return err(str(e))
    except OSError as e:
        return err(f"Couldn't save the wallpaper: {e}")
    return jsonify(wall.view())


@app.post("/api/wallpaper/upload")
def api_wall_upload():
    data = request.get_data()
    if not data:
        return err("No picture was sent")
    if len(data) > 40 * 1024 * 1024:
        return err("That picture is over 40 MB")
    try:
        full = render(io.BytesIO(data))[0]
    except Exception:
        return err("That file isn't a picture I can read")
    try:
        wall.set_image(full, (request.args.get("name") or "Uploaded picture")[:80])
    except OSError as e:
        return err(f"Couldn't save the wallpaper: {e}")
    return jsonify(wall.view())


@app.get("/api/wallpaper/image.jpg")
def api_wall_image():
    try:
        with open(WALL_IMG, "rb") as f:
            data = f.read()
    except OSError:
        return Response(status=404)
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-cache"})


@app.get("/api/files")
def api_files():
    """Pictures in one folder (for picking a wallpaper)."""
    p = os.path.normpath(request.args.get("path", ""))
    if not in_roots(p) or not os.path.isdir(p):
        return err("Not an allowed folder")
    files = []
    try:
        with os.scandir(p) as it:
            for e in it:
                if e.is_file() and is_image(e.name):
                    files.append({"name": e.name, "path": e.path})
    except OSError as e:
        return err(str(e))
    files.sort(key=lambda f: f["name"].lower())
    return jsonify({"path": p, "files": files[:400], "more": len(files) > 400})


@app.get("/api/preview.jpg")
def api_preview():
    p = os.path.normpath(request.args.get("path", ""))
    if not in_roots(p) or not os.path.isfile(p) or not is_image(p):
        return Response(status=404)
    try:
        with Image.open(p) as im:
            if im.format == "JPEG":
                im.draft("RGB", (320, 320))
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((320, 320))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=70)
    except Exception:
        return Response(status=404)
    return Response(buf.getvalue(), mimetype="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/browse")
def api_browse():
    p = request.args.get("path", "")
    if not p:
        return jsonify({"roots": [{"path": r, "exists": os.path.isdir(r)} for r in ROOTS]})
    p = os.path.normpath(p)
    if not in_roots(p) or not os.path.isdir(p):
        return err("Not an allowed folder")
    dirs, images = [], 0
    try:
        with os.scandir(p) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                if e.is_dir():
                    dirs.append({"name": e.name, "path": os.path.join(p, e.name)})
                elif e.is_file() and is_image(e.name):
                    images += 1
    except OSError as e:
        return err(str(e))
    dirs.sort(key=lambda d: d["name"].lower())
    parent = None if p in ROOTS else os.path.dirname(p)
    return jsonify({"path": p, "parent": parent, "dirs": dirs, "images": images})


# ---------------------------------------------------------------- picture sources for the Photo Editor
def jpeg(data, cache="no-cache"):
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": cache})


@app.get("/api/image.jpg")
def api_image():
    """A picture from the photo folders, at full working size."""
    p = os.path.normpath(request.args.get("path", ""))
    if not in_roots(p) or not os.path.isfile(p) or not is_image(p):
        return Response(status=404)
    ext = os.path.splitext(p)[1].lower()
    if request.args.get("raw") and ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") and os.path.getsize(p) < 40 * 1024 * 1024:
        with open(p, "rb") as f:  # untouched file (keeps PNG transparency); the browser shrinks it
            return Response(f.read(), mimetype={".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/jpeg"),
                            headers={"Cache-Control": "no-cache"})
    try:
        return jpeg(render(p)[0])
    except Exception:
        return Response(status=404)


@app.get("/api/shuffles/<sid>/full.jpg")
def api_full(sid):
    s = mgr.get(sid)
    if s is None:
        return Response(status=404)
    full = s.last_full
    if full is None and s.last:
        try:
            full = render(s.last)[0]
        except Exception:
            full = None
    return jpeg(full) if full else Response(status=404)


@app.get("/api/unsplash/full/<key>.jpg")
def api_u_full(key):
    full = unsplash.newest_photo.get(key) if UKEY_RE.match(key) else None
    if full:
        return jpeg(full)
    return api_u_thumb(key)


@app.get("/api/wallpaper/original.jpg")
def api_wall_orig():
    for p in (WALL_ORIG, WALL_IMG):
        try:
            with open(p, "rb") as f:
                return jpeg(f.read())
        except OSError:
            pass
    return Response(status=404)


@app.put("/api/wallpaper/adjust")
def api_wall_adjust():
    try:
        wall.set_adjust(request.get_json(silent=True) or {})
    except (OSError, ValueError) as e:
        return err(f"Couldn't change the wallpaper: {e}")
    return jsonify(wall.view())


def safe_name(n):
    n = re.sub(r"[^A-Za-z0-9 ._-]+", "", os.path.splitext(str(n or ""))[0]).strip(" .")[:60]
    return n or "edited"


@app.post("/api/edit/save")
def api_edit_save():
    """Save a picture from the Photo Editor into the edits folder (or another folder in your photo paths)."""
    data = request.get_data()
    if not data:
        return err("No picture was sent")
    folder = os.path.normpath(request.args.get("folder") or EDIT_DIR)
    if not (folder == EDIT_DIR or in_roots(folder)) or not os.path.isdir(folder):
        return err("Pick a folder inside your photo paths")
    if not os.access(folder, os.W_OK):
        return err(f"Photo Hub can't write to {folder}. Folders on /media need the add-on update's write access, "
                   "or pick the edits folder.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            png = request.args.get("format") == "png" or (im.mode in ("RGBA", "LA") and request.args.get("format") != "jpg")
            base = safe_name(request.args.get("name"))
            path = os.path.join(folder, base + (".png" if png else ".jpg"))
            i = 2
            while os.path.exists(path):
                path = os.path.join(folder, f"{base}-{i}" + (".png" if png else ".jpg"))
                i += 1
            if png:
                im.save(path, "PNG", optimize=True)
            else:
                im.convert("RGB").save(path, "JPEG", quality=92, optimize=True)
    except OSError as e:
        return err(f"Couldn't save it: {e}")
    except Exception:
        return err("That isn't a picture I can read")
    log.info("Photo Editor saved %s", path)
    return jsonify({"ok": True, "path": path, "name": os.path.basename(path)})


@app.get("/api/edit/recent")
def api_edit_recent():
    out = []
    try:
        with os.scandir(EDIT_DIR) as it:
            for e in it:
                if e.is_file() and is_image(e.name):
                    out.append({"name": e.name, "path": e.path, "t": e.stat().st_mtime})
    except OSError:
        pass
    out.sort(key=lambda x: -x["t"])
    return jsonify({"folder": EDIT_DIR, "writable": os.access(EDIT_DIR, os.W_OK), "files": out[:30]})


# ---------------------------------------------------------------- SVG Maker engine (its own process)
SVG_DIR = os.path.join(HERE, "svg")
SVG_PORT = int(os.environ.get("PS_SVG_PORT", 8101))
SVG_URL = f"http://127.0.0.1:{SVG_PORT}"
HOP = {"content-encoding", "transfer-encoding", "connection", "content-length", "keep-alive"}


def die_with_parent():
    """Linux: stop the engine too if Photo Hub itself is killed."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def svg_engine():
    """SVG Maker and the AI tools run in their own process (an asyncio server). Restart it if it ever stops."""
    while not stop.is_set():
        env = dict(os.environ, SVG_PORT=str(SVG_PORT), WWW_DIR=os.path.join(SVG_DIR, "www"), DATA_DIR=DATA_DIR)
        try:
            proc = subprocess.Popen([sys.executable, "-u", os.path.join(SVG_DIR, "server.py")], cwd=SVG_DIR, env=env,
                                    preexec_fn=die_with_parent)
        except OSError as e:
            log.error("Couldn't start the SVG Maker engine: %s", e)
            return
        while proc.poll() is None and not stop.is_set():
            time.sleep(1)
        if stop.is_set():
            proc.terminate()
            return
        log.warning("SVG Maker engine stopped (exit %s), restarting in 10 seconds", proc.returncode)
        stop.wait(10)


def proxy(path):
    try:
        r = requests.request(request.method, f"{SVG_URL}/{path}", params=request.args, data=request.get_data(),
                             headers={k: v for k, v in request.headers.items() if k.lower() in ("content-type", "accept")},
                             timeout=660)
    except requests.RequestException:
        return err("The SVG and AI engine is still starting. Try again in a few seconds.", 503)
    return Response(r.content, status=r.status_code, headers=[(k, v) for k, v in r.headers.items() if k.lower() not in HOP])


@app.route("/svg/", defaults={"p": ""}, methods=["GET", "POST"])
@app.route("/svg/<path:p>", methods=["GET", "POST"])
def svg_proxy(p):
    return proxy(p)


@app.route("/api/ai/<path:p>", methods=["GET", "POST"])
def ai_proxy(p):
    return proxy("api/photo/ai/" + p)


# ---------------------------------------------------------------- main
def main():
    if not ROOTS:
        log.warning("No photo paths configured. Add some under Configuration, then restart")
    log.info("Allowed paths: %s | formats: %s", ", ".join(ROOTS) or "none", ", ".join(FORMATS))
    mgr.load()
    log.info("Loaded %d folder shuffle(s)", len(mgr.shuffles))
    unsplash.load()
    wall.load()
    try:
        wall._publish()  # make sure the file the add-ons read matches the saved choice
    except OSError as e:
        wall.error = f"Can't write to {WWW_DIR}: {e}"
        log.warning(wall.error)
    log.info(
        "Loaded %d Unsplash collection(s) | key: %s | every %d min, size %s",
        len(unsplash.collections),
        "set" if UNSPLASH_KEY else "not set",
        UNSPLASH_MIN,
        UNSPLASH_SIZE,
    )
    for s in mgr.all():
        s.start()
    threading.Thread(target=unsplash.run, daemon=True).start()
    BACKUP.start()
    threading.Thread(target=mqtt_worker, daemon=True).start()
    if os.path.isfile(os.path.join(SVG_DIR, "server.py")):
        threading.Thread(target=svg_engine, daemon=True).start()
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PS_PORT", 8099)), threaded=True, use_reloader=False),
        daemon=True,
    ).start()

    signal.signal(signal.SIGTERM, lambda *a: stop.set())
    signal.signal(signal.SIGINT, lambda *a: stop.set())
    stop.wait()
    if mgr.client is not None:
        try:
            mgr.client.publish(STATUS_TOPIC, "offline", qos=1, retain=True).wait_for_publish(2)
            mgr.client.loop_stop()
            mgr.client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()

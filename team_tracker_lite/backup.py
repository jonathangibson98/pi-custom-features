#!/usr/bin/env python3
"""Shared backup helper for the add-ons in this repository (standard library only).

  backup.py restore   restore the backup named in the restore_backup option (run before the app starts)
  backup.py daemon    back up a minute after start-up, then every backup_interval_hours
  backup.py now       back up right now
  backup.py list      show the backups that exist

The add-on's start script sets:
  BACKUP_SLUG     add-on slug, used in file names
  BACKUP_EXTRA    comma list of extra folders. "@name" means the folder in the option called name
  BACKUP_EXCLUDE  comma list of file or folder names to leave out
  BACKUP_DATA     set to 0 to leave /data out
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback
import urllib.request
import zipfile

SLUG = (os.environ.get("BACKUP_SLUG") or "addon").strip()
OPTIONS_FILE = "/data/options.json"
STATE_FILE = "/data/.backup_state.json"
MAX_FILE = 25 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
ROOTS = ("/data", "/share", "/media", "/homeassistant", "/config", "/addon_configs", "/ssl")
SKIP_NAMES = {".backup_state.json", "__pycache__", "lost+found", "password.txt"}
SKIP_SUFFIX = (".tmp", ".lock", ".pid", ".sock", ".pyc", ".pem", ".key")
SECRET_WORDS = ("password", "passwd", "token", "secret", "key")
NAME_RE = re.compile(r"^%s-\d{8}-\d{6}(-\d+)?\.zip$" % re.escape(SLUG))
PRE_RE = re.compile(r"^%s-prerestore-\d{8}-\d{6}(-\d+)?\.zip$" % re.escape(SLUG))


def log(msg):
    print("[backup] " + msg, flush=True)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as err:
        log("Could not write %s: %s" % (path, err))


def under(path, root):
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def settings():
    opts = read_json(OPTIONS_FILE, {})
    if not isinstance(opts, dict):
        opts = {}
    folder = os.path.normpath(str(opts.get("backup_path") or "/share/%s_backups" % SLUG).strip())

    def num(key, default, low):
        try:
            return max(low, int(opts.get(key, default)))
        except (TypeError, ValueError):
            return default

    return {
        "opts": opts,
        "enabled": opts.get("backup_enabled", True) is not False,
        "folder": folder,
        "valid": folder.startswith("/") and folder not in ROOTS and any(under(folder, r) for r in ROOTS),
        "keep": num("backup_keep", 20, 1),
        "hours": num("backup_interval_hours", 24, 0),
        "restore": str(opts.get("restore_backup") or "").strip(),
    }


def extra_skip():
    return set(x.strip() for x in os.environ.get("BACKUP_EXCLUDE", "").split(",") if x.strip())


def sources(cfg):
    """Folders to back up, as a list of (name inside the zip, real folder)."""
    out, taken = [], []
    skip_real = os.path.realpath(cfg["folder"])

    def add(name, path, from_option):
        path = os.path.normpath(path.strip())
        if not path.startswith("/") or not any(under(path, r) for r in ROOTS):
            log("Skipping %s (not a folder this add-on can use)" % path)
            return
        if from_option and path in ROOTS:
            log("Skipping %s (that is a whole top-level folder, use a subfolder)" % path)
            return
        if not os.path.isdir(path):
            return
        real = os.path.realpath(path)
        if under(real, skip_real) or any(under(real, t) for t in taken):
            return
        taken.append(real)
        out.append((name, path))

    if os.environ.get("BACKUP_DATA", "1") != "0":
        add("data", "/data", False)
    n = 0
    for raw in os.environ.get("BACKUP_EXTRA", "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("@"):
            val = cfg["opts"].get(raw[1:])
            if isinstance(val, str):
                paths = [val]
            elif isinstance(val, list):
                paths = [str(v) for v in val]
            else:
                paths = []
            from_option = True
        else:
            paths, from_option = [raw], False
        for p in paths:
            if p.strip():
                n += 1
                add("extra%d" % n, p, from_option)
    return out


def collect(cfg):
    files, total, roots = [], 0, {}
    skip_real = os.path.realpath(cfg["folder"])
    skip = extra_skip()
    for name, base in sources(cfg):
        roots[name] = base
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_NAMES and d not in skip
                and os.path.realpath(os.path.join(dirpath, d)) != skip_real
            ]
            for fn in filenames:
                if fn in SKIP_NAMES or fn in skip or fn.endswith(SKIP_SUFFIX):
                    continue
                full = os.path.join(dirpath, fn)
                if full == OPTIONS_FILE or os.path.islink(full):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if st.st_size > MAX_FILE:
                    log("Skipping %s (bigger than 25 MB)" % full)
                    continue
                total += st.st_size
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                files.append(("%s/%s" % (name, rel), full, st))
    return roots, files, total


def fingerprint(files):
    h = hashlib.sha256()
    for arc, _full, st in sorted(files, key=lambda x: x[0]):
        h.update(("%s|%d|%d\n" % (arc, st.st_size, st.st_mtime_ns)).encode("utf-8", "replace"))
    return h.hexdigest()


def redact(value, key=""):
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if value and not isinstance(value, bool) and any(w in key.lower() for w in SECRET_WORDS):
        return "***"
    return value


def prune(cfg):
    try:
        names = sorted(os.listdir(cfg["folder"]))
    except OSError:
        return
    normal = [n for n in names if NAME_RE.match(n)]
    pre = [n for n in names if PRE_RE.match(n)]
    for old in normal[:-cfg["keep"]] + pre[:-3]:
        try:
            os.remove(os.path.join(cfg["folder"], old))
            log("Removed old backup %s" % old)
        except OSError:
            pass


def make_backup(reason, force=False, prerestore=False):
    cfg = settings()
    if not cfg["valid"]:
        log("backup_path %s is not allowed. Use a subfolder of /share, /media, /homeassistant or /config." % cfg["folder"])
        return None
    roots, files, total = collect(cfg)
    if not files:
        log("Nothing to back up yet.")
        return None
    if total > MAX_TOTAL:
        log("Backup skipped: %d MB is over the 500 MB limit. Use a smaller folder." % (total // 1048576))
        return None
    fp = fingerprint(files)
    state = read_json(STATE_FILE, {})
    last = state.get("last")
    if (not force and state.get("fingerprint") == fp and last
            and os.path.exists(os.path.join(cfg["folder"], last))):
        log("No changes since the last backup (%s), so no new file was made." % last)
        return None
    os.makedirs(cfg["folder"], exist_ok=True)
    label = SLUG + ("-prerestore" if prerestore else "")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name, n = "%s-%s.zip" % (label, stamp), 1
    while os.path.exists(os.path.join(cfg["folder"], name)):
        n += 1
        name = "%s-%s-%d.zip" % (label, stamp, n)
    path = os.path.join(cfg["folder"], name)
    tmp = path + ".tmp"
    manifest = {
        "slug": SLUG,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason,
        "roots": roots,
        "files": len(files),
    }
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr("options_reference.json", json.dumps(redact(cfg["opts"]), indent=2))
        for arc, full, st in files:
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            when = time.localtime(st.st_mtime)
            info = zipfile.ZipInfo(arc, date_time=when[:6] if when[0] >= 1980 else (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    os.replace(tmp, path)
    log("Saved %s (%d files, %s)" % (name, len(files), reason))
    if not prerestore:
        state["fingerprint"] = fp
        state["last"] = name
        write_json(STATE_FILE, state)
    prune(cfg)
    return name


def clear_restore_option(opts):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    body = dict(opts)
    body["restore_backup"] = ""
    req = urllib.request.Request(
        "http://supervisor/addons/self/options",
        data=json.dumps({"options": body}).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=15).read()
        log("restore_backup was cleared.")
    except Exception as err:
        log("Could not clear restore_backup automatically (%s). Clear it by hand." % err)


def restore():
    cfg = settings()
    state = read_json(STATE_FILE, {})
    want = cfg["restore"]
    if not want:
        if "restored" in state:
            state.pop("restored")
            write_json(STATE_FILE, state)
        return
    name = os.path.basename(want)
    if not name.endswith(".zip"):
        name += ".zip"
    if state.get("restored") == name:
        log("restore_backup is still set to %s and was already restored. Clear the option." % name)
        return
    path = os.path.join(cfg["folder"], name)
    if not os.path.isfile(path):
        log("Restore skipped: %s was not found in %s" % (name, cfg["folder"]))
        return
    try:
        z = zipfile.ZipFile(path)
        manifest = json.loads(z.read("manifest.json"))
    except Exception as err:
        log("Restore skipped: %s is not a readable backup (%s)" % (name, err))
        return
    if manifest.get("slug") != SLUG:
        log("Restore skipped: %s belongs to the add-on %s" % (name, manifest.get("slug")))
        return
    allowed = [os.path.normpath(base) for _n, base in sources(cfg)]
    targets = {}
    for root, base in (manifest.get("roots") or {}).items():
        if os.path.normpath(base) in allowed:
            targets[root] = os.path.normpath(base)
        else:
            log("Not restoring %s: that folder is not set up in this add-on now." % base)
    try:
        make_backup("before restore", force=True, prerestore=True)
    except Exception:
        log("Could not save a safety copy first:\n" + traceback.format_exc())
    count = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        parts = info.filename.split("/", 1)
        if len(parts) != 2 or parts[0] not in targets:
            continue
        base = targets[parts[0]]
        dest = os.path.normpath(os.path.join(base, parts[1]))
        if dest == base or not under(dest, base):
            log("Skipping unsafe path %s" % info.filename)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".restore.tmp"
        with z.open(info) as src, open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        os.replace(tmp, dest)
        count += 1
    state = read_json(STATE_FILE, {})
    state["restored"] = name
    write_json(STATE_FILE, state)
    log("Restored %d files from %s." % (count, name))
    clear_restore_option(cfg["opts"])


def show():
    cfg = settings()
    try:
        names = sorted((n for n in os.listdir(cfg["folder"]) if NAME_RE.match(n) or PRE_RE.match(n)), reverse=True)
    except OSError:
        names = []
    log("Backup folder: %s" % cfg["folder"])
    if names:
        log("Newest backups (to restore one, put its name in restore_backup): " + ", ".join(names[:10]))
    else:
        log("No backups yet.")


def daemon():
    cfg = settings()
    if not cfg["enabled"]:
        log("Automatic backups are off (backup_enabled is false).")
        return
    time.sleep(60)
    reason = "start"
    while True:
        try:
            make_backup(reason)
        except Exception:
            log("Backup failed:\n" + traceback.format_exc())
        reason = "scheduled"
        if cfg["hours"] <= 0:
            return
        time.sleep(cfg["hours"] * 3600)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "daemon"
    try:
        if cmd == "restore":
            restore()
            show()
        elif cmd == "daemon":
            daemon()
        elif cmd == "now":
            make_backup("manual", force=True)
        elif cmd == "list":
            show()
        else:
            print(__doc__)
    except Exception:
        log("Error:\n" + traceback.format_exc())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

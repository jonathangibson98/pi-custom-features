"""Backups for a Home Assistant add-on: one shared file, copied into each add-on (standard library only).

A backup is a .zip holding the add-on's own data (/data), any other folders it writes to (for example a save folder),
its Configuration tab settings, and a manifest. They are saved to the folder in the backup_path option (or a single
.zip file, overwritten each time), on a schedule (backup_every) and by hand, and the newest backup_keep are kept.

Restoring never swaps files under a running add-on. It saves a safety copy, puts the Configuration tab settings back
through the Supervisor, queues the backup in /data and restarts the add-on; on the next start apply_pending() (called
before the add-on reads any of its files) unpacks it. A web page for all this is served under /backups by whichever
web framework the add-on uses: call handle() from a route.

Keep this file identical in every add-on. The master copy is .shared/addon_backup.py in the repository.
"""
import fnmatch
import io
import json
import os
import shutil
import sys
import threading
import time
import urllib.request
import zipfile

FORMAT = 1
PENDING_NAME = ".restore_pending.zip"
ROOTS = tuple(os.environ.get("ADDON_BACKUP_ROOTS", "/share,/media,/homeassistant,/config,/addon_configs,/backup").split(","))
MAX_FILE = 50 * 1024 * 1024        # single files bigger than this are skipped (and listed)
MAX_TOTAL = 500 * 1024 * 1024      # a backup stops growing here
INGRESS = ("172.30.32.2",)  # Home Assistant's ingress proxy
ALWAYS_SKIP = ("__pycache__", "*.pyc", ".restore_pending.zip", "*.tmp")


def _log(msg):
    print("[backup] " + msg, flush=True)


def listen_stdin(on_backup):
    """Home Assistant's hassio.addon_stdin action writes to the add-on's stdin (with stdin: true in config.yaml).
    Sending "backup" there makes a backup now, so one script can back up every add-on at once."""
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
                return  # nothing attached (stdin off, or not running as an add-on)
            tail = (tail + chunk)[-64:]
            if b"backup" in tail.lower():
                tail = b""
                _log("Backup asked for by Home Assistant (hassio.addon_stdin)")
                try:
                    on_backup()
                except Exception as e:  # noqa: BLE001
                    _log("That backup failed: %s" % e)
    threading.Thread(target=run, daemon=True).start()


class Backup:
    """paths: list of (key, path or callable(options) -> path, mode, skip patterns).
    mode "replace": the folder belongs to this add-on, a restore makes it exactly like the backup (options.json is
    never touched). mode "merge": a shared folder, a restore only writes the backed-up files over what is there."""

    def __init__(self, slug, name, version, paths, data_dir="/data"):
        self.slug, self.name, self.version = slug, name, version
        self.data_dir = data_dir
        self.pending = os.path.join(data_dir, PENDING_NAME)
        self.paths = paths
        self.lock = threading.Lock()
        self.token = os.environ.get("SUPERVISOR_TOKEN", "")
        self.opts = self._options()
        self.last_error = ""
        self.restored = self.apply_pending()

    # ---------------------------------------------------------------- settings
    def _options(self):
        try:
            with open(os.path.join(self.data_dir, "options.json")) as f:
                return json.load(f)
        except Exception:
            return {}

    def target(self):
        """(folder, single file or None, problem)."""
        raw = str(self.opts.get("backup_path") or "/share/addon_backups/" + self.slug).strip().rstrip("/")
        path = os.path.normpath(raw)
        if not path.startswith(ROOTS) or ".." in raw.split("/"):
            return None, None, "backup_path must be inside %s." % ", ".join(r for r in ROOTS)
        root = "/" + path.split("/")[1]
        if not os.path.isdir(root):
            return None, None, "%s isn't available to this add-on. Use a folder inside /share." % root
        if path.lower().endswith(".zip"):
            return os.path.dirname(path), path, ""
        return path, None, ""

    def every(self):
        v = str(self.opts.get("backup_every") or "daily").lower()
        return {"off": 0, "daily": 86400, "weekly": 7 * 86400}.get(v, 86400)

    def keep(self):
        try:
            return max(1, min(100, int(self.opts.get("backup_keep") or 10)))
        except (TypeError, ValueError):
            return 10

    def resolved_paths(self):
        out = []
        for key, p, mode, skip in self.paths:
            try:
                p = p(self.opts) if callable(p) else p
            except Exception:
                p = None
            if p:
                out.append((key, os.path.normpath(str(p)), mode, tuple(skip or ())))
        return out

    # ---------------------------------------------------------------- making a backup
    def _skip(self, rel, skip):
        name = os.path.basename(rel)
        return any(fnmatch.fnmatch(name, s) or fnmatch.fnmatch(rel, s) or rel.startswith(s.rstrip("/") + "/")
                   for s in skip + ALWAYS_SKIP)

    def _files(self, folder, skip):
        if os.path.isfile(folder):
            yield os.path.basename(folder), folder
            return
        for dirpath, dirs, files in os.walk(folder):
            rel_dir = os.path.relpath(dirpath, folder)
            dirs[:] = [d for d in dirs if not self._skip(os.path.normpath(os.path.join(rel_dir, d)), skip)]
            for n in files:
                rel = os.path.normpath(os.path.join(rel_dir, n))
                if not self._skip(rel, skip):
                    yield rel, os.path.join(dirpath, n)

    def build_zip(self, out_path):
        """Write a backup to out_path. Returns the manifest."""
        manifest = {"format": FORMAT, "addon": self.slug, "name": self.name, "version": self.version,
                    "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "paths": {}, "skipped": []}
        total = 0
        tmp = out_path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("options.json", json.dumps(self._options(), indent=1))
            for key, folder, mode, skip in self.resolved_paths():
                if not os.path.exists(folder):
                    continue
                if os.path.realpath(folder) == os.path.realpath(os.path.dirname(out_path)):
                    continue
                manifest["paths"][key] = {"path": folder, "mode": mode, "file": os.path.isfile(folder)}
                for rel, full in self._files(folder, skip):
                    if os.path.realpath(full) == os.path.realpath(out_path) or full.endswith(".zip.tmp"):
                        continue
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        continue
                    if key == "data" and rel == "options.json":
                        continue
                    if size > MAX_FILE or total + size > MAX_TOTAL:
                        manifest["skipped"].append(os.path.join(folder, rel))
                        continue
                    try:
                        z.write(full, "files/%s/%s" % (key, rel))
                        total += size
                    except (OSError, ValueError):
                        manifest["skipped"].append(os.path.join(folder, rel))
            z.writestr("manifest.json", json.dumps(manifest, indent=1))
        os.replace(tmp, out_path)
        return manifest

    def backup_now(self, tag=""):
        folder, single, problem = self.target()
        if problem:
            raise RuntimeError(problem)
        with self.lock:
            os.makedirs(folder, exist_ok=True)
            if single and not tag:
                path = single
            else:
                stem = os.path.splitext(os.path.basename(single))[0] if single else self.slug + "_backup"
                path = os.path.join(folder, "%s%s_%s.zip" % (stem, ("_" + tag) if tag else "", time.strftime("%Y%m%d-%H%M%S")))
            m = self.build_zip(path)
            self.prune()
        self.last_error = ""
        _log("Saved %s (%d KB)%s" % (path, os.path.getsize(path) // 1024,
                                       ", skipped %d big files" % len(m["skipped"]) if m["skipped"] else ""))
        return path, m

    def prune(self):
        folder, single, _ = self.target()
        if single or not folder:
            return
        regular = [b for b in self.list() if not b["safety"]]
        safety = [b for b in self.list() if b["safety"]]
        for b in regular[self.keep():] + safety[3:]:
            try:
                os.remove(os.path.join(folder, b["file"]))
            except OSError:
                pass

    def list(self):
        folder, single, problem = self.target()
        if problem or not folder or not os.path.isdir(folder):
            return []
        out = []
        stem = os.path.splitext(os.path.basename(single))[0] if single else self.slug + "_backup"
        for n in os.listdir(folder):
            p = os.path.join(folder, n)
            if not (n.endswith(".zip") and n.startswith(stem) and os.path.isfile(p)):
                continue
            out.append({"file": n, "size": os.path.getsize(p), "time": os.path.getmtime(p),
                        "safety": "_pre-restore_" in n})
        out.sort(key=lambda b: b["time"], reverse=True)
        return out

    # ---------------------------------------------------------------- restoring
    def check_zip(self, data):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            m = json.loads(z.read("manifest.json"))
        except Exception:
            raise RuntimeError("That isn't a backup made by this tool.")
        if m.get("addon") != self.slug:
            raise RuntimeError("That backup is from %s, not %s." % (m.get("name") or m.get("addon"), self.name))
        if m.get("format", 0) > FORMAT:
            raise RuntimeError("That backup was made by a newer version. Update this add-on first.")
        return z, m

    def supervisor(self, method, path, body=None):
        if not self.token:
            return False, "not running under the Supervisor"
        req = urllib.request.Request("http://supervisor" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return 200 <= r.status < 300, ""
        except Exception as e:  # noqa: BLE001 - reported to the page
            detail = ""
            if hasattr(e, "read"):
                try:
                    detail = json.loads(e.read()).get("message") or ""
                except Exception:
                    pass
            return False, detail or str(e)

    def restore(self, data):
        """Queue a restore and restart. Returns a message for the page."""
        z, m = self.check_zip(data)
        try:
            self.backup_now("pre-restore")
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("Could not save a safety copy first, so nothing was changed: %s" % e)
        notes = []
        try:
            opts = json.loads(z.read("options.json"))
        except Exception:
            opts = None
        if isinstance(opts, dict) and opts:
            ok, err = self.supervisor("POST", "/addons/self/options", {"options": opts})
            notes.append("Configuration tab settings restored." if ok else
                         "Configuration tab settings were not restored (%s). Set them by hand if they changed." % err)
        with open(self.pending + ".tmp", "wb") as f:
            f.write(data)
        os.replace(self.pending + ".tmp", self.pending)
        ok, err = self.supervisor("POST", "/addons/self/restart")
        if ok:
            notes.append("The add-on is restarting to finish. Refresh this page in a minute.")
        else:
            notes.append("Restart the add-on (or container) to finish the restore.")
        _log("Restore of a backup from %s queued" % m.get("created"))
        return " ".join(notes)

    def apply_pending(self):
        """On start, before the add-on reads its files: unpack a queued restore."""
        if not os.path.isfile(self.pending):
            return None
        try:
            with open(self.pending, "rb") as f:
                z, m = self.check_zip(f.read())
            current = {k: (p, mode, skip) for k, p, mode, skip in self.resolved_paths()}
            for key, info in (m.get("paths") or {}).items():
                if key not in current:
                    continue
                dest, mode, skip = current[key]
                prefix = "files/%s/" % key
                names = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")]
                if info.get("file"):
                    if names:
                        os.makedirs(os.path.dirname(dest) or "/", exist_ok=True)
                        with open(dest, "wb") as o:
                            o.write(z.read(names[0]))
                    continue
                if mode == "replace" and os.path.isdir(dest):
                    for n in os.listdir(dest):
                        if n in ("options.json", PENDING_NAME) or self._skip(n, skip):
                            continue  # left out of backups on purpose (caches, models): keep them
                        p = os.path.join(dest, n)
                        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
                for n in names:
                    rel = n[len(prefix):]
                    out = os.path.normpath(os.path.join(dest, rel))
                    if not out.startswith(os.path.normpath(dest) + os.sep) or os.path.basename(out) == "options.json":
                        continue  # never write outside the folder, never over the Supervisor's options file
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with open(out, "wb") as o:
                        o.write(z.read(n))
            _log("Restored the backup from %s" % m.get("created"))
            return m.get("created")
        except Exception as e:  # noqa: BLE001 - never stop the add-on from starting
            _log("Restore failed: %s" % e)
            self.last_error = "The last restore failed: %s" % e
            return None
        finally:
            try:
                os.remove(self.pending)
            except OSError:
                pass

    # ---------------------------------------------------------------- schedule
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        listen_stdin(self._backup_from_ha)
        folder, _, problem = self.target()
        _log("Backups: %s, every %s, keep %d" % (problem or folder, self.opts.get("backup_every") or "daily", self.keep()))

    def _backup_from_ha(self):
        try:
            self.backup_now()
        except Exception as e:  # noqa: BLE001
            self.last_error = "The backup Home Assistant asked for failed: %s" % e
            raise

    def _loop(self):
        time.sleep(300)  # let the add-on settle after a start
        while True:
            try:
                every = self.every()
                if every:
                    newest = next((b for b in self.list() if not b["safety"]), None)
                    if not newest or time.time() - newest["time"] >= every - 600:
                        self.backup_now()
            except Exception as e:  # noqa: BLE001
                self.last_error = "The last automatic backup failed: %s" % e
                _log(self.last_error)
            time.sleep(1800)

    # ---------------------------------------------------------------- web page
    def handle(self, method, sub, query=None, body=b"", remote=None):
        """Route a request under /backups. sub is the rest of the path ("" for the page), remote the caller's IP.
        Returns (status, content type, bytes, extra headers). Only Home Assistant's sidebar (ingress) may use it:
        backups hold the add-on's settings, so they must never be reachable on an add-on's own open port."""
        query = query or {}
        sub = sub.strip("/")
        if remote not in INGRESS and not os.environ.get("ADDON_BACKUP_DEV"):
            return 403, "text/plain", b"Backups are only available from the Home Assistant sidebar.", {}

        def js(obj, status=200):
            return status, "application/json", json.dumps(obj).encode(), {}
        try:
            if sub == "" and method == "GET":
                return 200, "text/html; charset=utf-8", PAGE.replace("{{NAME}}", self.name).encode(), {"Cache-Control": "no-store"}
            if sub == "api/info":
                folder, single, problem = self.target()
                return js({"name": self.name, "folder": folder, "single": single, "problem": problem,
                           "every": self.opts.get("backup_every") or "daily", "keep": self.keep(),
                           "backups": self.list(), "error": self.last_error, "restored": self.restored,
                           "covers": [p for _, p, _, _ in self.resolved_paths()] + ["Configuration tab settings"]})
            if sub == "api/now" and method == "POST":
                path, m = self.backup_now()
                return js({"ok": True, "file": os.path.basename(path), "skipped": m["skipped"]})
            if sub in ("api/download", "api/restore", "api/delete"):
                name = str(query.get("file") or "")
                if sub != "api/download":
                    try:
                        name = str(json.loads(body or b"{}").get("file") or "")
                    except ValueError:
                        name = ""
                folder, _, problem = self.target()
                if problem or not any(b["file"] == name for b in self.list()):
                    return js({"ok": False, "error": "That backup isn't there any more."}, 404)
                path = os.path.join(folder, name)
                if sub == "api/download":
                    with open(path, "rb") as f:
                        return 200, "application/zip", f.read(), {"Content-Disposition": 'attachment; filename="%s"' % name}
                if sub == "api/delete":
                    os.remove(path)
                    return js({"ok": True})
                with open(path, "rb") as f:
                    return js({"ok": True, "message": self.restore(f.read())})
            if sub == "api/upload" and method == "POST":
                if not body:
                    return js({"ok": False, "error": "No file was sent."}, 400)
                return js({"ok": True, "message": self.restore(body)})
            return js({"ok": False, "error": "Not found"}, 404)
        except RuntimeError as e:
            return js({"ok": False, "error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            _log("Error: %s" % e)
            return js({"ok": False, "error": str(e)}, 500)


PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{NAME}} backups</title><style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,Roboto,sans-serif;background:#111318;color:#e6e6ef;margin:0;padding:16px}
.wrap{max-width:680px;margin:auto}h1{font-size:22px;margin:4px 0}a{color:#9fb0ff}
.card{background:#1b1e27;border:1px solid #2a2e3b;border-radius:14px;padding:16px;margin:14px 0}
.mut{color:#9a9fb5;font-size:13px}button{background:#5b6cff;color:#fff;border:0;border-radius:10px;padding:11px 14px;font-size:15px;cursor:pointer}
button.alt{background:#2a2e3b}button.red{background:#7f1d1d}button.sm{padding:6px 10px;font-size:13px}button:disabled{opacity:.5}
.b{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid #2a2e3b;flex-wrap:wrap}
.b:last-child{border:0}.row{display:flex;gap:6px;flex-wrap:wrap}.note{background:#232845;border-radius:10px;padding:10px 12px;font-size:14px;margin-top:10px}
.bad{background:#451a1a}code{background:#232634;padding:1px 5px;border-radius:5px;font-size:12px;word-break:break-all}
</style><!-- ha-mobile v1.0.0: copied from .shared/ha-mobile.css, edit it there -->
<style id="ha-mobile">
/* HA Mobile v1.0.0
 * Shared phone fixes for every add-on page, tuned for the Home Assistant iPhone app.
 * Copied into each page by .shared/sync_mobile.py: edit it here, then run .shared/sync.sh.
 * Rules use :where() (no specificity), so a page's own styles always win; only the
 * font-size rule that stops iOS zooming into text fields is forced.
 */
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
:where(body){overflow-wrap:break-word} /* long words and error text wrap instead of widening the page */
:where(img,video,canvas){max-width:100%}
:where(img,video){height:auto}
:where(pre){max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
:where(code,a,td,th,li,p){overflow-wrap:anywhere}
:where(table){max-width:100%}
@media (max-width:760px){
  /* iOS zooms the whole page into any text field under 16px; this stops it */
  input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file]):not([type=button]):not([type=submit]),
  select,textarea{font-size:16px!important}
  :where(body){overflow-x:hidden}
  /* wide tables scroll sideways instead of stretching the page */
  :where(table){display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
  /* rows of tabs scroll sideways instead of getting cut off */
  :where(.tabs,.subtabs,.seg,[role=tablist]){flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;max-width:100%}
  :where(.tabs,.subtabs,.seg,[role=tablist])::-webkit-scrollbar{display:none}
  :where(.tabs,.subtabs,.seg,[role=tablist])>*{flex-shrink:0}
  :where(dialog,.modal,.dialog,.sheet){max-width:calc(100vw - 16px)}
}
@media (pointer:coarse){
  /* finger-sized targets (Apple's guideline is 44pt) */
  :where(button,.btn,[role=tab],[role=button],select,summary){min-height:40px}
  :where(input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file])){min-height:40px}
  :where(input[type=checkbox],input[type=radio]){width:20px;height:20px}
  :where(input[type=range]){min-height:32px}
  :where(a[href="backups"]){display:inline-block;padding:10px 12px} /* the Backups link at the bottom of each page */
  :where(a,button,summary,label,[role=button]){-webkit-tap-highlight-color:transparent;touch-action:manipulation}
}
</style>
<!-- /ha-mobile -->
</head><body>
<!-- ha-theme v1.3.0: copied from .shared/ha-theme.js, edit it there -->
<script>
window.__hbAddon = "zone_creator";
/* HA Theme Bridge v1.3.0
 * Makes an add-on web UI follow the active Home Assistant theme (colors, dark/light,
 * dashboard wallpaper, glass blur, card corners and shadows) and updates live when
 * the theme changes. It reads the theme from the Home Assistant page that holds the
 * add-on (ingress runs on the same origin) and remaps this page's own colors to it.
 * Opened outside Home Assistant it does nothing, so the page keeps its own look.
 * Wallpaper, first match wins: the add-on's own "wallpaper" option (Configuration tab), then the
 * shared add-on wallpaper picked in Photo Hub (/local/addon-wallpaper/wallpaper.json), then the theme's.
 * The add-on option:
 *   empty = use the theme's wallpaper, "none" = no wallpaper, or an image:
 *   /local/pic.jpg (= /config/www/pic.jpg), just pic.jpg, /config/www/..., or https://...
 * Readability: over a wallpaper it measures the picture's bright and dark areas and dims (dark
 * themes) or lightens (light themes) it just enough for text to reach a 4.5:1 contrast.
 * Opt out on a page: <html data-ha-theme-off>
 * Variables you can use in new pages: --hb-bg --hb-card --hb-text --hb-text2 --hb-line
 * --hb-primary --hb-accent --hb-on --hb-error --hb-warning --hb-success --hb-field,
 * plus every core HA variable (--primary-color, --card-background-color, ...).
 */
(function () {
  'use strict';
  if (window.__haThemeBridge) return;
  window.__haThemeBridge = 1;
  var doc = document, root = doc.documentElement;
  if (root.hasAttribute('data-ha-theme-off')) return;

  /* ---------- find the Home Assistant window above us ---------- */
  var HA = null;
  try {
    var w = window;
    while (w.parent && w.parent !== w) {
      w = w.parent;
      if (w.document && w.document.querySelector('home-assistant')) HA = w;
    }
  } catch (e) { /* cross-origin parent: stop climbing */ }
  if (!HA) return;
  var nested = window.parent !== HA;

  /* ---------- color helpers ---------- */
  function parse(c) {
    if (!c) return null;
    c = String(c).trim().toLowerCase();
    var m;
    if (c.charAt(0) === '#') {
      var h = c.slice(1);
      if (!/^[0-9a-f]+$/.test(h)) return null;
      if (h.length === 3 || h.length === 4) h = h.replace(/./g, '$&$&');
      if (h.length !== 6 && h.length !== 8) return null;
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16),
        h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1];
    }
    if ((m = c.match(/^rgba?\(([^)]+)\)$/))) {
      var p = m[1].split(/[\s,\/]+/).filter(Boolean);
      if (p.length < 3) return null;
      var f = function (v, alpha) {
        return /%$/.test(v) ? parseFloat(v) * (alpha ? 0.01 : 2.55) : parseFloat(v);
      };
      var out = [f(p[0]), f(p[1]), f(p[2]), p.length > 3 ? f(p[3], 1) : 1];
      for (var i = 0; i < 4; i++) if (isNaN(out[i])) return null;
      return out;
    }
    if (c === 'white') return [255, 255, 255, 1];
    if (c === 'black') return [0, 0, 0, 1];
    if (c === 'transparent') return [0, 0, 0, 0];
    return null;
  }
  function info(c) {
    var r = c[0] / 255, g = c[1] / 255, b = c[2] / 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), ch = mx - mn, h = 0;
    if (ch) {
      if (mx === r) h = ((g - b) / ch) % 6;
      else if (mx === g) h = (b - r) / ch + 2;
      else h = (r - g) / ch + 4;
      h *= 60;
      if (h < 0) h += 360;
    }
    return { l: (mx + mn) / 2, ch: ch, h: h, a: c[3] };
  }
  /* greys, plus the dark navy/indigo shades many dark UIs use as their "grey" */
  function isNeutral(i) {
    return i.ch < 0.12 || (i.ch < 0.2 && i.h >= 200 && i.h <= 290 && (i.l < 0.32 || i.l > 0.85));
  }
  function lum(c) { return c ? (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255 : 0; }
  function rgbStr(c) { return Math.round(c[0]) + ',' + Math.round(c[1]) + ',' + Math.round(c[2]); }
  function hueRole(h) {
    return (h < 15 || h >= 335) ? 'error' : h < 65 ? 'warning' : h < 170 ? 'success' : 'primary';
  }
  function tint(role, a) { return 'rgba(var(--hb-' + role + '-rgb),' + (Math.round(a * 1000) / 1000) + ')'; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  var probe = null;
  function toRGB(v) {
    v = (v || '').trim();
    if (!v) return null;
    var p = parse(v);
    if (p) return p;
    if (!probe) {
      probe = doc.createElement('i');
      probe.style.display = 'none';
      (doc.body || root).appendChild(probe);
    }
    probe.style.color = '';
    probe.style.color = v;
    if (!probe.style.color) return null;
    return parse(getComputedStyle(probe).color);
  }

  /* ---------- what the page looked like before we touched it ---------- */
  var REFS = { dark: { b: 0.08, t: 0.92 }, light: { b: 0.96, t: 0.12 } };
  var designScheme = 'dark';
  (function measure() {
    var el = doc.body || root, cs = getComputedStyle(el);
    var txt = parse(cs.color), bg = parse(cs.backgroundColor);
    if (!bg || bg[3] < 0.5) bg = parse(getComputedStyle(root).backgroundColor);
    if (txt) designScheme = info(txt).l > 0.5 ? 'dark' : 'light';
    else if (bg && bg[3] > 0.5) designScheme = info(bg).l < 0.5 ? 'dark' : 'light';
    var ref = REFS[designScheme];
    if (txt) ref.t = info(txt).l;
    if (bg && bg[3] > 0.5 && Math.abs(info(bg).l - ref.t) > 0.3) ref.b = info(bg).l;
  })();

  /* ---------- color rewriting rules ---------- */
  var COLOR_RE = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b/g;
  var cardVars = {}, solidVars = {}, pageVars = {};

  function lastCompound(sel) {
    return (sel || '').split(',').map(function (s) {
      var parts = s.trim().split(/\s*[\s>+~]\s*/);
      return parts[parts.length - 1] || '';
    });
  }
  function kindOf(sel) {
    var lasts = lastCompound(sel), k = '';
    for (var i = 0; i < lasts.length; i++) {
      var s = lasts[i].toLowerCase();
      if (/^(html|body|:root)\b/.test(s)) return 'page';
      if (/\.(overlay|backdrop|scrim|mask|shade|sheet|modal|lightbox)\b|::backdrop/.test(s)) return 'scrim';
      if (/^(input|select|textarea)\b|\.(input|field-input|textfield)\b/.test(s)) k = k || 'input';
      else if (/^(header|nav|footer)\b|\.(top|topbar|nav|navbar|header|footer|bar|toolbar|appbar|bottom|tabbar|savebar)\b/.test(s)) k = k || 'bar';
      else if (/\.(card|panel|surface|sheet|modal|dialog|popup|menu|toast|drawer|pane|tile)\b|^(dialog|details)\b/.test(s)) k = k || 'card';
    }
    return k;
  }
  function ctxOf(p) {
    if (/^background(-color|-image)?$/.test(p)) return 'bg';
    if (p === 'color' || p === 'caret-color' || p === '-webkit-text-fill-color' || p === 'text-decoration-color') return 'text';
    if (/^border(-(top|right|bottom|left|block|inline)(-(start|end))?)?-color$/.test(p) || p === 'outline-color' || p === 'column-rule-color') return 'line';
    if (p === 'accent-color') return 'accent';
    return '';
  }

  /* returns {v, solid, card} or null to leave the color alone */
  function mapColor(c, ctx, ref, kind) {
    var i = info(c), a = i.a, dark = ref.b < 0.5;
    if (a === 0) return null;
    var span = ref.t - ref.b, t = span ? (i.l - ref.b) / span : 0, at = Math.abs(t);
    var neutral = isNeutral(i) || (ctx === 'line' && i.ch < 0.26 && (dark ? i.l < 0.45 : i.l > 0.6));
    if (neutral) {
      if (a < 0.98) {
        if (t > 0.5) return { v: tint('text', a) };            /* light-on-dark wash -> text tint */
        if (ctx !== 'bg' || kind === 'scrim') return null;     /* overlays and shadows stay */
        if (i.l < 0.05 && a < 0.5) return { v: 'var(--hb-inset)' };  /* black wash = inset box */
        if (i.l < 0.05) return null;
        if (kind === 'bar' || a > 0.8) return { v: 'var(--hb-bar)', card: true };
        if (kind === 'card' || a > 0.4) return { v: 'var(--hb-card)', card: true };
        return { v: 'var(--hb-inset)' };
      }
      if (ctx === 'text') return { v: t > 0.72 ? 'var(--hb-text)' : 'var(--hb-text2)' };
      if (ctx === 'line') return { v: 'var(--hb-line)' };
      if (ctx === 'accent') return { v: 'var(--hb-primary)' };
      if (kind === 'page') return { v: 'var(--hb-bg)' };
      if (kind === 'input') return { v: 'var(--hb-field)' };
      if (kind === 'bar') return { v: 'var(--hb-bar)', card: true };
      if (kind === 'card' && t < 0.45) return { v: 'var(--hb-card)', card: true };
      if (at < 0.04) return { v: 'var(--hb-inset)' };
      if (t > 0.6) return null;                                 /* bright chip on dark page: leave */
      return { v: tint('text', clamp(0.03 + at * 0.4, 0.05, 0.16)) };
    }
    var role = hueRole(i.h);
    if (a < 0.98) return { v: tint(role, a) };
    if (ctx === 'bg') {
      if (dark ? i.l < 0.3 : i.l > 0.82) return { v: tint(role, 0.2) };   /* tinted note/chip bg */
      return { v: 'var(--hb-' + role + ')', solid: true };
    }
    return { v: 'var(--hb-' + role + ')' };
  }

  var SEM_NAMES = [
    [/^(ok|good|success|live|green|pos|positive)(-?\d)?$/, 'success'],
    [/^(bad|red|danger|err|error|neg|negative)(-?\d)?$/, 'error'],
    [/^(warn|warning|amber)(-?\d)?$/, 'warning'],
    [/^(acc|accent|ac|primary|brand|link)$/, 'primary'],
    [/^(acc|accent|ac|primary)-?2$/, 'accent']
  ];
  function mapVar(name, val, ref) {
    var n = name.slice(2).toLowerCase();
    if (/^hb-/.test(n)) return null;
    var c = parse(val);
    if (!c) return null;
    var i = info(c), neutral = isNeutral(i), dark = ref.b < 0.5;
    var span = ref.t - ref.b, t = span ? (i.l - ref.b) / span : 0, at = Math.abs(t);
    if (n === 'on' || /^(acc|accent|ac|primary)-?(ink|on|fg|text)$|^on-(acc|accent|primary)$/.test(n)) return { v: 'var(--hb-on)' };
    var soft = /(-|^)(soft|tint|wash|bg|bg2|weak)$|soft$/.test(n), base = n.replace(/-?(soft|tint|wash|bg|bg2|weak|ink)$|soft$/, '');
    for (var k = 0; k < SEM_NAMES.length; k++) {
      if (SEM_NAMES[k][0].test(base) && (!neutral || base !== n)) {
        var role = SEM_NAMES[k][1];
        if (/-ink$/.test(n)) return { v: 'var(--hb-text)' };
        if (soft || i.a < 0.98) return { v: tint(role === 'accent' ? 'primary' : role, i.a < 0.98 ? i.a : 0.16) };
        return { v: 'var(--hb-' + role + ')', solid: true };
      }
    }
    if (/-ink$/.test(n)) return { v: 'var(--hb-text)' };
    if (!neutral) return null;                                 /* unknown colorful var (state colors): leave */
    if (i.a < 0.98) return t > 0.5 ? { v: tint('text', i.a) } : null;
    if (/line|border|sep|divid|rule|stroke|outline/.test(n)) return { v: 'var(--hb-line)' };
    if (/^(mut|muted|dim|mu|sub|sec|secondary|faint|hint|txt2|text2|tx2|ink2|subtle)(-?\d)?$/.test(n)) return { v: 'var(--hb-text2)' };
    if (/^(text|txt|tx|fg|fore|ink|c|font-color|text-color)(-?\d)?$/.test(n) && t > 0.3) return { v: t > 0.72 ? 'var(--hb-text)' : 'var(--hb-text2)' };
    if (/field|input|code|well/.test(n)) return { v: 'var(--hb-field)' };
    if (/chip|card-?2|panel-?2|surface-?2|bg-?3|raised|hover|alt|elev/.test(n)) return { v: tint('text', dark ? 0.08 : 0.06) };
    if (/card|panel|surface|sheet|tile|box|pane/.test(n)) return { v: 'var(--hb-card)', card: true };
    if (/^(bg|bg-?[0-2]|background|base|page|canvas|app-bg|ink)$/.test(n) || at < 0.04) return { v: 'var(--hb-bg)' };
    if (t > 0.72) return { v: 'var(--hb-text)' };
    if (t > 0.4) return { v: 'var(--hb-text2)' };
    return { v: tint('text', clamp(0.03 + at * 0.4, 0.05, 0.14)) };
  }

  function refVarNames(v) {
    var out = [], re = /var\(\s*(--[\w-]+)/g, m;
    while ((m = re.exec(v || ''))) out.push(m[1]);
    return out;
  }

  function doStyle(st, sel, scheme) {
    var ref = REFS[scheme], kind = kindOf(sel), names = [], k;
    for (k = 0; k < st.length; k++) names.push(st[k]);
    var solidBg = false, isCard = false;
    names.forEach(function (p) {
      var v = st.getPropertyValue(p), pr = st.getPropertyPriority(p);
      if (p.indexOf('--') === 0) {
        var r = mapVar(p, v, ref);
        pageVars[p] = 1;
        if (r) {
          if (r.card) cardVars[p] = 1;
          if (r.solid) solidVars[p] = 1;
          st.setProperty(p, r.v, pr);
        }
        return;
      }
      var ctx = ctxOf(p);
      if (!ctx || !v) return;
      var nv = v.replace(COLOR_RE, function (tok) {
        var c = parse(tok);
        if (!c) return tok;
        var r = mapColor(c, ctx, ref, kind);
        if (!r) return tok;
        if (ctx === 'bg' && r.solid) solidBg = true;
        if (ctx === 'bg' && r.card) isCard = true;
        return r.v;
      });
      if (nv !== v) st.setProperty(p, nv, pr);
    });
    /* shorthands that mix var() with literal colors only show up on the shorthand itself */
    ['background', 'border', 'border-top', 'border-right', 'border-bottom', 'border-left', 'outline'].forEach(function (p) {
      var v = st.getPropertyValue(p);
      if (!v || v.indexOf('var(') < 0) return;
      var ctx = p === 'background' ? 'bg' : 'line', pr = st.getPropertyPriority(p);
      var nv = v.replace(COLOR_RE, function (tok) {
        var c = parse(tok), r = c && mapColor(c, ctx, REFS[scheme], kind);
        if (!r) return tok;
        if (ctx === 'bg' && r.card) isCard = true;
        return r.v;
      });
      if (nv !== v) st.setProperty(p, nv, pr);
    });
    /* backgrounds written as var(--card) / var(--accent) */
    ['background', 'background-color', 'background-image'].forEach(function (p) {
      refVarNames(st.getPropertyValue(p)).forEach(function (n) {
        if (cardVars[n]) isCard = true;
        if (solidVars[n]) solidBg = true;
      });
    });
    if (solidBg) {
      var col = st.getPropertyValue('color');
      if (!col || /var\(--hb-text2?\)/.test(col) || refVarNames(col).some(function (n) {
        return /^--(text|txt|tx|ink|fg|c)$/.test(n);
      })) st.setProperty('color', 'var(--hb-on)');
    }
    if (isCard && kind !== 'page') {
      st.setProperty('-webkit-backdrop-filter', 'var(--hb-blur)');
      st.setProperty('backdrop-filter', 'var(--hb-blur)');
      ['top-left', 'top-right', 'bottom-right', 'bottom-left'].forEach(function (c) {
        var p = 'border-' + c + '-radius', v = st.getPropertyValue(p);
        if (v && v.indexOf('--hb-radius') < 0) st.setProperty(p, 'var(--hb-radius,' + v + ')');
      });
      var sh = st.getPropertyValue('box-shadow');
      if (sh.indexOf('--hb-shadow') < 0) st.setProperty('box-shadow', 'var(--hb-shadow,' + (sh || 'none') + ')');
      ['top', 'right', 'bottom', 'left'].forEach(function (s) {
        var p = 'border-' + s + '-color', v = st.getPropertyValue(p);
        if (v === 'var(--hb-line)') st.setProperty(p, 'var(--hb-card-border,var(--hb-line))');
        var pw = 'border-' + s + '-width', w = st.getPropertyValue(pw);
        if (w && w.indexOf('--hb-') < 0) st.setProperty(pw, 'var(--hb-card-border-width,' + w + ')');
      });
    }
  }

  function schemeOfMedia(text, fallback) {
    var m = /prefers-color-scheme\s*:\s*(dark|light)/.exec(text || '');
    return m ? m[1] : fallback;
  }
  function walk(rules, scheme) {
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i];
      if (r.style && r.selectorText != null) {
        doStyle(r.style, r.selectorText, scheme);
        if (r.cssRules && r.cssRules.length) walk(r.cssRules, scheme);
      } else if (r.cssRules && !(r.type === 7)) {           /* media / supports / layer / container */
        walk(r.cssRules, r.media ? schemeOfMedia(r.media.mediaText, scheme) : scheme);
      }
    }
  }
  var done = typeof WeakSet === 'function' ? new WeakSet() : null, doneList = [];
  function seen(s) {
    if (done) { if (done.has(s)) return true; done.add(s); return false; }
    if (doneList.indexOf(s) >= 0) return true; doneList.push(s); return false;
  }
  function baseScheme(rules) {
    var dark = false, light = false;
    (function scan(rs) {
      for (var i = 0; i < rs.length; i++) {
        var r = rs[i];
        if (r.media) {
          var s = schemeOfMedia(r.media.mediaText, '');
          if (s === 'dark') dark = true;
          if (s === 'light') light = true;
        }
      }
    })(rules);
    if (dark && !light) return 'light';
    if (light && !dark) return 'dark';
    return designScheme;
  }
  function processSheets() {
    for (var i = 0; i < doc.styleSheets.length; i++) {
      var s = doc.styleSheets[i], rules;
      if (s.ownerNode && s.ownerNode.id === 'hb-style') continue;
      try { rules = s.cssRules; } catch (e) { continue; }   /* other-origin CSS (CDN): skip */
      if (!rules || seen(s)) continue;
      walk(rules, baseScheme(rules));
    }
  }

  /* ---------- read the HA theme and publish it as variables ---------- */
  var CORE = ['primary-color', 'dark-primary-color', 'light-primary-color', 'accent-color', 'text-primary-color',
    'primary-text-color', 'secondary-text-color', 'disabled-text-color', 'text-light-primary-color',
    'primary-background-color', 'secondary-background-color', 'card-background-color', 'ha-card-background',
    'divider-color', 'error-color', 'warning-color', 'success-color', 'info-color', 'state-icon-color',
    'paper-item-icon-color', 'sidebar-background-color', 'sidebar-text-color', 'app-header-background-color',
    'app-header-text-color', 'ha-card-border-radius', 'ha-card-box-shadow', 'ha-card-border-color',
    'ha-card-border-width', 'primary-font-family', 'paper-font-body1_-_font-family', 'lovelace-background',
    'input-fill-color', 'mdc-theme-primary', 'switch-checked-color', 'table-row-background-color',
    'table-row-alternative-background-color', 'code-editor-background-color', 'markdown-code-background-color'];
  var BLUR_VARS = ['ha-card-backdrop-filter', 'card-backdrop-filter', 'ha-card-backdrop', 'backdrop-filter',
    'glass-blur', 'ha-blur', 'blur', 'card-blur', 'ha-card-blur'];
  var MOD_VARS = ['card-mod-card', 'card-mod-card-yaml', 'card-mod-root', 'card-mod-view', 'card-mod-row'];
  var lastKey = '', copied = {}, wallOverride = null;   /* null = no add-on option set */
  var globalWall = null;                               /* null = no shared wallpaper from Photo Hub */

  function themeSource() {
    var d = HA.document;
    return d.querySelector('home-assistant') || d.documentElement;
  }
  function readTheme() {
    var cs = HA.getComputedStyle(themeSource());
    var g = function (n) { return (cs.getPropertyValue('--' + n) || '').trim(); };
    var th = { vars: {} };
    var names = CORE.slice(), i, st = HA.document.documentElement.style;
    for (i = 0; i < st.length; i++) if (st[i].indexOf('--') === 0) names.push(st[i].slice(2));
    for (i = 0; i < cs.length; i++) if (cs[i].indexOf('--') === 0 && names.length < 900) names.push(cs[i].slice(2));
    names.forEach(function (n) {
      var v = g(n);
      if (v && v.length < 400) th.vars['--' + n] = v;
    });
    var blur = '';
    for (i = 0; i < BLUR_VARS.length && !blur; i++) blur = g(BLUR_VARS[i]);
    for (i = 0; i < MOD_VARS.length && !blur; i++) {
      var m = /backdrop-filter\s*:\s*([^;}!\n]+)/i.exec(g(MOD_VARS[i]));
      if (m) blur = m[1].trim();
    }
    if (/^[\d.]+(px|rem|em)$/.test(blur)) blur = 'blur(' + blur + ')';
    if (/var\(/.test(blur)) blur = '';
    th.blur = blur;
    th.bg = toRGB(g('primary-background-color')) || [17, 17, 17, 1];
    th.bg2 = toRGB(g('secondary-background-color')) || th.bg;
    th.text = toRGB(g('primary-text-color')) || (lum(th.bg) < 0.5 ? [225, 225, 225, 1] : [33, 33, 33, 1]);
    th.text2 = toRGB(g('secondary-text-color')) || th.text;
    th.cardRaw = g('ha-card-background') || g('card-background-color');
    th.card = toRGB(th.cardRaw) || th.bg2;
    th.line = g('divider-color') || 'rgba(' + rgbStr(th.text) + ',.12)';
    th.primary = toRGB(g('primary-color')) || [3, 169, 244, 1];
    th.accent = toRGB(g('accent-color')) || th.primary;
    th.on = toRGB(g('text-primary-color')) || [255, 255, 255, 1];
    th.error = toRGB(g('error-color')) || [219, 68, 55, 1];
    th.warning = toRGB(g('warning-color')) || [255, 166, 0, 1];
    th.success = toRGB(g('success-color')) || [67, 160, 71, 1];
    th.info = toRGB(g('info-color')) || [3, 155, 229, 1];
    th.wall = g('lovelace-background');
    if (th.wall && !/url\(|gradient\(/.test(th.wall) && !toRGB(th.wall)) th.wall = '';
    if (wallOverride !== null) th.wall = wallOverride;
    else if (globalWall !== null) th.wall = globalWall;
    th.radius = g('ha-card-border-radius');
    th.shadow = g('ha-card-box-shadow');
    th.cardBorder = g('ha-card-border-color');
    th.cardBorderW = g('ha-card-border-width');
    th.dark = th.wall ? lum(th.text) > 0.5 : lum(th.bg) < 0.5;
    return th;
  }

  function set(n, v) {
    if (v == null || v === '') root.style.removeProperty(n);
    else root.style.setProperty(n, v);
  }
  function css(c) {
    return c[3] < 1 ? 'rgba(' + rgbStr(c) + ',' + (Math.round(c[3] * 1000) / 1000) + ')' : 'rgb(' + rgbStr(c) + ')';
  }

  /* ---------- wallpaper readability ---------- */
  var dimCache = {};           /* wallpaper url -> {dark: alpha, light: alpha} */
  function lin(v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
  function relLum(c) { return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]); }
  function contrast(a, b) { return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); }
  function wallUrl(w) { var m = /url\(\s*["']?([^"')]+)["']?\s*\)/.exec(w || ''); return m ? m[1] : ''; }
  /* smallest overlay alpha so text over the worst part of the picture still reads */
  function needed(stats, th) {
    /* browsers mix a see-through layer in screen (sRGB) values, so blend those, then measure */
    var out = 0.12, bg = th.bg;
    [[th.text, 4.5], [th.text2, 3.2]].forEach(function (t) {
      var tl = relLum(t[0]), worst = tl > 0.5 ? stats.hi : stats.lo;
      for (var a = 0.12; a <= 0.85; a += 0.02) {
        var mix = [0, 1, 2].map(function (i) { return a * bg[i] + (1 - a) * worst[i]; });
        if (contrast(tl, relLum(mix)) >= t[1]) { out = Math.max(out, a); return; }
      }
      out = Math.max(out, 0.85);
    });
    return Math.round(out * 100) / 100;
  }
  function measure(url, th) {
    if (dimCache[url] || !window.Image) return;
    dimCache[url] = { pending: true };
    var img = new Image();
    if (/^https?:/.test(url) && url.indexOf(location.origin) !== 0) img.crossOrigin = 'anonymous';
    img.onload = function () {
      try {
        var cv = doc.createElement('canvas'), n = 48;
        cv.width = cv.height = n;
        var cx = cv.getContext('2d');
        cx.drawImage(img, 0, 0, n, n);
        var px = cx.getImageData(0, 0, n, n).data, ls = [];
        for (var i = 0; i < px.length; i += 4) {
          var c = [px[i], px[i + 1], px[i + 2]];
          ls.push({ l: relLum(c), c: c });
        }
        ls.sort(function (a, b) { return a.l - b.l; });
        /* 5% darkest / brightest areas: what text over the busiest part of the picture sits on */
        dimCache[url] = { lo: ls[Math.floor(ls.length * 0.05)].c, hi: ls[Math.floor(ls.length * 0.95)].c };
      } catch (e) { dimCache[url] = { failed: true }; }  /* other site without CORS: use a safe default */
      lastKey = ''; apply();
    };
    img.onerror = function () { dimCache[url] = { failed: true }; };
    img.src = url;
  }
  function dimFor(th) {
    var url = wallUrl(th.wall);
    if (!url) return 0;
    var st = dimCache[url];
    if (!st) { measure(url, th); return 0.35; }
    if (st.pending || st.failed) return 0.35;
    return needed(st, th);
  }

  function apply() {
    var th;
    try { th = readTheme(); } catch (e) { return; }
    var key = JSON.stringify(th);
    if (key === lastKey) return;
    lastKey = key;

    /* every HA variable, so new pages can just use var(--primary-color) */
    Object.keys(copied).forEach(function (n) { if (!th.vars[n]) root.style.removeProperty(n); });
    copied = {};
    Object.keys(th.vars).forEach(function (n) {
      if (pageVars[n]) return;
      root.style.setProperty(n, th.vars[n]);
      copied[n] = 1;
    });

    var cardSame = Math.abs(lum(th.card) - lum(th.bg)) < 0.01 && th.card[3] > 0.95 && !th.wall;
    set('--hb-bg', th.wall ? 'rgba(' + rgbStr(th.bg) + ',.45)' : css(th.bg));
    set('--hb-bg2', css(th.bg2));
    set('--hb-card', cardSame ? 'rgba(' + rgbStr(th.text) + ',.05)' : (th.cardRaw && !toRGB(th.cardRaw) ? th.cardRaw : css(th.card)));
    set('--hb-text', css(th.text));
    set('--hb-text2', css(th.text2));
    set('--hb-line', th.line);
    set('--hb-primary', css(th.primary));
    set('--hb-accent', css(th.accent));
    set('--hb-on', css(th.on));
    ['error', 'warning', 'success', 'info'].forEach(function (k) { set('--hb-' + k, css(th[k])); });
    ['text', 'bg', 'primary', 'accent', 'error', 'warning', 'success', 'info'].forEach(function (k) {
      set('--hb-' + k + '-rgb', rgbStr(th[k]));
    });
    set('--hb-field', 'rgba(' + rgbStr(th.text) + ',' + (th.dark ? '.07' : '.05') + ')');
    set('--hb-inset', 'rgba(' + rgbStr(th.bg) + ',' + (th.wall ? '.35' : '.6') + ')');
    set('--hb-bar', th.card[3] < 0.95 || th.wall ? 'var(--hb-card)' : 'rgba(' + rgbStr(th.bg) + ',.92)');
    set('--hb-blur', th.blur || 'none');
    set('--hb-radius', th.radius);
    set('--hb-shadow', th.shadow);
    set('--hb-card-border', th.cardBorder);
    set('--hb-card-border-width', th.cardBorderW);
    var dim = th.wall ? dimFor(th) : 0, veil = 'rgba(' + rgbStr(th.bg) + ',' + dim + ')';
    set('--hb-dim', String(dim));
    set('--hb-page', th.wall ? (dim ? 'linear-gradient(' + veil + ',' + veil + ') fixed, ' : '') + th.wall : css(th.bg));
    root.style.setProperty('color-scheme', th.dark ? 'dark' : 'light');
    /* a frame whose page and frame element disagree on color-scheme gets an opaque backdrop; keep them equal */
    try { if (window.frameElement) window.frameElement.style.colorScheme = th.dark ? 'dark' : 'light'; } catch (e) { /* cross-origin */ }
    root.classList.toggle('hb-dark', th.dark);
    root.classList.toggle('hb-light', !th.dark);
    root.classList.toggle('hb-wallpaper', !!th.wall);
    root.classList.toggle('hb-glass', !!th.blur);

    var s = doc.getElementById('hb-style');
    if (!s) {
      s = doc.createElement('style');
      s.id = 'hb-style';
      (doc.head || root).appendChild(s);
    }
    var page = nested && th.wall ? 'transparent' : 'var(--hb-page)';
    s.textContent =
      'html.hb-themed{background:' + page + ' !important;min-height:100%}' +
      'html.hb-themed body{background:transparent !important;color:var(--hb-text)}' +
      (th.wall ? 'html.hb-themed iframe{background:transparent !important}' +
        'html.hb-themed.hb-wallpaper body{text-shadow:0 1px 3px rgba(' + rgbStr(th.bg) + ',.55)}' +
        'html.hb-themed.hb-wallpaper input,html.hb-themed.hb-wallpaper textarea,html.hb-themed.hb-wallpaper select{text-shadow:none}' : '') +
      'html.hb-themed ::placeholder{color:var(--hb-text2);opacity:.8}';
    root.classList.add('hb-themed');
  }

  /* ---------- per add-on wallpaper option ---------- */
  function wallCss(v) {
    v = String(v == null ? '' : v).trim();
    if (!v || /^(theme|default|auto)$/i.test(v)) return null;
    if (/^(none|off|no)$/i.test(v)) return '';
    if (/url\(|gradient\(/.test(v)) return v;
    v = v.replace(/^\/?(config|homeassistant)\/www\//, '/local/').replace(/^www\//, '/local/');
    if (!/^(https?:)?\/\//.test(v) && v.charAt(0) !== '/') v = '/local/' + v;
    return 'center / cover no-repeat fixed url("' + v.replace(/"/g, '%22') + '")';
  }
  function loadWallpaperOption() {
    var m = /^\/api\/hassio_ingress\/[^/]+\//.exec(location.pathname);
    var el = themeSource(), hass = el && el.hass;
    if (!m || !hass || !hass.callWS || !(hass.user && hass.user.is_admin)) return;
    var base = m[0], key = 'hb-addon:' + base, hint = window.__hbAddon || '';
    var call = function (ep) {
      return hass.callWS({ type: 'supervisor/api', endpoint: ep, method: 'get' });
    };
    var ingressOf = function (info) { return String((info && (info.ingress_url || info.ingress_entry)) || ''); };
    var useInfo = function (info) {
      var o = (info && info.options) || {};
      wallOverride = 'wallpaper' in o ? wallCss(o.wallpaper) : null;
      lastKey = '';
      apply();
    };
    var cached = '';
    try { cached = sessionStorage.getItem(key) || ''; } catch (e) {}
    var find = function () {
      return call('/addons').then(function (r) {
        var list = (r && r.addons) || r || [], slugs = list.map(function (a) { return a.slug; });
        if (hint) slugs.sort(function (a, b) {
          var ha = a === hint || a.slice(-hint.length - 1) === '_' + hint, hb = b === hint || b.slice(-hint.length - 1) === '_' + hint;
          return (hb ? 1 : 0) - (ha ? 1 : 0);
        });
        var i = 0;
        var next = function () {
          if (i >= slugs.length || i >= 60) return null;
          var slug = slugs[i++];
          return call('/addons/' + slug + '/info').then(function (info) {
            if (ingressOf(info) && base.indexOf(ingressOf(info).replace(/\/?$/, '/')) === 0) {
              try { sessionStorage.setItem(key, slug); } catch (e) {}
              return info;
            }
            return next();
          }, next);
        };
        return next();
      });
    };
    (cached ? call('/addons/' + cached + '/info').then(function (info) {
      return ingressOf(info) && base.indexOf(ingressOf(info).replace(/\/?$/, '/')) === 0 ? info : find();
    }, find) : find()).then(function (info) { if (info) useInfo(info); }, function () {});
  }

  /* ---------- shared add-on wallpaper (picked in Photo Hub) ---------- */
  function loadGlobalWallpaper() {
    if (!window.fetch) return;
    fetch('/local/addon-wallpaper/wallpaper.json?t=' + Date.now(), { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var next = d && d.url ? wallCss(d.url) : null;
        if (next !== globalWall) { globalWall = next; lastKey = ''; apply(); }
      }, function () {});
  }

  /* ---------- run now, then follow changes ---------- */
  function run() { try { processSheets(); } catch (e) {} apply(); }
  run();
  var tm = null;
  function later() { clearTimeout(tm); tm = setTimeout(run, 120); }
  try {
    var mo = new HA.MutationObserver(later);
    mo.observe(HA.document.documentElement, { attributes: true, attributeFilter: ['style', 'class'] });
    mo.observe(themeSource(), { attributes: true, attributeFilter: ['style', 'class'] });
    if (HA.document.head) mo.observe(HA.document.head, { childList: true, subtree: true, characterData: true });
    var mq = HA.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) mq.addEventListener('change', later); else if (mq.addListener) mq.addListener(later);
  } catch (e) {}
  try {
    new MutationObserver(function (list) {
      for (var i = 0; i < list.length; i++) {
        for (var j = 0; j < list[i].addedNodes.length; j++) {
          var n = list[i].addedNodes[j];
          if (n.id === 'hb-style') continue;
          if (n.tagName === 'STYLE') later();
          if (n.tagName === 'LINK') n.addEventListener('load', later);
        }
      }
    }).observe(doc.head || root, { childList: true });
  } catch (e) {}
  doc.addEventListener('visibilitychange', function () { if (!doc.hidden) { later(); loadGlobalWallpaper(); } });
  window.addEventListener('load', later);
  try { loadWallpaperOption(); } catch (e) {}
  try { loadGlobalWallpaper(); } catch (e) {}
  window.haThemeBridge = { refresh: function () { lastKey = ''; run(); }, reloadWallpaper: loadGlobalWallpaper };
})();
</script>
<!-- /ha-theme -->
<div class="wrap">
<div class="row" style="justify-content:space-between;align-items:center"><h1>&#x1F4BE; {{NAME}} backups</h1><a href="./">&larr; Back</a></div>
<div id="msg"></div>
<div class="card"><div id="where" class="mut"></div>
<button id="now" style="width:100%;margin-top:12px">Back up now</button></div>
<div class="card"><b>Backups</b><div id="list"></div></div>
<div class="card"><b>Restore from a file</b><div class="mut" style="margin:6px 0 10px">A backup .zip from this add-on, for example one you downloaded or copied from another Home Assistant.</div>
<input type="file" id="up" accept=".zip,application/zip"></div>
<div class="mut">Restoring first saves a safety copy (named pre-restore), puts back the Configuration tab settings, then restarts the add-on to put the data back. Change the folder, schedule and how many are kept in the add-on's Configuration tab.</div>
</div><script>
const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const say=(t,bad)=>$("#msg").innerHTML=t?`<div class="note ${bad?"bad":""}">${esc(t)}</div>`:"";
async function api(p,o){const r=await fetch("backups/api/"+p,o);let j;try{j=await r.json()}catch(_){j={ok:false,error:"HTTP "+r.status}}return j}
const kb=n=>n>1048576?(n/1048576).toFixed(1)+" MB":Math.max(1,Math.round(n/1024))+" KB";
async function load(){
  const d=await api("info");
  $("#where").innerHTML=d.problem?`<span style="color:#fca5a5">${esc(d.problem)}</span> Fix <code>backup_path</code> in the Configuration tab.`:
    `Saved to <code>${esc(d.single||d.folder)}</code> &middot; automatic: <b>${esc(d.every)}</b>${d.single?" (one file, replaced each time)":", newest "+d.keep+" kept"}<br>Covers: ${d.covers.map(c=>c.startsWith("/")?"<code>"+esc(c)+"</code>":esc(c)).join(", ")}`;
  $("#now").disabled=!!d.problem;
  if(d.error)say(d.error,true);else if(d.restored&&!$("#msg").textContent)say("Restored the backup from "+d.restored+".");
  $("#list").innerHTML=d.backups.map(b=>`<div class="b"><div><div>${new Date(b.time*1000).toLocaleString()}${b.safety?' <span class="mut">(safety copy)</span>':""}</div><div class="mut">${esc(b.file)} &middot; ${kb(b.size)}</div></div>
    <div class="row"><a href="backups/api/download?file=${encodeURIComponent(b.file)}"><button class="alt sm">Download</button></a>
    <button class="sm" data-r="${esc(b.file)}">Restore</button><button class="red sm" data-d="${esc(b.file)}">Delete</button></div></div>`).join("")||'<div class="mut" style="margin-top:8px">None yet.</div>';
}
function twice(b,label,fn){if(b.dataset.armed){fn();return}b.dataset.armed=1;const t=b.textContent;b.textContent=label;setTimeout(()=>{delete b.dataset.armed;b.textContent=t},3500)}
$("#list").onclick=e=>{const b=e.target.closest("button");if(!b)return;
  if(b.dataset.r)twice(b,"Tap again",async()=>{b.disabled=true;say("Restoring...");const r=await api("restore",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({file:b.dataset.r})});say(r.ok?r.message:r.error,!r.ok);load()});
  if(b.dataset.d)twice(b,"Delete?",async()=>{const r=await api("delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({file:b.dataset.d})});if(!r.ok)say(r.error,true);load()});};
$("#now").onclick=async()=>{$("#now").disabled=true;say("Backing up...");const r=await api("now",{method:"POST"});
  say(r.ok?"Saved "+r.file+"."+(r.skipped.length?" Skipped "+r.skipped.length+" file(s) over 50 MB.":""):r.error,!r.ok);$("#now").disabled=false;load()};
$("#up").onchange=async e=>{const f=e.target.files[0];if(!f)return;if(!confirm("Restore "+f.name+"? The add-on restarts."))return;
  say("Uploading and restoring...");const r=await api("upload",{method:"POST",headers:{"Content-Type":"application/zip"},body:f});say(r.ok?r.message:r.error,!r.ok);e.target.value="";load()};
load();
</script></body></html>"""

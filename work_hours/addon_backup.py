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
        folder, _, problem = self.target()
        _log("Backups: %s, every %s, keep %d" % (problem or folder, self.opts.get("backup_every") or "daily", self.keep()))

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
</style></head><body><div class="wrap">
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

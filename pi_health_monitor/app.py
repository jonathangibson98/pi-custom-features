import json, os, time, threading, shutil, socket, http.client, urllib.request
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = "http://supervisor"
INTERVAL = 5
PORT = int(os.environ.get("PORT", "8099"))

# Runs as a Home Assistant add-on when a Supervisor token is present,
# otherwise as a plain Docker / docker compose container.
MODE = "supervisor" if TOKEN else "docker"
DOCKER_HOST = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
DISK_PATH = os.environ.get("DISK_PATH", "/data" if MODE == "supervisor" else "/")
cache = {"ready": False}
prev = {"idle": None, "total": None}

THROTTLE = {
    0: "Under-voltage NOW", 1: "Freq capped NOW", 2: "Throttled NOW", 3: "Soft temp limit NOW",
    16: "Under-voltage since boot", 17: "Freq capped since boot",
    18: "Throttled since boot", 19: "Soft temp limit since boot",
}


def sup(path):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get("data", {})


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=20):
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_path)


def docker_get(path):
    u = urlparse(DOCKER_HOST)
    if u.scheme == "unix":
        conn = UnixHTTPConnection(u.path)
    else:  # tcp://host:port, e.g. a docker-socket-proxy
        conn = http.client.HTTPConnection(u.hostname, u.port or 2375, timeout=20)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        data = r.read()
        if r.status != 200:
            raise RuntimeError(f"docker API {path} -> HTTP {r.status}")
        return json.loads(data)
    finally:
        conn.close()


def docker_row(c):
    try:
        s = docker_get(f"/containers/{c['Id']}/stats?stream=false")
        cpu, pre = s.get("cpu_stats", {}), s.get("precpu_stats", {})
        cpu_d = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get("total_usage", 0)
        sys_d = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
        # share of the whole host's CPU, same scale as the host CPU card
        cpu_pct = 100.0 * cpu_d / sys_d if cpu_d > 0 and sys_d > 0 else 0.0
        ms = s.get("memory_stats", {})
        st = ms.get("stats", {})
        cache = st.get("inactive_file", st.get("total_inactive_file", st.get("cache", 0)))
        mem = max(ms.get("usage", 0) - cache, 0)
        limit = ms.get("limit") or 0
        net = s.get("networks") or {}
        return {
            "name": (c.get("Names") or [c["Id"][:12]])[0].lstrip("/"), "slug": c["Id"][:12],
            "cpu": round(cpu_pct, 1), "mem": mem,
            "mem_pct": round(100 * mem / limit, 1) if limit else 0,
            "rx": sum(n.get("rx_bytes", 0) for n in net.values()),
            "tx": sum(n.get("tx_bytes", 0) for n in net.values()),
        }
    except Exception:
        return None


def docker_rows():
    containers = docker_get("/containers/json")  # running containers only
    with ThreadPoolExecutor(16) as ex:  # each stats call blocks ~1s for its 2nd sample
        return [r for r in ex.map(docker_row, containers) if r]


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default


def cpu_percent():
    v = [int(x) for x in read("/proc/stat").split("\n")[0].split()[1:]]
    idle, total = v[3] + v[4], sum(v)
    pct = 0.0
    if prev["total"] is not None and total > prev["total"]:
        pct = 100.0 * (1 - (idle - prev["idle"]) / (total - prev["total"]))
    prev["idle"], prev["total"] = idle, total
    return round(max(pct, 0), 1)


def meminfo():
    m = {}
    for line in read("/proc/meminfo", "").split("\n"):
        k, _, v = line.partition(":")
        if v:
            m[k] = int(v.split()[0]) * 1024
    used = m.get("MemTotal", 0) - m.get("MemAvailable", 0)
    return {
        "total": m.get("MemTotal", 0), "used": used,
        "pct": round(100 * used / m["MemTotal"], 1) if m.get("MemTotal") else 0,
        "swap_total": m.get("SwapTotal", 0), "swap_used": m.get("SwapTotal", 0) - m.get("SwapFree", 0),
    }


def throttle():
    for p in ("/sys/devices/platform/soc/soc:firmware/get_throttled",
              "/sys/devices/platform/soc/soc:firmware/rpi-hwmon/get_throttled"):
        raw = read(p)
        if raw is not None:
            try:
                val = int(raw, 16)
            except ValueError:
                continue
            return {"available": True, "raw": hex(val), "flags": [t for b, t in THROTTLE.items() if val & (1 << b)]}
    return {"available": False, "raw": None, "flags": []}


def pick(s):
    return {
        "cpu": round(s.get("cpu_percent", 0) or 0, 1),
        "mem": s.get("memory_usage", 0) or 0,
        "mem_pct": round(s.get("memory_percent", 0) or 0, 1),
        "rx": s.get("network_rx", 0) or 0,
        "tx": s.get("network_tx", 0) or 0,
    }


def one(name, slug, path):
    try:
        return {"name": name, "slug": slug, **pick(sup(path))}
    except Exception:
        return None


def collect():
    t = read("/sys/class/thermal/thermal_zone0/temp")
    temp_c = round(int(t) / 1000, 1) if t else None
    freq = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    load = (read("/proc/loadavg", "0 0 0").split()[:3])
    disk = {}
    if MODE == "supervisor":
        try:
            h = sup("/host/info")
            disk = {"total": h.get("disk_total"), "used": h.get("disk_used")}
        except Exception:
            pass
    if not disk.get("total"):
        u = shutil.disk_usage(DISK_PATH)
        disk = {"total": round(u.total / 1e9, 1), "used": round(u.used / 1e9, 1)}
    disk["pct"] = round(100 * disk["used"] / disk["total"], 1) if disk["total"] else 0

    if MODE == "supervisor":
        jobs = [("Home Assistant Core", "core", "/core/stats"), ("Supervisor", "supervisor", "/supervisor/stats")]
        try:
            for a in sup("/addons").get("addons", []):
                if a.get("state") == "started":
                    jobs.append((a["name"], a["slug"], f"/addons/{a['slug']}/stats"))
        except Exception:
            pass
        with ThreadPoolExecutor(6) as ex:
            rows = [r for r in ex.map(lambda j: one(*j), jobs) if r]
    else:
        try:
            rows = docker_rows()
            cache.pop("docker_error", None)
        except Exception as e:  # keep host metrics working without the socket
            rows = []
            cache["docker_error"] = str(e)
    rows.sort(key=lambda r: r["cpu"], reverse=True)

    return {
        "ready": True, "ts": time.time(), "mode": MODE,
        "cpu": cpu_percent(), "cores": os.cpu_count(),
        "freq_mhz": round(int(freq) / 1000) if freq else None,
        "temp_c": temp_c, "temp_f": round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None,
        "load": [float(x) for x in load],
        "uptime": float(read("/proc/uptime", "0").split()[0]),
        "mem": meminfo(), "disk": disk, "throttle": throttle(), "addons": rows,
    }


def sampler():
    while True:
        try:
            cache.update(collect())
            cache.pop("error", None)
        except Exception as e:
            cache["error"] = str(e)
        time.sleep(INTERVAL)


HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pi Health</title><style>
*{box-sizing:border-box}body{margin:0;padding:14px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;
background:linear-gradient(160deg,#0d0d0d,#1a1a2e);color:#eee;min-height:100vh}
h1{font-size:20px;margin:0 0 12px}h2{font-size:15px;margin:18px 0 8px;color:#aaa}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:#ffffff0d;border:1px solid #ffffff14;border-radius:12px;padding:12px}
.lbl{font-size:12px;color:#999}.val{font-size:24px;font-weight:600;margin:2px 0 6px}.sub{font-size:12px;color:#888}
.bar{height:6px;background:#ffffff14;border-radius:3px;overflow:hidden}.bar i{display:block;height:100%}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:#888;font-weight:500;padding:6px 4px}
td{padding:7px 4px;border-top:1px solid #ffffff10}.r{text-align:right}.warn{color:#ffb703}.bad{color:#ff4d6d}.ok{color:#2ec4b6}
.wrap{overflow-x:auto}
</style></head><body>
<!-- ha-theme v1.1.0: copied from .shared/ha-theme.js, edit it there -->
<script>
window.__hbAddon = "pi_health_monitor";
/* HA Theme Bridge v1.1.0
 * Makes an add-on web UI follow the active Home Assistant theme (colors, dark/light,
 * dashboard wallpaper, glass blur, card corners and shadows) and updates live when
 * the theme changes. It reads the theme from the Home Assistant page that holds the
 * add-on (ingress runs on the same origin) and remaps this page's own colors to it.
 * Opened outside Home Assistant it does nothing, so the page keeps its own look.
 * Wallpaper: the add-on's "wallpaper" option (Configuration tab) overrides the theme's:
 *   empty = use the theme's wallpaper, "none" = no wallpaper, or an image:
 *   /local/pic.jpg (= /config/www/pic.jpg), just pic.jpg, /config/www/..., or https://...
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
  var lastKey = '', copied = {}, wallOverride = null;   /* null = follow the theme */

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
    set('--hb-page', th.wall || css(th.bg));
    root.style.setProperty('color-scheme', th.dark ? 'dark' : 'light');
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
      (th.wall ? 'html.hb-themed iframe{background:transparent !important}' : '') +
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
  doc.addEventListener('visibilitychange', function () { if (!doc.hidden) later(); });
  window.addEventListener('load', later);
  try { loadWallpaperOption(); } catch (e) {}
  window.haThemeBridge = { refresh: function () { lastKey = ''; run(); } };
})();
</script>
<!-- /ha-theme -->
<h1>&#10084;&#65039; Pi Health <span id="st" class="sub"></span></h1>
<div class="grid" id="cards"></div>
<h2>Throttling / power</h2><div class="card" id="thr"></div>
<h2 id="rt">Add-ons &amp; system (sorted by CPU)</h2>
<div class="card wrap"><table><thead><tr><th>Name</th><th class="r">CPU</th><th class="r">RAM</th><th class="r">RAM %</th></tr></thead>
<tbody id="rows"></tbody></table></div>
<script>
const col=p=>p>85?'#ff4d6d':p>60?'#ffb703':'#2ec4b6';
const mb=b=>b>=1073741824?(b/1073741824).toFixed(2)+' GB':(b/1048576).toFixed(0)+' MB';
const up=s=>{const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?d+'d ':'')+h+'h '+m+'m'};
const card=(l,v,s,p)=>`<div class="card"><div class="lbl">${l}</div><div class="val" style="color:${p==null?'inherit':col(p)}">${v}</div>${p==null?'':`<div class="bar"><i style="width:${Math.min(p,100)}%;background:${col(p)}"></i></div>`}<div class="sub">${s||''}</div></div>`;
function render(d){
 if(!d.ready){document.getElementById('st').textContent='warming up...';return}
 const tp=d.temp_c==null?null:(d.temp_c-30)/55*100;
 document.getElementById('cards').innerHTML=
  card('CPU',d.cpu+'%',d.cores+' cores'+(d.freq_mhz?' @ '+d.freq_mhz+' MHz':''),d.cpu)+
  card('Temp',d.temp_c==null?'n/a':d.temp_c+'&deg;C',d.temp_f==null?'':d.temp_f+'&deg;F',tp)+
  card('Memory',d.mem.pct+'%',mb(d.mem.used)+' / '+mb(d.mem.total),d.mem.pct)+
  card('Disk',d.disk.pct+'%',d.disk.used+' / '+d.disk.total+' GB',d.disk.pct)+
  card('Load',d.load[0],'5m '+d.load[1]+' | 15m '+d.load[2],d.load[0]/d.cores*100)+
  card('Uptime',up(d.uptime),d.mem.swap_total?'Swap '+mb(d.mem.swap_used):'No swap');
 const t=d.throttle;
 document.getElementById('thr').innerHTML=!t.available?'<span class="sub">Not exposed on this hardware</span>':
  t.flags.length?t.flags.map(f=>`<div class="${f.includes('NOW')?'bad':'warn'}">&#9888; ${f}</div>`).join(''):'<span class="ok">&#10003; All clear, no throttling or under-voltage</span>';
 if(d.mode==='docker')document.getElementById('rt').textContent='Containers (sorted by CPU)';
 document.getElementById('rows').innerHTML=(d.addons.length?'':'<tr><td colspan="4" class="sub">'+(d.docker_error?'Docker API unavailable: '+d.docker_error:'No running containers')+'</td></tr>')+d.addons.map(a=>`<tr><td>${a.name}</td><td class="r" style="color:${col(a.cpu)}">${a.cpu}%</td><td class="r">${mb(a.mem)}</td><td class="r">${a.mem_pct}%</td></tr>`).join('');
 document.getElementById('st').textContent='updated '+new Date(d.ts*1000).toLocaleTimeString();
}
async function tick(){try{render(await (await fetch('api/stats')).json())}catch(e){document.getElementById('st').textContent='offline'}}
tick();setInterval(tick,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0].endswith("api/stats"):
            body, ctype = json.dumps(dict(cache)).encode(), "application/json"
        else:
            body, ctype = HTML.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=sampler, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()

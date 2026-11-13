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
</style></head><body><h1>&#10084;&#65039; Pi Health <span id="st" class="sub"></span></h1>
<div class="grid" id="cards"></div>
<h2>Throttling / power</h2><div class="card" id="thr"></div>
<h2 id="rt">Add-ons &amp; system (sorted by CPU)</h2>
<div class="card wrap"><table><thead><tr><th>Name</th><th class="r">CPU</th><th class="r">RAM</th><th class="r">RAM %</th></tr></thead>
<tbody id="rows"></tbody></table></div>
<script>
const col=p=>p>85?'#ff4d6d':p>60?'#ffb703':'#2ec4b6';
const mb=b=>b>=1073741824?(b/1073741824).toFixed(2)+' GB':(b/1048576).toFixed(0)+' MB';
const up=s=>{const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?d+'d ':'')+h+'h '+m+'m'};
const card=(l,v,s,p)=>`<div class="card"><div class="lbl">${l}</div><div class="val" style="color:${p==null?'#eee':col(p)}">${v}</div>${p==null?'':`<div class="bar"><i style="width:${Math.min(p,100)}%;background:${col(p)}"></i></div>`}<div class="sub">${s||''}</div></div>`;
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

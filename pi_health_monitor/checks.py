"""Deeper health checks for Pi Health Monitor. Standard library only, and run slowly (every few minutes, or when asked),
so the add-on stays light.

- Home Assistant's own health (Supervisor resolution center: issues, suggestions, unhealthy / unsupported)
- updates waiting (Core, OS, Supervisor, add-ons) and how old the newest backup is
- storage: disk space, SD card / eMMC wear when the card reports it, the biggest folders in the config folder
- the recorder database: size, and which entities, statistics and events take the most room
- entities that are unavailable, by integration
- errors and warnings in home-assistant.log, by where they come from
- network: internet and DNS response time
- 24-hour history of CPU, temperature and memory
"""
import json
import os
import re
import socket
import sqlite3
import time
import urllib.request
from collections import Counter, deque

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
CONF = os.environ.get("HA_CONFIG", "/homeassistant")
DB = os.path.join(CONF, "home-assistant_v2.db")
LOG = os.path.join(CONF, "home-assistant.log")
DB_SCAN_EVERY = 6 * 3600  # the database scan reads the whole table, so not often
DB_TIME_LIMIT = 120  # seconds before a database scan gives up

history = deque(maxlen=24 * 60)  # one point a minute for 24 hours: (t, cpu, temp, mem%)
state = {"checks": [], "db": None, "db_running": False, "updated": 0, "score": None}


def sup(path, method="GET"):
    req = urllib.request.Request("http://supervisor" + path, method=method, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", {})


def core(path):
    req = urllib.request.Request("http://supervisor/core/api" + path, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def add(out, key, title, level, detail, fix=""):
    out.append({"key": key, "title": title, "level": level, "detail": detail, "fix": fix})


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB":
            return ("%.0f %s" if u in ("B", "KB") else "%.1f %s") % (n, u)
        n /= 1024


def folder_size(path, limit=200000):
    total, n = 0, 0
    for dp, dns, fns in os.walk(path):
        for f in fns:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
            n += 1
            if n > limit:
                return total
    return total


# ---------------------------------------------------------------- the checks
def check_resolution(out):
    try:
        r = sup("/resolution/info")
    except Exception as e:  # noqa: BLE001
        add(out, "resolution", "Home Assistant health", "unknown", "Couldn't ask the Supervisor: %s" % e)
        return
    bad = r.get("unhealthy") or []
    uns = r.get("unsupported") or []
    issues = r.get("issues") or []
    sugg = r.get("suggestions") or []
    if bad:
        add(out, "resolution", "Home Assistant says the system is unhealthy", "bad", ", ".join(bad),
            "Settings > System > Repairs shows what to do. Unhealthy systems stop getting updates.")
    elif uns or issues:
        txt = []
        if uns:
            txt.append("unsupported: " + ", ".join(uns))
        if issues:
            txt.append("issues: " + ", ".join("%s (%s)" % (i.get("type"), i.get("context")) for i in issues[:6]))
        add(out, "resolution", "Home Assistant found problems", "warn", "; ".join(txt),
            "See Settings > System > Repairs." + (" Suggested: " + ", ".join(s.get("type", "") for s in sugg[:4]) if sugg else ""))
    else:
        add(out, "resolution", "Home Assistant health", "ok", "No repairs, nothing unsupported or unhealthy.")


def check_updates(out):
    waiting = []
    for name, path in (("Home Assistant Core", "/core/info"), ("Operating System", "/os/info"), ("Supervisor", "/supervisor/info")):
        try:
            i = sup(path)
            if i.get("update_available"):
                waiting.append("%s %s → %s" % (name, i.get("version"), i.get("version_latest")))
        except Exception:  # noqa: BLE001
            pass
    try:
        for a in sup("/addons").get("addons", []):
            if a.get("update_available"):
                waiting.append("%s %s → %s" % (a.get("name"), a.get("version"), a.get("version_latest")))
    except Exception:  # noqa: BLE001
        pass
    if waiting:
        add(out, "updates", "%d update%s waiting" % (len(waiting), "" if len(waiting) == 1 else "s"),
            "warn" if len(waiting) < 6 else "bad", "; ".join(waiting[:12]), "Settings > Updates. Take a backup first.")
    else:
        add(out, "updates", "Updates", "ok", "Everything is up to date.")


def check_backups(out):
    try:
        bks = sup("/backups").get("backups", [])
    except Exception as e:  # noqa: BLE001
        add(out, "backups", "Backups", "unknown", "Couldn't list backups: %s" % e)
        return
    if not bks:
        add(out, "backups", "No backups", "bad", "There are no Home Assistant backups at all.",
            "Settings > System > Backups: turn on automatic backups, ideally to another device or the cloud.")
        return
    newest = max(bks, key=lambda b: b.get("date") or "")
    try:
        t = time.mktime(time.strptime(newest["date"][:19], "%Y-%m-%dT%H:%M:%S"))
        age = (time.time() - t) / 86400
    except (KeyError, ValueError):
        age = 0
    size = sum(float(b.get("size") or 0) for b in bks)
    lvl = "ok" if age <= 3 else "warn" if age <= 10 else "bad"
    add(out, "backups", "Newest backup is %d day%s old" % (age, "" if int(age) == 1 else "s"), lvl,
        "%d backups, %.1f GB in total. Newest: %s" % (len(bks), size / 1024 if size > 100 else size, newest.get("name")),
        "" if lvl == "ok" else "Settings > System > Backups: set automatic backups.")


def check_storage(out, disk):
    pct = disk.get("pct") or 0
    free = (disk.get("total") or 0) - (disk.get("used") or 0)
    lvl = "ok" if pct < 75 else "warn" if pct < 90 else "bad"
    add(out, "disk", "Disk %.0f%% full (%.1f GB free)" % (pct, free), lvl, "",
        "" if lvl == "ok" else "Use Junk cleanup below, delete old backups, or shrink the database (see Database).")
    life = None
    try:
        life = sup("/host/info").get("disk_life_time")
    except Exception:  # noqa: BLE001
        pass
    if life is None:
        raw = None
        for p in ("/sys/block/mmcblk0/device/life_time", "/sys/block/mmcblk1/device/life_time"):
            try:
                raw = open(p).read().split()
                break
            except OSError:
                continue
        if raw:
            try:
                life = max(int(x, 16) for x in raw) * 10  # 0x01 = 0-10% used
            except ValueError:
                life = None
    if life is not None:
        lvl = "ok" if life < 70 else "warn" if life < 90 else "bad"
        add(out, "wear", "Storage wear about %d%%" % life, lvl, "How much of the SD card / eMMC's rated writes are used.",
            "" if lvl == "ok" else "Plan to move to an SSD or a new card, and keep backups off the Pi.")
    # read-only file system (a failing SD card often flips to read-only)
    try:
        with open(os.path.join(CONF, ".pi_health_write_test"), "w") as f:
            f.write("ok")
        os.remove(os.path.join(CONF, ".pi_health_write_test"))
    except OSError as e:
        add(out, "rofs", "Can't write to the config folder", "bad", str(e), "The storage may be failing or read only. Back up now.")
    # biggest folders in the config folder
    sizes = []
    try:
        for n in os.listdir(CONF):
            p = os.path.join(CONF, n)
            if os.path.isdir(p) and not os.path.islink(p):
                sizes.append((folder_size(p), n + "/"))
            elif os.path.isfile(p):
                sizes.append((os.path.getsize(p), n))
    except OSError:
        pass
    sizes.sort(reverse=True)
    state["config_sizes"] = [{"name": n, "size": s, "text": human(s)} for s, n in sizes[:10]]


def check_cpu_temp(out, live):
    t = live.get("temp_c")
    if t is not None:
        lvl = "ok" if t < 70 else "warn" if t < 80 else "bad"
        add(out, "temp", "CPU at %.0f°C" % t, lvl, "", "" if lvl == "ok" else "Add a heatsink or fan, and check the case isn't closed up.")
    flags = (live.get("throttle") or {}).get("flags") or []
    if flags:
        now = [f for f in flags if "NOW" in f]
        add(out, "power", "Power / throttling: " + ", ".join(flags), "bad" if now else "warn", "",
            "Under-voltage means the power supply or cable is too weak: use the official 5.1 V / 3 A (Pi 4) supply.")
    elif (live.get("throttle") or {}).get("available"):
        add(out, "power", "Power supply", "ok", "No under-voltage or throttling since boot.")
    mem = live.get("mem") or {}
    if mem.get("pct", 0) > 90 or (mem.get("swap_total") and mem.get("swap_used", 0) > 0.8 * mem["swap_total"]):
        add(out, "mem", "Memory is tight (%.0f%% used)" % mem.get("pct", 0), "warn", "",
            "The add-on list below shows what uses the most. Stop add-ons you don't need.")
    load = (live.get("load") or [0])[0]
    cores = live.get("cores") or 4
    if load > cores * 1.5:
        add(out, "load", "Very busy (load %.1f on %d cores)" % (load, cores), "warn", "", "See the add-on list below for what's using the CPU.")


def check_entities(out):
    try:
        states = core("/states")
    except Exception as e:  # noqa: BLE001
        add(out, "entities", "Entities", "unknown", "Couldn't read Home Assistant's entities: %s" % e)
        return
    bad = [s for s in states if s.get("state") == "unavailable"]
    by = Counter(s["entity_id"].split(".")[0] for s in bad)
    state["unavailable"] = [s["entity_id"] for s in bad][:200]
    state["entity_count"] = len(states)
    if not bad:
        add(out, "entities", "%d entities, none unavailable" % len(states), "ok", "")
        return
    pct = 100 * len(bad) / max(1, len(states))
    add(out, "entities", "%d of %d entities unavailable" % (len(bad), len(states)), "warn" if pct < 10 else "bad",
        "By type: " + ", ".join("%s %d" % kv for kv in by.most_common(8)),
        "Open the Entities card to see them. Often a device that's off, a removed integration, or leftovers you can delete.")


LOG_RE = re.compile(r"^\S+ \S+ (ERROR|WARNING|CRITICAL) \(\S+\) \[([^\]]+)\]")


def check_log(out):
    try:
        size = os.path.getsize(LOG)
    except OSError:
        return
    counts, srcs = Counter(), Counter()
    with open(LOG, "rb") as f:
        if size > 4 * 1024 * 1024:
            f.seek(size - 4 * 1024 * 1024)
        for raw in f:
            m = LOG_RE.match(raw.decode("utf-8", "replace"))
            if m:
                counts[m.group(1)] += 1
                src = m.group(2)
                src = re.sub(r"^(homeassistant\.components\.|custom_components\.)", "", src)
                srcs[(m.group(1), src.split(".")[0])] += 1
    state["log_sources"] = [{"level": lv, "source": s, "count": n} for (lv, s), n in srcs.most_common(12)]
    errs = counts["ERROR"] + counts["CRITICAL"]
    lvl = "ok" if errs < 10 else "warn" if errs < 100 else "bad"
    top = ", ".join("%s (%d)" % (s, n) for (lv, s), n in srcs.most_common(5) if lv != "WARNING")
    add(out, "log", "%d errors, %d warnings since the last restart" % (errs, counts["WARNING"]), lvl,
        ("Most from: " + top) if top else "", "" if lvl == "ok" else "Settings > System > Logs. The busiest sources are listed under Log.")


def check_network(out):
    def tcp(host, port):
        t = time.time()
        try:
            with socket.create_connection((host, port), timeout=4):
                return round((time.time() - t) * 1000)
        except OSError:
            return None
    net = tcp("1.1.1.1", 443) or tcp("8.8.8.8", 443)
    t = time.time()
    try:
        socket.getaddrinfo("www.home-assistant.io", 443)
        dns = round((time.time() - t) * 1000)
    except OSError:
        dns = None
    if net is None:
        add(out, "net", "No internet", "bad", "Couldn't reach 1.1.1.1 or 8.8.8.8.", "Check the router / cable.")
    elif dns is None:
        add(out, "net", "DNS isn't working", "bad", "Internet answers (%d ms) but names don't resolve." % net, "Check the DNS add-on / router DNS.")
    else:
        lvl = "ok" if net < 150 and dns < 500 else "warn"
        add(out, "net", "Internet %d ms, DNS %d ms" % (net, dns), lvl, "")


# ---------------------------------------------------------------- recorder database
def db_scan():
    """Which entities fill the recorder database. Reads it read-only; gives up after DB_TIME_LIMIT seconds."""
    if state["db_running"]:
        return
    state["db_running"] = True
    res = {"t": time.time(), "ok": False}
    try:
        files = {p: os.path.getsize(p) for p in (DB, DB + "-wal", DB + "-shm") if os.path.exists(p)}
        if DB not in files:
            res["error"] = "No SQLite database at %s (MariaDB/Postgres users: this part only works with the default database)." % DB
            return
        res["size"] = sum(files.values())
        res["size_text"] = human(res["size"])
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=20)
        start = time.time()
        con.set_progress_handler(lambda: 1 if time.time() - start > DB_TIME_LIMIT else 0, 20000)
        cur = con.cursor()
        total_states = cur.execute("SELECT COUNT(*) FROM states").fetchone()[0]
        # counts per entity come straight off the metadata_id index, so this stays quick even on big databases
        rows = cur.execute(
            "SELECT m.entity_id, x.c FROM (SELECT metadata_id, COUNT(*) c FROM states GROUP BY metadata_id "
            "ORDER BY c DESC LIMIT 30) x JOIN states_meta m ON x.metadata_id = m.metadata_id ORDER BY x.c DESC").fetchall()
        per_row = res["size"] * 0.6 / max(1, total_states)  # states, their indexes and attributes are most of the file
        res["entities"] = [{"entity_id": e, "rows": c, "pct": round(100 * c / max(1, total_states), 1),
                            "est": human(c * per_row)} for e, c in rows]
        res["states"] = total_states
        try:
            st = cur.execute("SELECT m.statistic_id, COUNT(*) c FROM statistics s JOIN statistics_meta m ON s.metadata_id = m.id "
                             "GROUP BY s.metadata_id ORDER BY c DESC LIMIT 10").fetchall()
            res["statistics"] = [{"id": i, "rows": c} for i, c in st]
            res["stat_series"] = cur.execute("SELECT COUNT(*) FROM statistics_meta").fetchone()[0]
        except sqlite3.Error:
            pass
        try:
            ev = cur.execute("SELECT t.event_type, COUNT(*) c FROM events e JOIN event_types t ON e.event_type_id = t.event_type_id "
                             "GROUP BY e.event_type_id ORDER BY c DESC LIMIT 8").fetchall()
            res["events"] = [{"type": t, "rows": c} for t, c in ev]
        except sqlite3.Error:
            pass
        try:
            oldest = cur.execute("SELECT MIN(last_updated_ts) FROM states").fetchone()[0]
            res["days"] = round((time.time() - oldest) / 86400, 1) if oldest else None
        except sqlite3.Error:
            pass
        con.close()
        top = [r["entity_id"] for r in res["entities"][:8] if r["pct"] >= 2]
        res["exclude_yaml"] = ("recorder:\n  exclude:\n    entities:\n" + "".join("      - %s\n" % e for e in top)) if top else ""
        res["ok"] = True
        res["took"] = round(time.time() - start, 1)
    except sqlite3.OperationalError as e:
        res["error"] = "Database scan stopped: %s" % ("took too long" if "interrupt" in str(e) else e)
    except Exception as e:  # noqa: BLE001
        res["error"] = "Database scan failed: %s" % e
    finally:
        state["db"] = res
        state["db_running"] = False


def check_db(out):
    d = state.get("db")
    try:
        size = sum(os.path.getsize(p) for p in (DB, DB + "-wal") if os.path.exists(p))
    except OSError:
        size = 0
    if not size:
        return
    lvl = "ok" if size < 1.5 * 1024 ** 3 else "warn" if size < 4 * 1024 ** 3 else "bad"
    detail = ""
    if d and d.get("ok") and d.get("entities"):
        e = d["entities"][0]
        detail = "Biggest: %s (%s%% of rows)." % (e["entity_id"], e["pct"])
        if d.get("days"):
            detail += " Keeps %s days." % d["days"]
    add(out, "db", "Database is %s" % human(size), lvl, detail,
        "" if lvl == "ok" else "See Database: exclude the busiest entities from the recorder, or lower purge_keep_days.")


# ---------------------------------------------------------------- run
def run_all(live):
    out = []
    for fn in (check_resolution, check_updates, check_backups, check_entities, check_log, check_network, check_db):
        try:
            fn(out)
        except Exception as e:  # noqa: BLE001
            add(out, fn.__name__, fn.__name__.replace("check_", "").title(), "unknown", "Check failed: %s" % e)
    try:
        check_storage(out, live.get("disk") or {})
        check_cpu_temp(out, live)
    except Exception as e:  # noqa: BLE001
        add(out, "host", "Host", "unknown", "Check failed: %s" % e)
    order = {"bad": 0, "warn": 1, "unknown": 2, "ok": 3}
    out.sort(key=lambda c: order.get(c["level"], 9))
    pts = {"ok": 100, "warn": 60, "bad": 10}
    scored = [pts[c["level"]] for c in out if c["level"] in pts]
    state["score"] = round(sum(scored) / len(scored)) if scored else None
    state["checks"] = out
    state["updated"] = time.time()


def record(live):
    history.append((int(time.time()), live.get("cpu"), live.get("temp_c"), (live.get("mem") or {}).get("pct")))


def view():
    h = list(history)
    return {"checks": state["checks"], "score": state["score"], "updated": state["updated"], "db": state["db"],
            "db_running": state["db_running"], "config_sizes": state.get("config_sizes") or [],
            "log_sources": state.get("log_sources") or [], "unavailable": state.get("unavailable") or [],
            "history": h[::max(1, len(h) // 288)]}  # about 5-minute points for the page


def ai_report():
    """Plain-text summary for the AI."""
    lines = ["Health score: %s/100" % state["score"]]
    for c in state["checks"]:
        lines.append("- [%s] %s. %s %s" % (c["level"], c["title"], c["detail"], c["fix"]))
    d = state.get("db") or {}
    if d.get("ok"):
        lines.append("Database %s, %s days, top entities by rows: %s" % (
            d.get("size_text"), d.get("days"), ", ".join("%s %s%%" % (e["entity_id"], e["pct"]) for e in d["entities"][:10])))
    if state.get("log_sources"):
        lines.append("Log sources: " + ", ".join("%s %s x%d" % (x["level"], x["source"], x["count"]) for x in state["log_sources"][:8]))
    if state.get("config_sizes"):
        lines.append("Biggest in config folder: " + ", ".join("%s %s" % (x["name"], x["text"]) for x in state["config_sizes"][:6]))
    return "\n".join(lines)


def ask_ai(entity, question):
    """Ask Home Assistant's AI Task to explain the report and give a fix plan."""
    if not entity:
        try:
            states = core("/states")
        except Exception:  # noqa: BLE001
            states = []
        for s in states:  # the household default AI Task, picked in Personalized Info
            a = s.get("attributes") or {}
            if s["entity_id"] in ("select.default_ai_task", "sensor.default_ai_task") or a.get("role") == "default_ai_task":
                v = s.get("state") if str(s.get("state", "")).startswith("ai_task.") else a.get("ai_task_entity")
                if str(v or "").startswith("ai_task."):
                    entity = v
                    break
        ents = [s["entity_id"] for s in states if s["entity_id"].startswith("ai_task.")]
        if not ents and not entity:
            raise RuntimeError("No AI Task entity found. Add one (Google Gemini, OpenAI, Anthropic, Ollama) and try again.")
        entity = entity or ents[0]
    prompt = ("You are a Home Assistant and Raspberry Pi expert. Here is a health report from a Home Assistant OS Raspberry Pi. "
              "Explain in plain words what matters most, then give a short numbered fix list, most important first, with exact "
              "steps (menu paths or YAML). Keep it under 250 words. Don't repeat things that are fine.\n\n" + ai_report())
    if question:
        prompt += "\n\nThe user also asks: " + question
    body = json.dumps({"entity_id": entity, "task_name": "Pi health", "instructions": prompt}).encode()
    req = urllib.request.Request("http://supervisor/core/api/services/ai_task/generate_data?return_response", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    out = (d.get("service_response") or {}).get("data")
    return out if isinstance(out, str) else json.dumps(out, indent=1)

#!/usr/bin/env python3
"""Regenerate each add-on's README.md and the generated parts of DOCS.md from config.yaml + translations/en.yaml.

Run from anywhere:  python3 .github/docsgen/gen.py
Hand-written text lives in meta.py (taglines, features, needs) and in DOCS.md outside the generated blocks.
Only the blocks between <!-- docs:... --> markers in DOCS.md are replaced; README.md is fully generated.
"""
import os
import re
import sys
from urllib.parse import quote

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from meta import META, ORDER, RAW, REPO  # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADD_REPO = "https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=" + quote("https://github.com/" + REPO, safe="")
ADD_BADGE = "https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg"
H_START, H_END = "<!-- docs:header (generated, edit .github/docsgen) -->", "<!-- /docs:header -->"
C_START, C_END = "<!-- docs:config (generated from config.yaml) -->", "<!-- /docs:config -->"
F_START, F_END = "<!-- docs:footer (generated) -->", "<!-- /docs:footer -->"


def load(slug):
    c = yaml.safe_load(open(os.path.join(ROOT, slug, "config.yaml")))
    t = {}
    tp = os.path.join(ROOT, slug, "translations", "en.yaml")
    if os.path.exists(tp):
        t = (yaml.safe_load(open(tp)) or {}).get("configuration", {}) or {}
    return c, t


def shield(label, msg, color, logo=""):
    q = lambda x: quote(str(x).replace("-", "--").replace("_", "__"), safe="")  # noqa: E731
    return "https://img.shields.io/badge/%s-%s-%s%s" % (q(label), q(msg), color, "?logo=" + logo if logo else "")


def badges(slug, c):
    cfg_url = quote(RAW + "/" + slug + "/config.yaml", safe="")
    out = [
        "![Version](https://img.shields.io/badge/dynamic/yaml?url=%s&query=%%24.version&label=version&color=41BDF5&logo=homeassistant)" % cfg_url,
        "![Architectures](%s)" % shield("arch", " | ".join(c.get("arch") or []), "informational"),
    ]
    if c.get("ingress"):
        out.append("![Sidebar](%s)" % shield("sidebar", "ingress", "success"))
    if c.get("image"):
        out.append("![Prebuilt image](%s)" % shield("image", "GHCR", "2ea44f", "docker"))
    else:
        out.append("![Builds locally](%s)" % shield("image", "builds on device", "lightgrey", "docker"))
    if "mqtt:want" in (c.get("services") or []) or "mqtt:need" in (c.get("services") or []):
        out.append("![MQTT](%s)" % shield("MQTT", "optional" if "mqtt:want" in c["services"] else "required", "660066", "mqtt"))
    opts = c.get("options") or {}
    if "ai_task_entity" in opts or slug in ("ai_builder", "photo_shuffle"):
        out.append("![AI Task](%s)" % shield("AI", "ai_task", "8A2BE2", "googlegemini"))
    if META[slug].get("docker"):
        out.append("![Docker](%s)" % shield("also runs in", "Docker", "2496ED", "docker"))
    if META[slug].get("deprecated"):
        out.append("![Deprecated](%s)" % shield("status", "moved to Photo Hub", "orange"))
    return " ".join(out)


def schema_type(v):
    s = str(v).rstrip("?")
    m = re.match(r"list\((.*)\)", s)
    if m:
        return "one of: " + ", ".join("`%s`" % x for x in m.group(1).split("|"))
    m = re.match(r"(int|float)\(([^,]*),([^)]*)\)", s)
    if m:
        lo, hi = m.group(2), m.group(3)
        return {"int": "whole number", "float": "number"}[m.group(1)] + (" (%s–%s)" % (lo or "…", hi or "…"))
    if s.startswith("match("):
        return "path" if "/" in s else "text"
    return {"str": "text", "bool": "true / false", "int": "whole number", "float": "number", "password": "secret",
            "email": "email", "url": "URL", "port": "port", "match(.*)": "text"}.get(s, s)


def fmt_default(v, secret):
    if secret:
        return "*(hidden)*" if v else "*(empty)*"
    if v is None or v == "":
        return "*(empty)*"
    if isinstance(v, bool):
        return "`true`" if v else "`false`"
    if isinstance(v, list):
        return ", ".join("`%s`" % x for x in v) if v else "*(none)*"
    if isinstance(v, dict):
        return "`%s`" % yaml.safe_dump(v, default_flow_style=True).strip()
    return "`%s`" % v


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "\\|")


def config_table(c, t):
    opts, schema = c.get("options") or {}, c.get("schema") or {}
    keys = list(opts) + [k for k in schema if k not in opts]
    if not keys:
        return "This add-on has no options on its Configuration tab."
    rows = ["| Option | Default | Type | What it does |", "|---|---|---|---|"]
    for k in keys:
        sv = schema.get(k, "")
        if isinstance(sv, (list, dict)):
            typ = "list" if isinstance(sv, list) else "group"
        else:
            typ = schema_type(sv) if sv else "—"
            if str(sv).endswith("?"):
                typ += ", optional"
        secret = "password" in str(sv) or re.search(r"password|secret|api_key|token", k)
        tr = t.get(k) or {}
        name = clean(tr.get("name"))
        desc = clean(tr.get("description"))
        rows.append("| `%s` | %s | %s | %s |" % (k, fmt_default(opts.get(k), secret), typ, ("**%s.** " % name.rstrip(".") if name else "") + desc))
    return "\n".join(rows)


def needs_line(c):
    bits = []
    if c.get("homeassistant_api"):
        bits.append("Home Assistant API")
    if c.get("hassio_api"):
        bits.append("Supervisor API")
    return ", ".join(bits) or "none"


def glance(slug, c):
    ports = c.get("ports") or {}
    maps = []
    for m in c.get("map") or []:
        if isinstance(m, dict):
            maps.append("`%s`%s" % (m.get("type"), " (read only)" if m.get("read_only", True) else ""))
        else:
            n, _, mode = str(m).partition(":")
            maps.append("`%s`%s" % (n, " (read only)" if mode == "ro" else ""))
    rows = [
        ("Version", "`%s`" % c.get("version")),
        ("Slug", "`%s`" % c.get("slug")),
        ("Architectures", ", ".join("`%s`" % a for a in c.get("arch") or [])),
        ("Opens from", "the sidebar (**%s**, ingress)" % (c.get("panel_title") or c.get("name")) if c.get("ingress") else "its own port"),
        ("Extra ports", ", ".join("`%s`" % p for p in ports) if ports else "none"),
        ("Folders it can reach", ", ".join(maps) or "only its own storage"),
        ("API access", needs_line(c)),
        ("MQTT", "optional (used when available)" if "mqtt:want" in (c.get("services") or []) else "required" if "mqtt:need" in (c.get("services") or []) else "not used"),
        ("Takes commands via `hassio.addon_stdin`", "yes" if c.get("stdin") else "no"),
        ("Install", "prebuilt image from GHCR" if c.get("image") else "built on your device"),
    ]
    return "| | |\n|---|---|\n" + "\n".join("| %s | %s |" % r for r in rows)


def slugify(h):
    h = re.sub(r"[`*_]", "", h.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def contents(body):
    lines, inside = [], False
    for ln in body.splitlines():
        if ln.startswith("```"):
            inside = not inside
            continue
        if inside:
            continue
        m = re.match(r"^(#{1,3}) (.+)$", ln)
        if not m:
            continue
        lvl, title = len(m.group(1)), m.group(2).strip()
        if lvl == 3 and len(body) < 9000:
            continue
        lines.append("%s- [%s](#%s)" % ("  " * (lvl - 1 if lvl > 1 else 0) if lvl == 3 else "", title, slugify(title)))
    return "\n".join(lines)


def strip_block(text, a, b):
    return re.sub(re.escape(a) + r".*?" + re.escape(b) + r"\n*", "", text, flags=re.S)


def write_docs(slug, c, t):
    p = os.path.join(ROOT, slug, "DOCS.md")
    text = open(p, encoding="utf-8").read()
    for a, b in ((H_START, H_END), (C_START, C_END), (F_START, F_END)):
        text = strip_block(text, a, b)
    body = text.lstrip()
    if body.startswith("# "):
        body = body.split("\n", 1)[1].lstrip("\n") if "\n" in body else ""
    m = META[slug]
    header = "\n".join([
        H_START,
        "# %s" % c["name"],
        "",
        badges(slug, c),
        "",
        "> " + m["tagline"],
        "",
        "## At a glance",
        "",
        glance(slug, c),
        "",
        "**You'll need:**",
        "",
        *["- " + n for n in m["needs"]],
        "",
        "## Contents",
        "",
        contents(body + "\n## Configuration reference\n## Help and feedback\n"),
        H_END,
        "",
    ])
    cfg = "\n".join([
        "", C_START,
        "## Configuration reference",
        "",
        "Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.",
        "",
        config_table(c, t),
        C_END,
    ])
    footer = "\n".join([
        "", F_START,
        "## Help and feedback",
        "",
        "- **Logs:** the add-on's **Log** tab shows what it's doing and most errors in plain words.",
        "- **Changes:** see the [changelog](CHANGELOG.md) (also on the add-on's **Changelog** tab).",
        "- **Problems or ideas:** [open an issue](https://github.com/%s/issues) and include the add-on version and the log." % REPO,
        "- **Pages follow your theme:** every page in this repository picks up your Home Assistant theme and wallpaper automatically.",
        "- **On your phone:** the pages are built for the Home Assistant iPhone and Android apps. Turn on **Show in sidebar** to reach them from the app's menu.",
        F_END, "",
    ])
    out = header + "\n" + body.rstrip() + "\n" + cfg + "\n" + footer
    open(p, "w", encoding="utf-8").write(out)


def write_readme(slug, c):
    m = META[slug]
    lines = [
        '<img src="icon.png" alt="" width="96" align="right">',
        "",
        "# %s" % c["name"],
        "",
        badges(slug, c),
        "",
        m["tagline"],
        "",
        "## Features",
        "",
        *["- " + f for f in m["features"]],
        "",
        "## What you need",
        "",
        "- Home Assistant OS or Supervised (add-ons need the Supervisor)",
        *["- " + n for n in m["needs"]],
        "",
        "## Install",
        "",
        "[![Add this repository to your Home Assistant](%s)](%s)" % (ADD_BADGE, ADD_REPO),
        "",
        "1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/%s`." % REPO,
        "2. Find **%s** in the store and click **Install**." % c["name"],
        "3. Check the **Configuration** tab, then **Start**." + (" Turn on **Show in sidebar** to open it from the sidebar." if c.get("ingress") else ""),
        "",
    ]
    if m.get("docker"):
        lines += ["It also runs without Home Assistant as a plain Docker container: see **Running without Home Assistant** in the docs.", ""]
    lines += [
        "## Documentation",
        "",
        "- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab",
        "- [Changelog](CHANGELOG.md)",
        "- [All add-ons in this repository](../README.md)",
        "",
    ]
    open(os.path.join(ROOT, slug, "README.md"), "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    for slug in ORDER:
        c, t = load(slug)
        write_readme(slug, c)
        write_docs(slug, c, t)
        print("ok", slug)

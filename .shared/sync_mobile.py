#!/usr/bin/env python3
"""Copy .shared/ha-mobile.css into every add-on page so it works well on phones.

Each add-on builds from its own folder, so each page carries its own copy inside a marked <style> block,
placed just before </head>. Edit .shared/ha-mobile.css, then run this from the repository root:

    python3 .shared/sync_mobile.py            # update every page that has the block, add it to pages that don't
    python3 .shared/sync_mobile.py --check    # exit 1 if any page is out of date (for CI)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
START, END = "<!-- ha-mobile", "<!-- /ha-mobile -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
SKIP_DIRS = {".git", "node_modules", ".github", ".shared"}


def block():
    css = open(os.path.join(HERE, "ha-mobile.css"), encoding="utf-8").read().strip()
    m = re.search(r"HA Mobile v([\d.]+)", css)
    for bad in ('"""', "</style", "{{", "{%"):
        if bad in css:
            sys.exit("ha-mobile.css must not contain %r" % bad)
    return "%s v%s: copied from .shared/ha-mobile.css, edit it there -->\n<style id=\"ha-mobile\">\n%s\n</style>\n%s\n" % (
        START, m.group(1) if m else "?", css, END)


def pages():
    yield os.path.join(HERE, "addon_backup.py")  # the master copy of the Backups page
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f)
            if f.endswith((".html", ".htm")) or (f.endswith(".py") and "</head>" in open(p, encoding="utf-8", errors="ignore").read()):
                yield p


def main():
    check = "--check" in sys.argv
    new, changed = block(), []
    for p in sorted(pages()):
        text = open(p, encoding="utf-8").read()
        if "</head>" not in text:
            continue
        out = BLOCK_RE.sub("", text) if START in text else text
        out = out.replace("</head>", new + "</head>", 1)
        if out != text:
            changed.append(os.path.relpath(p, ROOT))
            if not check:
                open(p, "w", encoding="utf-8").write(out)
    for c in changed:
        print(("  out of date: " if check else "  mobile: ") + c)
    print("ha-mobile %s (%d page%s %s)" % ("check" if check else "synced", len(changed), "" if len(changed) == 1 else "s",
                                         "need syncing" if check else "changed"))
    if check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Tiny shared helper: ask Home Assistant's AI Task (ai_task.generate_data) from an add-on.

Copied into each add-on by .shared/sync.sh (edit it here). Standard library only.
Needs `homeassistant_api: true` in the add-on's config. The AI Task entity comes from the add-on's
`ai_task_entity` option; empty uses the default AI Task picked in Personalized Info (select.default_ai_task),
and without that the first ai_task.* entity Home Assistant has.
"""
import json
import os
import re
import urllib.error
import urllib.request

API = os.environ.get("HA_API", "http://supervisor/core/api")


def _token():
    return os.environ.get("SUPERVISOR_TOKEN", "")


def available():
    return bool(_token())


def _call(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def entities():
    """AI Task entities: [{"id", "name"}]."""
    try:
        return [{"id": s["entity_id"], "name": (s.get("attributes") or {}).get("friendly_name") or s["entity_id"]}
                for s in _call("GET", "/states") if s["entity_id"].startswith("ai_task.")]
    except Exception:  # noqa: BLE001
        return []


def default_from(states):
    """The household default AI Task (set in Personalized Info), from a list of Home Assistant states, or ''."""
    for s in states:
        a = s.get("attributes") or {}
        if s.get("entity_id") in ("select.default_ai_task", "sensor.default_ai_task") or a.get("role") == "default_ai_task":
            v = str(s.get("state") or "")
            if v.startswith("ai_task."):
                return v
            v = str(a.get("ai_task_entity") or "")
            if v.startswith("ai_task."):
                return v
    return ""


def pick(chosen=""):
    chosen = str(chosen or "").strip()
    if chosen:
        return chosen
    try:
        d = default_from(_call("GET", "/states"))
        if d:
            return d
    except Exception:  # noqa: BLE001
        pass
    ents = entities()
    if not ents:
        raise RuntimeError("No AI Task entity found. Add one in Home Assistant (Google Gemini, OpenAI, Anthropic or Ollama), "
                           "or set ai_task_entity on the add-on's Configuration tab.")
    return ents[0]["id"]


def ask(prompt, entity="", task="Add-on helper", timeout=180):
    """Plain-text answer from the AI Task."""
    if not available():
        raise RuntimeError("AI help only works when this runs as a Home Assistant add-on.")
    body = {"entity_id": pick(entity), "task_name": task, "instructions": prompt}
    try:
        d = _call("POST", "/services/ai_task/generate_data?return_response", body, timeout)
    except urllib.error.HTTPError as e:
        raise RuntimeError("The AI Task call failed (HTTP %d): %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
    except urllib.error.URLError as e:
        raise RuntimeError("Couldn't reach Home Assistant: %s" % e.reason)
    out = (d.get("service_response") or {}).get("data")
    return out if isinstance(out, str) else json.dumps(out)


def ask_json(prompt, entity="", task="Add-on helper", timeout=180):
    """Answer parsed as JSON (the prompt must ask for JSON only)."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", ask(prompt, entity, task, timeout).strip())
    for a, b in (("{", "}"), ("[", "]")):
        i, j = t.find(a), t.rfind(b)
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                continue
    raise RuntimeError("The AI's answer wasn't in the expected format. Try again.")

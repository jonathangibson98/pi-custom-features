/* Small helpers shared by every page. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* el("div", {class: "card", onclick: fn}, child, "text", [more, kids]) */
function el(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else if (k === "checked" || k === "disabled" || k === "hidden") e[k] = !!v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}

/* Settings keys the server is allowed to change on its own (a locked add-on option, an empty AI Task falling back
   to the option, the personality list being tidied). Anything else that comes back different from what was sent
   means the save did not stick. */
const DRIFT_SKIP = new Set(["personalities", "helper_ai_task_entity", "ai_task_entity", "prefix_locked"]);
function settingsDrift(sent, got) {
  if (!sent || !got || typeof sent !== "object" || typeof got !== "object") return [];
  return Object.keys(sent).filter(k => !DRIFT_SKIP.has(k) && k in got && JSON.stringify(sent[k]) !== JSON.stringify(got[k]));
}
function driftBanner(keys) {
  let b = document.getElementById("savewarn");
  if (!b) {
    b = document.createElement("div"); b.id = "savewarn";
    b.style.cssText = "position:fixed;left:12px;right:12px;bottom:84px;z-index:50;padding:12px 14px;border-radius:12px;background:#7a1f1f;color:#fff;font-size:.9rem;box-shadow:0 6px 20px rgba(0,0,0,.4)";
    document.body.append(b);
  }
  b.replaceChildren("Saved, but the add-on sent back different values for: " + keys.join(", ") + ". Something on the add-on side is overriding what you saved, so your change did not stick. ",
    el("button", {class: "btn sm", style: "margin-left:8px", onclick: () => b.remove()}, "Dismiss"));
}

/* api("status") -> GET, api("ann/push", {...}) -> POST. Never throws.
   Always asks the network (cache: no-store) so a page reload can never show settings from before the last save. */
async function api(path, body) {
  const opts = body === undefined ? { cache: "no-store" } : { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  try {
    const r = await fetch(new URL("api/" + path, document.baseURI), opts);
    const j = await r.json();
    if (path === "ann/settings" && body !== undefined && j && !j.error) {
      const bad = settingsDrift(body, j);
      if (bad.length) driftBanner(bad);
    }
    return j;
  } catch (e) { return { ok: false, error: "Couldn't reach the add-on: " + e.message }; }
}

/* A button that needs a second tap within 3 seconds before it runs. */
function confirmTap(btn, label, fn) {
  const first = btn.textContent;
  let t = null;
  btn.addEventListener("click", ev => {
    if (!t) {
      btn.textContent = label; btn.classList.add("armed");
      t = setTimeout(() => { t = null; btn.textContent = first; btn.classList.remove("armed"); }, 3000);
      return;
    }
    clearTimeout(t); t = null; btn.textContent = first; btn.classList.remove("armed");
    fn(ev);
  });
  return btn;
}

const ago = s => {
  if (!s) return "";
  const d = new Date(String(s).replace(" ", "T"));
  if (isNaN(d)) return s;
  const m = Math.round((Date.now() - d) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return m + " min ago";
  if (m < 1440) return Math.round(m / 60) + " h ago";
  if (m < 43200) return Math.round(m / 1440) + " d ago";
  return String(s).slice(0, 10);
};

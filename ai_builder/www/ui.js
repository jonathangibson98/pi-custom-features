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

/* api("status") -> GET, api("ann/push", {...}) -> POST. Never throws. */
async function api(path, body) {
  const opts = body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  try {
    const r = await fetch(new URL("api/" + path, document.baseURI), opts);
    return await r.json();
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

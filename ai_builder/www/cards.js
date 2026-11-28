/* Cards page: AI-assisted dashboard card creator. Describe a card, pick the entities it reads, get Lovelace YAML. */
let S = {}, ENT = [], LIB = [], E = blank(), cur = {id: null, saved: false}, dirty = false, busy = false;
const cd = (path, body) => api("cards/" + path, body);
function blank() { return {name: "My card", request: "", entities: [], toggle: "", style: "glass", yaml: "", notes: "", needs: [], unknown: [], source: null, shape: ""}; }
let MADE = [];  /* announcements and facts made in the other tabs (from /api/made) */
const madeKey = x => x.kind + ":" + x.id;
const madeOf = src => src && MADE.find(x => x.kind === src.kind && x.id === src.id);
const esc = t => String(t).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true; } catch (e) { /* the app's frame may block the clipboard */ }
  const ta = el("textarea", {style: "position:fixed;top:0;left:0;opacity:0"}); ta.value = t; document.body.append(ta); ta.focus(); ta.select();
  try { ta.setSelectionRange(0, t.length); } catch (e) { /* ignore */ }
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
  ta.remove(); return ok;
}
/* same wrapper the server adds: the card only shows while an input_boolean is on */
const wrapYaml = (y, t) => "type: conditional\nconditions:\n  - condition: state\n    entity: " + t + "\n    state: 'on'\ncard:\n" + y.trimEnd().split("\n").map(l => l.trim() ? "  " + l : l).join("\n") + "\n";

/* ---------- views ---------- */
function showView(v) {
  $("#chrome").hidden = v === "edit";
  $("#v-lib").hidden = v !== "lib"; $("#v-edit").hidden = v !== "edit";
  try { window.scrollTo(0, 0); } catch (e) { /* ignore */ }
}
function setupNote() {
  const box = $("#setupnote"); box.replaceChildren();
  if (!S.ai_task_entity) box.append(el("div", {class: "note warn"}, el("div", {}, el("b", {}, "No AI Task is set. "), "Set one in the add-on Configuration tab (ai_task_entity) or in Announcements, Settings, then come back.")));
}
function flash(text, cls) { const m = $("#libmsg"); m.className = "msg " + (cls || ""); m.textContent = text || ""; }

/* ---------- library ---------- */
async function loadLib() {
  const d = await cd("library");
  LIB = d.items || []; renderLib();
}
function renderLib() {
  $("#libsub").textContent = LIB.length ? LIB.length + " card" + (LIB.length === 1 ? "" : "s") + " saved" : "";
  const box = $("#cards"); box.replaceChildren();
  if (!LIB.length) {
    box.style.display = "block";
    box.append(el("div", {class: "card empty"}, el("h3", {}, "No cards yet"),
      el("p", {}, "Say what you want the card to show, pick the entities it reads, and the AI writes it for you."),
      el("div", {class: "row"}, el("button", {class: "btn primary", onclick: () => openNew()}, "Make your first card"))));
    return;
  }
  box.style.display = "";
  LIB.forEach(it => box.append(libCard(it)));
}
function libCard(it) {
  const st = it.state || {}, msg = el("div", {class: "msg", style: "margin:0"});
  const del = el("button", {class: "btn danger sm"}, "Delete");
  confirmTap(del, "Tap again to delete", async () => { const r = await cd("library/delete", {id: it.id}); if (r.ok) { flash("Deleted " + (it.name || it.id) + ".", "ok"); loadLib(); } else flash(r.error, "bad"); });
  const dup = el("button", {class: "btn sm", onclick: async () => {
    const r = await cd("library/save", {name: (it.name || it.id) + " copy", state: Object.assign({}, st, {name: (it.name || it.id) + " copy"})});
    if (r.ok) { flash("Copied as " + r.item.name + ".", "ok"); loadLib(); } else flash(r.error, "bad");
  }}, "Duplicate");
  const copy = el("button", {class: "btn sm", disabled: !st.yaml, onclick: async () => {
    const ok = await copyText(st.yaml || ""); msg.className = "msg " + (ok ? "ok" : "warn");
    msg.textContent = ok ? "Copied. In your dashboard, add a Manual card and paste." : "Your browser blocked copying. Open the card and copy from the box.";
  }}, "Copy card");
  const ents = (st.entities || []).length;
  return el("div", {class: "card ann"},
    el("div", {class: "top"}, el("div", {style: "min-width:0"}, el("h3", {}, it.name || it.id)), st.yaml ? el("span", {class: "pill ok"}, "Built") : el("span", {class: "pill warn"}, "Not built yet")),
    el("div", {class: "clamp"}, st.request || "No description yet."),
    el("div", {class: "meta"}, st.source ? el("span", {class: "pill plain", title: st.source.kind}, "From " + ((madeOf(st.source) || {}).name || st.source.name)) : null,
      ents ? el("span", {class: "pill plain"}, ents + " entit" + (ents === 1 ? "y" : "ies")) : null,
      st.toggle ? el("span", {class: "pill plain", title: st.toggle}, "Has show / hide switch") : null,
      (st.needs || []).map(n => el("span", {class: "pill plain"}, n)), el("span", {class: "pill plain"}, "Edited " + ago(it.updated))),
    el("div", {class: "acts"}, el("button", {class: "btn primary sm", onclick: () => openItem(it)}, "Edit"), copy, dup,
      renameButton(it.name || it.id, n => api("rename", {lib: "cards", id: it.id, name: n}), () => { flash("Renamed.", "ok"); loadLib(); }), del), msg);
}

/* ---------- editor ---------- */
const say = (t, c) => { const m = $("#msg"); m.className = "msg " + (c || ""); m.textContent = t || ""; };
function paint() {
  const p = $("#estate");
  if (dirty) { p.className = "pill acc"; p.textContent = "Unsaved changes"; }
  else if (cur.saved) { p.className = "pill ok"; p.textContent = "Saved"; }
  else { p.className = "pill plain"; p.textContent = "New"; }
  $("#etitle").textContent = $("#name").value.trim() || "New card";
}
const markDirty = () => { dirty = true; paint(); };
function drawPickers() {
  $("#entpick").replaceChildren(picker(null, true, () => E.entities, a => { E.entities = a; markDirty(); }));
  $("#swpick").replaceChildren(picker(["input_boolean"], false, () => E.toggle ? [E.toggle] : [], a => { const old = E.toggle; E.toggle = a[0] || ""; markDirty(); applyToggle(old); }));
}
/* a switch picked after the card was built: wrap the YAML (or retarget the wrapper) so it takes effect */
function applyToggle(old) {
  const ta = $("#yaml"), y = ta.value, t = E.toggle;
  if (!y.trim() || !t || y.includes(t)) return;
  if (/^type:\s*conditional\b/.test(y.trim())) {
    if (old && y.includes(old)) { ta.value = E.yaml = y.split(old).join(t); say("Pointed the card's show / hide condition at " + t + ".", "ok"); }
    else say("This card already has its own condition. Change the entity in the YAML to " + t + ".", "warn");
    return;
  }
  ta.value = E.yaml = wrapYaml(y, t); say("Wrapped the card so it only shows while " + t + " is on.", "ok");
}
function drawNotes() {
  const b = $("#notes"); b.replaceChildren();
  if (E.notes) b.append(el("p", {class: "dim", style: "margin-bottom:10px"}, E.notes));
  if ((E.needs || []).length) b.append(el("div", {class: "note", style: "margin-bottom:10px"}, el("div", {}, el("b", {}, "Needs installed: "), E.needs.join(", ") + ". Custom cards come from HACS.")));
  if ((E.unknown || []).length) b.append(el("div", {class: "note warn", style: "margin-bottom:10px"}, el("div", {}, el("b", {}, "These entities don't exist in Home Assistant: "), E.unknown.join(", ") + ". Fix the names in the YAML or ask the AI to change them.")));
}
function drawCardSec() {
  const has = !!(E.yaml || "").trim();
  $("#cardsec").hidden = !has; $("#prevsec").hidden = !has;
  $("#build").textContent = has ? "Build it again from scratch" : "Build the card";
  drawNotes();
}
function openEditor(state, c) {
  cur = Object.assign({id: null, saved: false}, c);
  E = Object.assign(blank(), state);
  $("#name").value = E.name; $("#request").value = E.request; $("#style").value = E.style || "glass";
  $("#yaml").value = E.yaml || ""; $("#feedback").value = "";
  ["#bres", "#pres"].forEach(i => $(i).replaceChildren()); $("#ymsg").textContent = ""; say("");
  drawPickers(); drawCardSec(); drawFrom(); dirty = false; paint(); showView("edit");
}

/* ---------- start from an announcement or fact ---------- */
function drawFrom() {
  const sel = $("#fromsel"), have = MADE.filter(x => x.file && x.file.sensor);
  sel.replaceChildren(el("option", {value: ""}, "Nothing, I'll pick the entities myself"),
    ...have.map(x => el("option", {value: madeKey(x)}, (x.kind === "announcement" ? "Announcement: " : "Fact: ") + x.name + " (" + x.file.sensor + ")")));
  if (E.source && !have.some(x => madeKey(x) === madeKey(E.source))) sel.append(el("option", {value: madeKey(E.source)}, E.source.name + " (not saving to a file any more)"));
  sel.value = E.source ? madeKey(E.source) : "";
  const box = $("#fromnote"); box.replaceChildren();
  const m = madeOf(E.source);
  if (!E.source) return;
  if (E.shape) box.append(el("p", {class: "help"}, "The AI is told: " + E.shape));
  /* keep in step: the announcement or fact changed its sensor or switch since this card was made */
  const now = m && m.file ? {sensor: m.file.sensor, toggle: m.toggle || "", shape: m.file.shape} : null;
  if (!now) return;
  const diff = [];
  if (now.sensor && !E.entities.includes(now.sensor)) diff.push("it now writes " + now.sensor);
  if (now.toggle && now.toggle !== E.toggle) diff.push("its show / hide switch is now " + now.toggle);
  if (now.shape !== E.shape) diff.push("what is in its file changed");
  if (!diff.length) return;
  box.append(el("div", {class: "note warn"}, el("div", {}, el("b", {}, m.name + " changed: "), diff.join(", ") + ". "),
    el("button", {class: "btn sm", onclick: () => { useSource(m, true); }}, "Update this card's setup")));
}
function useSource(x, update) {
  const oldSensor = (madeOf(E.source) || {}).file ? madeOf(E.source).file.sensor : "";
  E.source = {kind: x.kind, id: x.id, name: x.name}; E.shape = x.file.shape || "";
  E.entities = E.entities.filter(e => !oldSensor || e !== oldSensor || e === x.file.sensor);
  if (x.file.sensor && !E.entities.includes(x.file.sensor)) E.entities = [x.file.sensor].concat(E.entities);
  const oldT = E.toggle; if (x.toggle && (update || !E.toggle)) E.toggle = x.toggle;
  if (!update && !E.request.trim()) {
    const f = x.file.fields || [], by = r => f.filter(y => y.as === r).map(y => y.key).join(" and ");
    E.request = "A glass card for my " + x.name + " " + x.kind + "." + (f.length && x.kind === "announcement"
      ? (by("title") ? " Show " + by("title") + " as the title." : "") + (by("text") ? " Show " + by("text") + " as the main text, scrolling if it is long." : "") + (by("small") ? " Put " + by("small") + " small and dim at the bottom." : "")
      : x.kind === "fact" && f.length ? " Rotate through the items, one at a time." : " Show the text, scrolling if it is long.");
    $("#request").value = E.request;
  }
  if (!E.name || E.name === "My card") { E.name = x.name + " card"; $("#name").value = E.name; }
  drawPickers(); if (E.toggle !== oldT) applyToggle(oldT); drawFrom(); markDirty();
}
$("#fromsel").onchange = () => {
  const v = $("#fromsel").value, x = MADE.find(y => madeKey(y) === v);
  if (!v) { E.source = null; E.shape = ""; drawFrom(); markDirty(); return; }
  if (x && x.file) useSource(x, false);
};
async function loadMade() { const d = await api("made"); MADE = (d && d.items) || []; }
/* the Announcements or Facts tab handed us something to build a card for */
async function takeHandoff() {
  let h = null;
  try { h = JSON.parse(localStorage.getItem("aib_card_from") || "null"); localStorage.removeItem("aib_card_from"); } catch (e) { h = null; }
  if (!h || Date.now() - (h.t || 0) > 120000) return;
  await loadMade();
  const x = MADE.find(y => y.kind === h.kind && y.id === h.id && y.file) || {kind: h.kind, id: h.id || "", name: h.name, toggle: h.toggle, file: {sensor: h.sensor, shape: h.shape, fields: []}};
  x.file = Object.assign({}, x.file, {sensor: h.sensor || x.file.sensor, shape: h.shape || x.file.shape});  /* what the editor has now, even if not saved yet */
  if (h.toggle) x.toggle = h.toggle;
  openEditor(blank(), {}); useSource(x, false);
  say("Started from " + x.name + ". Describe the look if you like, then Build the card.", "ok");
}
window.addEventListener("storage", e => { if (e.key === "aib_card_from" && e.newValue) takeHandoff(); });
onChanged(async () => { await loadMade(); if (!$("#v-lib").hidden) renderLib(); else drawFrom(); });
const openNew = () => openEditor(blank(), {});
const openItem = it => openEditor(Object.assign({}, it.state || {}, {name: (it.state || {}).name || it.name}), {id: it.id, saved: true});
$("#newcard").onclick = openNew;

document.addEventListener("input", e => {
  if (!e.target.closest("#v-edit")) return;
  const id = e.target.id;
  if (id === "name") E.name = e.target.value;
  else if (id === "request") E.request = e.target.value;
  else if (id === "yaml") E.yaml = e.target.value;
  else return;
  markDirty();
});
$("#style").onchange = () => { E.style = $("#style").value; markDirty(); };

let armedBack = null;
$("#back").onclick = () => {
  const b = $("#back");
  if (dirty && !armedBack) {
    b.textContent = "Leave without saving?"; b.classList.add("danger");
    armedBack = setTimeout(() => { armedBack = null; b.textContent = "← All cards"; b.classList.remove("danger"); }, 3500); return;
  }
  clearTimeout(armedBack); armedBack = null; b.textContent = "← All cards"; b.classList.remove("danger");
  dirty = false; showView("lib"); loadLib();
};

const stateOut = () => ({name: E.name, request: E.request, entities: E.entities, toggle: E.toggle, style: E.style, yaml: $("#yaml").value, notes: E.notes, needs: E.needs, unknown: E.unknown, source: E.source, shape: E.shape});
$("#save").onclick = async () => {
  E.name = $("#name").value.trim() || "My card"; E.yaml = $("#yaml").value;
  const b = $("#save"); b.disabled = true; say("Saving...");
  const r = await cd("library/save", {id: cur.id, name: E.name, state: stateOut()});
  b.disabled = false;
  if (!r.ok) { say(r.error || "That failed.", "bad"); return; }
  cur.id = r.item.id; cur.saved = true; dirty = false; paint(); say("Saved.", "ok"); notifyChanged("cards");
};

/* ---------- build / revise ---------- */
const setBusy = on => { busy = on; ["build", "revise", "chk", "preview", "swmake"].forEach(i => { $("#" + i).disabled = on; }); };
const spinner = t => [el("span", {class: "spin"}), t];
async function generate(feedback) {
  if (busy) return;
  const box = feedback ? $("#ymsg") : $("#bres");
  if (!feedback && !E.request.trim()) { box.className = "msg warn"; box.textContent = "Describe the card first."; return; }
  if (feedback && !feedback.trim()) { box.className = "msg warn"; box.textContent = "Type what to change first."; return; }
  setBusy(true); box.className = "msg"; box.replaceChildren(...spinner("Asking your AI Task. This can take a minute or two..."));
  const r = await cd("generate", {request: E.request, entities: E.entities, toggle: E.toggle, style: E.style, yaml: feedback ? $("#yaml").value : "", feedback: feedback || "",
    source: E.source && E.shape ? {name: E.source.name, kind: E.source.kind, sensor: (madeOf(E.source) || {file: {}}).file.sensor || E.entities[0] || "", shape: E.shape} : null});
  setBusy(false);
  if (!r.ok) {
    box.className = "msg bad"; box.replaceChildren(r.error || "That failed.");
    if (r.raw) box.append(el("details", {style: "margin-top:8px"}, el("summary", {}, "What the AI sent back"), el("pre", {}, r.raw)));
    return;
  }
  E.yaml = r.yaml; E.notes = r.notes || ""; E.needs = r.needs || []; E.unknown = r.unknown || [];
  if (r.name && (!$("#name").value.trim() || $("#name").value === "My card")) { E.name = r.name; $("#name").value = r.name; }
  $("#yaml").value = E.yaml; $("#feedback").value = ""; $("#pres").replaceChildren();
  box.className = "msg ok"; box.textContent = feedback ? "Updated. Read it before you copy it." : "Built. Read it before you copy it.";
  drawCardSec(); markDirty();
  try { $("#cardsec").scrollIntoView({behavior: "smooth", block: "start"}); } catch (e) { /* ignore */ }
}
let armedBuild = null;
$("#build").onclick = () => {
  const b = $("#build");
  if ((E.yaml || "").trim() && !armedBuild) {  /* it replaces the card in the box, so ask twice */
    b.textContent = "Tap again: replaces the card below"; b.classList.add("danger");
    armedBuild = setTimeout(() => { armedBuild = null; b.classList.remove("danger"); drawCardSec(); }, 3500); return;
  }
  clearTimeout(armedBuild); armedBuild = null; b.classList.remove("danger"); generate("");
};
$("#revise").onclick = () => generate($("#feedback").value);

$("#chk").onclick = async () => {
  const m = $("#ymsg"); setBusy(true); m.className = "msg"; m.replaceChildren(...spinner("Checking..."));
  const r = await cd("check", {yaml: $("#yaml").value});
  setBusy(false);
  if (!r.ok) { m.className = "msg bad"; m.textContent = r.error; return; }
  E.yaml = $("#yaml").value; E.needs = r.needs || []; E.unknown = r.unknown || []; drawNotes();
  m.className = "msg ok"; m.textContent = "That is a valid card." + (E.unknown.length ? " Some entities don't exist, see above." : "");
};
$("#copy").onclick = async () => {
  const m = $("#ymsg"), ta = $("#yaml"), ok = await copyText(ta.value);
  m.className = "msg " + (ok ? "ok" : "warn");
  m.textContent = ok ? "Copied. In your dashboard, add a Manual card and paste." : "Your browser blocked copying. Tap the box, select all, and copy.";
  if (!ok) { ta.focus(); ta.select(); }
};
$("#swmake").onclick = async () => {
  setBusy(true); say("Making the switch...");
  const r = await api("ann/card_switch", {name: ($("#name").value.trim() || "Card") + " visible"});
  setBusy(false);
  if (!r.ok) { say(r.error, "bad"); return; }
  if (!ENT.some(e => e.id === r.entity)) ENT.push({id: r.entity, name: r.entity});
  const old = E.toggle; E.toggle = r.entity; drawPickers(); markDirty(); applyToggle(old);
  if (!$("#msg").textContent) say(r.message, "ok");
};

/* ---------- preview ---------- */
const frameDoc = (title, html) => '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;min-height:100%}body{padding:14px;background:linear-gradient(135deg,#1c2b4d,#3b1d5e 55%,#0e3b3d);color:#fff;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}ha-card{display:block;position:relative;border-radius:12px;box-sizing:border-box;overflow:hidden}.t{font-size:20px;padding:14px 16px 0}</style><ha-card>'
  + (title ? '<div class="t">' + esc(title) + "</div>" : "") + html + "</ha-card>";
$("#preview").onclick = async () => {
  const b = $("#pres"); setBusy(true); b.replaceChildren(el("p", {class: "dim small"}, ...spinner("Asking Home Assistant to render it...")));
  const r = await cd("preview", {yaml: $("#yaml").value});
  setBusy(false); b.replaceChildren();
  if (!r.ok) { b.append(el("div", {class: "note bad"}, el("div", {}, r.error))); return; }
  if (r.note) b.append(el("div", {class: "note"}, el("div", {}, r.note)));
  (r.items || []).forEach((it, i) => {
    b.append(el("div", {class: "prevhead"}, el("b", {}, "Card " + (i + 1)), el("span", {class: "pill plain"}, it.type)));
    if (it.error) { b.append(el("div", {class: "note bad"}, el("div", {}, el("b", {}, "Home Assistant could not render it"), el("pre", {}, it.error)))); return; }
    if (it.type === "markdown") { b.append(el("pre", {}, it.html)); b.append(el("p", {class: "help"}, "Markdown is shown as plain text here. Home Assistant draws it properly on the dashboard.")); return; }
    const h = (it.html.match(/ha-card[^}]*?height:\s*(\d+)px/) || [])[1];
    b.append(el("iframe", {class: "prev", sandbox: "", srcdoc: frameDoc(it.title, it.html), style: "height:" + Math.min(Math.max((+h || 320) + 50, 180), 820) + "px;resize:vertical"}));
  });
  if ((r.items || []).length) b.append(el("p", {class: "help"}, "Rotating and scrolling cards animate, so give it a few seconds. Entities in the template are live."));
};

/* ---------- start ---------- */
Promise.all([api("ann/options"), api("ann/entities").then(r => Array.isArray(r) ? r : []), loadMade()]).then(async ([o, e]) => {
  if (o && !o.error) S = o; ENT = e; setupNote(); await loadLib(); showView("lib");
  await takeHandoff();
});

askAI($("#askhost"), () => ({section: "cards", name: $("#name").value.trim(), ai: S.ai_task_entity || "",
  content: "WHAT THE OWNER ASKED FOR:\n" + $("#request").value + "\n\nLOOK: " + $("#style").value + "\n\nTHE CARD YAML:\n" + $("#yaml").value,
  yamls: [{label: "Card", text: $("#yaml").value}]}),
  {placeholder: "Ask anything about this card, e.g. \"why is the text cut off?\" or \"how do I make it scroll?\" (optional when you press Check or Suggest)"});

/* Announcements page: library of saved announcements, editor, helper and settings. */
let O = {}, S = {}, ENT = [], LIB = [], FOUND = [], mem = {};
let cur = {id: null, isNew: true, pushed: false}, dirty = false, view = "lib", OPEN = "", HEL = {entity: "", goal: "", idea: ""};
let editorReady = false, rawMode = false;
let AUTO = SCHED.fill({watch: "", home: []});  /* the schedule being edited; the panel changes it in place */
const FACT = {home: []};  /* the default "someone is home" list, set in Facts > Settings */
const CARD = {sw: ""};  /* the dashboard-card switch picked in the editor (the picker widget keeps no value of its own) */
let IMPORT = {};  /* for an announcement converted from an imported script or automation: its original YAML, and the automation it replaces */

const aiName = () => S.helper_ai_task_entity || S.ai_task_entity || "";
const ann = (path, body) => api("ann/" + path, body);
const ASK = "Made with Announcement Maker";  // marker the server uses to recognise scripts made here
const DEF = "Default", DEF_STYLE = "Sound natural and friendly. No special personality, character, jokes or slang. Just clear and helpful.";
const persList = () => (S.personalities && S.personalities.length ? S.personalities : [{name: DEF, style: DEF_STYLE}]);


/* ---------- save to a file (plain text, or separate JSON fields for a card) ---------- */
let TXT_PREFIX = "file_reader/overwrite/";  /* the MQTT topic prefix from Facts > Settings, loaded at start */
const TXT_ROLES = [["title", "Title (top)"], ["text", "Text (middle)"], ["small", "Bottom line (small)"], ["hide", "Don't show"]];
const txtClean = f => String(f || "").replace(/[^A-Za-z0-9_\-./]/g, "");
const fieldKey = k => String(k || "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
/* the fields mode is only used when it is switched on and has at least one field. Returns null otherwise. */
function annFields(s) {
  const t = s && s.txt;
  if (!t || !t.on || t.mode !== "fields" || s.raw != null) return null;
  const seen = new Set(), fields = [];
  (t.fields || []).forEach(f => {
    const key = fieldKey(f.key);
    if (!key || seen.has(key) || key === "notification") return;
    seen.add(key); fields.push({key, hint: String(f.hint || "").trim(), as: ["title", "text", "small", "hide"].includes(f.as) ? f.as : "text"});
  });
  if (!fields.length) return null;
  const say = fields.some(f => f.key === t.say) ? t.say : (fields.find(f => f.as === "text") || fields[0]).key;
  return {fields, say};
}
const txtFileOf = (t, name) => txtClean(t.file) || ((slug(name) || "announcement").slice(0, 54) + (t.mode === "fields" ? ".json" : ".txt"));
const txtTopicOf = (t, name) => { const f = txtFileOf(t, name); if (f.includes("/")) return f; const p = TXT_PREFIX && !TXT_PREFIX.endsWith("/") ? TXT_PREFIX + "/" : TXT_PREFIX; return p + f; };
const txtSensorOf = (t, name) => {
  const s = String(t.sensor || "").trim(); if (s) return s;
  const b = (txtFileOf(t, name).split("/").pop() || "").replace(/\.[^.]*$/, "");
  return "sensor.read_" + (b || "announcement");
};
/* what the saved file looks like, told to the Cards AI so it can build a card before the file has data */
function annShape(t, name) {
  const F = annFields({txt: Object.assign({}, t, {on: true})});
  if (t.mode === "fields" && F) {
    const role = {title: "title", text: "main text", small: "small bottom line", hide: "not shown"};
    return "Its content attribute holds ONE JSON object written by the \"" + name + "\" announcement, for example {" + F.fields.map(f => JSON.stringify(f.key) + ": \"...\"").join(", ") + "}. "
      + "Fields: " + F.fields.map(f => f.key + " = " + (f.key === F.say ? "the spoken announcement" : (f.hint || "short text")) + " (show as " + role[f.as] + ")").join("; ") + ". "
      + "Strip ```json and ``` then parse with from_json(default={}). If it is not JSON, show the raw text.";
  }
  return "Its content attribute holds the plain text of the last \"" + name + "\" announcement (what it said out loud).";
}

/* ---------- presets ---------- */
const PRE = {
  "Weather & News": {name: "Weather and News", types: ["household", "locations", "weather", "news"], task: "Give a quick weather rundown for today and the week ahead, then the top news: local first, then US, then world."},
  "Welcome Home": {name: "Welcome Home", types: ["household", "locations", "calendar", "todo", "trash"], notify: 1, task: "Welcome home whoever just arrived. Go over the to-do list, remind us about the trash if it is going out, then run through what is on the calendar this week."},
  "You're Late": {name: "You're Late", types: ["household", "locations"], task: "Call out every person by name. Roast whoever is not home and work in where they are. Be nicer to whoever is home."},
  "Blank": {name: "My announcement", types: ["household"], task: ""}
};

/* ---------- your own pasted script ---------- */
const cleanId = x => { x = String(x || "").trim().toLowerCase().replace(/^script\./, ""); return /^[a-z0-9_]{1,60}$/.test(x) ? x : "" };
function getAlias(y) {
  const m = String(y).match(/^alias:[ \t]*(.+?)[ \t]*$/m); if (!m) return "";
  let v = m[1]; if (/^[>|]/.test(v)) return "";
  if (v[0] === '"' && v.endsWith('"')) { try { return JSON.parse(v) } catch (e) { return v.slice(1, -1) } }
  if (v[0] === "'" && v.endsWith("'")) return v.slice(1, -1).replace(/''/g, "'");
  return v;
}
function setAlias(y, name) {
  const line = "alias: " + JSON.stringify(name || "Announcement");
  return /^alias:.*$/m.test(y) ? y.replace(/^alias:.*$/m, () => line) : line + "\n" + y;
}
const defAuto = () => Object.assign({on: false, every: 0, unit: "hours", at: "", watch: "", watchAttr: "", watchFor: 0, home: []}, SCHED.extra());
const autoSummary = a => SCHED.summary(SCHED.fill(Object.assign({}, a)));
/* the schedule: an automation (<script id>_auto) that calls the script. Works for form scripts and pasted ones alike. */
function makeAuto(s0, sid) {
  const a = SCHED.fill(Object.assign(defAuto(), (s0 && s0.auto) || {}));
  if (!a.on) return "";
  const T = SCHED.triggers(a);
  if (!T.length) return "";
  const y = "alias: " + JSON.stringify((s0.name || "Announcement") + " (auto)") + "\ndescription: " + ASK + "\nmode: single\nmax_exceeded: silent\ntriggers:\n" + T.join("") + SCHED.conditionsYaml(a);
  return y + "actions:\n  - action: script." + sid + "\n";
}
const autoProblem = s => s.auto && s.auto.on && !makeAuto(s, "x") ? "The schedule needs a repeat time, a time of day or an entity to watch." : "";
const autoState = () => Object.assign(SCHED.clone(AUTO), {on: $("#auto-on").checked});
function drawAuto() {
  $("#schedpanel").replaceChildren(SCHED.panel(AUTO, {defaultHome: FACT.home, onChange: () => { gen(); markDirty(); }}));
}
function applyAuto(x) {
  AUTO = SCHED.fill(Object.assign(defAuto(), SCHED.clone(x || {})));
  $("#auto-on").checked = !!AUTO.on; drawAuto();
}

function setRaw(on) {
  rawMode = !!on;
  $("#autonum").textContent = rawMode ? "3" : "6";
  $("#formcards").hidden = rawMode; $("#rawcard").hidden = !rawMode;
  $("#trycard").hidden = rawMode; $("#ymldet").hidden = rawMode;
}

/* ---------- views ---------- */
function showView(v) {
  view = v;
  const editing = v === "edit";
  $("#chrome").hidden = editing;
  ["lib", "help", "set", "edit"].forEach(k => $("#v-" + k).hidden = k !== v);
  $$("#tabs .tab").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  $("#dock").hidden = v !== "set";
  try { window.scrollTo(0, 0) } catch (e) {}
}
$$("#tabs .tab").forEach(b => b.onclick = () => { showView(b.dataset.v); if (b.dataset.v === "lib") loadLib(); });

function setupNote() {
  const names = {ai_task_entity: "an AI Task", tts_entity: "a text-to-speech engine", speaker: "a main speaker"};
  const miss = Object.keys(names).filter(k => !S[k]);
  const box = $("#setupnote"); box.replaceChildren();
  if (!miss.length) return;
  box.append(el("div", {class: "note warn"}, el("div", {}, el("b", {}, "Finish setup to make announcements. "), "Still needed: " + miss.map(k => names[k]).join(", ") + "."),
    el("button", {class: "btn sm", onclick: () => showView("set")}, "Open Settings")));
}

/* ---------- library ---------- */
const outsSummary = st => {
  const o = st.outs || [], p = [];
  if (o.includes("tts")) p.push("Speaker");
  const a = o.filter(x => x.startsWith("a:")).length, n = o.filter(x => x.startsWith("n:")).length;
  if (a) p.push(a + " Alexa");
  if (n) p.push(n + " phone" + (n > 1 ? "s" : ""));
  return p.join(", ") || "No output";
};
function flash(text, cls) { const m = $("#libmsg"); m.className = "msg " + (cls || ""); m.textContent = text || ""; }

async function loadLib() {
  const d = await ann("library");
  if (d.error) { flash(d.error, "bad"); return; }
  LIB = d.items || []; FOUND = d.found || [];
  if ((d.renamed || []).length) flash("Picked up from Home Assistant: " + d.renamed.map(x => x.from + " is now " + x.to).join(", ") + ".", "ok");
  $("#libcount").textContent = LIB.length + FOUND.length;
  renderLib();
}

function renderLib() {
  const live = LIB.filter(x => x.pushed_at || x.in_ha).length;
  $("#libsub").textContent = LIB.length + FOUND.length ? (LIB.length + FOUND.length) + " announcement" + (LIB.length + FOUND.length === 1 ? "" : "s") + ", " + live + " in Home Assistant" : "";
  $("#updall").hidden = !LIB.some(x => x.pushed_at);

  /* announcements saved in this browser before the library existed */
  const lg = $("#legacy"); lg.replaceChildren();
  try { mem = JSON.parse(localStorage.getItem("ann") || "{}") } catch (e) { mem = {} }
  const old = Object.keys(mem);
  if (old.length) {
    lg.append(el("div", {class: "note", style: "margin-bottom:12px"}, el("div", {}, el("b", {}, old.length + " saved setup" + (old.length > 1 ? "s" : "") + " found in this browser. "), "Move them into My announcements so they are kept with the add-on."),
      el("button", {class: "btn sm", onclick: moveOld}, "Move them")));
  }

  const box = $("#cards"); box.replaceChildren();
  if (!LIB.length && !FOUND.length) {
    box.style.display = "block";
    box.append(el("div", {class: "card empty"}, el("h3", {}, "No announcements yet"),
      el("p", {}, "Pick what the AI should know, say what it should do, and choose where it plays."),
      el("div", {class: "row"}, el("button", {class: "btn primary", onclick: () => openNew()}, "Make your first announcement"))));
  } else box.style.display = "";
  LIB.forEach(it => box.append(libCard(it)));

  const fb = $("#found"); fb.replaceChildren();
  if (FOUND.length) {
    const c = el("div", {class: "card", style: "margin-top:18px"}, el("div", {class: "ch"}, el("h2", {}, "Made earlier, in Home Assistant"),
      el("p", {}, "These scripts were pushed before saving existed. Open one to edit it here.")));
    const l = el("div", {class: "list"});
    FOUND.forEach(f => {
      const msg = el("span", {class: "dim small"});
      const del = el("button", {class: "btn danger sm"}, "Delete");
      confirmTap(del, "Tap again to delete", () => removeAnn(f.id, true, true));
      l.append(el("div", {class: "li srcrow"}, el("div", {class: "t"}, el("b", {}, f.name), el("small", {class: "mono"}, "script." + f.id)), msg,
        el("button", {class: "btn sm", onclick: () => openFound(f, msg)}, "Open"), del));
    });
    c.append(l); fb.append(c);
  }
}

function libCard(it) {
  const st = it.state || {};
  const status = !it.pushed_at && !it.in_ha ? ["warn", "Draft, not in Home Assistant"] : it.in_ha ? ["ok", "In Home Assistant"] : ["bad", "Missing in Home Assistant"];
  const msg = el("div", {class: "msg", style: "margin:0"});
  const del = el("button", {class: "btn danger sm"}, "Delete");
  confirmTap(del, it.in_ha ? "Tap again: removes the script" + (it.auto_in_ha ? " and schedule" : "") + " too" : "Tap again to delete", () => removeAnn(it.id, !!it.in_ha));
  const run = el("button", {class: "btn sm", disabled: !it.in_ha, title: it.in_ha ? "Run it now" : "Push it to Home Assistant first", onclick: async () => {
    run.disabled = true; msg.className = "msg"; msg.textContent = "Starting...";
    const r = await ann("run", {id: it.id}); msg.className = "msg " + (r.ok ? "ok" : "bad"); msg.textContent = r.ok ? "Started." : (r.detail || r.error); run.disabled = false;
  }}, "Run now");
  const dup = el("button", {class: "btn sm", onclick: async () => {
    const id = uniqueId(slug((it.name || it.id) + " copy"));
    const r = await ann("library/save", {id, name: (it.name || it.id) + " copy", state: Object.assign({}, st, {name: (it.name || it.id) + " copy", auto: Object.assign(defAuto(), st.auto || {}, {on: false})}, st.raw != null ? {raw: setAlias(st.raw, (it.name || it.id) + " copy")} : {})});
    if (r.ok) { flash("Copied as a draft: " + id, "ok"); loadLib(); } else flash(r.error, "bad");
  }}, "Duplicate");
  return el("div", {class: "card ann"},
    el("div", {class: "top"}, el("div", {style: "min-width:0"}, el("h3", {}, it.name || it.id), el("div", {class: "dim small mono"}, "script." + it.id)), el("span", {class: "pill " + status[0]}, status[1])),
    el("div", {class: "clamp"}, st.raw != null ? "Your own script, kept exactly as you wrote it. Open it to convert it to the normal form." : (st.task || "No instructions yet.")),
    el("div", {class: "meta"}, st.raw != null ? el("span", {class: "pill plain"}, "Own script") : [el("span", {class: "pill plain"}, (st.src || []).length + " data source" + ((st.src || []).length === 1 ? "" : "s")), el("span", {class: "pill plain"}, outsSummary(st))],
      st.cardSw ? el("span", {class: "pill plain", title: st.cardSw}, "Card switch") : null,
      st.auto && st.auto.on ? (!it.auto_in_ha ? el("span", {class: "pill warn"}, "Schedule not pushed") : it.auto_on ? el("span", {class: "pill ok"}, "Runs " + autoSummary(st.auto)) : el("span", {class: "pill warn"}, "Schedule is off in HA")) : null,
      el("span", {class: "pill plain"}, "Edited " + ago(it.updated))),
    el("div", {class: "acts"}, el("button", {class: "btn primary sm", onclick: () => openItem(it)}, "Edit"), run, dup,
      renameButton(it.name || it.id, (n, m) => api("rename", {match_id: m, lib: "ann", id: it.id, name: n}), r => { flash(r.in_ha ? "Renamed in Home Assistant too. The script id stays " + it.id + "." + (r.note ? " " + r.note : "") : "Renamed. Push it to use the new name in Home Assistant.", "ok"); loadLib(); }), del), msg);
}

async function removeAnn(id, alsoScript, found) {
  const r = await ann("library/delete", {id, delete_script: !!alsoScript});
  if (r.ok) { flash(r.script_deleted ? "Deleted " + id + " and its script in Home Assistant." : "Deleted " + id + ".", "ok"); loadLib(); } else flash(r.error, "bad");
}

async function moveOld() {
  let n = 0;
  for (const k of Object.keys(mem)) {
    const id = uniqueId(slug(k)), r = await ann("library/save", {id, name: k, state: Object.assign({}, mem[k], {name: mem[k].name || k})});
    if (r.ok) { n++; delete mem[k]; }
  }
  try { localStorage.setItem("ann", JSON.stringify(mem)) } catch (e) {}
  flash("Moved " + n + " saved setup" + (n === 1 ? "" : "s") + " into the library as drafts.", "ok");
  loadLib();
}

$("#updall").onclick = () => {
  const b = $("#updall");
  if (!b.dataset.armed) {
    b.dataset.armed = 1; b.textContent = "Tap again to push all"; b.classList.add("primary");
    setTimeout(() => { delete b.dataset.armed; b.textContent = "Update all in Home Assistant"; b.classList.remove("primary") }, 4000); return;
  }
  delete b.dataset.armed; b.classList.remove("primary"); b.textContent = "Update all in Home Assistant"; updateAll();
};
async function updateAll() {
  const todo = LIB.filter(x => x.pushed_at); let ok = 0; const bad = [];
  flash("Updating " + todo.length + "...", "");
  for (const it of todo) {
    const r = await ann("push", {id: it.id, yaml: makeYaml(Object.assign({src: [], outs: [], pers: {}}, it.state)), auto_yaml: makeAuto(Object.assign({}, it.state, {name: (it.state || {}).name || it.name}), it.id), state: it.state});
    if (r.ok) ok++; else bad.push(it.name + ": " + (r.detail || r.error));
  }
  flash("Updated " + ok + " of " + todo.length + " with your current settings." + (bad.length ? " Failed: " + bad.join("; ") : ""), bad.length ? "bad" : "ok");
  loadLib();
}

/* ---------- ids ---------- */
function takenIds() {
  const s = new Set([...LIB.map(x => x.id), ...FOUND.map(x => x.id)]);
  ENT.forEach(e => { if (e.id.startsWith("script.")) s.add(e.id.slice(7)); });
  return s;
}
function uniqueId(base) {
  const t = takenIds(); let id = base, n = 2;
  while (t.has(id)) id = base.slice(0, 55) + "_" + (n++);
  return id;
}

/* ---------- editor: form <-> state ---------- */
function pickBox(parent, attr, key, label, on) {
  const i = el("input", {type: "checkbox", checked: !!on}); i.dataset[attr] = key;
  parent.append(el("label", {class: "pick", title: label}, i, el("span", {}, label)));
}
function st() {
  if (rawMode) return {name: $("#name").value, raw: $("#rawyaml").value, auto: autoState()};
  return {name: $("#name").value, auto: autoState(), src: $$("[data-s]:checked").map(c => c.dataset.s), outs: $$("[data-o]:checked").map(c => c.dataset.o),
    json: $$('[data-o^="n:"]:checked').length > 0, pers: Object.fromEntries($$("[data-p]").map(t => [t.dataset.p, t.value])),
    usePers: $("#usePers").checked && !!O.personality_select, one: $("#one").value, len: +$("#len").value || 1000,
    task: $("#task").value.trim(), vol: +$("#vol").value / 100, pause: $("#pause").checked,
    cardSw: CARD.sw, cardWhen: $("#cardwhen").value || "talk", cardOff: $("#cardoff").checked, cardHold: Math.max(0, Math.round(+$("#cardhold").value || 0))};
}
function drawCardPick() {
  $("#cardpick").replaceChildren(picker(["input_boolean"], false, () => CARD.sw ? [CARD.sw] : [], a => { CARD.sw = a[0] || ""; gen(); markDirty(); }));
}
$("#cardmake").onclick = async () => {
  const m = $("#cardmsg"), b = $("#cardmake"); b.disabled = true; m.className = "msg"; m.textContent = "Making the switch...";
  const r = await ann("card_switch", {name: ($("#name").value.trim() || "Announcement") + " card"});
  b.disabled = false; m.className = "msg " + (r.ok ? "ok" : "bad"); m.textContent = r.ok ? r.message : r.error;
  if (!r.ok) return;
  if (!ENT.some(e => e.id === r.entity)) ENT.push({id: r.entity, name: r.entity});
  CARD.sw = r.entity; drawCardPick(); gen(); markDirty();
};
function applyState(s) {
  applyAuto(s.auto);
  if (s.raw != null) { setRaw(true); if (s.name != null) $("#name").value = s.name; $("#rawyaml").value = s.raw; gen(); return; }
  setRaw(false);
  if (s.name != null) $("#name").value = s.name;
  $$("[data-s]").forEach(c => c.checked = (s.src || []).includes(c.dataset.s));
  $$("[data-o]").forEach(c => c.checked = (s.outs || []).includes(c.dataset.o));
  $$("[data-p]").forEach(t => { if (s.pers && s.pers[t.dataset.p] != null) t.value = s.pers[t.dataset.p] });
  if (s.usePers != null) $("#usePers").checked = !!s.usePers && !!O.personality_select;
  if (s.one) $("#one").value = s.one;
  if (!$("#one").value) $("#one").value = DEF;  /* the one it used was removed in Settings */
  if (s.len) $("#len").value = s.len;
  $("#task").value = s.task ?? s.extra ?? "";
  if (s.vol != null) $("#vol").value = Math.round(s.vol * 100);
  if (s.pause != null) $("#pause").checked = s.pause;
  CARD.sw = s.cardSw || ""; drawCardPick();
  $("#cardwhen").value = s.cardWhen === "start" ? "start" : "talk";
  $("#cardoff").checked = s.cardOff != null ? !!s.cardOff : true;
  $("#cardhold").value = s.cardHold || 0;
  gen();
}
/* Rebuild the option lists (sources, outputs, personalities) from settings. Keeps what is already ticked. */
function build() {
  const prev = editorReady ? st() : null;
  O = S; if (!Array.isArray(S.sources)) S.sources = migrate(S);
  ["srcs", "persbox", "presets", "outs"].forEach(i => $("#" + i).replaceChildren());
  usable().forEach(s => pickBox($("#srcs"), "s", s.id, s.label, s.type === "household"));
  if (!usable().length) $("#srcs").append(el("p", {class: "dim small"}, "No data sources yet. Add some in Settings."));
  if (O.speaker && O.tts_entity) pickBox($("#outs"), "o", "tts", "Main speaker (TTS)", 1);
  (O.alexa_targets || []).forEach(a => pickBox($("#outs"), "o", "a:" + a, "Alexa: " + a, 1));
  (O.notify_targets || []).forEach(a => pickBox($("#outs"), "o", "n:" + a, "Phone: " + a, 0));
  if (!$("#outs").children.length) $("#outs").append(el("p", {class: "dim small"}, "No speakers or phones yet. Add them in Settings."));
  $("#one").replaceChildren(...persList().map(p => el("option", {value: p.name}, p.name)));
  persList().forEach(p => {
    const t = el("textarea", {value: p.style || ""}); t.dataset.p = p.name; $("#persbox").append(el("label", {class: "l"}, p.name), t);
  });
  const hasSel = !!O.personality_select;
  $("#selwrap").hidden = !hasSel; $("#usePers").checked = hasSel;
  $("#len").value = O.default_length || 1000; $("#vol").value = O.default_volume || 70;
  drawCardPick();
  Object.entries(PRE).forEach(([k, p]) => {
    $("#presets").append(el("button", {class: "chip", onclick: () => {
      const have = usable().map(x => x.type), miss = p.types.filter(t => !have.includes(t));
      $("#pnote").textContent = miss.length ? "No source set up for: " + miss.map(t => TYPES[t]).join(", ") + " (add it in Settings)." : "";
      applyState({name: p.name, src: usable().filter(x => p.types.includes(x.type)).map(x => x.id), task: p.task,
        outs: $$("[data-o]").map(c => c.dataset.o).filter(o => !o.startsWith("n:") || p.notify)});
      markDirty();
    }}, k));
  });
  if (prev) applyState(prev);
  editorReady = true;
}

/* ---------- editor: script text ---------- */
function makeYaml(s0, o) {
  if (s0.raw != null) return s0.raw;  /* a pasted script is pushed exactly as written */
  o = o || {}; const s = o.silent ? Object.assign({}, s0, {outs: [], json: false, pause: false, cardSw: ""}) : s0;
  const chosen = s.src.map(id => usable().find(x => x.id === id)).filter(Boolean), n = JSON.stringify(s.name || "Announcement"), A = O.speaker || "media_player.SET_ME", players = O.music_players || [], flag = O.talking_flag,
    sp_on = s.outs.includes("tts") && !!O.tts_entity && !!O.speaker, al = (O.alexa_targets || []).filter(a => s.outs.includes("a:" + a)), nt = (O.notify_targets || []).filter(a => s.outs.includes("n:" + a)), speak = sp_on || al.length > 0;
  s.json = s.json || nt.length > 0;
  const F = annFields(s0), tx = s0.txt && s0.txt.on && s0.raw == null && !o.silent ? s0.txt : null;  /* tests without sound never write the file */
  const cs = String(s.cardSw || "").trim(), cardOn = /^input_boolean\.[a-z0-9_]+$/.test(cs);
  const cardStep = alias => `  - alias: ${alias}\n    action: input_boolean.turn_on\n    target:\n      entity_id: ${cs}\n`;
  let y = "alias: " + n + "\ndescription: " + ASK + "\nsequence:\n  - variables:\n      current_time: '{{ now().strftime(''%A, %B %-d %Y %-I:%M %p %Z'') }}'\n";
  chosen.forEach(c => { y += genPre(c) });
  if (chosen.length) y += "  - alias: Load data sources\n    variables:\n" + chosen.map(c => { const b = body(c).trim(); return b ? `      src_${c.id}: |-\n` + ind(b, 8) : `      src_${c.id}: ""` }).join("\n") + "\n";
  if (speak && s.pause && players.length) y += "  - alias: Pause music if playing\n    if:\n      - condition: state\n        entity_id:\n" + players.map(p => "          - " + p).join("\n") + "\n        state: playing\n        match: any\n    then:\n      - action: media_player.media_pause\n        target:\n          entity_id: " + players[0] + "\n";
  if (speak && flag) y += `  - action: input_boolean.turn_on\n    target:\n      entity_id: ${flag}\n`;
  if (sp_on) y += `  - delay:\n      seconds: 3\n  - action: media_player.volume_set\n    target:\n      entity_id: ${A}\n    data:\n      volume_level: ${s.vol}\n`;
  const task = r => {
    const L = ["Current time: {{ current_time }}. Use this to understand what 'tonight', 'this morning', 'Friday' etc. mean."];
    chosen.forEach(c => L.push(c.label.toUpperCase() + ":\n{{ src_" + c.id + " }}"));
    L.push("YOUR TASK: " + (s.task || "Give a short, useful rundown of the information above."));
    L.push("STYLE" + (F ? " (for the spoken part)" : "") + ": " + r + "\nNo markdown, bullet points, quotation marks or emojis. Keep it under " + s.len + " characters. One continuous flowing monologue that sounds natural read aloud by text-to-speech.");
    if (F) L.push("Output ONLY a JSON object, no code fences, no other text, with exactly these keys:\n" + F.fields.map(f => JSON.stringify(f.key) + ": " + (f.key === F.say
      ? "the full spoken announcement. Follow YOUR TASK and STYLE above for this one" + (f.hint ? " (" + f.hint + ")" : "") + "."
      : (f.hint || "short text") + ". Short plain text for a dashboard card, no markdown.")).join("\n") + (nt.length ? '\n"notification": one short sentence banner under 100 characters.' : ""));
    else if (s.json) L.push('Output ONLY a JSON object, no code fences, no other text, exactly like this:\n{"speech": "the full monologue", "notification": "one short sentence banner under 100 characters"}');
    return "- action: ai_task.generate_data\n  data:\n    task_name: " + n + "\n    entity_id: " + (O.ai_task_entity || "ai_task.SET_ME") + "\n    instructions: |-\n" + ind(L.join("\n\n"), 6) + "\n  response_variable: announcement";
  };
  const styleFor = k => s.pers[k] ?? s.pers[DEF] ?? DEF_STYLE;
  if (cardOn && s.cardWhen === "start") y += cardStep("Show dashboard card early");
  if (s.usePers) {
    y += "  - alias: Generate announcement\n    choose:\n";
    Object.keys(s.pers).forEach(k => { y += `      - conditions:\n          - condition: state\n            entity_id: ${O.personality_select}\n            state: ${JSON.stringify(k)}\n        sequence:\n` + ind(task(s.pers[k]), 10) + "\n" });
    y += "    default:\n" + ind(task(styleFor(DEF)), 6) + "\n";  /* dropdown on something unknown: use Default instead of saying nothing */
  } else y += ind(task(styleFor(s.one)), 2) + "\n";
  if (F) {  /* the answer is a JSON object: read it safely (code fences stripped), keep only the fields, speak the one picked */
    const item = F.fields.map(f => `'${f.key}': ((ann_json.get('${f.key}') or '') | string | trim)`).join(", ");
    y += "  - alias: Read the answer\n    variables:\n      ann_json: |-\n" + ind("{% set raw = announcement.data %}\n{% set d = (raw | string | replace('```json', '') | replace('```', '') | trim | from_json(default={})) if raw is string else raw %}\n{{ d if d is mapping else {} }}", 8) + "\n";
    y += "  - variables:\n      ann_fields: |-\n" + ind("{{ {" + item + "} }}", 8) + "\n      speech: |-\n" + ind(`{{ ann_fields.get('${F.say}', '') or ann_json.get('speech', '') or '' }}`, 8) + "\n";
    y += "  - alias: Stop if the AI answer was not usable\n    if:\n      - condition: template\n        value_template: \"{{ speech | length == 0 }}\"\n    then:\n"
      + (cardOn && s.cardWhen === "start" ? `      - action: input_boolean.turn_off\n        target:\n          entity_id: ${cs}\n` : "") + "      - stop: The AI answer was not usable JSON\n";
  } else {
    const sp = s.json ? "{{ (announcement.data | from_json).speech }}" : "{{ announcement.data }}";
    y += `  - variables:\n      speech: '${sp}'\n`;
  }
  if (tx) y += "  - alias: Save announcement " + (F ? "fields" : "text") + "\n    action: mqtt.publish\n    data:\n      topic: " + JSON.stringify(txtTopicOf(tx, s0.name || "Announcement")) + "\n      payload: '" + (F ? "{{ ann_fields | tojson }}" : "{{ speech }}") + "'\n";
  if (cardOn && s.cardWhen !== "start") y += cardStep("Show dashboard card");
  y += "  - alias: Deliver\n    parallel:\n";
  if (sp_on) y += `      - action: tts.speak\n        target:\n          entity_id: ${O.tts_entity}\n        data:\n          message: '{{ speech }}'\n          media_player_entity_id: ${A}\n`;
  if (al.length) y += "      - action: notify.alexa_media\n        data:\n          target:\n" + al.map(a => "            - " + a).join("\n") + "\n          message: '{{ speech }}'\n          data:\n            type: tts\n";
  const isSvc = id => { const e = ENT.find(x => x.id === id); return e ? !!e.svc : /^notify\.mobile_app_/.test(id) };
  const ne = nt.filter(i => !isSvc(i)), ns = nt.filter(isSvc), msg = "          title: " + n + "\n          message: " + (F ? "\"{{ ann_json.get('notification', '') or speech[:100] }}\"" : "'{{ (announcement.data | from_json).notification }}'") + "\n";
  if (ne.length) y += "      - action: notify.send_message\n        target:\n          entity_id:\n" + ne.map(a => "            - " + a).join("\n") + "\n        data:\n" + msg;
  ns.forEach(a => { y += "      - action: " + a + "\n        data:\n" + msg });
  if (!sp_on && !al.length && !nt.length) y += "      - delay:\n          seconds: 1\n";
  if (sp_on) y += `  - delay:\n      seconds: 15\n  - wait_for_trigger:\n      - trigger: state\n        entity_id: ${A}\n        to:\n          - paused\n          - idle\n    timeout:\n      seconds: 120\n    continue_on_timeout: true\n  - delay:\n      seconds: 5\n`;
  else if (al.length) y += "  - delay:\n      seconds: 40\n";
  if (speak && flag) y += `  - action: input_boolean.turn_off\n    target:\n      entity_id: ${flag}\n`;
  if (speak && s.pause && players.length) y += "  - if:\n      - condition: state\n        entity_id: " + players[0] + "\n        state: paused\n    then:\n      - action: media_player.media_play\n        target:\n          entity_id: " + players[0] + "\n";
  if (cardOn && s.cardOff) {  /* off after the speech is done (and the extra hold), or never if nothing waits and no hold is set */
    const hold = Math.max(0, Math.round(+s.cardHold || 0));
    if (hold > 0) y += `  - alias: Keep dashboard card up\n    delay:\n      seconds: ${hold}\n`;
    if (speak || hold > 0) y += `  - alias: Hide dashboard card\n    action: input_boolean.turn_off\n    target:\n      entity_id: ${cs}\n`;
  }
  return y;
}

/* Read a script made by this tool back into form state. Used for scripts that predate the library. */
function recover(cfg) {
  const s = {name: cfg.alias || "", src: [], outs: [], json: false, pers: {}, usePers: false, one: DEF, len: O.default_length || 1000, task: "", vol: (O.default_volume || 70) / 100, pause: false,
    cardSw: "", cardWhen: "talk", cardOff: true, cardHold: 0};
  const notes = [], acts = [];
  const walk = a => (Array.isArray(a) ? a : [a]).forEach(x => {
    if (!x || typeof x !== "object") return;
    acts.push(x);
    ["sequence", "then", "else", "parallel", "default"].forEach(k => x[k] && walk(x[k]));
    (Array.isArray(x.choose) ? x.choose : []).forEach(c => walk(c.sequence || []));
  });
  walk(cfg.sequence || []);
  const ok = new Set(usable().map(x => x.id)), lost = [];
  acts.forEach(x => { if (x.variables) Object.keys(x.variables).filter(k => k.startsWith("src_")).forEach(k => { const id = k.slice(4); (ok.has(id) ? s.src : lost).push(id) }) });
  if (lost.length) notes.push("These data sources no longer exist in Settings and were dropped: " + lost.join(", ") + ".");
  s.pause = acts.some(x => x.alias === "Pause music if playing");
  acts.forEach(x => {
    const a = x.action || "", d = x.data || {};
    if (a === "media_player.volume_set" && d.volume_level != null) s.vol = +d.volume_level;
    if (a === "tts.speak") s.outs.push("tts");
    if (a === "notify.alexa_media") [].concat(d.target || []).forEach(t => s.outs.push("a:" + t));
    if (a === "notify.send_message") [].concat((x.target || {}).entity_id || []).forEach(t => s.outs.push("n:" + t));
    else if (a.startsWith("notify.") && a !== "notify.alexa_media") s.outs.push("n:" + a);
  });
  const entOf = x => [].concat((x.target || {}).entity_id || (x.data || {}).entity_id || [])[0] || "";
  const secs = d => typeof d === "number" ? d : typeof d === "string" ? (d.split(":").reduce((a, v) => a * 60 + (+v || 0), 0)) : d ? (+d.hours || 0) * 3600 + (+d.minutes || 0) * 60 + (+d.seconds || 0) : 0;
  const showA = acts.find(x => /^Show dashboard card/.test(x.alias || "") && x.action === "input_boolean.turn_on");
  if (showA) {
    s.cardSw = entOf(showA); s.cardWhen = /early$/.test(showA.alias) ? "start" : "talk";
    s.cardOff = acts.some(x => x.alias === "Hide dashboard card");
    const hold = acts.find(x => x.alias === "Keep dashboard card up"); s.cardHold = hold ? secs(hold.delay) : 0;
  } else {  /* a hand-written script: an input_boolean it turns on that is not the talking flag is most likely the card switch */
    const on = acts.find(x => x.action === "input_boolean.turn_on" && entOf(x) && entOf(x) !== O.talking_flag);
    if (on) {
      s.cardSw = entOf(on); s.cardWhen = "talk"; s.cardOff = acts.some(x => x.action === "input_boolean.turn_off" && entOf(x) === s.cardSw); s.cardHold = 0;
      notes.push("Found " + s.cardSw + " being turned on, so it is filled in as the dashboard card switch" + (s.cardOff ? "." : ", and it is left on afterwards like your script does."));
    }
  }
  const ai = acts.filter(x => x.action === "ai_task.generate_data");
  const text = ai.length ? String((ai[0].data || {}).instructions || "") : "";
  const m = text.match(/YOUR TASK: ([\s\S]*?)\n\nSTYLE[^:\n]*: /);
  if (m) s.task = m[1].trim();
  else if (text) { s.task = text.trim(); s.pers = {[DEF]: "Follow the voice and tone given in the task."}; s.one = DEF; notes.push("Your own prompt was kept word for word as the instructions, and the style line only points back to it."); }
  const l = text.match(/under (\d+) characters/); if (l) s.len = +l[1];
  s.json = text.includes("Output ONLY a JSON object");
  const styleOf = t => { const z = String(t || "").match(/STYLE[^:\n]*: ([\s\S]*?)\nNo markdown/); return z ? z[1] : null };
  const ps = acts.find(x => Array.isArray(x.choose) && x.choose.some(c => JSON.stringify(c).includes("ai_task.generate_data")));
  if (ps && O.personality_select) {
    s.usePers = true;
    const known = new Set(persList().map(p => p.name)), gone = [];
    ps.choose.forEach(c => {
      const cond = (c.conditions || [])[0] || {}, a = (c.sequence || []).find(z => z.action === "ai_task.generate_data");
      if (cond.state && a) { const sy = styleOf((a.data || {}).instructions); if (sy != null) s.pers[cond.state] = sy; if (!known.has(cond.state)) gone.push(cond.state); }
    });
    if (gone.length) notes.push("These personalities are in the script but not in your list anymore, so they were dropped: " + gone.join(", ") + ".");
  } else if (text) {
    const sy = styleOf(text), hit = persList().find(p => p.style === sy);
    if (hit) s.one = hit.name; else if (sy != null) { s.pers = {[DEF]: sy}; s.one = DEF; notes.push("It used a custom personality style, which is now filed under " + DEF + "."); }
  }
  if (!m && text) s.usePers = false;
  s.outs = [...new Set(s.outs)];
  return {state: s, notes};
}

/* ---------- editor: open / dirty / save ---------- */
function markDirty() { dirty = true; paintState(); }
function paintState() {
  const p = $("#estate");
  if (dirty) { p.className = "pill acc"; p.textContent = cur.pushed ? "Changed since last push" : "Unsaved changes"; }
  else if (cur.pushed) { p.className = "pill ok"; p.textContent = "In Home Assistant"; }
  else if (cur.saved) { p.className = "pill warn"; p.textContent = "Saved draft"; }
  else { p.className = "pill plain"; p.textContent = "New"; }
  $("#etitle").textContent = $("#name").value.trim() || "New announcement";
  const id = cur.id || slug($("#name").value);
  $("#idhelp").textContent = cur.id ? "Script id: script." + cur.id + ". It stays the same if you rename this, so automations that call it keep working."
    : "It will be created as script." + id + (takenIds().has(id) ? " (a number is added because that name is taken)." : ".");
  $("#presetwrap").hidden = !cur.isNew || rawMode;
}
function openEditor(state, c, note) {
  cur = Object.assign({id: null, isNew: true, pushed: false, saved: false}, c);
  IMPORT = {original: state.original || "", replaces: state.replaces || "", done: !!state.replacedDone};
  $("#msg").textContent = ""; $("#tres").replaceChildren(); $("#pnote").textContent = "";
  const lg = $("#elegacy"); lg.hidden = !note; if (note) lg.firstElementChild.textContent = note;
  lg.querySelectorAll(".origbtn").forEach(b => b.remove());
  if (note && IMPORT.original && state.raw == null) {  /* converted from an import: one tap goes back to the original, kept exactly as written */
    const b = el("button", {class: "btn sm origbtn", style: "margin-top:8px"}, "Use my original instead");
    confirmTap(b, "Tap again: keep it exactly as written", () => {
      setRaw(true); $("#rawyaml").value = IMPORT.original; const a = getAlias(IMPORT.original); if (a) $("#name").value = a;
      IMPORT.replaces = ""; gen(); markDirty(); lg.firstElementChild.textContent = "Switched back to your original, kept exactly as written."; b.remove();
    });
    lg.append(b);
  }
  applyState(state); dirty = false; paintState(); showView("edit");
}
const blankState = () => ({name: "My announcement", src: usable().filter(x => x.type === "household").map(x => x.id),
  outs: $$("[data-o]").map(c => c.dataset.o).filter(o => !o.startsWith("n:")), task: "", len: O.default_length || 1000, vol: (O.default_volume || 70) / 100, pause: true,
  usePers: !!O.personality_select, one: DEF, pers: Object.fromEntries(persList().map(p => [p.name, p.style])),
  cardSw: "", cardWhen: "talk", cardOff: true, cardHold: 0, auto: defAuto()});
function openNew(over) { openEditor(Object.assign(blankState(), over || {}), {isNew: true}); }
function openItem(it) {
  const s = Object.assign(blankState(), it.state || {}, {name: (it.state || {}).name || it.name});
  openEditor(s, {id: it.id, isNew: false, pushed: !!(it.pushed_at || it.in_ha), saved: true});
}
async function openFound(f, msgEl) {
  msgEl.textContent = "Loading...";
  const r = await ann("script?id=" + encodeURIComponent(f.id));
  if (!r.ok) { msgEl.textContent = r.error; return; }
  msgEl.textContent = "";
  const {state, notes} = recover(r.config);
  openEditor(Object.assign(blankState(), state), {id: f.id, isNew: false, pushed: true, saved: false},
    "Opened from Home Assistant. Pushing rebuilds the script from this form, so anything you changed by hand in the script will be replaced." + (notes.length ? " " + notes.join(" ") : ""));
}

function say(text, cls) { const m = $("#msg"); m.className = "msg " + (cls || ""); m.textContent = text; }
async function persist(push) {
  const s = st();
  if (s.txt && s.txt.on && !s.txt.file) { s.txt.file = txtFileOf(s.txt, s.name); $("#txt-file").value = s.txt.file; }  /* fixed from now on, so a rename keeps the same file and sensor */
  if (push) { const bad = autoProblem(s); if (bad) { say(bad, "bad"); return; } }
  if (!cur.id) cur.id = uniqueId(slug(s.name));
  const btns = [$("#save"), $("#push")]; btns.forEach(b => b.disabled = true);
  say(push ? "Pushing to Home Assistant..." : "Saving...");
  let r;
  if (IMPORT.original && s.raw == null) Object.assign(s, {original: IMPORT.original, replaces: IMPORT.replaces || "", replacedDone: IMPORT.done});
  if (push) r = await ann("push", {id: cur.id, yaml: makeYaml(s), auto_yaml: makeAuto(s, cur.id), state: s, new: cur.isNew && !cur.pushed,
    replace_auto: IMPORT.replaces && !IMPORT.done && s.raw == null ? IMPORT.replaces : "", match_id: MATCH.checked()});
  else r = await ann("library/save", {id: cur.id, name: s.name, state: s, match_id: MATCH.checked()});
  btns.forEach(b => b.disabled = false);
  if (!(r.ok)) { say(r.detail || r.error || "That failed.", "bad"); if (!cur.saved && !cur.pushed && !cur.fixedId) cur.id = null; paintState(); return; }
  cur.saved = true; cur.isNew = false; if (push) cur.pushed = true; dirty = false; paintState(); notifyChanged("ann");
  if (push && r.replaced) IMPORT.done = true;
  const am = push ? (s.auto.on ? " It runs " + autoSummary(s.auto) + "." : r.auto === "removed" ? " The old schedule was removed." : "") : "";
  say(push ? "Done. script." + cur.id + " is up to date in Home Assistant." + am + (r.replaced ? " Your old automation " + r.replaced + " was turned off so it doesn't run twice." : "") : "Saved. Home Assistant still has the previous version." + (cur.pushed ? " Push to update it." : ""), "ok");
  if (r.id_note) say($("#msg").textContent + " " + r.id_note, "ok");
  if (r.name_warning) say($("#msg").textContent + " " + r.name_warning, "bad");
}
const MATCH = matchIdBox(); $("#idhelp").after(MATCH.row);
$("#save").onclick = () => persist(false);
$("#push").onclick = () => persist(true);

let armedBack = null;
$("#back").onclick = () => {
  const b = $("#back");
  if (dirty && !armedBack) {
    b.textContent = "Leave without saving?"; b.classList.add("danger");
    armedBack = setTimeout(() => { armedBack = null; b.textContent = "← All announcements"; b.classList.remove("danger") }, 3500); return;
  }
  clearTimeout(armedBack); armedBack = null; b.textContent = "← All announcements"; b.classList.remove("danger");
  dirty = false; showView("lib"); loadLib();
};
$("#newann").onclick = () => openNew();
$("#gohelp").onclick = () => { showView("help"); $("#tabs").hidden = true; HEL.back = true; drawHelper(); };  /* the helper hands its text back to this editor */

function gen() {
  const s = st(); $("#out").textContent = makeYaml(s);
  $("#autoopts").hidden = !s.auto.on;
  $("#autoout").textContent = makeAuto(s, cur.id || slug(s.name)) || (s.auto.on ? "Set a repeat time, a time of day or an entity to watch to see the schedule." : "No schedule. Turn on \"Run on a schedule\" to make one.");
  if (rawMode) { paintState(); return; }
  $("#onewrap").hidden = s.usePers; $("#volv").textContent = Math.round(s.vol * 100);
  $("#cardopts").hidden = !s.cardSw;
  const talks = s.outs.some(o => o === "tts" || o.startsWith("a:"));
  $("#cardhelp").textContent = s.cardOff ? (talks || s.cardHold > 0 ? "It turns off after the announcement has finished playing" + (s.cardHold > 0 ? ", plus " + s.cardHold + " seconds." : ".")
    : "Nothing here speaks, so it has no finish to wait for. Add extra seconds to have it turn off by itself, or leave it on.") : "It stays on after the announcement. Turn it off from your dashboard or another automation.";
  paintState();
}
document.addEventListener("input", e => {
  if (!e.target.closest("#v-edit")) return;
  if (rawMode) {
    if (e.target.id === "name") $("#rawyaml").value = setAlias($("#rawyaml").value, e.target.value);
    else if (e.target.id === "rawyaml") { const a = getAlias(e.target.value); if (a) $("#name").value = a; }
  }
  gen(); markDirty();
});
document.addEventListener("change", e => { if (e.target.closest("#v-edit")) { gen(); markDirty(); } });

$("#run").onclick = async () => {
  if (!cur.id) { say("Push it to Home Assistant first.", "warn"); return; }
  say("Starting...");
  const r = await ann("run", {id: cur.id}); say(r.ok ? "Started the saved script." : (r.detail || r.error), r.ok ? "ok" : "bad");
};
$("#copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("#out").textContent); say("Copied.", "ok"); }
  catch (e) { $("#out").closest("details").open = true; const r = document.createRange(); r.selectNodeContents($("#out")); getSelection().removeAllRanges(); getSelection().addRange(r); say("Selected. Press copy on your device."); }
};

/* ---------- test run ---------- */
const pre = t => el("pre", {}, t == null ? "" : String(t));
function showTest(r) {
  const b = $("#tres"); b.replaceChildren();
  if (r.status === "running") { b.append(el("p", {class: "dim small"}, el("span", {class: "spin"}), "Running. With sound this can take a couple of minutes.")); return; }
  if (r.status === "error") { b.append(el("div", {class: "note bad"}, el("div", {}, el("b", {}, "Test failed"), pre(r.error)))); return; }
  if (r.speech != null) b.append(el("b", {}, "What it said"), pre(r.speech));
  if (r.fields && typeof r.fields === "object" && Object.keys(r.fields).length) {  /* fields mode: what goes on the card */
    b.append(el("b", {style: "display:block;margin-top:10px"}, "What goes on the card"),
      el("div", {class: "list"}, Object.entries(r.fields).map(([k, v]) => el("div", {class: "li"}, el("div", {class: "t"}, el("b", {}, k), el("small", {}, String(v == null ? "" : v)))))));
  } else if (r.fields === "" || (r.fields && !Object.keys(r.fields).length)) b.append(el("div", {class: "note warn", style: "margin-top:10px"}, el("div", {}, "The AI's answer was not usable JSON, so nothing would be spoken or saved. Try again, or make the field descriptions clearer.")));
  const d = el("details", {open: r.speech == null, style: "margin-top:10px"}, el("summary", {}, "What the AI saw"));
  Object.entries(r.sources || {}).forEach(([k, v]) => d.append(el("p", {class: "dim small", style: "margin-top:8px"}, k.replace("src_", "")), pre(v)));
  b.append(d);
}
async function runTest(mode) {
  const s = st(); if (!s.src.length) { $("#tres").textContent = "Tick at least one data source first."; return; }
  const btns = ["t-data", "t-text", "t-full"].map(i => $("#" + i)); btns.forEach(x => x.disabled = true);
  try {
    const r = await ann("test", {mode, yaml: makeYaml(s, {silent: mode !== "full"})});
    if (r.ok === false || r.error) { $("#tres").textContent = r.error; return; }
    for (let i = 0; i < 200; i++) { const t = await (await fetch("./api/ann/test")).json(); showTest(t); if (t.status !== "running") break; await sleep(2500); }
  } catch (e) { $("#tres").textContent = "Failed: " + e; } finally { btns.forEach(x => x.disabled = false); }
}
$("#t-data").onclick = () => runTest("data"); $("#t-text").onclick = () => runTest("text"); $("#t-full").onclick = () => runTest("full");

/* ---------- import a pasted script ---------- */
const imsg = (t, c) => { const m = $("#impmsg"); m.className = "msg " + (c || ""); m.textContent = t || ""; };
function fillPick() {
  const sel = $("#imppick"); sel.replaceChildren(el("option", {value: ""}, "Choose a script..."));
  ENT.filter(e => e.id.startsWith("script.")).forEach(e => sel.append(el("option", {value: e.id.slice(7)}, e.name + " (" + e.id + ")")));
}
$("#importbtn").onclick = () => { $("#importbox").hidden = false; imsg(""); fillPick(); $("#impyaml").focus(); };
$("#impcancel").onclick = () => { $("#importbox").hidden = true; imsg(""); };
$("#imppickgo").onclick = async () => {
  const id = $("#imppick").value; if (!id) { imsg("Choose a script first.", "warn"); return; }
  imsg("Loading...");
  const r = await ann("script?id=" + encodeURIComponent(id));
  if (!r.ok) { imsg(r.error, "bad"); return; }
  $("#impyaml").value = r.yaml; $("#impid").value = id; imsg("Loaded. Press Import to take it over.", "ok");
};
$("#impgo").onclick = async () => {
  const b = $("#impgo"), typed = $("#impid").value.trim();
  if (typed && !cleanId(typed)) { imsg("The script id can only use lowercase letters, numbers and underscores.", "bad"); return; }
  if (($$('[name="impmode"]').find(x => x.checked) || {}).value !== "raw") { await importConvert(b, typed); return; }
  b.disabled = true; imsg("Checking your script...");
  const r = await ann("import", {yaml: $("#impyaml").value});
  b.disabled = false;
  if (!r.ok) { imsg(r.error || "That failed.", "bad"); return; }
  const id = cleanId(typed) || r.id || uniqueId(slug(r.alias)), takeover = !!(cleanId(typed) || r.id);
  if (LIB.some(x => x.id === id)) { imsg("script." + id + " is already in My announcements. Open it from the list below.", "bad"); return; }
  const inHA = ENT.some(e => e.id === "script." + id);
  $("#importbox").hidden = true; $("#impyaml").value = ""; $("#impid").value = ""; imsg("");
  openEditor(Object.assign(blankState(), {name: r.alias, raw: r.yaml}), {id, isNew: true, pushed: false, saved: false, fixedId: true},
    "Imported. Your script is kept exactly as written. " + (inHA ? "script." + id + " already exists in Home Assistant, so pushing replaces it." : "Pushing creates script." + id + " in Home Assistant.") + (takeover ? "" : " Nothing is in Home Assistant yet."));
  markDirty();
};
/* convert a pasted or loaded script / automation into a normal form announcement */
async function importConvert(b, typed) {
  if (!$("#impyaml").value.trim()) { imsg("Paste your script or automation, or load one, first.", "warn"); return; }
  b.disabled = true; imsg("Reading it and converting. Your AI Task helps with the prompt, so this can take a minute...");
  const r = await convertImport("announcement", $("#impyaml").value);
  b.disabled = false;
  if (!r.ok) { imsg(r.error || "That failed.", "bad"); return; }
  build();  /* show any data sources that were just added */
  const id = cleanId(typed) || cleanId(r.id) || uniqueId(slug(r.name));
  if (LIB.some(x => x.id === id)) { imsg("script." + id + " is already in My announcements. Open it from the list below.", "bad"); return; }
  const inHA = ENT.some(e => e.id === "script." + id);
  $("#importbox").hidden = true; $("#impyaml").value = ""; $("#impid").value = ""; imsg("");
  openEditor(Object.assign(blankState(), r.state, {original: r.original}), {id, isNew: true, pushed: false, saved: false, fixedId: true},
    convertNote(r, "announcement") + " " + (inHA ? "Pushing replaces script." + id + ", so automations that call it keep working." : "Pushing creates script." + id + "."));
  markDirty();
}
$("#rawcheck").onclick = async () => {
  say("Checking...");
  const r = await ann("import", {yaml: $("#rawyaml").value});
  say(r.ok ? "That is a valid script with " + (r.config.sequence || []).length + " top-level steps." : r.error, r.ok ? "ok" : "bad");
};
confirmTap($("#rawform"), "Tap again to convert", async () => {
  const b0 = $("#rawform"); b0.disabled = true;
  say("Converting. Your AI Task helps with the prompt, so this can take a minute...");
  const yml = $("#rawyaml").value, nm0 = $("#name").value;
  const cv = await convertImport("announcement", yml);
  b0.disabled = false;
  if (cv.ok) {
    build();  /* show any data sources that were just added */
    const keep = {id: cur.id, isNew: cur.isNew, pushed: cur.pushed, saved: cur.saved, fixedId: true};
    openEditor(Object.assign(blankState(), cv.state, {original: cv.original || yml, name: nm0 || cv.state.name}), keep,
      convertNote(cv, "announcement") + " Pushing replaces script." + cur.id + " with the form's version, so automations that call it keep working. Until you push, Use my original instead goes back.");
    markDirty(); say("Converted. Nothing is saved yet: check it, then Save or Save and push.", "ok");
    return;
  }
  if (cv.error && !/ai_task\.generate_data|YAML problem/.test(cv.error)) say(cv.error + " Trying the simple way instead...", "warn");
  const r = await ann("import", {yaml: yml});
  if (!r.ok) { say(r.error, "bad"); return; }
  const {state, notes} = recover(r.config);
  if (!state.task) { say("There is no ai_task.generate_data step in it to put in the form, so it stays as your own script.", "warn"); return; }
  const b = blankState(), nm = $("#name").value;
  applyState(Object.assign(b, state, {pers: Object.assign({}, b.pers, state.pers), name: nm}));
  markDirty();
  const lg = $("#elegacy"); lg.hidden = false;
  lg.firstElementChild.textContent = "Switched to the form tools. Pushing rebuilds the script from this form, so anything in your script the form does not cover is dropped. Leave without saving to keep your original." + (notes.length ? " " + notes.join(" ") : "");
  say("Switched to the form tools. Nothing is saved yet.", "ok");
});

/* ---------- helper ---------- */
function drawHelper() {
  const v = $("#v-help"); v.replaceChildren();
  const card = (t, sub) => { const c = el("div", {class: "card"}, el("div", {class: "ch"}, el("h2", {}, t), sub ? el("p", {}, sub) : null)); v.append(c); return c; };
  if (HEL.back) v.append(el("div", {class: "row"}, el("button", {class: "btn quiet sm", onclick: () => { HEL.back = false; $("#tabs").hidden = false; showView("edit"); }}, "← Back to the editor")));
  const info = "Using AI Task: " + (aiName() || "none set yet (see Settings)");
  const a = card("Write the instructions for me", "Say it your way. The AI writes clear instructions and picks the data to include.");
  const idea = el("textarea", {value: HEL.idea, placeholder: "e.g. Look at the weather for the week and tell me about it, but only if my work calendar has something on."});
  idea.oninput = () => { HEL.idea = idea.value };
  const wb = el("button", {class: "btn primary", style: "margin-top:10px"}, "Write it"), wr = el("div", {style: "margin-top:12px"});
  wb.onclick = async () => {
    if (!HEL.idea.trim()) { wr.textContent = "Type what you want first."; return; }
    wr.textContent = "Asking your AI Task..."; wb.disabled = true;
    const r = await ann("helper", {mode: "instructions", idea: HEL.idea, ai: aiName(), sources: usable().map(x => ({id: x.id, label: x.label + " (" + x.type + ")"})), calendars: (S.sources || []).filter(x => x.type === "calendar").flatMap(x => x.entities)});
    wb.disabled = false;
    if (!r.ok) { wr.textContent = r.error; return; }
    wr.replaceChildren(); const nm = el("input", {value: r.name || ""}), tk = el("textarea", {value: r.task});
    const labels = usable().filter(x => r.sources.includes(x.id)).map(x => x.label);
    const ub = el("button", {class: "btn good", onclick: () => {
      const s = {name: nm.value || "My announcement", src: r.sources.length ? r.sources : blankState().src, task: tk.value};
      if (HEL.back) { applyState(Object.assign(st(), s)); markDirty(); HEL.back = false; $("#tabs").hidden = false; showView("edit"); }
      else openNew(s);
    }}, HEL.back ? "Use in this announcement" : "Start an announcement with this");
    wr.append(el("label", {class: "l"}, "Script name"), nm, el("label", {class: "l"}, "Instructions (edit if you like)"), tk, el("p", {class: "help"}, "Will tick: " + (labels.join(", ") || "nothing extra")), el("div", {class: "row", style: "margin-top:10px"}, ub));
  };
  a.append(idea, wb, wr, el("p", {class: "help"}, info));
  const b = card("Add something to talk about", "Pick an entity and say what you want from it. The AI finds the right attribute and adds it as a data source.");
  b.append(el("label", {class: "l"}, "Entity"), picker(null, false, () => HEL.entity ? [HEL.entity] : [], x => { HEL.entity = x[0] || "" }), el("label", {class: "l"}, "What do you want from it?"));
  const gt = el("textarea", {placeholder: "e.g. Days left until the concert and where it is", value: HEL.goal, style: "min-height:70px"}); gt.oninput = () => { HEL.goal = gt.value };
  const tb = el("button", {class: "btn primary", style: "margin-top:10px"}, "Check it"), res = el("div", {style: "margin-top:12px"});
  tb.onclick = async () => {
    if (!HEL.entity || !HEL.goal) { res.textContent = "Pick an entity and say what you want."; return; }
    res.textContent = "Asking your AI Task..."; tb.disabled = true;
    const r = await ann("helper", {entity: HEL.entity, goal: HEL.goal, ai: aiName()});
    tb.disabled = false;
    if (!r.ok) { res.textContent = r.error; return; }
    res.replaceChildren(el("p", {}, el("b", {}, r.label), r.attribute ? " (attribute: " + r.attribute + ")" : " (whole entity)"), el("p", {class: "dim small"}, r.note), el("p", {class: "dim small"}, "Preview: " + r.preview));
    const ab = el("button", {class: "btn good", style: "margin-top:8px"}, "Add as data source");
    ab.onclick = async () => { S.sources.push(mk(S.sources, "entity", {label: r.label, entity: HEL.entity, attribute: r.attribute})); await saveSettings(); ab.textContent = "Added and saved"; ab.disabled = true; };
    res.append(ab);
  };
  b.append(gt, tb, res);
}

/* ---------- settings ---------- */
const FIELDS = {
  core: [["ai_task_entity", "AI Task", ["ai_task"], 0, "Writes the announcement text"], ["tts_entity", "Text-to-speech engine", ["tts"], 0, "Turns the text into speech"], ["speaker", "Main speaker", ["media_player"], 0, "Where speech plays"]],
  more: [["alexa_targets", "Extra Alexa speakers", ["media_player"], 1, "Spoken through the alexa_media integration"], ["music_players", "Music players to pause", ["media_player"], 1, "Paused while it talks, resumed after"], ["talking_flag", "Talking flag", ["input_boolean"], 0, "Optional. Turned on while it talks"], ["personality_select", "Personality dropdown", ["input_select"], 0, "Optional. The dropdown that picks the personality. Use the buttons under Personalities below to create or update it"]],
  phones: [["notify_targets", "Phone notifications", ["notify"], 1, 'Type or pick. Phones show as "service"']]
};
async function saveSettings() {
  S.personalities = persList().map(p => ({name: String(p.name || "").trim(), style: p.style || ""}));
  const r = await ann("settings", S);
  if (r.error) { $("#smsg").className = "msg bad"; $("#smsg").textContent = r.error; return false; }
  S = r; if (!Array.isArray(S.sources)) S.sources = []; build(); setupNote(); drawHelper(); drawSettings(); return true;
}
/* Names must be filled in and different from each other (the dropdown can't hold duplicates). */
function checkPers() {
  const seen = new Set();
  for (const p of persList()) {
    const n = String(p.name || "").trim();
    if (!n) return "Every personality needs a name.";
    if (seen.has(n.toLowerCase())) return 'Two personalities are both called "' + n + '". Give each one its own name.';
    seen.add(n.toLowerCase());
  }
  return "";
}
async function syncDropdown(create) {
  const m = $("#smsg"), bad = checkPers();
  if (bad) { m.className = "msg bad"; m.textContent = bad; return; }
  m.className = "msg"; m.textContent = "Saving, then updating Home Assistant...";
  if (!(await saveSettings())) return;
  const r = await ann("personality_dropdown", {create: !!create});
  if (r.settings) { S = r.settings; if (!Array.isArray(S.sources)) S.sources = []; build(); setupNote(); drawSettings(); }
  m.className = "msg " + (r.ok ? "ok" : "bad"); m.textContent = r.ok ? r.message + " Push your announcements again so their scripts use the new list." : r.error;
}
const varNames = s => ({weather: "fc_" + s.id + " (forecast response)", calendar: "cal_" + s.id + " (events response)", todo: "todo_" + s.id + " (items response)"}[s.type] || "");

function editor(s) {
  const box = el("div", {class: "card sub"}), f = (l, node) => box.append(el("label", {class: "l"}, l), node);
  const tpl = el("textarea", {class: "code"});
  const sync = () => { if (!s.template) tpl.value = auto(s) };
  const txt = (k, ph) => { const i = el("input", {placeholder: ph || "", value: s[k] || ""}); i.oninput = () => { s[k] = i.value; sync() }; return i };
  const one = (k, d, l) => f(l, picker(d, false, () => s[k] ? [s[k]] : [], a => { s[k] = a[0] || ""; sync() }));
  f("Name (shown in the editor and told to the AI)", (() => { const i = el("input", {value: s.label}); i.oninput = () => { s.label = i.value }; return i })());
  if (s.type === "household") { const t = el("textarea", {value: s.text || "", placeholder: "Who lives here, pets, friends, running jokes..."}); t.oninput = () => { s.text = t.value; sync() }; f("Text", t); one("entity", null, "Extra entity to append (optional)"); f("Its attribute (blank = state)", txt("attribute")); }
  if (s.type === "locations") one("entity", DOMS.locations, "Sensor whose attributes are name: place (blank = use people)");
  if (s.type === "weather") { one("entity", DOMS.weather, "Weather entity"); one("extra", ["sensor"], "Inside temperature sensor (optional)"); }
  if (s.type === "news") one("entity", DOMS.news, 'News feed sensor (needs an "entries" attribute)');
  if (s.type === "calendar") { f("Calendars", picker(DOMS.calendar, true, () => s.entities || [], a => { s.entities = a; sync() })); const d = el("input", {type: "number", value: s.days || 7}); d.oninput = () => { s.days = +d.value || 7; sync() }; f("Days ahead", d); }
  if (s.type === "todo") one("entity", DOMS.todo, "To-do list");
  if (s.type === "trash") one("entity", DOMS.trash, "Entity that is on when pickup is tomorrow");
  if (s.type === "entity") { one("entity", null, "Entity"); f("Attribute (blank = state + all attributes)", txt("attribute")); }
  tpl.value = body(s); tpl.oninput = () => { if (s.type === "template") s.template = tpl.value; else s.template = tpl.value === auto(s) ? "" : tpl.value };
  const hint = varNames(s);
  box.append(el("label", {class: "l"}, s.type === "template" ? "Template (Home Assistant Jinja)" : "Template the script uses (edit to fix it)"), tpl,
    el("p", {class: "help"}, (hint ? "Available variable: " + hint + ". " : "") + "This text becomes variable src_" + s.id + ". Use Preview the data in the editor to see what it renders."));
  if (s.type !== "template") box.append(el("button", {class: "btn sm", style: "margin-top:8px", onclick: () => { s.template = ""; tpl.value = auto(s) }}, "Reset template to auto"));
  return box;
}

function drawSettings() {
  const v = $("#v-set"); v.replaceChildren();
  const card = (t, sub) => { const c = el("div", {class: "card"}, el("div", {class: "ch"}, el("h2", {}, t), sub ? el("p", {}, sub) : null)); v.append(c); return c; };
  if (!ENT.length) v.append(el("div", {class: "note warn"}, el("div", {}, "Could not load your entity list from Home Assistant. You can still type entity ids into any field. Check the add-on's Log tab.")));
  const fields = (c, list) => list.forEach(([k, l, d, m, h]) => {
    c.append(el("label", {class: "l"}, l), picker(d, !!m, () => m ? (S[k] || []) : (S[k] ? [S[k]] : []), a => { S[k] = m ? a : (a[0] || "") }));
    if (h) c.append(el("p", {class: "help"}, h));
  });
  fields(card("Voice and speakers", "The AI Task, text-to-speech engine and main speaker are required. The rest is optional."), [...FIELDS.core, ...FIELDS.more]);
  fields(card("Phones"), FIELDS.phones);

  const si = card("Data sources", "These feed the data list in the editor. Edit one to fix it, remove ones you don't want, or add more.");
  const okIds = new Set(usable().map(x => x.id)), L = el("div", {class: "stack"});
  (S.sources || []).forEach((s, i) => {
    const row = el("div", {}), top = el("div", {class: "li srcrow", style: "display:flex;align-items:center;gap:10px"});
    const eb = el("button", {class: "btn sm", onclick: () => { OPEN = OPEN === s.id ? "" : s.id; drawSettings() }}, OPEN === s.id ? "Close" : "Edit");
    const db = el("button", {class: "btn danger sm"}, "Remove");
    confirmTap(db, "Tap again", () => { S.sources.splice(i, 1); if (OPEN === s.id) OPEN = ""; drawSettings() });
    top.append(el("div", {class: "t"}, el("b", {}, s.label), el("small", {}, TYPES[s.type] + (s.template && s.type !== "template" ? " · custom template" : "") + (okIds.has(s.id) ? "" : " · needs an entity before it shows up"))), eb, db);
    row.append(top); if (OPEN === s.id) row.append(el("div", {style: "margin-top:8px"}, editor(s)));
    L.append(row);
  });
  if (!(S.sources || []).length) L.append(el("p", {class: "dim small"}, "No sources yet."));
  si.append(L);
  const sel = el("select", {style: "width:auto"}); Object.entries(TYPES).forEach(([k, l]) => sel.append(el("option", {value: k}, l)));
  si.append(el("div", {class: "row", style: "margin-top:12px"}, sel, el("button", {class: "btn", onclick: () => { const n = mk(S.sources, sel.value); S.sources.push(n); OPEN = n.id; drawSettings() }}, "Add source")));

  const sp = card("Personalities", "Each one is a voice an announcement can use. Add your own, edit the wording, or remove the ones you don't want. Default has no special personality and always stays.");
  const PL = el("div", {class: "stack"});
  persList().forEach((p, i) => {
    const isDef = p.name === DEF && i === 0, row = el("div", {class: "card sub"});
    const nm = el("input", {value: p.name, maxlength: 40, placeholder: "Name, e.g. Pirate", disabled: isDef}); nm.oninput = () => { p.name = nm.value };
    const tx = el("textarea", {value: p.style || "", placeholder: "How should it sound? e.g. Talk like a grumpy pirate. PG-13."}); tx.oninput = () => { p.style = tx.value };
    row.append(el("label", {class: "l"}, isDef ? "Default (can't be renamed or removed)" : "Name"), nm, el("label", {class: "l"}, "How it sounds"), tx);
    if (!isDef) { const rm = el("button", {class: "btn danger sm", style: "margin-top:8px"}, "Remove"); confirmTap(rm, "Tap again", () => { S.personalities.splice(i, 1); drawSettings() }); row.append(rm); }
    PL.append(row);
  });
  const addName = el("input", {placeholder: "New personality name", maxlength: 40, style: "max-width:260px"});
  const addBtn = el("button", {class: "btn", onclick: () => {
    const n = addName.value.trim(); if (!n) { $("#smsg").className = "msg bad"; $("#smsg").textContent = "Type a name first."; return; }
    S.personalities = persList().concat([{name: n, style: ""}]); drawSettings();
  }}, "Add personality");
  sp.append(PL, el("div", {class: "row", style: "margin-top:12px"}, addName, addBtn));
  sp.append(el("h3", {style: "margin-top:18px"}, "Home Assistant dropdown"),
    el("p", {class: "help"}, S.personality_select
      ? "Using " + S.personality_select + ". Saving settings keeps its options matched to this list. If it can\'t be edited (for example it is written in configuration.yaml), a new one is made for you automatically."
      : "Optional. Make a dropdown in Home Assistant so you can switch personality from a dashboard, an automation or your phone."),
    el("div", {class: "row", style: "margin-top:8px"}, S.personality_select
      ? el("button", {class: "btn", onclick: () => syncDropdown(false)}, "Update the dropdown now")
      : el("button", {class: "btn good", onclick: () => syncDropdown(true)}, "Create the dropdown for me")),
    el("p", {class: "help"}, "After you add, rename or remove a personality, push your announcements again. Each script carries its own copy of the personalities."));

  const s2 = card("Defaults");
  [["default_volume", "Default volume %"], ["default_length", "Default length (characters)"]].forEach(([k, l]) => {
    const f = el("input", {type: "number", value: S[k] ?? "", style: "max-width:160px"});
    f.oninput = () => { S[k] = +f.value };
    s2.append(el("label", {class: "l"}, l), f);
  });

  const s4 = card("Move settings to another install");
  const io = el("textarea", {class: "code", placeholder: "Export puts your settings here as JSON. Paste settings here and press Import."});
  s4.append(el("div", {class: "row"},
    el("button", {class: "btn sm", onclick: () => { io.value = JSON.stringify(S, null, 1) }}, "Export"),
    el("button", {class: "btn sm", onclick: () => { try { const j = JSON.parse(io.value); const keep = persList(); S = Object.assign({}, S, j); if (!Array.isArray(j.sources)) S.sources = migrate(S);
            if (!Array.isArray(j.personalities)) { S.personalities = keep.map(p => Object.assign({}, p)); [["Hype", "hype_style"], ["Roast", "roast_style"], ["Sweetie Pie", "sweet_style"]].forEach(([n, k]) => { if (!j[k]) return; const f = S.personalities.find(p => p.name === n); if (f) f.style = j[k]; else S.personalities.push({name: n, style: j[k]}); }); } drawSettings(); $("#smsg").textContent = "Imported. Review, then save."; } catch (e) { $("#smsg").textContent = "That is not valid JSON." } }}, "Import")), io,
    el("p", {class: "help"}, "Your saved announcements are included when you use the Backup tab."));
  v.append(el("div", {style: "height:60px"}));
}
$("#setsave").onclick = async () => {
  const m = $("#smsg"), bad = checkPers();
  if (bad) { m.className = "msg bad"; m.textContent = bad; return; }
  if (!(await saveSettings())) return;
  m.className = "msg ok"; m.textContent = "Settings saved.";
  if (S.personality_select) {
    const r = await ann("personality_dropdown", {});
    if (r.settings) S = r.settings;
    if (!r.ok) { m.className = "msg bad"; m.textContent = "Settings saved, but the dropdown was not updated: " + r.error; }
    else if (!r.unchanged) m.textContent = "Settings saved. " + r.message + " Push your announcements again so their scripts use the new list.";
  }
};
$("#setfill").onclick = () => {
  let n = 0; Object.values(FIELDS).flat().forEach(([k, , d, m]) => { if (m || S[k]) return; const c = ENT.filter(e => d.includes(e.id.split(".")[0])); if (c.length === 1) { S[k] = c[0].id; n++ } });
  drawSettings(); $("#smsg").className = "msg"; $("#smsg").textContent = "Filled " + n + " (only where there was one match). Save to keep.";
};

/* another tab renamed or changed something: refresh the list (not while editing, so nothing typed is lost) */
onChanged(() => { if (view === "lib") loadLib(); });

/* a rename made in Home Assistant shows up here on its own (the add-on checks every 30 seconds) */
setInterval(() => { if (view === "lib" && !document.hidden && !(document.activeElement && document.activeElement.tagName === "INPUT")) loadLib(); }, 20000);

/* ---------- start ---------- */
Promise.all([api("ann/options"), api("ann/entities").then(r => Array.isArray(r) ? r : []), api("facts/options")]).then(async ([o, e, f]) => {
  if (o.error) { $("#setupnote").append(el("div", {class: "note bad"}, o.error)); return; }
  FACT.home = f && Array.isArray(f.home_entities) ? f.home_entities : [];
  S = o; ENT = e; build(); setupNote(); drawHelper(); drawSettings(); await loadLib(); showView("lib");
});

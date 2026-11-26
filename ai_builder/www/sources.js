/* Shared by Announcements and Facts: info sources (what the AI is told) and the entity picker.
   Needs the page to define: S (settings, with S.sources) and ENT (entity list). Both are read when called. */
const ind = (t, n) => t.split("\n").map(l => l ? " ".repeat(n) + l : l).join("\n");
const slug = (s, d) => (s || d || "announcement").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60).replace(/_$/, "") || d || "announcement";

const TYPES = {household: "Household info", locations: "Where everyone is", weather: "Weather", news: "News feed", calendar: "Calendar", todo: "To-do list", trash: "Trash reminder", entity: "Entity / attribute", template: "Custom template"};
const DOMS = {weather: ["weather"], news: ["sensor"], calendar: ["calendar"], todo: ["todo"], trash: ["schedule", "binary_sensor", "input_boolean"], locations: ["sensor"], household: null, entity: null};
function uid(L, type) { let n = 1, id = type; while (L.some(x => x.id === id)) { n++; id = type + "_" + n } return id }
function mk(L, type, o) { const base = (type === "entity" && o && o.label) ? slug(o.label) : type; return Object.assign({id: uid(L, base), type, label: TYPES[type], entity: "", entities: [], attribute: "", extra: "", text: "", days: 7, template: ""}, o || {}) }
function migrate(s) {
  const L = [], add = (t, o) => L.push(mk(L, t, o));
  add("household", {text: s.household_context || "", entity: s.combined_info_entity || "", attribute: s.combined_info_attribute || ""});
  add("locations", {entity: s.locations_entity || ""});
  if (s.weather_entity) add("weather", {entity: s.weather_entity, extra: s.inside_temp_entity || ""});
  if (s.news_entity) add("news", {label: "News headlines", entity: s.news_entity});
  if ((s.calendar_entities || []).length) add("calendar", {label: "Calendar (7 days)", entities: s.calendar_entities});
  if (s.todo_entity) add("todo", {entity: s.todo_entity});
  if (s.trash_entity) add("trash", {entity: s.trash_entity});
  (s.custom_sources || []).forEach(c => add("entity", {label: c.label, entity: c.entity, attribute: c.attribute || ""}));
  return L;
}
/* Where a source can be used: shared by announcements and facts (the default), or only one of them. Sources an AI made
   (the helper, an import) are flagged ai:true and live in their own "Made by AI" section, scoped to what made them.
   The page defines SCOPE as "ann" or "fact". */
const SCOPES = [["shared", "Shared (announcements and facts)"], ["ann", "Announcements only"], ["fact", "Facts only"]];
const scopeOf = s => (s.scope === "ann" || s.scope === "fact") ? s.scope : "shared";
const pageScope = () => (typeof SCOPE === "string" ? SCOPE : "");
const seesScope = (s, sc) => !sc || scopeOf(s) === "shared" || scopeOf(s) === sc;
const usable = () => (S.sources || []).filter(s => seesScope(s, pageScope())).filter(s => {
  if (["weather", "news", "todo", "trash", "entity"].includes(s.type)) return !!s.entity;
  if (s.type === "calendar") return (s.entities || []).length > 0;
  if (s.type === "template") return !!(s.template || "").trim();
  return true;
});
function genPre(s) {
  const lb = JSON.stringify;
  if (s.type === "weather") return `  - alias: ${lb("Get forecast: " + s.label)}\n    action: weather.get_forecasts\n    target:\n      entity_id: ${s.entity}\n    data:\n      type: daily\n    response_variable: fc_${s.id}\n`;
  if (s.type === "calendar") return `  - alias: ${lb("Get events: " + s.label)}\n    action: calendar.get_events\n    target:\n      entity_id:\n${s.entities.map(c => "        - " + c).join("\n")}\n    data:\n      start_date_time: "{{ now().strftime('%Y-%m-%d 00:00:00') }}"\n      duration:\n        days: ${s.days || 7}\n    response_variable: cal_${s.id}\n`;
  if (s.type === "todo") return `  - alias: ${lb("Get items: " + s.label)}\n    action: todo.get_items\n    target:\n      entity_id: ${s.entity}\n    data:\n      status: needs_action\n    response_variable: todo_${s.id}\n`;
  return "";
}
function auto(s) {
  const E = s.entity, A = s.attribute;
  const ent = A ? `{{ state_attr('${E}', '${A}') }}` : `{{ states('${E}') }} {{ states.${E}.attributes | default('', true) }}`;
  if (s.type === "household") return ((s.text || "") + (E ? " " + (A ? ent : `{{ states('${E}') }}`) : "")).trim();
  if (s.type === "locations") return E ? `{% for name, loc in states.${E}.attributes.items() if name != 'friendly_name' %}{{ name }} is at {{ loc }}. {% endfor %}\nA location of Home means they are at our house.` : "{% for p in states.person %}{{ p.name }} is {{ p.state }}. {% endfor %}";
  if (s.type === "weather") return `Right now it is {{ states('${E}') }}, {{ state_attr('${E}', 'temperature') | float(0) | round(0) | int }} degrees, humidity {{ state_attr('${E}', 'humidity') | float(0) | round(0) | int }} percent, wind {{ state_attr('${E}', 'wind_speed') | float(0) | round(0) | int }}.\nDaily forecast:\n{% for d in fc_${s.id}['${E}']['forecast'][:7] %}- {{ d.datetime[:10] }}: {{ d.condition | default('unknown') }}, high {{ d.temperature | default(0) | float(0) | round(0) | int }}, low {{ d.templow | default(0) | float(0) | round(0) | int }}, rain {{ d.precipitation | default(0) | float(0) | round(2) }}\n{% endfor %}` + (s.extra ? `\nInside temp: {{ states('${s.extra}') | float(0) | round(0) | int }} degrees.` : "");
  if (s.type === "news") return `{% for a in (state_attr('${E}', 'entries') or [])[:25] %}- {{ a.title }}: {{ a.summary }}\n{% endfor %}`;
  if (s.type === "calendar") return `{% for cal, d in cal_${s.id}.items() %}[{{ cal }}]\n{% for e in d.events %}- {{ e.summary }}: {{ e.start }}\n{% else %}(no events)\n{% endfor %}{% endfor %}`;
  if (s.type === "todo") return `{% for item in todo_${s.id}.get('${E}', {}).get('items', []) %}- {{ item.summary }}{% if item.get('due') %} (due {{ item.get('due') }}){% endif %}\n{% else %}Nothing on the list.\n{% endfor %}`;
  if (s.type === "trash") return `{{ 'Trash pickup is tomorrow, remind us to take it to the curb.' if is_state('${E}', 'on') else 'No trash pickup tomorrow, do not mention trash.' }}`;
  if (s.type === "entity") return ent;
  return "";
}
const body = s => s.type === "template" ? s.template : (s.template || auto(s));

/* Add a source an AI made, unless one that reads the same thing is already visible here (then reuse it, so nothing piles up).
   New ones are flagged ai:true and scoped to the page or kind that made them. Returns the source. */
function addAiSource(list, type, o, scope) {
  const sc = scope || pageScope() || "shared", sorted = a => JSON.stringify([...(a || [])].sort());
  const hit = list.find(x => seesScope(x, sc) && x.type === type && (type === "calendar" ? sorted(x.entities) === sorted((o || {}).entities)
    : type === "template" ? String(x.template || "").trim() === String((o || {}).template || "").trim()
    : ["household", "locations"].includes(type) ? true : (x.entity || "") === ((o || {}).entity || "") && (x.attribute || "") === ((o || {}).attribute || "")));
  if (hit) return hit;
  const n = mk(list, type, o); n.ai = true; n.scope = sc; list.push(n); return n;
}

/* ---------- entity picker ---------- */
function picker(doms, multi, get, set) {
  const w = el("div", {class: "picker"}), chips = el("div", {class: "chips"}), inp = el("input", {}), list = el("div", {class: "plist"});
  inp.placeholder = "Search or type an entity id" + (doms ? " (" + doms.map(d => d + ".*").join(", ") + ")" : "");
  const draw = () => { chips.replaceChildren(); get().forEach(v => chips.append(el("button", {class: "chip on x", onclick: () => { set(get().filter(x => x !== v)); draw() }}, v))); inp.hidden = !multi && get().length > 0 };
  const pick = id => { set(multi ? [...new Set([...get(), id])] : [id]); inp.value = ""; list.replaceChildren(); draw() };
  const show = () => {
    const t = inp.value.trim().toLowerCase(); list.replaceChildren();
    const add = (txt, sub, id) => list.append(el("div", {class: "pi", onpointerdown: ev => { ev.preventDefault(); pick(id) }}, txt, sub ? el("small", {}, sub) : null));
    if (/^[a-z_]+\.[a-z0-9_]+$/.test(t) && !ENT.some(e => e.id === t) && (!doms || doms.includes(t.split(".")[0]))) add("Use typed value: " + t, "", t);
    ENT.filter(e => !doms || doms.includes(e.id.split(".")[0])).filter(e => !t || e.id.includes(t) || e.name.toLowerCase().includes(t)).slice(0, 30).forEach(e => add(e.name, e.id, e.id));
  };
  inp.oninput = show; inp.onfocus = show; inp.onblur = () => setTimeout(() => list.replaceChildren(), 200);
  draw(); w.append(chips, inp, list); return w;
}

/* "Check with AI" button. getBody() returns what to send ({kind, name, id, yaml, auto_yaml, ai}); res is where the answer goes.
   hooks (optional, turns on the tick boxes and "Fix selected with AI"): state() the editor's current settings, apply(state) puts settings
   back into the editor and marks it as changed, sourceIds() the data source ids that exist. */
function aiReview(btn, res, getBody, hooks) {
  let last = null;
  const busy = (b, on, text) => { b.disabled = on; if (text) b.textContent = text; };
  function showFix(r, before) {
    const out = el("div", {style: "margin-top:12px"});
    if (r.applied.length) {
      out.append(el("div", {class: "note ok"}, el("div", {}, el("b", {}, "Changed " + r.applied.length + " setting" + (r.applied.length === 1 ? "" : "s") + " in the editor. "), "Nothing is saved or pushed yet. Look it over, then Save.")),
        el("div", {class: "list", style: "margin-top:10px"}, r.applied.map(a => el("div", {class: "li"}, el("div", {class: "t"}, el("b", {}, a.key),
          el("small", {style: "display:block"}, "Was: " + (a.before || "(empty)")), el("small", {style: "display:block"}, "Now: " + (a.after || "(empty)")))))));
      const undo = el("button", {type: "button", class: "btn sm", style: "margin-top:10px", onclick: () => { hooks.apply(before); out.replaceChildren(el("div", {class: "note"}, el("div", {}, "Put everything back the way it was."))); }}, "Undo these changes");
      out.append(undo);
    } else out.append(el("div", {class: "note warn"}, el("div", {}, "The AI did not change anything.")));
    (r.notes || []).forEach(n => out.append(el("p", {class: "help"}, (n.done ? "Done" : "Not changed") + " - " + (n.where ? n.where + ": " : "") + n.note)));
    out.append(el("p", {class: "help"}, "Press Check it again to see what is left."));
    return out;
  }
  function draw(r) {
    last = r;
    const probs = r.issues.filter(i => i.level === "problem"), tips = r.issues.filter(i => i.level !== "problem");
    const boxes = [];
    const row = i => {
      const cb = hooks ? el("input", {type: "checkbox", style: "flex:none;width:20px;height:20px;margin-right:2px", "aria-label": "Fix this"}) : null;
      if (cb) boxes.push([cb, i]);
      return el("div", {class: "li"}, cb, el("div", {class: "t"}, el("b", {}, (i.level === "problem" ? "Fix: " : "Tip: ") + (i.where || "")), el("small", {style: "display:block"}, i.message + (i.fix ? " " + i.fix : ""))));
    };
    const fixOut = el("div", {});
    const fixBtn = el("button", {type: "button", class: "btn", disabled: true}, "Fix selected with AI");
    const all = el("button", {type: "button", class: "btn sm"}, "Tick all");
    const upd = () => { const n = boxes.filter(([c]) => c.checked).length; fixBtn.disabled = !n; fixBtn.textContent = n ? "Fix " + n + " selected with AI" : "Fix selected with AI"; };
    boxes.forEach(([c]) => c.onchange = upd);
    const list = r.issues.length ? el("div", {class: "list", style: "margin-top:10px"}, [...probs, ...tips].map(row)) : null;
    boxes.forEach(([c]) => c.onchange = upd);
    all.onclick = () => { const on = boxes.some(([c]) => !c.checked); boxes.forEach(([c]) => c.checked = on); all.textContent = on ? "Untick all" : "Tick all"; upd(); };
    fixBtn.onclick = async () => {
      const picked = boxes.filter(([c]) => c.checked).map(([, i]) => i); if (!picked.length) return;
      const before = JSON.parse(JSON.stringify(hooks.state()));
      busy(fixBtn, true, "Fixing..."); fixOut.replaceChildren(el("p", {class: "dim small"}, "Your AI Task is working on it. This can take up to a minute."));
      try {
        const g = getBody();
        const f = await api("review/fix", {kind: g.kind, name: g.name, id: g.id, ai: g.ai, state: before, issues: picked, source_ids: hooks.sourceIds ? hooks.sourceIds() : [], sources: g.sources});
        if (!f || f.ok === false || f.error) { fixOut.replaceChildren(el("div", {class: "note bad"}, el("div", {}, (f && f.error) || "The fix failed."))); return; }
        if (f.applied.length) hooks.apply(f.state);
        fixOut.replaceChildren(showFix(f, before));
      } catch (e) { fixOut.replaceChildren(el("div", {class: "note bad"}, el("div", {}, "The fix failed: " + e))); }
      finally { busy(fixBtn, false); upd(); }
    };
    res.replaceChildren(...[
      el("div", {class: "note " + (r.verdict === "good" ? "ok" : "warn")}, el("div", {}, el("b", {}, r.verdict === "good" ? "Looks good. " : probs.length + " thing" + (probs.length === 1 ? "" : "s") + " to fix. "), r.summary || "")),
      r.ai_error ? el("p", {class: "help"}, r.ai_error) : null,
      list,
      hooks && r.issues.length && (r.ai && !r.ai_error) ? el("div", {class: "inline", style: "margin-top:10px"}, fixBtn, all) : null,
      hooks && r.issues.length && (!r.ai || r.ai_error) ? el("p", {class: "help"}, "Set an AI Task to let it fix things for you.") : null,
      fixOut,
      r.ai ? el("p", {class: "help"}, "Checked with " + r.ai + ".") : null].filter(Boolean));
  }
  btn.onclick = async () => {
    const b = getBody();
    const old = btn.textContent; busy(btn, true, "Checking...");
    res.replaceChildren(el("p", {class: "dim small"}, "Reading it with your AI Task. This can take up to a minute."));
    try {
      const r = await api("review", b);
      if (!r || r.ok === false || r.error) { res.replaceChildren(el("div", {class: "note bad"}, el("div", {}, (r && r.error) || "The check failed."))); return; }
      draw(r);
    } catch (e) { res.replaceChildren(el("div", {class: "note bad"}, el("div", {}, "The check failed: " + e))); }
    finally { busy(btn, false, old); }
  };
}

/* Repair banner: finds library items that use an AI Task that no longer exists and switches them all to one that does.
   o: {box, items (library items, each {id, name, state, pushed_at}), def (the default AI Task from Settings),
       saveDefault(entity) -> true/false, save(it, state) -> result, push(it, state) -> result, done(text, ok)} */
function aiRepair(o) {
  o.box.replaceChildren();
  const have = ENT.filter(e => e.id.startsWith("ai_task.")).map(e => e.id);
  if (!ENT.length) return;  /* the entity list did not load, so we cannot tell what is missing */
  const ID = /ai_task\.[a-z0-9_]+/g, gone = id => id && !have.includes(id);
  const missingOf = it => {
    const st = it.state || {}, m = new Set();
    if (st.ai) { if (gone(st.ai)) m.add(st.ai); } else if (gone(o.def) && o.def) m.add(o.def);
    ["raw", "autoRaw"].forEach(k => (String(st[k] || "").match(ID) || []).forEach(id => { if (gone(id)) m.add(id); }));
    return [...m];
  };
  const bad = o.items.map(it => ({it, miss: missingOf(it)})).filter(x => x.miss.length);
  const defBad = !!o.def && gone(o.def);
  if (!bad.length && !defBad) return;
  const names = [...new Set(bad.flatMap(x => x.miss).concat(defBad ? [o.def] : []))];
  const sel = el("select", {style: "width:auto;max-width:100%"}, have.map(id => el("option", {value: id}, id)));
  const btn = el("button", {type: "button", class: "btn sm", style: "margin-top:8px"}, have.length ? "Switch them and update" : "No AI Task found");
  btn.disabled = !have.length;
  const msg = el("p", {class: "help"});
  const run = async () => {
    const to = sel.value; btn.disabled = true; msg.textContent = "Working...";
    const fixes = [];
    let defOk = !defBad;
    if (defBad) { defOk = await o.saveDefault(to); if (!defOk) { msg.textContent = "Could not save the new default AI Task."; btn.disabled = false; return; } }
    let done = 0; const fail = [];
    for (const x of bad) {
      const st = JSON.parse(JSON.stringify(x.it.state || {}));
      if (st.ai && gone(st.ai)) st.ai = to;
      ["raw", "autoRaw"].forEach(k => { if (typeof st[k] === "string") st[k] = st[k].replace(ID, id => gone(id) ? to : id); });
      const r = x.it.pushed_at ? await o.push(x.it, st) : await o.save(x.it, st);
      if (r && r.ok) done++; else fail.push(x.it.name + ": " + ((r && (r.detail || r.error)) || "failed"));
    }
    o.done("Switched " + done + " of " + bad.length + " to " + to + (x_default(defBad, to)) + "." + (fail.length ? " Failed: " + fail.join("; ") : ""), !fail.length);
  };
  const x_default = (d, to) => d ? " and made it your default AI Task" : "";
  confirmTap(btn, "Tap again to switch and update Home Assistant", run);
  o.box.append(el("div", {class: "note warn"}, el("div", {},
    el("b", {}, "Some of these use an AI Task that does not exist any more. "), (bad.length ? bad.length + " item" + (bad.length === 1 ? "" : "s") + ": " : "") +
      (bad.length ? bad.slice(0, 6).map(x => x.it.name).join(", ") + (bad.length > 6 ? " and more" : "") + ". " : "Your default AI Task is missing. ") +
      "Missing: " + names.join(", ") + ". They stop at the AI step every time they run, so nothing new is written.",
    el("div", {style: "margin-top:8px"}, el("span", {class: "dim small"}, "Use this one instead: "), sel), btn, msg)));
}

/* AI Task choice for one announcement or fact: use the default from Settings, or pick a specific one.
   get()/set(): the saved override ("" = default). def: the default AI Task entity id. onChange(): called after a change. */
function aiChoice(get, set, def, onChange) {
  const box = el("div", {class: "aichoice"});
  let custom = !!get();
  const draw = () => {
    const seg = el("div", {class: "seg"}, [[false, "Use my default"], [true, "Pick one"]].map(([c, label]) => el("button", {type: "button", class: custom === c ? "on" : "", onclick: () => {
      custom = c; if (!c) { set(""); if (onChange) onChange(); } draw(); }}, label)));
    box.replaceChildren(...[seg,
      custom ? el("div", {style: "margin-top:8px"}, picker(["ai_task"], false, get ? () => (get() ? [get()] : []) : () => [], a => { set(a[0] || ""); if (onChange) onChange(); draw(); }))
        : null,
      el("p", {class: "help"}, custom
        ? (get() ? "This one uses " + get() + "." : "Nothing picked yet, so it uses the default" + (def ? " (" + def + ")" : "") + " until you do.")
        : (def ? "Using your default: " + def + ". Change the default in Announcements > Settings." : "No default AI Task is set. Pick one here, or set a default in Announcements > Settings."))].filter(Boolean));
  };
  draw();
  return box;
}


/* ---------- import: turn a hand-made script or automation into the form ----------
   The server reads it and says which data sources it needs. New ones go in the "Made by AI" section of Settings, only for
   what imported them (one that reads the same thing is reused). Returns the converted result, or {ok:false}. */
async function convertImport(target, yaml, autoYaml) {
  const sc = target === "fact" ? "fact" : "ann";
  const r = await api("convert", {target, yaml, auto_yaml: autoYaml || "", sources: ((typeof S === "object" && S.sources) || []).filter(x => seesScope(x, sc))});
  if (!r || !r.ok) return r || {ok: false, error: "That failed."};
  const fresh = await api("ann/options");  /* start from what is saved now, so nothing is lost */
  if (fresh.error) return {ok: false, error: fresh.error};
  if (!Array.isArray(fresh.sources)) fresh.sources = migrate(fresh);
  let changed = false;
  const ids = (r.sources || []).map(x => {
    if (x.existing && fresh.sources.some(s => s.id === x.existing)) return x.existing;
    const n = mk(fresh.sources, x.new.type, Object.assign({}, x.new, {template: x.new.type === "template" ? x.new.template : ""}));
    n.ai = true; n.scope = sc;  /* made by the import, so it goes in the AI section and only where it was made */
    fresh.sources.push(n); changed = true; return n.id;
  });
  Object.entries(r.settings_add || {}).forEach(([k, add]) => {
    const cur = Array.isArray(fresh[k]) ? fresh[k] : [], more = (add || []).filter(v => !cur.includes(v));
    if (more.length) { fresh[k] = cur.concat(more); changed = true; }
  });
  if (changed) {
    const saved = await api("ann/settings", fresh);
    if (saved.error) return {ok: false, error: saved.error};
    S = saved; if (!Array.isArray(S.sources)) S.sources = [];
  }
  r.state.src = [...new Set(ids)];
  r.added = (r.sources || []).filter(x => !x.existing).map(x => x.label);
  return r;
}
function convertNote(r, what) {
  const split = what === "fact" ? "the instructions, format and rules" : "the instructions and the voice";
  const p = ["Converted into a normal " + what + "." + (r.used_ai ? " Your AI Task split your prompt into " + split + ", so read them before you push." : "")];
  if ((r.added || []).length) p.push("New data sources added to Settings: " + r.added.join(", ") + ".");
  return p.concat(r.notes || []).join(" ");
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

/* ---------- the data sources list in Settings (used by both pages) ----------
   o: {scope: "ann" or "fact" (this page), redraw(), save() (optional, saves after a change)} */
let SRC_OPEN = "";
function srcManager(host, o) {
  const sc = o.scope, okIds = new Set(usable().map(x => x.id)), list = S.sources || (S.sources = []);
  const mine = list.filter(x => seesScope(x, sc));
  const row = x => {
    const r = el("div", {}), top = el("div", {class: "li srcrow", style: "display:flex;align-items:center;gap:10px"});
    const eb = el("button", {class: "btn sm", onclick: () => { SRC_OPEN = SRC_OPEN === x.id ? "" : x.id; o.redraw() }}, SRC_OPEN === x.id ? "Close" : "Edit");
    const db = el("button", {class: "btn danger sm"}, "Remove");
    confirmTap(db, "Tap again", () => { list.splice(list.indexOf(x), 1); if (SRC_OPEN === x.id) SRC_OPEN = ""; o.redraw(); });
    const sub = TYPES[x.type] + (scopeOf(x) !== "shared" && x.ai ? " · " + (scopeOf(x) === "ann" ? "announcements only" : "facts only") : "") + (x.template && x.type !== "template" ? " · custom template" : "") + (okIds.has(x.id) ? "" : " · needs an entity before it shows up");
    top.append(el("div", {class: "t"}, el("b", {}, x.label), el("small", {}, sub)), ...(x.ai ? [el("button", {class: "btn sm", title: "Move it out of the AI section", onclick: () => { delete x.ai; o.redraw(); }}, "Keep")] : []), eb, db);
    r.append(top);
    if (SRC_OPEN === x.id) {
      const use = el("select", {style: "width:auto"}, SCOPES.map(([v, l]) => el("option", {value: v}, l))); use.value = scopeOf(x);
      use.onchange = () => { if (use.value === "shared") delete x.scope; else x.scope = use.value; if (!seesScope(x, sc)) SRC_OPEN = ""; o.redraw(); };
      r.append(el("div", {style: "margin-top:8px"}, el("div", {class: "card sub"}, el("label", {class: "l"}, "Used by"), use,
        el("p", {class: "help"}, "Shared sources show up for both. An announcement or fact that already uses it stops seeing it if you narrow it to the other side.")), editor(x)));
    }
    return r;
  };
  const group = (title, hint, items) => {
    if (!items.length) return;
    host.append(el("h3", {style: "margin-top:16px"}, title + " · " + items.length), hint ? el("p", {class: "help"}, hint) : null, el("div", {class: "stack"}, items.map(row)));
  };
  const own = sc === "fact" ? "Facts only" : "Announcements only";
  group("Shared by announcements and facts", "Either one can use these.", mine.filter(x => !x.ai && scopeOf(x) === "shared"));
  group(own, "Only " + (sc === "fact" ? "facts" : "announcements") + " can use these.", mine.filter(x => !x.ai && scopeOf(x) === sc));
  group("Made by AI", "Added for you by the helper or an import, so they don't mix with the ones you made. Tap Keep to move one into your own list.", mine.filter(x => x.ai));
  if (!mine.length) host.append(el("p", {class: "dim small"}, "No sources yet."));
  const sel = el("select", {style: "width:auto"}), where = el("select", {style: "width:auto"});
  Object.entries(TYPES).forEach(([k, l]) => sel.append(el("option", {value: k}, l)));
  SCOPES.forEach(([v, l]) => where.append(el("option", {value: v}, l)));
  host.append(el("div", {class: "row", style: "margin-top:14px"}, sel, where, el("button", {class: "btn", onclick: () => {
    const n = mk(list, sel.value); if (where.value !== "shared") n.scope = where.value; list.push(n); SRC_OPEN = n.id; o.redraw();
  }}, "Add source")), el("p", {class: "help"}, "Pick who can use it: both, or just one."));
}
/* Save only the sources, on top of what is saved now (the Facts page uses this so it never overwrites Announcements settings). */
async function saveSources() {
  const fresh = await api("ann/options");
  if (fresh.error) return {error: fresh.error};
  fresh.sources = S.sources;
  const saved = await api("ann/settings", fresh);
  if (!saved.error) { S = saved; if (!Array.isArray(S.sources)) S.sources = []; }
  return saved;
}

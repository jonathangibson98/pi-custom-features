/* Facts page: library of saved facts, editor, helper and settings.
   Each fact is ONE Home Assistant automation (triggers, then ask the AI Task, then publish over MQTT). Older facts that were made as a script plus a schedule automation still work and can be switched over. */
let S = {}, F = {}, ENT = [], LIB = [], mem = {};
let cur = {id: null, isNew: true, pushed: false}, E = null, dirty = false, view = "lib", HEL = {entity: "", goal: "", idea: "", back: false};

const aiName = () => S.helper_ai_task_entity || S.ai_task_entity || "";
const fapi = (path, body) => api("facts/" + path, body);
const FASK = "Made with Fact Maker";  // marker the server uses to recognise scripts made here
const RESERVED = /^(current_time|seed|old_fact|fact_.*|src_.*|fc_.*|cal_.*|todo_.*|test_result)$/;
const fslug = s => slug(s, "fact").slice(0, 54).replace(/_$/, "") || "fact";

/* ---------- presets (modeled on the Random Fact, Dark History, Music Fact and City Fact automations) ---------- */
const lines = a => a.join("\n");
const ANGLES = ["a disgusting detail", "an absurd record", "a dark moment", "a myth that is actually false", "a tiny obscure detail", "a dumb mistake", "a wild coincidence"];
const PRE = {
  "Random trivia": {name: "Random Fact", file: "random_fact.txt", swear: "rated",
    task: "Share one real trivia fact about the topic.",
    skip: "honey never spoils, octopus hearts, Cleopatra and the pyramids, bananas being berries",
    picks: [{name: "topic", items: lines(["space and astronomy", "animals and insects", "the human body", "food and drink", "geography", "inventions and technology", "language and words", "sports history", "architecture and engineering", "weather and nature", "money and economics", "transportation"])}, {name: "angle", items: lines(ANGLES)}]},
  "Dark history": {name: "Dark History", file: "random_fact.txt", swear: "rated",
    task: "Share one real dark history fact about the topic.",
    skip: "Vlad the Impaler, iron maidens, Jack the Ripper, plague doctors, Salem witch trials",
    extra: "Only use events that are well documented and verifiable. If you are not sure a detail is real, pick a different fact. No urban legends presented as truth, and no made up dates or numbers. Skip anything involving sexual violence.",
    picks: [{name: "topic", items: lines(["a brutal historical execution or punishment method", "a horrifying medical practice from the past", "a government or corporate cover-up", "a bizarre or ironic historical death", "a disaster caused by pure incompetence", "a forgotten massacre or atrocity", "a creepy unsolved mystery or disappearance", "a messed up old law or tradition", "a notorious prison, asylum, or torture device", "a deadly industrial or workplace horror", "a plague, famine, or mass hysteria event", "a wartime horror most people never heard of"])},
      {name: "angle", items: lines(["a disgusting detail", "a dark moment", "a myth that is actually false", "a tiny obscure detail", "a dumb mistake that got people killed", "a wild coincidence", "a detail that sounds fake but is documented"])}]},
  "Music fact": {name: "Music Fact", file: "music_fact.txt", swear: "rated", style: "titled", obscure: false,
    titleHint: "the artist or band name", heading: "## 🎶MUSIC🎻 Fact About - {{ fact_title }}",
    task: "Pick a real artist or band from the genre given who was active in the decade given. If that genre did not exist in that decade, use the closest real match. Choose one with a well-documented public history, and do NOT pick the most famous name in that genre. Then share one cool, unique music trivia fact about that artist. Skip the famous stuff everyone already knows.",
    extra: "The fact must be real public music history.",
    picks: [{name: "genre", items: lines(["heavy metal", "hip hop", "trap", "punk", "hardcore", "metalcore", "grunge", "southern rap", "industrial", "classic rock", "death metal", "nu metal", "emo", "blues", "outlaw country", "reggae", "funk", "gangsta rap", "post-hardcore", "alternative rock", "jazz", "soul", "electronic", "Latin"])},
      {name: "decade", items: lines(["1980s", "1990s", "2000s", "2010s", "2020s"])},
      {name: "angle", items: lines(["a studio disaster", "a lyric origin story", "a wild feud", "a record or chart oddity", "a tiny obscure detail", "a dumb mistake", "a banned or censored moment", "a weird instrument or gear detail", "a wild coincidence", "a myth that is actually false"])}]},
  "City fact": {name: "City Cool Fact", file: "location_fact.txt", types: ["locations"], obscure: false,
    task: "Pick one city or town from the places listed above at random and share one fascinating, obscure historical or cultural fact about it. Open with the place name, then give the fact. Talk ONLY about the place. Warm and a little playful in tone.",
    picks: []},
  "Daily birthdays (JSON list)": {name: "Daily Birthdays", file: "notable_bday.txt", style: "json", listKey: "birthdays", count: 50, useDate: true, real: true, obscure: false, noPeople: false, avoidLast: false, seed: false,
    task: "List notable real people (celebrities, historical figures, athletes, musicians, actors or public figures) who were born on today's date in history. Use real, verifiable birthdays only. Do not invent people. Use a very wide historical range, from the 2020s back through the 1900s, and mix well known and lesser known names.",
    fields: [{key: "name", hint: "Full Name", type: "text"}, {key: "month", hint: "birth month number", type: "number"}, {key: "day", hint: "birth day of the month", type: "number"}, {key: "year", hint: "birth year", type: "number"}, {key: "known_for", hint: "brief description, 3-6 words", type: "text"}],
    sortBy: "year", sortDir: "desc", keepIf: "p.month | int(0) == now().month and p.day | int(0) == now().day",
    extra: "Every person MUST have been born on today's month and day. A person born on any other date is WRONG, even if they are a great match. Double check each birth month and day before adding them.",
    picks: [], auto: {on: true, every: 12, unit: "hours", watch: "", watchAttr: "", watchFor: 10, home: []}},
  "Blank list (JSON)": {name: "My list", style: "json", listKey: "items", count: 10, picks: [], task: "", obscure: false, noPeople: false, avoidLast: false,
    fields: [{key: "name", hint: "short name", type: "text"}, {key: "detail", hint: "one short sentence", type: "text"}]},
  "Blank": {name: "My fact", picks: [], task: ""}
};

/* ---------- state ---------- */
const defAuto = () => ({on: false, every: 10, unit: "minutes", at: "", watch: "", watchAttr: "", watchFor: 10, home: []});
const blankState = () => ({name: "My fact", src: [], task: "", picks: [], seed: true, len: F.default_length || 180, style: "plain", titleHint: "", heading: "", count: 5,
  file: "", swear: "none", real: true, obscure: true, skip: "", noPeople: true, avoidLast: true, lastEntity: "", lastAttr: "", extra: "", ai: "", auto: defAuto(), autoRaw: "", autoId: "", autoOnly: false,
  asAuto: true, listKey: "items", fields: [], sortBy: "", sortDir: "desc", keepIf: "", useDate: false});
const clone = o => JSON.parse(JSON.stringify(o));
const full = s => Object.assign(blankState(), clone(s || {}), {auto: Object.assign(defAuto(), (s && s.auto) || {})});

const cleanName = n => { n = String(n || "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").replace(/^[0-9]+/, ""); n = n.slice(0, 24); if (!n) return ""; return RESERVED.test(n) ? "pick_" + n : n; };
const itemsOf = p => String(p.items || "").split("\n").map(x => x.trim()).filter(Boolean);
const pickList = s => { const seen = new Set(); return (s.picks || []).map(p => ({name: cleanName(p.name), items: itemsOf(p)})).filter(p => p.name && p.items.length && !seen.has(p.name) && seen.add(p.name)); };
const fileOf = s => (s.file || "").trim() || fslug(s.name) + ".txt";
function topicOf(s) {
  const f = fileOf(s); if (f.includes("/")) return f;
  let pre = F.mqtt_prefix || ""; if (pre && !pre.endsWith("/")) pre += "/";
  return pre + f;
}
const fieldList = s => {
  const seen = new Set();
  const out = (s.fields || []).map(f => ({key: String(f.key || "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, ""), hint: String(f.hint || "").trim(), type: ["text", "number", "yesno"].includes(f.type) ? f.type : "text"}))
    .filter(f => f.key && !seen.has(f.key) && seen.add(f.key)).slice(0, 14);
  return out.length ? out : [{key: "name", hint: "", type: "text"}];
};
const listKeyOf = s => String(s.listKey || "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "items";
const cleanExpr = t => String(t || "").trim().replace(/^\{\{\s*/, "").replace(/\s*\}\}$/, "").replace(/[\r\n]+/g, " ").replace(/%\}/g, "").replace(/\{%/g, "");
const TYPE_WORDS = {text: "text", number: "whole number", yesno: "true or false"};
const lastRef = s => ({entity: s.lastEntity || F.last_entity || "", attr: s.lastEntity ? s.lastAttr : (s.lastAttr || F.last_attribute || "")});
const q1 = t => "'" + String(t).replace(/'/g, "''") + "'";  // single-quoted YAML string

/* ---------- the script ---------- */
function buildPrompt(s, chosen) {
  const P = [], picks = pickList(s), lr = lastRef(s), isJson = s.style === "json";
  if (s.useDate) P.push("Today's date is {{ now().strftime('%B %-d') }}.");
  if (chosen.length) P.push("Current time: {{ current_time }}.");
  chosen.forEach(c => P.push(c.label.toUpperCase() + ":\n{{ src_" + c.id + " }}"));
  const L = picks.map(p => p.name.replace(/_/g, " ").toUpperCase() + " FOR THIS RUN: {{ " + p.name + " }}");
  if (s.seed) L.push("Random seed for variety: {{ seed }}.");
  if (L.length) P.push(L.join("\n"));
  P.push("YOUR TASK: " + ((s.task || "").trim() || "Share one surprising, true fact."));
  if (s.real) P.push(isJson ? "Every item must be real public knowledge that can be verified. If you are not sure about an item, leave it out. Never invent anything: no made up names, dates or numbers." : "The fact must be real public knowledge that can be verified. If you are not sure a detail is true, pick a different fact. Never invent anything: no made up names, dates or numbers.");
  if (s.obscure) P.push("Go obscure. Deep cuts only. Do NOT use famous, overused facts" + ((s.skip || "").trim() ? " (for example: " + s.skip.trim() + ")" : "") + ".");
  if (s.noPeople) P.push("The fact must NOT reference or be about any person in our household or friend group, or their pets, jobs or relationships. Do not say things like \"someone is in\" or \"our\".");
  const rules = [s.extra, F.extra_rules].map(x => (x || "").trim()).filter(Boolean); rules.forEach(r => P.push(r));
  if (s.avoidLast && lr.entity && !isJson) P.push("{% if old_fact %}Do not repeat or rephrase this previous fact" + (s.style === "titled" ? ", and do not reuse its subject (named in its heading)" : "") + ": {{ old_fact }}{% endif %}");
  P.push({none: "Keep the language clean, no profanity.", mild: "Light language is fine, keep it PG-13.", rated: "Use profanity as needed."}[s.swear] || "");
  const n = +s.len || 180;
  if (isJson) { /* no length rule: it is a data list */ }
  else if (s.style === "list") P.push("Each line must be " + n + " characters or less.");
  else P.push("The fact part must be " + n + " characters or less.");
  if (isJson) {
    const J = fieldList(s), key = listKeyOf(s), cnt = Math.max(1, +s.count || 10);
    const ev = f => f.type === "number" ? "0" : f.type === "yesno" ? "true" : JSON.stringify(f.hint || f.key);
    const row = J.map(f => JSON.stringify(f.key) + ": " + ev(f)).join(", ");
    P.push("List " + cnt + " items.\nReturn ONLY valid JSON in exactly this structure, with no markdown code fences, no preamble, no explanation:\n{\"" + key + "\": [{" + row + "}, {" + row + "}]}\nFields: " +
      J.map(f => f.key + " = " + TYPE_WORDS[f.type] + (f.hint ? " (" + f.hint + ")" : "")).join("; ") + ".\nNumbers must be plain JSON numbers, not text.");
  } else if (s.style === "titled") P.push("Return exactly ONE line in this format, with three pipe characters between the two parts:\nTitle ||| The fact text\nThe title part is: " + ((s.titleHint || "").trim() || "a short name for what the fact is about") + ".\nNo markdown, no quotes, no preamble, no explanation.");
  else if (s.style === "list") P.push("Return exactly " + (+s.count || 5) + " lines, one item per line, with no numbering, bullets, markdown, quotes, preamble or explanation.");
  else P.push("Return ONLY the fact as plain text. No JSON, no markdown, no quotes, no preamble, no explanation.");
  return P.filter(x => x !== "").join("\n\n");
}

function makeYaml(s0, o) {
  if (s0.autoOnly) return "";
  if (s0.raw != null) return s0.raw;  /* a pasted script is pushed exactly as written */
  const s = full(s0);
  return "alias: " + JSON.stringify(s.name || "Fact") + "\ndescription: " + FASK + "\nmode: restart\nsequence:\n" + stepsYaml(s, o);
}

/* the steps (load data, pick random details, ask the AI, clean up, publish). A script has them under sequence:, an automation under actions: */
function stepsYaml(s, o) {
  const name = JSON.stringify(s.name || "Fact"), picks = pickList(s), lr = lastRef(s), isJson = s.style === "json";
  const chosen = (s.src || []).map(id => usable().find(x => x.id === id)).filter(Boolean);
  let y = "";
  if (chosen.length) y += "  - variables:\n      current_time: '{{ now().strftime(''%A, %B %-d %Y %-I:%M %p %Z'') }}'\n";
  chosen.forEach(c => { y += genPre(c) });
  if (chosen.length) y += "  - alias: Load data sources\n    variables:\n" + chosen.map(c => { const b = body(c).trim(); return b ? `      src_${c.id}: |-\n` + ind(b, 8) : `      src_${c.id}: ""` }).join("\n") + "\n";
  const useLast = s.avoidLast && !!lr.entity && !isJson, V = [];
  if (useLast) V.push("      old_fact: |-\n" + ind(lr.attr
    ? `{{ state_attr('${lr.entity}', '${lr.attr}') | default('', true) }}`
    : `{% set v = states('${lr.entity}') %}{{ '' if v in ['unknown', 'unavailable'] else v }}`, 8));
  picks.forEach(p => V.push(`      ${p.name}: |-\n` + ind("{{ [" + p.items.map(i => JSON.stringify(i)).join(", ") + "] | random }}", 8)));
  if (s.seed) V.push("      seed: '{{ range(1, 100000) | random }}'");
  if (V.length) y += "  - alias: Pick random details\n    variables:\n" + V.join("\n") + "\n";
  const ai = s.ai || S.ai_task_entity || "ai_task.SET_ME";
  y += "  - alias: Ask the AI\n    action: ai_task.generate_data\n    data:\n      task_name: " + name + "\n      entity_id: " + ai + "\n      instructions: |-\n" + ind(buildPrompt(s, chosen), 8) + "\n    response_variable: fact_raw\n";
  if (isJson) {
    const J = fieldList(s), key = listKeyOf(s), cnt = Math.max(1, +s.count || 10);
    const sortKeys = String(s.sortBy || "").split(",").map(x => x.trim()).filter(k => J.some(f => f.key === k));
    const item = J.map(f => f.type === "number" ? `'${f.key}': (p.get('${f.key}') | int(0))`
      : f.type === "yesno" ? `'${f.key}': (p.get('${f.key}') in [true, 'true', 'True', 'yes', 1])`
      : `'${f.key}': ((p.get('${f.key}') or '') | string | trim)`).join(", ");
    const keep = cleanExpr(s.keepIf) || "true";
    const sorted = sortKeys.length ? `ns.items | sort(attribute='${sortKeys.join(",")}'${s.sortDir === "asc" ? "" : ", reverse=true"})` : "ns.items";
    const tpl = "{% set raw = fact_raw.data %}\n" +
      "{% set d = (raw | string | replace('```json', '') | replace('```', '') | trim | from_json(default={})) if raw is string else raw %}\n" +
      `{% set src = d.get('${key}', []) if d is mapping else (d if d is list else []) %}\n` +
      "{% set ns = namespace(items=[]) %}\n" +
      `{% for p in src %}{% if p is mapping and (${keep}) %}{% set ns.items = ns.items + [{${item}}] %}{% endif %}{% endfor %}\n` +
      `{{ (${sorted})[:${cnt}] | list }}`;
    y += "  - alias: Clean up the answer\n    variables:\n      fact_items: |-\n" + ind(tpl, 8) + "\n";
    if (!(o && o.test)) y += `  - alias: Publish\n    if:\n      - condition: template\n        value_template: "{{ fact_items | length > 0 }}"\n    then:\n      - action: mqtt.publish\n        data:\n          topic: ${JSON.stringify(topicOf(s))}\n          payload: '{{ {"${key}": fact_items} | tojson }}'\n`;
    return y;
  }
  const P = [];
  if (s.style === "titled") {
    P.push("      fact_parts: |-\n        {{ (fact_raw.data | string).split('|||') }}");
    P.push("      fact_title: |-\n        {{ (fact_parts[0] | trim | replace('*', '') | replace('\"', '')) if fact_parts | length > 1 else '' }}");
    P.push("      fact_text: |-\n        {{ (fact_parts[1:] | join(' ') | trim | replace('\"', '')) if fact_parts | length > 1 else '' }}");
  } else if (s.style === "list") {
    P.push("      fact_text: |-\n        {% set ns = namespace(items=[]) %}{% for line in (fact_raw.data | string).split('\\n') %}{% set t = line | trim | replace('\"', '') %}{% if t %}{% set ns.items = ns.items + [t] %}{% endif %}{% endfor %}{{ ns.items[:" + (+s.count || 5) + "] | join('\\n') }}");
  } else P.push("      fact_text: |-\n        {{ fact_raw.data | string | trim | replace('\"', '') }}");
  const head = (s.heading || "").trim();
  P.push("      fact_out: |-\n" + ind((head ? head + "\n\n" : "") + "{{ fact_text }}", 8));
  y += "  - alias: Clean up the answer\n    variables:\n" + P.join("\n") + "\n";
  if (!(o && o.test)) y += `  - alias: Publish\n    if:\n      - condition: template\n        value_template: "{{ fact_text | length > 0 }}"\n    then:\n      - action: mqtt.publish\n        data:\n          topic: ${JSON.stringify(topicOf(s))}\n          payload: "{{ fact_out }}"\n`;
  return y;
}

const autoSummary = a => {
  const p = [];
  if (+a.every > 0) p.push("every " + Math.round(+a.every) + (a.unit === "hours" ? " h" : " min"));
  if (a.at) p.push("daily at " + a.at);
  if (a.watch) p.push("when " + a.watch + " changes");
  return p.join(" and ") || "no trigger set";
};
const F_PREFIX = () => { const p = F.mqtt_prefix || ""; return p && !p.endsWith("/") ? p + "/" : p; };
const isAutoOnly = s => !!(s && s.autoOnly);
const ownAuto = s => !!String((s && s.autoRaw) || "").trim();
function makeAuto(s0, sid) {
  if (ownAuto(s0)) return s0.autoRaw;
  if (s0.raw != null) return "";
  const s = full(s0), a = s.auto;
  if (!a.on) return "";
  const T = [];
  if (+a.every > 0) {
    if (a.unit === "hours") T.push(`  - trigger: time_pattern\n    hours: "/${Math.min(23, Math.max(1, Math.round(+a.every)))}"\n    minutes: 0\n`);
    else T.push(`  - trigger: time_pattern\n    minutes: "/${Math.min(59, Math.max(1, Math.round(+a.every)))}"\n`);
  }
  if (/^\d{1,2}:\d{2}$/.test(a.at || "")) T.push(`  - trigger: time\n    at: "${a.at.padStart(5, "0")}:00"\n`);
  if (a.watch) T.push(`  - trigger: state\n    entity_id: ${a.watch}\n` + (a.watchAttr ? `    attribute: ${a.watchAttr}\n` : "") + (+a.watchFor > 0 ? `    for:\n      seconds: ${Math.round(+a.watchFor)}\n` : ""));
  if (!T.length) return "";
  let y = "alias: " + JSON.stringify((s.name || "Fact") + " (auto)") + "\ndescription: " + FASK + "\nmode: restart\ntriggers:\n" + T.join("");
  const C = (a.home || []).map(e => {
    const d = e.split(".")[0];
    if (d === "zone") return `numeric_state\n        entity_id: ${e}\n        above: 0`;
    if (d === "person" || d === "device_tracker") return `state\n        entity_id: ${e}\n        state: home`;
    return `state\n        entity_id: ${e}\n        state: "on"`;
  });
  if (C.length === 1) y += "conditions:\n  - condition: " + C[0].replace(/\n        /g, "\n    ") + "\n";
  else if (C.length) y += "conditions:\n  - condition: or\n    conditions:\n" + C.map(c => "      - condition: " + c + "\n").join("");
  y += "actions:\n  - action: script." + sid + "\n";
  return y;
}
/* a generated fact as ONE automation: the schedule triggers, the presence conditions, and the steps as its actions */
const isAsAuto = s => !!(s && s.asAuto && !s.autoOnly && s.raw == null);
const viaAuto = s => isAutoOnly(s) || isAsAuto(s);
function makeAutomation(s0, sid) {
  const s = full(s0), a = s.auto, T = [];
  if (a.on && +a.every > 0) {
    if (a.unit === "hours") T.push(`  - trigger: time_pattern\n    hours: "/${Math.min(23, Math.max(1, Math.round(+a.every)))}"\n    minutes: 0\n`);
    else T.push(`  - trigger: time_pattern\n    minutes: "/${Math.min(59, Math.max(1, Math.round(+a.every)))}"\n`);
  }
  if (a.on && /^\d{1,2}:\d{2}$/.test(a.at || "")) T.push(`  - trigger: time\n    at: "${a.at.padStart(5, "0")}:00"\n`);
  if (a.on && a.watch) T.push(`  - trigger: state\n    entity_id: ${a.watch}\n` + (a.watchAttr ? `    attribute: ${a.watchAttr}\n` : "") + (+a.watchFor > 0 ? `    for:\n      seconds: ${Math.round(+a.watchFor)}\n` : ""));
  let y = "alias: " + JSON.stringify(s.name || "Fact") + "\ndescription: " + FASK + "\nmode: restart\n" + (T.length ? "triggers:\n" + T.join("") : "triggers: []\n");
  const C = (a.on ? (a.home || []) : []).map(e => {
    const d = e.split(".")[0];
    if (d === "zone") return `numeric_state\n        entity_id: ${e}\n        above: 0`;
    if (d === "person" || d === "device_tracker") return `state\n        entity_id: ${e}\n        state: home`;
    return `state\n        entity_id: ${e}\n        state: "on"`;
  });
  if (C.length === 1) y += "conditions:\n  - condition: " + C[0].replace(/\n        /g, "\n    ") + "\n";
  else if (C.length) y += "conditions:\n  - condition: or\n    conditions:\n" + C.map(c => "      - condition: " + c + "\n").join("");
  else y += "conditions: []\n";
  return y + "actions:\n" + stepsYaml(s, {});
}
const pushBody = (s, id, extra) => Object.assign({id, yaml: viaAuto(s) ? "" : makeYaml(s), auto_yaml: isAsAuto(s) ? makeAutomation(s, id) : makeAuto(s, id), state: s,
  auto_raw: ownAuto(s) && !isAsAuto(s), auto_only: viaAuto(s), cleanup_script: isAsAuto(s), auto_id: viaAuto(s) ? id : ownAuto(s) ? (s.autoId || "") : ""}, extra || {});
const hasTrigger = s => !!(s.auto && ((+s.auto.every > 0) || s.auto.at || s.auto.watch));

/* ---------- DOM ---------- */
/* ---------- views ---------- */
function showView(v) {
  view = v;
  $("#chrome").hidden = v === "edit";
  ["lib", "help", "set", "edit"].forEach(k => $("#v-" + k).hidden = k !== v);
  $$("#tabs .tab").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  $("#dock").hidden = v !== "set";
  try { window.scrollTo(0, 0) } catch (e) {}
}
$$("#tabs .tab").forEach(b => b.onclick = () => { showView(b.dataset.v); if (b.dataset.v === "lib") loadLib(); });

function setupNote() {
  const miss = [];
  if (!S.ai_task_entity) miss.push("an AI Task (set it in Announcements > Settings or the add-on options)");
  const box = $("#setupnote"); box.replaceChildren();
  if (!miss.length) return;
  box.append(el("div", {class: "note warn"}, el("div", {}, el("b", {}, "Finish setup to make facts. "), "Still needed: " + miss.join(", ") + "."),
    el("button", {class: "btn sm", onclick: () => showView("set")}, "Open Settings")));
}

/* ---------- library ---------- */
function flash(text, cls) { const m = $("#libmsg"); m.className = "msg " + (cls || ""); m.textContent = text || ""; }
async function loadLib() {
  const d = await fapi("library");
  if (d.error) { flash(d.error, "bad"); return; }
  LIB = d.items || [];
  if ((d.renamed || []).length) flash("Picked up from Home Assistant: " + d.renamed.map(x => x.from + " is now " + x.to).join(", ") + ".", "ok");
  $("#libcount").textContent = LIB.length;
  renderLib();
}
function renderLib() {
  const live = LIB.filter(x => x.pushed_at || x.in_ha).length;
  $("#libsub").textContent = LIB.length ? LIB.length + " fact" + (LIB.length === 1 ? "" : "s") + ", " + live + " in Home Assistant" : "";
  $("#updall").hidden = !LIB.some(x => x.pushed_at);
  const box = $("#cards"); box.replaceChildren();
  if (!LIB.length) {
    box.style.display = "block";
    box.append(el("div", {class: "card empty"}, el("h3", {}, "No facts yet"),
      el("p", {}, "Say what the fact should be about, add some random topics to keep it fresh, and choose where it is saved."),
      el("div", {class: "row"}, el("button", {class: "btn primary", onclick: () => openNew()}, "Make your first fact"))));
  } else box.style.display = "";
  LIB.forEach(it => box.append(libCard(it)));
}
function libCard(it) {
  const st = it.state || {}, raw = st.raw != null;
  const status = !it.pushed_at && !it.in_ha ? ["warn", "Draft, not in Home Assistant"] : it.in_ha ? ["ok", "In Home Assistant"] : ["bad", "Missing in Home Assistant"];
  const msg = el("div", {class: "msg", style: "margin:0"});
  const del = el("button", {class: "btn danger sm"}, "Delete");
  confirmTap(del, isAutoOnly(st) ? "Tap again: forgets it here (HA keeps it)" : it.in_ha ? (isAsAuto(st) ? "Tap again: removes the automation too" : "Tap again: removes the script too") : "Tap again to delete", () => removeFact(it.id, !isAutoOnly(st) && !!it.in_ha));
  const run = el("button", {class: "btn sm", disabled: !it.in_ha, title: it.in_ha ? "Run it now" : "Push it to Home Assistant first", onclick: async () => {
    run.disabled = true; msg.className = "msg"; msg.textContent = "Starting...";
    const r = await fapi("run", {id: it.id, auto_only: viaAuto(st)}); msg.className = "msg " + (r.ok ? "ok" : "bad"); msg.textContent = r.ok ? "Started." : (r.detail || r.error); run.disabled = false;
  }}, "Run now");
  const dup = el("button", {class: "btn sm", onclick: async () => {
    const nm = (it.name || it.id) + " copy", id = uniqueId(fslug(nm));
    const r = await fapi("library/save", {id, name: nm, state: Object.assign({}, st, {name: nm}, raw ? {raw: setAlias(st.raw, nm)} : {})});
    if (r.ok) { flash("Copied as a draft: " + id, "ok"); loadLib(); } else flash(r.error, "bad");
  }}, "Duplicate");
  const a = st.auto || {}, pills = [];
  const autoPill = () => !it.auto_in_ha ? el("span", {class: "pill warn"}, "Automation not pushed") : it.auto_on ? el("span", {class: "pill ok"}, "Your automation is on") : el("span", {class: "pill warn"}, "Your automation is off in HA");
  if (isAutoOnly(st)) { pills.push(el("span", {class: "pill plain"}, "Own automation")); pills.push(autoPill()); }
  else if (raw) { pills.push(el("span", {class: "pill plain"}, "Own script")); if (ownAuto(st)) pills.push(autoPill()); }
  else if (ownAuto(st)) {
    pills.push(el("span", {class: "pill plain"}, fileOf(Object.assign({}, st, {name: st.name || it.name}))));
    pills.push(autoPill());
  } else if (isAsAuto(st)) {
    pills.push(el("span", {class: "pill plain"}, fileOf(Object.assign({}, st, {name: st.name || it.name}))));
    if (st.style === "json") pills.push(el("span", {class: "pill plain"}, "JSON list"));
    if (!it.auto_in_ha) pills.push(el("span", {class: "pill warn"}, "Automation not pushed"));
    else if (!it.auto_on) pills.push(el("span", {class: "pill warn"}, "Automation is off in HA"));
    else pills.push(el("span", {class: "pill ok"}, a.on ? "Runs " + autoSummary(a) : "Manual only (use Run now)"));
  } else {
    pills.push(el("span", {class: "pill plain"}, fileOf(Object.assign({}, st, {name: st.name || it.name}))));
    if (a.on) pills.push(!it.auto_in_ha ? el("span", {class: "pill warn"}, "Schedule not pushed") : it.auto_on ? el("span", {class: "pill ok"}, "Runs " + autoSummary(a)) : el("span", {class: "pill warn"}, "Schedule is off in HA"));
    else pills.push(el("span", {class: "pill plain"}, "Manual only"));
  }
  pills.push(el("span", {class: "pill plain"}, "Edited " + ago(it.updated)));
  return el("div", {class: "card ann"},
    el("div", {class: "top"}, el("div", {style: "min-width:0"}, el("h3", {}, it.name || it.id), el("div", {class: "dim small mono"}, (viaAuto(st) ? "automation id: " : "script.") + it.id)), el("span", {class: "pill " + status[0]}, status[1])),
    el("div", {class: "clamp"}, isAutoOnly(st) ? "Your own automation, kept exactly as you wrote it. Open it to convert it to the normal form." : raw ? "Your own script, kept exactly as you wrote it. Open it to convert it to the normal form." : (st.task || "No instructions yet.")),
    el("div", {class: "meta"}, pills),
    el("div", {class: "acts"}, el("button", {class: "btn primary sm", onclick: () => openItem(it)}, "Edit"), run, el("button", {class: "btn sm", title: "Copy a dashboard card for this fact", onclick: () => copyCards([it], (t, c) => { msg.className = "msg " + (c || ""); msg.textContent = t; })}, "Copy card"), dup,
      renameButton(it.name || it.id, (n, m) => api("rename", {match_id: m, lib: "facts", id: it.id, name: n}), r => { flash(r.in_ha ? "Renamed in Home Assistant too. The id stays " + it.id + "." + (r.note ? " " + r.note : "") : "Renamed. Push it to use the new name in Home Assistant.", "ok"); loadLib(); }), del), msg);
}
async function removeFact(id, alsoScript) {
  const r = await fapi("library/delete", {id, delete_script: !!alsoScript});
  if (r.ok) { flash(r.script_deleted ? "Deleted " + id + " and removed it from Home Assistant." : "Deleted " + id + ".", "ok"); loadLib(); } else flash(r.error, "bad");
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
    const s = it.state || {}, r = await fapi("push", pushBody(s, it.id));
    if (r.ok) ok++; else bad.push(it.name + ": " + (r.detail || r.error));
  }
  flash("Updated " + ok + " of " + todo.length + " with your current settings." + (bad.length ? " Failed: " + bad.join("; ") : ""), bad.length ? "bad" : "ok");
  loadLib();
}

/* ---------- ids ---------- */
function takenIds() {
  const s = new Set(LIB.map(x => x.id));
  ENT.forEach(e => { if (e.id.startsWith("script.")) s.add(e.id.slice(7)); });
  return s;
}
function uniqueId(base) {
  const t = takenIds(); let id = base, n = 2;
  while (t.has(id)) id = base.slice(0, 50) + "_" + (n++);
  return id;
}

/* ---------- your own pasted script ---------- */
const cleanId = x => { x = String(x || "").trim().toLowerCase().replace(/^script\./, ""); return /^[a-z0-9_]{1,54}$/.test(x) ? x : "" };
function getAlias(y) {
  const m = String(y).match(/^alias:[ \t]*(.+?)[ \t]*$/m); if (!m) return "";
  let v = m[1]; if (/^[>|]/.test(v)) return "";
  if (v[0] === '"' && v.endsWith('"')) { try { return JSON.parse(v) } catch (e) { return v.slice(1, -1) } }
  if (v[0] === "'" && v.endsWith("'")) return v.slice(1, -1).replace(/''/g, "'");
  return v;
}
function setAlias(y, name) {
  const line = "alias: " + JSON.stringify(name || "Fact");
  return /^alias:.*$/m.test(y) ? y.replace(/^alias:.*$/m, () => line) : line + "\n" + y;
}
const imsg = (t, c) => { const m = $("#impmsg"); m.className = "msg " + (c || ""); m.textContent = t || ""; };
function fillAutoPick() {
  const sel = $("#impauto"); sel.replaceChildren(el("option", {value: ""}, "None"));
  loadAutos().then(L => L.forEach(a => sel.append(el("option", {value: a.id}, a.name + " (" + a.state + ")"))));
}
function fillPick() {
  const sel = $("#imppick"); sel.replaceChildren(el("option", {value: ""}, "Choose a script..."));
  ENT.filter(e => e.id.startsWith("script.")).forEach(e => sel.append(el("option", {value: e.id.slice(7)}, e.name + " (" + e.id + ")")));
}
$("#importbtn").onclick = () => { $("#importbox").hidden = false; imsg(""); fillPick(); fillAutoPick(); $("#impyaml").focus(); };
$("#impcancel").onclick = () => { $("#importbox").hidden = true; imsg(""); };
$("#imppickgo").onclick = async () => {
  const id = $("#imppick").value; if (!id) { imsg("Choose a script first.", "warn"); return; }
  imsg("Loading...");
  const r = await api("ann/script?id=" + encodeURIComponent(id));
  if (!r.ok) { imsg(r.error, "bad"); return; }
  $("#impyaml").value = r.yaml; $("#impid").value = id; imsg("Loaded. Press Import to take it over.", "ok");
};
const looksAuto = t => /^[ \t-]*(triggers?|actions?|automation)[ \t]*:/m.test(t) && !/^[ \t]*sequence[ \t]*:/m.test(t);
async function importAutoOnly(b) {
  const picked = $("#impauto").value, text = $("#impyaml").value;
  let yml, alias, id = "", takeover = false;
  b.disabled = true; imsg("Checking your automation...");
  if (!text.trim() && picked) {
    const r = await api("facts/automation?id=" + encodeURIComponent(picked));
    b.disabled = false;
    if (!r.ok) { imsg(r.error, "bad"); return; }
    yml = r.yaml; alias = (r.config && r.config.alias) || picked; id = picked; takeover = true;
  } else {
    const r = await api("facts/import_auto", {yaml: text});
    b.disabled = false;
    if (!r.ok) { imsg(r.error || "That failed.", "bad"); return; }
    yml = r.yaml; alias = r.alias; id = r.id || "";
    const L = await loadAutos();
    const same = L.find(a => a.id === id) || L.find(a => a.name.trim().toLowerCase() === alias.trim().toLowerCase());
    if (same) { id = same.id; takeover = true; }
  }
  const typed = $("#impid").value.trim().toLowerCase();
  if (typed) { if (!/^[a-z0-9_]{1,60}$/.test(typed)) { imsg("The id can only use lowercase letters, numbers and underscores (60 at most).", "bad"); return; } id = typed; takeover = (AUTOS || []).some(a => a.id === id); }
  if (!id) id = uniqueId(fslug(alias));
  if (LIB.some(x => x.id === id)) { imsg(id + " is already in My facts. Open it from the list below.", "bad"); return; }
  $("#importbox").hidden = true; $("#impyaml").value = ""; $("#impid").value = ""; $("#impauto").value = ""; imsg("");
  openEditor(Object.assign(blankState(), {name: alias, autoOnly: true, autoRaw: yml, autoId: id}), {id, isNew: true, pushed: false, saved: false, fixedId: true},
    "Imported. Your automation is kept exactly as written. " + (takeover ? "It matches an automation you already have in Home Assistant, so pushing replaces it (a copy of the old one is saved first)." : "Pushing creates it as a new automation in Home Assistant."));
  markDirty();
}
$("#copyall").onclick = () => copyCards(LIB, (t, c) => { const m = $("#libmsg"); m.className = "msg " + (c || ""); m.textContent = t; });
$("#impgo").onclick = async () => {
  const b = $("#impgo"), typed = $("#impid").value.trim();
  if (($$('[name="impmode"]').find(x => x.checked) || {}).value !== "raw") { await importConvert(b, typed); return; }
  if ((!$("#impyaml").value.trim() && $("#impauto").value) || looksAuto($("#impyaml").value)) { await importAutoOnly(b); return; }
  if (typed && !cleanId(typed)) { imsg("The script id can only use lowercase letters, numbers and underscores (54 at most).", "bad"); return; }
  b.disabled = true; imsg("Checking your script...");
  const r = await api("ann/import", {yaml: $("#impyaml").value});
  b.disabled = false;
  if (!r.ok) { imsg(r.error || "That failed.", "bad"); return; }
  const id = cleanId(typed) || cleanId(r.id) || uniqueId(fslug(r.alias)), takeover = !!(cleanId(typed) || cleanId(r.id));
  if (LIB.some(x => x.id === id)) { imsg("script." + id + " is already in My facts. Open it from the list below.", "bad"); return; }
  const inHA = ENT.some(e => e.id === "script." + id);
  let autoState = {};
  const pickedAuto = $("#impauto").value;
  if (pickedAuto) {
    const ar = await api("facts/automation?id=" + encodeURIComponent(pickedAuto));
    if (!ar.ok) { imsg(ar.error || "Could not load that automation.", "bad"); return; }
    autoState = {autoRaw: ar.yaml, autoId: ar.id};
  }
  $("#importbox").hidden = true; $("#impyaml").value = ""; $("#impid").value = ""; $("#impauto").value = ""; imsg("");
  openEditor(Object.assign(blankState(), {name: r.alias, raw: r.yaml}, autoState), {id, isNew: true, pushed: false, saved: false, fixedId: true},
    "Imported. Your script" + (autoState.autoRaw ? " and its automation are" : " is") + " kept exactly as written. " + (inHA ? "script." + id + " already exists in Home Assistant, so pushing replaces it." : "Pushing creates script." + id + " in Home Assistant.") + (takeover ? "" : " Nothing is in Home Assistant yet."));
  markDirty();
};

/* convert a fact that is still an own automation or own script (kept as written) into the normal form, keeping its id */
async function convertExisting(btn) {
  const own = isAutoOnly(E), text = own ? E.autoRaw : E.raw, autoText = own ? "" : (E.autoRaw || "");
  if (!String(text || "").trim()) { say("There is nothing to convert yet.", "warn"); return; }
  btn.disabled = true; say("Converting. Your AI Task helps with the prompt, so this can take a minute...");
  const r = await convertImport("fact", text, autoText);
  btn.disabled = false;
  if (!r.ok) { say(r.error || "That failed.", "bad"); return; }
  const keep = {id: cur.id, isNew: cur.isNew, pushed: cur.pushed, saved: cur.saved, fixedId: true};
  const where = own ? "Pushing replaces your automation " + cur.id + " in place with the form's version (a copy of the old one is saved first)."
                    : "Pushing turns it into one automation with the id " + cur.id + ".";
  openEditor(Object.assign(blankState(), r.state, {name: E.name || r.state.name, original: own ? text : (r.original || text), originalAuto: autoText}), keep,
    convertNote(r, "fact") + " " + where + " Until you push, Use my original instead goes back.");
  markDirty(); say("Converted. Nothing is saved yet: check it, then Save or Save and push.", "ok");
}

/* convert a pasted script or automation (or one picked from the list) into a normal form fact */
async function importConvert(b, typed) {
  let text = $("#impyaml").value, autoText = "";
  const picked = $("#impauto").value;
  if (picked) {
    const ar = await api("facts/automation?id=" + encodeURIComponent(picked));
    if (!ar.ok) { imsg(ar.error || "Could not load that automation.", "bad"); return; }
    if (text.trim()) autoText = ar.yaml; else text = ar.yaml;
  }
  if (!text.trim()) { imsg("Paste your script or automation, or pick one, first.", "warn"); return; }
  if (typed && !/^[a-z0-9_]{1,60}$/.test(typed)) { imsg("The id can only use lowercase letters, numbers and underscores.", "bad"); return; }
  b.disabled = true; imsg("Reading it and converting. Your AI Task helps with the prompt, so this can take a minute...");
  const r = await convertImport("fact", text, autoText);
  b.disabled = false;
  if (!r.ok) { imsg(r.error || "That failed.", "bad"); return; }
  const id = typed || (/^[a-z0-9_]{1,60}$/.test(r.id || "") ? r.id : "") || uniqueId(fslug(r.name));
  if (LIB.some(x => x.id === id)) { imsg(id + " is already in My facts. Open it from the list below.", "bad"); return; }
  const takeover = (await loadAutos()).some(a => a.id === id);
  $("#importbox").hidden = true; $("#impyaml").value = ""; $("#impid").value = ""; $("#impauto").value = ""; imsg("");
  openEditor(Object.assign(blankState(), r.state, {original: r.original}), {id, isNew: true, pushed: false, saved: false, fixedId: true},
    convertNote(r, "fact") + " " + (takeover ? "Pushing replaces your automation " + id + " in place (a copy of the old one is saved first)." : "Pushing creates it as one automation in Home Assistant."));
  markDirty();
}

/* ---------- your own automation ---------- */
let AUTOS = null;
async function loadAutos() {
  if (AUTOS) return AUTOS;
  const r = await api("facts/automations");
  AUTOS = r && r.ok ? r.items : [];
  return AUTOS;
}
function autoCard(n) {
  const has = ownAuto(E);
  const c = card(n, "Your own automation", "Optional. Keep an automation you already have, exactly as written. It is pushed with this script and replaces the schedule below.");
  const sel = el("select", {style: "max-width:420px"}, el("option", {value: ""}, "Load one you already have..."));
  loadAutos().then(L => L.forEach(a => sel.append(el("option", {value: a.id}, a.name + " (" + a.state + ")"))));
  const ta = el("textarea", {class: "code", spellcheck: "false", style: "min-height:220px", placeholder: "alias: My fact schedule\ntriggers:\n  - trigger: time_pattern\n    minutes: \"/10\"\nactions:\n  - action: script.my_fact", value: E.autoRaw || ""});
  const idin = el("input", {value: E.autoId || "", placeholder: "automation id (blank = new one)", style: "max-width:320px", autocomplete: "off"});
  const note = el("p", {class: "msg"});
  ta.oninput = () => { E.autoRaw = ta.value; changed(); };
  idin.oninput = () => { E.autoId = idin.value.trim().toLowerCase(); changed(); };
  const load = el("button", {class: "btn sm", onclick: async () => {
    if (!sel.value) { note.className = "msg warn"; note.textContent = "Choose an automation first."; return; }
    note.className = "msg"; note.textContent = "Loading...";
    const r = await api("facts/automation?id=" + encodeURIComponent(sel.value));
    if (!r.ok) { note.className = "msg bad"; note.textContent = r.error; return; }
    ta.value = E.autoRaw = r.yaml; idin.value = E.autoId = r.id; changed();
    note.className = "msg ok"; note.textContent = "Loaded. Pushing replaces it in Home Assistant (a copy of the old one is saved first).";
  }}, "Load");
  const clear = el("button", {class: "btn sm", onclick: () => { E.autoRaw = ""; E.autoId = ""; changed(); drawForm(); }}, "Remove it from this fact");
  add(c, el("div", {class: "row"}, sel, load), el("label", {class: "l"}, "Automation YAML"), ta,
    el("label", {class: "l"}, "Automation id"), idin,
    el("p", {class: "help"}, "Leave the id blank to make a new automation, or load one so pushing updates that same automation."),
    el("div", {class: "row", style: "margin-top:10px"}, has ? clear : null), note);
  return c;
}

/* ---------- visual editor for your own automation or script ---------- */
let FORMCTX = null;
/* field: which part of the state holds the YAML ("autoRaw" or "raw"); script: true for a script (steps only) */
function formCards(n, field, script) {
  let A = AF.Y.parse(E[field] || "");
  const holder = el("div", {class: "stack"});
  const msg = el("p", {class: "msg"});
  const ta = el("textarea", {class: "code", spellcheck: "false", style: "min-height:440px", value: E[field] || ""});
  const ctx = {
    commit() { E[field] = AF.Y.dump(A); ta.value = E[field]; changed(); },
    redraw() { draw(); },
    setAlias(v) { if (!A) { E[field] = setAlias(E[field], v); ta.value = E[field]; changed(); return; } A.alias = v; this.commit(); },
  };
  const draw = () => {
    holder.replaceChildren();
    if (!A) { holder.append(el("p", {class: "msg bad"}, "The YAML below could not be read, so the fields are hidden. Fix it and tap outside the box.")); return; }
    AF.cards(A, ctx, n, {script}).forEach(c => holder.append(c));
  };
  ta.oninput = () => { E[field] = ta.value; const a = getAlias(ta.value); if (a) { E.name = a; const ni = $("#form input"); if (ni) ni.value = a; } changed(); };
  ta.onchange = () => {
    const o = AF.Y.parse(ta.value), w = o ? "" : AF.Y.why(ta.value) || "That needs to be key: value lines.";
    if (!o) { A = null; msg.className = "msg bad"; msg.textContent = w; draw(); return; }
    A = o; msg.className = "msg ok"; msg.textContent = "Read. The fields above now match this YAML."; draw();
  };
  const chk = el("button", {class: "btn sm", onclick: async () => {
    say("Checking...");
    const r = script ? await api("ann/import", {yaml: E[field]}) : await api("facts/import_auto", {yaml: E[field]});
    say(r.ok ? "That is a valid " + (script ? "script." : "automation.") : r.error, r.ok ? "ok" : "bad");
  }}, "Check YAML");
  FORMCTX = ctx;
  draw();
  const adv = el("details", {class: "card"}, el("summary", {}, el("b", {}, "Full YAML (advanced)")),
    el("p", {class: "help", style: "margin:8px 0"}, "The same thing as the fields above. Edit either one. Changes made with the fields tidy up how the YAML is laid out, and what it does stays the same."),
    ta, el("div", {class: "row", style: "margin-top:10px"}, chk), msg);
  return [holder, adv];
}
function autoOnlyCard(n) { return formCards(n, "autoRaw", false); }

const TOPIC_RE = /^([ \t-]*topic:[ \t]*)(.+?)[ \t]*$/gm;
const topicsIn = y => [...String(y || "").matchAll(TOPIC_RE)].map(m => ({val: m[2].replace(/^(['"])(.*)\1$/, "$2")}));

/* ---------- dashboard card ---------- */
async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true; } catch (e) { /* the app's frame may block the clipboard */ }
  const ta = el("textarea", {style: "position:fixed;top:0;left:0;opacity:0"}); ta.value = t; document.body.append(ta); ta.focus(); ta.select();
  try { ta.setSelectionRange(0, t.length); } catch (e) { /* ignore */ }
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
  ta.remove(); return ok;
}
/* which fields of each item the rotating card shows, and how: title (bold), text, small (dim) or hide */
function defaultShow(s) {
  if (isAsAuto(s) && s.style === "json") {
    let first = true;
    return fieldList(s).filter(f => f.type === "text" || f.key === "year").map(f => {
      if (f.key === "year") return {key: f.key, as: "title"};
      const as = first ? "title" : "text"; first = false; return {key: f.key, as};
    });
  }
  return [{key: "name", as: "title"}, {key: "year", as: "title"}, {key: "known_for", as: "text"}, {key: "reason", as: "small"}];
}
function defaultCard(s) {
  const f = isAutoOnly(s) ? ((topicsIn(s.autoRaw)[0] || {}).val || "") : fileOf(s);
  const base = (f.split("/").pop() || "").replace(/\.[^.]*$/, "");
  const key = isAsAuto(s) && s.style === "json" ? listKeyOf(s) : ((String(s.autoRaw || "").match(/\{\s*"(\w+)"\s*:/) || [])[1]) || "items";
  const list = (isAutoOnly(s) && /tojson/.test(s.autoRaw || "")) || (isAsAuto(s) && s.style === "json");
  return {kind: list ? "list" : "text", show: defaultShow(s), secs: 8, height: 140, cpl: 40, scroll: false, toggle: "", sensor: s.lastEntity || (base ? "sensor.read_" + base : "sensor.read_fact"), emoji: list ? "📋" : "🎱", title: s.name || "Fact", key};
}
const cardOf = s => { const c = Object.assign(defaultCard(s), s.card || {}); if (c.kind === "scroll") { c.kind = "list"; c.scroll = true; } return c; };
const jq = t => String(t).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
/* wraps any card so it only shows while an input_boolean is on */
function cardYaml(s) {
  const c = cardOf(s), y = cardYamlBase(s), t = String(c.toggle || "").trim();
  if (!/^input_boolean\.[a-z0-9_]+$/.test(t)) return y;
  return "type: conditional\nconditions:\n  - condition: state\n    entity: " + t + "\n    state: 'on'\ncard:\n" + y.trimEnd().split("\n").map(l => l ? "  " + l : l).join("\n") + "\n";
}
function cardYamlBase(s) {
  const c = cardOf(s), L = [];
  const GLASS = [
    "ha-card {",
    "  background: rgba(255, 255, 255, 0.06) !important;",
    "  backdrop-filter: blur(28px) saturate(200%) !important;",
    "  -webkit-backdrop-filter: blur(28px) saturate(200%) !important;",
    "  border: 1px solid rgba(255, 255, 255, 0.2) !important;",
    "  border-radius: 20px !important;",
    "  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.4), inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;",
    "  color: rgba(255,255,255,0.9);"];
  if (c.kind === "list") {
    const key = String(c.key || "items").replace(/[^A-Za-z0-9_]/g, ""), secs = Math.max(2, +c.secs || 8), H = Math.max(80, +c.height || 140), SC = !!c.scroll, CPL = Math.max(10, +c.cpl || 40);
    const show = (c.show || []).map(x => ({key: String(x.key || "").replace(/[^A-Za-z0-9_]/g, ""), as: x.as})).filter(x => x.key && x.as !== "hide");
    const keysOf = r => show.filter(x => x.as === r).map(x => "'" + x.key + "'").join(", ");
    const roles = ["title", "text", "small"].filter(r => keysOf(r));
    const part = r => [
      "      {% set n_" + r + " = namespace(l=[]) %}",
      "      {% for k in [" + keysOf(r) + "] %}{% set v = person.get(k) %}{% if v is not none and v != '' and not (k == 'year' and v == 0) %}{% set n_" + r + ".l = n_" + r + ".l + [((v | abs | string) ~ ' BC') if (k == 'year' and v is number and v < 0) else (v | string)] %}{% endif %}{% endfor %}"];
    const out = {title: "      <b>{{ n_title.l | join(', ') }}</b>", text: "      <div class=\"fx-text\">{{ n_text.l | join(' · ') }}</div>", small: "      <div class=\"fx-reason\">{{ n_small.l | join(' · ') }}</div>"};
    L.push("{% set raw = (state_attr('" + jq(c.sensor) + "', 'content') or '') | replace('```json', '') | replace('```', '') | trim %}",
      "{% set data = (raw | from_json(default={})) if raw else {} %}",
      "{% set people = data.get('" + jq(key) + "', []) if data is mapping else (data if data is list else []) %}",
      "{% set count = [people | length, 1] | max %}",
      "{% set seconds_per_item = " + secs + " %}", "{% set total_duration = count * seconds_per_item %}", "{% set pct_per_item = 100 / count %}",
      "<style>", ...GLASS.map(x => "  " + x), "  height: " + H + "px !important;", "  overflow: hidden !important;", "}",
      ".fx-wrap { position: relative; height: " + (H - 60) + "px; overflow: hidden; padding: 0 16px; box-sizing: border-box; }",
      ".fx-item { position: absolute; top: 0; left: 16px; right: 16px; font-size: 18px; line-height: 1.3; opacity: 0; animation: fx-cycle {{ total_duration }}s infinite; }",
      ".fx-text { font-size: 15px; margin-top: 2px; }",
      ".fx-reason { font-size: 13px; opacity: 0.7; margin-top: 2px; }",
      "@keyframes fx-cycle {", "  0%, 100% { opacity: 0; }", "  2% { opacity: 1; }", "  {{ (pct_per_item - 2) | round(2) }}% { opacity: 1; }", "  {{ pct_per_item | round(2) }}% { opacity: 0; }", "}",
      ...(SC ? ["@keyframes fx-scroll {", "  0%, {{ (pct_per_item * 0.2) | round(2) }}% { transform: translateY(0); }", "  {{ (pct_per_item * 0.9) | round(2) }}%, 100% { transform: translateY(var(--sc)); }", "}"] : []),
      "</style>",
      "<div class=\"fx-wrap\">", "  {% if people | length == 0 %}<div style=\"font-size:18px;\">Nothing loaded yet</div>{% endif %}",
      "  {% for person in people %}",
      "  {% if person is mapping %}",
      ...roles.flatMap(part).map(x => x.replace(/^      /, "    ")),
      "    {% set dl = ((count - loop.index0) * seconds_per_item) % total_duration %}",
      ...(SC ? ["    {% set tot = " + roles.map(r => "(n_" + r + ".l | join(', ') | length)").join(" + ") + " %}",
        "    {% set ovf = [((tot / " + CPL + ") | round(0, 'ceil')) * 24 + " + roles.length * 4 + " - " + (H - 60) + ", 0] | max %}"] : []),
      "  <div class=\"fx-item\" style=\"animation-delay: -{{ dl }}s;\">",
      ...(SC ? ["  <div{% if ovf > 0 %} style=\"--sc: -{{ ovf }}px; animation: fx-scroll {{ total_duration }}s linear infinite; animation-delay: -{{ dl }}s;\"{% endif %}>"] : []),
      ...roles.map(r => out[r].replace(/^      /, "    ")),
      ...(SC ? ["  </div>"] : []),
      "  </div>", "  {% endif %}", "  {% endfor %}", "</div>");
    return "type: custom:html-template-card\ntitle: " + JSON.stringify((c.emoji ? c.emoji + " " : "") + c.title) + "\nignore_line_breaks: true\ncontent: |\n" + L.map(x => "  " + x).join("\n") + "\n";
  }
  const fb = ((c.emoji ? c.emoji + " " : "") + c.title.toUpperCase() + (c.emoji ? " " + c.emoji : "")).trim();
  L.push("{% set raw = (state_attr('" + jq(c.sensor) + "', 'content') or '') | trim %}",
    "{% set lines = raw.split('\\n') %}",
    "{% if raw.startswith('#') %}", "  {% set title = lines[0] | replace('#', '') | trim %}", "  {% set fact = lines[1:] | join(' ') | trim %}",
    "{% else %}", "  {% set title = '" + jq(fb) + "' %}", "  {% set fact = raw %}", "{% endif %}",
    "{% set len = fact | length %}",
    ...(c.scroll ? ["{% set fsize = 17 %}", "{% set overflow = [((len / " + Math.max(10, +c.cpl || 40) + ") | round(0, 'ceil')) * 22 - 106, 0] | max %}"] : [
    "{% if len > 260 %}", "  {% set fsize = 13 %}", "{% elif len > 220 %}", "  {% set fsize = 15 %}", "{% elif len > 160 %}", "  {% set fsize = 17 %}",
    "{% elif len > 100 %}", "  {% set fsize = 20 %}", "{% else %}", "  {% set fsize = 23 %}", "{% endif %}"]),
    "<style>", ...GLASS.map(x => "  " + x), "  height: 170px !important;", "  overflow: hidden !important;", "}",
    ".card-title { font-size: 25px; font-weight: 600; padding: 14px 16px 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
    ".content-wrap { height: 106px; overflow: hidden; padding: 4px 16px 0; box-sizing: border-box; display: flex; align-items: flex-start; }",
    ".content-text { font-size: {{ fsize }}px; line-height: 1.3; width: 100%;" + (c.scroll ? " {% if overflow > 0 %}--sc: -{{ overflow }}px; animation: txt-scroll {{ [(len / 8) | round(0, 'ceil'), 8] | max }}s linear infinite;{% endif %}" : "") + " }",
    ...(c.scroll ? ["@keyframes txt-scroll {", "  0%, 10% { transform: translateY(0); }", "  90%, 100% { transform: translateY(var(--sc)); }", "}"] : []),
    "</style>",
    "<div class=\"card-title\">{{ title }}</div>",
    "<div class=\"content-wrap\">", "  <div class=\"content-text\">{{ fact }}</div>", "</div>");
  return "type: custom:html-template-card\nignore_line_breaks: true\ncontent: |\n" + L.map(x => "  " + x).join("\n") + "\n";
}
function stackYaml(list) {
  return "type: vertical-stack\ncards:\n" + list.map(y => y.trimEnd().split("\n").map((l, i) => (i ? "    " : "  - ") + l).join("\n")).join("\n") + "\n";
}
function dashCard(n) {
  E.card = Object.assign(defaultCard(E), E.card || {});
  const c = E.card, prev = el("textarea", {class: "code", readonly: true, spellcheck: "false", style: "min-height:150px"}), msg = el("p", {class: "msg"});
  const upd = () => { prev.value = cardYaml(E); };
  const inp = (label, k, ph, help) => { const i = el("input", {value: c[k] || "", placeholder: ph || "", autocomplete: "off", spellcheck: "false"}); i.oninput = () => { c[k] = i.value.trim() === i.value ? i.value : i.value; upd(); markDirty(); }; return [el("label", {class: "l"}, label), i, help ? el("p", {class: "help"}, help) : null]; };
  const kind = el("select", {style: "max-width:320px"}, el("option", {value: "text"}, "Text card (one fact, title on top)"), el("option", {value: "list"}, "Rotating list (fades through a list)"),);
  kind.value = c.kind; kind.onchange = () => { c.kind = kind.value; drawOpts(); upd(); markDirty(); };
  const opts = el("div", {});
  const scrollOpts = () => {
    const w = el("div", {}), ck = el("input", {type: "checkbox", checked: !!c.scroll});
    ck.onchange = () => { c.scroll = ck.checked; drawOpts(); upd(); markDirty(); };
    w.append(el("label", {class: "check", style: "margin-top:10px"}, ck, el("span", {}, "Scroll when it doesn't fit the box", el("small", {}, " " + (c.kind === "list" ? "an item taller than the card scrolls while it is showing" : "long text scrolls up and down")))));
    if (c.scroll) {
      const i = el("input", {type: "number", min: 10, value: c.cpl || "", placeholder: "40", style: "max-width:140px"}); i.oninput = () => { c.cpl = i.value === "" ? "" : +i.value; upd(); markDirty(); };
      w.append(el("label", {class: "l"}, "Characters that fit on one line"), i, el("p", {class: "help"}, "Used to guess whether the text is taller than the card. Lower it if long text still gets cut off without scrolling, raise it if short text scrolls when it doesn't need to."));
    }
    return w;
  };
  const drawOpts = () => { opts.replaceChildren(); add(opts, inp("Sensor that reads the file", "sensor", "sensor.read_my_fact", "The file_reader sensor for this fact's file. It has to expose the text as a content attribute."),
    inp(c.kind === "list" ? "Card title" : "Fallback title", "title", "Random Fact", c.kind === "list" ? null : "Used when the file does not start with a # title line."), inp("Emoji", "emoji", "🎱"),
    c.kind === "list" ? inp("List name in the JSON", "key", "birthdays", "The key that holds the list, for example birthdays.") : null,
    c.kind === "list" ? listOpts() : null, scrollOpts()); };
  const listOpts = () => {
    if (!Array.isArray(c.show)) c.show = defaultShow(E);
    const box = el("div", {}), roleOpts = [["title", "Title (bold)"], ["text", "Text"], ["small", "Small, dim"], ["hide", "Don't show"]];
    box.append(el("label", {class: "l"}, "What to show for each item"));
    c.show.forEach((x, i) => {
      const k = el("input", {value: x.key, placeholder: "field name", autocomplete: "off", spellcheck: "false", style: "flex:1 1 120px;min-width:0"});
      const r = el("select", {style: "flex:0 0 auto;width:auto"}, roleOpts.map(([v, t]) => el("option", {value: v}, t))); r.value = x.as || "text";
      k.oninput = () => { x.key = k.value.trim(); upd(); markDirty(); }; r.onchange = () => { x.as = r.value; upd(); markDirty(); };
      const rm = el("button", {class: "btn danger sm"}, "Remove"); confirmTap(rm, "Tap again", () => { c.show.splice(i, 1); drawOpts(); upd(); markDirty(); });
      box.append(el("div", {class: "inline", style: "flex-wrap:wrap;gap:6px;margin-bottom:8px"}, k, r, rm));
    });
    const names = isAsAuto(E) && E.style === "json" ? fieldList(E).map(f => f.key).join(", ") : "";
    box.append(el("div", {class: "row"}, el("button", {class: "btn sm", onclick: () => { c.show.push({key: "", as: "text"}); drawOpts(); }}, "Add a field"),
      el("button", {class: "btn sm", onclick: () => { c.show = defaultShow(E); drawOpts(); upd(); markDirty(); }}, "Reset from this fact's fields")),
      el("p", {class: "help"}, "Type the field names from your items" + (names ? " (this fact has: " + names + ")" : "") + ". Fields with the same style are joined on one line."));
    const nm = (label, k, ph) => { const i = el("input", {type: "number", min: 1, value: c[k] || "", placeholder: ph, style: "max-width:140px"}); i.oninput = () => { c[k] = i.value === "" ? "" : +i.value; upd(); markDirty(); }; return [el("label", {class: "l"}, label), i]; };
    add(box, nm("Seconds each item stays up", "secs", "8"), nm("Card height (px)", "height", "140"), el("p", {class: "help"}, "Make the card taller if long text is cut off, or turn on scrolling below."));
    return box;
  };
  drawOpts(); upd();
  const toCards = el("button", {class: "btn", title: "Open the Cards tab with this fact's sensor and fields filled in", onclick: () => {
    const fl = isAsAuto(E) && E.style === "json" ? fieldList(E) : [];
    sendToCards({kind: "fact", id: cur.id || "", name: E.name || "Fact", sensor: c.sensor, toggle: c.toggle || "",
      shape: fl.length ? "Its content attribute holds JSON written by the \"" + (E.name || "Fact") + "\" fact: {\"" + listKeyOf(E) + "\": [ {" + fl.map(f => JSON.stringify(f.key) + ": ...").join(", ") + "}, ... ]}, a list of items. Field meanings: " + fl.map(f => f.key + " = " + (f.hint || "") + " (" + f.type + ")").join("; ") + ". Strip ```json and ``` then parse with from_json(default={})."
        : "Its content attribute holds the text of the \"" + (E.name || "Fact") + "\" fact" + (c.kind === "text" ? ", maybe with a first line starting with # that is its title" : "") + "."});
  }}, "Design a custom card in Cards");
  const copy = el("button", {class: "btn primary", onclick: async () => { const ok = await copyText(prev.value); msg.className = "msg " + (ok ? "ok" : "warn"); msg.textContent = ok ? "Copied. In your dashboard, add a Manual card and paste." : "Your browser blocked copying. Tap the box above, select all, and copy."; if (!ok) { prev.removeAttribute("readonly"); prev.focus(); prev.select(); } }}, "Copy dashboard card");
  return card(n, "Dashboard card", "Makes the glass-style card for this fact. Paste it into a Manual card on your dashboard.", el("label", {class: "l"}, "Style"), kind, el("label", {class: "l"}, "Show / hide switch (optional)"), picker(["input_boolean"], false, () => c.toggle ? [c.toggle] : [], a => { c.toggle = a[0] || ""; upd(); markDirty(); }), el("p", {class: "help"}, "Wraps the card so it only shows while this input_boolean is on, like your News and Music cards. Make it first under Settings > Devices & services > Helpers > Toggle."), opts, el("label", {class: "l"}, "Card YAML"), prev, el("div", {class: "row", style: "margin-top:10px"}, copy, toCards), msg);
}
async function copyCards(list, say2) {
  const ys = list.map(it => cardYaml(Object.assign({}, it.state || {}, {name: (it.state && it.state.name) || it.name})));
  const ok = await copyText(ys.length === 1 ? ys[0] : stackYaml(ys));
  say2(ok ? (ys.length === 1 ? "Card copied." : ys.length + " cards copied as one stack.") + " Paste into a Manual card." : "Your browser blocked copying. Open a fact and use Copy dashboard card.", ok ? "ok" : "warn");
}

/* ---------- editor ---------- */
const changed = () => { gen(); markDirty(); };
let MATCH = null;  /* the "also change the entity ID" box of the open editor */
const add = (parent, ...kids) => { kids.flat(Infinity).forEach(x => { if (x != null && x !== false) parent.append(x); }); return parent; };
const rawMode = () => E && E.raw != null;

function tf(label, key, o) {
  o = o || {};
  const i = el(o.area ? "textarea" : "input", {value: E[key] ?? "", placeholder: o.ph || "", type: o.num ? "number" : null, class: o.cls || null, style: o.style || null, min: o.min != null ? o.min : null, step: o.step || null});
  i.oninput = () => { E[key] = o.num ? (i.value === "" ? "" : +i.value) : i.value; if (o.after) o.after(); changed(); };
  return [el("label", {class: "l"}, label), i, o.help ? el("p", {class: "help"}, o.help) : null];
}
function cb(label, key, o) {
  o = o || {};
  const i = el("input", {type: "checkbox", checked: !!E[key]});
  i.onchange = () => { E[key] = i.checked; changed(); if (o.redraw) drawForm(); };
  return [el("label", {class: "check"}, i, el("span", {}, label, o.sub ? el("small", {}, " " + o.sub) : null)), o.help ? el("p", {class: "help"}, o.help) : null];
}
function sel(label, key, opts, o) {
  o = o || {};
  const s = el("select", {style: o.style || null}, opts.map(([v, t]) => el("option", {value: v}, t)));
  s.value = E[key]; s.onchange = () => { E[key] = s.value; changed(); if (o.redraw) drawForm(); };
  return [el("label", {class: "l"}, label), s, o.help ? el("p", {class: "help"}, o.help) : null];
}
const card = (n, title, sub, ...kids) => el("section", {class: "card"}, el("div", {class: "ch"}, el("h2", {}, n ? el("span", {class: "n"}, n) : null, title), sub ? el("p", {}, sub) : null), kids);

function drawForm() {
  const f = $("#form"); f.replaceChildren(); FORMCTX = null;
  const raw = rawMode();
  /* 1. name */
  const c1 = card(1, "Name");
  const nm = tf(viaAuto(E) ? "Automation name" : "Script name", "name", {after: () => { if (FORMCTX) FORMCTX.setAlias(E.name); else if (raw) E.raw = setAlias(E.raw, E.name); }});
  MATCH = matchIdBox();
  add(c1, nm, el("p", {class: "help", id: "idhelp"}), MATCH.row);
  if (cur.isNew && !raw && !isAutoOnly(E)) {
    const chips = el("div", {class: "chips"});
    Object.entries(PRE).forEach(([k, p]) => chips.append(el("button", {class: "chip", onclick: () => applyPreset(p)}, k)));
    add(c1, el("label", {class: "l"}, "Start from"), chips, el("p", {class: "msg warn", id: "pnote"}));
  }
  if (!cur.isNew && !raw && !viaAuto(E) && !ownAuto(E)) {
    const sw = el("button", {class: "btn sm", onclick: () => { E.asAuto = true; changed(); drawForm(); $("#trycard").hidden = false; say("Switched. Push to replace the script and its schedule automation with one automation.", "ok"); }}, "Switch to a single automation");
    add(c1, el("p", {class: "help"}, "This one is still a script plus a separate schedule automation."), el("div", {class: "row", style: "margin-top:6px"}, sw));
  }
  if (isAutoOnly(E) || raw) {
    /* made outside the add-on (imported "exactly as written" before converting existed): offer the normal form */
    const go = el("button", {class: "btn primary sm", style: "margin-top:10px"}, "Convert to the normal form");
    confirmTap(go, "Tap again to convert", () => convertExisting(go));
    add(c1, el("div", {class: "note", style: "margin-top:12px"}, el("div", {},
      el("b", {}, "Want the normal form instead? "),
      "This is your own " + (isAutoOnly(E) ? "automation" : "script") + ", kept exactly as written. Converting reads it into the same form as a fact made here: " +
      "the instructions, format and rules, random picks, the file, and the schedule. Your AI Task splits the prompt for you. Anything that doesn't fit is listed, and you can go back until you push."), go));
  }
  f.append(c1);
  if (isAutoOnly(E)) { const k = autoOnlyCard(2); k.forEach(x => f.append(x)); f.append(dashCard(6)); gen(); return; }
  if (raw) {
    formCards(2, "raw", true).forEach(x => f.append(x));
    f.append(autoCard(4));
    f.append(dashCard(5));
    gen();
    return;
  }

  /* 2. what it is about */
  const c2 = card(2, "What it's about", "Everything here is optional except the instructions.");
  const U = usable();
  add(c2, el("label", {class: "l"}, "Data to include (optional)"));
  const g = el("div", {class: "pickgrid"});
  U.forEach(s => { const i = el("input", {type: "checkbox", checked: (E.src || []).includes(s.id)}); i.onchange = () => { E.src = i.checked ? [...E.src, s.id] : E.src.filter(x => x !== s.id); changed(); }; g.append(el("label", {class: "pick", title: s.label}, i, el("span", {}, s.label))); });
  if (!U.length) g.append(el("p", {class: "dim small"}, "No data sources yet. Add some in Announcements > Settings, or use Helper > Add something to talk about."));
  add(c2, g, el("p", {class: "help"}, "Shared with Announcements. Ticked ones are given to the AI as extra context."));
  add(c2, tf("What should it say?", "task", {area: 1, cls: "tall", ph: "e.g. Share one real trivia fact about the topic. Keep it weird and specific."}));
  add(c2, el("div", {class: "row", style: "margin-top:8px"}, el("button", {class: "btn sm", onclick: () => { showView("help"); $("#chrome").hidden = true; $("#tabs").hidden = true; HEL.back = true; drawHelper(); }}, "Help me write this")));
  add(c2, el("label", {class: "l"}, "Random lists, so every run is different"));
  const pk = el("div", {});
  (E.picks || []).forEach((p, i) => {
    const n = el("input", {value: p.name, placeholder: "name, e.g. topic"}), it = el("textarea", {value: p.items, placeholder: "One option per line", style: "min-height:92px"});
    n.oninput = () => { p.name = n.value; changed(); }; n.onblur = () => { const c = cleanName(n.value); if (c !== n.value) { n.value = c; p.name = c; changed(); } };
    it.oninput = () => { p.items = it.value; changed(); };
    const rm = el("button", {class: "btn danger sm"}, "Remove"); confirmTap(rm, "Tap again", () => { E.picks.splice(i, 1); changed(); drawForm(); });
    pk.append(el("div", {class: "pickrow"}, n, it, rm));
  });
  add(c2, pk, el("div", {class: "row", style: "margin-top:10px"}, el("button", {class: "btn sm", onclick: () => { E.picks.push({name: ["topic", "angle", "genre", "decade", "style", "era"].find(x => !E.picks.some(p => p.name === x)) || "pick" + (E.picks.length + 1), items: ""}); changed(); drawForm(); }}, "Add a random list")),
    el("p", {class: "help"}, "Each run picks one option from every list, and the AI is told what was picked (for example \"TOPIC FOR THIS RUN: ...\"). Mention a list by name in your instructions if you like. Names use lowercase letters and underscores."));
  add(c2, cb("Add a random number so repeats are less likely", "seed"));
  f.append(c2);

  /* 3. how it reads */
  const c3 = card(3, "How it reads");
  add(c3, sel("Format", "style", [["plain", "Just the fact"], ["titled", "A title and the fact"], ["list", "A short list"], ["json", "A data list (JSON), like birthdays"]], {redraw: 1, style: "max-width:260px"}));
  if (E.style === "titled") add(c3, tf("What is the title?", "titleHint", {ph: "e.g. the artist or band name", help: "The AI answers as \"Title ||| fact\" and the script splits it. Use it in the heading as {{ fact_title }}."}));
  if (E.style === "list") add(c3, tf("How many lines", "count", {num: 1, min: 1, step: 1, style: "max-width:120px"}));
  if (E.style === "json") {
    if (!(E.fields || []).length) E.fields = [{key: "name", hint: "short name", type: "text"}];
    add(c3, el("p", {class: "help"}, "The AI answers with JSON. The automation reads it, keeps and sorts the items, and saves {\"" + listKeyOf(E) + "\": [...]} to the file."));
    add(c3, tf("List name in the JSON", "listKey", {ph: "items", style: "max-width:260px", help: "The key that holds the list in the saved file, for example birthdays. Letters, numbers and underscores."}));
    add(c3, tf("How many items", "count", {num: 1, min: 1, step: 1, style: "max-width:120px"}));
    add(c3, el("label", {class: "l"}, "What each item has"));
    const fr = el("div", {});
    E.fields.forEach((f, i) => {
      const k = el("input", {value: f.key, placeholder: "name, e.g. year", style: "flex:1 1 120px;min-width:0"}), h = el("input", {value: f.hint || "", placeholder: "what it holds, e.g. birth year", style: "flex:2 1 160px;min-width:0"});
      const t = el("select", {style: "flex:0 0 auto;width:auto"}, [["text", "Text"], ["number", "Number"], ["yesno", "Yes / no"]].map(([v, x]) => el("option", {value: v}, x)));
      t.value = f.type || "text";
      k.oninput = () => { f.key = k.value; changed(); }; k.onblur = () => { const c = String(k.value).toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, ""); if (c !== k.value) { k.value = c; f.key = c; changed(); } };
      h.oninput = () => { f.hint = h.value; changed(); }; t.onchange = () => { f.type = t.value; changed(); };
      const rm = el("button", {class: "btn danger sm"}, "Remove"); confirmTap(rm, "Tap again", () => { E.fields.splice(i, 1); changed(); drawForm(); });
      fr.append(el("div", {class: "inline", style: "flex-wrap:wrap;gap:6px;margin-bottom:8px"}, k, h, t, rm));
    });
    add(c3, fr, el("div", {class: "row"}, el("button", {class: "btn sm", onclick: () => { E.fields.push({key: "field" + (E.fields.length + 1), hint: "", type: "text"}); changed(); drawForm(); }}, "Add a field")),
      el("p", {class: "help"}, "Each field is one value per item. Text can hold words, Number is a whole number, Yes / no is true or false. The hint is shown to the AI as the example value."));
    add(c3, tf("Sort by (optional)", "sortBy", {ph: "e.g. year", style: "max-width:260px", help: "A field name, or several separated by commas (the first one wins). Yes / no fields put the yes items first when the order is highest first."}));
    add(c3, sel("Order", "sortDir", [["desc", "Highest or newest first"], ["asc", "Lowest or oldest first"]], {style: "max-width:260px"}));
    add(c3, tf("Only keep items where (optional)", "keepIf", {area: 1, ph: "p.month | int(0) == now().month and p.day | int(0) == now().day", style: "min-height:60px", help: "A Home Assistant template test, without the curly braces. p is one item, so p.year is its year field. Items that fail it are dropped, which catches AI mistakes."}));
    add(c3, cb("Tell the AI today's date", "useDate", {sub: "adds \"Today's date is ...\" to the instructions"}));
  }
  if (E.style !== "json") add(c3, tf(E.style === "list" ? "Max length of each line (characters)" : "Max length (characters)", "len", {num: 1, min: 40, step: 20, style: "max-width:160px"}));
  if (E.style !== "json") add(c3, tf("Heading above it (optional)", "heading", {area: 1, ph: "e.g. ## 🎶 MUSIC Fact About - {{ fact_title }}", style: "min-height:60px", help: "Saved in the file above the fact. You can use {{ fact_title }}" + (pickList(E).length ? ", " + pickList(E).map(p => "{{ " + p.name + " }}").join(", ") : "") + " and any Home Assistant template."}));
  add(c3, sel("Language", "swear", [["none", "Clean"], ["mild", "Light (PG-13)"], ["rated", "Profanity as needed"]], {style: "max-width:260px"}));
  add(c3, el("label", {class: "l"}, "Rules"));
  add(c3, cb("Only real, verifiable facts", "real", {sub: "if unsure it picks a different one"}));
  add(c3, cb("Go obscure, skip the famous ones", "obscure", {redraw: 1}));
  if (E.obscure) add(c3, tf("Famous ones to skip (optional)", "skip", {ph: "e.g. honey never spoils, octopus hearts", style: "margin-bottom:4px"}));
  add(c3, cb("Keep our household, pets and jobs out of it", "noPeople"));
  if (E.style !== "json") add(c3, cb("Don't repeat the last fact", "avoidLast", {redraw: 1, sub: "the AI is shown the previous one"}));
  if (E.avoidLast && E.style !== "json") {
    const lr = lastRef(E);
    add(c3, el("label", {class: "l"}, "Where the last fact is read from"), picker(null, false, () => E.lastEntity ? [E.lastEntity] : [], a => { E.lastEntity = a[0] || ""; changed(); }),
      el("p", {class: "help"}, lr.entity ? "Reading " + lr.entity + (lr.attr ? " attribute " + lr.attr : " state") + (E.lastEntity ? "." : " (the default from Settings).") : "Nothing set. Pick the sensor that reads your fact file, or set a default in Settings."));
    if (E.lastEntity) add(c3, tf("Attribute (blank = state)", "lastAttr", {style: "max-width:260px"}));
  }
  add(c3, tf("Extra rules (optional)", "extra", {area: 1, ph: "Anything else the AI must follow.", style: "min-height:70px"}));
  f.append(c3);

  /* 4. where it goes */
  const c4 = card(4, "Where it goes", "Saved over MQTT. A dashboard card (for example file_reader) shows the file.");
  add(c4, tf("File name", "file", {ph: fslug(E.name) + ".txt", help: "Added to the topic prefix from Settings. Type a full topic (with a slash) to override."}));
  add(c4, el("p", {class: "help"}, el("span", {}, "Publishes to "), el("code", {id: "topicshow"}, topicOf(E))));
  const adv = el("details", {style: "margin-top:12px"}, el("summary", {}, "Use a different AI Task for this one"));
  adv.append(picker(["ai_task"], false, () => E.ai ? [E.ai] : [], a => { E.ai = a[0] || ""; changed(); }), el("p", {class: "help"}, "Blank uses " + (S.ai_task_entity || "the AI Task from Announcements") + "."));
  add(c4, adv);
  f.append(c4);

  /* 5. schedule */
  const A = E.auto, asA = isAsAuto(E), c5 = card(5, asA ? "When it runs" : "Run it automatically", asA ? "This fact is one automation. Without a schedule it has no triggers, so run it by hand with Run now." : "Optional. Makes a Home Assistant automation that runs this script.");
  const on = el("input", {type: "checkbox", checked: !!A.on}); on.onchange = () => { A.on = on.checked; changed(); drawForm(); };
  add(c5, el("label", {class: "check"}, on, el("span", {}, "Run on a schedule")));
  if (A.on) {
    const ev = el("input", {type: "number", min: 0, step: 1, value: A.every, style: "width:90px"}); ev.oninput = () => { A.every = ev.value === "" ? "" : +ev.value; changed(); };
    const un = el("select", {style: "width:auto"}, el("option", {value: "minutes"}, "minutes"), el("option", {value: "hours"}, "hours")); un.value = A.unit; un.onchange = () => { A.unit = un.value; changed(); };
    add(c5, el("label", {class: "l"}, "Every"), el("div", {class: "inline"}, ev, un), el("p", {class: "help"}, "0 turns the repeat off. Minutes up to 59, hours up to 23."));
    const tm = el("input", {type: "time", value: A.at || "", style: "max-width:160px"}); tm.onchange = () => { A.at = tm.value; changed(); };
    const clr = el("button", {class: "btn sm", onclick: () => { A.at = ""; tm.value = ""; changed(); }}, "Clear");
    add(c5, el("label", {class: "l"}, "And at this time every day (optional)"), el("div", {class: "inline"}, tm, clr));
    add(c5, el("label", {class: "l"}, "And when this entity changes (optional)"), picker(null, false, () => A.watch ? [A.watch] : [], a => { A.watch = a[0] || ""; changed(); drawForm(); }));
    if (A.watch) {
      const at = el("input", {value: A.watchAttr, placeholder: "attribute (blank = state)", style: "max-width:240px"}); at.oninput = () => { A.watchAttr = at.value.trim(); changed(); };
      const fr = el("input", {type: "number", min: 0, step: 1, value: A.watchFor, style: "width:90px"}); fr.oninput = () => { A.watchFor = fr.value === "" ? 0 : +fr.value; changed(); };
      add(c5, el("div", {class: "inline", style: "margin-top:8px"}, at, el("span", {class: "dim small"}, "after it has held for"), fr, el("span", {class: "dim small"}, "seconds")));
    }
    add(c5, el("label", {class: "l"}, "Only when someone is home (optional)"), picker(null, true, () => A.home || [], a => { A.home = a; changed(); }),
      el("p", {class: "help"}, "Runs only if any of these is on or home. A zone counts when it has someone in it."));
    if ((F.home_entities || []).length && !(A.home || []).length) add(c5, el("button", {class: "btn sm", style: "margin-top:6px", onclick: () => { A.home = [...F.home_entities]; changed(); drawForm(); }}, "Use my default presence list"));
  }
  f.append(c5);
  if (!asA) f.append(autoCard(6));
  f.append(dashCard(asA ? 6 : 7));
  gen();
}

function applyPreset(p) {
  const have = usable(), keep = {name: E.name};
  const src = (p.types || []).length ? have.filter(x => p.types.includes(x.type)).map(x => x.id) : [];
  const miss = (p.types || []).filter(t => !have.some(x => x.type === t));
  E = full(Object.assign({}, blankState(), p, {src, picks: clone(p.picks || [])}));
  if (!p.name) E.name = keep.name;
  drawForm(); markDirty();
  const n = $("#pnote"); if (n) n.textContent = miss.length ? "No data source set up for: " + miss.map(t => TYPES[t]).join(", ") + " (add it in Announcements > Settings)." : "";
}

/* ---------- editor: open / dirty / save ---------- */
function markDirty() { dirty = true; paintState(); }
function paintState() {
  const p = $("#estate");
  if (dirty) { p.className = "pill acc"; p.textContent = cur.pushed ? "Changed since last push" : "Unsaved changes"; }
  else if (cur.pushed) { p.className = "pill ok"; p.textContent = "In Home Assistant"; }
  else if (cur.saved) { p.className = "pill warn"; p.textContent = "Saved draft"; }
  else { p.className = "pill plain"; p.textContent = "New"; }
  if (!E) return;
  $("#etitle").textContent = (E.name || "").trim() || "New fact";
  const id = cur.id || fslug(E.name), h = $("#idhelp");
  if (h && isAsAuto(E)) h.textContent = cur.id ? "Automation id: " + cur.id + ". It stays the same if you rename this. Pushing updates that automation in Home Assistant." : "It will be created as one automation (id " + id + (takenIds().has(id) ? ", a number is added because that name is taken" : "") + ").";
  else if (h && isAutoOnly(E)) h.textContent = cur.id ? "Automation id: " + cur.id + ". Pushing updates that automation in Home Assistant." : "";
  else if (h) h.textContent = cur.id ? "Script id: script." + cur.id + ". It stays the same if you rename this, so automations that call it keep working."
    : "It will be created as script." + id + (takenIds().has(id) ? " (a number is added because that name is taken)." : ".");
}
function openEditor(state, c, note) {
  cur = Object.assign({id: null, isNew: true, pushed: false, saved: false}, c);
  E = full(state);
  $("#msg").textContent = ""; $("#tres").replaceChildren();
  const n = $("#enote"); n.hidden = !note; if (note) n.firstElementChild.textContent = note;
  n.querySelectorAll(".origbtn").forEach(b => b.remove());
  if (note && E.original && !E.autoOnly && E.raw == null) {  /* converted from an import: one tap goes back to the original */
    const ob = el("button", {class: "btn sm origbtn", style: "margin-top:8px"}, "Use my original instead");
    confirmTap(ob, "Tap again: keep it exactly as written", () => {
      const auto = looksAuto(E.original), keep = {name: E.name, original: E.original};
      E = full(Object.assign(blankState(), keep, auto ? {autoOnly: true, autoRaw: E.original, autoId: cur.id} : {raw: E.original, autoRaw: E.originalAuto || ""}));
      $("#trycard").hidden = true; $("#ymldet").hidden = true;
      n.firstElementChild.textContent = "Switched back to your original, kept exactly as written."; ob.remove(); drawForm(); markDirty();
    });
    n.append(ob);
  }
  $("#trycard").hidden = rawMode() || isAutoOnly(E); $("#ymldet").hidden = rawMode() || isAutoOnly(E); $("#autodet").hidden = isAutoOnly(E) || isAsAuto(E) || (rawMode() && !ownAuto(E));
  drawForm(); dirty = false; paintState(); showView("edit");
}
function openNew(over) { openEditor(Object.assign(blankState(), over || {}), {isNew: true}); }
function openItem(it) {
  const s = Object.assign(blankState(), it.state || {}, {name: (it.state || {}).name || it.name});
  if (!("asAuto" in (it.state || {}))) s.asAuto = false;  /* made before facts became one automation: stays a script until switched */
  openEditor(s, {id: it.id, isNew: false, pushed: !!(it.pushed_at || it.in_ha), saved: true});
}
function say(text, cls) { const m = $("#msg"); m.className = "msg " + (cls || ""); m.textContent = text; }
function problems() {
  if (isAutoOnly(E)) return ownAuto(E) ? "" : "Paste the automation first.";
  if (rawMode()) return "";
  if (!(E.task || "").trim()) return "Say what the fact should be about first.";
  if (E.auto.on && !hasTrigger(E)) return "The schedule needs a repeat time or an entity to watch.";
  if (!/^[A-Za-z0-9_\-./]+$/.test(topicOf(E))) return "The file name can only use letters, numbers, underscores, dashes, dots and slashes.";
  return "";
}
async function persist(push) {
  if (push) { const p = problems(); if (p) { say(p, "warn"); return; } }
  if (!isAutoOnly(E) && E.raw == null && !String(E.file || "").trim()) E.file = fileOf(E);  /* fixed from now on, so a rename keeps the same file and sensor */
  const s = clone(E);
  if (!cur.id) cur.id = uniqueId(fslug(s.name));
  if (viaAuto(s)) s.autoId = cur.id;
  const btns = [$("#save"), $("#push")]; btns.forEach(b => b.disabled = true);
  say(push ? "Pushing to Home Assistant..." : "Saving...");
  let r;
  if (push) r = await fapi("push", pushBody(s, cur.id, {new: cur.isNew && !cur.pushed, match_id: !!(MATCH && MATCH.checked())}));
  else r = await fapi("library/save", {id: cur.id, name: s.name, state: s, match_id: !!(MATCH && MATCH.checked())});
  btns.forEach(b => b.disabled = false);
  if (!r.ok) { say(r.detail || r.error || "That failed.", "bad"); if (!cur.saved && !cur.pushed && !cur.fixedId) cur.id = null; paintState(); return; }
  cur.saved = true; cur.isNew = false; if (push) cur.pushed = true; dirty = false; paintState(); notifyChanged("facts");
  const am = push ? (isAsAuto(s) ? (s.auto.on ? " It runs " + autoSummary(s.auto) + "." : " It has no schedule, so use Run now.") + (r.cleaned ? " The old script and schedule automation were removed." : "") : ownAuto(s) ? " Your automation is pushed exactly as written." : s.raw == null && s.auto.on ? " The schedule (" + autoSummary(s.auto) + ") is on." : r.auto === "removed" ? " The old schedule was removed." : "") : "";
  say(push ? "Done. " + (viaAuto(s) ? "The automation" : "script." + cur.id) + " is up to date in Home Assistant." + am : "Saved. Home Assistant still has the previous version." + (cur.pushed ? " Push to update it." : ""), "ok");
  if (r.id_note) say($("#msg").textContent + " " + r.id_note, "ok");
  if (r.name_warning) say($("#msg").textContent + " " + r.name_warning, "bad");
}
$("#save").onclick = () => persist(false);
$("#push").onclick = () => persist(true);
let armedBack = null;
$("#back").onclick = () => {
  const b = $("#back");
  if (dirty && !armedBack) {
    b.textContent = "Leave without saving?"; b.classList.add("danger");
    armedBack = setTimeout(() => { armedBack = null; b.textContent = "← All facts"; b.classList.remove("danger") }, 3500); return;
  }
  clearTimeout(armedBack); armedBack = null; b.textContent = "← All facts"; b.classList.remove("danger");
  dirty = false; showView("lib"); loadLib();
};
$("#newfact").onclick = () => openNew();

function gen() {
  if (!E) return;
  $("#out").textContent = isAsAuto(E) ? makeAutomation(E, cur.id || fslug(E.name)) : makeYaml(E);
  const ys = $("#ymldet summary"); if (ys) ys.textContent = isAsAuto(E) ? "Show automation YAML" : "Show script YAML";
  $("#autodet").hidden = isAutoOnly(E) || isAsAuto(E) || (rawMode() && !ownAuto(E));
  const a = makeAuto(E, cur.id || fslug(E.name));
  $("#autoout").textContent = a || (rawMode() && !ownAuto(E) ? "" : E.auto.on ? "Set a repeat time or an entity to watch to see the schedule." : "No schedule. Turn on \"Run it automatically\" to make one.");
  const t = $("#topicshow"); if (t) t.textContent = topicOf(E);
  paintState();
}
$("#run").onclick = async () => {
  if (!cur.id) { say("Push it to Home Assistant first.", "warn"); return; }
  say("Starting...");
  const r = await fapi("run", {id: cur.id, auto_only: viaAuto(E)}); say(r.ok ? "Started the saved " + (viaAuto(E) ? "automation." : "script.") : (r.detail || r.error), r.ok ? "ok" : "bad");
};
$("#copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("#out").textContent); say("Copied.", "ok"); }
  catch (e) { $("#out").closest("details").open = true; const r = document.createRange(); r.selectNodeContents($("#out")); getSelection().removeAllRanges(); getSelection().addRange(r); say("Selected. Press copy on your device."); }
};

/* ---------- test run ---------- */
const pre = t => el("pre", {}, t == null ? "" : typeof t === "string" ? t : JSON.stringify(t));
function showTest(r) {
  const b = $("#tres"); b.replaceChildren();
  if (r.status === "running") { b.append(el("p", {class: "dim small"}, el("span", {class: "spin"}), "Running. The AI usually answers in a few seconds.")); return; }
  if (r.status === "error") { b.append(el("div", {class: "note bad"}, el("div", {}, el("b", {}, "Test failed"), pre(r.error)))); return; }
  const v = r.values || {};
  if (r.mode !== "data") {
    if (v.fact_items !== undefined) {
      const items = Array.isArray(v.fact_items) ? v.fact_items : [], key = listKeyOf(E || {});
      b.append(el("b", {}, (r.mode === "full" ? "What it published" : "What it would publish") + " (" + items.length + " item" + (items.length === 1 ? "" : "s") + ")"),
        pre(items.length ? JSON.stringify({[key]: items}, null, 1) : "(nothing: no items could be read, or none passed the filter. Check the raw answer below.)"));
    } else
    b.append(el("b", {}, r.mode === "full" ? "What it published" : "What it would publish"), pre(v.fact_out != null && v.fact_out !== "" ? v.fact_out : "(nothing: the AI answer could not be read)"));
    if (r.ai_raw != null && String(r.ai_raw) !== String(v.fact_text)) b.append(el("details", {style: "margin-top:10px"}, el("summary", {}, "What the AI answered, raw"), pre(r.ai_raw)));
  }
  const d = el("details", {open: r.mode === "data", style: "margin-top:10px"}, el("summary", {}, "What it picked and what the AI saw"));
  Object.entries(v).filter(([k]) => !k.startsWith("fact_")).forEach(([k, x]) => d.append(el("p", {class: "dim small", style: "margin-top:8px"}, k.replace("src_", "")), pre(x)));
  b.append(d);
}
async function runTest(mode) {
  const p = problems(); if (p) { $("#tres").textContent = p; return; }
  const btns = ["t-data", "t-text", "t-full"].map(i => $("#" + i)); btns.forEach(x => x.disabled = true);
  try {
    const r = await fapi("test", {mode, yaml: makeYaml(E)});
    if (r.ok === false || r.error) { $("#tres").textContent = r.error; return; }
    for (let i = 0; i < 200; i++) { const t = await (await fetch("./api/facts/test")).json(); showTest(t); if (t.status !== "running") break; await sleep(2500); }
  } catch (e) { $("#tres").textContent = "Failed: " + e; } finally { btns.forEach(x => x.disabled = false); }
}
$("#t-data").onclick = () => runTest("data"); $("#t-text").onclick = () => runTest("text"); $("#t-full").onclick = () => runTest("full");

/* ---------- helper ---------- */
function drawHelper() {
  const v = $("#v-help"); v.replaceChildren();
  const hcard = (t, sub) => { const c = el("div", {class: "card"}, el("div", {class: "ch"}, el("h2", {}, t), sub ? el("p", {}, sub) : null)); v.append(c); return c; };
  if (HEL.back) v.append(el("div", {class: "row"}, el("button", {class: "btn quiet sm", onclick: () => { HEL.back = false; $("#tabs").hidden = false; showView("edit"); }}, "← Back to the editor")));
  const a = hcard("Write it for me", "Say what kind of fact you want. The AI writes the instructions, suggests random lists to keep it varied, and picks a format.");
  const idea = el("textarea", {value: HEL.idea, placeholder: "e.g. A weird fact about a random national park every hour, short and funny."});
  idea.oninput = () => { HEL.idea = idea.value };
  const wb = el("button", {class: "btn primary", style: "margin-top:10px"}, "Write it"), wr = el("div", {style: "margin-top:12px"});
  wb.onclick = async () => {
    if (!HEL.idea.trim()) { wr.textContent = "Type what you want first."; return; }
    wr.textContent = "Asking your AI Task..."; wb.disabled = true;
    const r = await fapi("helper", {idea: HEL.idea, ai: aiName(), sources: usable().map(x => ({id: x.id, label: x.label + " (" + x.type + ")"}))});
    wb.disabled = false;
    if (!r.ok) { wr.textContent = r.error; return; }
    wr.replaceChildren();
    const nm = el("input", {value: r.name || ""}), tk = el("textarea", {value: r.task});
    const fmt = {plain: "just the fact", titled: "a title and the fact", list: "a short list", json: "a JSON data list (" + (r.fields || []).map(f => f.key).join(", ") + ")"}[r.style];
    const ub = el("button", {class: "btn good", onclick: () => {
      const s = {name: nm.value || "My fact", task: tk.value, picks: r.picks, style: r.style, titleHint: r.title_hint, heading: r.heading, file: r.file, len: r.length, src: r.sources};
      if (r.style === "json") Object.assign(s, {listKey: r.list_key || "items", fields: r.fields || [], count: r.count || 10, sortBy: r.sort_by || "", sortDir: r.sort_dir || "desc", useDate: !!r.uses_date, avoidLast: false});
      if (HEL.back && E) { Object.assign(E, s); HEL.back = false; $("#tabs").hidden = false; drawForm(); markDirty(); showView("edit"); }
      else openNew(s);
    }}, HEL.back ? "Use in this fact" : "Start a fact with this");
    wr.append(el("label", {class: "l"}, "Name"), nm, el("label", {class: "l"}, "Instructions (edit if you like)"), tk,
      el("p", {class: "help"}, "Format: " + fmt + ". " + (r.picks.length ? "Random lists: " + r.picks.map(p => p.name + " (" + itemsOf(p).length + ")").join(", ") + "." : "No random lists.") + (r.file ? " File: " + r.file + "." : "")),
      el("div", {class: "row", style: "margin-top:10px"}, ub));
  };
  a.append(idea, wb, wr, el("p", {class: "help"}, "Using AI Task: " + (aiName() || "none set yet")));

  const b = hcard("Add something to talk about", "Pick an entity and say what you want from it. The AI finds the right attribute and adds it as a data source, shared with Announcements.");
  b.append(el("label", {class: "l"}, "Entity"), picker(null, false, () => HEL.entity ? [HEL.entity] : [], x => { HEL.entity = x[0] || "" }), el("label", {class: "l"}, "What do you want from it?"));
  const gt = el("textarea", {placeholder: "e.g. The city each person is in right now", value: HEL.goal, style: "min-height:70px"}); gt.oninput = () => { HEL.goal = gt.value };
  const tb = el("button", {class: "btn primary", style: "margin-top:10px"}, "Check it"), res = el("div", {style: "margin-top:12px"});
  tb.onclick = async () => {
    if (!HEL.entity || !HEL.goal) { res.textContent = "Pick an entity and say what you want."; return; }
    res.textContent = "Asking your AI Task..."; tb.disabled = true;
    const r = await api("ann/helper", {entity: HEL.entity, goal: HEL.goal, ai: aiName()});
    tb.disabled = false;
    if (!r.ok) { res.textContent = r.error; return; }
    res.replaceChildren(el("p", {}, el("b", {}, r.label), r.attribute ? " (attribute: " + r.attribute + ")" : " (whole entity)"), el("p", {class: "dim small"}, r.note), el("p", {class: "dim small"}, "Preview: " + r.preview));
    const ab = el("button", {class: "btn good", style: "margin-top:8px"}, "Add as data source");
    ab.onclick = async () => {
      ab.disabled = true;
      const fresh = await api("ann/options");  /* start from what is saved now, so nothing made in Announcements is lost */
      if (fresh.error) { ab.textContent = fresh.error; return; }
      if (!Array.isArray(fresh.sources)) fresh.sources = migrate(fresh);
      fresh.sources.push(mk(fresh.sources, "entity", {label: r.label, entity: HEL.entity, attribute: r.attribute}));
      const saved = await api("ann/settings", fresh);
      if (saved.error) { ab.textContent = saved.error; return; }
      S = saved; if (!Array.isArray(S.sources)) S.sources = []; ab.textContent = "Added and saved"; if (E) drawForm();
    };
    res.append(ab);
  };
  b.append(gt, tb, res);
}

/* ---------- settings ---------- */
async function saveSettings() {
  const r = await fapi("settings", F);
  if (r.error) { $("#smsg").className = "msg bad"; $("#smsg").textContent = r.error; return false; }
  F = r; setupNote(); drawSettings(); return true;
}
function drawSettings() {
  const v = $("#v-set"); v.replaceChildren();
  const scard = (t, sub) => { const c = el("div", {class: "card"}, el("div", {class: "ch"}, el("h2", {}, t), sub ? el("p", {}, sub) : null)); v.append(c); return c; };
  if (!ENT.length) v.append(el("div", {class: "note warn"}, el("div", {}, "Could not load your entity list from Home Assistant. You can still type entity ids into any field. Check the add-on's Log tab.")));
  const c1 = scard("Where facts are saved", "Every fact publishes to this MQTT topic prefix plus its own file name.");
  const pf = el("input", {value: F.mqtt_prefix || "", placeholder: "file_reader/overwrite/", disabled: !!F.prefix_locked}); pf.oninput = () => { F.mqtt_prefix = pf.value.trim() };
  add(c1, el("label", {class: "l"}, "MQTT topic prefix"), pf, el("p", {class: "help"}, "For example file_reader/overwrite/ makes file_reader/overwrite/random_fact.txt for a fact whose file name is random_fact.txt." + (F.prefix_locked ? " This is set by the Facts file path option in the add-on Configuration tab. Change it there." : " You can also set it in the add-on Configuration tab (Facts file path).")));
  const c2 = scard("Don't repeat the last fact", "Default sensor the AI is shown so it avoids repeating itself. Each fact can use a different one.");
  add(c2, el("label", {class: "l"}, "Sensor that reads your fact file"), picker(null, false, () => F.last_entity ? [F.last_entity] : [], a => { F.last_entity = a[0] || ""; }));
  const la = el("input", {value: F.last_attribute || "", placeholder: "content", style: "max-width:260px"}); la.oninput = () => { F.last_attribute = la.value.trim() };
  add(c2, el("label", {class: "l"}, "Its attribute (blank = state)"), la);
  const c3 = scard("Someone is home", "The default list for \"Only when someone is home\" in a fact's schedule.");
  add(c3, picker(null, true, () => F.home_entities || [], a => { F.home_entities = a; }), el("p", {class: "help"}, "A zone (like zone.home) counts when someone is in it. People and device trackers count when home. Anything else counts when on."));
  const c4 = scard("Defaults");
  const dl = el("input", {type: "number", value: F.default_length ?? 180, style: "max-width:160px"}); dl.oninput = () => { F.default_length = +dl.value };
  const xr = el("textarea", {value: F.extra_rules || "", placeholder: "e.g. Never mention politics.", style: "min-height:80px"}); xr.oninput = () => { F.extra_rules = xr.value };
  add(c4, el("label", {class: "l"}, "Default length (characters)"), dl, el("label", {class: "l"}, "Rules added to every fact"), xr,
    el("p", {class: "help"}, "The AI Task, data sources and entity list are shared with Announcements. Change them in Announcements > Settings. Using AI Task: " + (aiName() || "none set yet") + "."));
  v.append(el("div", {style: "height:60px"}));
}
$("#setsave").onclick = async () => { if (await saveSettings()) { $("#smsg").className = "msg ok"; $("#smsg").textContent = "Settings saved."; } };

/* ---------- start ---------- */
onChanged(() => { if (view === "lib") loadLib(); });  /* another tab renamed or changed something */

/* a rename made in Home Assistant shows up here on its own (the add-on checks every 30 seconds) */
setInterval(() => { if (view === "lib" && !document.hidden && !(document.activeElement && document.activeElement.tagName === "INPUT")) loadLib(); }, 20000);
Promise.all([api("ann/options"), api("facts/options"), api("ann/entities").then(r => Array.isArray(r) ? r : [])]).then(async ([o, f, e]) => {
  if (o.error || f.error) { $("#setupnote").append(el("div", {class: "note bad"}, o.error || f.error)); return; }
  S = o; F = f; ENT = e; if (!Array.isArray(S.sources)) S.sources = migrate(S);
  setupNote(); drawHelper(); drawSettings(); await loadLib(); showView("lib");
});

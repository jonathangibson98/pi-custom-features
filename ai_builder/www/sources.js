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
const usable = () => (S.sources || []).filter(s => {
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


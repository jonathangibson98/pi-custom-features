/* "Save to a file and show it on a card" for announcements.
   Plain text mode: the script publishes what it says over MQTT (like Facts).
   Fields mode: the AI answers in JSON with the fields you set up (for example name, message, detail). One field is
   spoken, all of them are saved, and the card shows each one as its title, its text or its bottom line.
   The script side lives in makeYaml (announcements.js); this file is the editor, the card and the preview. */
(function () {
  if (typeof makeYaml !== "function" || typeof st !== "function" || typeof applyState !== "function" || typeof gen !== "function") return;
  const escH = t => String(t).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const jq = t => String(t).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  const frameDoc = (title, html) => '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;min-height:100%}body{padding:14px;background:linear-gradient(135deg,#1c2b4d,#3b1d5e 55%,#0e3b3d);color:#fff;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}ha-card{display:block;position:relative;border-radius:12px;box-sizing:border-box;overflow:hidden}.t{font-size:20px;padding:14px 16px 0}</style><ha-card>'
    + (title ? '<div class="t">' + escH(title) + "</div>" : "") + html + "</ha-card>";
  const DEFT = {on: false, mode: "text", fields: [], say: "", file: "", sensor: "", title: "", emoji: "\u{1F4E2}", scroll: true, cpl: 40, height: 300};
  const BDAY = [
    {key: "name", hint: "whose birthday it is, just the name", as: "title"},
    {key: "message", hint: "", as: "text"},
    {key: "detail", hint: "how old they are and what they are known for, under 60 characters", as: "small"}];
  let FLD = [];  /* the field rows being edited */
  const nameNow = () => ($("#name").value || "").trim() || "Announcement";

  const txtGet = () => ({on: $("#txt-on").checked, mode: $("#txt-mode").value === "fields" ? "fields" : "text", fields: FLD.map(f => Object.assign({}, f)), say: $("#txt-say").value || "",
    file: $("#txt-file").value.trim(), sensor: $("#txt-sensor").value.trim(), title: $("#txt-title").value.trim(),
    emoji: $("#txt-emoji").value.trim(), scroll: $("#txt-scroll").checked, cpl: +$("#txt-cpl").value || 40, height: +$("#txt-h").value || 300});
  const txtSet = t => {
    t = Object.assign({}, DEFT, t || {});
    $("#txt-on").checked = !!t.on; $("#txt-mode").value = t.mode === "fields" ? "fields" : "text";
    FLD = (Array.isArray(t.fields) ? t.fields : []).map(f => ({key: f.key || "", hint: f.hint || "", as: f.as || "text"}));
    $("#txt-file").value = t.file || ""; $("#txt-sensor").value = t.sensor || ""; $("#txt-title").value = t.title || "";
    $("#txt-emoji").value = t.emoji || ""; $("#txt-scroll").checked = !!t.scroll; $("#txt-cpl").value = t.cpl || 40; $("#txt-h").value = t.height || 300;
    drawFields(t.say);
  };
  const changed = () => { gen(); markDirty(); };

  /* ---------- the field rows ---------- */
  function drawSay(want) {
    const sel = $("#txt-say"), keep = want != null ? want : sel.value, keys = FLD.map(f => fieldKey(f.key)).filter(Boolean);
    sel.replaceChildren(...keys.map(k => el("option", {value: k}, k)));
    if (!keys.length) sel.append(el("option", {value: ""}, "Add a field first"));
    const firstText = FLD.map(f => ({k: fieldKey(f.key), as: f.as})).find(x => x.k && x.as === "text");
    sel.value = keys.includes(keep) ? keep : (firstText ? firstText.k : keys[0] || "");
  }
  function drawFields(want) {
    const box = $("#txt-fields"); box.replaceChildren();
    if (!FLD.length) box.append(el("p", {class: "dim small"}, "No fields yet. Add one, or start from the birthday example."));
    FLD.forEach((f, i) => {
      const k = el("input", {value: f.key, placeholder: "field name, e.g. name", autocomplete: "off", spellcheck: "false", style: "flex:1 1 110px;min-width:0"});
      const h = el("input", {value: f.hint, placeholder: "what the AI writes here", autocomplete: "off", style: "flex:3 1 200px;min-width:0"});
      const r = el("select", {style: "flex:0 0 auto;width:auto"}, TXT_ROLES.map(([v, t]) => el("option", {value: v}, t))); r.value = f.as || "text";
      k.oninput = () => { f.key = k.value; drawSay(); };
      k.onchange = () => { f.key = fieldKey(k.value); k.value = f.key; drawSay(); changed(); };
      h.oninput = () => { f.hint = h.value; };
      r.onchange = () => { f.as = r.value; };
      const rm = el("button", {class: "btn danger sm"}, "Remove");
      confirmTap(rm, "Tap again", () => { FLD.splice(i, 1); drawFields(); changed(); });
      box.append(el("div", {class: "inline", style: "flex-wrap:wrap;gap:6px;margin-bottom:8px"}, k, h, r, rm));
    });
    drawSay(want);
  }
  $("#txt-addf").onclick = () => { FLD.push({key: FLD.length ? "field" + (FLD.length + 1) : "title", hint: "", as: FLD.length ? "text" : "title"}); drawFields(); changed(); };
  $("#txt-bday").onclick = () => {
    FLD = BDAY.map(f => Object.assign({}, f)); drawFields("message");
    if (!$("#txt-title").value.trim()) $("#txt-title").value = "Birthday";
    if (!$("#txt-emoji").value.trim() || $("#txt-emoji").value === DEFT.emoji) $("#txt-emoji").value = "\u{1F382}";
    changed();
  };

  /* ---------- the glass card, same look as the Facts and Cards tabs ---------- */
  const GLASS = H => ["  ha-card {",
    "    background: rgba(255, 255, 255, 0.06) !important;",
    "    backdrop-filter: blur(28px) saturate(200%) !important;",
    "    -webkit-backdrop-filter: blur(28px) saturate(200%) !important;",
    "    border: 1px solid rgba(255, 255, 255, 0.2) !important;",
    "    border-radius: 20px !important;",
    "    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.4), inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;",
    "    color: rgba(255,255,255,0.9);",
    "    height: " + H + "px !important;",
    "    position: relative;",
    "    overflow: hidden !important;",
    "  }"];
  const SIZES = ["{% if len > 600 %}", "  {% set fsize = 13 %}", "{% elif len > 400 %}", "  {% set fsize = 15 %}", "{% elif len > 250 %}", "  {% set fsize = 17 %}",
    "{% elif len > 120 %}", "  {% set fsize = 20 %}", "{% else %}", "  {% set fsize = 23 %}", "{% endif %}"];
  const SCROLL_KF = ["  @keyframes txt-scroll {", "    0%, 10% { transform: translateY(0); }", "    90%, 100% { transform: translateY(var(--sc)); }", "  }"];

  function baseYaml(t, name) {
    const F = annFields({txt: Object.assign({}, t, {on: true})});
    const sensor = jq(txtSensorOf(t, name)), H = Math.max(120, +t.height || 300), CPL = Math.max(10, +t.cpl || 40);
    const fallback = ((t.emoji ? t.emoji + " " : "") + (t.title || name)).trim();
    if (t.mode === "fields" && F) {
      const keysOf = r => F.fields.filter(f => f.as === r).map(f => "'" + f.key + "'").join(", ");
      const hasFoot = !!keysOf("small"), HW = H - 64 - (hasFoot ? 30 : 0);
      const join = (r, sep) => ["{% set n = namespace(l=[]) %}",
        "{% for k in [" + keysOf(r) + "] %}{% set v = (d.get(k) or '') | string | trim %}{% if v %}{% set n.l = n.l + [v] %}{% endif %}{% endfor %}",
        "{% set f_" + r + " = n.l | join('" + sep + "') %}"];
      const L = ["{% set raw = (state_attr('" + sensor + "', 'content') or '') | replace('```json', '') | replace('```', '') | trim %}",
        "{% set d = (raw | from_json(default={})) if raw[:1] == '{' else {} %}",
        "{% set d = d if d is mapping else {} %}",
        ...join("title", ", "), ...join("text", " "), ...join("small", " · "),
        "{% if not d %}{% set f_text = raw %}{% endif %}",  /* an older plain-text file still shows */
        "{% set len = f_text | length %}"];
      if (t.scroll) L.push("{% set fsize = 18 %}", "{% set overflow = [((len / " + CPL + ") | round(0, 'ceil')) * 24 - " + HW + ", 0] | max %}");
      else L.push(...SIZES);
      L.push("<style>", ...GLASS(H),
        "  .card-title { font-size: 25px; font-weight: 600; padding: 14px 16px 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
        "  .content-wrap { height: " + HW + "px; overflow: hidden; padding: 4px 16px 0; box-sizing: border-box; }",
        "  .content-text { font-size: {{ fsize }}px; line-height: 1.3; width: 100%;" + (t.scroll ? " {% if overflow > 0 %}--sc: -{{ overflow }}px; animation: txt-scroll {{ [(len / 8) | round(0, 'ceil'), 8] | max }}s linear infinite;{% endif %}" : "") + " }",
        "  .card-foot { position: absolute; left: 16px; right: 16px; bottom: 10px; font-size: 14px; opacity: 0.7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }");
      if (t.scroll) L.push(...SCROLL_KF);
      L.push("</style>",
        '<div class="card-title">' + (t.emoji ? escH(t.emoji) + " " : "") + "{{ f_title if f_title else '" + jq(escH(t.title || name)) + "' }}</div>",
        '<div class="content-wrap">', "  <div class=\"content-text\">{{ f_text if f_text else 'Nothing announced yet.' }}</div>", "</div>");
      if (hasFoot) L.push("{% if f_small %}<div class=\"card-foot\">{{ f_small }}</div>{% endif %}");
      return "type: custom:html-template-card\nignore_line_breaks: true\ncontent: |\n" + L.map(x => "  " + x).join("\n") + "\n";
    }
    const HW = H - 64, title = escH(fallback);
    const L = ["{% set raw = (state_attr('" + sensor + "', 'content') or '') | trim %}", "{% set len = raw | length %}"];
    if (t.scroll) L.push("{% set fsize = 18 %}", "{% set overflow = [((len / " + CPL + ") | round(0, 'ceil')) * 24 - " + HW + ", 0] | max %}");
    else L.push(...SIZES);
    L.push("<style>", ...GLASS(H),
      "  .card-title { font-size: 25px; font-weight: 600; padding: 14px 16px 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
      "  .content-wrap { height: " + HW + "px; overflow: hidden; padding: 4px 16px 0; box-sizing: border-box; }",
      "  .content-text { font-size: {{ fsize }}px; line-height: 1.3; width: 100%;" + (t.scroll ? " {% if overflow > 0 %}--sc: -{{ overflow }}px; animation: txt-scroll {{ [(len / 8) | round(0, 'ceil'), 8] | max }}s linear infinite;{% endif %}" : "") + " }");
    if (t.scroll) L.push(...SCROLL_KF);
    L.push("</style>", '<div class="card-title">' + title + "</div>", '<div class="content-wrap">', '  <div class="content-text">{{ raw if raw else \'Nothing announced yet.\' }}</div>', "</div>");
    return "type: custom:html-template-card\nignore_line_breaks: true\ncontent: |\n" + L.map(x => "  " + x).join("\n") + "\n";
  }
  /* wrapped in the show / hide switch from the Dashboard card section, if one is picked */
  function cardYaml(t, name, sw) {
    const y = baseYaml(t, name);
    if (!/^input_boolean\.[a-z0-9_]+$/.test(String(sw || ""))) return y;
    return "type: conditional\nconditions:\n  - condition: state\n    entity: " + sw + "\n    state: 'on'\ncard:\n" + y.trimEnd().split("\n").map(l => l ? "  " + l : l).join("\n") + "\n";
  }

  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); return true; } catch (e) { /* the app's frame may block the clipboard */ }
    const ta = el("textarea", {style: "position:fixed;top:0;left:0;opacity:0"}); ta.value = t; document.body.append(ta); ta.focus(); ta.select();
    try { ta.setSelectionRange(0, t.length); } catch (e) { /* ignore */ }
    let ok = false; try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
    ta.remove(); return ok;
  }
  async function showPreview(box, yaml) {
    box.replaceChildren(el("p", {class: "dim small"}, el("span", {class: "spin"}), "Asking Home Assistant to render it..."));
    let r;
    try { r = await api("cards/preview", {yaml}); } catch (e) { r = {ok: false, error: String(e)}; }
    box.replaceChildren();
    if (!r || !r.ok) { box.append(el("div", {class: "note bad"}, el("div", {}, (r && r.error) || "That failed."))); return; }
    if (r.note) box.append(el("div", {class: "note"}, el("div", {}, r.note)));
    (r.items || []).forEach((it, i) => {
      box.append(el("div", {class: "prevhead"}, el("b", {}, "Card " + (i + 1)), el("span", {class: "pill plain"}, it.type)));
      if (it.error) { box.append(el("div", {class: "note bad"}, el("div", {}, el("b", {}, "Home Assistant could not render it"), el("pre", {}, it.error)))); return; }
      const h = (it.html.match(/ha-card[^}]*?height:\s*(\d+)px/) || [])[1];
      box.append(el("iframe", {class: "prev", sandbox: "", srcdoc: frameDoc(it.title, it.html), style: "height:" + Math.min(Math.max((+h || 320) + 50, 180), 820) + "px;resize:vertical"}));
    });
    if ((r.items || []).length) box.append(el("p", {class: "help"}, "Scrolling cards animate, so give it a few seconds. The card reads the sensor above, so if it says nothing announced yet, push the announcement and run it once with this switched on."));
  }

  function refresh() {
    const t = txtGet(), name = nameNow(), fields = t.mode === "fields";
    $("#txt-opts").hidden = !t.on;
    $("#txt-fieldsbox").hidden = !fields;
    $("#txt-cplwrap").hidden = !t.scroll;
    $("#txt-topic").textContent = txtTopicOf(t, name);
    $("#txt-file").placeholder = txtFileOf(Object.assign({}, t, {file: ""}), name);
    $("#txt-sensor").placeholder = txtSensorOf(Object.assign({}, t, {sensor: ""}), name);
    $("#txt-title").placeholder = fields ? "Shown when there is no title field" : name;
    $("#txt-fnote").textContent = fields && !annFields({txt: t}) ? "Add at least one field, or the plain text is saved instead." : "";
    $("#txt-yaml").value = cardYaml(t, name, typeof CARD === "object" ? CARD.sw : "");
  }

  /* hook into the existing editor */
  const origSt = st;
  st = function () { const s = origSt(); if (!rawMode) s.txt = txtGet(); return s; };
  const origApply = applyState;
  applyState = function (s) { origApply(s); txtSet(s && s.txt); gen(); };
  const origGen = gen;
  gen = function () { origGen(); refresh(); };
  if (typeof libCard === "function") {
    const origCard = libCard;
    libCard = function (it) {
      const c = origCard(it), t = it && it.state && it.state.txt, meta = c.querySelector(".meta");
      if (t && t.on && meta) meta.append(el("span", {class: "pill plain", title: txtTopicOf(t, it.name || it.id)}, (t.mode === "fields" ? "Saves fields to " : "Saves text to ") + txtFileOf(t, it.name || it.id)));
      return c;
    };
  }
  $("#txt-mode").onchange = () => { if ($("#txt-mode").value === "fields" && !FLD.length) { FLD = BDAY.map(f => Object.assign({}, f)); drawFields("message"); } };

  $("#txt-copy").onclick = async () => {
    const m = $("#txt-msg"), ta = $("#txt-yaml"), ok = await copyText(ta.value);
    m.className = "msg " + (ok ? "ok" : "warn");
    m.textContent = ok ? "Copied. In your dashboard, add a Manual card and paste." : "Your browser blocked copying. Tap the box, select all, and copy.";
    if (!ok) { ta.removeAttribute("readonly"); ta.focus(); ta.select(); }
  };
  $("#txt-prev").onclick = async () => {
    const b = $("#txt-prev"); b.disabled = true;
    await showPreview($("#txt-res"), baseYaml(txtGet(), nameNow()));
    b.disabled = false;
  };
  /* hand this announcement to the Cards tab, so the AI card creator starts from its sensor, fields and switch */
  $("#txt-cards").onclick = () => {
    const t = txtGet(), name = nameNow();
    sendToCards({kind: "announcement", id: cur.id || "", name, sensor: txtSensorOf(t, name), toggle: typeof CARD === "object" ? CARD.sw : "", shape: annShape(t, name)});
  };

  txtSet({}); refresh();
  api("facts/options").then(f => { if (f && typeof f.mqtt_prefix === "string") { TXT_PREFIX = f.mqtt_prefix; refresh(); } }).catch(() => {});
})();

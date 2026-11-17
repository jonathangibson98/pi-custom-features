/* A visual editor for an automation or script: triggers, conditions and steps as fields, so nothing has to be edited as YAML.
   It works on the parsed object. Anything it has no field for stays editable in each item's "More settings" box. */
const AF = (() => {
  const Y = {
    parse(t) { try { const o = jsyaml.load(t); return o && typeof o === "object" && !Array.isArray(o) ? o : null; } catch (e) { return null; } },
    dump(o) { return jsyaml.dump(o, {lineWidth: -1, noRefs: true, sortKeys: false}); },
    why(t) { try { const o = jsyaml.load(t); return o && typeof o === "object" && !Array.isArray(o) ? "" : "That needs to be key: value lines."; } catch (e) { return "YAML problem: " + String(e.message).split("\n")[0]; } },
  };
  const clone = o => JSON.parse(JSON.stringify(o));
  const getp = (o, p) => p.reduce((a, k) => (a == null ? undefined : a[k]), o);
  function setp(o, p, v) {
    const st = [o];
    for (let i = 0; i < p.length - 1; i++) {
      const cur = st[i][p[i]];
      if (cur === null || typeof cur !== "object") { if (v === undefined) return; st[i][p[i]] = {}; }
      st.push(st[i][p[i]]);
    }
    const last = p[p.length - 1], tail = st[st.length - 1];
    if (v === undefined) {
      delete tail[last];
      for (let i = p.length - 2; i >= 0; i--) { if (!Object.keys(st[i + 1]).length) delete st[i][p[i]]; else break; }
    } else tail[last] = v;
  }
  const pathOf = f => f.path || [f.k];
  const isObj = v => v !== null && typeof v === "object";
  const strs = v => (v == null || v === "" ? [] : Array.isArray(v) ? v.map(String) : [String(v)]);

  /* can this field show the value that is there now? (structured values stay in More settings) */
  function fieldOk(item, f) {
    const v = getp(item, pathOf(f));
    if (v === undefined || v === null) return v === undefined;
    if (f.kind === "entities") return Array.isArray(v) ? v.every(x => typeof x === "string") : typeof v === "string";
    if (f.kind === "entity") return typeof v === "string";
    if (f.kind === "select") return f.opts.some(o => o[0] === String(v));
    return !isObj(v);
  }

  function fieldEl(item, f, ctx) {
    const get = () => getp(item, pathOf(f));
    const put = v => { setp(item, pathOf(f), v); ctx.commit(); };
    const out = [el("label", {class: "l"}, f.label)];
    if (f.kind === "entities" || f.kind === "entity") {
      const multi = f.kind === "entities";
      out.push(picker(f.doms || null, multi, () => strs(get()), a => put(!a.length ? undefined : multi ? a : a[0])));
    } else if (f.kind === "select") {
      const s = el("select", {style: "max-width:320px"}, f.opts.map(o => el("option", {value: o[0]}, o[1])));
      s.value = get() == null ? "" : String(get());
      s.onchange = () => put(s.value === "" ? undefined : s.value);
      out.push(s);
    } else {
      const area = f.kind === "area", v0 = get();
      const i = el(area ? "textarea" : "input", {class: area ? "code" : null, spellcheck: "false", autocomplete: "off", placeholder: f.ph || "",
        value: v0 == null ? "" : String(v0), style: area ? "min-height:" + (f.h || 110) + "px" : null});
      i.oninput = () => { const t = i.value; put(t === "" ? undefined : f.num && /^-?\d+$/.test(t) ? +t : t); };
      out.push(i);
    }
    if (f.help) out.push(el("p", {class: "help"}, f.help));
    return out;
  }

  /* the fields of one item, plus a YAML box for every key there is no field for */
  function body(item, spec, ctx) {
    const hand = spec.fields.filter(f => fieldOk(item, f));
    const keep = (spec.keep || []).concat(["alias", "enabled"]);
    const rest = clone(item);
    keep.forEach(k => delete rest[k]);
    hand.forEach(f => setp(rest, pathOf(f), undefined));
    const has = Object.keys(rest).length > 0;
    const ta = el("textarea", {class: "code", spellcheck: "false", style: "min-height:" + (has ? 120 : 64) + "px", placeholder: "key: value", value: has ? Y.dump(rest).trimEnd() : ""});
    const err = el("p", {class: "msg"});
    ta.onchange = () => {
      let obj = {};
      if (ta.value.trim()) {
        const w = Y.why(ta.value);
        if (w) { err.className = "msg bad"; err.textContent = w; return; }
        obj = jsyaml.load(ta.value);
      }
      err.className = "msg"; err.textContent = "";
      const keepVals = {}; keep.forEach(k => { if (k in item) keepVals[k] = item[k]; });
      const handVals = hand.map(f => [f, getp(item, pathOf(f))]);
      Object.keys(item).forEach(k => delete item[k]);
      Object.assign(item, keepVals, obj);
      handVals.forEach(([f, v]) => { if (v !== undefined) setp(item, pathOf(f), v); });
      ctx.commit();
    };
    const det = el("details", {}, el("summary", {}, has ? "More settings (YAML)" : "More settings (optional)"), ta, err);
    if (has) det.open = true;
    return [hand.map(f => fieldEl(item, f, ctx)), spec.extra ? spec.extra(item, ctx) : null, det];
  }

  /* one item in a list: title, move and delete buttons, label, on/off, and its body */
  function shell(title, list, idx, inner, ctx) {
    const item = list[idx];
    const swap = d => () => { const j = idx + d; [list[idx], list[j]] = [list[j], list[idx]]; ctx.commit(); ctx.redraw(); };
    const del = el("button", {class: "btn danger sm"}, "Remove");
    confirmTap(del, "Tap again", () => { list.splice(idx, 1); ctx.commit(); ctx.redraw(); });
    const head = el("div", {class: "row", style: "justify-content:space-between;margin-bottom:8px"}, el("h3", {}, title),
      el("div", {class: "row"}, el("button", {class: "btn sm", disabled: idx === 0, title: "Move up", onclick: swap(-1)}, "↑"),
        el("button", {class: "btn sm", disabled: idx === list.length - 1, title: "Move down", onclick: swap(1)}, "↓"), del));
    const kids = [head];
    if (isObj(item)) {
      const al = el("input", {value: item.alias || "", placeholder: "Label (optional)", autocomplete: "off"});
      al.oninput = () => { if (al.value) item.alias = al.value; else delete item.alias; ctx.commit(); };
      const en = el("input", {type: "checkbox", checked: item.enabled !== false});
      en.onchange = () => { if (en.checked) delete item.enabled; else item.enabled = false; ctx.commit(); };
      kids.push(el("label", {class: "l"}, "Label"), al, el("label", {class: "check", style: "margin-top:8px"}, en, el("span", {}, "Turned on")));
    }
    kids.push(inner);
    return el("div", {class: "card sub"}, kids);
  }

  /* an item that is not a key/value block (a template string, say): edited as plain text */
  function plain(list, idx, ctx) {
    const t = el("textarea", {class: "code", spellcheck: "false", value: typeof list[idx] === "string" ? list[idx] : Y.dump(list[idx]).trimEnd()});
    t.oninput = () => { list[idx] = t.value; ctx.commit(); };
    return t;
  }

  /* ---- what each kind of item looks like ---- */
  const F = (k, label, o) => Object.assign({k, label}, o || {});
  const TRIG = {
    time_pattern: {label: "Every so often", fields: [F("hours", "Hours", {num: 1, ph: "/12 means every 12 hours"}), F("minutes", "Minutes", {num: 1, ph: "/10 means every 10 minutes"}), F("seconds", "Seconds", {num: 1})]},
    time: {label: "At a time", fields: [F("at", "Time", {ph: "07:30:00"})]},
    state: {label: "When something changes", fields: [F("entity_id", "Entities", {kind: "entities"})]},
    numeric_state: {label: "When a number crosses a line", fields: [F("entity_id", "Entities", {kind: "entities"}), F("above", "Above"), F("below", "Below")]},
    sun: {label: "Sunrise or sunset", fields: [F("event", "Event", {kind: "select", opts: [["sunrise", "Sunrise"], ["sunset", "Sunset"]]}), F("offset", "Offset", {ph: "-00:30:00"})]},
    homeassistant: {label: "Home Assistant", fields: [F("event", "Event", {kind: "select", opts: [["start", "Starts"], ["shutdown", "Shuts down"]]})]},
    template: {label: "When a template becomes true", fields: [F("value_template", "Template", {kind: "area"})]},
    event: {label: "When an event fires", fields: [F("event_type", "Event type")]},
    mqtt: {label: "When an MQTT message arrives", fields: [F("topic", "Topic")]},
    webhook: {label: "Webhook", fields: [F("webhook_id", "Webhook id")]},
  };
  const COND = {
    template: {label: "Template is true", fields: [F("value_template", "Template", {kind: "area"})]},
    state: {label: "Something is in a state", fields: [F("entity_id", "Entities", {kind: "entities"}), F("state", "State", {ph: "on"})]},
    numeric_state: {label: "A number is in range", fields: [F("entity_id", "Entities", {kind: "entities"}), F("above", "Above"), F("below", "Below")]},
    time: {label: "Time of day", fields: [F("after", "After", {ph: "07:00:00"}), F("before", "Before", {ph: "22:00:00"})]},
    trigger: {label: "Which trigger fired", fields: [F("id", "Trigger id")]},
  };
  const trigType = t => String(t.trigger || t.platform || "");
  const actKind = a => {
    if (!isObj(a)) return "plain";
    if (isObj(a.variables) && Object.keys(a).every(k => ["variables", "alias", "enabled"].includes(k))) return "vars";
    const act = a.action || a.service;
    if (act === "ai_task.generate_data") return "ai";
    if (act === "mqtt.publish") return "mqtt";
    return act ? "service" : "other";
  };

  function mqttExtra(item, ctx) {
    const pre = (typeof F_PREFIX === "function" ? F_PREFIX() : "");
    const cur = String(getp(item, ["data", "topic"]) || "");
    const target = pre + cur.split("/").pop();
    if (!pre || !cur || cur === target) return null;
    return el("div", {class: "row", style: "margin-top:6px"}, el("button", {class: "btn sm", onclick: () => { setp(item, ["data", "topic"], target); ctx.commit(); ctx.redraw(); }}, "Use my folder: " + target));
  }

  function varsBody(item, ctx) {
    const V = item.variables, wrap = el("div", {});
    const draw = () => {
      wrap.replaceChildren();
      Object.keys(V).forEach(k => {
        const vv = V[k], structured = isObj(vv);
        const ni = el("input", {value: k, spellcheck: "false", autocomplete: "off", style: "max-width:260px", placeholder: "name"});
        const ta = el("textarea", {class: "code", spellcheck: "false", style: "min-height:" + (String(structured ? Y.dump(vv) : vv).length > 140 ? 170 : 64) + "px",
          value: structured ? Y.dump(vv).trimEnd() : vv == null ? "" : String(vv)});
        const err = el("p", {class: "msg"});
        ta.oninput = () => {
          const t = ta.value;
          if (structured) { try { V[k] = jsyaml.load(t); err.className = "msg"; err.textContent = ""; } catch (e) { err.className = "msg bad"; err.textContent = "YAML problem: " + String(e.message).split("\n")[0]; return; } }
          else if (typeof vv === "number" && t.trim() !== "" && !isNaN(+t)) V[k] = +t;
          else if (typeof vv === "boolean" && /^(true|false)$/i.test(t.trim())) V[k] = t.trim().toLowerCase() === "true";
          else V[k] = t;
          ctx.commit();
        };
        ni.onchange = () => {
          const n = ni.value.trim();
          if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(n) || (n !== k && n in V)) { ni.value = k; return; }
          const nv = {}; Object.keys(V).forEach(x => { nv[x === k ? n : x] = V[x]; });
          Object.keys(V).forEach(x => delete V[x]); Object.assign(V, nv); ctx.commit(); draw();
        };
        const rm = el("button", {class: "btn danger sm"}, "Remove");
        confirmTap(rm, "Tap again", () => { delete V[k]; ctx.commit(); draw(); });
        wrap.append(el("div", {style: "margin-bottom:12px"}, el("div", {class: "row", style: "justify-content:space-between"}, ni, rm), ta, err));
      });
      wrap.append(el("button", {class: "btn sm", onclick: () => { let n = 1; while (("new_variable_" + n) in V) n++; V["new_variable_" + n] = ""; ctx.commit(); draw(); }}, "Add a variable"));
    };
    draw();
    return wrap;
  }

  function actionBody(list, idx, ctx) {
    const a = list[idx], kind = actKind(a);
    if (kind === "plain") return {title: "Step", inner: plain(list, idx, ctx)};
    if (kind === "vars") return {title: "Set variables", inner: varsBody(a, ctx)};
    if (kind === "ai") return {title: "Ask the AI", inner: body(a, {keep: ["action", "service", "metadata"], fields: [
      F("task_name", "Task name", {path: ["data", "task_name"]}),
      F("entity_id", "AI task entity", {kind: "entity", doms: ["ai_task"], path: ["data", "entity_id"]}),
      F("instructions", "What to ask", {kind: "area", h: 300, path: ["data", "instructions"], help: "Template tags like {{ now().year }} work here."}),
      F("response_variable", "Save the answer as", {ph: "result", help: "Later steps read it as {{ result.data }}."})]}, ctx)};
    if (kind === "mqtt") return {title: "Save to a file (MQTT)", inner: body(a, {keep: ["action", "service"], extra: mqttExtra, fields: [
      F("topic", "File path (topic)", {path: ["data", "topic"], ph: "file_reader/overwrite/my_fact.txt"}),
      F("payload", "What to save", {kind: "area", h: 130, path: ["data", "payload"]})]}, ctx)};
    if (kind === "service") return {title: "Do something", inner: body(a, {keep: [], fields: [F("action", "Action", {ph: "light.turn_on"})]}, ctx)};
    return {title: "Other step", inner: body(a, {keep: [], fields: []}, ctx)};
  }

  const NEWT = {
    time_pattern: {trigger: "time_pattern", hours: "/12"}, time: {trigger: "time", at: "07:00:00"}, state: {trigger: "state", entity_id: []},
    numeric_state: {trigger: "numeric_state", entity_id: [], above: 0}, sun: {trigger: "sun", event: "sunset"}, homeassistant: {trigger: "homeassistant", event: "start"},
    template: {trigger: "template", value_template: "{{ true }}"}, event: {trigger: "event", event_type: ""}, mqtt: {trigger: "mqtt", topic: ""}, webhook: {trigger: "webhook", webhook_id: ""},
  };
  const NEWC = {
    template: {condition: "template", value_template: "{{ true }}"}, state: {condition: "state", entity_id: [], state: "on"},
    numeric_state: {condition: "numeric_state", entity_id: [], above: 0}, time: {condition: "time", after: "07:00:00", before: "22:00:00"}, trigger: {condition: "trigger", id: ""},
  };
  const NEWA = () => ({
    ai: {action: "ai_task.generate_data", metadata: {}, data: {task_name: "", entity_id: "", instructions: ""}, response_variable: "result"},
    mqtt: {action: "mqtt.publish", data: {topic: (typeof F_PREFIX === "function" ? F_PREFIX() : "") + "my_fact.txt", payload: "{{ result.data }}"}},
    vars: {variables: {new_variable: ""}}, service: {action: "script.turn_on"}, delay: {delay: {seconds: 5}},
  });

  function adder(label, opts, make, list, ctx) {
    const s = el("select", {style: "max-width:320px"}, el("option", {value: ""}, label), opts.map(o => el("option", {value: o[0]}, o[1])));
    s.onchange = () => { if (!s.value) return; list.push(make(s.value)); ctx.commit(); ctx.redraw(); };
    return s;
  }

  /* the cards for one document. opt.script: a script (steps only), otherwise an automation */
  function cards(A, ctx, n, opt) {
    opt = opt || {};
    const out = [];
    const keyOf = (a, b) => (b in A && !(a in A) ? b : a);
    const arr = (a, b) => { const k = keyOf(a, b); if (!Array.isArray(A[k])) A[k] = A[k] == null ? [] : [A[k]]; return A[k]; };
    /* settings */
    const desc = el("input", {value: A.description || "", placeholder: "What it is for (optional)"});
    desc.oninput = () => { if (desc.value) A.description = desc.value; else delete A.description; ctx.commit(); };
    const mode = el("select", {style: "max-width:320px"}, [["single", "Single: ignore a new run while one is going"], ["restart", "Restart: start over on a new run"], ["queued", "Queued: run them one after another"], ["parallel", "Parallel: run them together"]].map(o => el("option", {value: o[0]}, o[1])));
    mode.value = ["single", "restart", "queued", "parallel"].includes(A.mode) ? A.mode : "single";
    mode.onchange = () => { A.mode = mode.value; ctx.commit(); };
    out.push(card(n++, "Settings", null, el("label", {class: "l"}, "Description"), desc, el("label", {class: "l"}, "If it is triggered again while running"), mode));

    if (!opt.script) {
      const T = arr("triggers", "trigger"), tw = el("div", {class: "stack"});
      T.forEach((t, i) => {
        if (!isObj(t)) { tw.append(shell("Trigger", T, i, plain(T, i, ctx), ctx)); return; }
        const ty = trigType(t), sp = TRIG[ty];
        tw.append(shell(sp ? sp.label : "Trigger" + (ty ? ": " + ty : ""), T, i, body(t, {keep: ["trigger", "platform", "id"], fields: (sp ? sp.fields : []).concat([F("id", "Trigger id", {help: "Optional. A condition can ask which trigger fired."})])}, ctx), ctx));
      });
      if (!T.length) tw.append(el("p", {class: "msg warn"}, "No triggers yet, so it only runs when you run it by hand."));
      tw.append(adder("Add a trigger...", Object.keys(TRIG).map(k => [k, TRIG[k].label]), k => clone(NEWT[k]), T, ctx));
      out.push(card(n++, "When it runs", "Any one of these starts it.", tw));

      const C = arr("conditions", "condition"), cw = el("div", {class: "stack"});
      C.forEach((c, i) => {
        if (!isObj(c)) { cw.append(shell("Condition", C, i, plain(C, i, ctx), ctx)); return; }
        const ty = String(c.condition || ""), sp = COND[ty];
        cw.append(shell(sp ? sp.label : "Condition" + (ty ? ": " + ty : ""), C, i, body(c, {keep: ["condition"], fields: sp ? sp.fields : []}, ctx), ctx));
      });
      if (!C.length) cw.append(el("p", {class: "help"}, "None. It runs every time a trigger fires."));
      cw.append(adder("Add a condition...", Object.keys(COND).map(k => [k, COND[k].label]), k => clone(NEWC[k]), C, ctx));
      out.push(card(n++, "Only if", "All of these must be true.", cw));
    }

    const S = arr("actions", "action"), key = opt.script ? "sequence" : keyOf("actions", "action");
    const L = opt.script ? (Array.isArray(A.sequence) ? A.sequence : (A.sequence = [])) : S;
    const sw = el("div", {class: "stack"});
    L.forEach((a, i) => { const b = actionBody(L, i, ctx); sw.append(shell(b.title, L, i, b.inner, ctx)); });
    if (!L.length) sw.append(el("p", {class: "msg warn"}, "No steps yet."));
    sw.append(adder("Add a step...", [["ai", "Ask the AI"], ["mqtt", "Save to a file (MQTT)"], ["vars", "Set variables"], ["service", "Do something (any action)"], ["delay", "Wait"]], k => clone(NEWA()[k]), L, ctx));
    out.push(card(n++, "What it does", "Steps run top to bottom.", sw));
    out.nextN = n;
    return out;
  }

  return {Y, cards, clone};
})();

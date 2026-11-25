/* Shared by Announcements and Facts: the "When it runs" schedule.
   One place builds the YAML (triggers and conditions) and draws the panel, so both pages behave the same.
   Needs the page to define: el(), $(), picker() and ENT (the entity list). */
const SCHED = (() => {
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const OPS = [["is", "is"], ["not", "is not"], ["above", "is above"], ["below", "is below"]];
  const DAYS = [["mon", "Mon"], ["tue", "Tue"], ["wed", "Wed"], ["thu", "Thu"], ["fri", "Fri"], ["sat", "Sat"], ["sun", "Sun"]];
  const MODES = [["any", "Any of them"], ["all", "All of them"], ["none", "None of them"]];
  const clone = x => JSON.parse(JSON.stringify(x));
  /* the settings added on top of what the pages already had; older saved schedules just get these defaults */
  const extra = () => ({homeMode: "any", from: "", to: "", win2: {from: "", to: ""}, days: [], months: [], sun: "", only: [], gap: 0, atMore: [], sunEvent: "", sunOffset: 0, watchTo: ""});
  const fill = a => {
    const d = extra();
    for (const k of Object.keys(d)) if (a[k] === undefined || a[k] === null) a[k] = d[k];
    for (const k of ["home", "days", "only", "months", "atMore"]) if (!Array.isArray(a[k])) a[k] = [];
    if (!a.win2 || typeof a.win2 !== "object") a.win2 = {from: "", to: ""};
    return a;
  };
  const isTime = t => /^\d{1,2}:\d{2}$/.test(t || "");
  const hms = t => t.padStart(5, "0") + ":00";
  const name = id => { const e = (typeof ENT !== "undefined" ? ENT : []).find(x => x.id === id); return e && e.name ? e.name : id; };

  /* ---------- YAML ---------- */
  const q = v => JSON.stringify(String(v));
  /* "is this entity on / home / has someone in it", by what kind of entity it is */
  function presence(e) {
    const d = e.split(".")[0];
    if (d === "zone") return {condition: "numeric_state", entity_id: e, above: 0};
    if (d === "person" || d === "device_tracker") return {condition: "state", entity_id: e, state: "home"};
    return {condition: "state", entity_id: e, state: "on"};
  }
  /* conditions as plain objects, in the order they are shown on the page */
  function conditions(a) {
    const C = [];
    const home = a.home || [];
    if (home.length) {
      const list = home.map(presence);
      if (a.homeMode === "all") C.push(list.length === 1 ? list[0] : {condition: "and", conditions: list});
      else if (a.homeMode === "none") C.push({condition: "not", conditions: list});
      else C.push(list.length === 1 ? list[0] : {condition: "or", conditions: list});
    }
    const win = (f, t) => { const x = {condition: "time"}; if (isTime(f)) x.after = hms(f); if (isTime(t)) x.before = hms(t); return Object.keys(x).length > 1 ? x : null; };
    const w1 = win(a.from, a.to), w2 = a.win2 ? win(a.win2.from, a.win2.to) : null;
    if (w1 && w2) C.push({condition: "or", conditions: [w1, w2]});
    else if (w1 || w2) C.push(w1 || w2);
    if ((a.days || []).length && a.days.length < 7) C.push({condition: "time", weekday: DAYS.map(d => d[0]).filter(d => a.days.includes(d))});
    if ((a.months || []).length && a.months.length < 12) C.push({condition: "template", value_template: "{{ now().month in [" + [...a.months].sort((x, y) => x - y).join(", ") + "] }}"});
    if (a.sun === "day") C.push({condition: "state", entity_id: "sun.sun", state: "above_horizon"});
    if (a.sun === "night") C.push({condition: "state", entity_id: "sun.sun", state: "below_horizon"});
    for (const o of a.only || []) {
      if (!o.entity) continue;
      const op = o.op || (o.not ? "not" : "is");
      if (o.state === "" || o.state == null) continue;
      if (op === "above" || op === "below") {
        if (isNaN(+o.state)) continue;
        const c = {condition: "numeric_state", entity_id: o.entity}; if (o.attr) c.attribute = o.attr; c[op] = +o.state; C.push(c); continue;
      }
      const c = {condition: "state", entity_id: o.entity, state: String(o.state)};
      if (o.attr) c.attribute = o.attr;
      if (op === "is" && +o.for > 0) c.for = {minutes: Math.round(+o.for)};
      C.push(op === "not" ? {condition: "not", conditions: [c]} : c);
    }
    if (+a.gap > 0) C.push({condition: "template", value_template: "{{ this.attributes.last_triggered is none or (now() - this.attributes.last_triggered).total_seconds() >= " + Math.round(+a.gap) * 60 + " }}"});
    return C;
  }
  /* an object as YAML lines. Strings are double-quoted (JSON strings are valid YAML), numbers stay numbers. */
  function emit(o, pad) {
    let out = "";
    for (const [k, v] of Object.entries(o)) {
      if (Array.isArray(v) && v.length && typeof v[0] === "object") out += pad + k + ":\n" + v.map(x => pad + "  - " + emit(x, pad + "    ").trimStart()).join("");
      else if (Array.isArray(v)) out += pad + k + ":\n" + v.map(x => pad + "  - " + q(x) + "\n").join("");
      else if (v && typeof v === "object") out += pad + k + ":\n" + emit(v, pad + "  ");
      else out += pad + k + ": " + (typeof v === "number" ? v : q(v)) + "\n";
    }
    return out;
  }
  /* "conditions:\n  - ...", or "" when there are none */
  function conditionsYaml(a) {
    const C = conditions(a);
    return C.length ? "conditions:\n" + C.map(c => "  - " + emit(c, "    ").trimStart()).join("") : "";
  }
  /* the triggers, each one a block that starts with "  - trigger:" */
  function triggers(a) {
    const T = [];
    if (+a.every > 0) {
      if (a.unit === "hours") T.push(`  - trigger: time_pattern\n    hours: "/${Math.min(23, Math.max(1, Math.round(+a.every)))}"\n    minutes: 0\n`);
      else T.push(`  - trigger: time_pattern\n    minutes: "/${Math.min(59, Math.max(1, Math.round(+a.every)))}"\n`);
    }
    if (isTime(a.at)) T.push(`  - trigger: time\n    at: "${hms(a.at)}"\n`);
    (a.atMore || []).filter(isTime).forEach(t => T.push(`  - trigger: time\n    at: "${hms(t)}"\n`));
    if (a.sunEvent === "sunrise" || a.sunEvent === "sunset") {
      const m = Math.round(+a.sunOffset || 0), hh = String(Math.floor(Math.abs(m) / 60)).padStart(2, "0"), mm = String(Math.abs(m) % 60).padStart(2, "0");
      T.push(`  - trigger: sun\n    event: ${a.sunEvent}\n` + (m ? `    offset: "${m < 0 ? "-" : ""}${hh}:${mm}:00"\n` : ""));
    }
    if (a.watch) T.push(`  - trigger: state\n    entity_id: ${a.watch}\n` + (a.watchAttr ? `    attribute: ${a.watchAttr}\n` : "") + (a.watchTo ? `    to: ${q(a.watchTo)}\n` : "") + (+a.watchFor > 0 ? `    for:\n      seconds: ${Math.round(+a.watchFor)}\n` : ""));
    return T;
  }
  const hasTrigger = a => !!(a && ((+a.every > 0) || isTime(a.at) || (a.atMore || []).some(isTime) || a.sunEvent || a.watch));

  /* ---------- plain-words summary ---------- */
  function when(a) {
    const p = [];
    if (+a.every > 0) p.push("every " + Math.round(+a.every) + (a.unit === "hours" ? " h" : " min"));
    const times = [a.at, ...(a.atMore || [])].filter(isTime);
    if (times.length) p.push("daily at " + times.join(", "));
    if (a.sunEvent) { const m = Math.round(+a.sunOffset || 0); p.push((m ? Math.abs(m) + " min " + (m < 0 ? "before " : "after ") : "at ") + a.sunEvent); }
    if (a.watch) p.push("when " + a.watch + (a.watchTo ? " changes to " + a.watchTo : " changes"));
    return p;
  }
  function only(a) {
    const p = [], n = (a.home || []).length;
    if (n) p.push((a.homeMode === "all" ? "all of " : a.homeMode === "none" ? "none of " : "any of ") + (n <= 3 ? a.home.map(name).join(", ") : n + " people/places") + " home");
    if (isTime(a.from) || isTime(a.to)) p.push((a.from || "00:00") + " to " + (a.to || "24:00") + (a.win2 && (isTime(a.win2.from) || isTime(a.win2.to)) ? " or " + (a.win2.from || "00:00") + " to " + (a.win2.to || "24:00") : ""));
    if ((a.months || []).length && a.months.length < 12) p.push([...a.months].sort((x, y) => x - y).map(m => MONTHS[m - 1]).join(" "));
    if ((a.days || []).length && a.days.length < 7) p.push(DAYS.filter(d => a.days.includes(d[0])).map(d => d[1]).join(" "));
    if (a.sun) p.push(a.sun === "day" ? "daytime" : "after dark");
    const o = (a.only || []).filter(x => x.entity && x.state !== "" && x.state != null).length;
    if (o) p.push(o + " extra check" + (o > 1 ? "s" : ""));
    if (+a.gap > 0) p.push("at most every " + Math.round(+a.gap) + " min");
    return p;
  }
  const summary = a => {
    const w = when(a).join(" and ") || "no trigger set", o = only(a);
    return w + (o.length ? ", only if " + o.join(", ") : "");
  };

  /* ---------- who is home (also used for the default in Settings) ---------- */
  /* a: any object with .home (list of entity ids) and .homeMode ("any", "all", "none"), changed in place.
     o: {onChange(), defaultHome: [], defaultMode: "any"}. The default button shows only while the list is empty. */
  function homePicker(a, o) {
    const O = o || {}, box = el("div", {class: "sched-home"});
    if (!Array.isArray(a.home)) a.home = [];
    if (!MODES.some(m => m[0] === a.homeMode)) a.homeMode = "any";
    const upd = () => { if (O.onChange) O.onChange(); draw(); };
    function draw() {
      const people = (typeof ENT !== "undefined" ? ENT : []).filter(e => e.id.startsWith("person."));
      const mode = el("div", {class: "seg"}, MODES.map(([id, label]) => el("button", {type: "button", class: a.homeMode === id ? "on" : "", onclick: () => { a.homeMode = id; upd(); }}, label)));
      const chips = el("div", {class: "chips", style: "margin:8px 0"});
      people.forEach(p => {
        const on = a.home.includes(p.id);
        chips.append(el("button", {type: "button", class: "chip" + (on ? " on" : ""), onclick: () => { a.home = on ? a.home.filter(x => x !== p.id) : [...a.home, p.id]; upd(); }}, p.name || p.id));
      });
      const others = a.home.filter(x => !x.startsWith("person."));
      const more = el("details", {class: "sched-more"}, el("summary", {}, "Add a zone, device tracker or any on/off entity" + (others.length ? " (" + others.length + ")" : "")),
        picker(null, true, () => others, v => { a.home = [...a.home.filter(x => x.startsWith("person.")), ...v]; upd(); }),
        el("p", {class: "help"}, "A zone (like zone.home) counts when someone is in it. People and device trackers count when home. Anything else counts when on."));
      if (others.length) more.open = true;
      const dh = O.defaultHome || [];
      const defBtn = dh.length && !a.home.length
        ? el("button", {type: "button", class: "btn sm", style: "margin-top:6px", onclick: () => { a.home = [...dh]; a.homeMode = O.defaultMode || "any"; upd(); }}, "Use my defaults (" + (MODES.find(m => m[0] === (O.defaultMode || "any")) || MODES[0])[1].toLowerCase() + ": " + (dh.length <= 3 ? dh.map(name).join(", ") : dh.length + " picked") + ")") : null;
      box.replaceChildren(...[mode, chips, people.length ? null : el("p", {class: "help"}, "No person entities found. Use the box below."), more, defBtn,
        a.home.length ? el("div", {style: "margin-top:6px"}, el("button", {type: "button", class: "btn sm", onclick: () => { a.home = []; upd(); }}, "Clear the list")) : null,
        el("p", {class: "help"}, a.homeMode === "all" ? "Runs only when everyone you picked is home." : a.homeMode === "none" ? "Runs only when none of the ones you picked is home." : "Runs when at least one of the ones you picked is home.")].filter(Boolean));
    }
    draw();
    return box;
  }

  /* ---------- the panel ---------- */
  /* a: the schedule object (changed in place). opts: {onChange(), defaultHome: [] and defaultMode (the saved defaults from Facts > Settings)} */
  function panel(a, opts) {
    fill(a);
    const O = opts || {}, root = el("div", {class: "sched"});
    let tab = hasTrigger(a) || !only(a).length ? "when" : "only";
    const change = () => { if (O.onChange) O.onChange(); drawTop(); };
    const top = el("div", {class: "sched-top"}), tabs = el("div", {class: "seg sched-tabs"}), body = el("div", {class: "sched-body"});
    const counts = () => ({when: when(a).length, only: only(a).filter(x => !x.startsWith("at most")).length, limits: +a.gap > 0 ? 1 : 0});
    function drawTop() {
      const w = when(a), o = only(a);
      top.replaceChildren(
        el("div", {class: "sched-line"}, el("b", {}, "Runs "), w.length ? w.join(" and ") : el("span", {class: "dim"}, "nothing yet. Set a repeat, a time or an entity on the When tab.")),
        o.length ? el("div", {class: "sched-line"}, el("b", {}, "Only if "), o.join(" · ")) : el("div", {class: "sched-line dim"}, "Always, whenever it triggers. Add limits on the Only if tab."));
      const c = counts();
      [...tabs.children].forEach(b => { const n = c[b.dataset.t]; b.firstChild.nodeValue = b.dataset.l + (n ? " · " + n : ""); });
    }
    [["when", "When"], ["only", "Only if"], ["limits", "Limits"]].forEach(([id, label]) => {
      const b = el("button", {type: "button", "data-t": id, "data-l": label, class: tab === id ? "on" : "", onclick: () => { tab = id; [...tabs.children].forEach(x => x.classList.toggle("on", x.dataset.t === id)); drawBody(); }}, label);
      tabs.append(b);
    });

    const field = (label, ...kids) => el("div", {class: "sched-f"}, el("label", {class: "l"}, label), ...kids);
    const num = (get, set, w) => { const i = el("input", {type: "number", min: 0, step: 1, value: get() || 0, style: "width:" + (w || 90) + "px"}); i.oninput = () => { set(i.value === "" ? 0 : +i.value); change(); }; return i; };

    function drawWhen() {
      const un = el("select", {style: "width:auto"}, el("option", {value: "minutes"}, "minutes"), el("option", {value: "hours"}, "hours"));
      un.value = a.unit === "minutes" ? "minutes" : "hours"; un.onchange = () => { a.unit = un.value; change(); };
      const at = el("input", {type: "time", value: a.at || "", style: "max-width:150px"}); at.onchange = () => { a.at = at.value; change(); };
      const more = el("div", {});
      const drawMore = () => more.replaceChildren(...a.atMore.map((t, i) => {
        const inp = el("input", {type: "time", value: t || "", style: "max-width:150px"}); inp.onchange = () => { a.atMore[i] = inp.value; change(); };
        return el("div", {class: "inline", style: "margin-top:6px"}, inp, el("button", {type: "button", class: "btn sm", onclick: () => { a.atMore.splice(i, 1); change(); drawMore(); }}, "Remove"));
      }));
      drawMore();
      const sunEv = el("select", {style: "width:auto"}, [["", "Off"], ["sunrise", "Sunrise"], ["sunset", "Sunset"]].map(([v, l]) => el("option", {value: v}, l)));
      sunEv.value = a.sunEvent || ""; sunEv.onchange = () => { a.sunEvent = sunEv.value; change(); };
      const watchOpts = el("div", {class: "inline", style: "margin-top:8px"});
      const drawWatchOpts = () => {
        watchOpts.replaceChildren(); if (!a.watch) return;
        const attr = el("input", {value: a.watchAttr || "", placeholder: "attribute (blank = state)", style: "max-width:230px"}); attr.oninput = () => { a.watchAttr = attr.value.trim(); change(); };
        const to = el("input", {value: a.watchTo || "", placeholder: "only when it becomes... (blank = any change)", style: "max-width:300px;margin-bottom:6px"}); to.oninput = () => { a.watchTo = to.value.trim(); change(); };
        watchOpts.append(to, attr, el("span", {class: "dim small"}, "after it has held for"), num(() => a.watchFor, v => a.watchFor = Math.max(0, Math.round(v))), el("span", {class: "dim small"}, "seconds"));
      };
      drawWatchOpts();
      body.replaceChildren(
        el("p", {class: "help"}, "Pick one or more ways to start it. They all work at the same time."),
        field("Repeat every", el("div", {class: "inline"}, num(() => a.every, v => a.every = v), un), el("p", {class: "help"}, "0 turns the repeat off. Minutes up to 59, hours up to 23.")),
        field("At this time every day", el("div", {class: "inline"}, at, el("button", {type: "button", class: "btn sm", onclick: () => { a.at = ""; at.value = ""; change(); }}, "Clear"))),
        field("More times every day", more, el("button", {type: "button", class: "btn sm", style: "margin-top:6px", onclick: () => { a.atMore.push(""); change(); drawMore(); }}, "Add a time")),
        field("At sunrise or sunset", el("div", {class: "inline"}, sunEv, el("input", {type: "number", step: 5, value: a.sunOffset || 0, style: "width:90px", oninput: ev => { a.sunOffset = ev.target.value === "" ? 0 : +ev.target.value; change(); }}), el("span", {class: "dim small"}, "minutes (negative = before)")),
          el("p", {class: "help"}, "Example: sunset with -30 runs half an hour before sunset.")),
        field("When this entity changes", picker(null, false, () => a.watch ? [a.watch] : [], v => { a.watch = v[0] || ""; drawWatchOpts(); change(); }), watchOpts));
    }

    function drawOnly() {
      /* 1. people */
      const homeBox = field("Who is home", homePicker(a, {onChange: change, defaultHome: O.defaultHome, defaultMode: O.defaultMode}));

      /* 2. time window + days */
      const tf = el("input", {type: "time", value: a.from || "", style: "max-width:140px"}), tt = el("input", {type: "time", value: a.to || "", style: "max-width:140px"});
      tf.onchange = () => { a.from = tf.value; change(); }; tt.onchange = () => { a.to = tt.value; change(); };
      const days = el("div", {class: "chips", style: "margin-top:6px"}, DAYS.map(([id, label]) => el("button", {type: "button", class: "chip" + (a.days.includes(id) ? " on" : ""), onclick: ev => {
        a.days = a.days.includes(id) ? a.days.filter(x => x !== id) : [...a.days, id]; ev.currentTarget.classList.toggle("on"); change(); }}, label)));
      const t2f = el("input", {type: "time", value: a.win2.from || "", style: "max-width:140px"}), t2t = el("input", {type: "time", value: a.win2.to || "", style: "max-width:140px"});
      t2f.onchange = () => { a.win2.from = t2f.value; change(); }; t2t.onchange = () => { a.win2.to = t2t.value; change(); };
      const timeBox = field("Time of day and days", el("div", {class: "inline"}, el("span", {class: "dim small"}, "between"), tf, el("span", {class: "dim small"}, "and"), tt,
        el("button", {type: "button", class: "btn sm", onclick: () => { a.from = a.to = ""; tf.value = tt.value = ""; change(); }}, "Clear")), days,
        el("div", {class: "inline", style: "margin-top:8px"}, el("span", {class: "dim small"}, "or also between"), t2f, el("span", {class: "dim small"}, "and"), t2t),
        el("div", {class: "chips", style: "margin-top:6px"}, MONTHS.map((label, i) => el("button", {type: "button", class: "chip" + (a.months.includes(i + 1) ? " on" : ""), onclick: ev => {
          a.months = a.months.includes(i + 1) ? a.months.filter(x => x !== i + 1) : [...a.months, i + 1]; ev.currentTarget.classList.toggle("on"); change(); }}, label))),
        el("p", {class: "help"}, "Leave the days and months empty for all of them. A window can cross midnight, like 22:00 to 06:00. The second window is for things like morning and evening."));

      /* 3. daylight */
      const sun = el("div", {class: "seg"}, [["", "Any time"], ["day", "Daytime only"], ["night", "After dark only"]].map(([id, label]) => el("button", {type: "button", class: (a.sun || "") === id ? "on" : "", onclick: () => { a.sun = id; change(); drawOnly(); }}, label)));
      const sunBox = field("Daylight", sun);

      /* 4. extra entity checks */
      const rows = el("div", {});
      const drawRows = () => {
        rows.replaceChildren(...a.only.map((o, i) => {
          const op = el("select", {style: "width:auto"}, OPS.map(([v, l]) => el("option", {value: v}, l))); op.value = o.op || (o.not ? "not" : "is");
          op.onchange = () => { o.op = op.value; o.not = op.value === "not"; change(); drawRows(); };
          const num_ = op.value === "above" || op.value === "below";
          const st = el("input", {value: o.state || "", placeholder: num_ ? "a number, like 75" : "state, like on or home", style: "max-width:200px"}); st.oninput = () => { o.state = st.value.trim(); change(); };
          const at_ = el("input", {value: o.attr || "", placeholder: "attribute (blank = state)", style: "max-width:200px"}); at_.oninput = () => { o.attr = at_.value.trim(); change(); };
          const forBox = op.value === "is" ? [el("span", {class: "dim small"}, "for at least"), num(() => o.for, v => o.for = Math.max(0, Math.round(v)), 70), el("span", {class: "dim small"}, "min")] : [];
          return el("div", {class: "card sub", style: "margin-top:8px"}, picker(null, false, () => o.entity ? [o.entity] : [], v => { o.entity = v[0] || ""; change(); }),
            el("div", {class: "inline", style: "margin-top:6px"}, op, st, at_), el("div", {class: "inline", style: "margin-top:6px"}, ...forBox, el("button", {type: "button", class: "btn sm", onclick: () => { a.only.splice(i, 1); change(); drawRows(); }}, "Remove")));
        }));
      };
      drawRows();
      const extraBox = field("Other things that must be true", rows, el("button", {type: "button", class: "btn sm", style: "margin-top:8px", onclick: () => { a.only.push({entity: "", state: "", not: false}); drawRows(); }}, "+ Add a check"),
        el("p", {class: "help"}, "For example a switch is on, a media player is not playing, or a temperature is above 75. All of them must be true."));
      body.replaceChildren(homeBox, timeBox, sunBox, extraBox);
    }

    function drawLimits() {
      body.replaceChildren(
        el("p", {class: "help"}, "Extra brakes so it does not run too often."),
        field("At most once every (minutes)", num(() => a.gap, v => a.gap = Math.max(0, Math.round(v))),
          el("p", {class: "help"}, "0 means no limit. Counts from the last time this automation ran, so a busy trigger such as an entity changing a lot cannot spam you.")));
    }
    function drawBody() { (tab === "when" ? drawWhen : tab === "only" ? drawOnly : drawLimits)(); }
    drawTop(); drawBody();
    root.append(top, tabs, body);
    return root;
  }

  return {DAYS, MONTHS, OPS, extra, fill, clone, conditions, conditionsYaml, triggers, hasTrigger, summary, panel, homePicker};
})();

/* "Check & ask AI" box, shared by Build, Announcements, Facts, Cards, Dashboards and Files.
   askAI(host, getCtx) fills the element `host` with the box. getCtx() runs each time a button is pressed and returns
   what is on screen right now:
     {section, name, content (text the AI should read), yamls: [{label, text}] (optional, parsed and entity-checked first),
      ai (optional AI Task entity), kind/sources (Announcements and Facts only)}
   Nothing is changed, saved or run: the box only reads and answers. Needs ui.js (el, api). */
function askAI(host, getCtx, opts) {
  opts = opts || {};
  const history = [];
  const out = el("div", {style: "margin-top:12px"});
  const q = el("textarea", {style: "min-height:70px", placeholder: opts.placeholder || "Ask anything about this, e.g. \"why would this never run?\" or \"how can I make it shorter?\" (optional when you press Check or Suggest)"});
  const bCheck = el("button", {type: "button", class: "btn primary"}, "Check for errors");
  const bSug = el("button", {type: "button", class: "btn"}, "Suggest improvements");
  const bAsk = el("button", {type: "button", class: "btn"}, "Ask");
  const bClear = el("button", {type: "button", class: "btn sm quiet", hidden: true}, "Clear chat");
  const all = [bCheck, bSug, bAsk];
  const lock = (on, active, text) => all.forEach(b => { b.disabled = on; if (b === active) { b.dataset.t = b.dataset.t || b.textContent; b.textContent = on ? text : b.dataset.t; } });

  const issueRow = i => el("div", {class: "li"}, el("div", {class: "t"},
    el("b", {}, (i.level === "problem" ? "Fix: " : "Tip: ") + (i.where || "")),
    el("small", {style: "display:block;white-space:pre-wrap"}, i.message + (i.fix ? " " + i.fix : ""))));

  function show(r, asked) {
    const kids = [];
    if (asked) kids.push(el("p", {class: "help", style: "white-space:pre-wrap"}, el("b", {}, "You: "), asked));
    if (r.mode === "check") {
      const probs = r.issues.filter(i => i.level === "problem");
      kids.push(el("div", {class: "note " + (probs.length ? "warn" : "ok")}, el("div", {},
        el("b", {}, probs.length ? probs.length + " thing" + (probs.length === 1 ? "" : "s") + " to fix. " : "No errors found. "), r.summary || "")));
    } else if (r.mode === "suggest") {
      kids.push(el("div", {class: "note ok"}, el("div", {}, r.summary || (r.issues.length ? "Here are some ideas." : "I could not find anything worth changing."))));
    } else if (r.answer) {
      kids.push(el("div", {class: "note"}, el("div", {style: "white-space:pre-wrap"}, r.answer)));
    }
    if (r.ai_error) kids.push(el("p", {class: "help"}, r.mode === "check" ? "Only the basic checks ran. " + r.ai_error : r.ai_error));
    if (r.issues.length) kids.push(el("div", {class: "list", style: "margin-top:10px"}, [...r.issues.filter(i => i.level === "problem"), ...r.issues.filter(i => i.level !== "problem")].map(issueRow)));
    if (r.ai && !r.ai_error) kids.push(el("p", {class: "help"}, "Answered by " + r.ai + ". Nothing was changed."));
    out.prepend(el("div", {style: "margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--line, rgba(128,128,128,.25))"}, kids));
    bClear.hidden = false;
  }

  async function go(mode, btn) {
    let ctx;
    try { ctx = getCtx() || {}; } catch (e) { ctx = {}; }
    const question = q.value.trim();
    if (mode === "ask" && !question) { q.focus(); return; }
    lock(true, btn, mode === "check" ? "Checking..." : mode === "suggest" ? "Thinking..." : "Asking...");
    const wait = el("p", {class: "dim small"}, el("span", {class: "spin"}), " Your AI Task is reading it. This can take up to a minute.");
    out.prepend(wait);
    try {
      const r = await api("ask", Object.assign({}, ctx, {mode, question, history}));
      wait.remove();
      if (!r || r.ok === false || r.error) { out.prepend(el("div", {class: "note bad"}, el("div", {}, (r && r.error) || "That did not work."))); return; }
      show(r, mode === "ask" ? question : question ? "(" + (mode === "check" ? "check" : "suggest") + ") " + question : "");
      if (mode === "ask") { history.push({q: question, a: r.answer}); q.value = ""; }
    } catch (e) {
      wait.remove(); out.prepend(el("div", {class: "note bad"}, el("div", {}, "That did not work: " + e)));
    } finally { lock(false, btn); }
  }

  bCheck.onclick = () => go("check", bCheck);
  bSug.onclick = () => go("suggest", bSug);
  bAsk.onclick = () => go("ask", bAsk);
  q.addEventListener("keydown", ev => { if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); go("ask", bAsk); } });
  bClear.onclick = () => { out.replaceChildren(); history.length = 0; bClear.hidden = true; };

  host.replaceChildren(
    el("p", {class: "dim small", style: "margin-bottom:10px"}, opts.intro || "Your AI Task reads what is on this page. Check it for errors, ask for ideas, or type your own question. Nothing is changed or run."),
    el("div", {class: "row", style: "flex-wrap:wrap;gap:8px"}, bCheck, bSug),
    el("label", {class: "l", style: "margin-top:14px"}, "Ask a question"),
    q,
    el("div", {class: "row", style: "margin-top:8px"}, bAsk, bClear),
    out);
}

/* Builds the whole card (title and all) and puts it in `parent`; use when the page has no ready-made spot for it. */
function askAICard(parent, getCtx, opts) {
  const body = el("div", {});
  parent.append(el("section", {class: "card", id: "askcard"}, el("div", {class: "ch"}, el("h2", {}, "✨ Check & ask AI")), body));
  askAI(body, getCtx, opts);
}

// FDE-Mode conversation view (tab "대화"). Left: the persona ↔ me chat room (typed turns stay drafts until [저장]).
// Centre: me ↔ Claude, view only — the user keeps typing in the Claude Code session they opened. Right: notes.
// Top: "놓친 것". Everything comes from fde.db through /api/{chat,convo,notes,gaps,drafts}; polled every 2 s.
"use strict";

const CV = (() => {
  const SP = { persona: "인물", me: "나" };
  const RSTATUS = { new: "분석 대기", analyzing: "분석 중", done: "분석 끝", undone: "취소됨" };
  const LONG = 1400;          // characters before a Claude reply folds
  const s = {
    mounted: false, timer: null, root: null, chatCursor: 0, convoCursor: 0, rCursor: "", rounds: {}, utt: {},
    drafts: [], speaker: "persona", notes: [], note: null, dirty: false, pending: null, editing: null,
    decisions: {}, pane: "chat", busy: false, gaps: null, search: "", saveBanner: "", stash: {},
  };

  const time = (ts) => (ts || "").slice(11, 16);
  const CHAT_EMPTY = "아직 인터뷰 대화가 없습니다. Claude Code에 <code>&gt;&gt;</code>로 붙여넣거나, 아래에서 인물·나를 골라 적은 뒤 [저장]하세요.";
  const CLAUDE_EMPTY = "아직 기록된 대화가 없습니다. 이 열은 보기만 합니다 — FDE가 켜진 Claude Code 세션에 말을 걸면 여기에 쌓입니다.";
  function emptyState(box, sel, msg) {
    const has = box.querySelector(sel), e = box.querySelector(":scope > .cv-empty");
    if (has && e) e.remove();
    if (!has && !e) box.insertAdjacentHTML("afterbegin", `<p class="muted cv-empty">${msg}</p>`);
  }
  const atBottom = (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  async function call(method, path, body) {
    const r = await fetch(path, { method, headers: WRITE_HEADERS, body: JSON.stringify({ project: state.project, ...(body || {}) }) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(data.error || String(r.status)); e.status = r.status; throw e; }
    return data;
  }

  // ---------- layout ----------
  function mount(view) {
    s.mounted = true; s.root = view; s.chatCursor = 0; s.convoCursor = 0; s.rCursor = ""; s.rounds = {}; s.utt = {};
    s.decisions = {}; s.gapsKey = ""; s.notesKey = ""; s.openGap = null; s.afterDiscard = null; s.stagesKey = ""; s.openStage = null;
    view.innerHTML = `
      <section class="cv" aria-label="대화 화면">
        <div class="cv-gaps" id="cv-gaps" role="region" aria-label="놓친 것"><span class="cv-gaps-title">놓친 것</span><span class="muted">불러오는 중…</span></div>
        <div class="cv-stages" id="cv-stages" role="region" aria-label="단계 지도" hidden></div>
        <div class="cv-gap-list" id="cv-gap-list" hidden></div>
        <div class="cv-bar">
          <input id="cv-search" type="search" placeholder="검색 ( / )" aria-label="대화 검색" autocomplete="off">
          <div class="cv-panes" role="group" aria-label="보이는 열">
            <button type="button" data-pane="chat" aria-pressed="true">인물 ↔ 나</button>
            <button type="button" data-pane="claude" aria-pressed="false" title="보기만 · 입력은 Claude Code에서">나 ↔ Claude</button>
            <button type="button" data-pane="notes" aria-pressed="false">메모</button>
          </div>
        </div>
        <div class="cv-cols" data-pane="chat">
          <section class="cv-col cv-chat" aria-label="인물과 나의 대화">
            <header class="cv-head"><b>인물 ↔ 나</b><span class="muted" id="cv-chat-count"></span></header>
            <div class="cv-scroll" id="cv-chat" role="log" aria-live="off" tabindex="0"></div>
            <div class="cv-save-banner" id="cv-banner" hidden></div>
            <div class="cv-split" id="cv-split" hidden></div>
            <form class="cv-compose" id="cv-compose" autocomplete="off">
              <div class="cv-who" role="group" aria-label="말한 사람">
                <button type="button" data-sp="persona" aria-pressed="true">인물</button>
                <button type="button" data-sp="me" aria-pressed="false">나</button>
              </div>
              <textarea id="cv-input" rows="2" placeholder="말을 적고 Enter · 줄바꿈 Shift+Enter · 통째 붙여넣기 가능" aria-label="인터뷰 턴 입력 (Enter 추가, Shift+Enter 줄바꿈, 대화를 통째로 붙여넣으면 나눠서 확인)"></textarea>
              <div class="cv-compose-actions">
                <button type="submit" class="small">턴 추가</button>
                <button type="button" class="small primary" id="cv-save-drafts" disabled>저장</button>
              </div>
            </form>
          </section>
          <section class="cv-col cv-claude" aria-label="나와 Claude의 대화(보기만)">
            <header class="cv-head"><b>나 ↔ Claude</b><span class="muted">보기만 · 입력은 Claude Code에서</span></header>
            <div class="cv-scroll" id="cv-claude" role="log" aria-live="off" tabindex="0"></div>
          </section>
          <section class="cv-col cv-notes" aria-label="메모">
            <details class="cv-roles" id="cv-roles" hidden><summary>의뢰 유형·역할 지도 <span class="chip warn" id="cv-roles-unknown"></span></summary><div id="cv-roles-body"></div></details>
            <header class="cv-head"><b>메모</b><button type="button" class="small" id="cv-new-note">새 메모</button></header>
            <div class="cv-note-list" id="cv-note-list"></div>
            <div class="cv-editor" id="cv-editor">
              <input id="cv-note-title" placeholder="제목" aria-label="메모 제목">
              <textarea id="cv-note-body" placeholder="인터뷰 중 메모 — [저장]을 눌러야 저장됩니다 (⌘S / Ctrl+S)" aria-label="메모 내용"></textarea>
              <div class="cv-links" id="cv-links"></div>
              <input id="cv-link-add" placeholder="근거 연결: U012 입력 후 Enter" aria-label="메모에 연결할 발화 번호(U…)" autocomplete="off">
              <div class="cv-checks" id="cv-checks"></div>
              <div class="row cv-editor-actions"><span class="cv-dirty" id="cv-dirty" aria-live="polite"></span><span class="spacer"></span>
                <button type="button" class="small primary" id="cv-save-note">저장</button></div>
            </div>
          </section>
        </div>
      </section>`;
    s.stick = { chat: true, claude: true };
    bind();
    layout();
    const st = s.stash[state.project];
    delete s.stash[state.project];
    if (st) { openNote(st.note); $("#cv-note-title").value = st.title; $("#cv-note-body").value = st.body; setDirty(st.dirty); $("#cv-input").value = st.input; }
    else newNote();
    const pane = location.hash.split(":")[1];   // #convo:claude opens a column directly on a narrow screen
    if (["chat", "claude", "notes"].includes(pane)) showPane(pane);
    poll(true);
    s.timer = setInterval(() => { if ($("#auto").checked) poll(false); }, 2000);
  }

  // Leaving the tab keeps an unsaved note and an unsent turn in memory; coming back to the same project restores them.
  function unmount() {
    if (s.mounted && (s.dirty || $("#cv-input").value.trim())) {
      s.stash[state.project] = { note: s.note, title: $("#cv-note-title").value, body: $("#cv-note-body").value,
                                 dirty: s.dirty, input: $("#cv-input").value };
    }
    clearInterval(s.timer); s.timer = null; s.mounted = false;
  }

  function follow() {          // keep a column at the bottom while the user has not scrolled up in it
    for (const [k, id] of [["chat", "#cv-chat"], ["claude", "#cv-claude"]]) {
      const box = $(id);
      if (box && s.stick[k] && box.clientHeight) box.scrollTop = box.scrollHeight;
    }
  }

  function layout() {   // the view fills the window below the sticky header; each column scrolls on its own
    const cv = s.root && s.root.querySelector(".cv");
    if (cv) cv.style.setProperty("--cv-top", `${Math.max(0, cv.getBoundingClientRect().top + window.scrollY)}px`);
  }

  // ---------- polling ----------
  async function poll(first) {
    if (s.busy || !s.mounted) return;
    s.busy = true;
    try {
      const [chat, cv, gaps, stages] = await Promise.all([
        api("chat", { since: s.chatCursor }), api("convo", { since: s.convoCursor, rsince: s.rCursor }), api("gaps"),
        api("stages").catch(() => ({ off: true }))]);
      if (!s.mounted) return;
      s.first = first;
      renderGaps(gaps);
      renderStages(stages);
      renderChat(chat, first);
      renderClaude(cv, first);
      layout();
      follow();
      if (first || !s.dirty) await loadNotes();
    } catch (e) {
      if (first) $("#cv-chat").innerHTML = `<p class="muted cv-empty">불러오지 못했습니다: ${esc(e.message)}</p>`;
    } finally { s.busy = false; }
  }

  // ---------- left: persona ↔ me ----------
  function bubble(u, reflected) {
    const side = u.speaker === "I" ? "me" : "persona";
    const n = reflected[u.id] || 0;
    const mark = u.speaker === "P" ? `<span class="cv-ref ${n ? "" : "none"}">${n ? `카드·요구 ${n}` : "아직 반영 안 됨"}</span>` : "";
    return `<div class="cv-msg ${side}${s.first ? "" : " cv-new"}" id="u-${esc(u.id)}" data-u="${esc(u.id)}" data-text="${esc(u.text)}">
      <div class="cv-bubble">${esc(u.text)}</div>
      <div class="cv-meta"><span class="cv-uid">${esc(u.id)}</span>${mark}<span class="cv-time">${esc(time(u.created_at))}</span>
        <button type="button" class="cv-link-btn" tabindex="-1" data-link="${esc(u.id)}" aria-label="${esc(u.id)}를 메모 근거로 연결">메모에 연결</button></div></div>`;
  }

  function separator(r) {
    const st = RSTATUS[r.status] || r.status || "";
    const src = r.source === "web" ? `<span class="chip acc">웹 저장</span>` : "";
    return `<div class="cv-round" id="round-${esc(r.id)}" data-round="${esc(r.id)}" role="heading" aria-level="3">
      <span><b>${esc(r.id)}</b> · ${esc(time(r.created_at))} · 발화 <span class="num">${esc(r.count)}</span> · <span class="cv-rstatus st-${esc(r.status)}">${esc(st)}</span> ${src}</span></div>`;
  }

  function systemBlock(r, utts) {
    const label = r.kind === "brief" ? "문제 설명" : "메모(붙여넣기)";
    return `<details class="cv-system" id="u-${esc((utts[0] || {}).id || r.id)}"><summary>${esc(label)} ${esc(r.id)} · ${esc(time(r.created_at))}</summary>
      ${utts.map((u) => `<p>${esc(u.text)}</p>`).join("")}</details>`;
  }

  function renderChat(d, first) {
    const box = $("#cv-chat");
    for (const r of d.rounds) {                 // status / count changes of rounds already on screen
      const old = s.rounds[r.id];
      s.rounds[r.id] = r;
      const el = document.getElementById(`round-${r.id}`);
      if (old && el && (old.status !== r.status || old.count !== r.count)) el.outerHTML = separator(r);
    }
    const byRound = {};
    for (const u of d.utterances) { s.utt[u.id] = u; (byRound[u.round] ||= []).push(u); }
    if (first) box.innerHTML = "";
    let html = "";
    for (const rid of Object.keys(byRound)) {
      const r = s.rounds[rid] || { id: rid, status: "", count: byRound[rid].length };
      const utts = byRound[rid];
      if (r.kind && r.kind !== "transcript") { html += systemBlock(r, utts); continue; }
      if (!document.getElementById(`round-${rid}`)) html += separator(r);
      html += utts.map((u) => bubble(u, d.reflected)).join("");
    }
    const draftsEl = document.getElementById("cv-drafts");
    if (html && draftsEl) draftsEl.insertAdjacentHTML("beforebegin", html); else if (html) box.insertAdjacentHTML("beforeend", html);
    for (const [uid, n] of Object.entries(d.reflected)) {     // 반영 표시 can change for old turns
      const el = box.querySelector(`#u-${CSS.escape(uid)} .cv-ref`);
      if (el && s.utt[uid] && s.utt[uid].speaker === "P") {
        const txt = n ? `카드·요구 ${n}` : "아직 반영 안 됨";
        if (el.textContent !== txt) { el.textContent = txt; el.classList.toggle("none", !n); }
      }
    }
    s.chatCursor = d.cursor;
    $("#cv-chat-count").textContent = `발화 ${Object.keys(d.reflected).length}`;
    renderDrafts(d.drafts);
    emptyState(box, ".cv-msg, .cv-system", CHAT_EMPTY);
    applySearch();
  }

  function renderDrafts(drafts, toBottom) {
    const same = JSON.stringify(drafts) === JSON.stringify(s.drafts) && document.getElementById("cv-drafts");
    s.drafts = drafts;
    $("#cv-save-drafts").disabled = !drafts.length;
    $("#cv-save-drafts").textContent = drafts.length ? `저장 (${drafts.length}턴)` : "저장";
    if (same && s.editing === null) return;
    const box = $("#cv-chat");
    const a = document.activeElement, keep = a && a.closest && a.closest("#cv-drafts") &&
      Object.entries(a.dataset).find(([k]) => k.startsWith("draft"));   // re-focus the same control after redrawing
    document.getElementById("cv-drafts")?.remove();
    if (!drafts.length) { emptyState(box, ".cv-msg, .cv-system", CHAT_EMPTY); return; }
    const rows = drafts.map((d, i) => {
      const side = d.speaker === "me" ? "me" : "persona";
      const body = s.editing === d.id
        ? `<textarea class="cv-draft-edit" data-edit="${d.id}" aria-label="임시 턴 고치기">${esc(d.text)}</textarea>
           <div class="row"><button type="button" class="small primary" data-draft-ok="${d.id}">고침</button><button type="button" class="small" data-draft-cancel>취소(Esc)</button></div>`
        : `<div class="cv-bubble">${esc(d.text)}</div>`;
      return `<div class="cv-msg ${side} draft" data-draft-row="${d.id}">${body}
        <div class="cv-meta"><span class="chip warn">임시</span>
          <button type="button" class="cv-mini" data-draft-sp="${d.id}" aria-label="화자 바꾸기">${SP[d.speaker]} ⇄</button>
          <button type="button" class="cv-mini" data-draft-edit="${d.id}">고치기</button>
          <button type="button" class="cv-mini" data-draft-up="${i}" ${i ? "" : "disabled"} aria-label="위로">↑</button>
          <button type="button" class="cv-mini" data-draft-down="${i}" ${i < drafts.length - 1 ? "" : "disabled"} aria-label="아래로">↓</button>
          <button type="button" class="cv-mini" data-draft-del="${d.id}">지우기</button></div></div>`;
    }).join("");
    box.insertAdjacentHTML("beforeend", `<div id="cv-drafts" class="cv-drafts" aria-label="저장 전 임시 턴">
      <div class="cv-round draft-head"><span>저장 전 ${drafts.length}턴 — [저장]하면 새 라운드가 됩니다</span></div>${rows}</div>`);
    if (toBottom) { s.stick.chat = true; follow(); }
    const ed = box.querySelector(".cv-draft-edit");
    if (ed) { ed.focus(); ed.setSelectionRange(ed.value.length, ed.value.length); }
    else if (keep) {
      let [k, v] = keep;
      if (k === "draftUp") v = String(Number(v) - 1);        // the turn moved: follow it
      else if (k === "draftDown") v = String(Number(v) + 1);
      const attr = "data-" + k.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
      (box.querySelector(`[${attr}="${CSS.escape(v)}"]:not([disabled])`) || box.querySelector("#cv-drafts button"))?.focus();
    }
  }

  async function addTurn(text) {
    if (!text.trim()) return;
    try { renderDrafts(await call("POST", "/api/drafts", { speaker: s.speaker, text }), true); $("#cv-input").value = ""; }
    catch (e) { toast("턴을 넣지 못했습니다: " + e.message); }
  }

  async function splitPaste(text) {
    try {
      const { turns } = await call("POST", "/api/drafts", { split: text });
      if (!turns.length) { toast("나눌 수 있는 턴이 없습니다"); return; }
      s.pending = turns;
      renderSplit();
    } catch (e) { toast("붙여넣기를 나누지 못했습니다: " + e.message); }
  }

  function renderSplit() {
    const box = $("#cv-split");
    if (!s.pending) { box.hidden = true; box.innerHTML = ""; return; }
    const unsure = s.pending.filter((t) => !t.sure).length;
    box.hidden = false;
    box.innerHTML = `<div class="row"><b>붙여넣은 대화 ${s.pending.length}턴</b><span class="muted">화자를 확인하세요${unsure ? ` · 불확실 ${unsure}` : ""}</span></div>
      <ol class="cv-split-list">${s.pending.map((t, i) => `<li class="${t.sure ? "" : "unsure"}">
        <button type="button" class="cv-mini" data-split-sp="${i}" aria-label="화자 바꾸기">${SP[t.speaker]} ⇄</button>
        <span>${esc(t.label ? t.label + ": " : "")}${esc(t.text)}</span></li>`).join("")}</ol>
      <div class="row"><button type="button" class="small primary" data-split-ok>임시 턴으로 넣기</button><button type="button" class="small" data-split-cancel>취소</button></div>`;
  }

  async function saveDrafts() {
    if (!s.drafts.length) return;
    const btn = $("#cv-save-drafts");
    btn.disabled = true;
    try {
      const r = await call("POST", "/api/drafts/save", { ids: s.drafts.map((d) => d.id) });
      if (r.round) {
        const b = $("#cv-banner");
        b.hidden = false;
        b.innerHTML = `<b>${esc(r.round)} 저장됨</b> — 터미널(Claude Code)에서 아무 말이나 보내면 분석이 시작됩니다.
          <button type="button" class="small" data-copy="진행">'진행' 복사</button><button type="button" class="cv-mini" data-banner-close aria-label="닫기">✕</button>`;
        toast(`${r.round} 저장 — 발화 ${r.count}개`);
      } else toast("저장할 턴이 없습니다(다른 창에서 이미 저장됨)");
      await poll(false);
    } catch (e) { toast("저장하지 못했습니다: " + e.message); btn.disabled = false; }
  }

  // ---------- centre: me ↔ Claude (view only) ----------
  function claudeItem(c) {
    if (c.kind === "paste") {
      return `<div class="cv-msg me" data-ts="${esc(c.ts)}"><button type="button" class="cv-chip-paste" data-goto-round="${esc(c.round || "")}"
        ${c.round ? "" : "disabled"}>${esc(c.text)}</button><div class="cv-meta"><span class="cv-time">${esc(time(c.ts))}</span></div></div>`;
    }
    if (c.role === "me") {
      return `<div class="cv-msg me" data-ts="${esc(c.ts)}" data-text="${esc(c.text)}"><div class="cv-bubble">${esc(c.text)}</div>
        <div class="cv-meta"><span class="cv-time">${esc(time(c.ts))}</span></div></div>`;
    }
    const long = c.text.length > LONG || c.text.split("\n").length > 30;
    return `<div class="cv-msg claude ${long ? "folded" : ""}" data-ts="${esc(c.ts)}" data-text="${esc(c.text)}">
      ${long ? `<div class="cv-fold-top"><button type="button" class="cv-mini" data-fold aria-expanded="false">접기</button></div>` : ""}
      <div class="cv-bubble md-wrap">${md(c.text)}</div>
      <div class="cv-meta"><span class="cv-who-label">Claude</span><span class="cv-time">${esc(time(c.ts))}</span>
        ${long ? `<button type="button" class="cv-mini" data-fold aria-expanded="false">더 보기</button>` : ""}</div></div>`;
  }

  function reportItem(r) {
    return `<div class="cv-card report" data-ts="${esc(r.finished_at)}" data-text="${esc(r.text)}" id="report-${esc(r.id)}">
      <div class="row"><span class="chip acc">라운드 보고서</span><b>${esc(r.round || r.id)}</b><span class="cv-time">${esc(time(r.finished_at))}</span></div>
      <details open><summary>펼치기 / 접기</summary>${md(r.text)}</details></div>`;
  }

  function decisionItem(d) {
    const done = !["new", "asked"].includes(d.status);
    const opts = (d.options || []).map((o) => `<li><span>${esc(o)}${o === d.recommended ? ' <span class="chip good">추천</span>' : ""}</span>
      <button type="button" class="small" data-copy="${esc(o)}" aria-label="선택지 '${esc(o)}' 복사">복사</button></li>`).join("");
    return `<div class="cv-card decision ${done ? "done" : ""}" id="dec-${esc(d.id)}" data-ts="${esc(d.created_at)}" data-text="${esc(d.title + " " + (d.context || ""))}">
      <div class="row">${chip(d.grade, d.grade === "D1" ? "bad" : "warn")}<b>${esc(d.id)}</b>${chip(done ? "답함" : "답 기다림", done ? "good" : "warn")}<span class="cv-time">${esc(time(d.created_at))}</span></div>
      <div class="q">${esc(d.title)} <button type="button" class="small" data-copy="${esc(d.title)}" aria-label="질문 복사">복사</button></div>
      ${d.context ? `<div class="meta">${esc(d.context)}</div>` : ""}<ul class="cv-opts">${opts}</ul>
      ${d.answer ? `<div class="meta">답: <b>${esc(d.answer)}</b></div>` : ""}</div>`;
  }

  function insertByTime(box, html, ts) {        // keep the centre column in time order
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    const el = t.content.firstElementChild;
    if (!s.first) el.classList.add("cv-new");
    const after = [...box.children].reverse().find((c) => (c.dataset.ts || "") <= (ts || ""));
    if (after) after.after(el); else box.prepend(el);
  }

  function renderClaude(d, first) {
    const box = $("#cv-claude");
    if (first) box.innerHTML = "";
    for (const c of d.items) insertByTime(box, claudeItem(c), c.ts);
    for (const r of d.reports) if (!document.getElementById(`report-${r.id}`)) insertByTime(box, reportItem(r), r.finished_at);
    for (const x of d.decisions) {
      const key = `${x.status}|${x.answer || ""}`;
      if (s.decisions[x.id] === key) continue;
      s.decisions[x.id] = key;
      document.getElementById(`dec-${x.id}`)?.remove();
      insertByTime(box, decisionItem(x), x.created_at);
    }
    s.convoCursor = d.cursor; s.rCursor = d.rcursor || s.rCursor;
    emptyState(box, ".cv-msg, .cv-card", CLAUDE_EMPTY);
    applySearch();
  }

  // ---------- right: notes ----------
  async function loadNotes() {
    const notes = await api("notes");
    const key = JSON.stringify(notes) + (s.note && s.note.id);
    if (key === s.notesKey) return;
    s.notesKey = key; s.notes = notes;
    const list = $("#cv-note-list");
    list.innerHTML = s.notes.map((n) => `<button type="button" class="cv-note-item ${s.note && s.note.id === n.id ? "on" : ""}" data-note="${n.id}">
      <b>${esc(n.title || "(제목 없음)")}</b><span class="cv-time">${esc(time(n.updated_at))}</span>
      ${n.checks.length ? `<span class="chip warn">기록에 없음 ${n.checks.length}</span>` : ""}</button>`).join("")
      || `<p class="muted cv-empty">아직 메모가 없습니다. 아래에 적고 [저장]하세요. 메모는 인물 발화로 쓰이지 않습니다.</p>`;
  }

  function newNote() { openNote({ id: null, title: "", body: "", links: [], checks: [], updated_at: null, rev: 0 }); }

  function openNote(n) {
    s.note = { ...n, links: [...(n.links || [])] };
    $("#cv-note-title").value = n.title || "";
    $("#cv-note-body").value = n.body || "";
    setDirty(false);
    renderLinks(); renderChecks(n.checks || []);
    document.querySelectorAll(".cv-note-item").forEach((b) => b.classList.toggle("on", Number(b.dataset.note) === n.id));
  }

  function setDirty(v) {
    s.dirty = v;
    $("#cv-dirty").textContent = v ? "● 저장 안 됨" : (s.note && s.note.id ? "저장됨" : "");
    $("#cv-dirty").classList.toggle("on", v);
  }

  function renderLinks() {
    $("#cv-links").innerHTML = (s.note.links || []).map((u) => `<span class="chip acc">${esc(u)}
      <button type="button" class="cv-x" data-unlink="${esc(u)}" aria-label="${esc(u)} 연결 빼기">✕</button></span>`).join("")
      || `<span class="muted">근거 연결 없음 — 말풍선의 [메모에 연결]</span>`;
  }

  function renderChecks(checks) {
    $("#cv-checks").innerHTML = checks.length
      ? `<div class="cv-warn">대화·자료에 없는 것: ${checks.map((c) => `<b>${esc(c.text)}</b>(${esc(c.kind)})`).join(", ")}</div>` : "";
  }

  async function saveNote() {
    const n = s.note;
    const body = { title: $("#cv-note-title").value, body: $("#cv-note-body").value, links: n.links };
    if (!body.title.trim() && !body.body.trim()) { toast("빈 메모는 저장하지 않습니다"); return; }
    try {
      const saved = n.id ? await call("PUT", "/api/notes", { ...body, id: n.id, base: n.rev })
                         : await call("POST", "/api/notes", body);
      openNote(saved);
      await loadNotes();
      toast(saved.checks.length ? `저장 — 기록에 없는 것 ${saved.checks.length}개` : "메모 저장");
    } catch (e) {
      if (e.status === 409) {
        $("#cv-checks").innerHTML = `<div class="cv-warn">다른 창에서 먼저 저장했습니다. 내 내용은 그대로 있습니다.
          <button type="button" class="small" data-note-copy>새 메모로 저장</button></div>`;
      } else toast("메모를 저장하지 못했습니다: " + e.message);
    }
  }

  function linkUtterance(uid) {
    if (!s.note.links.includes(uid)) { s.note.links.push(uid); setDirty(true); renderLinks(); }
    toast(`메모에 근거 연결: ${uid}`);
    if (window.matchMedia("(max-width: 899px)").matches) showPane("notes");
  }

  // ---------- top: 놓친 것 ----------
  const GAP = [
    ["unasked_high", "안 물어본 높음 카드"], ["asked_unanswered", "답 못 받은 질문"], ["unreflected", "반영 안 된 발화"],
    ["ungrounded_notes", "근거 없는 메모"], ["domain_words", "근거 없는 업종 낱말"]];

  function renderGaps(g) {
    const key = JSON.stringify(g);
    if (key === s.gapsKey) return;   // re-render only on change (keeps keyboard focus on the strip)
    s.gapsKey = key; s.gaps = g;
    $("#cv-gaps").innerHTML = `<span class="cv-gaps-title">놓친 것</span>` + GAP.map(([k, label]) => {
      const n = g.counts[k] || 0;
      return `<button type="button" class="cv-gap ${n ? "on" : ""}" data-gap="${k}" ${n ? "" : "disabled"} aria-expanded="false">${label} <b class="num">${n}</b></button>`;
    }).join("");
    if (s.openGap) showGap(s.openGap, true);
  }

  // ---------- 단계 지도 띠 + 의뢰 유형·역할 패널 ----------
  const SMARK = { done: "완료", partial: "빈칸 있음", open: "아직", reopened: "다시 열림" };
  function renderStages(m) {
    const band = $("#cv-stages"), roles = $("#cv-roles");
    if (!m || m.off) { band.hidden = true; roles.hidden = true; return; }
    const key = JSON.stringify(m);
    if (key === s.stagesKey) return;   // re-render only on change (keeps focus)
    s.stagesKey = key; s.stages = m;
    band.hidden = false;
    band.innerHTML = `<span class="cv-gaps-title">단계</span>` + m.stages.map((x) => {
      const n = x.gaps.length;
      return `<button type="button" class="cv-stage st-${x.status}${x.current ? " now" : ""}" data-stage="${x.id}" aria-expanded="false"
        aria-label="${x.id} ${esc(x.name)} — ${SMARK[x.status] || ""}${n ? `, 빈칸 ${n}` : ""}${x.current ? ", 지금 단계" : ""}${x.reopened ? `, 다시 연 횟수 ${x.reopened}` : ""}">
        <b>${x.id}</b> ${esc(x.name)} <span class="cv-stage-mark" aria-hidden="true">${esc(x.mark)}</span>${n && x.status !== "done" ? ` <b class="num">${n}</b>` : ""}</button>`;
    }).join("");
    if (s.openStage) showStage(s.openStage, true);
    const e = m.engagement || {}, unknown = (m.roles || []).filter((r) => r.who === "모름" && r.needed).length;
    roles.hidden = false;
    $("#cv-roles-unknown").textContent = unknown ? `모름 ${unknown}` : "";
    const u = (ids) => (ids || []).map((id) => `<button type="button" class="cv-mini" data-goto-u="${esc(id)}">${esc(id)}</button>`).join("");
    $("#cv-roles-body").innerHTML = `<div class="cv-types">${(e.types || []).map((t) => `<div><b>${esc(t.code)}</b> ${esc(t.label)} ${chip(t.confidence, t.confidence === "확실" ? "good" : t.confidence === "가능성 높음" ? "acc" : "warn")} ${u(t.evidence)}</div>`).join("")}</div>
      <table class="cv-role-table"><tbody>${(m.roles || []).map((r) => {
        const miss = r.who === "모름" || r.who === "확인 필요";
        return `<tr class="${miss ? (r.needed ? "unknown" : "optional") : ""}"><th scope="row" title="${esc(r.title || r.name)}">${esc(r.name)}</th>
        <td>${miss ? (r.needed ? `<b>${esc(r.who)}</b>` : '<span class="muted">필요하면 확인</span>') : (r.confidence ? chip(r.confidence, "warn") + " " : "") + esc(r.who)} ${u(r.evidence)}</td></tr>`;
      }).join("")}</tbody></table>
      ${(e.types || []).filter((t) => t.new).map((t) => `<div class="cv-warn">새 유형 신호: <b>${esc(t.code)}</b> ${esc(t.label)} ${u(t.evidence)} — 확인 필요</div>`).join("")}
      ${Object.entries(m.must_know || {}).map(([c, items]) => `<div class="meta"><b>${esc(c)} 꼭 알아야 할 것</b>: ${items.map(esc).join(" · ")}</div>`).join("")}`;
  }

  function showStage(id, keep) {
    const list = $("#cv-gap-list");
    if (!keep && s.openStage === id) { s.openStage = null; list.hidden = true; document.querySelectorAll(".cv-stage").forEach((b) => b.setAttribute("aria-expanded", "false")); return; }
    s.openStage = id; s.openGap = null;
    document.querySelectorAll(".cv-gap").forEach((b) => b.setAttribute("aria-expanded", "false"));
    document.querySelectorAll(".cv-stage").forEach((b) => b.setAttribute("aria-expanded", String(b.dataset.stage === id)));
    const x = ((s.stages || {}).stages || []).find((y) => y.id === id);
    if (!x) return;
    const gaps = x.gaps.map((g) => `<div class="cv-gap-item"><b>빈칸</b> ${esc(g.text)} <span class="muted">— ${esc(g.why)}</span></div>`).join("");
    const cards = x.cards.map((c) => `<button type="button" class="cv-gap-item" data-goto-card="${esc(c.id)}"><b>${esc(c.id)}</b> ${chip(c.status)} ${esc(c.text)}
      ${(c.evidence || []).map((e) => `<span class="cv-uid">${esc(e)}</span>`).join(" ")}</button>`).join("");
    list.hidden = false;
    list.innerHTML = `<div class="cv-gap-item"><b>${esc(x.id)} ${esc(x.name)}</b> · ${esc(SMARK[x.status] || "")}${x.reopened ? ` · 다시 연 횟수 ${x.reopened}` : ""}</div>`
      + (gaps || `<div class="cv-gap-item muted">빈칸 없음</div>`) + cards;
  }

  function showGap(k, keep) {
    s.openStage = null; document.querySelectorAll(".cv-stage").forEach((b) => b.setAttribute("aria-expanded", "false"));
    const list = $("#cv-gap-list");
    if (!keep && s.openGap === k) { s.openGap = null; list.hidden = true; return; }
    s.openGap = k;
    const items = (s.gaps || {})[k] || [];
    document.querySelectorAll(".cv-gap").forEach((b) => b.setAttribute("aria-expanded", String(b.dataset.gap === k)));
    const row = (it) => {
      if (k === "unasked_high" || k === "asked_unanswered") return `<button type="button" class="cv-gap-item" data-goto-card="${esc(it.id)}"><b>${esc(it.id)}</b> ${esc(it.text)}</button>`;
      if (k === "unreflected") return `<button type="button" class="cv-gap-item" data-goto-u="${esc(it.id)}"><b>${esc(it.id)}</b> ${esc(it.text)}</button>`;
      if (k === "ungrounded_notes") return `<button type="button" class="cv-gap-item" data-goto-note="${it.id}"><b>${esc(it.title || "(제목 없음)")}</b> ${esc(it.checks.map((c) => c.text).join(", "))}</button>`;
      return `<div class="cv-gap-item"><b>근거 없는 업종 낱말: ${esc(it.word)}</b> ${it.ids.map((id) => `<button type="button" class="cv-mini" data-goto-item="${esc(id)}">${esc(id)}</button>`).join(" ")}</div>`;
    };
    list.hidden = !items.length;
    list.innerHTML = items.slice(0, 60).map(row).join("");
  }

  // ---------- search / panes ----------
  function applySearch() {
    const q = s.search.trim().toLowerCase();
    s.root.querySelectorAll(".cv-scroll [data-text]").forEach((el) => {
      const hit = !q || (el.dataset.text || "").toLowerCase().includes(q);
      el.classList.toggle("dim", !hit);
      el.classList.toggle("hit", !!q && hit);
    });
  }

  function showPane(p) {
    s.pane = p;
    s.root.querySelector(".cv-cols").dataset.pane = p;
    s.root.querySelectorAll(".cv-panes button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pane === p)));
    follow();   // a column that was hidden opens at its bottom (unless the user scrolled it up before)
  }

  function gotoEl(id, pane) {
    if (pane) showPane(pane);
    const el = document.getElementById(id);
    if (!el) { toast("화면에 아직 없습니다"); return; }
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1600);
  }

  // ---------- events ----------
  function bind() {
    const root = s.root;
    const input = $("#cv-input");
    $("#cv-compose").addEventListener("submit", (e) => { e.preventDefault(); addTurn(input.value); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); addTurn(input.value); }
      else if (e.key === "Escape" && !e.isComposing) { input.value = ""; }
    });
    for (const [k, id] of [["chat", "#cv-chat"], ["claude", "#cv-claude"]]) {
      const box = $(id);
      box.addEventListener("scroll", () => { if (box.clientHeight) s.stick[k] = atBottom(box); }, { passive: true });
    }
    $("#cv-link-add").addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      const uid = e.target.value.trim().toUpperCase();
      if (/^U\d+$/.test(uid)) { linkUtterance(uid); e.target.value = ""; } else toast("U로 시작하는 발화 번호를 적어 주세요(예: U012)");
    });
    input.addEventListener("paste", (e) => {
      const text = e.clipboardData ? e.clipboardData.getData("text") : "";
      if (text.split("\n").filter((l) => l.trim()).length >= 3) { e.preventDefault(); splitPaste(text); }
    });
    $("#cv-note-title").addEventListener("input", () => setDirty(true));
    $("#cv-note-body").addEventListener("input", () => setDirty(true));
    $("#cv-search").addEventListener("input", (e) => { s.search = e.target.value; applySearch(); });
    $("#cv-search").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.target.value = ""; s.search = ""; applySearch(); e.target.blur(); } });
    root.addEventListener("click", onClick);
    root.addEventListener("keydown", (e) => {
      const ed = e.target.closest && e.target.closest(".cv-draft-edit");
      if (!ed) return;
      if (e.key === "Escape" && !e.isComposing) { e.preventDefault(); s.editing = null; renderDrafts(s.drafts, false); }
      else if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); finishEdit(Number(ed.dataset.edit), ed.value); }
    });
    window.addEventListener("resize", layout);
  }

  async function finishEdit(id, text) {
    s.editing = null;
    try { renderDrafts(await call("PUT", "/api/drafts", { id, text }), false); } catch (e) { toast("고치지 못했습니다: " + e.message); }
  }

  async function onClick(e) {
    const t = e.target.closest("button, [data-goto-round]");
    if (!t) return;
    const d = t.dataset;
    try {
      if (d.sp) { s.speaker = d.sp; s.root.querySelectorAll(".cv-who button").forEach((b) => b.setAttribute("aria-pressed", String(b === t))); $("#cv-input").focus(); }
      else if (t.id === "cv-save-drafts") await saveDrafts();
      else if (d.draftSp) { const x = s.drafts.find((y) => y.id === Number(d.draftSp)); renderDrafts(await call("PUT", "/api/drafts", { id: x.id, speaker: x.speaker === "me" ? "persona" : "me" }), false); }
      else if (d.draftEdit) { s.editing = Number(d.draftEdit); renderDrafts(s.drafts, false); }
      else if (d.draftOk) { const ed = s.root.querySelector(".cv-draft-edit"); await finishEdit(Number(d.draftOk), ed.value); }
      else if ("draftCancel" in d) { s.editing = null; renderDrafts(s.drafts, false); }
      else if (d.draftDel) renderDrafts(await call("DELETE", `/api/drafts?id=${Number(d.draftDel)}`, {}), false);
      else if (d.draftUp || d.draftDown) {
        const i = Number(d.draftUp ?? d.draftDown), j = d.draftUp !== undefined ? i - 1 : i + 1;
        const order = s.drafts.map((x) => x.id); [order[i], order[j]] = [order[j], order[i]];
        renderDrafts(await call("PUT", "/api/drafts", { order }), false);
      }
      else if (d.splitSp !== undefined) { const x = s.pending[Number(d.splitSp)]; x.speaker = x.speaker === "me" ? "persona" : "me"; x.sure = true; renderSplit(); }
      else if ("splitOk" in d) {   // the confirmed split stays on screen until the server has it
        renderDrafts(await call("POST", "/api/drafts", { turns: s.pending }), true); s.pending = null; renderSplit(); $("#cv-input").focus();
      }
      else if ("splitCancel" in d) { s.pending = null; renderSplit(); }
      else if ("bannerClose" in d) $("#cv-banner").hidden = true;
      else if (d.link) linkUtterance(d.link);
      else if (d.unlink) { s.note.links = s.note.links.filter((u) => u !== d.unlink); setDirty(true); renderLinks(); }
      else if (t.id === "cv-save-note") await saveNote();
      else if (t.id === "cv-new-note") guardDiscard(newNote);
      else if (d.note) guardDiscard(() => openNote(s.notes.find((n) => n.id === Number(d.note))));
      else if ("discardSave" in d) { const go = s.afterDiscard; s.afterDiscard = null; await saveNote(); if (!s.dirty && go) go(); }
      else if ("discardDrop" in d) { const go = s.afterDiscard; s.afterDiscard = null; setDirty(false); if (go) go(); }
      else if ("discardCancel" in d) { s.afterDiscard = null; renderChecks(s.note.checks || []); }
      else if ("noteCopy" in d) { s.note = { ...s.note, id: null, updated_at: null, rev: 0 }; await saveNote(); }
      else if ("fold" in d) {   // both toggles (top: only while open; bottom) follow the state
        const m = t.closest(".cv-msg"); const open = m.classList.toggle("folded") === false;
        m.querySelectorAll("[data-fold]").forEach((b) => { b.textContent = open ? "접기" : "더 보기"; b.setAttribute("aria-expanded", String(open)); });
        if (!open) m.scrollIntoView({ block: "nearest" });
      }
      else if (d.gotoRound !== undefined && d.gotoRound) gotoEl(`round-${d.gotoRound}`, "chat");
      else if (d.gap) showGap(d.gap);
      else if (d.stage) showStage(d.stage);
      else if (d.gotoU) gotoEl(`u-${d.gotoU}`, "chat");
      else if (d.gotoNote) { showPane("notes"); guardDiscard(() => openNote(s.notes.find((n) => n.id === Number(d.gotoNote)))); }
      else if (d.gotoCard) goTab("cards", `card-${d.gotoCard}`);
      else if (d.gotoItem) {
        const id = d.gotoItem;
        if (id.startsWith("Q")) goTab("cards", `card-${id}`); else if (id.startsWith("R")) goTab("requirements", `req-${id}`);
        else goTab("build");
      }
      else if (d.pane) showPane(d.pane);
    } catch (err) { toast("실패: " + err.message); }
  }

  // Leaving an unsaved note asks inline (no browser dialog): save and go on, drop it, or stay.
  function guardDiscard(go) {
    if (!s.dirty) { go(); return; }
    s.afterDiscard = go;
    $("#cv-checks").innerHTML = `<div class="cv-warn" role="alert">저장하지 않은 메모가 있습니다.
      <button type="button" class="small primary" data-discard-save>저장하고 넘어가기</button>
      <button type="button" class="small" data-discard-drop>버리기</button><button type="button" class="small" data-discard-cancel>그대로 두기</button></div>`;
  }

  document.addEventListener("keydown", (e) => {
    if (!s.mounted) return;
    if (e.key === "Escape" && s.pending && !e.isComposing) { s.pending = null; renderSplit(); $("#cv-input").focus(); return; }
    if ((e.metaKey || e.ctrlKey) && (e.key === "s" || e.key === "S" || e.code === "KeyS")) {
      e.preventDefault();
      const inNotes = e.target.closest && e.target.closest(".cv-notes");
      if (inNotes || (s.dirty && !s.drafts.length)) saveNote(); else if (s.drafts.length) saveDrafts(); else if (s.dirty) saveNote();
    } else if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
      const tag = (e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
      e.preventDefault(); $("#cv-search").focus();
    }
  });
  window.addEventListener("beforeunload", (e) => {
    const kept = Object.keys(s.stash).length;   // an unsaved note kept while another tab or project is open
    if (kept || (s.mounted && (s.dirty || ($("#cv-input") && $("#cv-input").value.trim())))) { e.preventDefault(); e.returnValue = ""; }
  });

  return { mount, unmount, get mounted() { return s.mounted; } };
})();

// FDE-Mode dashboard. Read-only view of .claude/fde-mode/fde.db, plus question-card status buttons.
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { project: "", tab: "overview", timer: null };
const TOKEN = (document.querySelector('meta[name="fde-token"]') || {}).content || "";
const WRITE_HEADERS = { "Content-Type": "application/json", "X-FDE": "1", "X-FDE-Token": TOKEN };

function md(text) {
  // Small, safe markdown: headings, lists, quotes, bold, code, tables.
  const lines = esc(text || "").split("\n");
  let out = [], inTable = false, inList = false, inCode = false;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/_(.+?)_/g, "<i>$1</i>");
  for (const raw of lines) {
    const l = raw;
    if (l.startsWith("```")) { out.push(inCode ? "</pre>" : "<pre>"); inCode = !inCode; continue; }
    if (inCode) { out.push(l); continue; }
    if (/^\|.*\|\s*$/.test(l)) {
      if (/^\|\s*-/.test(l)) continue;
      const cells = l.split("|").slice(1, -1).map((c) => `<td>${inline(c.trim())}</td>`).join("");
      if (!inTable) { out.push("<table>"); inTable = true; }
      out.push(`<tr>${cells}</tr>`); continue;
    } else if (inTable) { out.push("</table>"); inTable = false; }
    if (/^\s*[-*] /.test(l)) { if (!inList) { out.push("<ul>"); inList = true; } out.push(`<li>${inline(l.replace(/^\s*[-*] /, ""))}</li>`); continue; }
    else if (inList) { out.push("</ul>"); inList = false; }
    const h = l.match(/^(#{1,4}) (.*)$/);
    if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (l.startsWith("&gt; ")) { out.push(`<blockquote>${inline(l.slice(5))}</blockquote>`); continue; }
    out.push(l.trim() ? `<p>${inline(l)}</p>` : "");
  }
  if (inTable) out.push("</table>"); if (inList) out.push("</ul>"); if (inCode) out.push("</pre>");
  return `<div class="md">${out.join("\n")}</div>`;
}

async function api(name, params = {}) {
  const q = new URLSearchParams({ project: state.project, ...params });
  const r = await fetch(`/api/${name}?${q}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.json();
}

function toast(msg) { const t = $("#toast"); t.textContent = msg; clearTimeout(t._h); t._h = setTimeout(() => (t.textContent = ""), 1600); }
function chip(text, cls = "") { return text ? `<span class="chip ${cls}">${esc(text)}</span>` : ""; }
function confCls(c) { return c === "확실" ? "good" : c === "가능성 높음" ? "acc" : "warn"; }
function impCls(i) { return i === "높음" ? "bad" : i === "중간" ? "warn" : ""; }

async function loadProjects() {
  const list = await fetch("/api/projects").then((r) => r.json());
  const sel = $("#project");
  sel.innerHTML = list.map((p) => `<option value="${esc(p.root)}">${esc(p.name)} — ${esc(p.root)}</option>`).join("");
  const saved = new URLSearchParams(location.search).get("project")
    || (() => { try { return localStorage.getItem("fde.project"); } catch { return null; } })();
  state.project = list.find((p) => p.root === saved) ? saved : (list[0] || {}).root || "";
  sel.value = state.project;
}

const VIEWS = {
  async overview() {
    const o = await api("overview");
    const c = o.counts, tl = o.timeline || {};
    $("#phase").textContent = `${o.state.phase} ${o.state.phase_ko} · R${String(o.state.round).padStart(2, "0")} · ${o.state.mode === "on" ? "켜짐" : "꺼짐"}`;
    const kpis = [["발화", c.utterances], ["요구사항(must)", `${c.requirements} (${c.must})`], ["열린 질문", c.open_questions],
      ["답 받은 질문", c.answered_questions], ["대기 결정(D1/D2)", c.pending_decisions], ["가정", c.assumptions],
      ["실행 중 에이전트", c.agents_running], ["완료/실패", `${c.agents_done} / ${c.agents_failed}`], ["구현 작업", `${c.tasks_done}/${c.tasks}`]];
    const ms = Object.entries(tl).filter(([k, v]) => typeof v === "object")
      .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v.at)}</td><td>${v.min_left >= 0 ? v.min_left + "분 남음" : "지남"}</td></tr>`).join("");
    const sw = Object.entries(o.switches || {}).map(([k, v]) => chip(`${k} ${v ? "on" : "off"}`, v ? "" : "warn")).join(" ");
    $("#tab-convo").hidden = (o.switches || {}).conversation_view === false;
    const runs = (o.runs || []).map((r) => `<tr><td>${esc(r.id)}</td><td>${esc(r.pipeline)}</td><td>${esc(r.stage)} ${esc(r.stage_name)}</td><td>${chip(r.status, r.status === "done" ? "good" : r.status === "failed" ? "bad" : "acc")}</td></tr>`).join("");
    const notes = (o.notifications || []).map((n) => `<tr><td class="muted">${esc((n.ts || "").slice(11, 16))}</td><td>${chip(n.payload?.kind || "")}</td><td>${esc(n.payload?.text || "")}</td></tr>`).join("");
    return `<div class="grid">${kpis.map(([k, v]) => `<div class="panel kpi"><b>${esc(v)}</b><span>${esc(k)}</span></div>`).join("")}</div>
      <div class="split"><div><h2>시간표</h2>${ms ? `<table><tr><th>마일스톤</th><th>시각</th><th>남은 시간</th></tr>${ms}</table>` : '<p class="muted">마감 시각이 설정되지 않았습니다(project.toml [schedule])</p>'}
      <h2>스위치</h2><div class="row">${sw}</div></div>
      <div><h2>최근 알림</h2><table>${notes || '<tr><td class="muted">없음</td></tr>'}</table></div></div>
      <h2>실행(파이프라인)</h2><table><tr><th>실행</th><th>종류</th><th>단계</th><th>상태</th></tr>${runs}</table>`;
  },
  async cards() {
    const d = await api("cards");
    const open = d.questions.filter((q) => ["open", "held"].includes(q.status));
    const done = d.questions.filter((q) => !["open", "held"].includes(q.status));
    const card = (q, i) => {
      const flags = (q.flags || []).map((f) => chip(f, "warn")).join(" ");
      const ev = (q.evidence_text || []).map((e) => `<div class="ev">${esc(e.id)} "${esc(e.text)}"</div>`).join("");
      const ans = (q.answers_text || []).map((e) => `<div class="ev">답 ${esc(e.id)} "${esc(e.text)}"</div>`).join("");
      const mis = (q.flags || []).some((f) => f.includes("불일치"))
        ? `<div class="meta">렌즈: [${esc(q.lens?.confidence)}] · 검증관: [${esc(q.verifier?.confidence)}] ${esc(q.verifier?.why || "")}</div>` : "";
      const cnt = q.counter?.verdict && q.counter.verdict !== "ask" ? `<div class="meta">반론관: ${esc(q.counter.verdict)} — ${esc(q.counter.why || "")}</div>` : "";
      return `<div class="card ${i < 5 && q.status === "open" ? "lead" : ""} ${flags ? "flag" : ""}" id="card-${esc(q.id)}">
        <div class="row"><b>${esc(q.id)}</b>${chip(q.confidence, confCls(q.confidence))}${chip("영향 " + q.impact, impCls(q.impact))}
        ${chip(q.bucket === "propose" ? "제안" : q.bucket === "hold" ? "보류" : "질문", "acc")}${chip(q.status)} ${flags}</div>
        <div class="q">${esc(q.text)}</div>
        <div class="meta">답에 따라 바뀌는 것: ${esc(q.decision_at_stake || "-")}</div>${ev}${mis}${cnt}${ans}
        <div class="row" style="margin-top:6px">
          <button class="small primary" data-copy="${esc(q.text)}">복사</button>
          ${["asked", "assumed", "dropped", "held", "open"].map((s) => `<button class="small" data-q="${esc(q.id)}" data-s="${s}">${{ asked: "물어봄", assumed: "가정으로", dropped: "버림", held: "보류", open: "다시 열기" }[s]}</button>`).join("")}
        </div></div>`;
    };
    const asm = (d.assumptions || []).map((a) => `<tr><td>${esc(a.id)}</td><td>${chip(a.status)}</td><td>${esc(a.text)}</td><td class="muted">${esc(a.reason)}</td></tr>`).join("");
    const drop = (d.dropped || []).map((x) => `<tr><td class="muted">${esc(x.round)}</td><td>${esc((x.lens_agents || [x.agent]).map((a) => (a || "").replace("fde-", "")).join(", "))}</td><td>${esc(x.gap)}</td><td>${chip(x.status)}</td></tr>`).join("");
    return `<h2>지금 물어볼 질문 (${open.length})</h2>${open.map(card).join("") || '<p class="muted">열린 질문이 없습니다</p>'}
      <details><summary>물어봤거나 정리된 질문 (${done.length})</summary>${done.map(card).join("")}</details>
      <h2>가정</h2><table><tr><th>id</th><th>상태</th><th>내용</th><th>이유</th></tr>${asm || '<tr><td class="muted">없음</td></tr>'}</table>
      <h2>억지·중복으로 탈락한 후보 (잘못 버렸는지 확인용)</h2><table><tr><th>라운드</th><th>렌즈</th><th>빈틈</th><th>판정</th></tr>${drop || '<tr><td class="muted">없음</td></tr>'}</table>`;
  },
  async decisions() {
    const rows = await api("decisions");
    return `<p class="muted">결정은 메인 대화에서 선택지로 묻습니다. 여기서는 상태만 봅니다.</p><table><tr><th>id</th><th>등급</th><th>상태</th><th>결정</th><th>선택지 / 추천</th><th>답</th></tr>
      ${rows.map((d) => `<tr><td>${esc(d.id)}</td><td>${chip(d.grade, d.grade === "D1" ? "bad" : d.grade === "D2" ? "warn" : "")}</td><td>${chip(d.status)}</td>
      <td><b>${esc(d.title)}</b><div class="meta">${esc(d.context)}</div></td><td>${(d.options || []).map((o) => esc(o)).join("<br>")}<div class="meta">추천: ${esc(d.recommended)}</div></td><td>${esc(d.answer || "")}</td></tr>`).join("")}</table>`;
  },
  async reports() {
    const list = await api("reports");
    return list.map((r) => `<h2>${esc(r.id)} <span class="muted">${esc((r.finished_at || "").slice(11, 16))}</span></h2>${md(r.text)}`).join("") || '<p class="muted">아직 보고서가 없습니다</p>';
  },
  async requirements() {
    const d = await api("requirements");
    const pr = { must: 0, should: 1, could: 2 };
    const reqs = d.requirements.sort((a, b) => (pr[a.priority] ?? 3) - (pr[b.priority] ?? 3));
    return `<table><tr><th>id</th><th>우선</th><th>유형</th><th>요구사항</th><th>상태</th><th>확신</th><th>실현</th><th>근거</th></tr>
      ${reqs.map((r) => `<tr id="req-${esc(r.id)}"><td>${esc(r.id)}${r.frozen ? " 🔒" : ""}</td><td>${chip(r.priority, r.priority === "must" ? "bad" : "")}</td><td>${esc(r.type)}</td>
      <td>${esc(r.statement)}${(r.conflict || []).length ? `<div class="meta">충돌: ${esc(r.conflict.join(", "))}</div>` : ""}</td><td>${chip(r.status)}${r.confirmed ? chip("확인됨", "good") : ""}</td>
      <td>${chip(r.confidence, confCls(r.confidence))}</td><td>${chip(r.feasibility, r.feasibility === "불가" ? "bad" : r.feasibility === "주의" ? "warn" : "good")}<div class="meta">${esc(r.feasibility_note || "")}</div></td>
      <td class="meta">${esc((r.evidence || []).join(", "))}</td></tr>`).join("")}</table>
      <h2>수용 테스트</h2><table><tr><th>id</th><th>요구사항</th><th>입력</th><th>기대</th><th>실패 기준</th></tr>
      ${d.tests.map((t) => `<tr><td>${esc(t.id)}</td><td>${esc((t.requirements || []).join(", "))}</td><td>${esc(t.input)}</td><td>${esc(t.expected)}</td><td>${esc(t.fail_if)}</td></tr>`).join("")}</table>
      <h2>위험</h2><table>${d.risks.map((r) => `<tr><td>${esc(r.id)}</td><td>${chip(r.severity)}</td><td>${esc(r.text)}</td><td class="muted">${esc(r.source)}</td></tr>`).join("") || '<tr><td class="muted">없음</td></tr>'}</table>`;
  },
  async persona() {
    const d = await api("persona");
    const m = d.metrics || {}, P = m.persona || {}, I = m.interviewer || {};
    const bars = (obj) => { const mx = Math.max(1, ...Object.values(obj || {}).map(Number)); return Object.entries(obj || {}).map(([k, v]) => `<div class="row"><span style="width:110px">${esc(k)}</span><div class="bar" style="flex:1"><i style="width:${(100 * v) / mx}%"></i></div><span class="muted">${esc(v)}</span></div>`).join(""); };
    const areas = Object.fromEntries(Object.entries(P.by_area || {}).map(([k, v]) => [k, v.count]));
    return `<div class="split"><div><h2>인물 모델 (persona.md)</h2>${d.persona_md ? md(d.persona_md) : '<p class="muted">아직 없습니다(토론 라운드에서 인물 이해 본부장이 씁니다)</p>'}</div>
      <div><h2>패턴 지표 ${esc(d.metrics_round || "")}</h2>
      <div class="panel"><h3>주제별 언급</h3>${bars(areas)}<h3>자주 쓴 표지어</h3>${bars(P.marker_words)}
      <h3>시간 표현</h3><div class="meta">${esc((P.time_mentions || []).map((t) => `${t.id}: ${t.hits.join(", ")}`).join(" / ") || "-")}</div>
      <h3>등장한 다른 사람</h3>${bars(P.others_mentioned)}</div>
      <h2>인터뷰어(나) 지표</h2><div class="panel"><h3>영역 커버리지</h3>${bars(I.coverage)}
      <div class="meta">아직 안 건드린 영역: <b>${esc((I.untouched_areas || []).join(", ") || "없음")}</b></div>
      <h3>질문 형식</h3>${bars(I.qtype)}
      <div class="meta">모호한 답 뒤 후속 질문 비율: ${esc(I.followup_rate ?? "-")} · 말한 양(나:인물) ${esc(I.talk_ratio_i_to_p ?? "-")} · 해결책 먼저 제시 ${esc((I.solution_first || []).length)}회</div></div></div></div>
      <h2>개인화 표 (인물 패턴 → 봇 동작)</h2>${d.personalization_map ? md(d.personalization_map) : '<p class="muted">아직 없습니다</p>'}
      <h2>사용 환경 (환경 분석가)</h2>${d.environment_md ? md(d.environment_md) : '<p class="muted">아직 없습니다(문제 설명·빠른 분석에서 환경 분석가가 씁니다)</p>'}
      <h2>전달 형태 (패키징 전략가)</h2>${d.packaging_md ? md(d.packaging_md) : '<p class="muted">아직 없습니다</p>'}`;
  },
  async debates() {
    const d = await api("debates");
    const items = d.debates.map((x) => `<div class="card"><div class="row"><b>${esc(x.id)}</b>${chip(x.status, x.status === "ruled" ? "good" : "acc")}</div>
      <div class="q">${esc(x.topic)}</div>${(x.positions || []).map((p) => `<div class="ev"><b>${esc((p.by || "").replace("fde-", ""))}</b> [${esc(p.mode)}${p.stance ? " · " + esc(p.stance) : ""}] ${esc(p.text)}</div>`).join("")}
      ${x.ruling ? `<div class="meta"><b>중재:</b> ${esc(x.ruling)}</div>` : ""}${(x.minority || []).map((m) => `<div class="meta">소수 의견: ${esc(m.by || "")} ${esc(m.text || m)}</div>`).join("")}</div>`).join("");
    return `<h2>쟁점</h2>${items || '<p class="muted">아직 토론 라운드가 없습니다</p>'}
      <h2>소수 의견</h2>${d.minority_md ? md(d.minority_md) : '<p class="muted">없음</p>'}
      <h2>입장 변화</h2>${d.stance_md ? md(d.stance_md) : '<p class="muted">없음</p>'}
      ${(d.minutes || []).map((m) => `<h2>회의록 ${esc(m.name)}</h2>${md(m.text)}`).join("")}`;
  },
  async data() {
    const d = await api("data");
    return `<table><tr><th>id</th><th>파일</th><th>종류</th><th>상태</th><th>행</th><th>메모</th></tr>${d.assets.map((a) => `<tr><td>${esc(a.id)}</td><td>${esc(a.path)}</td><td>${esc(a.kind)}</td><td>${chip(a.status)}</td><td>${esc(a.rows ?? "")}</td><td class="muted">${esc(a.notes || a.report || "")}</td></tr>`).join("") || '<tr><td class="muted">받은 데이터가 없습니다</td></tr>'}</table>
      <h2>데이터 본부 보고</h2><table>${d.reports.map((r) => `<tr><td>${esc(r.agent.replace("fde-", ""))}</td><td>${esc(r.mode)}</td><td>${esc(r.summary)}</td></tr>`).join("")}</table>`;
  },
  async build() {
    const d = await api("build");
    return `<h2>구현 작업</h2><table><tr><th>id</th><th>조각</th><th>작업</th><th>담당</th><th>파일</th><th>상태</th></tr>${d.tasks.map((t) => `<tr><td>${esc(t.id)}</td><td>${esc(t.notes?.slice ?? "")}</td><td>${esc(t.title)}</td><td>${esc((t.owner || "").replace("fde-", ""))}</td><td class="meta">${esc((t.files || []).join(", "))}</td><td>${chip(t.status, t.status === "done" ? "good" : t.status === "blocked" ? "bad" : "acc")}</td></tr>`).join("") || '<tr><td class="muted">핵심 동결 뒤에 생깁니다</td></tr>'}</table>
      <h2>릴리스</h2><table>${d.releases.map((r) => `<tr><td>${esc(r.tag)}</td><td>${r.good ? chip("정상", "good") : chip("미확인", "warn")}</td><td class="meta">${esc(r.created_at)}</td><td>${esc(r.notes)}</td></tr>`).join("") || '<tr><td class="muted">없음</td></tr>'}</table>
      <h2>기술 결정 (ADR)</h2><table>${d.adrs.map((a) => `<tr><td>${esc(a.id)}</td><td><b>${esc(a.title)}</b><div class="meta">${esc(a.decision)}</div></td><td>${chip(a.grade)}</td><td>${chip(a.status)}</td></tr>`).join("") || '<tr><td class="muted">없음</td></tr>'}</table>
      <h2>검증 못 함 (${(d.unverified || []).length})</h2><table>${(d.unverified || []).map((u) => `<tr><td>${esc(u.run)}</td><td>${esc(u.agent.replace("fde-", ""))}</td><td>${esc(u.item)}</td></tr>`).join("") || '<tr><td class="muted">없음</td></tr>'}</table>
      <h2>리뷰·배포·QA</h2><table>${d.qa.map((q) => `<tr><td>${esc(q.run)}</td><td>${esc(q.agent.replace("fde-", ""))}</td><td>${esc(q.mode)}</td><td>${esc(q.summary)}</td></tr>`).join("")}</table>
      <details><summary>spec.md</summary>${md(d.spec_md)}</details>`;
  },
  async org() {
    const d = await api("org");
    const byDiv = {};
    for (const a of d.roster) (byDiv[a.division_ko] ||= []).push(a);
    const st = {}; for (const x of d.dispatches) st[x.agent] = st[x.agent] || x;
    const roster = Object.entries(byDiv).map(([div, list]) => `<div class="panel"><h3>${esc(div)}</h3>${list.map((a) => {
      const last = st[a.name]; const s = last ? last.status : "";
      return `<div class="row"><span>${a.head ? "★ " : ""}${esc(a.ko)}</span>${chip(a.effort, a.effort === "xhigh" ? "acc" : "")}${a.quick ? chip("빠른") : ""}${a.independent ? chip("독립석", "warn") : ""}${s ? chip(s, s === "done" ? "good" : s === "failed" ? "bad" : "acc") : ""}</div>`;
    }).join("")}</div>`).join("");
    const rows = d.dispatches.slice(0, 120).map((x) => `<tr><td class="meta">${esc((x.issued_at || "").slice(11, 19))}</td><td>${esc(x.run)}</td><td>${esc(x.stage)}</td><td>${esc(x.ko)}</td><td>${esc(x.mode)}</td><td>${chip(x.status, x.status === "done" ? "good" : x.status === "failed" ? "bad" : "acc")}${x.attempts > 1 ? chip("재시도", "warn") : ""}</td><td class="meta">${esc(x.summary || x.error || "")}</td></tr>`).join("");
    return `<h2>조직</h2><div class="grid">${roster}</div><h2>디스패치</h2><table><tr><th>시각</th><th>실행</th><th>단계</th><th>에이전트</th><th>모드</th><th>상태</th><th>요약</th></tr>${rows}</table>`;
  },
  async transcript() {
    const rows = await api("transcript");
    const who = { I: "나", P: "인물", B: "문제", N: "메모", "?": "?" };
    return rows.map((u) => `<div class="utt ${esc(u.speaker)}"><span class="muted">${esc(u.id)}</span><span class="who">${esc(who[u.speaker] || u.speaker)}</span>
      <div>${esc(u.text)}<div class="row">${(u.tags || []).map((t) => chip(t)).join("")}${u.area ? chip(u.area, "acc") : ""}${u.qtype ? chip(u.qtype) : ""}${u.parse_conf < 0.7 ? chip("화자 불확실", "warn") : ""}</div></div></div>`).join("") || '<p class="muted">아직 대화가 없습니다</p>';
  },
  async convo() { return ""; },  // rendered by convo.js (CV), never through this string path
  async events() {
    const rows = await api("events");
    return `<table><tr><th>시각</th><th>종류</th><th>대상</th><th>내용</th></tr>${rows.map((e) => `<tr><td class="meta">${esc((e.ts || "").slice(11, 19))}</td><td>${esc(e.kind)}</td><td>${esc(e.ref)}</td><td class="meta">${esc(typeof e.payload === "string" ? e.payload : JSON.stringify(e.payload))}</td></tr>`).join("")}</table>`;
  },
};

async function render() {
  if (!state.project) { $("#view").innerHTML = '<p class="muted">FDE를 켠 프로젝트가 없습니다. Claude Code에서 /fde-mode 를 실행하세요.</p>'; return; }
  if (state.tab === "convo") {           // the conversation view keeps its own DOM and 2-second polling (convo.js)
    if (!CV.mounted) { state.last = ""; CV.mount($("#view")); }
    VIEWS.overview().catch(() => {});
    $("#clock").textContent = new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return;
  }
  if (CV.mounted) CV.unmount();
  try {
    const html = await VIEWS[state.tab]();
    if (state.tab === "convo") return;   // tab switched while loading
    if (html !== state.last) {          // re-render only when something changed (keeps open <details> and selections)
      const y = window.scrollY;
      $("#view").innerHTML = html;
      window.scrollTo(0, y);
      state.last = html;
    }
    if (state.tab !== "overview") VIEWS.overview().catch(() => {});
  } catch (e) { $("#view").innerHTML = `<p class="muted">불러오지 못했습니다: ${esc(e.message)}</p>`; }
  const now = new Date(); $("#clock").textContent = now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// Switch tab; with `anchor`, scroll to that element once the view has rendered and flash it.
async function goTab(tab, anchor) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  state.tab = tab; state.last = ""; window.scrollTo(0, 0);
  await render();
  const el = anchor && document.getElementById(anchor);
  if (el) { el.scrollIntoView({ block: "center" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1600); }
}

document.addEventListener("click", async (ev) => {
  const t = ev.target;
  if (t.matches(".tabs button")) {
    goTab(t.dataset.tab);
  } else if (t.dataset.copy !== undefined) {
    try { await navigator.clipboard.writeText(t.dataset.copy); toast("복사했습니다"); } catch { toast("복사 실패 — 직접 선택해 주세요"); }
  } else if (t.dataset.q) {
    const r = await fetch("/api/question", { method: "POST", headers: WRITE_HEADERS,
      body: JSON.stringify({ project: state.project, id: t.dataset.q, status: t.dataset.s }) });
    toast(r.ok ? `${t.dataset.q} → ${t.textContent}` : "바꾸지 못했습니다"); state.last = ""; render();
  }
});
$("#project").addEventListener("change", (e) => {
  if (CV.mounted) CV.unmount();   // a new project starts a fresh conversation view (an unsaved note stays with its project)
  state.project = e.target.value; state.last = ""; try { localStorage.setItem("fde.project", state.project); } catch {} render();
});
$("#auto").addEventListener("change", (e) => { clearInterval(state.timer); if (e.target.checked) state.timer = setInterval(render, 4000); });

// A link can open a tab directly: http://127.0.0.1:28420/#convo
(async () => {
  await loadProjects();
  const tab = location.hash.slice(1).split(":")[0];
  if (VIEWS[tab] || tab === "convo") await goTab(tab); else await render();
  state.timer = setInterval(render, 4000);
})();

"""Copy-pasted chat → numbered utterances.

The user copies the persona chat by hand, so every paste can overlap the last
one, miss a reply, or lose speaker names. This module does the deterministic
part (save the raw text untouched, split, map speakers, drop the overlap, number
the utterances) and marks low-confidence lines so the scribe agent only has to
fix what code could not decide.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from fde_mode import db
from fde_mode.lexicon import question_type
from fde_mode.state import Ctx, set_state
from fde_mode.util import iso, jaccard, norm, write_text

EXPLICIT = {
    "transcript": (">>", ">>>", "[대화]", "대화:", "#대화", "::t"),
    "brief": (">>brief", ">>문제", ">>브리프", "[문제]", "[브리프]", "문제:", "#문제"),
    "note": (">>note", ">>메모", "[메모]", "메모:", "#메모"),
}

KAKAO_EXPORT = re.compile(r"^\s*\[(?P<label>[^\]]{1,20})\]\s*\[(?:오전|오후)?\s*\d{1,2}:\d{2}\]\s*(?P<text>.*)$")
LABEL_COLON = re.compile(r"^\s*(?P<label>[^\s:：/\.\d][^:：/]{0,14}?)\s*[:：]\s*(?P<text>.*)$")
TIMESTAMP_ONLY = re.compile(r"^\s*(?:\d{4}[.\-/]\s*\d{1,2}[.\-/]\s*\d{1,2}\.?\s*)?(?:(?:오전|오후|AM|PM|am|pm)\s*)?"
                            r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\s*$")
READ_MARK = re.compile(r"^\s*(?:읽음|1|안읽음|전송됨|Sent|Read)\s*$")
URLISH = re.compile(r"https?://", re.I)
SENTENCE_END = re.compile(r"[.?!？。…]$|(?:요|다|죠|까|네|군|지)$")
# Claude Code wraps a bracketed terminal paste as <pasted_content id="…"> … </pasted_content>: not the user's words
PASTE_WRAPPER = re.compile(r"</?pasted_content(?:\s[^>]*)?>")
HANGUL = re.compile(r"[가-힣]")


def unwrap(text: str) -> str:
    return PASTE_WRAPPER.sub("", text or "")


def _explicit(stripped: str, strict: bool = False) -> tuple[str, str, float, str] | None:
    """The marker on the first line. `strict` (the marker found inside a paste): the whole line must be the marker and
    ">>>" never counts — a pasted REPL session (">>> import …") or a quote ("> > …") is not an interview."""
    first, _, rest = stripped.partition("\n")
    head = first.strip()
    for kind in ("brief", "note", "transcript"):  # longer markers first (">>brief" before ">>")
        for mark in EXPLICIT[kind]:
            if strict and (mark == ">>>" or head.lower() != mark.lower()):
                continue
            if head == mark or head.lower().startswith(mark.lower()):
                remainder = head[len(mark):].strip()
                body = (remainder + "\n" + rest).strip() if remainder else rest.strip()
                return kind, body, 1.0, f"explicit:{mark}"
    return None


def missed_paste(prompt: str) -> bool:
    """A paste (Claude Code's wrapper) or a marker line that `classify` did not save — the user must be told."""
    lines = [ln.strip() for ln in unwrap(prompt).splitlines() if ln.strip()]
    marks = {m.lower() for ms in EXPLICIT.values() for m in ms} - {">>>"}
    if any(ln.lower() in marks for ln in lines):  # a marker line on its own that saved nothing (empty, or not first)
        return True
    # a wrapped paste of mostly Korean sentences (a brief or an interview without a marker) — not code or a log
    return bool(PASTE_WRAPPER.search(prompt or "")) and len(lines) >= 2 and \
        sum(1 for ln in lines if HANGUL.search(ln)) * 2 >= len(lines)


def classify(prompt: str, cfg: dict, auto: bool = True) -> tuple[str, str, float, str]:
    """Return (kind, body, score, reason). kind: transcript | brief | note | none."""
    raw = (prompt or "").replace("\r\n", "\n").replace("\r", "\n")
    text = unwrap(raw)
    stripped = text.lstrip()
    if not stripped or stripped.startswith("/"):
        return "none", "", 0.0, "empty-or-command"
    m = PASTE_WRAPPER.search(raw)
    got = _explicit(stripped, strict=raw.lstrip().startswith("<pasted_content"))  # first line typed, or pasted
    if got is None and m and not m.group(0).startswith("</"):  # words typed before the paste, the marker inside it
        got = _explicit(unwrap(raw[m.end():]).lstrip(), strict=True)
    if got:
        return got
    if not auto:
        return "none", "", 0.0, "auto-off"
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 4:
        return "none", "", 0.0, "too-short"
    aliases = set(cfg.get("interview", {}).get("interviewer_aliases", [])) | set(
        cfg.get("interview", {}).get("persona_aliases", []))
    labels = Counter()
    kakao = 0
    for ln in lines:
        m = KAKAO_EXPORT.match(ln)
        if m:
            kakao += 1
            labels[m.group("label").strip()] += 1
            continue
        if URLISH.search(ln):
            continue
        m = LABEL_COLON.match(ln)
        if m and len(m.group("label").strip()) <= 15:
            labels[m.group("label").strip()] += 1
        elif ln.strip() in aliases:
            labels[ln.strip()] += 1
    repeated = {k: v for k, v in labels.items() if v >= 2 or k in aliases}
    if kakao >= 2:
        return "transcript", text.strip(), 0.95, "kakao-export"
    if len(repeated) >= 2 and sum(repeated.values()) >= 3:
        return "transcript", text.strip(), 0.85, f"labels:{','.join(list(repeated)[:4])}"
    standalone = Counter(ln.strip() for ln in lines if 0 < len(ln.strip()) <= 15 and not SENTENCE_END.search(ln.strip()))
    rep_standalone = {k: v for k, v in standalone.items() if v >= 2}
    if len(rep_standalone) >= 2 and sum(rep_standalone.values()) >= 4:
        return "transcript", text.strip(), 0.75, f"name-lines:{','.join(list(rep_standalone)[:4])}"
    return "none", "", 0.0, "no-speaker-pattern"


def _speaker_for(label: str, cfg: dict, learned: dict[str, str]) -> tuple[str, float]:
    iv = {a.lower() for a in cfg.get("interview", {}).get("interviewer_aliases", [])}
    pv = {a.lower() for a in cfg.get("interview", {}).get("persona_aliases", [])}
    low = label.strip().lower()
    if low in iv:
        return "I", 1.0
    if low in pv:
        return "P", 1.0
    if label in learned:
        return learned[label], 0.85
    return "?", 0.4


def parse(body: str, cfg: dict, learned: dict[str, str] | None = None) -> tuple[list[dict], dict[str, str]]:
    """Split a paste into utterances [{speaker, label, text, conf}].

    speaker: I (interviewer = the user), P (persona), B (brief), N (note), ? (unknown).
    """
    learned = dict(learned or {})
    lines = unwrap(body).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    aliases = set(cfg.get("interview", {}).get("interviewer_aliases", [])) | set(
        cfg.get("interview", {}).get("persona_aliases", []))
    nonempty = [ln.strip() for ln in lines if ln.strip()]
    standalone = Counter(ln for ln in nonempty if 0 < len(ln) <= 15 and not SENTENCE_END.search(ln)
                         and not TIMESTAMP_ONLY.match(ln))
    name_lines = {k for k, v in standalone.items() if v >= 2} | (aliases & set(nonempty)) | (set(learned) & set(nonempty))
    colon_labels = Counter()
    for ln in nonempty:
        m = LABEL_COLON.match(ln)
        if m and not URLISH.search(ln):
            colon_labels[m.group("label").strip()] += 1
    colon_ok = {k for k, v in colon_labels.items() if v >= 2 or k in aliases or k in learned}

    blocks: list[dict] = []
    cur: dict | None = None

    def push(label: str | None, text: str) -> None:
        nonlocal cur
        if cur is not None and not cur["text"].strip() and cur.get("bare"):
            cur["text"] = cur["bare"]
        if cur is not None and (cur["text"].strip() or cur["label"]):
            blocks.append(cur)
        cur = {"label": label, "text": text}

    for raw in lines:
        ln = raw.rstrip()
        s = ln.strip()
        if not s:
            if cur is not None and cur["label"] is None and cur["text"].strip():
                push(None, "")  # blank line ends an unlabeled block
            continue
        if TIMESTAMP_ONLY.match(s) or READ_MARK.match(s):
            if cur is not None and cur["label"] and not cur["text"].strip():
                cur["bare"] = s  # "이름\n10:30": the answer may be just a time or a number (kept if nothing follows)
            continue
        m = KAKAO_EXPORT.match(s)
        if m:
            push(m.group("label").strip(), m.group("text").strip())
            continue
        m = LABEL_COLON.match(s)
        if m and not URLISH.search(s) and m.group("label").strip() in colon_ok:
            push(m.group("label").strip(), m.group("text").strip())
            continue
        if s in name_lines:
            push(s, "")
            continue
        if cur is None:
            cur = {"label": None, "text": s}
        else:
            cur["text"] = (cur["text"] + "\n" + s).strip() if cur["text"] else s
    if cur is not None and not cur["text"].strip() and cur.get("bare"):
        cur["text"] = cur["bare"]
    if cur is not None and cur["text"].strip():
        blocks.append(cur)

    labels_in_order = [b["label"] for b in blocks if b["label"]]
    unknown = [l for l in dict.fromkeys(labels_in_order) if _speaker_for(l, cfg, learned)[0] == "?"]
    if unknown:
        # Guess: the label whose blocks end with a question more often is the interviewer.
        qrate = {}
        for l in unknown:
            texts = [b["text"] for b in blocks if b["label"] == l]
            qrate[l] = sum(1 for t in texts if t.rstrip().endswith(("?", "？"))) / max(1, len(texts))
        known_i = any(_speaker_for(l, cfg, learned)[0] == "I" for l in labels_in_order)
        known_p = any(_speaker_for(l, cfg, learned)[0] == "P" for l in labels_in_order)
        for l in sorted(unknown, key=lambda x: -qrate[x]):
            if not known_i and qrate[l] >= 0.5:
                learned[l] = "I"
                known_i = True
            elif not known_p:
                learned[l] = "P"
                known_p = True
    out: list[dict] = []
    for b in blocks:
        text = b["text"].strip()
        if not text:
            continue
        if b["label"]:
            sp, conf = _speaker_for(b["label"], cfg, learned)
            if sp == "?" and b["label"] in learned:
                sp, conf = learned[b["label"]], 0.6
        else:
            sp, conf = ("I", 0.45) if text.rstrip().endswith(("?", "？")) else ("P", 0.4)
        out.append({"speaker": sp, "label": b["label"] or "", "text": text, "conf": conf})
    return out, learned


def drop_overlap(new: list[dict], tail: list[dict]) -> tuple[list[dict], int]:
    """Remove the prefix of `new` that repeats the end of the stored transcript."""
    if not new or not tail:
        return new, 0
    best = 0
    max_k = min(len(new), len(tail))
    for k in range(max_k, 0, -1):
        a = tail[-k:]
        b = new[:k]
        if all(_same(x["text"], y["text"]) for x, y in zip(a, b)):
            best = k
            break
    kept = new[best:]
    # Long exact repeats anywhere near the tail are also overlap (partial re-copies).
    recent = {norm(u["text"]) for u in tail[-40:] if len(norm(u["text"])) >= 12}
    filtered = [u for u in kept if norm(u["text"]) not in recent]
    return filtered, best + (len(kept) - len(filtered))


def _same(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return len(na) >= 12 and jaccard(a, b) >= 0.9


def stored_tail(ctx: Ctx, n: int = 60) -> list[dict]:
    rows = db.rows(ctx.conn, "SELECT * FROM utterances ORDER BY seq DESC LIMIT ?", (n,))
    return list(reversed(rows))


def ingest(ctx: Ctx, body: str, kind: str = "transcript", source: str = "paste",
           utts: list[dict] | None = None) -> dict[str, Any]:
    """Store one paste as a new round. Returns a summary for the hook/director.

    `utts` (dashboard chat room): turns whose speakers the user already set — stored as given, no parsing and no
    overlap trimming. One write transaction: a paste from the hook and a save from the dashboard never get the
    same round."""
    with db.write_txn(ctx.conn):
        return _ingest(ctx, body, kind, source, utts)


def _ingest(ctx: Ctx, body: str, kind: str, source: str, utts: list[dict] | None) -> dict[str, Any]:
    st = ctx.refresh()
    # never behind an existing round (an older database can carry a lagging state.round): no id or raw file reused
    n = max(int(st.get("round") or 0), int(db.scalar(ctx.conn, "SELECT MAX(n) FROM rounds", default=0))) + 1
    rid = f"R{n:02d}"
    raw_path = ctx.p.inbox / f"{rid}.{kind}.raw.md"
    write_text(raw_path, body if body.endswith("\n") else body + "\n")  # never edited afterwards
    warnings: list[str] = []
    if kind == "transcript" and utts is not None:
        tail = stored_tail(ctx)
        if tail and utts and tail[-1]["speaker"] == "I" and utts[0]["speaker"] == "I":
            warnings.append("직전 질문에 대한 인물 답이 빠졌을 수 있습니다(인터뷰어 발화가 연속)")
    elif kind == "transcript":
        utts, learned = parse(body, ctx.cfg, st.get("speakers") or {})
        tail = stored_tail(ctx)
        utts, dropped = drop_overlap(utts, tail)
        if dropped:
            warnings.append(f"이전 붙여넣기와 겹친 발화 {dropped}개를 뺐습니다")
        if tail and utts and tail[-1]["speaker"] == "I" and utts[0]["speaker"] == "I":
            warnings.append("직전 질문에 대한 인물 답이 빠졌을 수 있습니다(인터뷰어 발화가 연속)")
        low = [u for u in utts if u["conf"] < 0.7]
        if low:
            warnings.append(f"화자가 불확실한 발화 {len(low)}개 → 기록관이 확인합니다")
        set_state(ctx, speakers=learned)
    else:
        sp = "B" if kind == "brief" else "N"
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()] or [body.strip()]
        utts = [{"speaker": sp, "label": kind, "text": p, "conf": 1.0} for p in paras]
    if not utts:
        ctx.event("paste.empty", rid, {"kind": kind})
        return {"round": None, "kind": kind, "count": 0, "warnings": warnings + ["새 발화가 없습니다"]}
    seq0 = int(db.scalar(ctx.conn, "SELECT MAX(seq) FROM utterances", default=0))
    ids = []
    for i, u in enumerate(utts, 1):
        seq = seq0 + i
        uid = f"U{seq:03d}"
        ids.append(uid)
        qtype = question_type(u["text"]) if u["speaker"] == "I" else ""
        db.upsert(ctx.conn, "utterances", {
            "id": uid, "seq": seq, "round": rid, "speaker": u["speaker"], "speaker_label": u["label"],
            "text": u["text"], "tags": "[]", "area": "", "qtype": qtype, "parse_conf": u["conf"],
            "created_at": iso(),
        })
    ctx.conn.execute(  # a plain INSERT: an id that already exists is an error, never a silent merge of two rounds
        "INSERT INTO rounds(id, n, kind, status, raw_path, first_u, last_u, created_at, finished_at, note) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (rid, n, kind, "new", ctx.p.rel(raw_path), ids[0], ids[-1], iso(), None,
         json.dumps({"source": source, "warnings": warnings}, ensure_ascii=False)))
    set_state(ctx, round=n)
    export(ctx)
    ctx.event("paste.ingested", rid, {"kind": kind, "count": len(ids), "warnings": warnings})
    by = Counter(u["speaker"] for u in utts)
    return {"round": rid, "kind": kind, "count": len(ids), "first": ids[0], "last": ids[-1],
            "speakers": dict(by), "low_confidence": sum(1 for u in utts if u["conf"] < 0.7),
            "warnings": warnings, "raw": ctx.p.rel(raw_path)}


def export(ctx: Ctx) -> None:
    """Rewrite transcript.jsonl from the database (the file agents read)."""
    rows = db.rows(ctx.conn, "SELECT id, seq, round, speaker, speaker_label, text, tags, area, qtype, parse_conf "
                             "FROM utterances ORDER BY seq")
    lines = []
    for r in rows:
        r["tags"] = json.loads(r.get("tags") or "[]")
        lines.append(json.dumps(r, ensure_ascii=False))
    write_text(ctx.p.transcript, "\n".join(lines) + ("\n" if lines else ""))


def apply_updates(ctx: Ctx, updates: list[dict]) -> int:
    """Scribe/tagger/topic-classifier corrections: {id, speaker?, text?, tags?, area?, qtype?, split?}."""
    changed = 0
    for u in updates or []:
        uid = u.get("id")
        row = db.one(ctx.conn, "SELECT * FROM utterances WHERE id=?", (uid,))
        if not row:
            continue
        fields: dict[str, Any] = {}
        if u.get("speaker") in ("I", "P", "B", "N", "?"):
            fields["speaker"] = u["speaker"]
            fields["parse_conf"] = 0.95
        if isinstance(u.get("text"), str) and u["text"].strip() and u.get("text_fix_reason"):
            fields["text"] = u["text"].strip()  # only whitespace/merge fixes; scribe never rewrites words
        if isinstance(u.get("tags"), list):
            merged = sorted(set(json.loads(row.get("tags") or "[]")) | set(map(str, u["tags"])))
            fields["tags"] = json.dumps(merged, ensure_ascii=False)
        if isinstance(u.get("area"), str):
            fields["area"] = u["area"]
        if isinstance(u.get("qtype"), str):
            fields["qtype"] = u["qtype"]
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            ctx.conn.execute(f"UPDATE utterances SET {sets} WHERE id=?", (*fields.values(), uid))
            changed += 1
    if changed:
        export(ctx)
    return changed


def utterance_map(ctx: Ctx) -> dict[str, dict]:
    return {r["id"]: r for r in db.rows(ctx.conn, "SELECT * FROM utterances ORDER BY seq")}

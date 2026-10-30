"""Citation check. Deterministic on purpose: an LLM verifier can wave through a
quote that does not exist; a string comparison cannot."""
from __future__ import annotations

import json
import re
from typing import Any

from fde_mode import db
from fde_mode.state import Ctx
from fde_mode.util import containment, norm, write_json

ID_RE = re.compile(r"U\d{3,}")


def _segments(quote: str) -> list[str]:
    parts = re.split(r"…|\.\.\.|\[중략\]|\(중략\)", quote or "")
    return [p.strip() for p in parts if len(norm(p)) >= 4]


def quote_in(quote: str, texts: list[str]) -> bool:
    if not quote or not norm(quote):
        return True  # no quote given → only ids are checked
    segs = _segments(quote) or [quote]
    joined = "\n".join(texts)
    for s in segs:
        ns = norm(s)
        if ns and ns in norm(joined):
            continue
        if containment(s, joined) >= 0.85:
            continue
        return False
    return True


def check_one(utts: dict[str, dict], evidence: list[str] | None, quote: str | None) -> dict[str, Any]:
    ids = [e for e in (evidence or []) if isinstance(e, str)]
    ids = [m for e in ids for m in ID_RE.findall(e)] or ids
    missing = [i for i in ids if i not in utts]
    texts = [utts[i]["text"] for i in ids if i in utts]
    q_ok = quote_in(quote or "", texts) if texts else (not quote)
    ok = not missing and q_ok
    return {"ok": ok, "ids": ids, "missing_ids": missing, "quote_found": q_ok, "no_evidence": not ids}


def run(ctx: Ctx, round_id: str, out_path=None) -> dict[str, Any]:
    utts = {r["id"]: r for r in db.rows(ctx.conn, "SELECT id, text FROM utterances")}
    cands = db.rows(ctx.conn, "SELECT * FROM candidates WHERE round=? AND (merged_into IS NULL OR merged_into='') "
                              "AND kind IN ('question','proposal','assumption','risk')", (round_id,))
    results = {}
    for c in cands:
        ev = json.loads(c.get("evidence") or "[]")
        r = check_one(utts, ev, c.get("quote"))
        results[c["id"]] = r
        ctx.conn.execute("UPDATE candidates SET cite_ok=? WHERE id=?", (1 if r["ok"] else 0, c["id"]))
    summary = {"round": round_id, "checked": len(results), "failed": [k for k, v in results.items() if not v["ok"]],
               "results": results}
    if out_path:
        write_json(out_path, summary)
    return summary

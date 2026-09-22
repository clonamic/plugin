#!/usr/bin/env python3
"""Explicit local prompt-style capture, profiling, and deterministic export."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


SCHEMA_VERSION = 1
ANALYZER_VERSION = "1"
DATABASE_MODE = 0o600
DIRECTORY_MODE = 0o700
BUSY_TIMEOUT_MS = 5000
SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = SKILL_ROOT / "references" / "runtime-contract.json"

TABLES = (
    """
    CREATE TABLE prompt_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        captured_at TEXT NOT NULL,
        source_role TEXT NOT NULL CHECK (source_role = 'user'),
        explicit_command TEXT NOT NULL CHECK (explicit_command = '/clonamic-my-language'),
        raw_prompt BLOB NOT NULL CHECK (typeof(raw_prompt) = 'blob'),
        sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
        byte_count INTEGER NOT NULL CHECK (byte_count >= 0)
    )
    """,
    """
    CREATE TABLE prompt_analyses (
        sample_id INTEGER PRIMARY KEY REFERENCES prompt_samples(id) ON DELETE CASCADE,
        analyzer_version TEXT NOT NULL,
        analysis_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE style_checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        through_sample_id INTEGER NOT NULL REFERENCES prompt_samples(id),
        total_events INTEGER NOT NULL CHECK (total_events > 0),
        unique_samples INTEGER NOT NULL CHECK (unique_samples > 0),
        analyzer_version TEXT NOT NULL,
        profile_sha256 TEXT NOT NULL CHECK (length(profile_sha256) = 64),
        profile_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX prompt_samples_hash ON prompt_samples(sha256)",
    "CREATE INDEX style_checkpoints_through ON style_checkpoints(through_sample_id)",
)

EXPECTED_COLUMNS = {
    "prompt_samples": {
        "id",
        "captured_at",
        "source_role",
        "explicit_command",
        "raw_prompt",
        "sha256",
        "byte_count",
    },
    "prompt_analyses": {"sample_id", "analyzer_version", "analysis_json"},
    "style_checkpoints": {
        "id",
        "created_at",
        "through_sample_id",
        "total_events",
        "unique_samples",
        "analyzer_version",
        "profile_sha256",
        "profile_json",
    },
}

KOREAN_ENDINGS = (
    "해주세요",
    "해줘",
    "합니다",
    "하세요",
    "할래",
    "하자",
    "거야",
    "같아",
    "맞아",
    "이다",
    "한다",
    "해",
    "요",
    "지",
    "다",
)

DIRECT_MARKERS = (
    "해줘",
    "해주세요",
    "해봐",
    "하자",
    "해야",
    "할래",
    "must",
    "do this",
    "please",
)
FORMAL_MARKERS = ("합니다", "입니다", "하십시오", "해주세요", "please", "could you")
INFORMAL_MARKERS = ("해줘", "하자", "할래", "거야", "맞아", "해봐")
HEDGE_MARKERS = ("것 같", "아마", "혹시", "일단", "maybe", "perhaps", "probably")
AVERSION_MARKERS = {
    "negative-imperative-ko": ("하지 마", "하지마", "하지 말", "하지말"),
    "excess-rejection-ko": ("과한", "불필요", "쓸모없"),
    "explicit-exclusion-ko": ("제외", "금지", "안 돼", "안돼"),
    "negative-imperative-en": ("do not", "don't", "never", "avoid"),
}


def _contract() -> dict[str, Any]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("runtime contract schema version does not match the database schema")
    return data


def default_database_path() -> Path:
    contract = _contract()
    configured = os.environ.get(contract["data_home_environment"])
    base = Path(configured).expanduser() if configured else Path.home() / ".clonamic"
    return base / "my-language" / contract["default_database_name"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _private_parent(path: Path) -> None:
    path.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    try:
        path.chmod(DIRECTORY_MODE)
    except PermissionError:
        pass


def _validate_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if tables != set(EXPECTED_COLUMNS):
        raise sqlite3.DatabaseError("database tables do not match schema version 1")
    for table, expected in EXPECTED_COLUMNS.items():
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if actual != expected:
            raise sqlite3.DatabaseError(f"database columns do not match schema version 1: {table}")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise sqlite3.DatabaseError("database quick_check failed")


def _initialize(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise sqlite3.DatabaseError(f"unsupported newer schema version: {version}")
    if version == 0:
        existing = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
        ).fetchone()
        if existing:
            raise sqlite3.DatabaseError("unsupported unversioned database; migration refused")
        for statement in TABLES:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    _validate_schema(connection)


@contextmanager
def _database(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    database = Path(path).expanduser() if path is not None else default_database_path()
    if database.exists() and database.is_symlink():
        raise ValueError("symbolic-link database paths are not allowed")
    _private_parent(database.parent)
    connection = sqlite3.connect(database, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA foreign_keys = ON")
        _initialize(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
        if database.exists() and not database.is_symlink():
            try:
                database.chmod(DATABASE_MODE)
            except PermissionError:
                pass


def _count_markers(folded: str, markers: Iterable[str]) -> int:
    return sum(folded.count(marker) for marker in markers)


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _mean(values: Sequence[float]) -> float:
    return round(statistics.fmean(values), 6) if values else 0.0


def _detect_language(text: str) -> dict[str, Any]:
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    letters = hangul + latin
    hangul_ratio = _ratio(hangul, letters)
    latin_ratio = _ratio(latin, letters)
    if not letters:
        detected = "undetermined"
    elif hangul_ratio >= 0.8:
        detected = "ko"
    elif latin_ratio >= 0.8:
        detected = "en"
    else:
        detected = "mixed"
    return {
        "detected": detected,
        "hangul_characters": hangul,
        "latin_characters": latin,
        "hangul_ratio": hangul_ratio,
        "latin_ratio": latin_ratio,
    }


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?。！？]+|\n+", text) if part.strip()]


def _ending_counts(sentences: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sentence in sentences:
        cleaned = sentence.rstrip(" \\t\"'”’)]}.,!?。！？")
        for ending in KOREAN_ENDINGS:
            if cleaned.endswith(ending):
                counts[ending] = counts.get(ending, 0) + 1
                break
    return dict(sorted(counts.items()))


def analyze_prompt(raw_prompt: bytes) -> dict[str, Any]:
    try:
        text = raw_prompt.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("prompt must be valid UTF-8") from error
    if not text:
        raise ValueError("prompt payload must not be empty")

    folded = text.casefold()
    lines = text.splitlines() or [text]
    nonblank_lines = [line for line in lines if line.strip()]
    sentences = _sentences(text)
    sentence_lengths = [len(re.sub(r"\s+", "", sentence)) for sentence in sentences]
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    paragraph_sentence_counts = [len(_sentences(paragraph)) for paragraph in paragraphs]
    tokens = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[가-힣]+|\d+", text)
    latin_tokens = [token for token in tokens if re.fullmatch(r"[A-Za-z]+(?:'[A-Za-z]+)?", token)]
    punctuation = {
        character: text.count(character)
        for character in (".", ",", "!", "?", ":", ";", "(", ")", "[", "]", "{", "}", '"', "'", "`", "~", "-", "*", "#")
        if text.count(character)
    }
    bullet_lines = sum(bool(re.match(r"^\s*[-*+]\s+", line)) for line in lines)
    numbered_lines = sum(bool(re.match(r"^\s*\d+[.)]\s+", line)) for line in lines)
    direct_count = _count_markers(folded, DIRECT_MARKERS)
    formal_count = _count_markers(folded, FORMAL_MARKERS)
    informal_count = _count_markers(folded, INFORMAL_MARKERS)
    hedge_count = _count_markers(folded, HEDGE_MARKERS)
    request_count = direct_count + text.count("?")
    aversions = {
        label: count
        for label, markers in AVERSION_MARKERS.items()
        if (count := _count_markers(folded, markers))
    }

    quirks = []
    if '["' in text or "['" in text:
        quirks.append("quoted-square-payload")
    if "->" in text or "→" in text:
        quirks.append("arrow-transition")
    if re.search(r"([!?~])\1+", text):
        quirks.append("repeated-punctuation")
    if bullet_lines or numbered_lines:
        quirks.append("explicit-list-structure")
    if "```" in text:
        quirks.append("fenced-code")
    language = _detect_language(text)
    if language["detected"] == "mixed":
        quirks.append("within-sample-code-switching")

    return {
        "schema_version": SCHEMA_VERSION,
        "language": language,
        "sentence_rhythm": {
            "count": len(sentences),
            "mean_characters": _mean(sentence_lengths),
            "median_characters": round(float(statistics.median(sentence_lengths)), 6)
            if sentence_lengths
            else 0.0,
            "short_sentence_ratio": _ratio(sum(length <= 20 for length in sentence_lengths), len(sentence_lengths)),
        },
        "paragraph_rhythm": {
            "count": len(paragraphs),
            "mean_sentences": _mean(paragraph_sentence_counts),
            "blank_line_count": len(re.findall(r"\n\s*\n", text)),
        },
        "request_style": {
            "request_marker_count": request_count,
            "direct_marker_count": direct_count,
            "formal_marker_count": formal_count,
            "informal_marker_count": informal_count,
            "hedge_marker_count": hedge_count,
            "directness": _ratio(direct_count, direct_count + hedge_count),
            "formality": _ratio(formal_count, formal_count + informal_count),
            "hedge_rate_per_sentence": _ratio(hedge_count, len(sentences)),
        },
        "punctuation_formatting": {
            "character_count": len(text),
            "line_count": len(lines),
            "nonblank_line_count": len(nonblank_lines),
            "punctuation": punctuation,
            "bullet_lines": bullet_lines,
            "numbered_lines": numbered_lines,
            "code_fence_count": text.count("```") // 2,
            "quoted_payload_count": text.count('["') + text.count("['"),
        },
        "korean_endings": _ending_counts(sentences),
        "code_switching": {
            "active": language["detected"] == "mixed",
            "latin_token_ratio": _ratio(len(latin_tokens), len(tokens)),
        },
        "list_habits": {
            "uses_bullets": bool(bullet_lines),
            "uses_numbering": bool(numbered_lines),
            "uses_fenced_code": "```" in text,
        },
        "stable_quirk_candidates": sorted(quirks),
        "aversion_markers": dict(sorted(aversions.items())),
    }


def _sum_nested(analyses: Sequence[dict[str, Any]], section: str, key: str) -> int:
    return sum(int(item[section][key]) for item in analyses)


def _aggregate_core(analyses: Sequence[dict[str, Any]]) -> dict[str, Any]:
    sentence_counts = [_sum_nested([item], "sentence_rhythm", "count") for item in analyses]
    sentence_means = [item["sentence_rhythm"]["mean_characters"] for item in analyses]
    paragraph_counts = [_sum_nested([item], "paragraph_rhythm", "count") for item in analyses]
    paragraph_means = [item["paragraph_rhythm"]["mean_sentences"] for item in analyses]
    request_styles = [item["request_style"] for item in analyses]
    character_count = _sum_nested(analyses, "punctuation_formatting", "character_count")
    punctuation_totals: dict[str, int] = {}
    ending_totals: dict[str, int] = {}
    for item in analyses:
        for key, value in item["punctuation_formatting"]["punctuation"].items():
            punctuation_totals[key] = punctuation_totals.get(key, 0) + int(value)
        for key, value in item["korean_endings"].items():
            ending_totals[key] = ending_totals.get(key, 0) + int(value)
    return {
        "sentence_rhythm": {
            "mean_sentences_per_sample": _mean(sentence_counts),
            "mean_characters_per_sentence": _mean(sentence_means),
            "short_sentence_ratio": _mean(
                [item["sentence_rhythm"]["short_sentence_ratio"] for item in analyses]
            ),
        },
        "paragraph_rhythm": {
            "mean_paragraphs_per_sample": _mean(paragraph_counts),
            "mean_sentences_per_paragraph": _mean(paragraph_means),
            "blank_lines_per_sample": _mean(
                [item["paragraph_rhythm"]["blank_line_count"] for item in analyses]
            ),
        },
        "request_style": {
            "directness": _mean([item["directness"] for item in request_styles]),
            "formality": _mean([item["formality"] for item in request_styles]),
            "hedge_rate_per_sentence": _mean(
                [item["hedge_rate_per_sentence"] for item in request_styles]
            ),
            "samples_with_requests": sum(bool(item["request_marker_count"]) for item in request_styles),
        },
        "punctuation_formatting": {
            "punctuation_per_1000_characters": {
                key: round(value * 1000 / character_count, 6)
                for key, value in sorted(punctuation_totals.items())
            }
            if character_count
            else {},
            "bullet_sample_ratio": _mean(
                [float(item["list_habits"]["uses_bullets"]) for item in analyses]
            ),
            "numbered_sample_ratio": _mean(
                [float(item["list_habits"]["uses_numbering"]) for item in analyses]
            ),
            "fenced_code_sample_ratio": _mean(
                [float(item["list_habits"]["uses_fenced_code"]) for item in analyses]
            ),
        },
        "korean_endings": dict(sorted(ending_totals.items(), key=lambda item: (-item[1], item[0]))),
        "code_switching": {
            "mixed_sample_ratio": _mean(
                [float(item["code_switching"]["active"]) for item in analyses]
            ),
            "mean_latin_token_ratio": _mean(
                [item["code_switching"]["latin_token_ratio"] for item in analyses]
            ),
        },
        "list_habits": {
            "bullet_samples": sum(item["list_habits"]["uses_bullets"] for item in analyses),
            "numbered_samples": sum(item["list_habits"]["uses_numbering"] for item in analyses),
            "fenced_code_samples": sum(item["list_habits"]["uses_fenced_code"] for item in analyses),
        },
    }


def build_profile(analyses: Sequence[dict[str, Any]], *, total_events: int) -> dict[str, Any]:
    if not analyses:
        raise ValueError("at least one unique analysis is required")
    language_counts: dict[str, int] = {}
    quirk_counts: dict[str, int] = {}
    aversion_counts: dict[str, int] = {}
    by_language_input: dict[str, list[dict[str, Any]]] = {}
    for item in analyses:
        language = item["language"]["detected"]
        language_counts[language] = language_counts.get(language, 0) + 1
        by_language_input.setdefault(language, []).append(item)
        for quirk in item["stable_quirk_candidates"]:
            quirk_counts[quirk] = quirk_counts.get(quirk, 0) + 1
        for marker, count in item["aversion_markers"].items():
            aversion_counts[marker] = aversion_counts.get(marker, 0) + int(count)

    unique_count = len(analyses)
    dominant = sorted(language_counts, key=lambda key: (-language_counts[key], key))[0]
    repeated_minimum = 2
    stable_quirks = [
        {"name": key, "evidence_samples": value}
        for key, value in sorted(quirk_counts.items())
        if value >= repeated_minimum and _ratio(value, unique_count) >= 0.3
    ]
    aversions = [
        {"name": key, "evidence_count": value}
        for key, value in sorted(aversion_counts.items())
        if value >= repeated_minimum
    ]
    profile = {
        "schema_version": SCHEMA_VERSION,
        "language": {"dominant": dominant, "unique_sample_counts": dict(sorted(language_counts.items()))},
        **_aggregate_core(analyses),
        "stable_repeated_quirks": stable_quirks,
        "aversions": aversions,
        "confidence": {
            "overall": round(min(1.0, unique_count / 10), 6),
            "unique_samples": unique_count,
            "total_events": total_events,
            "repeated_feature_minimum": repeated_minimum,
        },
        "evidence_counts": {
            "unique_samples": unique_count,
            "total_events": total_events,
            "duplicate_events": total_events - unique_count,
        },
        "by_language": {
            language: {
                "unique_samples": len(group),
                **_aggregate_core(group),
            }
            for language, group in sorted(by_language_input.items())
        },
    }
    return profile


def _unique_analyses(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT pa.analysis_json
        FROM prompt_samples AS ps
        JOIN prompt_analyses AS pa ON pa.sample_id = ps.id
        WHERE ps.id IN (SELECT MIN(id) FROM prompt_samples GROUP BY sha256)
        ORDER BY ps.sha256
        """
    ).fetchall()
    return [json.loads(row["analysis_json"]) for row in rows]


def _counts(connection: sqlite3.Connection) -> tuple[int, int, int]:
    row = connection.execute(
        "SELECT COUNT(*) AS events, COUNT(DISTINCT sha256) AS unique_samples, COALESCE(MAX(id), 0) AS last_id FROM prompt_samples"
    ).fetchone()
    return int(row["events"]), int(row["unique_samples"]), int(row["last_id"])


def _materialize_checkpoint(connection: sqlite3.Connection) -> sqlite3.Row:
    total_events, unique_samples, last_id = _counts(connection)
    if not total_events:
        raise ValueError("no explicit user sample is available")
    profile = build_profile(_unique_analyses(connection), total_events=total_events)
    profile_json = _canonical(profile).decode("utf-8")
    profile_hash = _sha256(profile_json.encode("utf-8"))
    connection.execute(
        """
        INSERT INTO style_checkpoints
            (created_at, through_sample_id, total_events, unique_samples, analyzer_version, profile_sha256, profile_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (_now(), last_id, total_events, unique_samples, ANALYZER_VERSION, profile_hash, profile_json),
    )
    return connection.execute("SELECT * FROM style_checkpoints WHERE id = last_insert_rowid()").fetchone()


def capture(
    raw_prompt: bytes,
    *,
    path: str | Path | None = None,
    source_role: str = "user",
    explicit_command: str = "/clonamic-my-language",
) -> dict[str, Any]:
    contract = _contract()
    if source_role != contract["source_role"]:
        raise PermissionError("only an explicit user payload may be captured")
    if explicit_command != contract["explicit_command"]:
        raise PermissionError("the exact explicit command is required")
    analysis = analyze_prompt(raw_prompt)
    digest = _sha256(raw_prompt)
    with _database(path) as connection:
        connection.execute(
            """
            INSERT INTO prompt_samples
                (captured_at, source_role, explicit_command, raw_prompt, sha256, byte_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_now(), source_role, explicit_command, sqlite3.Binary(raw_prompt), digest, len(raw_prompt)),
        )
        sample_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO prompt_analyses (sample_id, analyzer_version, analysis_json) VALUES (?, ?, ?)",
            (sample_id, ANALYZER_VERSION, _canonical(analysis).decode("utf-8")),
        )
        total_events, unique_samples, _ = _counts(connection)
        latest = connection.execute(
            "SELECT * FROM style_checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchone()
        through = int(latest["through_sample_id"]) if latest else 0
        pending_unique = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT newer.sha256)
                FROM prompt_samples AS newer
                WHERE newer.id > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM prompt_samples AS older
                      WHERE older.id <= ? AND older.sha256 = newer.sha256
                  )
                """,
                (through, through),
            ).fetchone()[0]
        )
        persisted = pending_unique >= int(contract["checkpoint_unique_sample_threshold"])
        checkpoint = _materialize_checkpoint(connection) if persisted else latest
        if checkpoint is not None:
            profile = json.loads(checkpoint["profile_json"])
            profile_state = "updated-checkpoint" if persisted else "checkpoint"
        else:
            profile = build_profile(_unique_analyses(connection), total_events=total_events)
            profile_state = "provisional"
    return {
        "status": "captured",
        "sample_id": sample_id,
        "sha256": digest,
        "byte_count": len(raw_prompt),
        "total_events": total_events,
        "unique_samples": unique_samples,
        "checkpoint_id": int(checkpoint["id"]) if checkpoint else None,
        "checkpoint_updated": persisted,
        "pending_unique_samples": 0 if persisted else pending_unique,
        "profile_state": profile_state,
        "profile": profile,
    }


def inspect(path: str | Path | None = None) -> dict[str, Any]:
    with _database(path) as connection:
        total_events, unique_samples, last_id = _counts(connection)
        checkpoint = connection.execute(
            "SELECT id, through_sample_id, total_events, unique_samples, profile_sha256 FROM style_checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "status": "ready",
        "total_events": total_events,
        "unique_samples": unique_samples,
        "last_sample_id": last_id,
        "checkpoint": dict(checkpoint) if checkpoint else None,
    }


def _export_files(profile: dict[str, Any], profile_hash: str) -> dict[str, bytes]:
    contract = _contract()
    profile_document = {
        "schema_version": SCHEMA_VERSION,
        "profile_sha256": profile_hash,
        "profile": profile,
    }
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": contract["profile_plugin_name"],
        "version": contract["profile_plugin_version"],
        "description": "Explicit portable Clonamic style profile without source prompts.",
        "license": "MIT",
        "author": {"name": "Clonamic"},
        "keywords": ["language", "style", "profile", "explicit"],
    }
    apply_skill = """---
name: clonamic-my-language
description: Apply this derived style profile only when the user explicitly invokes /clonamic-my-language.
disable-model-invocation: true
user-invocable: true
---

# Clonamic My Language Profile

Run only on an explicit `/clonamic-my-language` invocation. Read
`references/style-profile.json`, then shape only the current response with supported observable
fields. Preserve facts, quoted text, numbers, identifiers, code, and requested structure before
style. Treat low-confidence fields as weak hints. Never infer personality or load the profile into
ordinary conversation.

Run exactly one review pass. This main command owns the pass: use the package's native
`clonamic-my-language-review` child agent only when the host exposes it and pass
`active_command=/clonamic-my-language`; otherwise apply the same preservation checks sequentially.
Never route the reviewer outside this explicit command. Persist nothing.
"""
    review_skill = """---
name: clonamic-my-language-review
description: Review one draft against the exported profile only inside an active explicit my-language invocation.
disable-model-invocation: true
user-invocable: false
---

# Clonamic My Language Review

This is a portable review contract, not an independently routed command. Accept work only with
`active_command=/clonamic-my-language`; otherwise return `refused_inactive_invocation`. Compare the
current draft with the sibling profile while preserving facts, quoted text, numbers, identifiers,
code, and the requested structure. Return the draft unchanged when it passes; otherwise return one
corrected draft without commentary. Persist nothing and do not infer unsupported traits.
"""
    native_reviewer = """---
name: clonamic-my-language-review
description: Internal child reviewer for an active /clonamic-my-language command only; never select for ordinary requests.
tools: []
---

# Clonamic My Language Review

Accept work only when the parent supplies `active_command=/clonamic-my-language`, the exported
profile, and the current draft. Return `refused_inactive_invocation` otherwise. Run one preservation
and observable-style check, then return the unchanged or corrected draft without analysis. Use no
tools and persist nothing.
"""
    openai_apply = """interface:
  display_name: "Clonamic My Language Profile"
  short_description: "Apply one exported style profile explicitly"
  default_prompt: "Use $clonamic-my-language for this response only."
policy:
  allow_implicit_invocation: false
"""
    openai_review = """interface:
  display_name: "Clonamic My Language Review"
  short_description: "Review one explicitly styled draft"
  default_prompt: "Use $clonamic-my-language-review inside the active style command."
policy:
  allow_implicit_invocation: false
"""
    license_text = """MIT License

Copyright (c) 2026 Clonamic

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    return {
        "LICENSE": license_text.encode("utf-8"),
        "agents/clonamic-my-language-review.md": native_reviewer.encode("utf-8"),
        "plugin.json": _canonical(manifest, pretty=True),
        "skills/clonamic-my-language/SKILL.md": apply_skill.encode("utf-8"),
        "skills/clonamic-my-language/agents/openai.yaml": openai_apply.encode("utf-8"),
        "skills/clonamic-my-language/references/style-profile.json": _canonical(
            profile_document, pretty=True
        ),
        "skills/clonamic-my-language-review/SKILL.md": review_skill.encode("utf-8"),
        "skills/clonamic-my-language-review/agents/openai.yaml": openai_review.encode("utf-8"),
    }


def export_checkpoint(
    destination: str | Path, *, path: str | Path | None = None
) -> dict[str, Any]:
    output = Path(destination).expanduser()
    if output.exists() or output.is_symlink():
        raise FileExistsError("export destination already exists")
    if output.parent.exists() and output.parent.is_symlink():
        raise ValueError("symbolic-link export parents are not allowed")
    with _database(path) as connection:
        total_events, _, last_id = _counts(connection)
        if not total_events:
            raise ValueError("no explicit user sample is available")
        latest = connection.execute(
            "SELECT * FROM style_checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest is None or int(latest["through_sample_id"]) != last_id:
            latest = _materialize_checkpoint(connection)
        profile = json.loads(latest["profile_json"])
        profile_hash = str(latest["profile_sha256"])

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        files = _export_files(profile, profile_hash)
        for relative, content in sorted(files.items()):
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        os.replace(staging, output)
    return {
        "status": "exported",
        "plugin": _contract()["profile_plugin_name"],
        "version": _contract()["profile_plugin_version"],
        "profile_sha256": profile_hash,
        "file_count": len(files),
        "destination": str(output),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="operation", required=True)

    capture_parser = subcommands.add_parser("capture", help="capture stdin from one explicit user command")
    capture_parser.add_argument("--database", type=Path)
    capture_parser.add_argument("--source-role", default="user")
    capture_parser.add_argument("--explicit-command", default="/clonamic-my-language")

    inspect_parser = subcommands.add_parser("inspect", help="show counts without prompt content")
    inspect_parser.add_argument("--database", type=Path)

    export_parser = subcommands.add_parser("export", help="export the current raw-free checkpoint")
    export_parser.add_argument("--database", type=Path)
    export_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.operation == "capture":
            result = capture(
                sys.stdin.buffer.read(),
                path=arguments.database,
                source_role=arguments.source_role,
                explicit_command=arguments.explicit_command,
            )
        elif arguments.operation == "inspect":
            result = inspect(arguments.database)
        else:
            result = export_checkpoint(arguments.output, path=arguments.database)
    except (FileExistsError, PermissionError, ValueError, sqlite3.DatabaseError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Decide whether a Korean revision stays inside the change bound."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTRAST = ("가 아니라", "것이 아니라", "것은 아니다", "인가, ")
MODALITY = ("해야 한다", "할 수 있다")


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    prev = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        cur = [i]
        for j, b in enumerate(right, 1):
            cost = 0 if a == b else 1
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def change_rate(before: str, after: str) -> float:
    if not before:
        return 0.0 if not after else 1.0
    return levenshtein(before, after) / len(before)


def contrast_wiped(before: str, after: str) -> bool:
    before_count = sum(before.count(token) for token in CONTRAST)
    after_count = sum(after.count(token) for token in CONTRAST)
    return before_count >= 5 and after_count == 0


def modality_lost(before: str, after: str) -> bool:
    return any(before.count(mark) > after.count(mark) for mark in MODALITY)


def judge(before: str, after: str) -> int:
    distance = levenshtein(before, after)
    length = len(before)
    if not before and after:
        return 2
    if length and distance * 100 >= length * 50:
        return 2
    if length and distance * 100 >= length * 30:
        return 1
    if contrast_wiped(before, after) or modality_lost(before, after):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    before_path = Path(args.before)
    after_path = Path(args.after)
    if not before_path.is_file() or not after_path.is_file():
        print("missing input", file=sys.stderr)
        return 3
    before = before_path.read_text(encoding="utf-8")
    after = after_path.read_text(encoding="utf-8")
    code = judge(before, after)
    payload = {"rate": change_rate(before, after), "code": code}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"rate={payload['rate']:.4f} code={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

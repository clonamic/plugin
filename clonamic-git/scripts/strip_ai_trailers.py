#!/usr/bin/env python3
"""Remove AI attribution trailers and footers from a commit message, PR body, tag or release note.

Usage:
  strip_ai_trailers.py [FILE]           FILE given: rewrite it in place (commit-msg hook mode).
                                        No FILE: read stdin, write stdout.
  --check                               Do not write; list what would be removed; exit 1 if anything.
  --pattern REGEX                       Extra line pattern to remove (repeatable, case-insensitive).
  --patterns-file PATH                  File with one extra regex per line (# comments allowed).
  --no-git-config                       Ignore `git config --get-all clonamic.aiPattern`.
  --quiet                               No stderr summary.

Human trailers (for example `Co-authored-by: Jane Doe <jane@example.com>`) are kept.
Exit codes: 0 ok, 1 attribution found (--check only), 2 usage or regex error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 12):
    sys.exit("strip_ai_trailers.py needs Python 3.12+; install it (for example `uv python install 3.12`).")

# Names that identify an AI tool or vendor when they start a trailer value or identity name.
AI_NAME = re.compile(
    r"^\W*(?:github\s+)?(?:claude|anthropic|codex|openai|chatgpt|gpt[-\s]?\d[\w.-]*|cursor|grok|xai|x\.ai"
    r"|copilot|gemini|aider|devin|jules|windsurf|codeium|cline|amazon\s+q|opencode)\b",
    re.IGNORECASE,
)
# Vendor domains; an address there counts as AI only when its local part looks like an agent or noreply.
AI_DOMAIN = re.compile(
    r"@(?:[\w-]+\.)*(?:anthropic\.com|openai\.com|cursor\.com|cursor\.sh|x\.ai|aider\.chat|devin\.ai"
    r"|cognition\.ai|codeium\.com|windsurf\.com)$",
    re.IGNORECASE,
)
AGENT_LOCAL = re.compile(
    r"no-?reply|agent|bot|claude|codex|cursor|grok|copilot|gemini|aider|devin|chatgpt|assistant",
    re.IGNORECASE,
)
GITHUB_AI_NOREPLY = re.compile(r"^\d+\+copilot@users\.noreply\.github\.com$", re.IGNORECASE)
NOREPLY = re.compile(r"no-?reply", re.IGNORECASE)

TRAILER = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*:\s*(.+?)\s*$")
TRAILER_KEYS = {
    "co-authored-by", "coauthored-by", "co-author", "co-authors", "signed-off-by", "assisted-by",
    "generated-by", "made-with", "created-with", "built-with", "written-by", "authored-by", "helped-by",
    "reviewed-by", "acked-by", "tested-by", "ai-assisted-by", "ai-agent", "ai-model", "agent",
}
IDENT = re.compile(r"^(?P<name>.*?)\s*(?:<(?P<email>[^<>]*)>)?\s*$")

FOOTER = re.compile(
    r"^[\W_]*(?:generated|created|made|written|built|authored|assisted|produced|co-?authored|powered)"
    r"\s+(?:with|by|using|via|in)\s+\[?(?:the\s+)?(?:claude|anthropic|codex|openai|chatgpt|cursor|grok|xai"
    r"|copilot|github\s+copilot|gemini|aider|devin|jules|windsurf|an?\s+ai\b|ai\b)",
    re.IGNORECASE,
)
ROBOT = re.compile(r"^\s*\U0001F916")
AGENT_LINK = re.compile(
    r"https?://(?:claude\.ai/code/|chatgpt\.com/codex/|cursor\.com/(?:background-agent|agents))",
    re.IGNORECASE,
)


def is_ai_identity(name: str, email: str) -> bool:
    """True when a name/email pair belongs to an AI tool, vendor agent, or bot account."""
    name, email = (name or "").strip(), (email or "").strip().strip("<>")
    if "[bot]" in name.lower() or "[bot]" in email.lower() or GITHUB_AI_NOREPLY.match(email):
        return True
    if email and AI_DOMAIN.search(email) and AGENT_LOCAL.search(email.split("@", 1)[0]):
        return True
    return bool(AI_NAME.match(name)) and (not email or bool(NOREPLY.search(email)) or bool(AI_DOMAIN.search(email)))


def classify(line: str, extra: list[re.Pattern[str]]) -> str | None:
    """Return why a line is AI attribution, or None to keep it."""
    if ROBOT.match(line):
        return "robot-emoji"
    if FOOTER.match(line):
        return "generated-footer"
    if AGENT_LINK.search(line):
        return "agent-session-link"
    m = TRAILER.match(line)
    if m and m.group(1).lower() in TRAILER_KEYS:
        ident = IDENT.match(m.group(2))
        if ident and is_ai_identity(ident.group("name"), ident.group("email") or ""):
            return "ai-trailer"
    for pattern in extra:
        if pattern.search(line):
            return "custom-pattern"
    return None


def strip_message(text: str, extra: list[re.Pattern[str]] | None = None) -> tuple[str, list[tuple[str, str]]]:
    """Return (clean_text, [(reason, removed_line), ...]). Unchanged text is returned byte-identical."""
    extra = extra or []
    kept: list[str] = []
    removed: list[tuple[str, str]] = []
    for line in text.splitlines():
        reason = classify(line, extra)
        if reason:
            removed.append((reason, line))
        else:
            kept.append(line)
    if not removed:
        return text, []
    out: list[str] = []
    for line in kept:
        if not line.strip() and (not out or not out[-1].strip()):
            continue  # collapse blank runs left behind and drop leading blanks
        out.append(line.rstrip() if not line.strip() else line)
    while out and not out[-1].strip():
        out.pop()
    return ("\n".join(out) + "\n") if out else "", removed


def git_config_patterns() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "config", "--get-all", "clonamic.aiPattern"], capture_output=True, text=True, check=False
        )
    except OSError:
        return []
    return [p for p in proc.stdout.splitlines() if p.strip()] if proc.returncode == 0 else []


def compile_patterns(raw: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in raw]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove AI attribution trailers/footers from a message.")
    parser.add_argument("file", nargs="?", help="message file to rewrite in place (hook mode)")
    parser.add_argument("--check", action="store_true", help="report only; exit 1 when attribution is found")
    parser.add_argument("--pattern", action="append", default=[], help="extra regex (repeatable)")
    parser.add_argument("--patterns-file", help="file with one extra regex per line")
    parser.add_argument("--no-git-config", action="store_true", help="ignore git config clonamic.aiPattern")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    raw = list(args.pattern)
    try:
        if args.patterns_file:
            raw += [
                ln.strip() for ln in Path(args.patterns_file).read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")
            ]
        if not args.no_git_config:
            raw += git_config_patterns()
        extra = compile_patterns(raw)
    except (OSError, re.error) as exc:
        print(f"clonamic-git: {exc}", file=sys.stderr)
        return 2

    if args.file:
        path = Path(args.file)
        text = path.read_bytes().decode("utf-8", "surrogateescape")
    else:
        text = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")

    clean, removed = strip_message(text, extra)

    if args.check:
        for reason, line in removed:
            print(f"{reason}\t{line}", file=sys.stderr)
        return 1 if removed else 0

    if args.file:
        if removed:
            path.write_bytes(clean.encode("utf-8", "surrogateescape"))
    else:
        sys.stdout.buffer.write(clean.encode("utf-8", "surrogateescape"))
    if removed and not args.quiet:
        print(f"clonamic-git: removed {len(removed)} AI attribution line(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

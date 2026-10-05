#!/usr/bin/env python3
"""Install (or remove) the clonamic-git commit-msg hook in one repository.

Usage:
  install_hook.py [--repo DIR] [--hooks-dir DIR]          install
  install_hook.py [--repo DIR] [--hooks-dir DIR] --uninstall
  install_hook.py [--repo DIR] [--hooks-dir DIR] --status

Installs two files into the repository's own hooks directory (inside .git, never tracked):
  clonamic-strip-ai-trailers   a self-contained copy of strip_ai_trailers.py (survives plugin updates)
  commit-msg                   a tiny wrapper that runs it on the message file
An existing commit-msg hook that is not ours is never touched; the line to add to it is printed instead.
If core.hooksPath points outside the repository's git dir (husky, a shared or global hooks dir), nothing is
written unless --hooks-dir is given explicitly.
Exit codes: 0 ok, 1 refused (foreign hook or shared hooks path), 2 error.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 12):
    sys.exit("install_hook.py needs Python 3.12+; install it (for example `uv python install 3.12`).")

MARKER = "# clonamic-git commit-msg hook"
FILTER_NAME = "clonamic-strip-ai-trailers"
SOURCE = Path(__file__).resolve().parent / "strip_ai_trailers.py"
WRAPPER = f"""#!/bin/sh
{MARKER} (remove with: install_hook.py --uninstall, or delete this file and {FILTER_NAME})
exec "$(dirname "$0")/{FILTER_NAME}" "$1"
"""
CHAIN_LINE = f'"$(git rev-parse --git-path hooks)/{FILTER_NAME}" "$1" || exit 1'


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def resolve_hooks_dir(repo: str, explicit: str | None) -> tuple[Path, bool]:
    """Return (hooks_dir, is_private) where private means inside the repository's git common dir."""
    if explicit:
        return Path(explicit).resolve(), True
    top = Path(repo).resolve()  # --git-path / --git-common-dir are relative to the -C directory
    hooks = Path(git(repo, "rev-parse", "--git-path", "hooks"))
    common = Path(git(repo, "rev-parse", "--git-common-dir"))
    hooks = (hooks if hooks.is_absolute() else top / hooks).resolve()
    common = (common if common.is_absolute() else top / common).resolve()
    return hooks, hooks.is_relative_to(common)


def make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def is_ours(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the clonamic-git commit-msg hook in one repo.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--hooks-dir", help="explicit hooks directory (overrides core.hooksPath safety check)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--uninstall", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    try:
        hooks, private = resolve_hooks_dir(args.repo, args.hooks_dir)
    except RuntimeError as exc:
        print(f"clonamic-git: {exc}", file=sys.stderr)
        return 2
    hook, filt = hooks / "commit-msg", hooks / FILTER_NAME

    if args.status:
        state = "installed" if is_ours(hook) else ("filter-only" if filt.exists() else "not-installed")
        if hook.exists() and not is_ours(hook):
            state += " (foreign commit-msg hook present)"
        print(f"{state}: {hooks}")
        return 0

    if args.uninstall:
        removed = []
        if is_ours(hook):
            hook.unlink()
            removed.append(hook.name)
        if filt.exists() and is_ours(filt):
            filt.unlink()
            removed.append(filt.name)
        print(f"removed {', '.join(removed)} from {hooks}" if removed else f"nothing to remove in {hooks}")
        if hook.exists():
            print(f"note: a foreign commit-msg hook remains; delete this line from it if you added it:\n  {CHAIN_LINE}")
        return 0

    if not private:
        print(
            f"refused: hooks directory {hooks} is outside this repository's git dir (core.hooksPath).\n"
            "Add the hook there yourself, or rerun with --hooks-dir to choose a directory explicitly.",
            file=sys.stderr,
        )
        return 1

    hooks.mkdir(parents=True, exist_ok=True)
    source = SOURCE.read_text(encoding="utf-8").splitlines(keepends=True)
    body = source[1:] if source and source[0].startswith("#!") else source
    filt.write_text("#!/usr/bin/env python3\n" + MARKER + " filter\n" + "".join(body), encoding="utf-8")
    make_executable(filt)

    if hook.exists() and not is_ours(hook):
        print(
            f"installed {filt}\nrefused to replace the existing {hook} (not ours).\n"
            f"To chain it, add this line near the end of that hook:\n  {CHAIN_LINE}",
            file=sys.stderr,
        )
        return 1

    hook.write_text(WRAPPER, encoding="utf-8")
    make_executable(hook)
    print(f"installed {hook} and {filt}")
    print(f"remove with: python3 {Path(__file__).resolve()} --repo {os.path.abspath(args.repo)} --uninstall")
    print(f"  or delete {hook} and {filt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

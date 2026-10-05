#!/usr/bin/env python3
"""Derive every host manifest and marketplace from each plugin's root plugin.json.

The root plugin.json (Agent Plugins 1.0.0) is the only file edited by hand.
Codex, Cursor, and Grok read it directly; this script writes the rest:

  <plugin>/.claude-plugin/plugin.json   Claude Code
  <plugin>/.codex-plugin/plugin.json    Codex UI overlay (interface is kept as-is)
  <plugin>/.cursor-plugin/plugin.json   Cursor, only when the plugin ships agents/
  .claude-plugin/marketplace.json       Claude Code, Cursor, Grok (Codex also reads it)
  .agents/plugins/marketplace.json      Codex
  clonamic-harness/skills/*/references  copies of ../template/ spec and report formats

Usage:
  python3 scripts/sync_manifests.py          # rewrite derived files
  python3 scripts/sync_manifests.py --check  # exit 1 if anything is stale or invalid
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
STANDARD_KEYS = (
    "$schema", "name", "version", "description", "homepage",
    "repository", "license", "author", "keywords", "extensions",
)
HOST_KEYS = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")
# Strictest common rule: Grok forbids '.', the standard forbids leading/trailing and doubled separators.
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RESERVED_PREFIXES = ("claude-", "anthropic-", "cc-plugin-")
LEGACY_HOST_DIR = "io.github.algocean1204.clonamic"
MARKETPLACE = "clonamic"
OWNER = {"name": "Clonamic"}
DESCRIPTION = "Clonamic skills for Claude Code, Codex, Cursor, and Grok."
# Kept out of the public marketplaces; manifests are still maintained.
UNLISTED = frozenset({"clonamic-admin"})
# ../template/ is the single source for the spec and report formats; the harness ships copies.
TEMPLATE_DIR = REPO.parent / "template"
TEMPLATE_COPIES = {
    "작업명세서.md": "clonamic-harness/skills/clonamic-spec/references/work-spec.md",
    "개발명세서.md": "clonamic-harness/skills/clonamic-spec/references/dev-spec.md",
    "보고서.md": "clonamic-harness/skills/clonamic-finish/references/report.md",
}


def plugin_dirs() -> list[Path]:
    return sorted(p.parent for p in REPO.glob("clonamic-*/plugin.json"))


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def normalized_root(manifest: dict) -> dict:
    """Put $schema first, keep the author's key order, drop keys the closed schema rejects."""
    result = {"$schema": SCHEMA}
    for key, value in manifest.items():
        if key in STANDARD_KEYS and key != "$schema":
            result[key] = value
    return result


def host_fields(root: dict) -> dict:
    return {key: root[key] for key in HOST_KEYS if key in root}


def codex_interface(plugin: Path) -> dict | None:
    for source in (plugin / ".codex-plugin/plugin.json", plugin / LEGACY_HOST_DIR / "codex/plugin.json"):
        data = read_json(source)
        if data and "interface" in data:
            return data["interface"]
    return None


def derived_files(plugin: Path, root: dict) -> dict[Path, str]:
    files = {plugin / "plugin.json": dump(root), plugin / ".claude-plugin/plugin.json": dump(host_fields(root))}

    codex = {**host_fields(root), "skills": "./skills/"}
    interface = codex_interface(plugin)
    if interface is not None:
        codex["interface"] = interface
    files[plugin / ".codex-plugin/plugin.json"] = dump(codex)

    if (plugin / "agents").is_dir():
        cursor = {**host_fields(root), "skills": "./skills/", "agents": "./agents/"}
        files[plugin / ".cursor-plugin/plugin.json"] = dump(cursor)
    return files


def marketplaces(listed: list[tuple[Path, dict]]) -> dict[Path, str]:
    claude = {"name": MARKETPLACE, "owner": OWNER, "description": DESCRIPTION, "plugins": []}
    codex = {"name": MARKETPLACE, "interface": {"displayName": "Clonamic"}, "plugins": []}
    for plugin, root in listed:
        source = f"./{plugin.relative_to(REPO).as_posix()}"
        claude["plugins"].append({"name": root["name"], "source": source, "description": root.get("description", "")})
        category = (codex_interface(plugin) or {}).get("category", "Productivity")
        codex["plugins"].append({
            "name": root["name"],
            "source": {"source": "local", "path": source},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": category,
        })
    return {
        REPO / ".claude-plugin/marketplace.json": dump(claude),
        REPO / ".agents/plugins/marketplace.json": dump(codex),
    }


def template_copies() -> dict[Path, str]:
    """Skipped when the plugin repo is checked out without its sibling template/ repo."""
    if not TEMPLATE_DIR.is_dir():
        return {}
    return {REPO / target: (TEMPLATE_DIR / source).read_text(encoding="utf-8") for source, target in TEMPLATE_COPIES.items()}


def validate(plugin: Path, raw: dict) -> list[str]:
    rel = plugin.relative_to(REPO)
    problems = []
    name = raw.get("name", "")
    if name != plugin.name:
        problems.append(f"{rel}: name {name!r} must equal the folder name")
    if not NAME_PATTERN.fullmatch(name) or len(name) > 64:
        problems.append(f"{rel}: name {name!r} must be 1-64 chars of [a-z0-9-] (no '.', Grok)")
    if name.startswith(RESERVED_PREFIXES):
        problems.append(f"{rel}: name {name!r} uses a prefix Claude reserves")
    if not raw.get("description"):
        problems.append(f"{rel}: description is required")
    author = raw.get("author")
    if author is not None and set(author) - {"name", "email", "url"}:
        problems.append(f"{rel}: author allows only name, email, url")
    if (plugin / LEGACY_HOST_DIR).exists():
        problems.append(f"{rel}: {LEGACY_HOST_DIR}/ is read by no host; run sync, then delete it")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report stale or invalid files without writing")
    args = parser.parse_args()

    problems: list[str] = []
    wanted: dict[Path, str] = {}
    listed: list[tuple[Path, dict]] = []
    for plugin in plugin_dirs():
        raw = read_json(plugin / "plugin.json")
        root = normalized_root(raw)
        wanted.update(derived_files(plugin, root))
        if plugin.parent == REPO and plugin.name not in UNLISTED:
            listed.append((plugin, root))
        problems += validate(plugin, raw) if args.check else []
    wanted.update(marketplaces(listed))
    wanted.update(template_copies())

    stale = [path for path, text in wanted.items() if not path.is_file() or path.read_text(encoding="utf-8") != text]
    orphans = [p for p in REPO.glob("clonamic-*/.cursor-plugin/plugin.json") if p not in wanted]
    if args.check:
        problems += [f"{p.relative_to(REPO)}: out of date; run python3 scripts/sync_manifests.py" for p in stale]
        problems += [f"{p.relative_to(REPO)}: plugin has no agents/; run sync to remove it" for p in orphans]
        for line in problems:
            print(line, file=sys.stderr)
        return 1 if problems else 0

    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wanted[path], encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")
    for path in orphans:
        path.unlink()
        path.parent.rmdir()
        print(f"removed {path.relative_to(REPO)}")
    print(f"{len(stale)} file(s) updated, {len(wanted) - len(stale)} already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())

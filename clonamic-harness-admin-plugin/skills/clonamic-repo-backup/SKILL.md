---
name: clonamic-repo-backup
description: "Folder-to-GitHub PRIVATE backup pipeline driven by an in-folder `.backup-repo` marker (one line: owner/repo). Load ONLY on an explicit backup request for a folder — /backup, '이 폴더 백업', '백업 레포 설정/연결'. First run with no marker or repo: ask the user, then configure — setup and backup complete as ONE pipeline. Never auto-loads, never runs on a schedule. Not for public distribution."
---

# clonamic-repo-backup — Folder → Private GitHub Backup

One pipeline, five stages. Later runs skip every stage already satisfied — a configured folder goes straight to stage 4–5 with zero questions.

## Pipeline

1. **Marker** — read `<folder>/.backup-repo` (single line, `owner/repo`). Missing → ASK the user once: propose `<owner>/<folder-name>-backup` (private), accept their name, then write the marker file. Never guess silently.
2. **Repo** — `gh repo view <owner/repo>` fails → `gh repo create <owner/repo> --private -d "Backup of <folder-name>"`. PRIVATE always; public only on an explicit user order in chat.
3. **Git wiring** (idempotent) — `git init -b main` if no repo; verify/set `remote origin git@github.com:<owner/repo>.git`; repo-local auth (this machine's default SSH key is a different account): set `git config core.sshCommand "ssh -i <key> -o IdentitiesOnly=yes"` + `user.name` + `user.email` with the account/key facts from `~/.agents/user/profile/identity.md` (single source — never hardcode here).
4. **Secret gate** (fail-closed, same patterns as push-skillbook.sh) — `rg` for `sk-ant-…|gh[pousr]_…|github_pat_…|hf_…|xox[baprs]-…|AKIA…|xai-…|sk-proj-…|AIza…|PRIVATE KEY`; any hit → STOP, show hits, never push. Tracked `auth.json`/`.env*`/`credentials*`/`*.pem`/`id_rsa*` → move to `.gitignore`, never commit.
5. **Sync + push** — `git add -A`; single commit `Backup <YYYY-MM-DD HH:MM>` (no AI attribution); `git push -u origin main`. Nothing staged but upstream behind → push the stranded commit. Nothing at all → report `in-sync`.

## Rules

- Explicit invocation only; one folder per run; never touch files outside the target folder.
- Setup never ends half-done: if any of stages 1–3 changed something, stages 4–5 run in the same pipeline (configure → verify → push, one flow).
- This is the generic 4th backup channel — the environment (`agents-setting-back-up`), clean distro (`clonamic-harness-full-package`), and skillbook keep their own dedicated pipelines.
- Report outcome-first, one line: `repo · commit-hash · pushed/in-sync` (failures shown plainly with the blocking stage).

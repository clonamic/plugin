---
name: clonamic-git-clean
description: "Find and remove AI traces (AI/bot Co-authored-by trailers, 'Generated with' footers, AI/bot author or committer identities) from git history. Runs only on the explicit /clonamic-git-clean command or a direct request such as '커밋 기록에서 AI 흔적 지워줘'. Rewrites unpushed commits after making a backup branch; pushed history only on the user's explicit instruction."
disable-model-invocation: true
user-invocable: true
---

# clonamic-git-clean — remove AI traces from history

Runs only on the explicit `/clonamic-git-clean` command or a direct user request; never on your own initiative.

Resolve `CLONAMIC_GIT_ROOT` to the plugin directory two levels above this `SKILL.md` (it contains `scripts/`). Scripts need Python 3.12+ (standard library only); if `python3` is older, install 3.12 (`uv python install 3.12` or the OS package manager) instead of falling back. Below, `$STRIP` = `python3 "$CLONAMIC_GIT_ROOT/scripts/strip_ai_trailers.py"` and `$SCAN` = `python3 "$CLONAMIC_GIT_ROOT/scripts/scan_history.py"`.

## Scope

- **Default: unpushed commits of the current branch only** — `@{upstream}..HEAD`, or `<branch> --not --remotes` when the branch has no upstream.
- **Pushed commits** (anything reachable from a remote ref) are rewritten only when the user explicitly says so in this conversation (for example "푸시된 커밋까지 정리해"). Then follow "Pushed history" below.
- Never use `git filter-repo` or other tools that are not part of git unless the user already has them and asks.

## Procedure — unpushed history

1. **Preflight.** Abort with a plain message if a rebase/merge/cherry-pick is in progress. `git status --porcelain` must be empty; otherwise ask the user to commit or stash first (do not stash on your own).
2. **Scan.** `$SCAN --json` (default range). Exit 0 → report "정리할 AI 흔적 없음" and stop. Exit 2 → report the git error and stop.
3. **Identity.** If any finding is an `author`/`committer` `ai-identity`, run `$SCAN --check-identity`; the replacement identity must be the user's verified identity (ask if it is missing or not clearly theirs). Collect the exact AI emails found.
4. **Backup.** `git branch clonamic-backup/<branch>-<YYYYMMDD-HHMMSS> HEAD`. Never skip this.
5. **Rewrite.** Same tree, new messages (and identities if step 3 found any):

   ```bash
   FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f \
     --msg-filter '$STRIP --quiet' \
     --env-filter 'case "$GIT_AUTHOR_EMAIL" in <ai-email-1>|<ai-email-2>) GIT_AUTHOR_NAME="<user name>"; GIT_AUTHOR_EMAIL="<user email>";; esac
                   case "$GIT_COMMITTER_EMAIL" in <ai-email-1>|<ai-email-2>) GIT_COMMITTER_NAME="<user name>"; GIT_COMMITTER_EMAIL="<user email>";; esac' \
     -- '@{upstream}..<branch>'            # no upstream: -- <branch> --not --remotes
   ```

   Expand `$STRIP` to the absolute command inside the quotes. Omit `--env-filter` when no identity needs fixing. If local tags point at rewritten commits, add `--tag-name-filter cat` and list those tags after `--`; recreate an annotated tag whose own message has attribution with `git tag -f -a <tag> <commit> -F <cleaned message>`.
6. **Verify.** `git diff --quiet <backup> HEAD` (exit 0: content unchanged) and `$SCAN` (exit 0). Either fails → `git reset --hard <backup>` and report the failure.
7. **Tidy.** `git update-ref -d refs/original/refs/heads/<branch>`; remove a leftover `.git-rewrite/` directory. Keep the backup branch and tell the user how to delete it (`git branch -D clonamic-backup/…`). Other local branches that contain the old commits still point at them — list them.

## Pushed history (explicit instruction only)

Before rewriting, tell the user in Korean, once, and wait for a yes:

- 원격 기록을 바꾸므로 `--force-with-lease` 푸시가 필요하고, 같은 브랜치를 쓰는 사람은 다시 받아야(reset/re-clone) 합니다.
- 열린 PR·포크·GitHub 캐시에는 예전 커밋이 남을 수 있고, 완전 삭제는 GitHub 지원 요청이 필요할 수 있습니다. Contributors 표시는 반영까지 최대 약 24시간 걸립니다.
- 보호 브랜치는 강제 푸시가 막혀 있을 수 있습니다.

Then run the same procedure with the range the user named (for example `-- <first-bad>^..<branch>` or `-- <branch>` for the whole branch), and push with `git push --force-with-lease=<branch>:<old remote sha> origin <branch>`. Never force-push a branch the user did not name.

## GitHub texts (on request)

PR bodies and release notes are not git history. When the user asks, scan them with `gh pr view N --json body -q .body | $STRIP --check` and `gh release view <tag> --json body -q .body | $STRIP --check`, then update with `gh pr edit N --body-file <clean>` / `gh release edit <tag> --notes-file <clean>`. Keep every non-attribution line.

## Report examples (Korean)

```text
AI 흔적 정리 완료 (feature/login, 푸시 안 된 커밋 3개)
- 제거: Co-authored-by: Claude … 2줄, Generated with [Codex] … 1줄
- 작성자 교체: cursoragent@cursor.com → 김사용자 <kim@example.com> (1개 커밋)
- 내용 변경 없음 확인 (git diff 비어 있음), 재검사 통과
- 백업: clonamic-backup/feature-login-20261005-142210 (확인 후 `git branch -D`로 삭제)
```

```text
푸시된 커밋 5개에도 AI 트레일러가 있습니다. 기본 설정상 푸시된 기록은 고치지 않았습니다.
정리하려면 "푸시된 커밋까지 정리해"라고 말씀해 주세요. 강제 푸시가 필요합니다.
```

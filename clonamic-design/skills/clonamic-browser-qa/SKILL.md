---
name: clonamic-browser-qa
description: Drive a real browser to verify a web UI — open pages, run user flows, capture screenshots across viewports, read console and network errors, walk keyboard focus, emulate reduced motion and dark mode, run an accessibility scan, and compare against a reference image. Uses the host's own browser tool when present, otherwise Playwright from the project or through npx. Use for visual QA, screenshots, flow checks, reproducing a UI bug, or as the evidence step of UI design and review.
---

# Clonamic Browser QA

Turn "it should look right" into screenshots, logs, and pass/fail checks from a real browser.

## 1. Choose the driver

Use the first that is available:

1. **The host's browser tool** (a browser-control or preview tool exposed to the agent). Best for
   interactive exploration and quick screenshots.
2. **The project's Playwright** — `@playwright/test` or `playwright` already in `package.json`.
   Use its config, its pinned version, and its test runner for repeatable checks.
3. **Playwright through npx** for a one-off run: `npx playwright screenshot …`, or a scratch
   install for scripted flows (see [playwright-recipes.md](references/playwright-recipes.md)).
   This downloads the package and a browser build (~150 MB) on first use: tell the user once and
   follow the host's approval rules for network and installs.

Always use a fresh browser context. Never drive or modify the user's personal browser profile,
cookies, or extensions unless they asked for exactly that.

## 2. Start the target

- Dev server: the project's own script (`npm run dev`, etc.) in the background. Note the port and
  process, wait until the URL answers, and stop it at the end.
- Static files: `python3 -m http.server <port> --directory <dir>` or opening the file URL.
- Remote URL: only one the user gave or the project documents.

## 3. Plan the checks

Write a short matrix before running anything: page or flow × viewport × state. Defaults:

- Viewports 375×812, 768×1024, 1440×900; full-page screenshots.
- States: default, hover/focus on the primary action, an open menu or dialog, empty, error,
  loading where reachable; dark mode and `reducedMotion: 'reduce'` when supported.

## 4. Run

- Navigate, then wait for a visible outcome (a heading, a role, network idle) — not fixed sleeps.
- For flows, act through roles and labels (`getByRole`, `getByLabel`), and assert the visible
  result after each step.
- Collect console errors, page exceptions, and failed requests (status ≥ 400) for every page.
- Keyboard pass: Tab through the page, record the focused element and whether a ring is visible.
- Optional accessibility scan with axe through npm at run time; report rule ids and node counts.
- Reference comparison: same viewport and state as the reference, then a pixel diff or a careful
  side-by-side; list differences by region.

## 5. Look at the evidence

Open each screenshot and inspect it: overflow, clipping, overlap, unreadable text, missing images
or fonts, layout shift, focus visibility. A screenshot you did not look at is not evidence.

## 6. Clean up

Stop servers and browsers you started. Save artifacts in a temporary directory or the location the
user named; do not create new top-level folders in the repository.

## Report format (user-facing, Korean)

```markdown
## 브라우저 QA 결과 — 회원가입 흐름 (Chromium, Playwright 1.x)

| 확인 항목 | 375 | 768 | 1440 | 비고 |
|---|---|---|---|---|
| 첫 화면 렌더 | 통과 | 통과 | 통과 | |
| 이메일 형식 오류 표시 | 통과 | 통과 | 통과 | 오류 문구가 입력란 아래에 표시됨 |
| 가입 완료 이동 | 실패 | 통과 | 통과 | 375px에서 약관 체크박스가 버튼에 가려짐 |
| 콘솔 오류 | 1건 | 1건 | 1건 | `favicon.ico` 404 |

- 키보드: 모든 입력란과 버튼에 포커스 링 표시, 순서 정상.
- 산출물: `/tmp/qa-signup/` 스크린샷 9장, 콘솔 로그 1개.
- 확인하지 못한 항목: Safari(WebKit) 미실행.
```

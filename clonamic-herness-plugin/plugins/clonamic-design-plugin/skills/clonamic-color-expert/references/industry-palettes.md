# Industry & brand-mood palettes (reference data, not a token source)

Source: 업종별 웹사이트 컬러 가이드 — <https://cool-mint-391.notion.site/3b0cd7df65e08103bafdc3d0babc2389>,
published by 에이원 스튜디오 (<https://aewonstudio.com/>). Retrieved 2026-08-02.

**What this is.** A positioning map: which mood an industry's customers expect, and which
direction to avoid. It is marketing content from a studio, not a standards document. The hex
values and the industry→mood mapping are reproduced as data; the pitfall notes are restated in
our own words.

**What this is NOT.** An accessible token set. Measured against the source's own role
assignment (background = page, main = headings/header/footer, accent = buttons and links),
**8 of 28 role pairs fail WCAG AA**. Those pairs are marked non-shippable below.

## Hard rules when citing this file

1. Use it to pick a DIRECTION. Never emit a source hex into a role marked FAIL.
2. Ship the repaired value instead, and say in the report that it was repaired and why.
3. A filled accent button needs an explicit label token — black or white, whichever passes.
   The source never states this and the wrong default fails in four of the seven moods.
4. Re-measure after any substitution. These numbers describe THESE hexes only.
5. The project's existing color system always wins; this is a starting point, not a migration.

## Mood palettes — measured

`제목` = main on background (large text, needs 3.0). `링크` = accent on background (normal
text, needs 4.5). `버튼면` = accent as a UI surface (needs 3.0). `라벨` = best of black/white
on the accent (needs 4.5).

| 무드 | 메인 | 배경 | 포인트 | 제목 | 링크 | 버튼면 | 라벨 |
|---|---|---|---|---|---|---|---|
| 고급스러움 | `#171412` | `#EFEAE1` | `#A88A5C` | 15.30 OK | 2.72 **FAIL** | 2.72 **FAIL** | 5.80 검 |
| 전문성·신뢰 | `#12304F` | `#F2F5F8` | `#3B7DD8` | 12.29 OK | 3.76 **FAIL** | 3.76 OK | 4.60 검 |
| 산업 신뢰 | `#2B3138` | `#EDF0F3` | `#0E7BC4` | 11.48 OK | 3.95 **FAIL** | 3.95 OK | 4.52 흰 |
| 친근함 | `#FF7A45` | `#FFF4EC` | `#3E2A20` | 2.39 **FAIL** | 12.46 OK | 12.46 OK | 13.49 흰 |
| 감성·부드러움 | `#C9A9A0` | `#FAF6F2` | `#7C6E66` | 2.02 **FAIL** | 4.56 OK | 4.56 OK | 4.91 흰 |
| 미래 지향 | `#6C4CF1` | `#0C0C16` | `#E9E9F2` | 3.65 OK | 16.12 OK | 16.12 OK | 15.65 검 |
| 자연·건강 | `#5F7255` | `#F4F1E8` | `#B9A77F` | 4.62 OK | 2.09 **FAIL** | 2.09 **FAIL** | 8.00 검 |

- **고급스러움** (luxury) — Desaturate to read as expensive.
- **전문성·신뢰** (professional trust) — The safest pairing for licensed professions.
- **산업 신뢰** (industrial B2B) — Greys carry a sense of scale.
- **친근함** (friendly) — Body copy in deep brown, not black.
- **감성·부드러움** (soft) — Remove the vivid hues and it softens.
- **미래 지향** (future) — A darker canvas reads as newer.
- **자연·건강** (natural) — Beige instead of pure white.

## Repairs for the failing pairs (lightness only, hue and saturation kept)

Repairs clear the threshold by at least 0.1 so rounding cannot put them back under.

| 무드 | 역할 | 원본 | 현재 | 수리값 | 수리 후 | ΔL |
|---|---|---|---|---|---|---|
| 고급스러움 | 링크 | `#A88A5C` | 2.72 | `#7C6542` | 4.62 | 13.6%p |
| 고급스러움 | 버튼면 | `#A88A5C` | 2.72 | `#9D8054` | 3.10 | 3.7%p |
| 전문성·신뢰 | 링크 | `#3B7DD8` | 3.76 | `#296DCC` | 4.62 | 5.9%p |
| 산업 신뢰 | 링크 | `#0E7BC4` | 3.95 | `#0D70B3` | 4.61 | 3.6%p |
| 친근함 | 제목 | `#FF7A45` | 2.39 | `#FF4A02` | 3.11 | 13.1%p |
| 감성·부드러움 | 제목 | `#C9A9A0` | 2.02 | `#B08275` | 3.10 | 13.3%p |
| 자연·건강 | 링크 | `#B9A77F` | 2.09 | `#7C6A44` | 4.65 | 23.6%p |
| 자연·건강 | 버튼면 | `#B9A77F` | 2.09 | `#9C8655` | 3.12 | 13.8%p |

The 자연·건강 link repair moves lightness by the most; at that distance the palette visibly
changes, so treat it as a design decision to surface, not a silent substitution.

## Industry → mood

### 전문 · 금융

| 업종 | 무드 | 메인 | 피할 것 |
|---|---|---|---|
| 변호사 · 법무법인 | 전문성·신뢰 | `#12304F` | Neon or pastel reads as unserious. |
| 세무사 · 회계사 | 전문성·신뢰 | `#12304F` | Do not run several saturated hues at once. |
| 노무사 · 행정사 | 전문성·신뢰 | `#12304F` | A faint grey canvas beats pure white. |
| 경영 · 전략 컨설팅 | 고급스러움 | `#171412` | Blue alone makes it look like a bank. |
| 부동산 · 중개 | 전문성·신뢰 | `#12304F` | Red emphasis signals a distress sale. |
| 보험 · 재무설계 | 전문성·신뢰 | `#12304F` | Avoid pairing green with red. |

### 의료 · 건강

| 업종 | 무드 | 메인 | 피할 것 |
|---|---|---|---|
| 병원 · 의원 | 전문성·신뢰 | `#12304F` | Red suggests blood; keep it out. |
| 치과 | 전문성·신뢰 | `#12304F` | A saturated sky blue reads childish; raise the white. |
| 한의원 | 자연·건강 | `#5F7255` | Brown on its own looks dated. |
| 약국 · 건강기능식품 | 자연·건강 | `#5F7255` | Fluorescent green reads cheap. |
| 요가 · 필라테스 | 감성·부드러움 | `#C9A9A0` | A black canvas reads cold here. |
| 헬스 · PT | 미래 지향 | `#6C4CF1` | Stop at three colors. |

### 뷰티 · 라이프

| 업종 | 무드 | 메인 | 피할 것 |
|---|---|---|---|
| 에스테틱 · 피부관리 | 감성·부드러움 | `#C9A9A0` | Hot pink reads cheap. |
| 헤어 · 네일 살롱 | 고급스러움 | `#171412` | The work photos lead; the canvas recedes. |
| 화장품 브랜드 | 감성·부드러움 | `#C9A9A0` | Too many hues and the product disappears. |
| 공방 · 원데이클래스 | 자연·건강 | `#5F7255` | Beige is warmer than white here. |

### F&B · 로컬

| 업종 | 무드 | 메인 | 피할 것 |
|---|---|---|---|
| 카페 · 베이커리 | 친근함 | `#FF7A45` | Deep brown copy suits it better than black. |
| 파인다이닝 · 레스토랑 | 고급스러움 | `#171412` | A bright canvas lowers the perceived price. |
| 식품 · 푸드 브랜드 | 자연·건강 | `#5F7255` | Do not port packaging primaries straight to the web. |
| 소품샵 · 리빙 | 자연·건강 | `#5F7255` | Clashing with product photography kills both. |

### 교육 · 콘텐츠

| 업종 | 무드 | 메인 | 피할 것 |
|---|---|---|---|
| 학원 · 과외 | 전문성·신뢰 | `#12304F` | Fluorescents make it look like a worksheet. |
| 온라인 강의 · 코칭 | 친근함 | `#FF7A45` | Cold hues suppress the signup click. |
| 유아 · 키즈 | 친근함 | `#FF7A45` | A full rainbow reads as disorganised. |
| 사진 · 영상 스튜디오 | 고급스러움 | `#171412` | No color outside the work itself. |

### 기술 · B2B

| 업종 | 무드 | 메인 | 피할 것 |
|---|---|---|---|
| IT · SaaS · 앱 | 미래 지향 | `#6C4CF1` | Dark mode is the default expectation. |
| AI 서비스 | 미래 지향 | `#6C4CF1` | Violet plus teal is the common look; avoid both together. |
| 제조 · 부품 · 엔지니어링 | 산업 신뢰 | `#2B3138` | Greys carry the sense of scale. |
| 물류 · 유통 | 산업 신뢰 | `#2B3138` | Keep orange to the accent role only. |
| 건축 · 인테리어 | 고급스러움 | `#171412` | Drawings and photography lead. |
| 디자인 · 마케팅 에이전시 | 고급스러움 | `#171412` | Chasing every trend erases the identity. |

When the mood the user wants and the mood their industry expects disagree, follow the
industry — that is the source's own advice and it matches how the audience reads the page.

## Tools the source recommends

Coolors (build and lock a palette) · Realtime Colors (see it applied to a real layout) ·
WebAIM Contrast Checker (verify a pair). None are required here — this skill computes
contrast offline, and the network boundary in SKILL.md still applies.

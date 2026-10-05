# Playwright recipes

Use the project's Playwright version when it has one. Otherwise pick a current release, pin it in
the commands, and name it in the report.

## Quick screenshots with no install step

```bash
npx -y playwright@<version> install chromium
npx -y playwright@<version> screenshot --viewport-size "375, 812" --full-page http://localhost:5173 /tmp/qa/home-375.png
npx -y playwright@<version> screenshot --viewport-size "1440, 900" --color-scheme dark http://localhost:5173 /tmp/qa/home-1440-dark.png
```

`--wait-for-selector <css>` waits for content; `npx playwright pdf <url> <file>` prints a PDF.

## Scratch install for scripted checks

Keep it outside the repository; nothing is added to the project.

```bash
QA=/tmp/qa-run && mkdir -p "$QA"
npm install --prefix "$QA" --no-save playwright@<version>
"$QA/node_modules/.bin/playwright" install chromium
node "$QA/check.mjs"   # script saved inside $QA so `import 'playwright'` resolves
```

## Screenshot matrix with console and network capture

```js
// check.mjs
import { chromium } from 'playwright';

const url = process.env.URL ?? 'http://localhost:5173/';
const out = process.env.OUT ?? '/tmp/qa-run';
const viewports = [[375, 812], [768, 1024], [1440, 900]];
const problems = [];

const browser = await chromium.launch();
for (const [width, height] of viewports) {
  for (const colorScheme of ['light', 'dark']) {
    const context = await browser.newContext({ viewport: { width, height }, colorScheme, reducedMotion: 'reduce' });
    const page = await context.newPage();
    page.on('console', (m) => m.type() === 'error' && problems.push(`console ${width}: ${m.text()}`));
    page.on('pageerror', (e) => problems.push(`exception ${width}: ${e.message}`));
    page.on('response', (r) => r.status() >= 400 && problems.push(`http ${r.status()} ${r.url()}`));
    await page.goto(url, { waitUntil: 'networkidle' });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    if (overflow) problems.push(`horizontal overflow at ${width}px`);
    await page.screenshot({ path: `${out}/page-${width}-${colorScheme}.png`, fullPage: true });
    await context.close();
  }
}
await browser.close();
console.log(problems.length ? problems.join('\n') : 'no problems captured');
```

## Flow with visible assertions

```js
const page = await (await browser.newContext()).newPage();
await page.goto(`${url}signup`);
await page.getByLabel('이메일').fill('not-an-email');
await page.getByRole('button', { name: '가입하기' }).click();
await page.getByText('올바른 이메일 주소를 입력하세요').waitFor({ timeout: 5000 });
await page.getByLabel('이메일').fill('qa@example.com');
await page.getByRole('button', { name: '가입하기' }).click();
await page.waitForURL('**/welcome');
```

Each `waitFor` / `waitForURL` throws on failure — catch it, screenshot, and record the step.

## Keyboard focus walk

```js
for (let i = 0; i < 40; i++) {
  await page.keyboard.press('Tab');
  const info = await page.evaluate(() => {
    const el = document.activeElement;
    const style = getComputedStyle(el);
    return { tag: el.tagName, name: el.getAttribute('aria-label') ?? el.textContent?.trim().slice(0, 40),
             ring: style.outlineStyle !== 'none' || style.boxShadow !== 'none' };
  });
  console.log(i, info);
}
```

## Accessibility scan (run-time dependency)

```bash
npm install --prefix "$QA" --no-save @axe-core/playwright
```

```js
import AxeBuilder from '@axe-core/playwright';
const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze();
for (const v of result.violations) console.log(v.impact, v.id, v.nodes.length);
```

Automated scans find a fraction of issues; keep the manual keyboard and contrast checks.

## Comparing with a reference image

- Inside a Playwright test project: `await expect(page).toHaveScreenshot('home.png', { maxDiffPixelRatio: 0.01 })`.
- Ad hoc: install `pixelmatch` and `pngjs` into the scratch folder, render at the reference's exact
  viewport and device scale factor, and write a diff image. Mask dynamic regions (dates, avatars)
  before comparing.

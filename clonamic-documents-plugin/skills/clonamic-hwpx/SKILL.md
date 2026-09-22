---
name: clonamic-hwpx
description: "Create, read, inspect, convert, or edit Korean HWPX documents, including text, tables, images, templates, and legacy HWP conversion. Use for HWPX, HWP, 한글, 한컴, or Hancom document tasks."
---

# HWPX creation, editing, and analysis

Resolve `HWPX_SKILL_ROOT` to the host-provided directory containing this
`SKILL.md`. Every bundled Python helper must run from that root, even when the
user's current directory is another project. Never scan vendor-specific home
directories or execute a same-named project script.

## Overview

A .hwpx file is a ZIP archive containing XML files, based on the OWPML (Open Word-Processor Markup Language) standard (KS X 6101).

## Quick Reference

| Task | Approach |
|------|----------|
| Read/analyze content | `hwpxjs` or unpack for raw XML |
| Create new document | Use `hwpxjs` - see Creating New Documents below |
| Edit existing document | Unpack → edit XML → repack - see Editing Existing Documents below |
| **Insert images** | **Use lxml with complete hp:pic structure** - see [references/image-insertion.md](references/image-insertion.md) |

### Converting .hwp to .hwpx

Legacy `.hwp` files must be converted before editing:

```bash
# Use only an existing project-local CLI
test -x ./node_modules/.bin/hwpxjs
./node_modules/.bin/hwpxjs convert:hwp document.hwp output.hwpx

```

Do not use LibreOffice as an HWP→HWPX fallback. Its legacy Hangul filter does
not provide a reliable HWPX export path and may silently corrupt newer input.

### Reading Content

```bash
# Text extraction via an existing project-local CLI
./node_modules/.bin/hwpxjs txt document.hwpx

# HTML conversion (includes images/styles)
./node_modules/.bin/hwpxjs html document.hwpx > output.html

# Raw XML access
python "$HWPX_SKILL_ROOT/scripts/unpack.py" document.hwpx unpacked/
```

### Rendering

This package does not claim a portable HWPX→PDF or image renderer. Use only a
renderer that the host has positively identified and validated on a disposable
copy of the actual document. Otherwise report visual rendering unavailable and
continue with structural validation.

---

## Creating New Documents

Generate `.hwpx` files with an already installed project-local `@ssabrojs/hwpxjs`. If it is
missing, report the unavailable runtime. Installation is a separate setup mutation: only after an
explicit setup request, select and record an exact approved version, then run
`npm install --save-exact @ssabrojs/hwpxjs@<approved-version>`.

### Setup
```javascript
const { HwpxWriter, HwpxReader } = require("@ssabrojs/hwpxjs");
const fs = require("fs");

// Create document from plain text
const writer = new HwpxWriter();
const content = `문서 제목

첫 번째 문단입니다.
두 번째 문단입니다.`;

const buffer = await writer.createFromPlainText(content);
fs.writeFileSync("output.hwpx", buffer);
```

### Reading Documents

```javascript
const { HwpxReader } = require("@ssabrojs/hwpxjs");
const fs = require("fs");

const reader = new HwpxReader();
const fileBuffer = fs.readFileSync("document.hwpx");
const boundedBuffer = fileBuffer.buffer.slice(
  fileBuffer.byteOffset,
  fileBuffer.byteOffset + fileBuffer.byteLength,
);
await reader.loadFromArrayBuffer(boundedBuffer);

// Extract text
const text = await reader.extractText();
console.log(text);

// Get document info
const info = await reader.getDocumentInfo();
console.log(info);

// List images
const images = await reader.listImages();
console.log(images);
// [{ binPath: "BinData/0.jpg", width: 200, height: 150, format: "jpg" }]
```

### HTML Conversion

```javascript
// Basic HTML conversion
const html = await reader.extractHtml();

// With all options
const fullHtml = await reader.extractHtml({
  paragraphTag: "p",
  tableClassName: "hwpx-table",
  renderImages: true,       // Include images
  renderTables: true,       // Include tables
  renderStyles: true,       // Apply styles (bold, italic, color)
  embedImages: true,        // Base64 embed images
  tableHeaderFirstRow: true // First row as <th>
});
```

### HWP to HWPX Conversion

```javascript
const { HwpConverter } = require("@ssabrojs/hwpxjs");

const converter = new HwpConverter({ verbose: true });

// Check availability
if (converter.isAvailable()) {
  // Convert HWP to HWPX
  const result = await converter.convertHwpToHwpx("input.hwp", "output.hwpx");
  if (result.success) {
    console.log(`Converted: ${result.processingTime}ms`);
  }

  // Or extract text only
  const text = await converter.convertHwpToText("input.hwp");
}
```

### Template Processing

```javascript
// hwpxjs supports {{key}} template replacement
const reader = new HwpxReader();
await reader.loadFromArrayBuffer(templateBuffer);

// Apply template replacements
const html = await reader.extractHtml();
const result = html
  .replace(/\{\{name\}\}/g, "홍길동")
  .replace(/\{\{date\}\}/g, "2025-01-01");
```

### Critical Rules for hwpxjs

- **createFromPlainText returns Buffer** - save with `fs.writeFileSync(path, buffer)`
- **loadFromArrayBuffer for reading** - pass the bounded slice from `byteOffset` through `byteLength`, never the raw pooled `fileBuffer.buffer`
- **Text-only creation** - for tables/images, use XML editing approach below
- **HwpConverter for HWP files** - pure TypeScript, no LibreOffice needed
- **extractHtml for rich content** - includes styles, tables, images

---

## Editing Existing Documents

**Follow all 3 steps in order.**

### Step 1: Unpack
```bash
python "$HWPX_SKILL_ROOT/scripts/unpack.py" document.hwpx unpacked/
```

### Step 2: Edit XML

Edit files in `unpacked/Contents/`. See XML Reference below for patterns.

**Use the Edit tool directly for string replacement. Do not write Python scripts.** Scripts introduce unnecessary complexity. The Edit tool shows exactly what is being replaced.

**CRITICAL: Remove `<hp:linesegarray>` when modifying text.** This element contains cached layout data. Leaving stale linesegarray causes character overlap:

```xml
<!-- BEFORE: paragraph with stale layout cache -->
<hp:p id="0" paraPrIDRef="0" styleIDRef="0">
  <hp:run charPrIDRef="19">
    <hp:t>Original text</hp:t>
  </hp:run>
  <hp:linesegarray>
    <hp:lineseg textpos="0" vertpos="0" vertsize="1000" horzsize="5000" .../>
  </hp:linesegarray>
</hp:p>

<!-- AFTER: remove linesegarray entirely -->
<hp:p id="0" paraPrIDRef="0" styleIDRef="0">
  <hp:run charPrIDRef="19">
    <hp:t>New longer text that exceeds original width</hp:t>
  </hp:run>
</hp:p>
```

**Note**: Multiple `<hp:run>` elements share one `<hp:linesegarray>`. Remove it when editing ANY run in the paragraph.

### Step 3: Pack
```bash
python "$HWPX_SKILL_ROOT/scripts/pack.py" unpacked/ output.hwpx
```

### Common Pitfalls

- **Character overlap after edit**: Remove `<hp:linesegarray>` from the edited `<hp:p>`. Multiple `<hp:run>` elements share one linesegarray—remove it when editing ANY run.
- **Wrong table cell modified**: Include `<hp:cellAddr>` in search pattern. **CRITICAL: `<hp:cellAddr>` appears AFTER cell content, not before.** Use `grep -B20 'colAddr="2" rowAddr="0"' section0.xml`.
- **Preserve `charPrIDRef`**: Don't change charPrIDRef when editing text—it references font/size/style in header.xml.
- **File corruption from string replacement**: Use lxml for structural changes (inserting elements). String replacement breaks XML parent-child relationships.
- **Page overflow from text replacement**: Replacing blanks/spaces with text can cause content overflow and page breaks. Solutions: (1) Keep replacement text similar in length to original spaces, (2) Preserve charPrIDRef for underlined fields to maintain underline style, (3) Reduce unnecessary whitespace proportionally, (4) Cell/margin adjustments may be needed.
- **Image size too large (e.g., 635mm)**: HWP unit calculation error. 1 HWP unit = 1/7200 inch, so **1mm ≈ 283.5 HWP units**.
  - ❌ Wrong: `width="180000"` → 635mm (too large!)
  - ✅ Correct: `width="3400"` → ~12mm (signature size)
  - Formula: `mm × (7200 ÷ 25.4) = HWP units`

---

## XML Reference

### Key Elements

| Element | Purpose |
|---------|---------|
| `<hp:p>` | Paragraph |
| `<hp:run>` | Text run with formatting |
| `<hp:t>` | Text content |
| `<hp:tbl>` | Table |
| `<hp:tc>` | Table cell |
| `<hp:cellAddr>` | Cell position (AFTER content) |
| `<hp:pic>` | Image |
| `<hp:linesegarray>` | Layout cache (remove when editing) |

Paragraph and table-cell XML structures live in [references/xml-reference.md](references/xml-reference.md) (avoids duplicating the reference here).

### Images

**⚠️ CRITICAL: Image insertion requires ALL 15 child elements in hp:pic. Missing elements cause crashes!**

See [references/image-insertion.md](references/image-insertion.md) for the **complete required structure**.

**Quick checklist for image insertion:**

1. Copy image file to `BinData/`
2. Add to manifest `Contents/content.hpf`:
```xml
<opf:item id="image1" href="BinData/image1.png" media-type="image/png" isEmbeded="1"/>
```
3. Insert complete `<hp:pic>` with ALL 15 elements (use lxml, not string replacement)

**Minimum required hp:pic elements** (in order):
1. `hp:offset` 2. `hp:orgSz` 3. `hp:curSz` 4. `hp:flip` 5. `hp:rotationInfo`
6. `hp:renderingInfo` 7. `hc:img` 8. `hp:imgRect` 9. **`hp:imgClip`** ⚠️
10. `hp:inMargin` 11. **`hp:imgDim`** ⚠️ 12. **`hp:effects`** ⚠️
13. `hp:sz` 14. `hp:pos` 15. `hp:outMargin`

**Size units:** HWP uses 1/7200 inch units. **1mm ≈ 283.5 units** (7200 ÷ 25.4)

### Page Break

```xml
<hp:p pageBreak="1" ...>  <!-- pageBreak="1" inserts break before paragraph -->
```

### Differences from DOCX

| Aspect | HWPX | DOCX |
|--------|------|------|
| Text element | `<hp:t>` | `<w:t>` |
| Paragraph | `<hp:p>` | `<w:p>` |
| Run | `<hp:run>` | `<w:r>` |
| Layout cache | `<hp:linesegarray>` | None |
| Content location | `Contents/section*.xml` | `word/document.xml` |
| Cell identifier | `<hp:cellAddr>` after content | implicit order |

**Key difference**: HWPX stores layout cache in linesegarray; DOCX doesn't. This is why editing HWPX requires removing linesegarray.

For detailed XML structures (headers/footers, lists/numbering, paragraph formatting), see [references/xml-reference.md](references/xml-reference.md).

---

## Dependencies

- **hwpxjs**: existing project-local exact version for reading, writing, HTML conversion, and
  HWP→HWPX conversion. Never invoke it through plain `npx` or install it implicitly.
- **Python standard library**: package/unpackage and structural validation helpers
- **lxml**: optional explicit runtime for structural image insertion examples

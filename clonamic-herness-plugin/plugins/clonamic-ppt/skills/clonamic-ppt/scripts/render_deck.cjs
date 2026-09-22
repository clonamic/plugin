#!/usr/bin/env node
/**
 * DeckIR → PPTX. No layout decisions here.
 */
const fs = require("fs");
const path = require("path");

function loadPptxgen() {
  const pluginRoot = path.resolve(__dirname, "../../..");
  const nodeModules = fs.realpathSync(path.join(pluginRoot, "node_modules")) + path.sep;
  const pptxResolved = require.resolve("pptxgenjs", { paths: [pluginRoot] });
  const pptxReal = fs.realpathSync(pptxResolved);
  if (!pptxReal.startsWith(nodeModules)) {
    throw new Error(`pptxgenjs must resolve inside ${nodeModules}`);
  }
  const imageResolved = require.resolve("image-size", { paths: [pluginRoot] });
  const imageReal = fs.realpathSync(imageResolved);
  const vendorImage = fs.realpathSync(path.join(pluginRoot, "vendor/image-size/index.js"));
  if (imageReal !== vendorImage) {
    throw new Error(`image-size must resolve to ${vendorImage}`);
  }
  return require(pptxResolved);
}

const PptxGenJS = loadPptxgen();

function parseArgs(argv) {
  const out = { input: null, out: null };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--input" || argv[i] === "-i") out.input = argv[++i];
    else if (argv[i] === "--out" || argv[i] === "-o") out.out = argv[++i];
    else if (!out.input) out.input = argv[i];
    else if (!out.out) out.out = argv[i];
  }
  if (!out.input || !out.out) {
    console.error("usage: render_deck.cjs --input deck_ir.json --out presentation.pptx");
    process.exit(2);
  }
  return out;
}

function mapShape(t) {
  const P = PptxGenJS;
  // instance has shapes after construct; use string names
  const m = {
    rect: "rect",
    round_rect: "roundRect",
    ellipse: "ellipse",
    line: "line",
    chevron: "chevron",
    arrow: "rightArrow",
  };
  return m[t] || "roundRect";
}

function renderElement(pptx, slide, el) {
  const { x, y, w, h } = el.bbox;
  if (el.kind === "text") {
    const st = el.style || {};
    const raw = String(el.text || "")
      .replace(/[\u2018\u2019\u201A\u2032]/g, "'")
      .replace(/[\u201C\u201D\u201E\u2033]/g, '"')
      .replace(/\u00A0/g, " ");
    slide.addText(raw, {
      x,
      y,
      w,
      h,
      objectName: el.element_id || "text",
      fontFace: st.font_family || "AppleGothic",
      fontSize: st.font_size_pt || 15,
      color: (st.color || "111827").replace("#", ""),
      bold: (st.weight || 400) >= 600,
      italic: !!st.italic,
      align: st.align || "left",
      valign: st.valign || "top",
      margin: 0,
      wrap: el.token_ref === "source" ? h > 0.34 : true,
      paraSpaceAfter: 0,
      lineSpacingMultiple: st.line_height || 1.2,
    });
  } else if (el.kind === "shape") {
    const fill = el.fill && el.fill.color ? el.fill.color.replace("#", "") : "FFFFFF";
    const fillT = el.fill && el.fill.transparency != null ? el.fill.transparency : 0;
    const line = el.stroke
      ? { color: el.stroke.color.replace("#", ""), width: el.stroke.width_pt || 0.6 }
      : { color: "FFFFFF", transparency: 100 };
    const opts = {
      x,
      y,
      w,
      h,
      objectName: el.element_id || "shape",
      fill: { color: fill, transparency: fillT },
      line,
    };
    if (el.shape_type === "round_rect") opts.rectRadius = el.radius_in == null ? 0.1 : el.radius_in;
    slide.addShape(mapShape(el.shape_type), opts);
  } else if (el.kind === "table") {
    const cols = el.columns || [];
    const rows = el.rows || [];
    const headerFill = (el.header_fill || "111827").replace("#", "");
    const headerColor = (el.header_color || "FFFFFF").replace("#", "");
    const bodyFill = (el.body_fill || "FFFFFF").replace("#", "");
    const altFill = (el.alt_fill || "F7F8FA").replace("#", "");
    const bodyColor = (el.body_color || "111827").replace("#", "");
    const borderColor = (el.border_color || "EEF1F4").replace("#", "");
    const header = cols.map((c) => ({
      text: String(c),
      options: { fill: { color: headerFill }, color: headerColor, bold: true, align: "left", valign: "middle" },
    }));
    const body = rows.map((r, ri) =>
      cols.map((_, i) => ({
        text: String((r && r[i]) || ""),
        options: {
          fill: { color: ri % 2 === 1 ? altFill : bodyFill },
          color: bodyColor,
          align: "left",
          valign: "middle",
        },
      }))
    );
    const colW = cols.length ? Array(cols.length).fill(w / cols.length) : [w];
    slide.addTable([header, ...body], {
      x,
      y,
      w,
      h,
      objectName: el.element_id || "table",
      colW,
      border: { pt: 0.6, color: borderColor },
      fontFace: "AppleGothic",
      fontSize: 13,
      valign: "middle",
    });
  } else if (el.kind === "chart") {
    const cats = el.categories || [];
    const series = (el.series || []).map((s) => ({
      name: s.name || "series",
      labels: cats,
      values: s.values || [],
    }));
    if (!series.length || !cats.length) return;
    const type = (el.chart_type || "bar") === "line" ? pptx.charts.LINE : pptx.charts.BAR;
    const highlight = new Set(el.highlight || []);
    const first = series[0] && series[0].values ? series[0].values : [];
    const peak = first.length ? Math.max(...first.map(Number)) : null;
    const accent = (el.accent || "2F6FED").replace("#", "");
    const dark = (el.accent_dark || "174EA6").replace("#", "");
    const chartColors = cats.map((c, i) => {
      if (highlight.has(c)) return dark;
      if (peak != null && Number(first[i]) === peak) return dark;
      return accent;
    });
    slide.addChart(type, series, {
      x,
      y,
      w,
      h,
      objectName: el.element_id || "chart",
      barDir: "bar",
      showValue: true,
      showLegend: series.length > 1,
      chartColors,
      chartArea: { fill: { color: "FFFFFF" } },
      valGridLine: { color: "EEF1F4", size: 0.5 },
      catGridLine: { style: "none" },
      catAxisLabelColor: "59636E",
      valAxisLabelColor: "59636E",
      dataLabelColor: "111827",
      fontFace: "AppleGothic",
    });
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const deck = JSON.parse(fs.readFileSync(args.input, "utf8"));
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Clonamic";
  pptx.title = deck.title || "Untitled";
  pptx.subject = deck.title || "";

  const slides = [...(deck.slides || [])].sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  for (const s of slides) {
    const slide = pptx.addSlide();
    slide.background = { color: (s.background_color || "FFFFFF").replace("#", "") };
    const els = [...(s.elements || [])].sort((a, b) => (a.z_index || 0) - (b.z_index || 0));
    for (const el of els) renderElement(pptx, slide, el);
    if (s.notes) slide.addNotes(s.notes);
  }

  const out = path.resolve(args.out);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  await pptx.writeFile({ fileName: out });
  console.log(out);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

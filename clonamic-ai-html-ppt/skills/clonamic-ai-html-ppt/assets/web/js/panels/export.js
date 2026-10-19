// PDF export dialog: scope, one file or one per page, target folder. Falls back to the print page
// when the server has no Chrome (503).

import { el, modal, toast, store as ls } from "../ui.js";

const DIR_KEY = "ppt-export-dir";

export function openExport(C, { pages: preset } = {}) {
  const pages = C.store.childIds(null);
  const fromPanel = Array.isArray(preset) ? pages.filter((id) => preset.includes(id)) : null;
  const marked = fromPanel?.length ? fromPanel : C.pages?.marked?.length ? C.pages.marked : C.selection.ids.filter((id) => C.store.get(id)?.type === "page");
  const radio = (name, value, label, checked, disabled) => el("label", { class: `radio${disabled ? " off" : ""}` },
    el("input", { type: "radio", name, value, checked: checked || null, disabled: disabled || null }), el("span", {}, label));
  const scope = el("fieldset", { class: "fs" }, el("legend", {}, "범위"),
    radio("scope", "current", "현재 페이지", !fromPanel?.length),
    radio("scope", "marked", `선택한 페이지${marked.length ? ` (${marked.length})` : ""}`, !!fromPanel?.length, !marked.length),
    radio("scope", "all", `전체 (${pages.length})`, false));
  const mode = el("fieldset", { class: "fs" }, el("legend", {}, "파일"),
    radio("mode", "single", "한 파일로", true), radio("mode", "each", "페이지마다 따로", false));
  const dir = el("input", { type: "text", value: ls(DIR_KEY) || "~/Downloads", "aria-label": "저장할 폴더", spellcheck: "false" });
  const out = el("div", { class: "export-out", "aria-live": "polite" });
  const pick = (name) => scope.parentElement.querySelector(`input[name="${name}"]:checked`)?.value;
  let btn = null;
  const body = el("div", { class: "form" }, scope, mode, el("label", {}, "저장할 폴더", dir), out);
  const m = modal({ title: "PDF로 내보내기", body, actions: [
    { label: "닫기" },
    { label: "내보내기", kind: "primary", ref: (b) => { btn = b; }, run: async () => {
      const sc = pick("scope");
      const ids = sc === "all" ? [] : sc === "marked" ? marked : [C.currentPage() || pages[0]].filter(Boolean);
      const folder = dir.value.trim() || "~/Downloads";
      ls(DIR_KEY, folder);
      btn.disabled = true;
      out.replaceChildren(el("p", { class: "dim" }, "내보내는 중…"));
      const r = await C.api.pdf(C.deckId, { pages: ids, mode: pick("mode"), dir: folder });
      btn.disabled = false;
      if (r.ok && Array.isArray(r.data?.files)) {
        out.replaceChildren(el("p", {}, `${r.data.files.length}개 파일을 저장했습니다.`),
          el("ul", { class: "files" }, ...r.data.files.map((f) => el("li", {}, el("code", {}, f),
            el("button", { type: "button", class: "small", on: { click: () => navigator.clipboard?.writeText(f).then(() => toast("경로를 복사했습니다."), () => {}) } }, "경로 복사")))));
        return false;
      }
      if (r.status === 503) {
        const list = (ids.length ? ids : pages).join(",");
        const w = window.open(`/print.html?deck=${encodeURIComponent(C.deckId)}&pages=${encodeURIComponent(list)}&auto=1`, "_blank");
        out.replaceChildren(el("p", {}, w ? "Chrome을 찾지 못해 인쇄 창을 열었습니다. 대상에서 ‘PDF로 저장’을 고르세요." : "팝업이 막혔습니다. 팝업을 허용한 뒤 다시 시도하세요."));
        return false;
      }
      out.replaceChildren(el("p", { class: "error" }, `내보내지 못했습니다: ${r.data?.error || r.status}`));
      return false;
    } },
  ] });
  return m;
}

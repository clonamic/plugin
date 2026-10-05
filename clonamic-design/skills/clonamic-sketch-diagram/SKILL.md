---
name: clonamic-sketch-diagram
description: Create an editable hand-drawn style diagram as an Excalidraw (.excalidraw) file — flowcharts, architecture sketches, explainers, sequence or state sketches, and low-fidelity wireframes — and check it with a deterministic validator for ids, bindings, overlaps, and text fit. Use when the user asks for Excalidraw or a hand-drawn/sketch look. Not when Mermaid, a polished vector diagram, or prose is enough, and not for product UI.
---

# Clonamic Sketch Diagram

The deliverable is a valid, editable `.excalidraw` file. An SVG or PNG preview is a bonus derived
from it.

## Procedure

1. **Answer the question first.** List what the diagram must show: nodes, relationships, the
   reading order (left→right or top→bottom), and the one thing the viewer should take away. Cut
   nothing that the user asked for; add nothing they did not need.
2. **Lay out on a grid.** Assign each node a cell (e.g. 200px columns, 140px rows); align ranks;
   keep 60px+ between nodes so arrows have room. Group with a dashed frame only when the group is
   real (a service boundary, a phase).
3. **Write the JSON** following [format.md](references/format.md): readable ids, one hand-drawn
   style (`roughness: 1`, `fontFamily: 1`), black strokes, at most one emphasis color unless the
   brief asks for more. Size every shape for its text. Labels stay horizontal and short.
4. **Route arrows** with bindings at both ends and bend points around shapes; arrows never cross a
   label, and every arrow has an obvious owner and direction. Label decision branches.
5. **Validate** — `python3 scripts/check_excalidraw.py <file>` (path relative to this skill's
   folder). Fix every ERROR; treat each WARN as a defect unless you can say why it is intended
   (for example, a node deliberately placed on a boundary frame).
6. **Preview when possible.** Open the file in an Excalidraw editor the user has, or render it in
   a browser page that loads Excalidraw's export utilities from npm or a pinned CDN at run time
   (check that package's current export API first) and screenshot the result via
   `clonamic-browser-qa`. Look at it: legibility, arrow clarity, nothing clipped or stacked. If no
   renderer is available, deliver the file and say the preview was not rendered.

## Report format (user-facing, Korean)

```markdown
## 다이어그램 — 주문 처리 흐름 (`order-flow.excalidraw`)

- 구성: 노드 9개(서비스 5, 결정 2, 외부 시스템 2), 화살표 11개, 좌→우 읽기 순서
- 검증: `check_excalidraw.py` 오류 0건, 경고 0건
- 미리보기: `order-flow.png` 렌더 후 겹침·잘림 없음 확인
- 편집: Excalidraw에서 파일을 열면 손그림 스타일 그대로 수정할 수 있습니다.
```

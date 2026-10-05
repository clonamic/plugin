# The .excalidraw file, in brief

A scene is one JSON object:

```json
{ "type": "excalidraw", "version": 2, "source": "clonamic", "elements": [], "appState": { "viewBackgroundColor": "#ffffff" }, "files": {} }
```

## Element fields you set by hand

| Field | Value |
|---|---|
| `id` | unique short string (`"box-api"`, `"arrow-api-db"`) — readable ids make edits easy |
| `type` | `rectangle`, `ellipse`, `diamond`, `text`, `arrow`, `line`, `frame` |
| `x`, `y`, `width`, `height` | pixels; `x`/`y` is the top-left corner |
| `strokeColor`, `backgroundColor` | hex, or `"transparent"` |
| `fillStyle` | `"solid"`, `"hachure"`, `"cross-hatch"` |
| `strokeWidth` | 1, 2, or 4 |
| `strokeStyle` | `"solid"`, `"dashed"`, `"dotted"` |
| `roughness` | 0 smooth, 1 sketchy (default for this look), 2 very rough |
| `opacity` | 0–100 |
| `seed` | any integer; fixes the hand-drawn wobble |
| `roundness` | `null` for sharp corners, `{ "type": 3 }` for rounded rectangles |
| `groupIds`, `boundElements`, `frameId` | `[]`, `[]` or `null`, `null` unless used |
| `isDeleted`, `locked` | `false` |
| `version`, `versionNonce`, `updated` | any integers; the editor rewrites them |

## Text

`text`, `originalText` (same string), `fontSize` (16–20 for labels, 28–36 for titles),
`fontFamily` (1 = hand-drawn face), `textAlign`, `verticalAlign`, `lineHeight` (1.25), and
`containerId` (`null` for free text).

**Text inside a shape:** the text has `containerId: "<shape id>"`, and the shape lists it:
`"boundElements": [{ "id": "<text id>", "type": "text" }]`. Center the text box inside the shape.
Size the shape for the text: about 0.6 × fontSize per Latin character and 1.0 × fontSize per Hangul
character, plus 20–40px padding.

## Arrows

`points` are relative to the arrow's `x`/`y`; the first point is `[0, 0]`. `width`/`height` equal
the points' extent. Connect ends with bindings, and list the arrow in each shape's `boundElements`
(`{ "id": "<arrow id>", "type": "arrow" }`):

```json
{
  "id": "arrow-api-db", "type": "arrow", "x": 260, "y": 140, "width": 120, "height": 0,
  "points": [[0, 0], [120, 0]],
  "startBinding": { "elementId": "box-api", "focus": 0, "gap": 6 },
  "endBinding": { "elementId": "box-db", "focus": 0, "gap": 6 },
  "startArrowhead": null, "endArrowhead": "arrow",
  "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
  "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "seed": 7,
  "groupIds": [], "boundElements": [], "frameId": null, "roundness": null,
  "isDeleted": false, "locked": false, "version": 1, "versionNonce": 1, "updated": 1
}
```

A label on an arrow is a text element whose `containerId` is the arrow id. Bends are extra points
(`[[0,0],[0,60],[140,60]]`) — use them to route around shapes instead of crossing them.

## Shape vocabulary

| Shape | Meaning |
|---|---|
| rectangle | step, service, component, screen |
| rounded rectangle | user-facing action or state |
| ellipse | start/end, actor, external system |
| diamond | decision (label the outgoing arrows) |
| dashed rectangle or frame | boundary, group, environment |
| line without heads | association or divider |

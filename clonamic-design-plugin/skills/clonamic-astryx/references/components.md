# Astryx Component Index + Themes (vendored snapshot)

Source: https://astryx.atmeta.com/components , https://astryx.atmeta.com/themes
Fetched: 2026-07-25
Status at fetch time: Beta, 150-160+ components advertised across marketing
copy; category listing below reflects the live index at fetch time.

Component props/behavior change between Beta releases — treat names here as
an index for discovery only. Get authoritative current props with
`astryx component <Name> --props --json` (see `cli-manifest.md`).

## Categories

- **Action** — Button, Button Group, Dropdown Menu, Icon Button, Link, More
  Menu, Segmented Control, Toggle Button, Toggle Button Group, Toolbar
- **Chat** — Chat Composer, Chat Layout, Chat Message, Chat Message
  Metadata, Chat System Message, Chat Tool Calls
- **Container** — Card, Carousel, Clickable Card, Collapsible, Selectable
  Card
- **Content** — Avatar, Avatar Group, Blockquote, Citation, Code, Code
  Block, Empty State, Heading, Icon, Kbd, Markdown, Text, Thumbnail,
  Timestamp, Token
- **Data Input** — Calendar, Checkbox Input, Date Input, Date Range Input,
  Date Time Input, Field, File Input, Multi Selector, Number Input, Power
  Search, Radio List, Selector, Slider, Switch, Text Area, Text Input, Time
  Input, Tokenizer, Typeahead, Typeahead Item
- **Feedback & Status** — Badge, Banner, Progress Bar, Skeleton, Spinner,
  Status Dot
- **Layout** — App Shell, Aspect Ratio, Divider, Form Layout, Grid, Layout,
  Resize Handle, Section
- **Navigation** — Breadcrumbs, Outline, Pagination, Side Nav, Tab List, Top
  Nav, Top Nav Mega Menu, Top Nav Mega Menu Featured Card, Top Nav Menu
- **Overlay** — Command Palette, Dialog, Hover Card, Lightbox, Overlay,
  Popover, Toast, Tooltip
- **Table & List** — List, Metadata List, Overflow List, Table, Tree List
- **Utility** — VisuallyHidden

Note: `Avatar`/`Avatar Group` size prop changed in v0.1.8 (abbreviated scale
`xsm/sm/md/lg/xl` replacing the prior values) — a concrete example of why
props must be re-checked live, not assumed from this list.

## Theme presets

Preset names appeared inconsistently across two official pages at fetch
time (`neutral, stone, gothic, matcha, y2k, butter, studio` per
`/themes`; `neutral, stone, gothic, matcha, y2k, butter, chocolate` per
`/docs/getting-started`) — confirm the current set with
`astryx docs theme` or `astryx theme --list` rather than trusting either
list here. `neutral` is the installed default. `gothic` is dark-only;
others support light/dark. Theming uses CSS custom properties; scaffold
with the CLI's theme command, edit the generated `defineTheme` file, then
`astryx theme build <file>` for production CSS.

## Other packages in the monorepo

- `@astryxdesign/core` — components, theme system, utilities
- `@astryxdesign/cli` — CLI tooling
- `@astryxdesign/build` — Babel/PostCSS/Vite plugins for StyleX source
  builds
- `@astryxdesign/theme-*` — theme packages
- `@astryxdesign/vega`, `@astryxdesign/charts` — chart components (canary
  only at fetch time)

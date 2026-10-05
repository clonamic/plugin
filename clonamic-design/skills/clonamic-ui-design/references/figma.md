# Working with Figma

Use the Figma tool the host already has connected (an MCP server or built-in integration). Read
its tool list first; tool names differ between integrations. If none is connected, say so and ask
for an exported PNG plus the key values (colors, fonts, spacing). Never guess file keys, node ids,
or values, and never install or register a Figma server yourself.

## Figma → code

1. Get the exact frame: design context or node data, variables/styles, and a rendered screenshot.
2. Map Figma variables and styles to the project's existing tokens. Where no token matches, add a
   semantic token rather than hard-coding the value.
3. Rebuild with the project's components, using auto-layout direction, gap, and padding as the
   flex/grid spec. Treat absolute coordinates as hints, not CSS.
4. Fill what the frame does not show — hover/focus/disabled states, responsive behavior, long
   text — using the project's system and the quality floor.
5. Screenshot the implementation at the frame's width and compare side by side with the Figma
   render. List any deliberate deviation and why.

## Writing into Figma

1. Inspect the document and page first; reuse existing frames, components, and styles.
2. Create the top frame with explicit size and a meaningful name; build children inside it with
   auto layout rather than manual coordinates.
3. Text: load the font, fix the text box width (or set it to auto width), then set content, then
   style. A box narrow enough to wrap one character per line is a bug.
4. Use sampled values from the reference, not approximations from memory.
5. Export the top frame as an image and look at it. Fix wraps, overlaps, misalignment, and
   clipping, then export again. A Figma task is not done until one clean export has been inspected.
6. Delete scratch nodes, group logically, and report the page and frame names.

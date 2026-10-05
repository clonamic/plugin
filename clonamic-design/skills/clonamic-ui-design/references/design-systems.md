# Choosing and using a design system

## 1. Find what already exists

Check before choosing anything: `package.json` dependencies (component and styling libraries),
Tailwind or theme config, token files (`tokens.*`, `theme.*`, CSS custom properties on `:root`),
a shared components folder, and font loading. If any system exists, use it and stop here. Never
migrate an existing UI to a different system as a side effect of a design task.

## 2. New project with no system

Choose by these criteria, in order:

1. **Framework fit** — native to the project's framework and rendering model (SSR, RSC, islands).
2. **Accessible primitives** — keyboard support, focus management, ARIA patterns for dialog, menu,
   combobox, tabs, and toast handled by the library.
3. **Styling model** — headless primitives when the brand needs its own look; a styled kit when
   speed matters more than identity. Theming must go through CSS variables or tokens.
4. **Health** — active maintenance, typed API, permissive license, reasonable bundle impact.

Verify the current API from the library's own documentation or CLI at run time (a docs tool if the
host has one); do not rely on remembered props. Pin an exact version. Installing is part of the
approved task scope — confirm with the user if the task did not already include it.

## 3. Token architecture

- **Primitive**: raw ramps (`blue-600`, `space-4`, `radius-2`).
- **Semantic**: roles (`accent`, `text-muted`, `surface-raised`, `space-section`).
- **Component**: only where a component must deviate (`button-primary-bg`).

Components consume semantic tokens. A theme switch (dark mode, brand variant) replaces semantic
values only.

Minimum set: color roles (see color-and-theme.md), type scale and families, spacing scale,
radius, shadow/elevation, motion durations and easings, z-index layers, breakpoints.

## 4. Component state checklist

Each interactive component defines default, hover, focus-visible, active/pressed, disabled,
loading, error, and (where relevant) selected and empty. Missing states are the most common
source of an unfinished look.

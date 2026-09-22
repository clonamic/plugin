---
name: clonamic-market
description: Match a requested capability to the smallest optional catalog plugin. Use for availability questions, not installation or activation.
---

# Clonamic Market

Read `../../catalog/plugins.json` and select the narrowest effective capability from explicit
caller- or host-supplied configuration, platform, installed-package, dependency, and runtime data.

Use `clonamic resolve-plugins` when the binary is available. Otherwise apply the same model-side
fallback: Core stays active; overlay only supplied config layers; require the package to be enabled,
supported on the named platform, installed, dependency-ready, and runtime-ready when declared.
Never search a home directory, assume installation, or treat an enabled toggle as runtime evidence.

- Prefer one plugin; add another only for a distinct uncovered capability.
- Report configured, installed, platform_supported, dependencies_ready, effective, reason, and manifest separately.
- Never infer installation or authority. A disabled plugin is unavailable; enabling grants nothing.
- If no catalog or match exists, state that without inventing a capability.

Return the plugin name, match, and resolver reason. Installation stays a platform action.

# Asset pipeline gate

- Use only repository-owned or properly licensed local models, textures, audio, and fonts.
- Preserve source-to-output provenance and deterministic export settings.
- Validate scale, axes, origin, UVs, animation clips, color space, alpha, and compression after export.
- Provide poster/static fallback and an explicit load/error state.
- Do not fetch a hosted Spline/Rive/Lottie/model asset during build or runtime unless the product already owns that dependency and the user permits online behavior.
- Never modify a global browser, Blender, package-manager, or MCP configuration to make an asset pipeline work.

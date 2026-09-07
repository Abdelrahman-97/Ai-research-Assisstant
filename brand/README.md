# Neura brand kit

Colours: teal `#0a6b63` · soft teal `#4cc2b6` · ink `#1a2b32` · off-white `#f4f6f6` · muted `#5f6f75`
Fonts: serif headlines (Georgia/Times), clean sans body (Arial/DejaVu Sans).

## Files
- `logo-icon-teal.png` — Facebook Page & Instagram **profile picture** (also app icon)
- `logo-icon-transparent.png` — teal mark for light backgrounds
- `logo-horizontal.png` — full "Neura RESEARCH" lockup (headers, docs)
- `facebook-cover.png` — Facebook **cover photo** (1640×624, mobile-safe)
- `template-post-*.png/.svg` — 1080×1080 feed posts (light + teal)
- `template-story-*.png/.svg` — 1080×1920 stories (light + teal), 12% safe margins
- `*.tokens.svg` — same templates with `{{HEADLINE}}` / `{{BODY}}` placeholders for automation

## Auto-generating a post (for the social-media tool)
1. Pick a template's `*.tokens.svg`.
2. Replace `{{HEADLINE}}` and `{{BODY}}` with the AI-written text (escape `&`, `<`, `>`).
3. Render to PNG at the template's width/height (e.g. `cairosvg`).
4. Publish the PNG to Facebook / Instagram / WhatsApp.

See `brand-kit.json` for the machine-readable spec.

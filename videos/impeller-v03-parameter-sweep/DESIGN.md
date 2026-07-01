# Impeller v0.3 Parameter Sweep Video Design

## Style Prompt

Use a restrained engineering-review visual system: light technical canvas, graphite labels, muted green shaded metal, dark ink construction lines, and amber status accents. The video should feel like a deterministic CAD/geometry audit surface, not a product promo. The left side is dominated by the geometry; the right side is a compact instrument panel with live parameters and validity state.

## Colors

- Canvas: `#edf2ef`
- Panel: `#f8faf7`
- Frame stroke: `#b9c5be`
- Primary text: `#17211d`
- Secondary text: `#5d6b65`
- Shaded metal: `#70977f`
- Wire ink: `#123241`
- Accent amber: `#b86721`
- Valid green: `#1f7a5a`

## Typography

- Data and labels: `IBM Plex Mono`
- Section titles: `IBM Plex Mono`

## What NOT to Do

- Do not use neon, purple/blue gradients, decorative orbs, or marketing-style hero layouts.
- Do not show STL triangle edges; wireframe means surface UV and construction parameter lines.
- Do not use camera auto-rotation; geometry should be comparable across frames.
- Do not hide invalidity state; if a generated frame fails validity, the dashboard must show it.

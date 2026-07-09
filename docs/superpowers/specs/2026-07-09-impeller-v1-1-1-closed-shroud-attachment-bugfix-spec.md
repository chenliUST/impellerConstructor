# Impeller V1.1.1 Closed Shroud Attachment Bugfix Spec

Date: 2026-07-09

## Goal

Fix the V1.1.1 closed throughflow preset so the closed impeller topology is material-consistent:

- the outer shroud is a finite-thickness material shell, not only a single cover/reference surface;
- blade section loops stay inside the material domain between hub and shroud;
- closed blades have two attachment/root transitions: blade root to inner hub and blade tip to outer shroud;
- both attachment transitions have width/lift on the order of the average blade thickness, avoiding oversized bulges.

## Scope

This is a V1.1.1 bugfix. It does not introduce a new geometry version or replace the V1.1 blade-to-blade loop constructor.

## Geometry Contract

Closed shroud support must expose inspectable material surfaces:

- inner shroud flow surface from `tip_or_shroud_profile_rz_mm`;
- outer shroud material surface offset by `hood_wall_thickness_mm`;
- inlet and outlet shroud rim surfaces joining the inner and outer profiles.

Closed blade loops must use an effective span domain:

- lower span boundary is lifted from hub by `root_blade_lift_mm`;
- upper span boundary is inset from shroud by `shroud_blade_inset_mm`;
- the remaining blade domain must be positive and bounded.

The blade tip to shroud attachment must be treated as a second root-like transition:

- `closed_shroud_attachment` bridges the blade tip loop to the shroud inner surface;
- inset distance should be approximately the average blade thickness;
- quality metadata must report requested/min/max inset and pass/fail status.

## Preset Policy

The closed preset defaults should use attachment sizes near the average blade thickness:

- `average_blade_thickness_mm`: approximately 22 mm;
- `root_attachment_width_mm`: approximately 22 mm;
- `root_attachment_lift_mm`: approximately 22 mm;
- `root_blade_lift_mm`: approximately 22 mm;
- `shroud_blade_inset_mm`: approximately 22 mm;
- `hood_wall_thickness_mm`: remains a visible material thickness, about 24 mm.

## Tests

Add or extend tests so they fail if:

- closed shroud support is only a single surface;
- closed shroud material thickness is missing or not reflected in support surfaces;
- closed blade root or tip attachment distances fall outside a blade-thickness-scale band;
- closed blade loops exceed the hub-to-shroud material span domain.

## Out Of Scope

- exact production B-Rep sewing;
- new axial/mixed topology semantics;
- changing V1.1.1 open impeller root/tip rules.

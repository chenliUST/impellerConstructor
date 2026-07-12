# Impeller V1.1.2 Insight Log

Date: 2026-07-10

## Insight 1: S-Q-H Is Valid, But It Should Not Be The User-Facing Mental Model

The S-Q-H domain matches common blade-to-blade / streamwise-pitchwise-span parameterization practice. It is a sound internal construction domain.

The problem is not S-Q-H. The problem is exposing indirect scalar handles as if they are the universal geometry language. V1.1.2 should keep S-Q-H internally while exposing NURBS support profiles, skeleton fields, thickness fields, and segment curves as the primary semantic objects.

## Insight 2: Active Blade Span Is Different From Support Span

Root lift and closed-shroud inset mean the blade-side loop does not begin exactly at the hub or shroud support surface.

The better abstraction is:

```text
support span = hub to tip/shroud
active span = support span minus attachment offsets
```

This removes ambiguity in `span_stations_h` and makes root/shroud attachment surfaces first-class transition ribbons rather than accidental gaps.

## Insight 3: Rounded Edge Does Not Mean Semicircle Primitive

The desired leading and trailing edge shape is "rounded like a real blade nose or tail", not a literal half circle.

The robust rule is:

```text
edge cap = NURBS curve
sagitta = target from local thickness
continuity = measured against pressure/suction joins
```

If the target sagitta and continuity conflict, the builder must report the resolved values and errors rather than generating a spike or forcing a primitive.

## Insight 4: Preset Seeds Must Not Become Universal Rules

Several values were introduced conversationally to make a visible test model: blade count, thickness, high twist, support profile height, and sampling density.

Those are useful preset seeds. They are not universal impeller construction rules. V1.1.2 needs explicit metadata that distinguishes:

```text
preset_seed
derived_ui_handle
canonical_parameter
```

## Insight 5: Multi-View Annotation Is A Geometry Debugger, Not A New Editor

The frontend needs a multi-view tab because the actual model is too complex to validate from a single perspective.

The first version should annotate resolved canonical parameters on generated views. It should not introduce another independent edit path. Edits remain in existing parameter and curve-control payloads until the canonical schema proves stable.

## Insight 6: The Lowest-Risk Implementation Is A Translator Layer

Rewriting the surface graph kernel as exact NURBS would reset too much validated behavior.

The safer path is:

```text
legacy V1.1 preset fields
  -> canonical V1.1.2 NURBS parameterization
  -> existing V1.1 loop family and surface graph
```

This lets tests compare old and new semantics while preserving the work already done on face families, viewer metadata, mesh export, and preset routing.

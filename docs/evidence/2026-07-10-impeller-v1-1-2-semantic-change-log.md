# Impeller V1.1.2 Semantic Change Log

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

## Change Summary

V1.1.2 introduces a canonical NURBS parameterization layer for the existing V1.1 blade-to-blade loop surface-family constructor.

The geometry family remains V1.1:

```text
geometry_version = 1.1
transition_geometry_status = topology_first_blade_to_blade_5_loop_surface_family_graph
```

The semantic patch becomes:

```text
geometry_patch_version = 1.1.2
math_parameterization = v1_1_2_canonical_nurbs_parameterization
```

## What Changes

### 1. Input Language

Previous V1.1 input mixed universal rules, UI handles, and preset-specific tuning values.

V1.1.2 classifies input into:

```text
universal canonical inputs
preset-owned seeds
derived UI handles
```

The constructor consumes canonical input. Legacy V1.1 fields translate into canonical input.

### 2. Span Semantics

Previous wording allowed `span_stations_h = 0` to look like "blade begins on raw hub support".

V1.1.2 defines active blade span through `active_span_policy`:

```text
support span = hub to tip/shroud
active blade span = support span minus root and tip offsets
h = 0 means active blade root boundary
```

The root and tip offsets are resolved and reported.

### 3. Blade Shape Semantics

Previous V1.1 scalar shape handles such as `main_flow_turn_q_mm` and `midspan_bow_q_mm` remain deterministic but are no longer the universal mathematical rule.

V1.1.2 introduces:

```text
blade_skeleton_field = NURBS surface in S-H-Q
thickness_field = NURBS scalar field in S-H-thickness
section_loop_family = NURBS segment curve family
```

### 4. Leading And Trailing Edge Semantics

Previous discussions used "half thickness semicircular cap" language to describe desired rounded behavior.

V1.1.2 clarifies that leading and trailing edges are:

```text
NURBS cap curves with rounded-cap intent
```

The sagitta may target half local thickness, but the resolved curve is a spline and must satisfy measured join continuity.

### 5. Frontend Inspection Semantics

V1.1.2 adds a `Parameter views` tab.

This tab displays generated-model multi-view annotations for:

```text
support profiles
active span offsets
blade skeleton field
thickness field
cap sagitta targets and resolved values
attachment width and lift
pose field
main/splitter population
```

The tab is inspection-only. It does not mutate geometry.

## What Does Not Change

- The V1.1 S-Q-H blade-to-blade domain remains the core construction domain.
- The six blade face families remain pressure, suction, leading, trailing, root attachment, and tip/shroud attachment.
- Existing active preset ids remain stable.
- The implementation remains sampled review-grade geometry, not exact sewn production CAD.
- Historical V1.0 and V1.1 documentation and evidence remain valid and are not deleted.

## Reason For The Change

The project needs a clear parameterized impeller expression that is:

- deterministic;
- visually direct;
- globally and locally adjustable;
- decoupled enough for future optimization;
- close enough to current V1.1 to avoid restarting the geometry stack.

V1.1.2 is a semantic adapter and canonicalization layer, not a rebuild.

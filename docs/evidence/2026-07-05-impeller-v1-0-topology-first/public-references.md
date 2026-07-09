# Public References For V1.0 Topology-First Constructor

**Date:** 2026-07-05

## Turbomachinery Blade Geometry

### NASA BladeCAD

Source:

```text
https://ntrs.nasa.gov/citations/19960047133
https://ntrs.nasa.gov/api/citations/19960047133/downloads/19960047133.pdf
```

Relevance:

- BladeCAD is a public NASA turbomachinery blade geometry reference.
- It defines blade sections with respect to general surfaces of revolution representing throughflow geometry.
- The completed blade design is represented as a NURBS surface and exported to IGES for design, analysis, and manufacturing workflows.

V1.0 implication:

```text
Generating blade faces from a section network and throughflow/revolve context is feasible and aligned with public turbomachinery CAD practice.
```

### Versatile Tool For Parametric Smooth Turbomachinery Blades

Source:

```text
https://www.mdpi.com/2226-4310/9/9/489
```

Relevance:

- B-splines control meanline curvature, thickness, leading-edge shape, sweep/lean, and spanwise variation.
- The paper emphasizes smooth blade curvature for pressure distribution and attached flow.
- It reports watertight solid bodies and optional fluid domains from a parametric scheme.

V1.0 implication:

```text
The leading edge, trailing edge, thickness, and spanwise variation should be part of the native blade parameterization, not post-hoc surface repair.
```

### Unified Geometry Parametrization For Turbomachinery Blades

Source:

```text
https://www.sciencedirect.com/science/article/pii/S0010448520301809
```

Relevance:

- Presents a general blade parametrization method for axial, radial, and mixed-flow blades.
- Uses typical turbomachinery design variables and NURBS curves/surfaces.

V1.0 implication:

```text
The V1.0 versioned DSL can support radial/open/closed impellers while keeping the door open for broader turbomachinery configurations.
```

### Parametric 3D Blade Modeler

Source:

```text
https://repository.tudelft.nl/record/uuid%3A9bbcf030-af4b-42c8-a7e5-2157bde13706
```

Relevance:

- Reports blade geometry built with NURBS curves and surfaces.
- The goal is high smoothness and avoiding sharp edges.

V1.0 implication:

```text
NURBS face networks are an appropriate native representation for the blade, not only an export approximation.
```

## CAD Validity And Topology

### OCCT Shape Healing

Source:

```text
https://dev.opencascade.org/doc/overview/html/occt_user_guides__shape_healing.html
```

Relevance:

- OCCT identifies wrong wire orientation, self-intersecting wires, missing seam edges, and gaps in wires as face validity problems.
- Shape Healing can repair these issues, but repair may modify topology or geometry.

V1.0 implication:

```text
The constructor should generate valid wires, shared edges, seams, and face orientations directly. Healing is a diagnostic/export fallback, not the primary modeling rule.
```

### OCCT Sewing

Source:

```text
https://dev.opencascade.org/doc/overview/html/occt_user_guides__modeling_algos.html
https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___sewing.html
```

Relevance:

- Sewing analyzes free boundaries, identifies merge candidates, and merges separate faces.
- It is a shape-processing algorithm, not a substitute for a coherent constructor topology.

V1.0 implication:

```text
V1.0 should use shared-edge identity before export. Sewing may verify or package the shape, but it should not invent topology that the constructor failed to define.
```

## Model Finishing Failure Evidence

### CFturbo Model Finishing

Source:

```text
https://manual.cfturbo.com/en/model_finishing.html
```

Relevance:

- Finishing can fail when fillet radius is too large.
- Sharp blade edges can prevent fillet creation between blade and hub/shroud.
- Failure can occur when blade extension to hub/shroud fails.
- Intersections can occur because of oscillating geometry or closely spaced blades.
- Fillets are not supported when solid generation is unavailable.

V1.0 implication:

```text
Fillets and chamfers are fragile when treated as late finishing operations. A robust constructor should encode blade edge, root, and hub bevel faces before finishing/export.
```

## Continuity Measurement

### Rhino GlobalEdgeContinuity

Source:

```text
https://docs.mcneel.com/rhino/9/help/en-us/commands/globaledgecontinuity.htm
```

Relevance:

- Evaluates `G0`, `G1`, and `G2` continuity along surface edge pairs.
- Provides visual feedback for adjusting surfaces to achieve desired continuity.

V1.0 implication:

```text
Continuity belongs on named edge pairs. The V1.0 surface graph should expose per-edge G0/G1/G2 measurements and visible diagnostics.
```

## V1.0.3 Preset Retuning References

### CFturbo Impeller Design Steps And Meridional Contour

Sources:

```text
https://manual.cfturbo.com/en/impeller.html
https://manual.cfturbo.com/en/mercon.html
https://manual.cfturbo.com/en/mer_hub-shroud_contour.html
```

Relevance:

- CFturbo lists impeller design as main dimensions, meridional contour, mean-line design, blade properties, blade profiles, blade edges, CFD setup, and model finishing.
- CFturbo states that meridional contour design is the second important impeller design step and that the primary flow path is necessary for following steps.
- Its hub/shroud contour page exposes Bezier-point manipulation for primary flow path contours.

V1.0.3 implication:

```text
The preset should not use a cone-like generated fallback when a V1.0 constructor provides hub/tip NURBS defaults. Hub and tip support surfaces are carrier curves first, and blade section-loop construction follows them.
```

### CFturbo Blade Thickness And Splitter Guidance

Source:

```text
https://manual.cfturbo.com/en/bl_setup.html
```

Relevance:

- CFturbo documents blade setup, splitter limitations, and blade-thickness effects on blockage and flow calculation.
- Its warning guidance includes reducing blade number and/or blade thickness when blockage is too high.

V1.0.3 implication:

```text
The V1.0.3 inspection preset should use fewer blade pairs with main/splitter blades and keep the maximum blade thickness near 20 mm instead of using the previous 32 mm debug thickness.
```

### CAESES Radial Impeller Modeling Workflow

Source:

```text
https://www.caeses.com/blog/2022/centrifugal-water-pump-design/
```

Relevance:

- CAESES describes the first radial impeller modeling step as generating 2D meridional contours.
- The shroud contour connects inlet and outlet diameters, and the hub contour is derived using a width distribution.

V1.0.3 implication:

```text
Frontend scalar values should not claim ownership of curve-defined meridional geometry. The ParameterPanel should expose only high-level review inputs, while hub/tip/section-loop controls are edited as curve data.
```

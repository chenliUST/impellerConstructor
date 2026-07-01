# Impeller UI And DSL Issue Evidence

Date: 2026-06-30

Evidence screenshot:

- `current-open-impeller-ui-issue.png`

Post-implementation smoke evidence:

- `v03-open-smoke.png`
- `v03-closed-smoke.png`

Observed issues captured from the current frontend:

1. Curve editor panels are visually too small for controlled manipulation.
2. Curve editor panels show curve names and coordinate-system labels, but no live numeric values for control points.
3. Open impeller still exposes a visible `Tip support` layer and renders a tip/reference support surface, making it visually too similar to the closed impeller case.
4. Current manifest reports open impeller surface graph with tip/reference support included in the shaded/wireframe inspection path.

User-requested follow-up requirements:

1. Enlarge curve operation areas and show numeric values for editable curve/control-point handles.
2. Hide open-impeller tip reference surface in frontend/model visualization while preserving any internal mathematical support required for blade tip construction.
3. Add DSL v0.3 semantics for nonzero hub and hood/shroud thickness.
4. Add DSL v0.3 semantics for hub and hood/shroud chamfers/fillets.
5. Treat hub as a real solid: hub revolved surface plus top/bottom faces plus bottom thickness, with mounting bore cylinder removed.

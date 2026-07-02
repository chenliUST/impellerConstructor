export function edgeTreatmentRows(manifest) {
  const edgeFamilies = manifest?.edge_families || {};
  const transitionPolicies = manifest?.transition_policies || {};

  return Object.entries(transitionPolicies)
    .map(([fallbackPolicyId, policy]) => {
      const policyId = policy.policy_id || fallbackPolicyId;
      const edgeFamily = policy.edge_family || policyId.replace(/\.default$/, "");
      const family = edgeFamilies[edgeFamily] || {};
      const treatment = policy.treatment || "none";
      const enabled = policy.enabled !== false;
      const radiusMm = Number(policy.radius_mm ?? 0);

      return {
        policyId,
        edgeFamily,
        scope: family.scope || "",
        enabled,
        treatment,
        radiusMm,
        continuity: policy.continuity || "",
        status: edgeTreatmentStatus(enabled, treatment, radiusMm),
      };
    })
    .sort((left, right) =>
      [left.scope, left.edgeFamily, left.policyId].join("\u0000").localeCompare(
        [right.scope, right.edgeFamily, right.policyId].join("\u0000"),
      ),
    );
}

export function updateTransitionRow(currentOverrides, policyId, patch) {
  const next = { ...(currentOverrides || {}) };
  const row = { ...(next[policyId] || {}) };

  if (Object.hasOwn(patch, "enabled")) {
    row.enabled = patch.enabled;
  }
  if (Object.hasOwn(patch, "treatment")) {
    row.treatment = patch.treatment;
  }
  if (Object.hasOwn(patch, "radiusMm")) {
    row.radius_mm = patch.radiusMm;
  }

  next[policyId] = row;
  return next;
}

export function buildTransitionOverridePayload(overrides) {
  return overrides && Object.keys(overrides).length ? overrides : null;
}

function edgeTreatmentStatus(enabled, treatment, radiusMm) {
  if (!enabled || treatment === "none") {
    return "OFF";
  }
  if (radiusMm < 0) {
    return "INVALID";
  }
  return "OK";
}

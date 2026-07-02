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
        status: transitionStatus(enabled, treatment, radiusMm),
      };
    })
    .sort((left, right) =>
      [left.scope, left.edgeFamily, left.policyId].join("\u0000").localeCompare(
        [right.scope, right.edgeFamily, right.policyId].join("\u0000"),
      ),
    );
}

export function updateTransitionRow(currentOverrides, policyId, patch, baseRow = null) {
  const next = { ...(currentOverrides || {}) };
  const row = { ...(next[policyId] || {}) };

  if (Object.hasOwn(patch, "treatment")) {
    row.treatment = patch.treatment;
    row.enabled = patch.treatment !== "none";
    if (patch.treatment === "none") {
      delete row.radius_mm;
    } else if (!positiveRadius(row.radius_mm) && baseRow?.treatment === "none") {
      row.radius_mm = fallbackRadiusMm(baseRow);
    }
  }
  if (Object.hasOwn(patch, "enabled")) {
    row.enabled = patch.enabled;
    const currentTreatment = row.treatment ?? baseRow?.treatment ?? "none";
    if (patch.enabled && currentTreatment === "none") {
      row.treatment = "fillet";
      if (!positiveRadius(row.radius_mm)) {
        row.radius_mm = fallbackRadiusMm(baseRow);
      }
    } else if (!patch.enabled) {
      delete row.radius_mm;
    }
  }
  if (Object.hasOwn(patch, "radiusMm")) {
    if (patch.radiusMm === null || patch.radiusMm === undefined) {
      delete row.radius_mm;
    } else {
      row.radius_mm = patch.radiusMm;
    }
  }

  next[policyId] = row;
  return next;
}

export function effectiveTransitionRow(row, override = {}) {
  const hasOverrideTreatment = Object.hasOwn(override, "treatment");
  const hasOverrideEnabled = Object.hasOwn(override, "enabled");
  const treatment = hasOverrideTreatment ? override.treatment : row.treatment;
  let enabled = hasOverrideEnabled ? override.enabled : row.enabled;

  if (treatment === "none") {
    enabled = false;
  } else if (hasOverrideTreatment && !hasOverrideEnabled) {
    enabled = true;
  }

  const radiusMm = Object.hasOwn(override, "radius_mm") ? Number(override.radius_mm) : row.radiusMm;

  return {
    ...row,
    enabled,
    treatment,
    radiusMm,
    status: transitionStatus(enabled, treatment, radiusMm),
  };
}

export function buildTransitionOverridePayload(overrides) {
  const payload = {};

  for (const [policyId, override] of Object.entries(overrides || {})) {
    const row = {};
    if (Object.hasOwn(override, "enabled")) {
      row.enabled = override.enabled;
    }
    if (Object.hasOwn(override, "treatment")) {
      row.treatment = override.treatment;
    }
    const active = row.enabled !== false && row.treatment !== "none";
    if (active && Object.hasOwn(override, "radius_mm") && Number.isFinite(Number(override.radius_mm))) {
      row.radius_mm = Number(override.radius_mm);
    }
    if (Object.keys(row).length) {
      payload[policyId] = row;
    }
  }

  return Object.keys(payload).length ? payload : null;
}

function transitionStatus(enabled, treatment, radiusMm) {
  if (!enabled || treatment === "none") {
    return "OFF";
  }
  if (!Number.isFinite(radiusMm) || radiusMm <= 0) {
    return "INVALID";
  }
  return "OK";
}

function fallbackRadiusMm(baseRow) {
  for (const candidate of [baseRow?.radiusMm, baseRow?.defaultRadiusMm, baseRow?.mappedRadiusMm]) {
    if (positiveRadius(candidate)) {
      return Number(candidate);
    }
  }
  return 1;
}

function positiveRadius(radiusMm) {
  const radius = Number(radiusMm);
  return Number.isFinite(radius) && radius > 0;
}

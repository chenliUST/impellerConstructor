# Impeller V1.1.6 R14 Insight Log

Date: 2026-07-17

## Findings

1. The UI appeared to remain at `edge closure`, but retained stage evidence
   shows the dominant cost was the following deviation stage: about 89 minutes
   versus about four minutes for edge closures.
2. The previous comparison rebuilt the same source acceleration structure for
   each directional query and issued separate centroid and vertex queries.
3. Surface comparisons are independent after semantic correspondence and phase
   alignment, so bounded surface-level parallelism does not change geometry or
   metric meaning.
4. A whole-audit cache cannot help after a restart during deviation. Exact
   per-surface checkpoints make completed work recoverable at the natural
   semantic boundary.
5. Import-time orphan recovery caused false `v116_audit_interrupted` failures:
   a second Python process could import the API while the real worker remained
   alive. Recovery must inspect worker PID liveness and run only at startup.
6. On the current 16 GB workstation, two workers are the conservative default.
   Four workers remain opt-in because exact indexes and query buffers increase
   peak memory.

## Deferred Performance Work

- Parameter extraction and the three staged constructor calls still account
  for about 17 minutes in the retained audit.
- Heatmap and manifest JSON artifacts total roughly 291 MB. Their binary or
  streamed representation requires a separate payload-contract change.
- A fresh R14 full audit is required before projecting the synthetic speedup to
  KS007G23B wall time.


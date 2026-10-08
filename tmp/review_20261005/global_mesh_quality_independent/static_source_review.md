# Global mesh quality candidate: static source review

Review date: 2026-10-05 (Asia/Shanghai)

## Scope and freeze

Read-only review of the frozen candidate source, readback checks, and JSON contract. No source was executed; no candidate, CAD, or visualization was generated. Source hashes were rechecked and match the author/root pins:

| File | SHA-256 | Result |
|---|---|---|
| `candidate.py` | `c77a82c9503275aab746e0a092fcedca1e5985de091e9053d5401073f5cb7a7c` | match |
| `focused_checks.py` | `9e0dc06422938124dfe63588cb7f07739b6ead950132066f9327a718260be11f` | match |
| `candidate_contract.json` | `b952251d1995fd29e65aa3c18b19ae7c341827eb52e402af0581dbc2d3febc95` | match |

The candidate is constrained to the frozen baseline/local-B inputs, replaces the 128-face z=0 fan, preserves its 128-vertex interface, and writes under `vesselforge/tmp/review_20261005/global_mesh_quality_candidate`. The source declares no mechanics or physical-fragment qualification.

## Blocking finding

**The schema-v2 marker does not itself make legacy readers reject this NPZ.** `candidate.py` correctly writes `lineage_schema_version=2`, `legacy_schema_v1_safe=False`, and a guard string (lines 539–542), and cross-parent faces receive `source_face_ids=-1` with all-NaN legacy barycentrics while carrying explicit patches (lines 484–487, 511–515). The focused check verifies those candidate-side fields (lines 542–547). However, repository-wide Python source search found no existing `vesselforge` reader that checks those markers before consuming the legacy arrays. A reader that ignores the metadata can treat `-1` as Python's last-index sentinel and read NaN barycentrics. The output location is isolated and this candidate does not invoke such a reader, so this is a downstream compatibility-gate gap rather than a defect in the candidate's patch overlay. The contract's statement that metadata “forbids” schema-v1 readers is stronger than the behavior implemented.

Root should treat old-reader rejection as unresolved unless a concrete consuming path is shown to hard-fail on schema v2 (or the artifact remains strictly quarantined from those readers).

## Checks that are implemented in source

- The frozen input hashes and embedded provenance are checked before candidate construction (`candidate.py:93–124`).
- The source does not use a centroid parent to label an entire face. Each output floor triangle is clipped against the frozen fan triangles; positive patch areas must cover the whole output area without positive-area overlap (`candidate.py:444–475`). A legacy source row is written only when exactly one source patch covers the full face (`candidate.py:477–487, 511–515`).
- Cross-parent faces have explicit v2 status and patch records with source/output barycentrics and sampled linear/sRGB color arrays (`candidate.py:489–515, 538–562`). Readback checks reconstruct patch vertices in both charts, check simplex rows, patch area/coverage and overlap, and require sentinel/NaN for multi-parent rows (`focused_checks.py:302–374`).
- Q and aspect use actual displaced XYZ triangle coordinates, with the standard `Q = 4√3 A / Σ(edge²)` and `aspect = longest_edge² / (2A)` (`focused_checks.py:96–121`). Input and candidate global metrics cover every face; floor metrics cover the replaced fan faces (`focused_checks.py:444–447`).
- Whole-mesh readback checks edge incidence, winding consistency, duplicate/repeated faces, connected components, Euler characteristic, zero-area faces, and signed volume (`focused_checks.py:124–180, 561–570`).
- Non-floor face connectivity, source IDs, barycentric rows, and preserved outer arrays are compared exactly to local-B (`focused_checks.py:452–470, 591–601`).

## Non-blocking audit gaps to keep visible

- `candidate_nonfloor_body_quality` is the metric over *all* non-floor faces, including any wall, support, inner, or base faces (`focused_checks.py:448–450, 586`). It cannot be cited as a body-only statistic. Global full-mesh metrics are computed separately and are suitable for global before/after comparison.
- New floor vertex lineage is populated by `_source_owner` and barycentric evaluation (`candidate.py:384–389, 524–531`), but focused readback does not independently reconstruct every new vertex through that vertex-lineage row. Face patch lineage is checked.
- The readback validates floor and outer colors in linear RGB, but does not independently validate stored floor/patch sRGB arrays against the conversion formula. Candidate construction computes those arrays directly (`candidate.py:304–306, 547–560`).
- Outer per-corner relief error is reported by `_outer_color_error`, but the required-gate list does not require its magnitude or compare it to the input (`focused_checks.py:203–252, 514–520, 619–649`). Existing outer relief arrays are still required to be bitwise preserved.

## Decision

Source review is **not fully clear for generation approval** while old-reader rejection/quarantine remains a contract requirement. I found no source-level defect in the clipped multi-parent patch mapping or the global actual-triangle quality formulas. A passing generation would still establish only the stated analytic fixture geometry and experiment targets, not physical or mechanical qualification.

# Global mesh quality candidate: revised static source review

Review date: 2026-10-05 (Asia/Shanghai)

## Frozen source and scope

I rechecked the final `SOURCE_FREEZE.json` SHA-256: `09b972cdc1c04698b12f01acd88479a564ce03b0bf1ff68af2e9979e4e104b17`. Its four listed files match their recorded SHA-256 and byte counts:

| File | SHA-256 | Bytes |
|---|---|---:|
| `candidate.py` | `3a3a9c5a82cf936d3611ccffdfc6956331f3ba6514114b1905ff76e3254f4445` | 33,917 |
| `focused_checks.py` | `35ca4504cb161bd5780c0d9f6e7df53eea72b51e7fd0a8486dcea62d92bc5c65` | 48,948 |
| `candidate_contract.json` | `b804e6089d4553dcc393dfc866f0e92f8f4dd0bf4d38c4bded433103328cd998` | 6,810 |
| `SOURCE_REVIEW.md` | `efe51794fbe8ef0c25ab0f0390d5375b2ce219c6d47347468b8bf2d92c9bbac5` | 5,009 |

This was a read-only static review. I did not run the candidate, tests, rendering, CAD, or a solver. The declared generation output directory exists and is empty. The freeze says no candidate has been generated and no tests have been run.

## Narrow revision check

The prior arbitrary 12-parent limit is removed. `candidate.py:451–469` clips each output floor triangle against each frozen parent face and permits up to `len(floor_source_ids)` patches. The pinned fan is checked as 128 faces by the producer (`candidate.py:208–236`); readback independently derives the same fan, requires the saved declaration to match it, and enforces the cap against that derived set (`focused_checks.py:282–287, 365–368, 440–444`). Readback also rejects duplicate parent IDs within one child face (`focused_checks.py:414–417`). The contract and freeze record the same 128-parent bound.

This removes the earlier static blocker: a triangle near the retained center is no longer rejected merely for crossing more than 12 radial sectors. Per-face storage remains bounded by the complete frozen fan, while the existing global limits remain 15,000 patch records, 60,000 patch-polygon vertices, and 120 seconds. The fixed lattice, geometry, and quality targets are unchanged.

## Required source gates rechecked

- **Serialized schema-v1 face-lineage names:** candidate assembly removes `source_face_ids` and `face_corner_barycentric_to_source`, and writes only the explicitly named v2 single-parent arrays (`candidate.py:522–531`). Focused readback requires the standard keys to be absent, the v2 aliases present, schema version 2, quarantine status, and legacy compatibility marked `UNKNOWN` (`focused_checks.py:659–668`). No production-reader compatibility claim is made.
- **Face patches and CSR:** readback verifies CSR start/end offsets and monotonicity, valid unique floor output face IDs, complete patch-column lengths, each patch's source parent, positive area, simplex coordinates, and source/output chart reconstruction. It checks per-face area coverage and pairwise overlap, and rejects duplicate source parents for one face (`focused_checks.py:282–318, 362–434`). The builder independently checks area coverage/no overlap before serialization (`candidate.py:471–479`).
- **Single- and cross-parent lineage:** a legacy-single-parent row is written only when exactly one clipped parent patch covers the whole child face; otherwise the named v2 row uses `-1`/NaNs and the face is represented by patches (`candidate.py:481–520`). The readback reconstructs single-parent face corners and validates the explicit multi-parent sentinel.
- **Appended vertex lineage:** each appended vertex must reference a source face from the independently derived frozen bottom fan, have valid simplex barycentrics, and reconstruct its XYZ location within `1e-9 mm` (`focused_checks.py:476–505`); this gate is required for check success.
- **Color:** floor vertex and patch linear-RGB samples are compared with the frozen field, and stored sRGB is independently compared against sRGB conversion of those samples (`focused_checks.py:320–360, 394–398, 454–457`). Both color-space errors are included in required gates (`focused_checks.py:669–685`).
- **Unchanged outer and nonfloor data:** outer arrays and nonfloor face connectivity, source rows, and barycentric rows are compared exactly. Finite outer color and relief sampling errors are recomputed against the frozen field for input and candidate, and their maximum-error deltas must remain within fixed tolerances (`focused_checks.py:551–566, 627–638, 719–737`). The combined non-floor metric is named `candidate_nonfloor_quality`.

## Decision

I found **no remaining static blocker to one bounded candidate-generation attempt** under the frozen 120-second and global data budgets. This is source readiness only: all generated-array, topology, quality, color, and lineage outcomes remain unobserved until the authorized run. `legacy_reader_compatibility` remains **UNKNOWN**, and the candidate remains quarantined from production. Any successful run would establish only the specified analytic fixture and geometric triangle checks; it would not qualify mechanics, solver resolution, material response, or a real fragment match.

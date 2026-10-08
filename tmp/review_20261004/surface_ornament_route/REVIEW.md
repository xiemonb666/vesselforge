# Review freeze

This directory freezes the corrected VF → PG-Frag → A12 → RelicWeave route, R2 provenance semantics, read-only references, current artifacts, and preserved snapshots. `SCOPE_DIFF.md` records the scope and label changes; `FREEZE_MANIFEST.json` and `SHA256SUMS.txt` hold current hashes.

`ownedtmp/rejected_scope_v1/` preserves the v1 service-boundary draft and original freeze under `REJECTED_SCOPE_DRIFT`. `ownedtmp/pre_r2_semantics_v2/` preserves the route version before the R2 label-semantics correction.

No Python, CAD, tests, solver, GPU, or Git work was run. The checksum list includes the current manifest hash and does not hash itself.

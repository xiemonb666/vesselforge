# Review freeze

This directory freezes the corrected VF → PG-Frag → A12 → RelicWeave data route, the read-only inputs consulted, and the authored unexecuted prototype. See `FREEZE_MANIFEST.json` for current hashes and roles.

`ownedtmp/rejected_scope_v1/` preserves the previously rejected DESIGN/PLAN and their original SHA-256 snapshot under the marker `REJECTED_SCOPE_DRIFT`. That snapshot records the superseded service boundaries.

No Python, CAD, tests, solver, GPU, or Git work was run. `SHA256SUMS.txt` lists current input and artifact hashes plus the current manifest hash; it does not hash itself.

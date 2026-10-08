# Independent failure-call-graph supplement

**Current disposition: BLOCKING SOURCE BUG; do not retry until the author’s narrow fix and regression are frozen and reviewed.** This supplement supersedes the earlier “no source-level blocker” disposition for execution decisions. The earlier report pair is preserved unchanged as a historical static review; I missed this call-semantics defect in that review.

I independently read the failed child receipt and parent-runner receipt, and inspected the pinned source read-only. The child receipt reports `CandidateUnknown: barycentric coordinates escaped their source simplex`, `UNKNOWN_OR_FAIL`, child elapsed 1.197 s and return code 2. The parent receipt reports `CHILD_NONZERO_EXIT`, elapsed 1.391 s and `timed_out=false`. Its before/after input and source hashes match. The run directory contains only the child receipt, parent receipt, and empty combined-output log; no candidate NPZ or focused-checks output was written. I did not inspect or audit any candidate arrays, and I ran no source, test, geometry, CAD, or solver code.

## Failure path

In the reviewed snapshot, `candidate.py:183-195` implements `_barycentric_xy`: after computing signed weights, it raises `CandidateUnknown` whenever the point is outside that triangle’s simplex by more than 1e-10. That is appropriate for callers that require an already-contained point.

But `candidate.py:301-309` uses the same checked helper as a search operation. `_source_owner` loops over cap source faces in ascending identity, calls the checked helper at line 306, and only then would test containment at line 307. For a lattice point outside the first tested source face, the helper raises before the predicate can reject that face and continue to a later true owner. The matching exception text in the run receipt confirms this failure mode. `_triangulate_cap` calls this owner search for every new interior point at line 371 after creating the Delaunay output; therefore the failure occurs while assigning new-vertex lineage, before candidate NPZ save, not because the reviewed receipt shows a quality-gate failure.

The focused readback checks exercise saved lineage, but the pinned `focused_checks.py` has no direct regression for the ownership search’s “first parent is outside, later parent contains” control flow. I read the current source at SHA `9f09faf13fb423d1cbf6aeec0f41e4ece7533e648adf0e8b26762669a892c114`; before and after my relevant source read, its hash was unchanged. The failed-run receipt pins that same candidate hash.

## Narrow review criterion for the author fix

The minimal semantics-preserving fix is to separate raw signed barycentric calculation (with only the existing degenerate-triangle guard) from the existing validated/raising helper. Only the owner-search loop should use raw weights for its current containment predicate; after it accepts an owner, the current barycentric-cleaning and normalization path should produce saved lineage. Preserve the existing 1e-10 and 5e-13 tolerances and the separate Delaunay path/options. A focused two-parent toy regression should make the first parent miss and the second contain the point, then assert the second owner and valid barycentrics; optionally verify a shared-edge point still selects the lowest-ID containing parent.

This is a control-flow/ownership issue. The previous fixed cap IDs, geometry budgets, quality gates, and lineage readback remain separate review subjects and are not evidence that this owner path succeeds. No post-fix judgment is made here; review the author’s frozen narrow diff before any retry.


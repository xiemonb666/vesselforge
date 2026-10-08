# Saved-NPZ owner-fix readback recovery v1

## Current status

This package is source-only and awaits root source review. No saved-array focused checks, mesh readback, geometry generation, or rendering were run while preparing it. The prior `run02_owner_fix` remains failed: its child returned 2 after saving NPZ SHA `f505831ba0b3ae58c3846f227750e62c902f0f79c250fc3c9b8a5fb748fab7be`; its parent returned 1. Its original receipts and NPZ are pinned and remain unchanged.

## Failure diagnosis and minimal checker change

The failed candidate saved its arrays and returned from `run_focused_checks`; `candidate_owner_fix.py` then failed at `json.dumps(checks, ..., allow_nan=False)`. Static tracing plus a small VesselForge-Python scalar-type probe localized the non-native booleans to the two direct entries in the check map: `global_minimum_Q_improves_above_float_resolution` and `global_maximum_aspect_improves_above_float_resolution`. Both comparisons use tolerances formed from `np.finfo(np.float64).eps`, and therefore yielded `numpy.bool_` values. The details are appended separately at [run02_owner_fix_failure_cause_append.md](../../tmp/review_20261005/global_two_cap_mesh_candidate/run02_owner_fix_failure_cause_append.md); the old receipt was not edited.

`focused_checks_recovery_v1.py` is an isolated copy of the original focused checker. Its only algorithmic diff materializes the two existing tolerance values as Python `float` and those two existing gate results as Python `bool`. This preserves their binary64 values and comparison outcomes. The checker keeps all fixed tolerances and thresholds unchanged, performs no recursive type coercion, and retains strict `allow_nan=False` serialization.

## Readback boundary

The recovery worker reads the failed run's saved NPZ plus the pinned baseline and local-B NPZs, local-B checks, case freeze, and refinement-source hash. It invokes the saved-array focused checker once. The checker imports the pinned `candidate_owner_fix.py` only for the existing two-parent owner-lookup toy regression; it does not import or call the candidate's `main`, `build_candidate`, or any geometry-generation path. The worker writes `readback_checks.json` before attempting the existing renderer, then records renderer status separately and requests the two actual-geometry equal-aspect PNGs. A returned false gate is recorded as `DISCREPANCY`; a successful recovery is labelled `RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN`. Neither case rewrites the original failed run's status.

The PowerShell outer runner refuses an existing recovery-output directory, verifies frozen source/input/history pins, launches the worker once, monitors total artifact bytes, and kills the child tree at the fixed deadline. Its source contract is 60 seconds hard total, 50 seconds child wait, 3 seconds cleanup wait, and 20 MiB across the complete new output tree. No retry, tuning, CAD, or solver path exists in this package.

## Frozen material

The recovery freeze pins the original owner-fix source freeze `29beabbda63c8e6c6ca08234fb0f529da67227a475edb8b1cc664923801c9df6`, the unchanged candidate/checker dependencies, recovery worker and outer runner, the failed saved NPZ, all five original inputs, the interpreter, and the previous run's receipt/history files. Exact pin values are in [READBACK_RECOVERY_FREEZE.json](READBACK_RECOVERY_FREEZE.json). Output is isolated under `vesselforge/tmp/review_20261005/global_two_cap_mesh_candidate/recovery_readback_ownerfix_v1/`.

This readback would report geometric triangle metrics only. Tetrahedral quality, full-tet behavior, physical validity, mechanical h, solver results, and R2 qualifications remain unknown.

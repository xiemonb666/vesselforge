# Saved run02 readback completion source review

## State

This is a source-only recovery package awaiting root review. It has not been executed. The original `run02_v2bugfix/run_receipt.json` remains `UNKNOWN_OR_FAIL`, and the preserved candidate NPZ is treated as read-only input. Any later successful readback must be labeled `RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN`; a failed check or other mismatch must be labeled `RECOVERED_READBACK_WITH_DISCREPANCY`. Neither label changes the original run02 result.

## Narrow checker correction

The saved NPZ was written before `focused_checks.run_focused_checks` stopped on `NameError: COLOR_FINITE_SAMPLE_TOL`. The checker referenced that name at its finite outer-field error-delta gate but did not define it. The frozen candidate source already defines `COLOR_FINITE_SAMPLE_TOL = 1e-12`. The only checker edit adds the same module-level constant:

```python
COLOR_FINITE_SAMPLE_TOL = 1e-12
```

No tolerance changes, comparison changes, or other checker logic changes are included. The pre-edit checker and original `SOURCE_FREEZE.json` were copied byte-for-byte to `run02_v2bugfix/pre_readback_source_snapshot/` before this edit.

## Readback adapter

`readback_completion_adapter.py` verifies the preserved run02 receipt, its failed status and hash, the saved NPZ SHA-256, the v2 source freeze, the pre-edit checker snapshot, the frozen candidate source, and all five original input pins. It reads the already saved candidate arrays and invokes only `focused_checks.run_focused_checks`, `summarize_triangle_quality`, and `render_saved_meshes`. It does not import `candidate.py`, invoke `candidate.main`, create or alter mesh arrays, rewrite the candidate NPZ, or write to the original run02 directory. Checks, a result manifest, readback receipt, and the two actual equal-scale PNGs go to a new `completion_review/` directory. The output directory must not exist before execution.

The manifest reports global, floor, and nonfloor geometric triangle quality, floor patch lineage including the observed maximum parent-patch count per output face, and the frozen schema-v2 quarantine. Triangle quality is not reported as tetrahedral quality, solver `h`, mechanics, fracture, or material validation. The fixed targets remain floor minimum Q ≥ 0.35, floor maximum aspect ≤ 5.0, and strict global Q/aspect improvement.

## Execution adapter and limit

`execute_readback_completion.ps1` verifies this source freeze and all immutable file hashes before launching the Python adapter. It uses `System.Diagnostics.Process` with asynchronous stdout and stderr reads, then records `Process.ExitCode` directly after the child exits. Empty stdout is serialized as an empty string. The runner has a hard 120-second wait limit and kills the child if that limit is reached. It records pre/post hashes for the reviewed sources, five original inputs, saved candidate NPZ, original run02 receipt, freeze, and Python runtime. Captured logs and the execution receipt are written only under `completion_review/`.

This package is awaiting root review. No focused checks, PNG rendering, candidate generation, CAD, or solver work has been run for this completion adapter.

# Saved-NPZ recovery runner v2

Source-only revision for root review. No NPZ readback, focused checks, render, geometry generation, CAD, solver, test suite, or Git operation was run.

The original run02 failed after saving candidate NPZ SHA `f505831ba0b3ae58c3846f227750e62c902f0f79c250fc3c9b8a5fb748fab7be`; its RCs remain parent 1 / child 2 and status `UNKNOWN_OR_FAIL`. V1 recovery files and freeze are unchanged. V2 reuses the v1 recovery checker with the same two native-scalar producer conversions and no other numerical algorithm or tolerance changes.

The v2 inner runner and independent supervisor both require the root-coordination switch `-RootApprovedReadback`; the supervisor is the only intended entry point. It launches the inner runner hidden, terminates its process tree at 55 seconds, reserves up to 3 seconds for cleanup and 2 seconds for the final size check/return, and independently observes the complete fresh output tree. The inner runner keeps its worker wait at 50 seconds and records that observation without claiming its own post-hash/receipt I/O has a hard 60-second bound.

Artifact accounting names three stages: polling while the worker runs, total bytes after worker exit and before the runner receipt, and a rescan after the final receipt is written. The receipt's status, padded return code, and 12-digit final byte count are fixed-width. The runner predicts its exact UTF-8 receipt size, writes the final status, and rescans; any final total above 20 MiB yields `ARTIFACT_CAP_EXCEEDED` and return code 125 in the receipt and process. The supervisor independently rejects a cap excess. No status or return code is changed after a completed final receipt without rewriting and rescanning that same fixed-width receipt.

The worker keeps numerical and render results separate, saves `readback_checks.json` before rendering, and writes only beneath `vesselforge/tmp/review_20261005/global_two_cap_mesh_candidate/recovery_readback_ownerfix_v2/`. The intended execution command, after root's source review, is:

```powershell
& 'vesselforge/experiments/global_two_cap_mesh_candidate_20261005/run_readback_recovery_supervisor_v2.ps1' -RootApprovedReadback
```

Exact source/input/history pins and the fixed limits are in [READBACK_RECOVERY_FREEZE_v2.json](READBACK_RECOVERY_FREEZE_v2.json) and [READBACK_RECOVERY_CONTRACT_v2.json](READBACK_RECOVERY_CONTRACT_v2.json). The original v1 freeze, failed receipts, prior run tree, and saved candidate NPZ are preserved by hash.

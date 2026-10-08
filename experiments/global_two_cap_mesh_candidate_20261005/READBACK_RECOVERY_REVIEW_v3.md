# Saved-NPZ recovery runner v3

Source-only revision for root review. No NPZ readback, focused checks, render, geometry generation, CAD, solver, test suite, or Git operation was run.

The original run02 failure and saved candidate NPZ remain unchanged. V1 and v2 recovery packages, freezes, failed receipts, and run trees remain separate and pinned. V3 changes only the PowerShell expected-pin count expression, which now counts the expected object's properties as an array on PowerShell 7.6.5; it also uses v3 identifiers and a distinct fresh output root.

Both v3 PowerShell entry points require `-RootApprovedReadback`. The intended entry point is [run_readback_recovery_supervisor_v3.ps1](run_readback_recovery_supervisor_v3.ps1). It waits up to 55 seconds for the inner runner, allows up to 3 seconds for process-tree cleanup, measures and reports any supervisor elapsed overrun, and observes output-tree size. Those synchronous observations do not establish a hard 60-second bound for all supervisor I/O. Any future execution must be launched by a separate outer harness that enforces the total 60-second wall limit and 20 MiB artifact cap.

Artifact accounting records the worker-active polling stage, the output tree after worker exit and before the inner receipt, and the output tree including the receipt. The inner runner writes a cap failure status/return code when its measured total exceeds 20 MiB. The independent outer harness remains required to bound all post-exit I/O and enforce the cap for the full invocation.

The worker keeps numerical and render results separate, saves `readback_checks.json` before rendering, and writes only beneath `vesselforge/tmp/review_20261005/global_two_cap_mesh_candidate/recovery_readback_ownerfix_v3/`. No readback or render is authorized by this source package. The reviewed command would be:

```powershell
& 'vesselforge/experiments/global_two_cap_mesh_candidate_20261005/run_readback_recovery_supervisor_v3.ps1' -RootApprovedReadback
```

Exact source/input/history pins and fixed limits are in [READBACK_RECOVERY_FREEZE_v3.json](READBACK_RECOVERY_FREEZE_v3.json) and [READBACK_RECOVERY_CONTRACT_v3.json](READBACK_RECOVERY_CONTRACT_v3.json). The interpretation remains geometric triangle readback only; full-tet, physical, mechanical-h, solver, and R2 conclusions remain unknown.

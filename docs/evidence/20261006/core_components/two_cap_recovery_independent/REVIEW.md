# Independent static review: readback recovery v2

**Decision: BLOCKED. The frozen v2 inner runner rejects valid pin maps before starting the readback worker.** Do not treat the v2 package as executable until the count check is corrected and the revised source is frozen/reviewed. The saved NPZ’s SHA-256 matches the requested pin; I verified it by file hashing only and did not load or inspect its arrays.

## Blocking preflight defect

At `run_readback_recovery_once_v2.ps1:118`, the runner compares the scalar hashtable count with `$pathMap.Expected.PSObject.Properties.Count`. Under the PowerShell 7.6.5 behavior reported by root’s native probe, `$obj.PSObject.Properties.Count` for a two-property object yields the member-access result `[1,1]`, rather than scalar 2. The same expression therefore rejects the frozen source/input/history maps (15, 5, and 10 entries) even though each expected hash pair matches. I verified the pinned comparison expression and the map cardinalities; I did not repeat the PowerShell probe.

The count guard is inside the preflight loop at lines 108–120. Recovery-root creation follows at lines 125–131, and worker launch follows at 133–136. Thus the frozen v2 runner throws “pin set differs from freeze” and exits before loading the already-saved candidate NPZ, running numerical checks, or rendering. A scalar property-count expression is needed before this recovery can run.

## Static checks that pass

The requested freeze hash `a6a3694567130fc57f041ff57f7a5266a6a59a5ac61685a021499f77fbcc479c` matches. All hashes listed by the freeze, its five input hashes, and the existing candidate file hash match their pins. The candidate NPZ at `run02_owner_fix/candidate_arrays.npz` hashes to `f505831ba0b3ae58c3846f227750e62c902f0f79c250fc3c9b8a5fb748fab7be`; this review only streamed it through SHA-256.

The worker has no candidate builder path. It verifies hashes, loads baseline/local-B fixtures and the one pinned saved candidate NPZ, calls `run_focused_checks` once, writes numerical results, then renders from those same loaded saved arrays. It does not call candidate generation, CAD, or a solver. `focused_checks_recovery_v1.py` differs from the pinned owner-fix checker only by materializing the existing two scaled float64-epsilon thresholds as Python floats and the two comparison results as Python bools. The formulas remain `64 * float64_epsilon * max(1, abs(before), abs(after))`; the numeric gates are unchanged. I refer to these as scaled epsilon thresholds, not as 64 local ULPs.

Numerical and rendering outcomes are represented separately. The worker writes `readback_checks.json` before rendering, writes `render_status.json` separately, and exits 0 only if numerical checks and rendering pass and all pins remain unchanged. It returns nonzero for failed checks/rendering or pin drift. A numerical recovery label can still appear when rendering fails because that label follows numerical checks only; the separate render status and nonzero exit must be read with it.

The inner runner and supervisor count the full recovery output tree, including redirected stdout/stderr, readback artifacts, and the inner runner receipt. The inner runner predicts the UTF-8 receipt byte length, uses fixed-width final status/count fields, rescans after writing, and returns 125 with an artifact-cap status when the final count exceeds 20 MiB; the outer supervisor also polls and rescans that same tree. This is a monitored fail-and-report cap, not a filesystem quota: an over-limit partial artifact may remain, but the final overage is reflected in status/return code.

## Timing boundary

The PowerShell files allocate a 50 s worker wait, a 55 s inner-runner deadline, and 3 s cleanup within a nominal 60 s supervisor window. The supervisor itself does not independently bound synchronous hash/tree scans, process-launch/kill calls, or final output. Its 60 s check can report an overrun after such a call returns; it cannot terminate itself. A separate external watchdog is therefore needed for a true end-to-end 60 s cap. Root has stated that the authorized invocation will use an external hard watchdog, so this timing limitation does not require redesigning the recovery algorithm.

No recovery worker, focused check, render, solver, or candidate generation was run by this reviewer. The existing report directories and candidate NPZ were not modified.


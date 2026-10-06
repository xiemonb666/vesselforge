# Semantic base/neck exact-check plan

The active bowl apex parameter is 8/12. The archived 10/12 case and its original freeze remain in `prior_10_12_freeze/`. Geometry targets and the `R≥9 mm` meridian screen are unchanged.

## Rank precheck

This precheck completed once with the bundled VF interpreter and `-B`. It imported the inert driver by adding only the experiment directory to `sys.path`, then called only `basis_row` and exact `_rank` on fixed-pole-reduced equality matrices. All four current bowl/jar r/z systems have rank(A)=rank([A|b])=3. The archived bowl 10/12 radial system has rank(A)=2 and rank([A|b])=3. Result, stdout, stderr, and runtime/source receipts are saved beside this plan. No Hessian or KKT matrix was formed, no curve extracted or sampled, and no CAD was loaded.

## One conditional exact candidate run

Root preauthorized one call to `run_fixed_candidates(root_ready=True)` only if all four current systems have `rank(A)=rank([A|b])=3), the historical case has the recorded inconsistency witness, and the five frozen source pins match. Use the bundled VF interpreter with `-B`, external 60-second timeout, and the driver's 8 MiB JSON cap. Refuse existing output. Capture exact argv, runtime, return code, elapsed time, stdout/stderr, and pre/post hashes. No retry or parameter change.

The KKT dimensions remain r=13 and z=14 per family, with affine RHS `(-2H_fF q_F, b−A_F q_F)`. A zero exit only means exact arithmetic completed; it is not a geometry pass. Keep mixed Bernstein signs and failed sufficient hull/pole screens as NOT_CERTIFIED/UNKNOWN, while negative endpoint `P_R=S³−81D²` is a genuine point counterexample.

No CAD/OCC, STEP, mesh, solver, PNG, lip, inner profile, normal offset, full wall thickness, or archaeology/style qualification is authorized in this run.

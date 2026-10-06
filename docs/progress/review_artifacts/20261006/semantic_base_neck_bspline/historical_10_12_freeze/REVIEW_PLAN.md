# Source review and bounded-run plan

Only these new paths are in scope: `vesselforge/experiments/semantic_base_neck_bspline_20261006/` and `vesselforge/tmp/review_20261006/semantic_base_neck_bspline_20261006/`. The prior 11-pole source, cases, and outputs stay frozen.

Review the 17-pole degree-5 knot vector, automatic flat-base/cylindrical-neck pole rules, six exact equalities, and fixed/free partitions. Confirm the reduced exact KKT dimensions `13×13` for `r` and `14×14` for `z`; the affine fixed-pole RHS is `(-2H_fF q_F, b−A_F q_F)`. Singular row/KKT systems must fail without regularization.

Before any future solve, root must approve the fixed seed cases. If approved, make one exact Fraction call via the bundled VF runtime after adding only the experiment directory to `sys.path`; do not import the `vesselforge` package initializer. Cap the process at 10 seconds and the result JSON at 8 MiB. The writer refuses an existing output directory. Capture argv, runtime, rc, elapsed time, stdout/stderr, output hash, and pre/post pins.

The report must keep the `R≥9 mm` target on spans 1–10. Exclude span 0 and 11 only when their exact straight-segment semantics and positive speed are proved. Check exact feature/equality residuals, all strict point inequalities, hull and derivative-pole certificates, endpoint tangents, C4 jets through order four, and degree-24 `P_R` coefficients. A failed sufficient pole/hull enclosure is NOT_CERTIFIED; negative endpoint `P_R` is a point counterexample; mixed coefficients remain UNKNOWN.

No curve call, KKT solve, display sampling, PNG, CAD/OCC, STEP, mesh, solver, material/archaeology claim, inner profile, normal offset, or global wall claim has been run or is authorized by this source freeze.

# Semantic base/neck source plan

Source-only freeze candidate. Nothing in the driver has been imported or invoked; there is no control net, Hessian, KKT result, sampled curve, curvature coefficient, image, or CAD output.

## One bounded math call, only after root READY

Use the bundled VF interpreter with `-B`. Add only the experiment directory to `sys.path`, then import `semantic_base_neck_driver` as a top-level module. Do not import the `vesselforge` package: its initializer may load native components.

The fixed system sizes are `r: 10 free + 3 equalities = 13×13` and `z: 11 free + 3 equalities = 14×14`, for four Fraction solves across bowl and jar. The affine RHS is `(-2H_fF q_F, b−A_F q_F)`. Exact row rank, KKT nonsingularity, equality residuals, and strict point checks must be retained; no ridge, pseudoinverse, floating solve, knot changes, or target edits are allowed.

The exact Boehm extraction must yield twelve six-pole Bezier spans. Check feature equalities; exact endpoint jets through order four; convex-hull bounds; derivative-pole direction screens; regularity on every span; and exact flat-base/cylindrical-neck exclusions. Compute degree-24 Bernstein coefficients of `P_R=S³−81D²` only on non-flat spans 1–10. Negative endpoint values are point counterexamples; mixed coefficients and failed sufficient pole screens remain UNKNOWN. Keep `R≥9 mm` unchanged.

The future output path is `vesselforge/tmp/review_20261006/semantic_base_neck_bspline_20261006/minimum_jerk_candidate`. Enforce an external 10-second wall limit and an 8 MiB JSON cap; refuse an existing output directory. Record argv/runtime, rc, elapsed time, stdout/stderr, output hash, and frozen pre/post pins. Exit 0 means exact arithmetic completed, not that all geometry screens passed.

No CAD/OCC, STEP, mesh, solver, material calibration, archaeology/style qualification, inner profile, normal offset, wall-reach claim, or lip construction is in scope. A later visualization, if requested, must render saved controls only and label display sampling separately from exact certificates.

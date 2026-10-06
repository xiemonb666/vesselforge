# Semantic base-and-neck B-spline candidate

Status: source-only. The older 11-control minimum-jerk candidate and its results remain frozen and untouched.

## Fixed profile semantics

Each outer meridian is a degree-5 unit-weight B-spline with 17 RZ poles, clamped endpoint multiplicity six, and eleven simple knots `k/12`. It has twelve exact Bezier spans and C4 internal continuity. The first six `z` poles are fixed at zero, making span 0 an exactly flat exterior base. The final six `r` poles are fixed to the mouth radius, making span 11 an exactly cylindrical neck. `Q0.r=0` fixes the axis. These pole rules replace a drifting round-bottom optimum with explicit foot and neck geometry.

The fixed bowl seed is foot `(24,0)` at `u=1/12`, apex `(60,77.4)` at `10/12`, neck start `(57,86)` at `11/12`, and mouth `(57,90)` at `u=1`. The jar seed is `(18,0)`, `(54,62)` at `6/12`, `(26,102)` at `11/12`, and `(26,120)` at `u=1`. The foot radii are engineering seeds, not archaeological or style validation. Mouth/body datums remain 90/120 mm; accepted total crest targets 92/122 mm refer to a future, unbuilt lip and are not checked here.

## Deterministic free-pole selection

With unit weights, all declared equalities are linear. For `r`, seven pole values are fixed (`Q0` and `Q11…Q16`), leaving ten unknowns and three equalities: foot radius, apex radius, and apex `dr/du=0`. Its KKT system is 13×13. For `z`, six poles (`Q0…Q5`) are fixed, leaving eleven unknowns and three equalities: apex height, neck-start height, and mouth height. Its KKT system is 14×14. Foot height, axis horizontal tangent, neck-start/mouth radius, and mouth radial tangent follow from the fixed poles; no redundant rows are added.

The candidate rule minimizes the exact rational functional `∫||C'''(u)||²du`. The affine KKT uses `2H_ff` and right-hand side `(-2H_fF q_F, b−A_F q_F)`, with the exact degree-2 Bernstein Gram integral assembled over all twelve knot spans. The quadratic nullspace of the third-derivative energy is eliminated by fixed poles: a homogeneous quadratic perturbation is zero on the final span for `r` and on the first span for `z`, so it must vanish globally. The exact equality-rank check must still establish independent rows; then the constrained minimizer is unique. Rank/residual failure stops the candidate. No ridge, pseudoinverse, floating solve, or parameter retuning is allowed.

## Geometry gates

The full non-flat body and shoulder retain the `R≥9 mm` meridian-curvature screen on spans 1–10. The screen is not weakened to improve a candidate. Spans 0 and 11 are excluded only after exact pole checks prove a flat base meridian and constant-radius neck meridian; both still require exact positive-speed evidence. This says nothing about total surface curvature: a surface of revolution has circumferential curvature on the neck. A derivative-pole sign failure or control-hull failure means its sufficient certificate was not obtained, not that the curve itself failed. A negative endpoint of `P_R=S³−R²D²` is a genuine point counterexample; mixed Bernstein signs remain UNKNOWN. Base/neck span regularity, exact C4 join jets through order four, global reach, normal wall thickness, inner geometry, lip shape, and material qualification are separate records.

No basis, extraction, Hessian, KKT solve, curve sample, curvature coefficient, CAD shape, or image has been generated.

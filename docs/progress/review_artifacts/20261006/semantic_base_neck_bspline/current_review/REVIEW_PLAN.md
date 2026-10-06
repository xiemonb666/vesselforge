# Semantic base/neck source review

The active fixed cases use a bowl apex at 8/12 and preserve the jar apex at 6/12. The prior bowl 10/12 case, manifest, source snapshot, and infeasibility note are preserved under `prior_10_12_freeze/`.

The source remains unchanged. It builds exact degree-5, 17-pole, unit-weight B-spline candidates with twelve simple-knot spans and C4 joins. The semantic first span is a flat base and the final span has constant meridian radius; the `R≥9 mm` meridian curvature screen remains on spans 1–10. No zero circumferential-curvature or global normal-wall claim is made.

The exact Fraction rank precheck completed: all four current systems have rank(A)=rank([A|b])=3, while the archived bowl 10/12 radial system has rank 2 versus augmented rank 3. The precheck called only the driver's `basis_row` and `_rank`; it did not form a Hessian or KKT matrix, extract/evaluate a curve, load CAD, or render.

Root has authorized one exact candidate call with `root_ready=True` after the five current source pins are reverified, using the bundled VF Python `-B`, a 60-second external timeout, and the existing 8 MiB output cap. Keep the resulting geometric status distinctions literal: point counterexamples are failures, while mixed Bernstein signs and unsuccessful sufficient enclosures remain UNKNOWN. No retries or parameter changes.

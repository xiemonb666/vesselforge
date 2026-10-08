# Coupled beaker profile candidate v2

This directory freezes one analytic RZ section candidate for a representative beaker. It is a geometry-design prototype only. The actual vessel style is unknown and has not been matched to a reference; no material calibration, manufacturability, functional qualification, native CAD, or reusable family range is claimed. `height_mm = 110` is the outer and inner rim endpoint elevation. It is not the full section height: the symmetric lip reaches exactly `1795/16 = 112.1875 mm`, and the Bezier control-hull upper bound is `112.8 mm`.

The candidate keeps a `2.5 mm` paired radial control-pole gap up to the shoulder transition, then locally increases the shoulder-to-rim radial endpoint gap from `2.5 mm` to `3.5 mm`. The rounded lip endpoints are `(r,z) = (37.5,110)` and `(34,110)`, so the lip's horizontal endpoint gap is `3.5 mm`; both endpoint tangents are vertical and opposed, and endpoint second derivatives are zero. The inner and outer are coupled through shared endpoint jets and identical z control poles on the paired side spans. All gaps stated here are radial section gaps, not normal wall thickness.

## Why the 2.5 mm convex-lip target is infeasible

For a regular, simple, convex lip with a single half-turn, the tangent angle changes by `pi`. The absolute horizontal endpoint separation is the absolute value of the horizontal tangent integrated over arc length; because radius decreases throughout the open interval, this is the integral of the absolute horizontal tangent component. If the curvature radius is everywhere at least `R`, then `ds >= R |d(theta)|`, and over the half-turn the integral of the absolute horizontal tangent component with respect to angle is `2`. Thus `gap >= 2R`. At a fixed `2.5 mm` endpoint gap, asking for `R >= 1.25 mm` forces equality throughout. Equality would require constant curvature magnitude `1/R` wherever the horizontal tangent component is nonzero. That conflicts with zero endpoint curvature and continuous curvature at the endpoints, so the target is strictly unattainable under these assumptions.

The assumptions apply to this candidate: its degree-five lip has exact vertical endpoint jets, nonzero endpoint speeds, strictly decreasing radius on the open parameter interval, and an exact same-sign Bernstein coefficient certificate for `r' z'' - z' r''`. These establish a regular, convex, one-turn, no-inflection half-turn. The proof would not by itself rule out a non-convex or multi-turn lip, but those are outside this fixed candidate. Increasing the local endpoint gap to `3.5 mm` makes the `1.25 mm` radius target feasible in principle because the necessary lower bound becomes `gap/2 = 1.75 mm`; finite samples still must be checked, and do not prove a whole-span bound.

## Frozen coupled shape

The quintic Hermite data are converted to exact rational degree-five Bezier control nets. Every declared non-axis join shares position, first derivative, and second derivative exactly. Monotonicity is checked from exact control-polygon derivative signs. Paired wall spans share their z poles; radial pairing does not establish normal thickness.

The outer underside and base stations are `(12,0)`, `(15,1.5)`, `(18,6.5)`, and the shared wall root `(20,10)` mm, with tangents `(4,0)`, `(4,3)`, `(8,14)`, and `(8,14)` in mm per local parameter. The outer wall then passes through `(24,17)`, `(30,30)`, `(38,50)`, `(42,70)`, `(39,96)`, and the rim `(37.5,110)` mm. Side radial gaps are exactly `2.5 mm` before the final shoulder-to-rim span, then transition to `3.5 mm` at the rim while preserving C2 endpoint jets and the same z poles.

The inner base fairing shares the wall-root jet at `(17.5,10)` mm, adds the fixed station `(13.75,7.5)` mm, and meets the inner floor tangent at `(10,4.5)` mm. This is deliberately one bounded fairing candidate, not an optimization range. It remains a known design failure if the finite curvature check confirms its second span below the `1.25 mm` target; the target will not be relaxed and no further tuning is included in this candidate.

The lip uses a vertical tangent scale of `7 mm` per local parameter, zero second derivative at both endpoints, a fixed `3.5 mm` radial gap, and symmetric control poles. Its exact crest is above the rim endpoint. The case JSON pins every value to this one candidate; its degenerate ranges document fixed values, not a promised family domain.

## Evidence boundaries

The pre-freeze exploratory run is retained under `tmp/review_20261005/smooth_coupled_design/` with an explicit exploratory filename. It reports exact non-axis C2 and control checks passing, sampled outer base/lower-body and lip radii above `1.25 mm`, and an inner base fairing minimum near `0.743 mm` below target. It is exploratory because the case metadata wording is being corrected before the source/case freeze; its JSON must not be presented as the frozen run.

The planned frozen run samples analytic Bezier derivatives at `1001` uniform parameter values per span and tests `101` normal rays per eligible outer base/side span. These are finite floating-point diagnostics, not whole-span curvature bounds. A 2D normal probe finds a candidate intersection with the paired inner boundary, not a classifier-confirmed material interval, not a surface-normal thickness proof, and not a global minimum. The probe excludes near-axis samples and samples with outward radial normal dot `<= 0.25`; reports must retain these exclusions and every UNKNOWN.

An old native classifier UNKNOWN from v1, at `(x,y,z) = (13.565030591,-9.063863664,4.531738447) mm`, may be shown only as historical context on the RZ plot at `r = sqrt(x^2+y^2)`. It has not been tested on v2 and does not locate a v2 failure. If a later, separately authorized native run is made, keep classifier tolerance at `1e-7 mm`; inspect trim state and face orientation and probe both normal offsets around the selected boundary without promoting UNKNOWN by tolerance relaxation.

No CAD/OCC/STEP work is part of this freeze. The shape is an analytic candidate only, and a plotted RZ section is not a CAD solid or a claim of realistic vessel styling.

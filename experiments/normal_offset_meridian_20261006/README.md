# Jar meridian true-normal offset certificate — source only

This is a bounded exact-arithmetic kernel plus a fixed one-shot adapter for a later, separately authorized check of the frozen jar candidate. The adapter is source only until root GO; it verifies the saved result and independent audit before exact Boehm extraction, certificate arithmetic, or display sampling. It never reads NPZ, invokes a curve driver, renders, or creates CAD.

## Frozen scope

The source concerns only the 2D meridian curve of this jar engineering candidate. It cannot promote the parent body to PhysicsReady. Successful local status is exactly `INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE`. Whole-body minimum wall thickness, normal-strip global injectivity, lip closure, revolved-surface self-intersection, native B-rep validity, material properties, and physics status remain `UNKNOWN`.

The pinned upstream evidence is the saved result JSON, its frozen semantic-base/neck driver, and the independent saved audit. The parent reports all 10 jar side spans pass the R9 curvature bound, with 12 regularity, 11 C4, and 5 feature checks passing. The 80-iteration optimization did not converge; that is not treated as a geometry feasibility failure. This source-only pass records those as provenance premises and does not recompute them. `certify_study()` requires explicit true attestations for pinned all-span R9 and regularity before it can emit the successful status.

## Exact geometry and certificate

For degree-5 polynomial Bezier span coordinates `r(u), z(u)` supplied as exact rational Bernstein controls, `v=sqrt(r'^2+z'^2)` and the inward unit-normal offset at `t=3 mm` is

`r_i = r - t z'/v`, `z_i = z + t r'/v`.

With signed curvature `kappa=(r' z''-z' r'')/v^3`, the offset derivative is `(1-t*kappa)(r',z')`. The pinned regularity audit supplies `v>0`; the pinned R9 bound gives `1-t*kappa >= 2/3` on every side span. Straight base/neck spans require exact zero curvature and have factor 1. The source does not substitute a radial offset or claim a rational offset curve.

To prove the inward radius is nonnegative, first establish `r>=0` and `z'>=0`, then certify exactly

`Q = r^2 (r'^2+z'^2) - t^2 z'^2 >= 0`.

For degree 5, Q has degree 18 and 19 Bernstein coefficients. Bernstein products and degree elevation use `Fraction` arithmetic. All exact endpoint negatives are counterexamples. Nonnegative coefficients prove the whole interval. Mixed coefficients trigger midpoint de Casteljau subdivision; unresolved mixed signs, exhausted depth, or exhausted shared budget return `UNKNOWN`, never `FAIL`. One shared study budget covers all checks: at most 64 visited nodes and depth 6.

Side monotonicity requires nonnegative `z'` Bernstein controls with at least one positive control, which implies strict increase in the open span. The flat base requires `z'=0` and monotone `r`; the straight neck requires `r'=0` and monotone `z`. Their local curve checks exclude 2D meridian self-crossing under those premises only.

`true_offset_display_25()` returns 25 direct normal-offset samples per supplied span for a later finite display. These samples are display data, never proof. No such samples are computed in this pass.

## Negative fixtures and review state

`case_false.json` contains (1) a radius-1 vertical straight span whose 3 mm true inward offset has exact endpoint Q=-8 mm^4 and radius -2 mm, and (2) a strictly positive polynomial with mixed Bernstein controls that remains unresolved under the declared depth/budget. Each fixture has its own 8-node/depth-6 budget, separate from the single jar study. The expected outcomes are a real endpoint counterexample and `UNKNOWN`, respectively.

The fixed runner verifies the embedded and independent input hashes, extracts 12 spans with 44 exact knot insertions, makes one shared 64-node/depth-6 certificate call (37 primitive nonnegative checks), and prepares 25 display samples per span. The two false-fixture calls use independent budgets. It has a 15-second outer limit, one-shot lock, no retry, and a 4 MiB aggregate output cap counting result, receipt, lock, and raw stdout/stderr bytes. Receipt summaries use UTF-8 replacement decoding while `.bin` logs preserve captured bytes. Rendering is a later saved-result-only step.

Current state: `SOURCE_ONLY_READY_AWAITING_ROOT_GO`. Only Python AST, JSON, and SHA checks are permitted in this pass. A future root GO is required before extracting control points, constructing span inputs, running the certificate, or generating the 25-point display data.

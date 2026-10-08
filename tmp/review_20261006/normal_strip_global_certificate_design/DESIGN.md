# 3 mm normal-strip global certificate — design proposal

**State:** design only; no geometry was evaluated and no certificate or test was run. The selected engineering path is the jar outer meridian → exact 3 mm inward normal meridian → explicitly closed mother profile. The design is independent of the pending local-offset trial result.

## Why a second certificate is required

The pinned local kernel defines the exact inward normal offset

\[
F(u,t)=c(u)+tN_{in}(u),\qquad
N_{in}=(-z'(u)/v(u),\ r'(u)/v(u)),\qquad
v=\sqrt{r'^2+z'^2},\quad 0\leq t\leq3\text{ mm}.
\]

For the source's signed curvature convention, its differential is

\[
F_u=(1-t\kappa)c'(u),\qquad F_t=N_{in},\qquad
\det(F_u,F_t)=(1-t\kappa)v.
\]

The pinned jar R9 premise gives `1 - t*kappa >= 2/3` on the side spans; exact straight base/neck pieces have factor 1. With `v>0`, this proves a nonsingular local normal map throughout the strip. It rules out a local focal fold. It does **not** rule out distant normal fibres meeting, a boundary loop crossing itself, an inner profile colliding with a remote outer segment, or a closure patch crossing the strip. The existing local `Q >= 0` proof addresses offset radius, not global injectivity or minimum wall thickness. The kernel itself reports both `global_wall_status` and `normal_strip_global_injectivity` as `UNKNOWN`.

## Preferred proof route: Jordan boundary plus degree

Let `D = [u0,u1] x [0,3]` be the complete parameter rectangle for the proposed outer-to-inner strip. First prove exact regularity `v>0` and the stated positive Jacobian bound on every closed span and every join. Prove that the mapped boundary `F(∂D)` is one simple Jordan curve, with the orientation induced by the positive Jacobian. The boundary consists of the outer meridian (`t=0`), the reversed true-normal inner meridian (`t=3`), and the two endpoint fibres. Each endpoint fibre must be the actual base/lip connector if this rectangle is claimed to describe the closed mother. If the production base or lip differs from a normal fibre, include its exact closure patches and prove their seams and nonintersection separately; a strip-only Jordan curve does not certify that extra closure.

Then apply the planar degree theorem. For a point away from the mapped boundary, the degree equals the winding number of the Jordan boundary. It is 1 inside and 0 outside. Every interior preimage has positive local index because `det(F_u,F_t)>0`, so an interior point has exactly one preimage. Boundary simplicity gives uniqueness for boundary preimages. An interior point cannot map onto the Jordan boundary: local openness would also map nearby points to the exterior, where the degree is zero. Thus `F` is globally one-to-one on the closed rectangle and is a homeomorphism onto its image. This proves an embedded normal strip, conditional on every stated boundary and regularity premise.

The boundary proof is itself a global obligation. Use exact rational Bezier controls for the outer curve and exact join equalities. Enclose the algebraic inner curve and endpoint normals with outward rational intervals. For each pair of boundary arcs, prove disjointness unless they are the same arc or share a prescribed endpoint; at a shared endpoint, prove a one-sided local chart and the exact seam equality. A positive orientation witness or exact winding computation must accompany Jordan simplicity. Finite display samples or a finite set of radial rays cannot establish this boundary claim.

## Fallback proof route: interval patches over the full strip

Use this route if the boundary-pair proof is too weak or if additional closure patches must be included. Partition every exact Bezier span crossed with `t ∈ [0,3]` into rational parameter rectangles. The partition must cover the complete closed domain, including span seams and any separately mapped base/lip patches.

For each cell, bound `q = r'^2 + z'^2` with rational Bernstein/subdivision bounds. If `0 < q_lo <= q <= q_hi`, use `1/sqrt(q_hi) <= 1/sqrt(q) <= 1/sqrt(q_lo)` to construct outward-rounded rational enclosures for `N_in`, `F`, and `DF`. A cell with no strictly positive speed lower bound remains unresolved. Record interval endpoints and every comparison exactly; do not use floating tolerances as proof.

Prove local injectivity on a finite cover of the domain, including neighborhoods crossing every join. One sufficient check on a convex chart `U` is a rational nonsingular matrix `A` with an exact enclosure proving `sup_U ||A^-1 DF - I||_∞ < 1`; the mean-value bound then makes `F` injective on `U`. For each remaining pair of cells, prove their image enclosures disjoint. A pair may be omitted from the separation list only when a common certified local chart covers both cells. Shared seams may intersect only at their prescribed common image; prove that equality and use the joint chart to exclude other coincidences. A machine-checkable cell-pair table must show that every source-point pair is either covered by one injective chart or by an image-disjoint cell pair. If that coverage cannot be established, return `UNKNOWN`.

Use one candidate-wide cap of **256 interval cells and refinement depth 8**. Count boundary/cap cells and any square-root enclosure refinements in the same budget. Budget exhaustion, a zero speed lower bound, overlapping unresolved image boxes, or a missing pair-coverage case means `UNKNOWN`; it is not evidence that the target geometry is impossible. A negative result is permitted only with an exact distinct-parameter collision witness or another exact violated premise.

## Existing coefficient evidence and missing obligations

The frozen rational Bezier coefficients can directly support exact derivative/curvature expressions, C4 join checks, Bernstein hull bounds, span regularity and monotonicity checks, straight-base/neck checks, and the existing local radius numerator `Q`. The pinned metadata reports jar geometry evidence and records that the 80-iteration optimizer did not converge; optimizer status does not decide this topological proof. The independent audit is pinned as a reconstruction audit, not as a global strip certificate.

The source does not currently provide a Jordan proof, exhaustive nonadjacent parameter-pair separation, a quantitative speed lower bound carried into square-root interval enclosures, a complete exact lip/base boundary model, or a global nearest-point/reach proof. The local R9 factor plus `Q >= 0` cannot substitute for those missing results. Even a globally injective side strip is not by itself a complete closed mother or a native B-rep certificate.

For a **3 mm minimum Euclidean wall** claim, include the entire relevant closed boundary and endpoint/cap behavior. For a point on the 3 mm inner offset to have its generating outer point as its nearest point, rule out a closer foot on every other outer or closure piece. For a closed regular boundary, an alternative closest point in the inward direction would produce a second normal representation inside the certified strip; endpoints, corners, axis contacts, and non-normal lip/base patches need separate checks. State this nearest-point conclusion separately from the simpler claim that the normal map is injective.

## Boundary cases that must be explicit

- **Axis `r=0`:** meridian-plane injectivity does not make revolution regular at the axis; the angular orbit collapses there. Prove `r>=0`, identify every intended axis contact, and provide a compatible cap/vertex sewing rule. If the part never reaches the axis, prove a strict positive radial lower bound. A local nonnegative-radius result alone is insufficient.
- **Flat base and straight neck:** their curvature factor is 1, but they remain in the global cell-pair and boundary checks. Straightness does not prevent collision with a remote inner, lip, or side patch.
- **Lip and endcaps:** give exact curves/surfaces, endpoint equality, tangent/jet requirements for the intended joint, and nonintersection checks. A sampled or visually smooth lip is not a certificate.
- **Span adjacency:** carry exact C4 join identities and positive speed through all seams. Joint local charts must cover adjacent cells, including the corners at `t=0` and `t=3`; do not silently skip adjacent pairs.
- **Closed profile/revolution:** verify the complete outer + lip + inner + base contour is a simple oriented meridian boundary in `r>=0`. A successful 2D side-strip proof does not by itself validate the 3D revolved surface or any CAD kernel topology.

## Minimum future fixtures

1. **Positive control:** an exact rational straight meridian `c(u)=(R,H u)`, with rational `R>3 mm` and `H>0`, represented as degree-5 Bezier data. Its strip is the rectangle `F(u,t)=(R-t,H u)`; the expected result is `PASS`, with no axis contact. This exercises the boundary/degree path and exact cell coverage without relying on samples.
2. **Nonlocal crossing negative:** an exact rational C4 Bezier chain with two nonadjacent straight branches separated by a rational gap `g` satisfying `0<g<6 mm`, oriented so their inward normals face one another. The fixture must include an exact pair of distinct parameters and depths `t1,t2 ∈ [0,3]` with `t1+t2=g`, proving `F(u1,t1)=F(u2,t2)`, while an independent exact check establishes `1-t*kappa>=2/3` over the entire chain. The remote connector must preserve that local premise and the source curve itself must be simple. Expected result: `EXACT_COUNTEREXAMPLE_GLOBAL_COLLISION`, not `UNKNOWN` and not a curvature failure. Until a concrete pinned rational connector and equality witness are supplied, this is a fixture specification, not a completed test.

The existing local `case_false.json` fixtures remain useful for radius-counterexample and unresolved-Bernstein semantics, but they do not exercise this global certificate.

## Minimum prerequisites before native closed B-rep work

Require a globally simple meridian contour in `r>=0`, exact outer/inner/base/lip endpoint correspondence, no unintended patch intersections, and an explicit axis rule. Revolved faces must have consistent orientation and closed sewing: each non-seam edge is paired exactly twice, shared edges use matching parameterization, and no T-junctions or zero-area sliver faces remain. Treat the axis as a collapsed orbit with deliberate cap topology. Then run the selected CAD kernel's native validity check on the closed solid. These are geometry/B-rep prerequisites only; style, material, novelty, and physics remain separately unproven.

## Pinned source context

- Normal-offset kernel: `normal_offset_meridian_certificate.py`, SHA-256 `48ee9fbc2c69ba97dbeb3f34de298a60571786aaf3359cc784b79d2fbfaa6114` (216 lines); README SHA-256 `93f456967f3f7ea31440e1bc5b814380efbe7df90faf422995e6874a17d7a1ef`.
- Frozen constrained source: `curvature_constrained_meridian.py`, SHA-256 `96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce` (450 lines).
- Saved candidate result SHA-256 `839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185`; independent saved audit SHA-256 `fe0c7c0f1af9fda79d2f94b607b58629bf1e04317a3bd22b290ea92340bbdc0b`.
- Frozen semantic driver SHA-256 `038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3`.

Only source mathematics and saved metadata were inspected for this design. Numeric control payloads were not read or used. No solver, curve, geometry, CAD, renderer, or test was run.

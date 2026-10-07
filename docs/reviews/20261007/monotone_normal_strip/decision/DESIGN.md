# Monotone-slice proof for the jar normal strip

**State:** proof design for root decision only. No new curve, geometry, optimizer, kernel, CAD, or test run was performed. Only the pinned saved JSON and frozen-source mathematics were read. The result is independent of the local-offset run's global status.

## Finding

For this actual jar, the saved exact coefficient signs support a much smaller proof than a two-dimensional cell-pair search. With the existing local factor `1 - s*kappa >= 2/3`, fixed-depth height is nondecreasing along the whole base/side/neck path. It is constant only along the single flat base. At any fixed height, the side/neck portion is a unique branch and its radius strictly decreases as normal depth `s` increases. The base plateau is injective in radius and attaches to that branch at one seam. Subject to the endpoint/closure premises below, this proves the **2D meridian normal-strip map is globally injective** and its image is a Jordan strip.

This is a conditional proof route, not a certificate result. The saved local-offset output still says `normal_strip_global_injectivity=UNKNOWN` and `global_wall_status=UNKNOWN`. Even after a successful monotone-strip certificate, minimum Euclidean wall thickness against all closure patches, lip geometry, and native B-rep validity remain separate obligations.

## Exact source evidence

- Normal-offset result: `vesselforge/tmp/review_20261006/normal_offset_meridian_20261006/retry01_after_zprime_fix/normal_offset_meridian_result.json`, SHA-256 `96ea35c44d40d12acc4b57a932ebb5194dbccdfd516b1fc2338ec58c51a9956a`. It reports `INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE`, 12 span-local passes, and leaves both global fields `UNKNOWN`.
- Constrained saved result: `vesselforge/tmp/review_20261006/curvature_constrained_meridian_20261006/curvature_constrained_meridian_result.json`, SHA-256 `839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185`. Its jar metadata reports all ten nonflat side spans proved at R9, all 12 spans regular, all 11 joins C4, and the exact feature/hull gates passing. It explicitly leaves `global_normal_wall=UNKNOWN_NOT_COMPUTED`.
- Frozen driver: `vesselforge/experiments/semantic_base_neck_bspline_20261006/semantic_base_neck_driver.py`, SHA-256 `038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3`. `_derivative_poles` forms exact degree-scaled consecutive Bezier-control differences divided by positive span width; `certify_controls` records nonnegative z-derivative poles, open-span regularity, and exact C4 endpoint jets.
- Normal-offset source: `normal_offset_meridian_certificate.py`, SHA-256 `48ee9fbc2c69ba97dbeb3f34de298a60571786aaf3359cc784b79d2fbfaa6114`. It uses `F=(r-s*z'/v, z+s*r'/v)` and `F_u=(1-s*kappa)c'`.

The following signs are exact signs of the stored derivative Bernstein poles, computed from the serialized rational Bezier controls as `5*(p[i+1]-p[i])/h`; `h>0` does not affect signs. `0` means an exact zero pole. These are sign summaries only, not reconstructed or sampled curves.

| span | kind | z′ pole signs | r′ pole signs | implication |
|---:|---|---|---|---|
| 0 | flat base | `00000` | `+++++` | z′ is identically zero; r′ strictly positive |
| 1 | side | `0000+` | `+++++` | z′ is positive in the open span; its base-join endpoint may be zero |
| 2–4 | side | `+++++` | `+++++` | z′ positive throughout each span |
| 5 | side | `+++++` | `++++0` | z′ positive; radial tangent reaches zero at apex seam |
| 6 | side | `+++++` | `0----` | z′ positive; radial tangent leaves apex with negative sign |
| 7–9 | side | `+++++` | `-----` | z′ positive and r′ negative |
| 10 | side | `+++++` | `-0000` | z′ positive; radial tangent reaches zero at neck seam |
| 11 | straight neck | `+++++` | `00000` | z′ positive and r′ identically zero |

For every side/neck span, the z′ Bernstein poles are nonnegative and at least one is positive. Since every degree-4 Bernstein basis function is positive on the open span, this proves `z′(u)>0` at every interior point even when endpoint poles are zero. On the base, exact flatness gives `z′=0`, while every r′ pole is positive. The saved metadata pins exact C4 at both special joins `u=1/12` and `u=11/12`; all 11 joins pass.

The same saved exact endpoint coefficients prove three needed ordering predicates without printing their values: the outer start is on `r=0`; terminal neck radius is strictly greater than 3 mm; and `z_mouth-z_base > 3 mm`. The offset certificate also passes its exact nonnegative-radius check. These are meridian predicates only.

## Fixed-height injectivity proof

Write `c(u)=(r(u),z(u))`, `v=sqrt(r′²+z′²)`, `N=(-z′/v,r′/v)`, and `F(u,s)=c(u)+sN(u)`, with `0<=s<=3`. Let `lambda=1-s*kappa`. Then

\[
Z_u=F_{z,u}=\lambda z',\qquad Z_s=F_{z,s}=r'/v,
\]

\[
R_u=F_{r,u}=\lambda r',\qquad R_s=F_{r,s}=-z'/v.
\]

On side and neck, `lambda>=2/3` and `z′>0` in each open span, so for fixed `s`, `Z(u,s)` strictly increases from the base/side seam to the mouth. Exact C4 joins make `F` continuous and preserve the same tangent/normal at the base-side and side-neck seams. Zero z′ at the first side endpoint is allowed: it is an isolated seam endpoint, not a flat side interval.

For any fixed target height `Z` above the base plane and below the mouth, the side/neck equation `Z(u,s)=Z` therefore selects a unique `u(s)` whenever `z_base+s < Z`. Implicit differentiation on each open span gives

\[
\frac{du}{ds}\Big|_Z=-\frac{r'/v}{\lambda z'},\qquad
\frac{dR}{ds}\Big|_Z=R_s+R_u\frac{du}{ds}=-\frac{v}{z'}<0.
\]

The curvature factor cancels. Thus one fixed-height level cannot contain two side/neck points at distinct normal depths with the same radius. At a span seam or isolated endpoint with `z′=0`, use continuity and the strictly decreasing limits from adjacent open spans; no division by zero is asserted at that endpoint. At a fixed depth, strict z monotonicity selects only one side/neck parameter.

The base is the sole plateau and must be handled directly, not by dividing by `z′`. There `r′>0`, `z′=0`, hence `F(u,s)=(r(u), z_base+s)`. A fixed height meets the base at exactly one depth `s=Z-z_base`, and the base radius is strictly increasing from the axis to the base/side seam. The side/neck branch at that height exists only for smaller depths and its radius decreases toward the seam radius; it stays strictly outside the base-radius interval, touching it only at the same seam point. Therefore the base creates no second preimage.

For each height `Z`, the admissible depth set is the connected interval `0<=s<=min(3,Z-z_base)` when `z_base<=Z<=z_mouth`, because the two endpoint heights are `z_base+s` on the flat-base axis end and the constant `z_mouth` on the vertical neck end. The exact saved inequality `z_mouth-z_base>3` keeps the whole strip ordered. The preceding cases prove injectivity for every height slice, hence for all of `F([u0,u1]x[0,3])`. A continuous injection from this compact rectangle is a homeomorphism to its image; its boundary is consequently a simple Jordan curve. This replaces global 2D cell-pair search for this specific profile.

The same calculation proves radial nesting of the side/neck graphs on their common height range: for `z_base+3 < Z < z_mouth`, the 3 mm graph has smaller radius than the outer graph at that height. The bottom interval is exceptional: the inner flat base is at `z_base+3`, so it must be treated as the cap/axis part of the cross-section, not as a side graph over the outer base's full height range.

## Endpoints, closure, and claim limits

- **Axis:** `r(u0)=0` and `F(u0,s)=(0,z_base+s)`. This is injective in the meridian plane. Under revolution, every angular value collapses to the axis; omit this degenerate orbit as an ordinary face and provide the intentional cap/vertex topology. The normal-radius pass proves nonnegative radius; it does not validate the revolved cap.
- **Base/side seam:** the base tangent has `r′>0,z′=0`; the first side span has a zero z′ endpoint pole but is strictly rising immediately inside. Exact C4 identifies the seam normal and endpoint fiber.
- **Apex:** `r′` changes sign through zero while `z′>0`; the fixed-height proof does not require monotone radius along the outer meridian and remains valid there.
- **Side/neck seam:** `r′` reaches zero and the straight neck has `r′=0,z′>0`; exact C4 makes the offset join continuous. Along the neck, `F=(r_m-s,z)`.
- **Top/lip:** the terminal normal fiber is `(r_m-s,z_mouth)`, a radial segment. The closed-mother claim is covered only if the intended lip is exactly this segment with the pinned endpoint/seam; otherwise its full patch must be checked against the strip and all other closures. A mouth rim that is not this fiber leaves the closed profile unresolved.
- **Minimum wall:** strip injectivity and same-height radial nesting do not alone prove a 3 mm minimum Euclidean distance to arbitrary lip/base/cap faces. A nearest-foot/reach argument must include the complete closed boundary and handle endpoint/corner minimizers. Until then `global_wall=UNKNOWN`.
- **Native B-rep/revolution:** still requires a simple closed meridian with explicit cap/lip sewing, valid collapsed-axis topology, and native kernel validation. This design makes no material, physics, style, or B-rep claim.

## Minimal bounded implementation and counterexamples

1. Read only the pinned exact JSON controls and existing certificate flags. Form each degree-4 derivative-pole sign from exact rational differences; verify the sign table above, the base and neck identities, positive endpoint predicates, local `lambda` premises, exact endpoint regularity, and the two seam C4 records. No square roots need numeric enclosure: the proof uses only `v>0` and the sign of `-v/z′`.
2. If any z′ pole vector is mixed, first use exact 1D Bernstein subdivision only (proposed cap: depth 8 and 64 total leaves across spans). A proved nonnegative nonzero polynomial is acceptable; unresolved sign, extra flat interval, endpoint-range gap, or missing closure premise returns `UNKNOWN`. Do not fall back to finite rays or classify the geometry as impossible.
3. Positive fixture: an exact monotone side with one radial flat base and one vertical neck, exact C4 seams, `z_mouth-z_base>3`, and the endpoint normal fibers as closures. Expected: fixed-height proof closes and the strip is injective.
4. Negative fixture: an exact simple rational chain with two nonadjacent facing straight branches at same-height locations, gap `g<6 mm`, and exact distinct `(u1,s1),(u2,s2)` where `s1+s2=g` gives equal `F`. Keep `lambda>=2/3` on the connector. Expected: exact collision counterexample; the z′ monotonicity gate fails, demonstrating that local curvature alone is insufficient.
5. Sufficiency false-positive guard: a fixture with mixed Bernstein poles but a truly positive z′ polynomial must remain `UNKNOWN` until exact 1D subdivision proves the sign; mixed control coefficients alone do not imply geometry failure.

Compared with the general Jordan/2D interval design, this route is smaller and uses exact signs already present in the candidate. It is candidate-specific: a second height plateau, nonmonotone z, a lip patch outside the terminal normal fiber, or a non-normal cap returns to a separate closure/patch proof rather than being silently covered.

# Global wall-distance review

## Decision

The saved/design theorem for injectivity of `F(u,s)` only on `0 <= s <= 3` does **not by itself** prove `min |c(u)-F(v,3)| >= 3`. Exact base and mouth fibers establish the corresponding distances, but do not exclude a nonlocal pair. For an interior nearest point on the inner curve, stationarity plus `q'(v)=(1-3κ(v))c'(v)` gives `c(u)=F(v,3±d)` when the distance is `d<3`. Injectivity through depth 3 excludes the `3-d` case; it says nothing about `3+d`.

A counterexample uses two interior straight subarcs oriented east: `A(x)=(x,0)` and `B(x)=(x,4)`, with left normal north. Their depth-3 strips occupy `0<=y<=3` and `4<=y<=7`, so they are disjoint, while `dist(B(x), F_A(x,3))=1`. Join their remote ends with a broad smooth connector whose strip stays clear, and add remote straight terminal pieces if desired. The whole depth-3 normal strip remains embedded, yet the outer-to-inner minimum is at most 1. Thus the issue can occur at an interior footpoint, even with zero curvature on the two relevant pieces.

## Conditional route for this jar

The exact evidence described in `DESIGN.md` appears to support a stronger, candidate-specific proof, subject to completing the following bounded checks. Extend the formula for `F` to `0<=s<=6`. The all-side `Rcurv>=9` bound gives `lambda=1-sκ>=1/3` through depth 6; base and neck have `lambda=1`. The side/neck have `z'>0` on open spans, and the base is the sole `z` plateau. The fixed-height identity `dR/ds=-v/z'<0` therefore still holds through depth 6. With `z_mouth-z_base=120>6`, the same slice argument (base plateau handled directly, seams identified by the exact C4 jets) proves the extended meridian map injective. The exact radial sign pattern and endpoints give `r>=18` on the side, so the extended strip remains at nonnegative radius (side `R>=12`, neck `R>=20`).

For an interior minimizer of `|c(u)-q(v)|`, `q(v)=F(v,3)` and `q'=(1-3κ)c'` is nonzero and parallel to `c'`. Hence `c(u)-q(v)=αN(v)`. If the distance is `d<3`, then `c(u)=F(v,3+α)` with `0<3+α<6`, contradicting injectivity of the extended strip against `c(u)=F(u,0)`. A corresponding pair has distance exactly 3, so this proves equality once endpoint minimizers are excluded.

The endpoints can be discharged from the actual signs, rather than assumed clear. At the axis, `q(a)=(0,3)`: the flat base has distance `sqrt(r²+9)>=3`, and every side/neck point has `r>=18`. At the mouth, `q(b)=(23,120)`: the neck has `r=26`, hence distance at least 3. If a closer side point minimized distance to this endpoint, stationarity in `u` would put `q(b)-c(u)` on `±N(u)`. The outward sign is impossible: it would require `c_r<23`, which by the exact sign table occurs only on the rising side (`r'>0`), where `q_z-c_z>0` has the opposite sign from `-N_z`. The inward sign would give `q(b)=F(u,d)` for `0<d<3`, contradicting extended injectivity and `q(b)=F(b,3)`. Check the two outer endpoints directly. This argument relies on the saved rising/falling radial signs and monotone `z`, not only the straight neck endpoint.

Thus a separate no-endpoint-nearby premise is necessary for the abstract depth-3 theorem, but the stated jar signs plus a verified depth-6 extension can supply the needed endpoint lemma. Until that extension and endpoint argument are exact-certificate-bound, the Euclidean minimum remains unproved.

## 3D and closure scope

For full surfaces of revolution with nonnegative radii, the squared distance between points at azimuths `θ,φ` is

`(r-ρ)^2 + (z-ζ)^2 + 2rρ(1-cos(θ-φ))`.

Its minimum over azimuth is the meridian distance, also when a radius is zero. Therefore the meridian curve-pair bound transfers exactly to the revolved side surfaces. At the axis all azimuths collapse to one point; this does not change the distance identity, but CAD still needs intentional axis vertex/cap topology and kernel validation.

This claim concerns only `c` versus `F(.,3)`. A real CAD lip, fillet, seam, cap, or other closure patch is outside that pair. An exact radial 3 mm mouth fiber gives the mathematical endpoint, but does not certify a modified CAD lip or its junctions. Do not call clearance to a lip or closed material region “wall thickness”; model the actual closure and state the thickness convention separately.

## Bounded certificate plan

1. Bind the exact controls, all 11 C4 joins, derivative signs, base/neck identities, endpoint coordinates, side `Rcurv>=9`, and `z_mouth-z_base>6` to the pinned geometry.
2. Prove `lambda>=1/3` for `s<=6`; use exact sign/range arguments on fixed-height slices, with the flat base and both seams handled as separate cases. Return `UNKNOWN` if any sign, seam, or range premise is unresolved.
3. Certify endpoint clearance directly as a fallback/independent check: on each rational quintic span form exact degree-10 Bernstein coefficients of `|c(u)-q(a)|²-9` and `|c(u)-q(b)|²-9`; use exact subdivision with a fixed depth/leaf cap and endpoint-factor handling at the axis and mouth equalities. Unresolved leaves return `UNKNOWN`.
4. Only then claim the meridian minimum equals 3 and transfer it to the revolved side surfaces. Check actual CAD lip/seam/cap patches and native B-rep validity as separate obligations.

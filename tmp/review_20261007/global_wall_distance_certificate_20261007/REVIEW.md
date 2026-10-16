# Global wall-distance checker review

The depth-3 strip result remains a conditional injectivity result and reports Euclidean wall distance as `UNKNOWN`. The new source checker does not reuse that result as a distance proof.

It binds the pinned actual jar B-spline controls to the local exact Bezier spans, verifies the ten R9 polynomials and eleven global-parameter C4 joins, and checks the complete derivative sign table. Those signs give a single rising side/neck height branch, a single flat base, and side radius at least 18 mm.

The exact R9 inequality gives `|κ|<=1/9`; hence `lambda=1-sκ>=1/3` for `0<=s<=6`. The same fixed-height argument extends to depth 6 because `z_mouth-z_base=120 mm`; the base plateau and seam fibers require their stated separate cases. Since `|N_r|<=1`, the inner radius is at least 12 mm on the side and 20 mm on the neck at depth 6.

Interior nearest-footpoint stationarity then maps any pair shorter than 3 mm to a collision between `F(.,0)` and `F(.,s)` for some `0<s<6`, contradicting that extended embedding. The axis and mouth inner endpoints are separately checked against every outer span with exact degree-10 Bernstein subdivision, depth cap 8 and 64 leaves per span.

If run successfully, the meridian curve-pair minimum is exactly 3 mm and the same set-distance minimum holds for their full surfaces of revolution. The checker has not been executed; therefore no PASS, numeric result, CAD lip result, native B-rep result, or production wall qualification is asserted. Any unproved premise or exhausted subdivision budget returns `UNKNOWN`.

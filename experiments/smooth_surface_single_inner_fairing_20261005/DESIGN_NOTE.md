# Single-span inner base fairing candidate

This isolated candidate inherits the frozen beaker v2 case and changes only its inner base fairing. It removes the interior station `(13.75, 7.5) mm`, keeps the exact parent inner-wall root jet at `(17.5, 10) mm` and inner-floor tangent jet at `(10, 4.5) mm`, and replaces the two parameter widths `0.3 + 0.5` with one fixed width `0.8`. All outer stations, side spans, thickened rim, lip, root/floor endpoint jets, case dimensions, and other v2 parameters remain identical.

The exact quintic Hermite-to-Bezier control points implied by those endpoint jets and width `0.8` are:

| Pole | r (mm) | z (mm) |
|---:|---:|---:|
| 0 | 17.50 | 10.00 |
| 1 | 16.22 | 7.76 |
| 2 | 14.94 | 5.52 |
| 3 | 11.28 | 4.50 |
| 4 | 10.64 | 4.50 |
| 5 | 10.00 | 4.50 |

The pole differences establish strictly decreasing radius and nonincreasing height by the Bernstein derivative-control sign property. With radius strictly decreasing, the parameterized arc is regular and injective. The source adds an exact rational Bernstein-sign check for `r' z'' - z' r''`; only a nonzero same-sign certificate may establish the arc's no-inflection convexity. A separate 1001-sample curvature check evaluates the unchanged `1.25 mm` finite-sample target and does not imply a whole-span radius bound. No result is pre-assumed: if curvature sign certification or the sample target fails, the fixed candidate remains `NEEDS_REVIEW` and is not tuned.

The inner root and floor endpoint jets are inherited exactly, so the single span remains C2-connected to the same inner wall and floor. Removing the interior station removes the imposed two-piece change of curvature that produced the observed S-like inner fairing. Whether the remaining single span meets the curvature target is an open diagnostic result.

This is one analytic beaker profile only. Vessel style and material are unknown; the radial side gaps are not normal thickness; physical qualification, native validity, global self-intersection, global minimum normal wall, and reusable family bounds remain unknown. The nominal `110 mm` height remains the rim endpoint elevation, not the lip crest or a validated native bounding height. This candidate has no CAD/OCC/STEP execution in its freeze scope.

# Catalog corner fairing — source-only review receipt

Review scope: inspect the already-produced source, design note, JSON audit, source pins, and profile plot. This receipt adds no geometry, CAD, or STEP run. The fairing proposal remains a candidate for independent review; it is not a native model and is not approved for fracture training.

## Inputs and integrity

- The experiment reads the existing `vesselforge.profile_catalog.build_profile("bowl")` and `build_profile("jar")` defaults. It does not edit the catalog or change production geometry.
- `profile_catalog.py` SHA-256 before/after: `e9d4bc1458a107208e537449d6526f1c0077d6d3afc6953a6200d86512f9c26f`.
- Fairing source SHA-256: `6c1e94150d769158c757469141aab23796b005421d3878b150271d375086d534`.
- Exact VF runtime SHA-256 recorded in the audit: `2b83f3f84ea2f51132fa1aae73815be54126a799521de85ff6ea70627cde6da7`.
- `PRE_RUN_SOURCE_PINS.json` and `POST_RUN_SOURCE_PINS.json` are byte-identical; the final audit also says `all_source_pins_unchanged: true`.
- The inspected output sizes are 43,891 bytes for source, 2,602 bytes for the design note, 116,672 bytes for `DESIGN_AUDIT.json`, and 164,328 bytes for the PNG.

## What the final audit establishes

`DESIGN_AUDIT.json` has status `PASS_BOUNDED_MATH_DESIGN_ONLY`, reports 0.953 seconds wall time, `cad_imported: false`, `native_cad_or_step_started: false`, and `step_exported: false`. In the official saved audit, the two defaults together used 207 curve-parameter stations (bowl 90, jar 117) and 216 contour vertices (bowl 95, jar 121), each below the 256 cap. The displayed 207 is a per-execution count, not a count of distinct geometry points across repeated development checks.

- Bowl: 10 eligible corners faired and 5 corners protected. Height 90 mm, maximum radius 60 mm, mouth diameter 108 mm, declared base 6 mm, declared wall 3 mm. Sampled signed-area change is +0.32093 mm². Bounded sampled contour-pair distance is 1.025229 mm before and after to the displayed precision.
- Jar: 13 eligible corners faired and 4 corners protected. Height 120 mm, maximum radius 54 mm, mouth diameter 46 mm, declared base 5.5 mm, declared wall 3 mm. Sampled signed-area change is +0.13853 mm². Bounded sampled contour-pair distance is 1.390641 mm before and after to the displayed precision.
- Catalog wall/base declarations retain their original meaning: the wall is a corresponding-height radial meridian offset, not a measured global normal minimum; the base is an inside-floor datum offset, not a full-solid minimum-wall measurement. Outer and inner profiles are faired independently, so no unchanged-wall claim follows.
- The fairing policy is fixed at 12% of the shorter adjacent segment for each trim, with 25%/50% collinear controls on each trimmed ray. Segments shorter than 2 mm and turns at or above 170 degrees are rejected; adjacent trims consuming at least 25% of a segment are rejected. The endpoints match the source tangent and have zero endpoint curvature, supporting geometric C2 joins for regular curves. Shared-parameter C2 is explicitly not claimed. Controls stay on the adjacent trimmed source rays, so the Bezier convex-hull property confines each curve to that local hull.
- Axis/floor and lip endpoints are protected. The bowl maximum-radius apex is also protected to keep that extremum exact; the jar maximum-radius span remains. This necessarily leaves sharp corners.

The script supplies analytic regularity and curvature-bound checks for each candidate quintic. The self-intersection, contour separation, and curvature extrema checks that rely on finite samples are bounded checks for these two defaults only, not exact/global certificates or a generic catalog-wide proof.

## Repeated-query accounting

The final saved audit contains one execution's 207 curve-parameter stations and 216 contour vertices. The working record for this task also contains five earlier development executions of the same bounded two-default analysis, each reporting the same 207 stations and 216 contour vertices. Across those six executions, the recorded totals are therefore 1,242 repeated parameter-station evaluations and 1,296 repeated contour-vertex samples; these are cumulative work counts, not unique geometry samples. One early exploratory loader pulled in native-module imports through `vesselforge.__init__`, but it did not construct CAD geometry. Subsequent source-only loading and the saved official run bypassed that package initializer. No more math or CAD was run for this review.

## Visual inspection and remaining unknowns

The PNG shows the original catalog polylines, proposed meridian fairings, and protected sharp corners for both families. It is legible, though the shared legend slightly overlaps the jar panel's horizontal-axis label. It is a source-derived profile plot, not a render of a native BRep.

Still unknown: global minimum normal wall and local wall changes; stress/fracture behavior at the retained sharp corners; any between-sample self-intersection or curvature extremum; real-vessel/style correspondence and manufacturing feasibility; and all native BRep, STEP, shell, mesh, material, solver, and fracture qualification. Do not treat this proposal as a true-geometry training body unless it passes separate native validation and review.

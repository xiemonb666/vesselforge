# Smooth surface route proposal — fixed cases v0.2

**State: source, fixed parameters, and review plan only. No Python module was imported and no CAD or STEP operation was run.** The checked-in source contains the actual edge/wire/face/revolve path, but it remains unexecuted pending main-agent review.

## Chosen construction

The two bounded fixtures are a beaker and bowl using the VesselForge catalog defaults in `fixed_cases.json`. Each outer wall is a chain of exact degree-5 Bezier spans made from explicit quintic-Hermite station positions, first derivatives, and second derivatives. Every station stores one shared jet for its adjoining spans, so the join is C2 and local station edits affect only neighboring spans. The inside wall is authored as a matching control net shifted inward by the radial setting at unchanged z. That value is named `wall_radial_setting_mm`; it does **not** claim to be a normal thickness.

The meridian is closed explicitly in this order: flat underside from the axis, quintic outside base blend, outer wall spans, a rounded quintic lip bridge, reversed inner wall spans, flat inner floor, and the axial closure. The outside base blend joins the flat underside and side with matching first and second derivatives. The lip bridge joins the outer and inner sides with matching vertical tangent and zero second derivative. The only excluded C2 joins are the axis endpoints that collapse under revolution. The complete material face is revolved 360 degrees around Z; the source does not call OCC's offset API.

For degree 5 on a local `[0,1]` span, endpoint data `(P0,D0,A0)` and `(P1,D1,A1)` produce:

```text
B0 = P0
B1 = P0 + D0/5
B2 = P0 + 2*D0/5 + A0/20
B3 = P1 - 2*D1/5 + A1/20
B4 = P1 - D1/5
B5 = P1
```

When spans have different parameter widths, the source compares `D_local/h` and `A_local/h²`. The fixed stations set second derivatives to zero at shared points; interior curvature is calculated from analytic Bezier derivatives and sampled along each segment. This is a finite report, not a whole-span curvature bound.

## Why this route follows the recorded evidence

- `vesselforge/src/vesselforge/profile_catalog.py` creates the bowl/beaker/jar candidates as point lists. Its inner profile subtracts a declared radial amount at corresponding control heights and correctly labels that value as not a global normal minimum.
- `vesselforge/src/vesselforge/geometry.py` uses a separate fixed polyline and a discrete corner-miter inner path before revolving. Its profile-distance samples explicitly stop short of claiming a whole-solid minimum.
- The historical `smooth_cad_brep` experiment demonstrated a smooth degree-5 C2 source meridian and a valid one-solid/one-shell native BREP. It still built the inside wall with `BRepOffsetAPI_MakeOffset`; the README records a separate STEP round trip with two shells/zero solids and says the BREP candidate was not promoted. The new source directly builds both sides and the closed material section, so it does not rely on that offset operation. STEP translation remains an independent acceptance check.
- The old interpolated outline's recorded sampled minimum curvature radius was 0.0725 mm, with 664 of 10,001 samples below 4 mm. That is evidence against offsetting that particular outline by 4 mm; it is not evidence about these new fixed curves.

## Fixed-case checks and limits

The source checks the fixed input control nets before CAD construction. For these finite cases it checks the exact Bernstein control polygons for increasing side z, monotone radius within each authored side span, radial separation, positive inner radius, authored radius bounds, monotone base bridge, monotone radial lip bridge above the rim, and floor direction. Those sign checks plus the ordered joins provide a finite fixed-case meridian-simple construction argument and reject an unexplained span overshoot. They do not certify any unsupplied parameter values or a future bowl/beaker family domain; the report retains family-wide self-intersection as `UNKNOWN`.

The native builder creates real CadQuery edges from the six-pole quintic nets, combines one closed wire, creates a positive-area face, and revolves that face. It requires a valid shape with exactly one valid solid and one closed shell, with zero open-boundary shells. The staged checker then samples the actual revolution faces below the nominal rim whose outward normals have a radial component above the documented cutoff, confirms each outward normal with solid classification, queries all line/shape hits, clusters duplicate seam hits, and classifies every interval. It records the first outer-entry/material/inner-exit interval separately from the radial setting. The flat floor and rounded lip are excluded from this sidewall ray set; their settings and geometry remain separately identified. Any selected ray that misses or is ambiguous remains `UNKNOWN` and fails the local probe gate. These sampled distances do not prove a global minimum normal thickness.

The optional STEP function is separate from native construction. It exports/reimports the solid and records counts, validity, volume, and bounding-box deltas. It is behind an explicit CLI flag and must not be called before review. A failed STEP round trip leaves the native evidence separately reviewable and does not turn into a promoted asset.

Both report and image output must say `ANALYTIC_CANDIDATE_ONLY`, `real_vessel_match=NOT_VALIDATED`, `material_or_physical_qualification=NOT_VALIDATED`, and `global_minimum_normal_wall_thickness=UNKNOWN`. The 3D render uses a tessellation of the native solid; the section panel uses the actual planar face created by intersecting that solid with a half-space box.

## Standard methods and candidate contribution

Quintic Hermite/Bernstein construction, C2 derivative constraints, explicit closed-section revolution, native B-rep validity checks, curvature sampling, OCC all-hit ray queries, and STEP round-trip checks are established methods. The candidate contribution is their traceable combination for fixed profiles: locally editable paired walls with clearly named radial-only provenance; a directly closed, rounded material section that bypasses the prior offset path; and a per-candidate record that keeps local measurements separate from unknown global thickness and real-vessel/physical claims. No novelty, real-vessel resemblance, material qualification, or physical performance is asserted.

## Review and ownership

- Main agent reviews the source, fixed station parameters, all-hit checker, STEP flag, and output plan before any fixture runs.
- This experiment directory owns the source and case data only. Production `src/`, existing tests, other experiment files, and Git state stay out of scope.
- After review, run only the two fixed cases on the tiny local runtime. Inspect both images and reports before deciding whether another bounded revision is warranted.
- RelicWeave integration consumes a versioned analytic candidate record with evidence and refusal reasons; it must preserve the geometry-only status and must not label the profile a real vessel or a physically qualified asset.

The exact inputs and post-review command/check sequence are in `fixed_cases.json` and `LOCAL_FIXTURE_CHECK_PLAN.md`. The artifacts have frozen SHA-256 values in `../../tmp/review_20261004/smooth_surface_route/FROZEN_SHA256.txt`.

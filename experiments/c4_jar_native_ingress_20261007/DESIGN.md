# C4 jar native B-rep ingress design

Status: source-only proposal for root review. No CadQuery/OCP imports, constructors, CAD calls, exports, or tests were run for this task. Native execution remains disabled until root selects the route and grants a one-run GO.

## Pinned evidence and scope

- The outer jar candidate is `GEOMETRY_ENGINEERING_CANDIDATE_ONLY`; its saved result pins 17 rational RZ poles, a degree-5 curve with 12 spans, 11 exact C4 joins, and five declared features. The saved independent audit is a separate evidence file.
- The 3 mm inner-curve certificate reports `INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE` for all 12 spans. It uses the true inward normal formula and proves the local curvature factor is at least 2/3 on the side and 1 on the straight base and neck.
- The later strip result reports `GLOBAL_MERIDIAN_STRIP_INJECTIVITY_PROVED_CONDITIONAL` only for the 2D meridian map over all 12 spans and `0 <= s <= 3 mm`. Its endpoint fibers include `(0,0)->(0,3)`, `(18,0)->(18,3)`, and `(26,120)->(23,120)`.
- That strip result still marks `global_minimum_euclidean_wall`, `native_brep`, and `physics` as `UNKNOWN`. It does not establish 3D revolved-surface self-intersection freedom, a CAD lip, or a closed solid. The 25-per-span normal-offset samples are display data, not CAD control geometry.

## Proposed one-shot construction

1. Read only the pinned outer result and independent audit. Verify hashes, candidate status, 17 poles, degree 5, 12 spans, all 11 C4 joins, and the named flat-base / side / straight-neck span map before creating geometry.
2. Construct the outer meridian directly from the 17 saved control poles and the pinned open-uniform knot sequence: degree 5, endpoint multiplicity 6, eleven simple internal knots at `j/12`. Convert the exact saved rational coordinates to finite millimetre doubles only at the OCP point boundary. Build one `Geom_BSplineCurve` edge in the global XZ plane. Do not fit, interpolate, or build CAD from the 300 display stations.
3. Make one open planar wire from that edge and call the existing OCC `BRepOffsetAPI_MakeOffset` path with an open result and arc join mode at the root-frozen signed 3 mm distance. The sign must encode the certified inward normal: `(-z'/v, r'/v)` in `(r,z)`. The resulting OCC wire is the inner CAD contour; do not replace it with a sampled spline. Require one valid open wire and the expected endpoints `(0,3)` and `(23,120)` within a separately approved endpoint tolerance. A reversed result, extra wire, self-intersection, or endpoint miss is a preserved failure; there is no sign-flip or route retry.
4. Close one material section in this order: exact outer contour from axis base to mouth; straight radial lip from `(26,120)` to `(23,120)`; reversed OCC offset contour back to `(0,3)`; axis segment back to `(0,0)`. Assemble without tolerance-based endpoint snapping. Require one valid closed wire and one finite positive-area face.
5. Revolve the section once through 360 degrees about global `+Z`. The outer flat-base span becomes the external bottom plane, the side spans form the outer wall, the straight-neck span forms the outer cylinder; corresponding inner spans form the inner floor/wall/neck, and the mouth connector forms the annular lip. The axis closure is a degenerate revolution boundary, not a material face; explicitly check that it creates no invalid zero-area face or open shell.
6. Require one valid solid, one closed shell, finite positive surface area and volume, and valid faces/edges. Record the B-rep geometry-only bounds and face inventory before export. Export one STEP in millimetres and import it once; require the same solid/shell counts, closed shell, finite positive area/volume, matching bounds, and a one-to-one face inventory. A topology repair or healing operation is outside this pilot.

## Checks and tolerance meanings

- `1e-7 mm` is the existing VF geometry-only STEP identity tolerance for bounds/face inventory. It is not the inner wall thickness, an offset-fit tolerance, a wire snap tolerance, or a global minimum-wall claim. Existing face inventory comparison is order-sensitive; if STEP reorders or splits faces, report identity `UNKNOWN` unless root approves a role-based matcher.
- Root must freeze separate limits for offset target distance, endpoint closure, normal-angle deviation, and STEP area/volume deltas. The CadQuery `Wire.offset2D` source wrapper exposes offset distance and join type but no approximation-tolerance argument; the kernel default must not be described as the approved tolerance.
- For each of the 12 source spans, evaluate independent deterministic stations on the exact outer curve and the mathematical target `C_3(u)=(r-3 z'/v, z+3 r'/v)`. Project target points onto the finite trimmed native outer/inner edges, and project native edge stations back to the exact target. Report maximum bidirectional distance, witness span/parameter/coordinates, projection multiplicity, and coverage. Compare normalized tangents (equivalently planar normals) at the same projected stations and report maximum angular deviation. Include knot endpoints and refine where residual/angle changes; cap station work and return `UNKNOWN` if convergence, unique correspondence, or coverage fails. These are sampled diagnostics, not a global Hausdorff proof.
- Keep semantic roles tied to source span ranges and generating edges: outer base / side / neck, inner base / side / neck, and lip. After STEP, classify by surface geometry plus source-correspondence samples; never assign semantic labels by face index alone. If STEP strips lineage or cannot be matched uniquely, preserve the geometry result and mark labels `UNKNOWN`.
- Report the requested normal offset as 3 mm and the offset-target residual separately. Keep global minimum Euclidean wall thickness `UNKNOWN` until a dedicated clearance check covers the complete closed B-rep, including base, lip, and axis closure. Neither the local normal certificate nor the 2D strip proof establishes that 3D minimum.

## Bounded run contract for a later root GO

One native solid build, one STEP export, one STEP import; 60 seconds wall time and 20 MiB total persisted output including STEP, result/receipt, and raw logs. No retry, optimizer, mesh, solver, normal-ray study, or production change. Persist source/input before-and-after hashes, exact argv/return code/elapsed time, the exact poles/knots, topology counts, area/volume/bounds, face-role map, station counts, distance/angle maxima and witnesses, and every failed/unknown gate. A cap or validator failure is retained without increasing budgets.

## Root decisions required before implementation

1. Confirm the `BRepOffsetAPI_MakeOffset` open-wire route and the signed call (`+3` or `-3` mm) from the pinned section orientation. If it fails, decide whether a separately reviewed `Geom_OffsetCurve` route is allowed; no automatic fallback.
2. Set numeric limits for offset residual, endpoint closure, normal angle, and STEP area/volume deltas. Keep each distinct from the fixed `1e-7 mm` identity policy.
3. Choose semantic face naming: sidecar role map with geometric re-identification, or an AP242/XCAF named STEP path. The existing shape-only exporter does not establish persisted face names.
4. Confirm the axis-degenerate edge is accepted only when OCC returns one valid closed solid, and decide whether global minimum Euclidean wall must remain an explicit blocker for any later CAD candidate claim.
5. Confirm the one-run 60-second / 20-MiB output contract.

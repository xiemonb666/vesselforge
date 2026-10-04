# Draft: local error-controlled tessellation for the analytic relief fixture

**Status:** Plan for a later owner-authorized comparison; not implemented or run. No changes to the frozen prototype, run01, run02, production modules, or generated evidence are part of this draft.

## Fixed analytic source shared by both candidates

Use the same `R = 20 mm`, `wall = 3 mm`, `height = 24 mm`, `floor = 2 mm` cylinder and the same immutable parent surface. Keep eight motifs, center height `z = 13 mm`, circumferential half-width `2.7 mm`, vertical half-height `2.1 mm`, raised amplitude `0.45 mm`, and the exact base/pigment linear-RGB inputs and standard sRGB transfer already frozen in run02. The field, source/material inputs, and continuous rest-coordinate surface stay identical; only the local tessellation density changes.

For the cylinder, parameterize the reference exterior as

`X0(theta,z) = (R cos(theta), R sin(theta), z)`

with local chart `u = R * wrapped_delta_theta`, `v = delta_z` and the corresponding constant-radius metric. Evaluate the same continuous motif function `h(theta,z)` on this chart, and use `X1(theta,z) = X0(theta,z) + h(theta,z) * e_r(theta)` as the analytic displaced reference. This metric is exact for the fixture's constant radius only. It is not a global chart for a vessel with a changing-radius profile.

Keep baseline vertex IDs and coordinates stable. For inserted samples, retain the same `parent_surface_id`, wrapped `(theta,z)` rest coordinate, and source-triangle/barycentric lineage to the coarse baseline where applicable. Evaluate rest points on the same analytic cylinder and sample color and height from the same continuous functions. New density candidates are precision representations of this one parent/field, never additional independent samples or fracture GT.

## Two local density candidates to compare

Keep archived run02 (`128 x 25`, nominal `0.982 mm` circumferential and `1.000 mm` vertical chart pitches) as the coarse baseline. Compare two proposed maximum metric edge lengths on the ornament-support patches:

| Candidate | Proposed maximum chart edge in the ornament support and transition band | Nominal ratio to `0.45 mm` height |
| --- | ---: | ---: |
| Local A | `0.50 mm` | `1.11` |
| Local B | `0.25 mm` | `0.56` |

These are candidate targets, not results or accepted production settings. The continuous ellipse/smoothstep support is local to each motif; add only the transition band needed for a conforming mesh and preserve the coarser mesh outside it. Repeat one identical sector pattern eight times. The motif centered at the angular seam must be refined symmetrically across both seam sides, with one periodic seam topology and no duplicate seam vertices. Use a conforming transition (no T-junctions); do not globally densify the whole vessel merely to hide local error. Sample the unchanged analytic field at all new vertices—do not smooth, widen, or otherwise alter the pattern.

The original inner wall, floor, lip, and unaffected exterior stay on the same source geometry. Preserve the run02 closure/winding/incidence checks after refinement. A failure at either density is evidence to report, not permission to relax a gate or silently refine again.

## Geometry error check against the continuous field

For every outer relief triangle in each candidate, evaluate the triangle barycenter and all three edge midpoints. Convert each barycentric sample to `(theta,z)` by locally unwrapping its triangle's angular coordinates around a vertex before interpolation; wrap the result back to the periodic domain for field evaluation. This avoids interpolating across a false `2*pi` jump at the seam.

At each query, compare the point on the saved piecewise-linear triangle,
`Xtri = sum_i(w_i * X1_i)`, with the exact continuous point `X1(theta_q,z_q)`. Record sample count and RMS, p95, p99, and maximum Euclidean error in millimeters, plus the maximum separately for barycenters and edge midpoints. The proposed geometry acceptance target is `max_sampled_error <= 0.02 mm` for this analytic fixture.

This is a finite set of interior probes, not a certified supremum, Hausdorff-distance bound, or proof of maximum error everywhere. It says nothing about self-intersection, general offset validity, a curved parent, material behavior, or physical fidelity. Keep the threshold labeled as a proposed fixture-mapping tolerance, not an archaeological or manufacturing tolerance.

## Normal and resolution metrics

At the same edge-midpoint and barycenter queries, compare each oriented displaced-triangle normal with the analytic normal of the radial-graph surface. With `e_r = (cos(theta),sin(theta),0)` and `e_theta = (-sin(theta),cos(theta),0)`, the continuous reference normal is proportional to

`e_r - (h_theta / (R+h)) * e_theta - h_z * e_z`.

Normalize both directions and record the sampled angle error in degrees (RMS, p95, maximum; split by barycenter and edge midpoint). This is a report metric in this draft; no angle gate is imposed until the owner chooses one. Evaluate derivatives from the analytic field or a verified derivative implementation, including the zero-gradient center and support-boundary cases.

For each candidate, measure the maximum actual 3D edge length over displaced outer triangles and divide by the fixed `0.45 mm` amplitude. Also record the maximum chart-metric edge length divided by the amplitude. Keep the nominal baseline pitch ratios above separate from these measured mesh values; do not infer the latter from the nominal grid. These ratios diagnose whether the relief is represented by edges materially coarser than its amplitude but are not by themselves an error bound.

## Invariants, scope, and decision rule

- Verify exact source/prototype/parameter hashes, unchanged continuous motif/material inputs, immutable rest lineage, seam periodicity, and the run02 topology checks for each candidate.
- Verify linear-RGB samples come from the same field and sRGB values use the same transfer. Material/PBR and device calibration remain `UNKNOWN`; a render is still a mapping preview.
- Keep the radial-wall value explicitly labeled as an analytic-cylinder proxy. Do not present it as the minimum distance between the complete outer and inner triangulated surfaces. No global wall, collision, or self-intersection result is part of this draft.
- Report each tessellation as a resolution variant of one analytic sample. Do not use them as independent data, fracture GT, R2, or training examples.
- If at least one candidate meets the `0.02 mm` sampled geometry target, present both error summaries and costs for owner review; select the coarsest passing representation only after that review. If neither passes, stop with both measured failures and wait for the owner. Do not automatically escalate density or rerun.
- A later authorized run should save arrays, per-candidate parameter/source hashes, exact argv/stdout/stderr/exit, error summaries, and a flat-triangle visual review from those saved arrays. Do not use a smoothing shader to conceal faceting.

No density comparison, new mesh, Python run, CAD operation, solver operation, production change, training-data change, or Git operation has been made for this draft.

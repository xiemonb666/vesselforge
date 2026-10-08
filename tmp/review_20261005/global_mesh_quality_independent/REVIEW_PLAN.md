# Independent review plan: global mesh quality candidate

Status: `WAITING_FOR_AUTHOR_FREEZE`. No candidate files have been opened and no generation, refinement, CAD, or quality computation has been run for the new candidate.

## Input freeze scope

Before review, the author must freeze one exact artifact set under `vesselforge/experiments/global_mesh_quality_candidate_20261005/`. Review begins only after a manifest or equivalent states the candidate case IDs and SHA-256 hashes for the saved candidate NPZs, checks/receipt, source/config, and any analytic field parameters needed to reproduce geometry and color samples. I will hash those exact files first, compare each hash to the freeze record, and save the verified input manifest and receipt in this directory. If any hash differs, I will stop and wait for a corrected freeze.

The frozen comparison inputs are:

| Input | SHA-256 |
|---|---|
| Baseline fixture `vesselforge/tmp/review_20261004/surface_ornament_route/run02/fixture_arrays.npz` | `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974` |
| Existing A candidate arrays | `ac3c7da3dda89ab2e6d26b997a05d4d693384626f44e0d5154c061824d2e87e6` |
| Existing B candidate arrays | `8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf` |
| Existing refinement prototype | `5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74` |

The previous independent measurements are the comparison baseline, not acceptance criteria: A full-mesh minimum Q `0.084885`, maximum aspect `20.3800` in the planar floor fan; B full-mesh minimum Q `0.084885`, maximum aspect `20.3800` in the same fan; B outer body maximum aspect `8.00137`. B support/transition minimum Q was `0.840856` and `0.857729`, respectively. The 20 mm radial fan is a geometric shape measurement, not a fracture-mechanics `h` value.

## Independent calculations after freeze

1. **Whole-mesh triangle shape.** For every face in each candidate, compute displaced-XYZ triangle area, side lengths, `Q = 4*sqrt(3)*A/sum(l_i^2)`, minimum altitude `2*A/l_max`, and aspect ratio `l_max/min_altitude`. Report full-mesh extrema and the same extrema by `body`, `support`, `transition`, `inner`, and `base`, with counts, candidate face index, source face ID, candidate vertex IDs, vertex coordinates, three edge lengths, area, altitude, Q, and aspect. Use the same group definitions for old and new candidates: outer `body` has all three saved relief heights equal to zero; `support` has all three strictly positive; `transition` has a mix of zero and positive; `inner` has a baseline source face whose three vertices are all in `inner_side_vertex_indices`; `base` is the remaining source-face set. These groups must partition all faces exactly.

2. **Cylinder chart shape.** For outer and inner cylindrical groups, independently unwrap each face's three angles around its first vertex, use the shortest periodic angular differences, and compute intrinsic chart edges from `sqrt((R*delta_theta)^2 + delta_z^2)`. Report full outer/inner chart extrema by the same region groups. This prevents a seam branch or 3D chord from being mistaken for an intrinsic cylinder edge. Base and floor faces use their planar XYZ geometry.

3. **Topology and orientation.** From candidate faces, independently count unique undirected edges, boundary and non-two-incidence edges, directed winding conflicts, duplicate unoriented faces, repeated-index faces, zero-area faces, and connected components. Recompute `V-E+F`, signed volume from displaced XYZ, and positive orientation. Compare to the frozen check file. Expected closed-shell results are one component, no boundary/non-two-incidence/winding conflicts, Euler characteristic 2, and positive volume; any departure is reported directly.

4. **Lineage and boundary identity.** Verify `source_face_ids` range against the frozen baseline faces; verify every face-corner barycentric row and each new-vertex lineage row is finite, within the simplex, and sums to one. Reconstruct every child face corner and every new vertex from the recorded baseline source face and barycentrics. For outer/inner cylindrical parents, interpolate in a locally unwrapped `(theta,z)` chart and compare modulo `2*pi` with radius-scaled angular residual; do not use straight 3D barycentric interpolation for cylinder reprojection. Reconstruct planar base/rim points in rest XYZ. Report per-surface residual counts, RMS, p95/p99/max, and source/target IDs. Check all original baseline rest and relief vertices are `array_equal` in the candidate prefix. Verify seam coordinates do not create duplicate physical vertices at the periodic join, and record z/radius identity for the cap, floor, inner wall, and outer wall interfaces.

5. **Color preservation and residuals.** Check frozen `outer_base_linear_rgb` and `outer_base_srgb` against baseline with `array_equal`. Map expanded `outer_color_*` values back to original vertex IDs, report exact-row counts and maximum absolute channel differences, and compare linear residuals to the prototype's `BASELINE_COLOR_TOL=1e-12` without calling tolerance-level equality bitwise equality. If the frozen candidate includes the exact analytic field/configuration needed to evaluate new-vertex colors, independently evaluate it from the frozen parameters and report residuals for every saved outer sample; otherwise mark new-sample color residual `UNKNOWN`. Check `linear_rgb_to_srgb` consistency and report its maximum residual.

6. **Geometry error.** Independently verify every candidate vertex against the frozen analytic rest/displaced surface and evaluate the saved field at every required candidate outer sample when the frozen field definition is available. Recompute the same finite face probes at barycenters and edge midpoints only if their exact construction is documented in the freeze; report count and p95/p99/max. Label finite probe results as sampled errors, never a global supremum or Hausdorff guarantee. If the frozen field oracle or construction cannot be reproduced independently, retain analytic geometry residual as `UNKNOWN`; do not reuse the earlier recorded finite maxima as independent evidence.

7. **Global comparison.** Compare the new candidate with both frozen A and B using identical formulas, unit conventions, classification, and complete face sets. Report whether any claimed global or body/fan improvement introduces regressions in support/transition, inner, or base groups, as well as changes in topology, volume, colors, lineage residual, and original boundary identity. A ROI-only comparison is insufficient.

## Decision boundary

This review can establish data integrity, discretization shape, closed-shell topology, recorded lineage reconstruction, sampled analytic geometry residuals, and color-array preservation against the synthetic fixture. It cannot establish physical material qualification, mechanics, fracture classification, a real fragment match, or real-vessel fidelity. No Q, altitude, aspect, or sampled geometry threshold is available here beyond the frozen prototype tolerances; report measurements and gate comparisons without inventing a physical pass threshold.

## Awaiting freeze

No computation for the new candidate will start until its author-provided file/hash manifest is present and stable. All review writes remain in `vesselforge/tmp/review_20261005/global_mesh_quality_independent/`.

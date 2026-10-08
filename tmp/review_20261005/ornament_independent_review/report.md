# Independent ornament candidate review

This is a read-only audit of the saved run and its analytic cylinder fixture. I independently read the two NPZ files, recomputed topology and outer triangle metrics, inspected both original PNGs, and made one unlit review visualization. No candidate or production source was changed.

The saved run receipt says `PASS_ALL_CANDIDATES`, exit code 0, for `local_a_0p50mm, local_b_0p25mm`. It records source SHA-256 `5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74`, baseline fixture arrays SHA-256 `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974`, and case freeze SHA-256 `ab89a0832366d0391b9539248cfbfab62e7ea770f3cf9b1499ee6b39b0b533c1`. This is a candidate gate result for an analytic sample-resolution experiment; it does not establish material fidelity or a real fragment match.

For triangle quality, Q is `4√3 A / Σ(edge²)`, so an equilateral triangle has Q=1. Aspect is longest edge divided by shortest altitude, so an equilateral triangle is about 1.155. The relative edge measure divides the longest support/transition edge by the saved global peak relief H=0.45 mm. These are descriptive measurements; the saved checks define no minimum Q or maximum aspect acceptance limits.

## Candidate measurements

### local_a_0p50mm

Candidate SHA-256: `ac3c7da3dda89ab2e6d26b997a05d4d693384626f44e0d5154c061824d2e87e6`. The NPZ exposes 25 arrays; all floating arrays are finite and all listed shapes/dtypes are archived in `independent_metrics.json`.

Topology recomputed from relief vertices: 9,490 vertices, 18,976 faces, 28,464 unique edges; 0 boundary edges, 0 non-two-incidence edges, 0 winding conflicts, 1 component, Euler characteristic 2. Signed volume is 10202.014179 mm³ and positive. Independent values match the recorded topology checks.

For outer support and transition faces (classified here as a face touching a vertex with positive saved relief), the maximum chart edge is 0.500000 mm (1.111× the 0.450 mm peak relief); the displaced 3D chord maximum is 0.522549 mm (1.161×). The worst displaced triangle has Q=0.842, aspect 2.111, source face 3006; its chart edges are 0.350342, 0.350342, 0.500000 mm and its saved vertex reliefs are 0.241059, 0.157015, 0.089213 mm.

The candidate has 49,280 finite geometry probes: I independently confirmed the saved arrays are finite and the count equals four probes per outer face. The maximum error 0.014577 mm against a 0.020 mm sample gate and maximum normal angle 5.826° are the values recorded in `checks.json`; I could not independently recompute those reference residuals from the candidate NPZ alone because the baseline reference arrays are not included. The normal angle has no owner acceptance limit. The probe set is barycenters plus edge midpoints, not a global bound.

Lineage arrays pass independent shape, finiteness, source-ID range, and barycentric-simplex checks (maximum sum error 0.0e+00 for face corners; 0.0e+00 for new vertices). The saved run check reports chart reconstruction residual 1.776e-14 mm, but source baseline face connectivity is absent from the candidate NPZ, so I could not independently repeat its geometric source-triangle reconstruction.

| NPZ field | Shape | dtype | finite |
|---|---:|---|---|
| `vertices_rest_xyz_mm` | `[9490, 3]` | `float64` | yes |
| `vertices_relief_xyz_mm` | `[9490, 3]` | `float64` | yes |
| `faces` | `[18976, 3]` | `int64` | yes |
| `outer_vertex_indices` | `[6288]` | `int64` | yes |
| `outer_theta_rad` | `[6288]` | `float64` | yes |
| `outer_z_mm` | `[6288]` | `float64` | yes |
| `outer_color_linear_rgb` | `[6288, 3]` | `float64` | yes |
| `outer_color_srgb_for_display` | `[6288, 3]` | `float64` | yes |
| `outer_relief_height_mm` | `[6288]` | `float64` | yes |
| `outer_normals_analytic_displaced` | `[6288, 3]` | `float64` | yes |
| `outer_source_face_ids` | `[6144]` | `int64` | yes |
| `source_face_ids` | `[18976]` | `int64` | yes |
| `face_corner_barycentric_to_source` | `[18976, 3, 3]` | `float64` | yes |
| `vertex_lineage_source_face_id` | `[9490]` | `int64` | yes |
| `vertex_lineage_barycentric` | `[9490, 3]` | `float64` | yes |
| `outer_base_linear_rgb` | `[3200, 3]` | `float64` | yes |
| `outer_base_srgb` | `[3200, 3]` | `float64` | yes |
| `baseline_fixture_arrays_sha256` | `[]` | `<U64` | yes |
| `refinement_source_sha256` | `[]` | `<U64` | yes |
| `case_freeze_sha256` | `[]` | `<U64` | yes |
| `outer_radius_mm` | `[]` | `float64` | yes |
| `original_vertex_count` | `[]` | `int64` | yes |
| `original_face_count` | `[]` | `int64` | yes |
| `refinement_rounds` | `[]` | `int64` | yes |
| `target_edge_mm` | `[]` | `float64` | yes |

### local_b_0p25mm

Candidate SHA-256: `8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf`. The NPZ exposes 25 arrays; all floating arrays are finite and all listed shapes/dtypes are archived in `independent_metrics.json`.

Topology recomputed from relief vertices: 18,546 vertices, 37,088 faces, 55,632 unique edges; 0 boundary edges, 0 non-two-incidence edges, 0 winding conflicts, 1 component, Euler characteristic 2. Signed volume is 10202.175146 mm³ and positive. Independent values match the recorded topology checks.

For outer support and transition faces (classified here as a face touching a vertex with positive saved relief), the maximum chart edge is 0.250000 mm (0.556× the 0.450 mm peak relief); the displaced 3D chord maximum is 0.262357 mm (0.583×). The worst displaced triangle has Q=0.841, aspect 2.117, source face 3038; its chart edges are 0.175171, 0.175171, 0.250000 mm and its saved vertex reliefs are 0.241059, 0.199642, 0.161492 mm.

The candidate has 121,728 finite geometry probes: I independently confirmed the saved arrays are finite and the count equals four probes per outer face. The maximum error 0.006024 mm against a 0.020 mm sample gate and maximum normal angle 3.277° are the values recorded in `checks.json`; I could not independently recompute those reference residuals from the candidate NPZ alone because the baseline reference arrays are not included. The normal angle has no owner acceptance limit. The probe set is barycenters plus edge midpoints, not a global bound.

Lineage arrays pass independent shape, finiteness, source-ID range, and barycentric-simplex checks (maximum sum error 0.0e+00 for face corners; 0.0e+00 for new vertices). The saved run check reports chart reconstruction residual 1.776e-14 mm, but source baseline face connectivity is absent from the candidate NPZ, so I could not independently repeat its geometric source-triangle reconstruction.

| NPZ field | Shape | dtype | finite |
|---|---:|---|---|
| `vertices_rest_xyz_mm` | `[18546, 3]` | `float64` | yes |
| `vertices_relief_xyz_mm` | `[18546, 3]` | `float64` | yes |
| `faces` | `[37088, 3]` | `int64` | yes |
| `outer_vertex_indices` | `[15344]` | `int64` | yes |
| `outer_theta_rad` | `[15344]` | `float64` | yes |
| `outer_z_mm` | `[15344]` | `float64` | yes |
| `outer_color_linear_rgb` | `[15344, 3]` | `float64` | yes |
| `outer_color_srgb_for_display` | `[15344, 3]` | `float64` | yes |
| `outer_relief_height_mm` | `[15344]` | `float64` | yes |
| `outer_normals_analytic_displaced` | `[15344, 3]` | `float64` | yes |
| `outer_source_face_ids` | `[6144]` | `int64` | yes |
| `source_face_ids` | `[37088]` | `int64` | yes |
| `face_corner_barycentric_to_source` | `[37088, 3, 3]` | `float64` | yes |
| `vertex_lineage_source_face_id` | `[18546]` | `int64` | yes |
| `vertex_lineage_barycentric` | `[18546, 3]` | `float64` | yes |
| `outer_base_linear_rgb` | `[3200, 3]` | `float64` | yes |
| `outer_base_srgb` | `[3200, 3]` | `float64` | yes |
| `baseline_fixture_arrays_sha256` | `[]` | `<U64` | yes |
| `refinement_source_sha256` | `[]` | `<U64` | yes |
| `case_freeze_sha256` | `[]` | `<U64` | yes |
| `outer_radius_mm` | `[]` | `float64` | yes |
| `original_vertex_count` | `[]` | `int64` | yes |
| `original_face_count` | `[]` | `int64` | yes |
| `refinement_rounds` | `[]` | `int64` | yes |
| `target_edge_mm` | `[]` | `float64` | yes |

## Visual inspection and limits

Both original `flat_triangle_visual.png` files place the analytic cylinder fixture beside saved flat triangles. The x-axis tick labels crowd together at the lower-right of each mesh panel. The displaced surface shows repeated shallow oval marks, and the flat view has a fan or spike-shaped support transition around the motif. These images show the saved analytic sample and its triangulation; they do not demonstrate a measured fragment, a calibrated material, a physically validated relief, or a vessel match.

The new `independent_relief_review.png` shows a piecewise-linear section at the relief peak, the 0.25 mm candidate relief mesh with height-coded flat face colors and no lighting, and an equal-scale chart view of its worst displaced transition triangle with its three vertex heights. All plotted lengths use millimeters. The local cylinder chart uses arc length `R·Δθ` and z; the 3D relief patch uses that chart plus saved relief height. This makes relief and triangle shape inspectable without a material shader, while the mesh remains only a synthetic cylinder sample.

The finite geometry gate is finite sampling only: the checks explicitly describe barycenter and edge-midpoint probes, with no certified supremum or global Hausdorff bound. The check files also mark independent sample/ground truth `NO`, physical/material qualification `NOT_VALIDATED`, physics `UNKNOWN`, real-vessel match `NOT_VALIDATED`, global minimum normal wall thickness `UNKNOWN`, self-intersection/general offset validity `NOT_ASSESSED`, and fracture labels `NONE`. Treat `PASS_ALL_CANDIDATES` as “these recorded gates passed,” not as evidence that the candidate meets RelicWeave’s real-fragment objective.

The exact receipt and check files, input SHA-256 manifest, complete independent metrics, original PNG copies, review PNG, and analysis script are saved alongside this report.

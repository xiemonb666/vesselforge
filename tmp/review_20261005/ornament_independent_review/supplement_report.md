# Ornament lineage and whole-mesh quality supplement

Frozen baseline SHA-256 was verified before opening its NPZ: `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974`. This equals the authorized hash `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974`.

This supplement reads the frozen baseline fixture, the saved candidate NPZs, and their recorded checks. It uses NumPy calculations only. It does not run the refinement generator or CAD and does not modify production or candidate artifacts.

## Lineage reconstruction method

For every candidate face corner, the stored `source_face_ids` selects a baseline triangle and the corresponding row in `face_corner_barycentric_to_source` supplies its barycentric weights. New vertices use `vertex_lineage_source_face_id` and `vertex_lineage_barycentric` the same way. Outer and inner cylinder residuals are computed in each baseline triangle’s locally unwrapped cylindrical chart: unwrap its three source angles around corner zero, interpolate `(theta,z)` with the barycentric weights, compare the candidate angle using the shortest periodic delta, and convert angular residual to millimeters using the appropriate radius. This avoids treating a curved cylinder point as a straight 3D chord interpolation. Remaining planar base/rim faces are reconstructed in rest XYZ.

## Preservation and lineage results

### local_a_0p50mm

Original baseline rest and relief vertices are array-equal: `True` / `True`; original outer relief heights are array-equal by vertex ID: `True`. The frozen `outer_base_linear_rgb` and `outer_base_srgb` arrays are bitwise equal to baseline: `True` / `True`. Expanded `outer_color_*` samples mapped to the original outer vertex IDs are NON_BITWISE_EQUAL: maximum absolute differences are 1.110e-16 linear RGB and 1.110e-16 sRGB; 3128/3200 linear rows and 3160/3200 sRGB rows are bitwise exact. The recorded linear difference 1.110e-16 is within the prototype's `BASELINE_COLOR_TOL=1e-12`, and its field/color gate is `True`. This supports tolerance-level numerical preservation, not byte-for-byte equality of expanded field samples.

Face-corner lineage reconstructed 56,928/56,928 corners; all reconstructed: `True`. Maximum residuals by source type: outer 1.776e-14 mm (n=36,960); inner 0.000e+00 mm (n=18,432); base 0.000e+00 mm (n=1,536).

New vertex lineage reconstructed 3,088/3,088 vertices; all reconstructed: `True`. Maximum residuals by source type: outer 1.776e-14 mm (n=3,088); inner none (n=0); base none (n=0).

Source IDs, outer parent-face set, face-corner barycentric simplices, and new-vertex barycentric simplices all pass: `True`, `True`, `True`, `True`.

The full-mesh minimum 3D Q and maximum aspect both occur in the planar base fan, source face 12372: edges 20.000000, 0.981649, 20.000000 mm, Q=0.0849, minimum altitude=0.981353 mm, aspect=20.3800. This is the radial floor fan from the center vertex to adjacent rim vertices. The full-mesh minimum altitude instead occurs in source face 2778 at 0.245435 mm. Relief support/transition minimum Qs are 0.8420/0.8566, while the unornamented outer body reaches maximum aspect 4.0007.

| region | triangles | min Q | min altitude (mm) | max aspect | Q source | altitude source | aspect source |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 18,976 | 0.0849 | 0.245435 | 20.3800 | 12372 | 2778 | 12372 |
| body | 9,696 | 0.4935 | 0.245435 | 4.0007 | 2523 | 2778 | 2362 |
| support | 1,888 | 0.8420 | 0.245982 | 2.1111 | 3006 | 3040 | 3006 |
| transition | 736 | 0.8566 | 0.245440 | 2.0434 | 3007 | 2785 | 3007 |
| inner | 6,144 | 0.8622 | 0.617049 | 2.0088 | 6370 | 10210 | 6370 |
| base | 512 | 0.0849 | 0.798601 | 20.3800 | 12372 | 12743 | 12372 |

Cylinder groups also have intrinsic chart metrics in `supplement_metrics.json`; 3D values above measure saved relief-mesh chords. Neither metric measures fracture mechanics or validates a physical `h`.

### local_b_0p25mm

Original baseline rest and relief vertices are array-equal: `True` / `True`; original outer relief heights are array-equal by vertex ID: `True`. The frozen `outer_base_linear_rgb` and `outer_base_srgb` arrays are bitwise equal to baseline: `True` / `True`. Expanded `outer_color_*` samples mapped to the original outer vertex IDs are NON_BITWISE_EQUAL: maximum absolute differences are 1.110e-16 linear RGB and 1.110e-16 sRGB; 3128/3200 linear rows and 3160/3200 sRGB rows are bitwise exact. The recorded linear difference 1.110e-16 is within the prototype's `BASELINE_COLOR_TOL=1e-12`, and its field/color gate is `True`. This supports tolerance-level numerical preservation, not byte-for-byte equality of expanded field samples.

Face-corner lineage reconstructed 111,264/111,264 corners; all reconstructed: `True`. Maximum residuals by source type: outer 1.776e-14 mm (n=91,296); inner 0.000e+00 mm (n=18,432); base 0.000e+00 mm (n=1,536).

New vertex lineage reconstructed 12,144/12,144 vertices; all reconstructed: `True`. Maximum residuals by source type: outer 1.776e-14 mm (n=12,144); inner none (n=0); base none (n=0).

Source IDs, outer parent-face set, face-corner barycentric simplices, and new-vertex barycentric simplices all pass: `True`, `True`, `True`, `True`.

The full-mesh minimum 3D Q and maximum aspect both occur in the planar base fan, source face 12372: edges 20.000000, 0.981649, 20.000000 mm, Q=0.0849, minimum altitude=0.981353 mm, aspect=20.3800. This is the radial floor fan from the center vertex to adjacent rim vertices. The full-mesh minimum altitude instead occurs in source face 2778 at 0.122718 mm. Relief support/transition minimum Qs are 0.8409/0.8577, while the unornamented outer body reaches maximum aspect 8.0014.

| region | triangles | min Q | min altitude (mm) | max aspect | Q source | altitude source | aspect source |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 37,088 | 0.0849 | 0.122718 | 20.3800 | 12372 | 2778 | 12372 |
| body | 20,384 | 0.2385 | 0.122718 | 8.0014 | 3752 | 2778 | 2934 |
| support | 8,544 | 0.8409 | 0.122757 | 2.1165 | 3038 | 3258 | 3038 |
| transition | 1,504 | 0.8577 | 0.122718 | 2.0383 | 3039 | 3291 | 3039 |
| inner | 6,144 | 0.8622 | 0.617049 | 2.0088 | 6370 | 10210 | 6370 |
| base | 512 | 0.0849 | 0.798601 | 20.3800 | 12372 | 12743 | 12372 |

Cylinder groups also have intrinsic chart metrics in `supplement_metrics.json`; 3D values above measure saved relief-mesh chords. Neither metric measures fracture mechanics or validates a physical `h`.

## Interpretation and limits

The fan-like view alone did not establish triangle severity. The full-mesh metrics now show that minimum Q=0.0849 and maximum aspect=20.38 are in a planar base radial fan triangle with 20 mm radial edges, a 0.982 mm rim chord, and 0.981 mm minimum altitude. It is high-aspect, but not zero-area; without an owner threshold it cannot be called a pass/fail defect. Relief support and transition triangles have minimum Q about 0.841 and maximum aspect about 2.117 in these runs. The finer candidate’s unornamented outer body reaches aspect about 8.0. These are triangle-shape descriptors; a 20 mm fan chord or triangle quality is not a mechanical relief height `h` or a fracture criterion.

The recorded finite geometry probe errors remain recorded checks, not independently reproduced analytic-field residuals in this supplement. Reconstructing the saved mesh lineage against the baseline does not by itself reproduce the prototype’s analytic field sampling or certify a global geometry error. Those analytic residuals remain unknown here. The 20 mm radius cylinder and its chord triangle metrics are a synthetic fixture; they do not establish mechanics, material response, real-fragment correspondence, or calibrated relief.

See `supplement_metrics.json` for full residual distributions, worst-face vertex IDs and edge lengths, chart metrics by region, and the baseline schema. Input hashes and a completion receipt are saved alongside this report.

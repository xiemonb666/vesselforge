# Apsida reference mesh variation — corrected run02

This run uses the unchanged full raw indexed mesh at
[`../scanned_anchor_audit/raw_geometry.npz`](../scanned_anchor_audit/raw_geometry.npz).
The reusable deformer keeps the source vertex order, all 651,814 source face
indices, all 389 edge-connected components, and the original per-vertex RGB
payload. The field applies one common unit calibration, then keeps axial height
variation independent from radial width and localized body controls.

The explicit candidate calibration is 1000 mm/raw unit, the 1 m/raw-unit
interpretation. Applied to the raw Z span of 0.119432, this gives 119.432 mm,
which is 0.432 mm above the catalog's reported 119 mm height. The OBJ declares
no units, and the rim and base diameters do not match the candidate scale
exactly. Treat 1000 mm/raw unit as a documented hypothesis, not calibrated
metrology. The frame is the candidate Z-up axis through the audit's top-rim
circle center and raw Z midpoint.

The audit's exact-weld derivative in
[`refinement_v2`](../scanned_anchor_audit/refinement_v2/README.md) was reviewed
but not applied. It derives from a main-only mesh, removes 388 small raw
components and four zero-area faces, and reports two non-manifold edges. This
run therefore records refinement as pending and retains the unchanged raw
geometry in full.

The base anchor and three localized variants are in `run02/`. Each `views.png`
sheet is neutral-shaded with side, front, top, and oblique views at one shared
parallel camera scale. `source_color_views.png` shows the retained OBJ vertex
colors in the same views. `receipt.json` records scale/frame evidence, input
and derived hashes, preserved face/attribute counts, inherited audit findings,
and analytic Jacobian samples. These sampled values do not certify triangle
self-intersection or constant wall thickness. The mesh remains a surface scan;
this deformer performs no repair, smoothing, decimation, remeshing, or part
removal.

| Variant | Controls | Artifacts |
| --- | --- | --- |
| Base anchor | All variation controls zero | [neutral views](run02/base_anchor/views.png), [source colors](run02/base_anchor/source_color_views.png), [receipt](run02/base_anchor/receipt.json) |
| Fuller belly | `belly_fullness = 0.055` | [neutral views](run02/fuller_belly/views.png), [source colors](run02/fuller_belly/source_color_views.png), [receipt](run02/fuller_belly/receipt.json) |
| Broader upper body and rim | `upperbody_width = 0.035`, `mouth_width = 0.045` | [neutral views](run02/broader_upper_and_rim/views.png), [source colors](run02/broader_upper_and_rim/source_color_views.png), [receipt](run02/broader_upper_and_rim/receipt.json) |
| Broader foot | `foot_width = 0.055` | [neutral views](run02/broader_foot/views.png), [source colors](run02/broader_foot/source_color_views.png), [receipt](run02/broader_foot/receipt.json) |

To reproduce run02 from the workspace root:

```powershell
.\third_party\vesselforge-runtime\venv\Scripts\python.exe .\vesselforge\experiments\continuation_20261015\reference_mesh_variation\generate_variations.py
```

The source model is attributed to Medelhavsmuseet, SHM 17946:0047, via Apsida /
Digital Heritage Research Lab under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Redistributed adaptations must preserve the attribution and ShareAlike terms.

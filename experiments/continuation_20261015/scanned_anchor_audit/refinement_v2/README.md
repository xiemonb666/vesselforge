# Exact-coordinate-weld derivative audit: Apsida SHM 17946:0047

This is a separate reviewed derivative branch from `refined_v1`; the source ZIP/OBJ/MTL, raw NPZ, and V1 files were not modified. Source item: [Apsida record 49281](https://apsida.cut.ac.cy/items/show/49281). License: **CC BY-SA 4.0**. Attribution: “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” Any redistribution must preserve attribution and ShareAlike terms.

## Operation and measured result

V1 main-only source: 321,632 vertices, 643,336 faces. The exact-coordinate map found 8 duplicate XYZ groups and reduced the vertex count by 8. It used exact float64 XYZ equality (`numpy.unique`), with no rounding, tolerance, smoothing, scaling, hole filling, or capping. Four faces (raw source IDs 125490, 125512, 292495, 292503) collapsed to fewer than three unique indices and were removed; each was already zero-area from duplicate coordinates. No other triangle or connected handle/foot/body geometry was deleted. See the full old-to-new maps and per-face record.

The candidate status is **FAIL_DO_NOT_USE_AS_CLOSED_PHYSICAL_MESH**. Before: V=321632, E=965004, F=643336, χ=-36; after: V=321624, E=964996, F=643332, χ=-40. Formal genus from χ is before=19 and after=21, but neither is a physical shape measurement; V1 has four degenerate faces and V2 is non-manifold. After metrics: 0 boundary edges; 2 non-manifold edges; 0 inconsistent-winding edges; 0 exact zero-area faces; 1 duplicate triangle groups. Signed volume delta=0 raw-units³ (tolerance: abs 1e-12, rel 1e-09).

The reported source-coordinate unit is **UNKNOWN**. `1 raw unit = 1 m` (multiply by 1000 for mm) remains a scale candidate only, inferred from extents and catalogue dimensions, not calibrated. Passing mesh topology does not qualify wall thickness, scan completeness, physical solidity, or metrology.

## Outputs

- `SHM17946_0047_main_component_exactweld_candidate.obj` and `.npz`: exact-weld derivative, retaining original source positions with unit unknown.
- `SHM17946_0047_exactweld_maps.npz`: raw/V1 vertex and face maps, plus all four removed face IDs.
- `exact_duplicate_xyz_groups.csv`, `removed_degenerate_faces.csv`, `duplicate_faces_diagnostic.csv`: audit trails.
- `refinement_receipt.json`: source hashes, topology comparisons, license, acceptance gates, and render hashes.
- `exactweld_side.png`, `exactweld_oblique.png`, `exactweld_top.png`, `exactweld_bottom.png`, `refined_y_section.png`: full candidate views; display normals are recomputed only for visualization.

See the sibling `refinement_v1` for the pre-weld main-only candidate and full disconnected-island inventory. Raw source and prior renders remain preserved.

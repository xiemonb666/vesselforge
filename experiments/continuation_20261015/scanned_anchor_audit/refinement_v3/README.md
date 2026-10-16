# One local paired-triangle repair: Apsida SHM 17946:0047

This is a separate v3 derivative; the official source ZIP/OBJ/MTL and v1/v2 files remain unchanged. Source: [Apsida item 49281](https://apsida.cut.ac.cy/items/show/49281). Attribution: “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” License: **CC BY-SA 4.0**; preserve attribution and ShareAlike on redistributed derivatives. The OBJ header says it was generated with Agisoft Metashape, but the capture setup and calibration are unknown.

## Single authorized repair

After v2 exact-coordinate welding, raw source triangles **125422 and 125511** became a coincident opposite-winding pair (same 3 XYZ positions, opposite orientation). Together they formed an overlapping zero-thickness double patch and caused two edge-incidence-4 edges. This branch removes **both faces as a pair**, not one arbitrarily. It adds no surface, cap, or fill. Triangle-level coordinates, areas, signed volumes, vertex IDs, source face IDs, and old-to-new maps are in `local_pair_repair.csv` and `SHM17946_0047_localrepair_maps.npz`. Only unreferenced vertex pruning is permitted; actually pruned count=0.

Before: V=321624, E=964996, F=643332, χ=-40; after: V=321624, E=964995, F=643330, χ=-41. After: boundary=0, edge-non-manifold=0, vertex-link defects=7, winding conflicts=0, components=1, zero-area faces=0, duplicate triangle groups=0. Surface area change=-9.1397565071815734e-09 source units²; signed volume change=0 source units³.

Candidate status: **FAIL_UNQUALIFIED_SCAN_USE_AS_VISUAL_REFERENCE_ONLY**. The v3 edge counts are all 2, but the vertex-link audit finds 7 vertices with multiple disconnected link cycles; this is a pinched, non-manifold surface. The Euler characteristic is odd (χ=-41), so there is no valid closed orientable manifold genus. No additional repair will be attempted under this branch; use the scan as a visual/reference source and reconstruct a parametric CAD solid from documented evidence instead. Even a topology pass is **not physics qualification** or metrology: native units are UNKNOWN, and the scale candidate of 1 raw unit = 1 m is uncalibrated. High Euler genus / tunnels are mesh diagnostics, not evidence for real designed vessel features. The 388 detached raw islands remain preserved in the original source and full audit; their omission from this derivative is not a statement about physicality.

## Outputs

- `SHM17946_0047_main_component_localrepair_candidate.obj` and `.npz`: candidate geometry with unchanged positions and face windings except the exact pair removal.
- `SHM17946_0047_localrepair_maps.npz`: full raw/V2 to V3 vertex and face maps, removed face IDs and any pruned vertices. The raw face map accounts for all 8,484 omitted triangles: 8,478 disconnected-island faces, four collapsed zero-area faces from v2, and the two v3 opposite-winding faces.
- `local_pair_repair.csv`: source and candidate face IDs, coordinates, area, and signed volume contribution for each removed triangle.
- `vertex_link_anomalies.csv`: all pinched vertices and their separated link cycles.
- `refinement_receipt.json`: license, parent hashes, topology before/after, visual hashes, and gates.
- `localrepair_side.png`, `localrepair_oblique.png`, `localrepair_top.png`, `localrepair_bottom.png`, `refined_y_section.png`: output views; recomputed point normals are display-only.

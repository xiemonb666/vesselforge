# Reviewed refinement candidate: Apsida SHM 17946:0047

This is a **candidate derivative** of the retained public Apsida model, not a claim that its small components are physically false or that the mesh is ready for simulation. Source: [Apsida item 49281](https://apsida.cut.ac.cy/items/show/49281), [OBJ ZIP](https://apsida.cut.ac.cy/files/original/529/49281/Footed_Bowl_SHM_17946_0047_Obj06.zip). Attribution: “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” Source rights are CC BY-SA 4.0; keep derivative geometry and render outputs under the same license and retain attribution. The license/legal code is in the parent asset directory.

## Refinement performed

The source has 389 indexed edge-connected components. This candidate retains the largest component (ID 0: 321,632 vertices, 643,336 faces, 0.103607534504 raw-unit² area, 0.000257257611876 raw-unit³ signed volume) and omits only the other 388 separate components in this derivative. The removed manifest lists every component ID, vertices/faces, area/volume, bounds relative to the main bounds, and exact nearest point-to-main-triangle distances. Raw source files and the earlier full-geometry audit remain intact.

The retained main component contains all four exact zero-area triangles found by the audit. Each has three different OBJ vertex IDs but only two distinct XYZ positions. Face indices (0-based) are 125490, 125512, 292495, 292503; all belong to component 0. They are preserved without welding/deletion/repair. **Do not use this candidate as a physics-qualified or validated solid mesh** until a topology-aware repair and revalidation are reviewed. No hole caps, smoothing, remeshing, or decimation were applied.

The main component's 643,336 faces have 0 boundary edges, 0 non-manifold edges, and 0 inconsistent-winding edges by indexed edge incidence. It is one edge-connected, closed indexed surface, but this does not establish scan completeness, physical solidity, or capture accuracy.

## Coordinate and dimension status

Coordinates are copied from the source OBJ and remain in its **UNKNOWN** coordinate units. The candidate interpretation 1 raw unit = 1 m (multiply by 1000 for mm) is only a magnitude/metadata-based hypothesis, not a declared or calibrated unit. Under that hypothesis, source height 119 mm is close to the OBJ Z extent, while the rim/base estimates do not match their reported dimensions exactly. No scaling has been baked into the derivative.

## Files

- `SHM17946_0047_main_component.obj`: geometry-only OBJ. Vertex positions are copied exactly from the source values (written to 9 decimal places); face winding/order is preserved. UVs, normals, material, and texture are omitted in this candidate; the original OBJ/MTL/ZIP remain in the parent directory.
- `SHM17946_0047_main_component.npz`: `vertices_source_units`, remapped `faces`, `source_vertex_indices`, and `source_face_indices` for direct programmatic reuse.
- `refinement_receipt.json`: source hashes, versions, exact changes, post-export validation, dimensions, license, and render hashes.

## Visual review matrix

| Review | View/file | Result |
|---|---|---|
| Complete side profile | [orthographic side](../refinement_v1/refined_side.png) | Full bowl, stem, foot, and one visible handle; no clipping after explicit clipping-range reset. |
| Overall form and paired handles | [oblique](../refinement_v1/refined_oblique.png) | Both handles, rim, inner surface, bowl body, stem, and full foot visible. |
| Opening / inner surface | [top](../refinement_v1/refined_top.png) | Bowl cavity and both handles visible. |
| Foot underside | [bottom](../refinement_v1/refined_bottom.png) | Foot area visible from below. |
| Inner/outer wall and foot | [Y-center section](../refinement_v1/refined_y_section.png) | One continuous cut outline shows paired surfaces and foot; raw-coordinate section samples are in `refined_y_section.csv`. This is a section of the actual mesh, not a generated revolved body. |

All render views use the retained main-component triangles. Only computed normals/material lighting are used for display; geometry is not transformed. Renders are new files in the refinement audit directory.

The previous audit's `scan_side.png` had been overwritten when fixing a stale camera clipping range; the earlier raster was invalid because it clipped the foot. These new `refined_*` images are separate. Their hashes identify the current renders, while unchanged source OBJ/ZIP hashes identify native geometry provenance.

No LOD was created: the full-detail main mesh is already 643k faces, and there was no reason to add decimation risk. No tests of the application were run because no application code changed; the geometry export was reparsed and compared byte-value-for-value at positions and face-index order.

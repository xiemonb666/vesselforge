# Tiny route plan

**Status:** planned only; no phase below has been executed in this task.

## 0. Freeze inputs and scope

- Keep the parent reference geometry immutable and versioned.
- Freeze only the handful of source files listed in `vesselforge/tmp/review_20261004/surface_ornament_route/FREEZE_MANIFEST.json`; record their SHA-256 values alongside this proposal and prototype.
- Do not add a bulk scan corpus or infer labels from generated CAD or from mesh resolution changes.

## 1. One local mapping fixture

Use `surface_mapping_prototype.py` to describe a hollow analytic cylinder with an outer side, an inner side, a floor, an underside, and an annular rim. Apply one periodic motif to the outer side only. The function returns both the original rest-coordinate closed mesh and a displaced mesh with the same faces, plus the surface color values. The source has not been run; inspect or revise it before execution.

A later tiny visual acceptance should show the 3D displaced cylinder from outside and in section, plus a 2D color swatch generated from the same sample values. Accept only when:

1. The motif closes at the angular seam and its measured local circumferential size uses `R * delta_theta` for this constant-radius fixture.
2. The stored color samples refer to the original rest coordinates, and cutting or moving a fragment only subsets/transforms geometry while preserving those attributes.
3. The height changes outer boundary vertices along their outward material normals. The inner wall, floor, and rim connectivity remain part of the returned closed boundary mesh.
4. The fixture's wall clearance and curvature proxy are reported as fixture-only measurements; a genuine relief pipeline also runs the full checks listed in DESIGN.md.
5. The displayed RGB goes through the sRGB transfer after linear compositing. PBR/material calibration stays marked unknown.

The parent agent owns the one visual acceptance and its review. This phase must stay small and local; no CAD solver is needed for the analytic fixture.

## 2. Connect the observation to adjacency candidate route

RelicWeave stores a shard observation as measured facts, derived features, uncertainty, and source provenance. PG-Frag consumes that observation and returns ranked historical neighbors with separate evidence such as broken-edge geometry, surface continuity, decoration phase, and catalog/object relationships. Keep the evidence channels and their confidence distinct. VesselForge may supply a proposed parent surface and rest-coordinate map for a reconstruction preview, but neither that surface nor its ornament can create a verified adjacency relation or a fracture target. Human/catalog evidence and physical fracture evidence remain separately labeled.

## 3. Validate the first GPU batch

Only after the local fixture and attribute invariance are accepted, batch independent observed surface patches on RTX 5090. Batch rest coordinates, metric/chart data, and field evaluation; keep each output tied to its parent and source observation. Preserve the exact same geometry and label semantics across performance variants. GPU batching changes throughput, not ground truth. Compare a fixed small batch against the local reference output within documented numeric tolerance before scaling.

## Stop conditions

Stop and mark the relief path unresolved if outward normals are ambiguous, the source-to-parent correspondence is lost, geometry clearance or self-intersection is unknown, the color preview has not applied sRGB encoding, or a data pipeline treats mesh tessellation as a fracture label. The scalar height field alone never passes the actual-relief acceptance.

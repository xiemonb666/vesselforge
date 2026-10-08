# Tiny VF → PG-Frag → A12 → RelicWeave route plan

**Status:** design only. No phase below has been executed in this task.

## 0. Per-sample provenance and qualification

- Allow mother assets to be procedural, reference-derived, or measurement-based. Preserve the actual source and method for each sample.
- Store material assumptions, color calibration, and physics qualification as independent fields; use unknown or unqualified values when evidence is absent.
- Separate synthetic known lineage/adjacency from historically verified relationship ground truth. Never infer historical truth from a generated mother or ornament.
- Keep this first pass small. Do not start with a scale corpus.

## 1. Local VF mapping fixture

Use `surface_mapping_prototype.py` to describe a hollow analytic cylinder with an outer side, inner side, floor, underside, and annular rim. Apply one periodic motif to the outer side only. The source returns original rest-coordinate mesh data, a separate displaced mesh, and color samples. It has not been run.

A later tiny visual acceptance should show the displaced cylinder from outside and in section, plus a 2D color swatch generated from the same sample values. Accept only when:

1. The motif closes at the angular seam and its local circumferential size uses `R * delta_theta` for this constant-radius fixture.
2. Color samples refer to original rest coordinates and survive fracture/cut lineage and rigid movement without pattern regeneration.
3. Height changes outer boundary vertices along outward material normals; the inner wall, floor, and rim remain part of the closed boundary mesh.
4. Wall clearance and curvature values remain labeled as fixture-only proxies. A real relief path must check closure, self-intersection, collision, minimum residual wall, normal orientation, and offset/curvature risks.
5. Linear color is composited before sRGB display encoding. PBR/material calibration remains unknown unless separately measured.

This fixture validates only VF-side surface, material, and ornament mapping. It creates no PG-Frag result or historical GT.

## 2. Tiny synthetic data-chain sample

- VF emits one parameterized mother and records source, material, ornament, calibration, and qualification fields.
- PG-Frag applies its native physical fragmentation path and preserves fracture surfaces plus known synthetic parent/fragment relationships. Historical relation labels are attached only from documented or independently verified evidence.
- A12 derives a few low-cost observations from that source, records degradation and capture settings, adds detailed annotations, runs quality control, and packages a small experimental-pretraining sample. Keep all variants linked to the same source fragment.
- RelicWeave consumes those observation records and owns candidate retrieval, evidence presentation, requests for additional acquisition, or STOP. Keep synthetic and historical evaluation results separate.

## 3. Future GPU throughput check

After local geometry, provenance, and quality controls are accepted, consider RTX 5090 batches for synthetic mother/fracture/degradation throughput. Compare a fixed small batch against a higher-precision reference for geometry, labels, and fields before scaling, and record numeric tolerances. This is a future plan only: no GPU implementation or performance result exists.

## Stop conditions

Do not claim a historical relation when only synthetic lineage is known. Mark material calibration or physical qualification unknown when unsupported. Stop relief qualification when normals, wall clearance, collision, or self-intersection checks are unresolved. Treat mesh precision levels and degraded views as representations of their source, not independent fracture ground truth. A scalar height image alone never passes the actual-relief acceptance.
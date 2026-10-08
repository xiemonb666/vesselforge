# Finite B-rep normal-wall probe adapter

State: **source-only, not executed**. No STEP import, CAD probe, section operation, or render has run. The parent agent must review `normal_wall_probe.py` and `run_normal_wall_probe.ps1` before any future execution.

## Frozen inputs

- STEP: `vesselforge/experiments/smooth_surface_native_adapter_20261005/tmp/runs/single_inner_native_01/candidate.step`, SHA-256 `9a6ac86efb2d714e5d2d737263307014487fe2e45979c4181f6071c6f0cf6c71`.
- Source run receipt: adjacent `run_receipt.json`, SHA-256 `4c17fe03c74a6fe4474d98b3de9305916572910247c64bd144189ca2c3f711c8`.
- The receipt reports mm units, one solid, one shell, 19 STEP faces; `normal_wall_status=UNKNOWN_NOT_RUN_NO_APPROVED_PRODUCTION_BREP_RAY_CHECKER` and global self-intersection remains unknown.

## Existing-method review

- `vesselforge/experiments/smooth_cad_spike.py::sample_sidewall_normal_rays` uses trimmed UV classification at `1e-7 mm`, actual B-rep revolution-face normals, inside/outside checks, and `IntCurvesFace_ShapeIntersector`. Its current qualification summary chooses the first positive hit and aggregates sampled distances. It does not preserve every hit's face identity or classifier state on both sides of each hit.
- `vesselforge/src/vesselforge/semantics.py::_interior_sample` gives the canonical trimmed-UV sample pattern and explicitly reverses normals for `TopAbs_REVERSED` faces.
- `vesselforge/src/vesselforge/wall_mesh_binding.py` fixes CAD numeric tolerance at `1e-7 mm` and rechecks canonical B-rep face normals.
- `vesselforge/experiments/smooth_cad_brep/executed_source_snapshot/build_brep_candidate.py::halfspace_profile_probe` uses a global-X radial line at `z=28 mm`; its first two radii are radial separation, not a normal wall result.

## Adapter method and limits

The adapter is fixed to the STEP and receipt hashes above and verifies one solid, one shell, 19 faces, and mm units. It imports the STEP once. It enumerates actual B-rep faces and a 2×2 interior UV sample grid per face, checks each UV point and small UV neighbors with `BRepClass_FaceClassifier`, obtains the face-oriented normal from `BRepLProp_SLProps`, and records the actual face ID, UV, point, normal, radial-normal dot, and angle to the radial direction. The global Z axis comes from the frozen receipt.

Only clean, outward-facing, revolution-surface sidewall samples in the central axial band can launch a probe. Inner-wall samples are recorded without rays. The lower 12 mm global-Z bounding band is excluded as a base/floor candidate. The upper 12 mm band is excluded as an unresolved rim/lip candidate: the receipt explicitly says nominal rim Z is not the bounding-box maximum, so the adapter does not equate the two. Sloped portions beyond 30 degrees from the radial direction are labelled as rounded transitions and excluded. UV-neighbor failures and seam/trim states remain explicit unknowns. This sampling rule is a finite region choice; it is not a claim that the excluded fillets are safe.

For each selected outer sample, the ray starts `0.0001 mm` inside the actual source face along its actual outward unit normal and travels along the negative normal for a fixed 20 mm segment. `BRepClass3d_SolidClassifier`, `BRepClass_FaceClassifier`, the surface normal evaluation, and intersector loading all keep the existing `1e-7 mm` tolerance. Every intersector hit is retained with raw index, parameter in mm, point, actual face ID, UV, face normal, radial angle, angle to the ray, trimmed classifier state, and classifier states in the open intervals on both sides. The first exit is only a measured interval when that hit is uniquely mapped to an actual inner-sidewall face; a hit on the base, rounded base/shoulder, lip, rim, or trim boundary stays UNKNOWN. No point projection, hit deduplication, averaging, or radial-gap substitution is used; later hits remain in the evidence.

A local interval is measured only when the outward source offset classifies `OUT`, the inward source offset and ray start classify `IN`, the first raw hit establishes a unique `IN→OUT` transition across open intervals, its hit UV is interior, the hit face maps to the imported B-rep, and the actual exit normal is defined. Coincident face/seam hits, short unresolved intervals, an `ON` hit, a missing hit, a failed classifier/intersector, or an undefined normal produce `UNKNOWN` for that probe. All remaining raw hits still appear in the data. The per-ray distance is source offset plus that actual ray parameter; no aggregate min/mean or pass threshold is reported.

Hard bounds are 128 rays, 512 raw hits total, a 20 mm finite search segment, and 180 seconds of worker wall time. A candidate or hit-cap overflow fails closed without subsampling/truncating a measurement or retrying; timeout is also retained as the first failure. Expected future figures are one actual OCCT `y=0` section and one 3D plot of actual ray/source/hit coordinates, with mm axes and no body-mesh measurement. Both are finite visual evidence only. `global_wall_status` is permanently `UNKNOWN_FINITE_PROBES_ONLY`.

The receipt's exact paired side control-pole gap `5/2 mm = 2.5 mm` is copied only as context and explicitly labelled **not normal wall thickness**. The probe distance is computed solely along actual B-rep normals between actual classified interval boundaries. No mesh generation, solver, normal-wall quality promotion, or global minimum-wall proof is included.

## Reviewed source fingerprints

The hashes below identify the read-only method sources reviewed when this plan was prepared. `FREEZE.json` records adapter, wrapper, input, and method-source hashes. `normal_wall_probe.py` has not imported CadQuery/OCP and has not loaded the STEP.

If later approved, use the VF interpreter through `run_normal_wall_probe.ps1`; it records the actual `python.exe -B adapter.py` argv, process rc, elapsed time, and pre/post hashes in this same directory. The Python adapter also has a one-shot lock and a 180 second child timeout.




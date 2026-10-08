# v6 B-rep face-bounds identity plan

Inspection date: 2026-10-04. This is a read-only source/API review for the v5 actual-run failure `CANONICAL_BREP_FACE_BOUNDS_MISMATCH:0`. No production source, v4 asset, or fixture was changed. No CAD construction, STEP operation, binding, test, or solver was run here. The only runtime call imported CadQuery/OCP and printed installed API metadata/docstrings; it created no shape.

## Producer and consumer contract

The production package producer is `vesselforge/src/vesselforge/asset.py`. It exports/imports STEP and selects the reimport as `canonical`; then `mesh_shape(canonical, spec)` runs at line 127. After that, round-trip bounds are queried at lines 149-150 and the per-face `brep_face_inventory` is written at lines 314-326. Each row records index, geometric type, `Center()`, `Area()`, and six `bbox_mm` values obtained from no-argument `face.BoundingBox()` calls at lines 321-324.

`vesselforge/src/vesselforge/geometry.py:178-193` shows that `mesh_shape` first calls `BRepTools.Clean_s(shape.wrapped, True)`, creates `BRepMesh_IncrementalMesh` with the declared linear/angular deflections, and performs it. This is a mutating mesh-cache operation on the same canonical TopoDS shape passed by `asset.py`. `geometry.py:198-214` then reads the per-face triangulations to emit surface triangles. Therefore the producer computes its inventory after adding mesh-cache state.

The consumer is `vesselforge/src/vesselforge/wall_mesh_binding.py`. `build_wall_mesh_binding` reimports the exact STEP once at lines 988-989, then `_binding_from_loaded_inputs` calls `_check_face_inventory` at lines 867-868. The check at lines 669-697 again calls no-argument `face.BoundingBox()` and compares all six components against the manifest at the existing `cad_numeric_tolerance_mm`. This happens before consumer-side re-meshing. Producer and consumer therefore request the same high-level call from different mesh-cache states.

The tiny runner at `vesselforge/tmp/review_20261004/wall_mesh_binding/run_hollow_cylinder_binding.py:39-53,209` independently mirrors the producer ordering: it records face bounds after its single `mesh_shape` call. This fixture is not the production asset producer; `asset.py` is the relevant package contract.

## Installed CadQuery behavior

The project allows CadQuery `>=2.8,<2.9`. The inspected runtime is Python 3.12.14 / CadQuery 2.8.0. `cadquery/occ_impl/shapes.py:683-692` implements `Shape.BoundingBox(tolerance=None)` by calling `BoundBox._fromTopoDS(self.wrapped, tol=tolerance)`. `cadquery/occ_impl/geom.py:982-1005` defaults `_fromTopoDS` to `optimal=True`, then calls `BRepBndLib.AddOptimal_s(shape, bbox)` without passing either optional flag. In this optimal branch it does not pass CadQuery's local `tol` variable.

The installed OCP method docstring reports `AddOptimal_s(S, B, useTriangulation: bool = True, useShapeTolerance: bool = False)`. Its documentation describes an optimal/precise box and says shape tolerances are applied only when `useShapeTolerance=True`. `Add_s` documentation explicitly says its default uses face triangulation when present and expands by triangulation deflection plus face tolerance; CadQuery's non-optimal path uses that method. The current no-argument call does not explicitly select a cache-independent bounds policy: the optimal API's `useTriangulation` default is true. This makes triangulation/cache state a plausible source of disagreement, but this static inspection does not prove that it caused the observed face-0 mismatch or explain its magnitude. The independent STEP diagnostic should settle that point; retain UNKNOWN until it does.

## Smallest safe contract correction if the diagnostic confirms cache dependence

Use one shared face-bounds helper for both `asset.py` inventory production and `wall_mesh_binding.py` verification. Compute a documented B-rep geometry bound with `BRepBndLib.AddOptimal_s(face.wrapped, box, useTriangulation=False, useShapeTolerance=False)` (or an equivalent API proven to exclude cached tessellation), and serialize those six values in millimetres. Keeping `useShapeTolerance=False` gives the nominal trimmed-geometry bounds under the kernel's numerical precision; if the product instead chooses tolerance-expanded bounds, that choice must be explicit and identical at producer and consumer. Never rely on CadQuery's implicit default for an identity field.

Version the bounds algorithm in the `brep_face_inventory` contract (including the backend/API policy) and make the consumer require that version. Regenerated inventory and consumer verification must use the same helper; missing/old/unknown algorithm metadata should fail closed as UNKNOWN, not be silently interpreted with the new meaning. Leave the existing numeric comparison threshold unchanged. Continue to check the face count/order/type, center, area, full canonical face reclassification, file SHA and station checks independently; a matching bounding box is corroborating face metadata, not a unique topology identity.

The minimal regression should evaluate the same canonical STEP face inventory before and after meshing/cache insertion and confirm identical canonical bounds, then compare against a fresh STEP import using the same helper. Keep a distinct altered/reordered-face negative case. If diagnostic data shows that explicit geometry-only bounds still disagree, do not implement this as a tolerance adjustment: keep the binding UNKNOWN and investigate the exact face/source STEP or producer pipeline discrepancy.

## Read-only evidence snapshot

- `asset.py`: `f9c11a60beed1d165431b8ea590c52db382b780479ad262fee1cc5a7be3274d0`
- `geometry.py`: `0c48940d9ef22aabb068a2e7c6e89b4249a7e724d0ade1c8933a6c951e086047`
- v5 `wall_mesh_binding.py`: `81668d278f165e2fa75b874fccfaef726024d249605d324f6e1acbe1ca96be45`
- tiny runner: `37a4f438c6eae507a6fc02ed1aaf59fbc625bd1dab7c536ef28bf2a4683925dc`
- CadQuery `shapes.py`: `6f6a9136b45177bd9cb00ed1706f90078aab04ea2b1a7eb26ab5b46aa43f6c94`
- CadQuery `geom.py`: `4a32ab0aabb4a045a4ecb3853c2ec126e3675d39357adb38923acc97c08fc6a`
- OCP `BRepBndLib` package initializer: `6b1830406e7e1c4a1a962e701b6cf141bba935e403162638743bdbf8d26079d4`
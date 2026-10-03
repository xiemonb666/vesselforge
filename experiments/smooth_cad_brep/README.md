# Native BREP persistence spike

This folder keeps a portable, reviewable copy of the one-solid native BREP experiment under the VesselForge experiments tree. It does not alter VesselForge production schema, APIs, generator behavior, or the `forge.asset.v1` contract. Strict canonical STEP remains the production format. The completed historical candidate is `BREP_CANDIDATE` / `NOT_PROMOTED`; it is not a `solid.step` asset.

## Historical run versus portable source

The executed evidence remains under `relicweave-synlab/tmp/review_20261004/implementation/vf_brep_persistence/native_brep_persistence/`. Its `run_receipt.json` and `mesh_refinement_receipt.json` retain the actual historical argv and exit codes. The original builder source is byte-identical to `executed_source_snapshot/build_brep_candidate.py`. It made one body `exportBrep` call and one `importBrep` call. Its exit code was 2 because the first 0.05 mm mesh exceeded the 0.10 mm sampled-deviation gate; the native BREP round trip itself retained one valid solid and one shell. The single authorized remesh later passed at 0.02 mm linear and 0.08 rad angular deflection.

The pre-run Python 3.12 bytecode cache for that remesh is retained as `executed_source_snapshot/refine_native_brep_mesh.executed.cpython-312.pyc`, with its SHA-256 in `execution_source_manifest.json`. After the run, a label-only wording correction changed the readable `.py` source. `executed_source_snapshot/refine_native_brep_mesh.postrun_label_corrected.py` is that later source, not an exact source snapshot of the historical invocation. The current helper snapshot also includes the trimmed-face diagnostic added for remeshing; its exact pre-build bytes were not preserved. These distinctions are recorded rather than presenting later files as byte-identical run inputs.

`build_brep_candidate.py` and `refine_native_brep_mesh.py` in this folder are portable copies and were not executed for the reported candidate. Both require explicit `--repository-root` and `--output` arguments. The builder requires a new empty output directory, sets a write marker before its only BREP export, and refuses a second attempt in that directory. The remesher reads that directory's BREP and report, uses one 0.02 mm / 0.08 rad tessellation, and writes a separate attempt marker; it never writes a BREP. These portable scripts deliberately report `BREP_PERSISTENCE_PRESERVED_QA_PENDING` or `BREP_MESH_QA_PASSED_FULL_GEOMETRY_QA_PENDING`: they do not synthesize the historical normal-wall-ray, floor, cavity-probe, or native section-face checks. A portable run cannot report `BREP_CANDIDATE` unless every required full-QA check is actually present and true. `brep_persistence_helper.py` and `accepted_profile_definition.py` contain the isolated profile, offset, trimmed-face projection, and preview helpers used by those portable scripts.

## Recorded candidate evidence

The persisted native BREP retained one valid solid and one shell, volume 26,998.301999424355 mm³, and a 41 × 41 × 56 mm bounding box. The exact lower and upper degree-5 B-spline spans pass the C2 join check; the 2,001-sample-per-span curvature check found a minimum radius of 5.941661 mm against the 5 mm threshold. The first mesh used 0.05 mm absolute linear and 0.08 rad angular deflection; it had 10,217 nodes and 20,430 faces. Its 602 samples produced a 0.115315794 mm maximum and 0.018486547 mm p95. The worst sample was an edge midpoint at `(-11.608900893, -9.376768122, 35.567023604)` mm on native BREP face 5. That isolated threshold miss selected the one remesh at 0.02 mm linear while holding 0.08 rad angular deflection.

The remesh of the same reimported BREP had 13,244 nodes and 26,484 faces. In 602 deterministic samples, maximum trimmed-face distance was 0.040084606 mm, p95 was 0.014721735 mm, and no samples were unknown. The worst point was a triangle centroid at `(0.767308222, 15.257633082, 30.884973456)` mm on native BREP face 6, with its UV projection classified inside the trimmed domain. The body plus actual half-space section used 45,272 faces and 2.375 seconds. Normal wall rays measured 4.000000 mm, floor separation measured 4.000000 mm, and the actual `y >= 0` cut retained one valid solid at 0.499999844 of the original volume. The reloaded-BREP image is at the historical evidence path's `renders/native_brep_and_half_section.png`.

The method projects deterministic mesh edge-midpoint and triangle-centroid samples to the native trimmed BREP face selected by triangle lineage. It classifies periodic UV copies against the trimmed domain and uses exact point-to-trim-edge distance when a valid trimmed surface projection is unavailable. This is finite sampled evidence, not a full Hausdorff bound. The earlier STEP round trip remains a failure (two shells, zero solids); this BREP result does not claim STEP persistence or replace STEP in production.

## Portable invocation shape

These commands are examples only and were not run in this task. Choose a fresh output directory for a new native BREP attempt, then use that same directory for the one-time remesh:

```powershell
& <python.exe> .\vesselforge\experiments\smooth_cad_brep\build_brep_candidate.py `
  --repository-root <repository-root> --output <new-empty-candidate-directory>

& <python.exe> .\vesselforge\experiments\smooth_cad_brep\refine_native_brep_mesh.py `
  --repository-root <repository-root> --output <same-candidate-directory>
```

The source and artifact hashes for the actual tmp run are in its `source_and_artifact_sha256.json`; hashes for the retained source snapshots and portable copies are in `execution_source_manifest.json`.

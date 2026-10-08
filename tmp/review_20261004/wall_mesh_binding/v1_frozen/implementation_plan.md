# Wall mesh binding stage 1 fixture and review plan

This directory freezes an executable, tiny analytic fixture plan for `vf.wall-mesh-binding.v1`. The runner is source only and has not been executed. It creates one 10 mm tall nested-wire extrusion with outer radius 10 mm and inner radius 8 mm, exports one STEP file, imports that exact STEP file once, and calls `geometry.mesh_shape` once on the imported shape. It uses no Boolean or solver.

The runner writes its generated package only to a required absolute output path that must not already exist. It derives face semantics and the wall reference from the one canonical import, writes the minimal `forge.asset.v1` payloads needed by `validate_asset`, then reuses that same in-memory canonical shape in `_binding_from_loaded_inputs`. This avoids a second STEP import while exercising the same internal verification and binding path used by the public reader after package/hash validation.

The fixed analytic wall oracle is `10.0 - 8.0 = 2.0 mm` in the radial direction. It is only an input-geometry reference for this binding fixture. The run does not call `wall_intervals`, does not infer a global minimum, and cannot establish material or physical qualification. All requested mother wall-reference stations must bind; missing or ambiguous stations remain `UNKNOWN`.

## Frozen files

- `fixture_input.json`: geometry, error-budget inputs, operation counts, and scope limits.
- `run_hollow_cylinder_binding.py`: one-shot fixture package builder and audit report writer.
- `freeze.json`: SHA-256 values for the implementation, tests, plan, fixture input, and runner source at review freeze. It intentionally does not hash itself.

## Review gate

The parent agent must review these frozen sources and inputs before invoking the runner or the test file. Until that review, no CAD, STEP export/import, mesh generation, pytest, Boolean, ray query, solver, or Git command is authorized in this subtask.

After approval, the one-shot command is:

```powershell
python vesselforge/tmp/review_20261004/wall_mesh_binding/run_hollow_cylinder_binding.py --output <new-absolute-output-directory>
```

The runner rejects an existing output directory. It emits `metadata/wall_mesh_binding.json` containing the five independent file-byte hashes, the composite mesh-content hash, backend versions, station rows and projection/normal errors, and the explicit nonclaims. The generated report is audit output, not a P03 input and not a global wall QA result.

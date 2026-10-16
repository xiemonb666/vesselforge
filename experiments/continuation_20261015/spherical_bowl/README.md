# Bounded spherical-bowl asset cases

The frozen case inputs are in `cases/`. From the VesselForge repository root, launch each case with the bundled runtime and a fresh run directory:

```powershell
.\experiments\continuation_20261015\spherical_bowl\run_case.ps1 `
  -PythonExecutable ..\third_party\vesselforge-runtime\venv\Scripts\python.exe `
  -CaseFile experiments/continuation_20261015/spherical_bowl/cases/three_bands.json `
  -RunDirectory experiments/continuation_20261015/spherical_bowl/runs/three_bands_01

.\experiments\continuation_20261015\spherical_bowl\run_case.ps1 `
  -PythonExecutable ..\third_party\vesselforge-runtime\venv\Scripts\python.exe `
  -CaseFile experiments/continuation_20261015/spherical_bowl/cases/four_bands.json `
  -RunDirectory experiments/continuation_20261015/spherical_bowl/runs/four_bands_01
```

The launcher refuses existing run directories and the Python runner refuses existing package destinations. Every run records its exact case and argv, runner bytes, VesselForge source snapshot and inventory, output hashes, validation results, independent analytic volume comparison, elapsed time, and package byte count. A failed or timed-out run is retained in its own run directory; retry with a new run-directory name and output path.

The initial bounded results are recorded in `docs/continuation/20261015/SPHERICAL_BOWL.md`.

The saved-asset comparison is produced by `render_saved_assets.py` and stored under `visualization/`. It reads every saved triangle and its rest-coordinate-derived per-face color without downsampling; the separate `render_receipt.json` binds both input package hashes, the renderer source hash, and the PNG hash. The image is a geometry/paint preview with explicitly unvalidated material labeling.

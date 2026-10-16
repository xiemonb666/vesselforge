# Generic STEP partition diagnostic

`run_reference_tetra.py` meshes the current daily Aberdeen size-reference candidate (`daily_aberdeen_108x53_v5`) as an engineering diagnostic. That candidate is explicitly not a measured profile reconstruction or a physically qualified training specimen. The independent meridian volume and section area are checks on this CAD candidate, not evidence that its assumed profile matches the museum object.

The runner imports its millimetre STEP into Gmsh/OCC with `Geometry.OCCTargetUnit=M`, cuts at `x=0`, and writes a text MSH 2.2 mesh plus an SI NPZ representation at a 1.5 mm global target. The run is capped at 100,000 T4 cells, 2 GiB forecast memory, 32 MiB STEP input and 250 source faces. The 2.6 mm pilot produced 19,171 T4 cells, corresponding to 10.3 cells per `CAD volume / h^3`; the preflight uses a factor of 10, which exceeded measured density in the 1.9 mm pilot (34,434 cells, 7.2 per `CAD volume / h^3`). The reusable adapter keeps its default factor at 50 for uncalibrated geometry. It rejects output whose tetrahedral volume differs from OCC by more than 1%.

Run from the workspace root with:

```powershell
& .\third_party\vesselforge-runtime\venv\Scripts\python.exe .\vesselforge\experiments\continuation_20261015\reference_tetra\run_reference_tetra.py
```

The existing `face_lineage.json` contains source face IDs and roles but no exact mapping to the imported Gmsh OCC surface tags. The adapter therefore leaves exterior source face IDs and roles unknown for this candidate. Exact roles are supported when metadata supplies a direct source-face-ID to imported-surface-tag binding; descendant faces are then propagated through OCC's boolean fragment parent map.

The generated mesh is diagnostic geometry only. It does not establish source-profile fidelity, material calibration, fracture behavior, or solver qualification.

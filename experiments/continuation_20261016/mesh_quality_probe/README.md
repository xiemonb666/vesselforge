# Correction — 2026-10-16

The v1 report's 103 mm same-tag displacement and all-49-surface connectivity changes were artifacts of Gmsh node-ID renumbering, not physical boundary movement. A controlled rerun with `Mesh.Renumber=0` confirms exact boundary/interface coordinate and triangle-connectivity preservation. See [the v2 findings](run_v2/README.md) and [machine-readable v2 report](run_v2/mesh_quality_probe_v2.json). The historical v1 measurements below are retained; do not interpret its raw-tag displacement as geometric motion.

# Bounded Gmsh tetra quality probe

This experiment tested the existing full-size daily Aberdeen v5 diagnostic mesh at `vesselforge/experiments/continuation_20261015/reference_tetra/daily_aberdeen_v5_diagnostic`. It did not reload or change the STEP design, loading, material model, or element order. It did not run a solver. The source is a disposable geometry diagnostic, not the latest v6 mesh or an accepted physical mother.

**Result: no optimizer produced a qualifying candidate.** The Gmsh default optimizer did not improve the minimum tetrahedron altitude. Both default calls changed the loaded mesh's surface triangulation and moved boundary/interface nodes, so their outputs failed the exact surface-preservation gate. The Netgen call raised an access violation and left 28,330 negatively oriented tetrahedra in its isolated model; the independent audit rejected it. No candidate mesh was written.

The baseline is 56,139 T4 elements and 18,236 nodes. Its minimum per-tetrahedron altitude is 0.0587216 mm; p1, p5, and median are 0.359507, 0.663232, and 1.139899 mm. The Gmsh `minSICN` minimum and median are 0.045115 and 0.829620. The independent `tetra_audit` passes, and the mesh volume is 0.6121% below the source CAD volume.

| Run | T4 | Minimum altitude (mm) | Minimum / median `minSICN` | Surface result | Tetra audit | Decision |
|---|---:|---:|---:|---|---|---|
| Baseline | 56,139 | 0.058722 | 0.045115 / 0.829620 | Exact source coordinates and triangle connectivity | PASS | Control |
| Gmsh default, `force=True` | 56,128 | 0.058722 | 0.045115 / 0.829606 | Failed: 17,891 surface nodes moved; maximum displacement 103.649 mm; all 49 surface entity connectivities changed, including all 541 interface triangles | PASS | Rejected |
| Gmsh default, `force=False` | 56,139 | 0.058722 | 0.045115 / 0.829620 | Failed with the same boundary/interface movement and connectivity changes | PASS | Rejected |
| Netgen, `force=True` | 56,139 | Not meaningful after orientation failure | -0.997458 / -0.316390 | Surface tags, coordinates, and triangles remained unchanged | FAIL: 28,330 negative tetrahedra | Rejected |

The global minimum altitude stayed unchanged in all runs, so the mesh-only stable-step ceiling proxy is 1.0× and implies no reduction in steps per fixed duration. This is only a geometric ratio estimate; no material wave speed or native solver timestep was evaluated. The default optimizer slightly raised p1 and p5 altitudes while leaving the worst height unchanged, and its median SICN changed by -0.0000145.

Each optimization used a fresh Gmsh 4.15.2 model loaded from the original MSH and one `gmsh.model.mesh.optimize` pass, with `dimTags` containing only the two volume entities. Gmsh's [4.15.2 API manual](https://gmsh.info/doc/texinfo/gmsh.html) documents the default tetrahedral optimizer, the optional `Netgen` method, the discrete-entity `force` flag, and `getElementQualities` with `minSICN`. The post-run gate compared surface entity tags, triangle node-tag connectivity and orientation, and surface-node coordinates by exact Gmsh node tag; it did not guess correspondences by nearest point. The source NPZ coordinates match the text MSH coordinates within 1e-17 m (maximum difference 6.94e-18 m from text serialization). Optimizer preservation was checked bitwise against the loaded MSH baseline.

The existing source-face ancestry is `PRESENT_BUT_UNBOUND`. Its exterior source face IDs remain unknown; this experiment does not assign them. The baseline and all accepted/rejected optimizer runs were checked with the existing independent tetra audit, including orientation, manifold boundary, partition closure, interface-parent, and volume checks.

The source forecast is 96,942 tetrahedra and 1,588,297,728 bytes, within the declared 100,000-cell and 2 GiB limits. The successful full probe took 23.016 seconds of process wall time. Peak process memory was not sampled; the recorded memory figure is the source's declared forecast.

Run from the workspace root with:

```powershell
& .\third_party\vesselforge-runtime\venv\Scripts\python.exe .\vesselforge\experiments\continuation_20261016\mesh_quality_probe\run_mesh_quality_probe.py
```

The runner writes `mesh_quality_probe.json`; it writes a variant-named `.msh` and `.npz` under `candidates/` only if every preservation/audit/resource gate passes and the minimum altitude strictly improves. The current candidate list is empty.

Source hashes and run-by-run checks are in [mesh_quality_probe.json](mesh_quality_probe.json). Runner SHA-256: `aa32f021526b883d367a46fd9faf6f14f5af46ab4e512e9bd5267bd364621417`. Probe JSON SHA-256: `92d392e529c4931866e822b6394415d49bc628a769d4a04dbaa98398b95fcc0f`.

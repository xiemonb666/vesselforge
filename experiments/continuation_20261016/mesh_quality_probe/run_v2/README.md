# Gmsh mesh-quality probe, renumber-controlled rerun

This is a separate, bounded rerun of the existing full-size daily Aberdeen v5 diagnostic mesh. It loads the original MSH, records exact Gmsh node and element tags, sets `Mesh.Renumber=0` before opening/optimizing, and runs one default Gmsh tetrahedral optimizer pass on the two volume entities. It does not change STEP geometry, loading, constitutive model, or discretization order, and it does not run solver evolution. This v5 diagnostic is not the latest v6 mesh or an accepted physical mother.

**Result: no candidate qualifies.** In this rerun, all 49 surface entities retain the same indexed node tags, bitwise boundary/interface coordinates, and oriented triangle connectivity under the same surface-element tags. The independent `tetra_audit` passes, and every tetrahedron remains positively oriented. The minimum tetrahedron altitude is unchanged at 0.0587216 mm, so the strict quality-improvement gate rejects the mesh. No candidate MSH was written.

| Metric | Baseline | After one default optimizer pass |
|---|---:|---:|
| T4 elements / nodes | 56,139 / 18,236 | 56,128 / 18,236 |
| Minimum tetrahedron altitude (mm) | 0.0587216313 | 0.0587216313 |
| 1st percentile altitude (mm) | 0.3595067280 | 0.3644679623 |
| 5th percentile altitude (mm) | 0.6632324910 | 0.6639288855 |
| Median altitude (mm) | 1.1398991534 | 1.1399143691 |
| Minimum / median Gmsh `minSICN` | 0.04511485 / 0.82962030 | unavailable: `Unknown element 92465` |
| Signed tetrahedral volume (m³) | 3.2517391035e-5 | 3.2517391035e-5 |
| Relative CAD-volume error | 0.6121% | 0.6121% |
| Independent tetra audit | PASS | PASS |

`Mesh.Renumber` read as 1 at Gmsh initialization, was set to 0 before loading the mesh, and remained 0 after loading and optimizing. The [official Gmsh 4.15.2 manual](https://gmsh.info/doc/texinfo/gmsh.html) defines this option as renumbering nodes and elements in a continuous sequence after mesh generation, with default 1; its mesh API documents the empty method string as the default tetrahedral optimizer. The option is recorded as a controlled setting, not assumed to guarantee tag stability by itself.

With renumbering disabled, the rerun reports the same node tags before and after, no boundary or interface node movement, and exact surface triangle element-tag/connectivity equality. Two interior nodes changed coordinates at the bit level, with a maximum displacement of 1.84e-18 m. The root review corrects the earlier 103 mm same-tag displacement/all-49-connectivity-change claim as a Gmsh ID-renumbering artifact, not physical boundary motion. This rerun independently confirms exact boundary/interface preservation with `Mesh.Renumber=0`; the earlier post-optimization arrays were not retained here, so this artifact does not reconstruct an old-to-new node-tag bijection.

The optimizer changed the T4 count by 11. Of the exact tetrahedron element tags, 57 occur only before and 46 only after; all common element tags retained their oriented node-tag connectivity. The independent audit recalculated geometry from coordinates/connectivity. Gmsh's post-optimization `getElementQualities` lookup failed with `Unknown element 92465`, so the report leaves optimized `minSICN` unavailable and records the audit's stored-cell-volume comparison as not evaluated. It does not invent a replacement SICN value.

The source reports 96,942 forecast tetrahedra and 1,588,297,728 forecast peak bytes, below the declared 100,000-cell and 2 GiB limits. The worker took 8.13 seconds; the controller completed in 8.86 seconds. Actual peak memory was not sampled. Worker stdout and stderr were empty; all files in this run directory total 42,001 bytes, below the 256 MiB cap. The source exterior ancestry remains `PRESENT_BUT_UNBOUND`; no face mapping was inferred.

The successful JSON reflects the final complete invocation. During runner debugging, two earlier invocations each reached their single optimizer call but failed before producing a complete report: one exposed Gmsh's post-optimization `getElementQualities(..., 'volume')` error, and one failed in the probe's follow-on capture code. Neither retained a candidate or output mesh. These are disclosed here; the recorded quality/audit result is from the completed invocation.

Reproduce from the workspace root with:

```powershell
& .\third_party\vesselforge-runtime\venv\Scripts\python.exe .\vesselforge\experiments\continuation_20261016\mesh_quality_probe\run_v2\run_mesh_quality_probe_v2.py
```

The runner is [run_mesh_quality_probe_v2.py](run_mesh_quality_probe_v2.py), and machine-readable results are in [mesh_quality_probe_v2.json](mesh_quality_probe_v2.json). Runner SHA-256: `de2abe873a12ad6357bdec5b0e3580cd2bdceaf5cfdc18227fcf92d6b80ead06`. JSON SHA-256: `503c2cba42977c3a98bd3a71796a3a49570c9799d9765afd386bf2eca23c8042`.

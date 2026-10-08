# VesselForge profile catalog native adapter pilot

This experiment calls the existing `vesselforge.profile_catalog.build_profile("bowl")` and `build_profile("jar")` default cases, validates the returned input data without changing it, and revolves each `closed_material_section_mm` polyline into one native CadQuery/OCC solid. It has no production integration point.

The catalog describes length in millimetres and uses a right-handed Z-up meridian `(radius_mm, z_mm)`. The adapter maps radius to the CadQuery XZ workplane and revolves about global Z. It preserves all default parameters, ranges, source strings, and the catalog's wall/base declaration meanings in the input and output records.

The profile is a piecewise-linear analytic candidate. This pilot does not claim C2 continuity, smoothing, global minimum normal wall, a measured wall, real-vessel/style matching, material qualification, mesh quality, or physical performance. STEP identity checks cover topology, cavity probes, bounding boxes, and volume only. PNGs show an OCC section of the STEP-roundtripped BRep plus a tessellated display view of that BRep.

Run once with the exact VesselForge virtualenv pinned in the adapter:

```powershell
& 'third_party/vesselforge-runtime/venv/Scripts/python.exe' -B 'vesselforge/experiments/catalog_native_adapter_20261006/catalog_native_adapter.py'
```

The runner refuses to overwrite `vesselforge/tmp/review_20261006/catalog_native_adapter_20261006/pilot_01`, permits one child process per default profile, allows no retry, caps each child at 38 seconds and the parent at 85 seconds, and checks each candidate output tree against 10 MiB.

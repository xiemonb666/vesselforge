# Catalog native adapter pilot result

The one-use pilot completed both default cases from `vesselforge.profile_catalog.build_profile`. It finished in 8.36 seconds total, with one native build, one STEP export/import, and zero retries per family. All recorded source pins were unchanged before and after execution.

The adapter uses the catalog's `(radius_mm, z_mm)` points unchanged in a right-handed Z-up frame, mapped to a CadQuery XZ workplane and revolved about global Z. The catalog profiles are piecewise-linear analytic candidates. The catalog's wall declaration remains a constant radial meridian offset at corresponding control heights; the base declaration remains the inside-floor datum relative to the outside floor. The existing production `geometry.build_components` was not used because it computes a true meridian-normal side offset and adds a handle. The existing smooth adapter was read for its bounded native validation pattern, but its exact quintic candidate and C2 checks are unrelated to these catalog profiles.

| Case | BRep / STEP | BBox (mm) | Volume (mm³) | Cavity probe | Wall probe | STEP | PNG | Case artifacts |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| Bowl default | Valid, 1 solid, 1 closed shell; 14 faces | x/y ±60, z 0–90 | 76,934.46249376034 | Outside | Inside | 31,197 B | 343,127 B | 553,435 B |
| Jar default | Valid, 1 solid, 1 closed shell; 16 faces | x/y ±54, z 0–120 | 86,855.41354514113 | Outside | Inside | 35,912 B | 295,645 B | 514,650 B |

For both STEP roundtrips, the bounding-box delta was 0 mm and volume deltas were below `9e-8 mm³`. The wall probe verifies representative material exists between paired radial-offset profile segments; it is not a minimum-wall measurement. The axial probe verifies the vessel cavity is not filled.

The result is only native CAD/STEP topology and parameter-bound evidence. No C2/smoothness, global minimum normal wall, measured wall, real-vessel/style match, material/physical qualification, mesh validation, or solver result is claimed. Each PNG shows an OCC planar section of the STEP-roundtripped BRep and a tessellated display view of that BRep.

## Artifacts

- Adapter and implementation note: `vesselforge/experiments/catalog_native_adapter_20261006/`
- Pilot manifest: `pilot_01/pilot_manifest.json`
- Pre/post source pins: `pilot_01/PRE_RUN_SOURCE_PINS.json`, `pilot_01/POST_RUN_SOURCE_PINS.json`
- Bowl: `pilot_01/bowl_default/candidate.step`, `pilot_01/bowl_default/native_brep_section_and_3d.png`, `pilot_01/bowl_default/native_case_receipt.json`
- Jar: `pilot_01/jar_default/candidate.step`, `pilot_01/jar_default/native_brep_section_and_3d.png`, `pilot_01/jar_default/native_case_receipt.json`

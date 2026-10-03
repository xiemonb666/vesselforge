# VesselForge Core

An independently installable, deliberately small CAD and asset-package prototype for the RelicWeave vertical slice. The first supported specimen is one open, turned vessel with a swept, boolean-fused handle. It is not a general historical vessel generator.

The package emits `forge.asset.v1`: millimetres, right-handed Z-up, a STEP solid, a triangulated surface, optical fields evaluated in immutable asset-local rest coordinates, provenance, file hashes, a data dictionary, and geometry-only QA. The mechanics values are illustrative and marked `UNVALIDATED_PROTOTYPE`. The painted band recipes are reproducible optical rules, have zero geometric relief, and are marked `NOT_VALIDATED` as historical styles.

Intact-surface regions are classified per trimmed face from the canonical STEP solid using OpenCascade surface type/axis and face-oriented normals, then projected through triangle-to-face lineage. The package records the rule/version, backend, sample UV/normal, source STEP SHA-256 and evidence for every face. Any unknown face blocks coloring and asset generation; the reserved fracture code is not assigned to this intact sample.

Install into an isolated Python 3.11–3.13 environment:

```powershell
python -m pip install -e ".[test]"
vesselforge generate --out .\out\four_bands --pattern four_bands --seed 20261003
vesselforge validate .\out\four_bands
```

The corresponding Python API is `vesselforge.create_asset_package(...)` and `vesselforge.validate_asset(...)`. No SynLab runtime is required. Canonical surface arrays and spec are seeded/reproducible; STEP headers can contain timestamps, so byte-identical packages are not promised.

## Scope and limitations

- The local example is small by design (target body width 41 mm, height 56 mm, 4 mm shell target). Local use is for smoke tests and review. Approved later batch synthesis/training belongs on the separate RTX 5090 / 48 GB host.
- Wall evidence covers the analytic meridian side profile and a measured planar floor face; it is not a global minimum-wall proof over the fused solid. Mesh-to-canonical-STEP deviation uses deterministic finite sampling at the declared absolute linear deflection; it is not a Hausdorff proof.
- The Python API rejects non-finite specs and bounds linear tessellation deflection to 0.04–0.25 mm and angular tolerance to 0.02–0.20 radians to limit local mesh size. Values outside the supported prototype envelope fail clearly; they are not silently clamped.
- CAD validity, wall checks, STEP round-trip, mesh-to-CAD sampled deviation, and clean exports do not establish material calibration, real impact physics, type accuracy, or historical ornament authenticity.
- The initial geometry has no relief. Later cup/bowl/plate/jar/bottle/jug parameter models and true relief require their own sourced references and refreshed wall/curvature/solver QA.
- Assets use only package-relative paths. Validators reject absolute paths, traversal, symlinks and hash/byte mismatches.


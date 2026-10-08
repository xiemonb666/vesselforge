# Final source-only review

**Source review: ACCEPTED.** The revised source removes the earlier representation-sensitive role gate and fixes the axis shape test. I found no remaining static blocker in the reviewed revision. This acceptance does not authorize or report a CAD/STEP pilot; execution remains disabled and runtime geometry outcomes remain unknown.

## Reviewed bytes

- Driver `native_c4_ingress.py`: SHA-256 `361dac93245b10baa5d331e8d66f808b3bb0af317b8f4ac8d0f13de7acaf7f6e`.
- Capture runner `capture_once.py`: `f06787c7dd358149f701abaa14bdbfa58c6251ab73c9bc1c417542f2744b886a`.
- Case `native_c4_ingress_case.json`: `c440df8ff8d7cd0ec3f6d67d6ce8b566f783974bdf14cd27aafdf6203cba96be`.
- Pins `native_source_v1/source_pins.json`: `33f727be1fc4f31b84f894ac6f34c98235036fdc46ada255b87b6bf41a98bc04`.
- `native_input_gate.py` remains byte-identical to the prior freeze: `45ee34ab7963c2d8886bd21be6844a0d171adb8257ee3665bd91a182aa4d44e4`.

The final driver, runner, case, and pins were diffed against the five-file `pre_face_type_revision_freeze`; the unchanged input gate also matched its frozen bytes. The final case and pins parse with unique JSON member names. Pins contain 20 records (4 source files, 5 inputs, 2 preserved files, 9 tooling files), and all 20 referenced SHA-256 values match current files. Both authorization flags remain `false`; the future `run01_root_go` directory is absent.

## Findings

The native face roles now come from `Generated(source_edge)` history. Each result must be a FACE, match exactly one face in the actual body inventory under `IsSame`, and be unique across roles. Representation-independent source-edge bounds check the base, varying-radius side, constant-radius neck, and flat lip signatures. Adaptor surface types are recorded as report data only.

After STEP import, each face must uniquely match one native per-role bounding-box and area fingerprint. The `1e-7 mm` per-bound and `1e-8` relative-area thresholds match the case. Ambiguous, duplicate, or absent matches fail the semantic-role gate. The source explicitly limits these metrics and the body bounds/area/volume comparison; it makes no full geometry-equality or wall-thickness claim.

Axis history now checks `ShapeType()` against `TopAbs_FACE` before interpreting it, records `Generated(axis_edge)` and `Degenerated()` results, and requires a valid closed solid with the planned face gates. The exact-version stub wheel confirms the changed API names: `BRepPrimAPI_MakeRevol.Generated`, `Degenerated`, and `HasDegenerated`; `TopoDS_Shape.ShapeType` and `IsSame`; `Geom_Curve.Value`; and `TopTools_ListOfShape.Extent`, `First`, and `Last`. Evidence is from wheel SHA-256 `5ecba090df1ada12c558ff4a1b49c61d5155edc8cb3411067a785e3b43f4b359`, version 7.9.3.1.1, read as a static archive without importing OCP.

The capture runner computes the child timeout from elapsed preflight time, with a 55-second ceiling and a four-second post-child reserve inside the 60-second outer budget. It rejects a run when no child time remains and records an over-budget result after pin hashing or output tally. The STEP size reserve and exclusive 20 MiB persisted-output limit remain in force; collisions refuse a second attempt.

## Review limits

This is source acceptance only. No OCP import, provider import, CAD construction, STEP export/import, test, or runtime query was performed. Native topology validity, kernel adaptor classes, face fingerprint uniqueness at runtime, STEP roundtrip metrics, and elapsed time remain unverified. Global native wall thickness, full geometric equality, lip qualification, and physics remain `UNKNOWN`.

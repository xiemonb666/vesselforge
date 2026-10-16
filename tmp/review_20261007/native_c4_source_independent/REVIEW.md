# Independent source-only review

**Decision: NO-GO for the frozen source.** The main concern is representation-sensitive face classification, which is likely to stop the native role gate. A second shape-kind check may also misclassify the axis history result. This review did not execute the runner or construct geometry.

Scope: the native driver, input gate, one-shot runner, case JSON, source pins, and matched OCCT 7.9.3.1.1 stub/sign evidence. Review used static reads and hashes only; no OCP/provider/NumPy imports, CAD construction, STEP work, or tests.

## Pinned source identity

- `native_c4_ingress.py`: SHA-256 `b7f0550a0c0b60b557f8190e25c1b827a7a8b550fcc37b3cea0cc9cbc2d9fc04` (matches pin).
- `native_input_gate.py`: `45ee34ab7963c2d8886bd21be6844a0d171adb8257ee3665bd91a182aa4d44e4` (matches pin).
- `capture_once.py`: `7ea52a08da1900825fe950ee05bf8fadeecc5b98c1192d60e29366ddb639f4c4` (matches pin).
- `native_c4_ingress_case.json`: `38fd2a65f8769dab9c994ba0ad270fba0340475a1c9a2be33a867c676f26eb8f` (matches pin).
- `native_source_v1/source_pins.json`: current SHA-256 `330f6695491a9e9edd925bce02557251424ef8ac0d5a3689dfb1a6984409c1f0`; it has no externally enforced expected digest in the runner.
- Matched stub wheel SHA-256: `5ecba090df1ada12c558ff4a1b49c61d5155edc8cb3411067a785e3b43f4b359`; signature evidence SHA-256: `7240b899b1de8efb86e441a1a5bc58acfdda97606f551bcd44727b6b97a74dbe`.

## Blockers and high risks

1. **Likely native face-role gate failure — high confidence.** The driver builds the outer curve as `Geom_BSplineCurve` and the inner as `Geom_OffsetCurve` (lines 117–125), then revolves trimmed portions of those curves (171–180). `classify_face` requires `GeomAbs_Plane` for base/lip and `GeomAbs_Cylinder` for neck; `SurfaceOfRevolution` and `BSplineSurface` are sent through a side-only radial-maximum classifier (244–265). A revolved trimmed B-spline/offset span can keep a generic revolution or spline adaptor even when the trimmed geometry is flat or cylindrical. A base then has neither plane classification nor a 26/23 mm side radius; a neck can be labeled as a side. The first generated role check can therefore fail. Native roles should follow `Generated(source_edge)` history and be checked against the actual body-face inventory; imported roles need representation-independent unique metrics.

2. **Axis shape-kind test is not reliable — high risk.** The driver calls `TopoDS.Face(axis_generated.First())` and treats an exception as proof that the generated shape is not a face (294–300). The matched stub promises a `TopoDS_Face` return, not a checked cast. A typed downcast may not throw for an edge/vertex, so this test can report a face for a non-face axis result. Check the original shape's `ShapeType()` against `TopAbs_FACE` before any cast. The `Degenerated()` and `HasDegenerated()` method spellings are present in the matching `BRepPrimAPI` stub (lines 395 and 412), so those calls themselves are supported.

3. **Source freeze is not anchored to a reviewed pin-file digest — high risk.** `capture_once.preflight` compares source hashes to values read from `source_pins.json`, then records that same file's pre/post hash. It never compares the pin file to a separately fixed reviewed digest. Coordinated edits to a source and its pin record before `--root-go` can pass these checks. The current pin-file digest is recorded above for external review.

4. **The 60-second outer budget is not enforced — medium risk.** The case declares `outer_wall_seconds: 60`, while the runner only bounds the child process at 55 seconds (capture lines 24 and 82–91). Preflight, post-run hashing, output writes, and receipt fixed-point work occur outside that timeout and have no outer deadline.

5. **Duplicate JSON member — low risk.** `source_pins.json` repeats the `input_gate` key under `source_files`. Both values are currently identical, but JSON object member names should be unique and the Python loader silently keeps one value.

## Limits

This is a static source review, not a runtime diagnosis. No numeric native geometry or STEP result is asserted. Offset sign `+3 mm` with `V=+Y` is consistent with the pinned OCCT source correction (`T × V`); the case appropriately leaves native global wall thickness and geometry equality unknown. No GO is recommended until the role mapping and axis shape test are revised and reviewed.

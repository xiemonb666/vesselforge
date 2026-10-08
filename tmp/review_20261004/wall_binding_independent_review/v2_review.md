# Wall mesh binding v2 independent review

Review target: the v2 freeze and the static v1→v2 helper/test changes. Review date: 2026-10-04.

## Decision

Both v1 P2 findings are closed at the intended public API boundary in the frozen v2 source. The source changes are sufficient to proceed to the single tiny CAD fixture and the targeted pytest run. This is a static go-ahead for those checks, not evidence that the fixture binds or that tests pass; neither was executed here.

## P2 closure checks

- **Terminal-row aggregation bypass — closed for the public API.** `bind_stations_to_parent_mesh` is removed from `__all__` and no longer exists under that public name. The aggregator is `_aggregate_bound_stations`, excluded from `__all__`, and its output states `aggregation_scope: internal_station_status_aggregation_only_not_external_source_authentication` (`wall_mesh_binding.py:38–45, 483–531`). The only production top-level report builder accepts package paths, verifies the asset and its hashes, validates the STEP-bound wall reference, imports the exact STEP, rechecks face semantics/inventory, recomputes stations, then aggregates those rows (`:898–954`). A caller can deliberately import the underscore helper and get an aggregate `PASS` from a forged terminal row; the helper explicitly labels that output internal and unauthenticated. That private Python implementation detail is not a public qualification path.
- **Boolean/malformed tessellation policy — closed statically.** All six manifest/report values reject booleans and values outside `numbers.Real`, then require finite positive numbers; angular values must be below π; three linear and three angular sources must agree (`:657–704`). `BindingPolicy.__post_init__` independently checks its five fields for non-boolean real, finite, positive values, angle range, and finite derived thresholds (`:58–93`). The frozen target fixture therefore keeps its original limits: linear projection `0.0500101 mm`; normal-angle threshold `0.16 rad` (about `9.17°`). Serialization now names the normal-angle policy and states that the threshold is a local acceptance threshold, not a measured error or a global bound (`:115–135`).

## Public single-station helper

`bind_station_to_parent_mesh` remains in `__all__` and returns one row with `status: BOUND` plus measured point/normal residuals and projection details (`:325–480`). It documents that its station must already have been rechecked against the canonical STEP face (`:334–337`). The row has no top-level `PASS_MOTHER_STATION_BINDING` status and no qualification object; only `build_wall_mesh_binding` emits the source-bound aggregate qualification after the package/STEP validation path. A direct caller can violate the documented precondition and fabricate a local `BOUND` row, so consumers must treat this function as a low-level primitive. It does not provide or imply a higher-level global-wall, fragment, or physical qualification. This is not a remaining blocker for one tiny fixture plus target tests.

## Other static checks

- Mesh-content identity remains distinct from STEP/file-byte hashes. The hash canonicalizes coordinates as little-endian float64 and triangle/face-lineage indices as little-endian signed int64, with names, shapes, units, and frame in its header. Production validation checks finite vertices, triangle/index bounds, nondegenerate triangles, and lineage indices against the reimported B-rep face count. The asset contract and wall reference require millimeters and `right_handed_z_up`.
- The source-bound path hashes the actual canonical STEP bytes, checks the semantics/reference SHA slots, requires the recorded CadQuery/OCP versions, compares reimported face count/order and indexed inventory, recomputes face classifications, and requires the stored trimmed UV point to classify as `IN`. Recomputed face-oriented normals account for reversed B-rep face orientation.
- Station candidates are projected only to triangles whose lineage equals the station's exact B-rep face. Different-face triangles are only an ambiguity/clearly-nearer probe, never a fallback (`:409–437`). Inner and outer roles must match the corresponding canonical semantic face before projection (`:845–865`). The hollow-cylinder fixture uses radius 10 mm and bore radius 8 mm, yielding a declared 2 mm radial separation; a swapped wall label should fail the same-face projection and nearest-other-face checks. That last statement is a geometric inference from the fixture and policy, not a runtime observation.
- The batch result still requires a nonempty requested set and every station to be `BOUND`; qualification fields keep global minimum/global wall unverified, fragment lineage unavailable/unimplemented, and physics/physical qualification unknown (`:885–895` and aggregate record fields).
- The unchanged runner has one nested-wire solid extrusion, one STEP export, one import, and one `mesh_shape` call, writes only to a required absolute output path that does not already exist, and has no Boolean or solver calls. The runner hashes its generated STEP after export and passes the same canonical import into the shared internal verification path. It validates the generated package before binding. The file and call counts are verified statically; there is no runtime receipt yet because execution is frozen as `NOT_RUN`. No STEP bytes exist before the runner, so its actual STEP SHA can only be checked in the resulting output.

## Frozen version evidence

The v2 helper/tests hashes match the v2 freeze exactly. The preserved v1 source, tests, fixture, plan, runner, and original freeze each match the hashes recorded by `freeze_v2.json`. Shared dependencies, fixture, plan, and runner also match their v2 freeze values. Full pins are in `v2_pin.json`.

No source, test, fixture, runner, or freeze file was modified by this review. No Python import, pytest, CAD/STEP, ray query, solver, or Git operation was run.

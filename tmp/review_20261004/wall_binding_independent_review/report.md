# VesselForge wall-mesh binding independent static review

Review date: 2026-10-04 (Asia/Shanghai)

## Result

Static review found two P2 issues in exported/lower-level validation surfaces. The public `build_wall_mesh_binding` path contains important independent checks and is not shown to hit the terminal-row bypass, but it can accept boolean tessellation policy values as numeric values in a malformed package. Do not treat a `PASS_MOTHER_STATION_BINDING` from direct calls to the lower-level exported aggregator as trusted provenance until the first issue is closed.

No tests, Python imports, CAD/STEP, solver, Git, or other execution were performed. The freeze says the package is pending parent review. No `.step` or `.stp` asset currently exists under `vesselforge`, so there is no exported STEP byte stream whose actual SHA can be independently reported before the authorized one-shot runner executes.

## P2 findings

1. **The exported station aggregator trusts terminal `BOUND` rows.** In `wall_mesh_binding.py:38–45`, `bind_stations_to_parent_mesh` is part of `__all__`. At lines 461–462 it copies any input mapping already tagged `status: BOUND` without validating station identity, geometry, arrays, or the supplied parent mesh hash. Lines 467–475 then issue top-level `PASS_MOTHER_STATION_BINDING` if every supplied row has that tag. A single row like `{"station_id":"x","status":"BOUND"}` is enough to produce a top-level pass with malformed/empty arrays and a fabricated hash. The production builder (`build_wall_mesh_binding`, lines 859–896) first validates the asset and wall-reference, reimports the hash-verified STEP, then `_binding_from_loaded_inputs` creates its own station rows, so this finding concerns the separately exported lower-level API; it does not demonstrate a bypass through that high-level path. The existing aggregation tests at `test_wall_mesh_binding.py:174–212` cover real low-level bound rows and a mixed bound/unknown case, but not forged terminal rows. Keep aggregation private or require validated rows/provenance before allowing terminal states to pass through.

2. **Boolean tessellation values pass the high-level policy loader.** `_load_binding_policy` (`wall_mesh_binding.py:624–648`) calls `float(value)` before checking source types. Since `float(True) == 1.0`, three matching `true` values in the spec, tessellation block, and geometry report satisfy the finite/positive/equality checks. For a boolean linear target, the resulting linear projection limit is `1.0000201 mm` (`1.0 + 2×1e-5 + 1e-7`); for a boolean angular target it is clamped to 15 degrees. `schema.validate_asset` validates payload hashes and lineage but does not enforce strict numeric types for these provenance tessellation fields. This can make a malformed package's declaration much more permissive than the intended tessellation target. Reject booleans and non-numeric JSON types before conversion; validate `BindingPolicy` construction too if the exported low-level functions remain public.

## Independent checks that passed statically

- All frozen source and dependency SHA-256 values match `freeze.json` (listed below). This review did not change any source or fixture input.
- `parent_mesh_content_sha256` (`wall_mesh_binding.py:102–151`) separates mesh-content identity from file-byte hashes and the STEP SHA. It requires units `mm` and frame `right_handed_z_up`; normalizes vertices to contiguous little-endian float64 and face/lineage indices to contiguous little-endian signed int64, and includes names, canonical dtypes, and shapes in the hash header. The existing hash test checks endian and index-width normalization while preserving triangle winding (`test_wall_mesh_binding.py:49–58`).
- The production builder first invokes `validate_asset`, then hashes the manifest-selected canonical STEP, semantics, surface, lineage, and wall-reference payloads. The schema checks triangle shapes, vertex-index bounds, triangle-to-face lineage bounds, and consistency of semantic codes with that lineage. `validate_wall_reference` binds the reference to the actual STEP hash and enforces `mm`, `right_handed_z_up`, unique face/station IDs, face inventory coverage, and outer/inner radial-normal signs.
- For production input, the helper imports the exact hashed STEP once, requires the recorded CadQuery/OCP backend versions, checks the ordered face count and per-index inventory, then recomputes classification evidence in the imported shape. The station UV sample is independently classified against the trimmed source face and must be `IN`; its point and face-oriented normal are recomputed and compared to the frozen reference. Reversed faces have their normal reversed before comparison.
- Mesh projection is restricted to triangles whose `face_source_brep_index` equals the station's exact B-rep face. Other faces are used only for ambiguity/clearly-nearer rejection and are never a projection fallback (`wall_mesh_binding.py:390–445`). Outer/inner role is checked against the semantics row before binding (`:791–810`). The small hollow-cylinder reference has an analytic 2 mm radial separation and a 0.05 mm chord target, so a wrong-wall projection should fail the local projection/error or nearer-other-face checks; this remains an inference from the declared geometry and tolerance, not observed CAD output.
- The local station budgets are source-derived and measured: point/normal residuals are recomputed from the STEP face, then mesh projection distance and triangle normal angle are measured. With the frozen fixture values, the intended linear limit is `0.0500101 mm` (`0.05 + 2×5e-6 + 1e-7`), and the normal-angle limit is `0.16 rad` (about `9.17°`, twice `0.08 rad`). These support finite station-to-mesh correspondence only; they do not measure a global CAD-to-mesh error bound or certify all triangles.
- Mixed station statuses do not produce a pass in the high-level path: it requires a nonempty station set and `stations_bound == stations_requested` (`wall_mesh_binding.py:830–839`). Qualification fields keep fragment mapping unavailable/unimplemented, global minimum/global wall unverified, physics unassessed, and physical qualification unknown. Coverage is explicitly a finite station mapping fraction, not area coverage.
- The runner source statically contains one `cq.exporters.export`, one `cq.importers.importStep`, and one `mesh_shape(canonical, spec)` call (`run_hollow_cylinder_binding.py:104–139`), writes only to a required absolute output that must not exist (`:65–83`), uses one nested-wire extrusion, and contains no Boolean or solver call. It hashes the actual STEP after export and places that value in semantics, wall reference, manifest, and the independently computed binding input hashes (`:109`, `:125–134`, `:203`, `:219–225`). The output binding record carries real payload hashes and a separate canonical mesh-content hash. The execution budget and operation count are static source evidence only: no run was performed, and the runner does not emit runtime counters. Actual STEP SHA, actual operation counts, station residuals, and a generated receipt remain unavailable until the parent-authorized single execution.

## Freeze hashes

| File | Observed SHA-256 | Frozen expected SHA-256 | Result |
| --- | --- | --- | --- |
| `wall_mesh_binding.py` | `516b2a1d3c6956aadd83485beb0c272b2df56a3c30cb578040849312b7341e9d` | same | match |
| `test_wall_mesh_binding.py` | `db4f9c7abbb2e045086fbde5ba79fd04adccef58cea952926e436defcd48d1d7` | same | match |
| `fixture_input.json` | `706cefe1127c46f75889931eda68d963d08577638e0d962a6041e132226a323b` | same | match |
| `implementation_plan.md` | `b609dd97d1274cfe558aa4f811a0ed493e0622e1f240c65b18f4ad2edf7268a3` | same | match |
| `run_hollow_cylinder_binding.py` | `37a4f438c6eae507a6fc02ed1aaf59fbc625bd1dab7c536ef28bf2a4683925dc` | same | match |
| `asset.py` | `f9c11a60beed1d165431b8ea590c52db382b780479ad262fee1cc5a7be3274d0` | same | match |
| `geometry.py` | `0c48940d9ef22aabb068a2e7c6e89b4249a7e724d0ade1c8933a6c951e086047` | same | match |
| `schema.py` | `b58ae7b3bc5e09b699a36fe57fada12dd969759cf9991bf2749660d6cfbbdfe9` | same | match |
| `semantics.py` | `dfcc366d868c65313bcd5a43faf91d482b89848c2b15d4d9e66158ac291231af` | same | match |
| `wall_reference.py` | `a4f06671fc138fcf6912d9d075841fa958185b44a1d9c7e93b0b62e2fe29e8c8` | same | match |

`freeze.json` explicitly excludes its own hash. The review artifacts do not state that CAD execution, tests, or a source STEP hash were verified.

## Snapshot boundary and authorized follow-up

The review findings and hash table above apply only to the frozen v1 snapshot. Root has authorized the owner to revise the two P2 findings after this review. The original five owned artifacts remain preserved under `vesselforge/tmp/review_20261004/wall_mesh_binding/v1_frozen/`; I independently rehashed those copies and all five match `freeze_v1.json`. At the final scan, the shared working copies of `wall_mesh_binding.py` and `test_wall_mesh_binding.py` had changed to `a8e3094dbaef8f4545e76826c6ea440c0ae2b2a67fcc1335df5b0f7ce7d65b39` and `65b67107858a351e83edddd6fccd97dcb585b7f0afd7d2b94d076f0878e1a7e6`, respectively. Those authorized candidate bytes are pending a new freeze and separate review; this report makes no claim about them. The fixture and runner were not executed, and remain `NOT_RUN`.

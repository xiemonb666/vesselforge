# VesselForge pause and resume handover — 2026-10-16

## Pause boundary

The user explicitly paused development. The current authorized scope is GitHub delivery and documentation only. This note records the checkpoint; it does not resume feature work. While the pause remains in effect, do not add functionality, run a solver or new physical experiment, or treat an assigned experiment as permission to execute it. This documentation pass does not commit or push; the parent agent owns final review and any later delivery action.

The current developer entry point is the [VesselForge README](../../../README.md). The workspace continuation record is at `ShardForge/docs/continuation/20261016/STATUS.md`; it is outside the standalone VesselForge repository. Read it again when development resumes because experiment status may have changed.

## Current deliverables and boundaries

- The earlier v5 full-size mesh remains a diagnostic: all exterior source FIDs/roles were `UNKNOWN` on STEP import. The 16-face witness ancestry result belongs to v6 run05 and is not inherited from v5.
- VesselForge is a separately installable Python package. `pyproject.toml` declares Python 3.11–3.13, CadQuery 2.8.x and NumPy 2.x; `test` adds pytest. `.github/workflows/ci.yml` configures Windows and Ubuntu across Python 3.11, 3.12 and 3.13. The existing smoke CLI still generates one small swept-handle prototype; it is not the newer reference-profile catalog.
- A small set of source-guided geometry candidates has actual STEP, section, face-lineage and structural records. The daily Aberdeen v6 and Met 18.56.44 v2 candidates still include unmeasured local features as assumptions. They are candidates, not metrically verified reconstructions.
- The latest VF geometry mesh is [reference v6 run05](../../../experiments/continuation_20261016/reference_v6_tetra/run05/). Its [audit receipt](../../../experiments/continuation_20261016/reference_v6_tetra/run05/audit_receipt.json) records `PASS_WITNESS_ANCESTRY_TETRA_MESH`: 86,624 positive T4, 44,182 exterior triangles with all 16 source FIDs/roles, 356 interface triangles with two partition parents, and 0.240308% CAD-to-mesh volume error. The independent root readback is `ShardForge/experiments/continuation_20261016/root_v6_run05_readback.json`, outside the VF repository; it reports `ROOT_INDEPENDENT_V6_RUN05_GEOMETRY_READBACK_PASS`.
- Run05's two foot-fillet surface areas remain about -9.72% and -8.70% relative to their CAD source faces. The readback accepts geometry, serialization and face-source mapping only. It does not accept whole-feature fidelity, real-world shape accuracy, material calibration, solver evolution, fracture or training eligibility.
- One actual native zero-step preflight has been prepared for the unchanged run05 mesh under `pgfrag/experiments/continuation_20261016/reference_v6_preflight/inputs/`; `native_preflight/` output is not yet present. The v5 preflight and 100 ns zero-load benchmark are separate cost/numerical controls and cannot be presented as v6 evolution or fracture.
- Reference-driven material and blue-and-white appearance work supplies a technical foundation, not a finished specimen. The Met 50899 fired-photo projection is a partial appearance proxy, not original pigment recovery or a complete ornament. Source-specific material constants remain uncalibrated.
- The Apsida SHM 17946:0047 scan refinement v3 still has seven pinched vertex links and remains visual-reference-only. Its source record says CC BY-SA 4.0; preserve attribution/share-alike obligations for applicable derivatives. The downloaded/refined asset is in workspace-level `third_party/`, not necessarily in a GitHub clone. Other sources have different terms; consult the object-level catalogs in `docs/references/`.
- Complete qualified physical-package count remains zero. A small accepted numerical control, geometry-only run05 result, or source-preserving data plumbing does not change that count.

## Resume order

When the user resumes development, first read the current continuation status and inspect the current contents of each listed experiment path. These steps are the latest recorded priorities, not approval to execute them during the pause.

1. **Close the prepared run05 native zero-step preflight.** Work in the PGFrag `reference_v6_preflight` experiment. Confirm that the two physical-group name aliases preserve the source MSH's nodes, elements, tags, ordering and connectivity; bind the cost/stability receipt to exact mesh and input hashes. Treat placeholder material properties as uncalibrated. A successful initialization is not solver evolution or fracture.
2. **Complete review of the instrumented h/h2/h4 coupon campaign.** Use it to examine native onset, signed work/dissipation and event behavior before proposing a realistic loaded run. Keep h/8 as a separate decision after root review. The earlier negative dissipation was traced to a direction-reversal/opening event, while complete historical arrays for an independent force-law reconstruction remain unavailable.
3. **Finish the A12/PG mother-binding audit.** Bind the VF run05 exterior FIDs through the frozen face-lineage record and original mesh tags/connectivity, and retain interface faces as source-FID-null. This is geometry/data plumbing only; it does not create a physical-fragment package. The audit plan is in `ShardForge/docs/continuation/20261016/generic_binding_audit/REPORT.md` outside this repo.
4. **Resume specimen and appearance qualification as separate deliverables.** Refine and review each imported asset, fill measured-vs-assumed geometry and family parameter gaps, and develop complete source-grounded motifs and materials. Only after those are reviewed should a native fracture vertical slice be planned. Do not mark outputs training-eligible until the applicable source, material, solver, fracture and data gates all pass.

Keep the user requirement in scope across these steps: everyday and archaeological families both need real form references, several common and dedicated controls, meaningful motif content/layout, source-aware material and appropriate process constraints. Every imported asset must be refined and reviewed before final use. Track progress by accepted deliverables and explicit open gates, not a guessed overall percentage.

## Environment facts for the next developer

The inspected Windows environment is in the shared workspace's `third_party/vesselforge-runtime/venv`: Python 3.12.14, CadQuery 2.8.0, `cadquery-ocp` 7.9.3.1.1, NumPy 2.5.3 and pytest 8.4.2. The run05 receipt records Gmsh Python/API 4.15.2. VF's normal editable install is `python -m pip install -e ".[test]"`; Gmsh is an optional external SDK, loaded by the witness-mesh runner from the workspace root's `third_party/pgfrag-geometry-runtime/sdk/gmsh-4.15.2-Windows64-sdk/lib`. Its license is in the SDK's `share/doc/gmsh/LICENSE.txt`. The VF repository itself currently has no `LICENSE` file or project license declaration.

For this documentation checkpoint, only README/config/source-path inspection and a read-only import/version query were performed. No test suite, asset generator, Gmsh mesh build, native preflight, solver or physical experiment was run.


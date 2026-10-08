# v3 test-fixture-only patch

The approved v2 run collected 24 cases and produced 15 passes / 9 failures. Its raw stdout, stderr, JUnit XML, receipt, source snapshot and v2 test snapshot remain under `v2_run/` and `v2_frozen/`.

All nine failures came from the tests not meeting the existing helper's array-health preconditions or from an incomplete mock:

- Seven cases supplied fewer than four valid triangles. `_append_distant_triangles` now adds disjoint, nondegenerate +X triangles at x=100 mm, far outside the test probe regions. It appends triangle lineage in lockstep. The plane-pair fixture now has four triangles; one-triangle reversed-normal and two-triangle same-face-tie / outer-inner fixtures add only enough far triangles to reach four.
- The corrupt-lineage test keeps its intentionally invalid face id but now supplies one lineage id per triangle, so the case reaches the lineage-range guard.
- The trimmed-UV mock face now provides `.wrapped`; its mocked classifier returns ON or OUT before any real OCP face API is reached. This remains a mock-only early-return test.

No production source, source tolerance, mesh-health guard, analytic runner, or fixture input was changed. These repairs make the unit fixtures exercise their intended branches; they do not demonstrate that the production core changed or fixed the prior failures.

## Frozen v3 verification command

Run once with the approved runtime from the `vesselforge` working directory, `PYTHONPATH=src`, and `PYTHONDONTWRITEBYTECODE=1`:

```powershell
C:/Users/xiemo/Desktop/ShardForge/third_party/vesselforge-runtime/venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp <owned-v3-run>/pytest_tmp --junitxml <owned-v3-run>/junit.xml tests/test_wall_mesh_binding.py
```

Only if that one invocation exits 0, run the frozen hollow-cylinder runner once to a fresh `v3_run/cylinder_asset_run01` directory. Any failure stops the sequence; do not edit and rerun.

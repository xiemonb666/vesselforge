# v4 test-only patch

The v3 source, diff, freeze manifest, and failed run receipt are preserved in `v3_frozen/`; the full raw v3 outputs remain in `v3_run/`.

Only the reversed-parent-normal test assertion changed. The exercised implementation includes the selected candidate in `tied_local`, so the observed fail-closed reason is `SAME_FACE_TIE_NORMAL_DISAGREEMENT`, including for a single candidate. The v4 test now asserts all of the reviewed behavior: `UNKNOWN`, that exact reason, tied triangle index `[0]`, and measured angular disagreement approximately equal to pi. No production source, other test, fixture input, runner, tolerance, or geometry gate changed.

The test suite is approved for one v4 invocation. The analytic runner is approved once only if that invocation exits 0. Any failure stops the sequence without another edit or run.

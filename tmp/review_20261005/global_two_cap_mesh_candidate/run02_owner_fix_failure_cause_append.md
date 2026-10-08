# run02 owner-fix failure cause note

This is an addendum for the failed `run02_owner_fix` evidence. It does not edit or relabel `run02_owner_fix/run_receipt.json`, its parent receipt, or its saved NPZ.

The candidate had saved `candidate_arrays.npz` and returned from `run_focused_checks`; its next operation was `json.dumps(checks, ..., allow_nan=False)` in `candidate_owner_fix.py`. That serialization raised `TypeError: Object of type bool is not JSON serializable`. The outer and child receipts remain `CHILD_NONZERO_EXIT` / `UNKNOWN_OR_FAIL` with parent RC 1 and child RC 2.

Static producer tracing identifies the nested offending values as the two global-improvement gates in `focused_checks_owner_fix.py`: `checks.global_minimum_Q_improves_above_float_resolution` and `checks.global_maximum_aspect_improves_above_float_resolution`. Their tolerances were computed with `np.finfo(np.float64).eps`, so the tolerance scalars were `numpy.float64`; the comparisons produced `numpy.bool_` values, which NumPy names `bool` in its serialization error. A VesselForge-Python scalar-type microprobe confirmed the types of these exact expressions and confirmed `np.array_equal` returns a Python `bool`; the full checks, saved-NPZ readback, and renderer were not rerun for this diagnosis.

The isolated recovery checker materializes only these two fixed tolerance expressions as Python `float` and their comparison results as Python `bool` at the producer. This keeps the same binary64 gate values and boolean decisions. It does not use `default=str`, broad recursive conversion, relaxed tolerance, or nonfinite-value replacement; strict `allow_nan=False` remains in force.

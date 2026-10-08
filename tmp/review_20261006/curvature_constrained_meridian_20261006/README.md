# Review briefcase

This folder records the constrained-design source pins and is the only planned location for a future optimizer receipt. No run marker or optimizer result is present from this source-only review. The frozen minimum-jerk input remains at its original path and is unchanged.

The sole default design case is the explicit bowl apex correction to 72 mm plus the unchanged jar case in `vesselforge/experiments/curvature_constrained_meridian_20261006/design_cases.json`. A future optimizer call requires `root_ready=True`; the R9 pairwise height precheck runs before the lazy SciPy import. The actual old seed is corrected by exact RREF to a compatible Q0 and then used with an exact nullspace parameterization.

# Scope diff for main-agent review

This is an additive, source-only experiment folder. It changes no existing files.

| Artifact | Purpose | Execution state |
| --- | --- | --- |
| `refinement_prototype.py` | NumPy-only local conforming refinement, analytic field evaluation, finite geometry/normal probes, full topology checks, and flat-triangle rendering from saved candidate arrays | Authored; not imported or run |
| `candidate_cases.json` | Frozen input source pins, fixed analytic field, local `0.50 mm` and `0.25 mm` candidates, and proposed gates | Authored; candidates unmeasured |
| `CHECK_PLAN.md` | Source review boundaries, later run/check procedure, and claim limits | Authored; later command not run |

The read-only parent is `vesselforge/tmp/review_20261004/surface_ornament_route/run02/fixture_arrays.npz`, SHA-256 `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974`. The frozen source, checker, and parameter hashes are listed in `candidate_cases.json`. The parent arrays, prototype, checker, parameters, run directories, production modules, tests, and Git state have not been changed.

There is no measured refinement result in this folder. The source has not executed, no candidate mesh has been generated, and no CAD or native geometry operation has run.

"""Run the isolated two-parent owner lookup regression without mesh generation."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from focused_checks_owner_fix import owner_lookup_two_parent_toy_regression


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REPORT_PATH = (
    REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_two_cap_mesh_candidate"
    / "owner_fix_two_parent_toy_check.json"
)


def main() -> int:
    started = time.perf_counter()
    report = owner_lookup_two_parent_toy_regression()
    receipt = {
        "check_id": "global_two_cap_owner_fix_two_parent_toy_v1",
        "status": "PASS" if report["passed"] else "FAIL",
        "actual_argv": list(sys.argv),
        "python_executable": sys.executable,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "mesh_generation_invoked": False,
        "candidate_main_invoked": False,
        "result": report,
    }
    if REPORT_PATH.exists():
        raise FileExistsError(f"refusing to overwrite focused unit evidence: {REPORT_PATH}")
    with REPORT_PATH.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

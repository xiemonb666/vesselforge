from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind a preserved asset package once without rebuilding geometry.")
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--wall-reference", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    from vesselforge.wall_mesh_binding import build_wall_mesh_binding

    asset_root = args.asset_root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite binding report: {output}")
    record: dict[str, Any] = build_wall_mesh_binding(asset_root, args.wall_reference)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    qualification = record.get("qualification") if isinstance(record.get("qualification"), dict) else {}
    summary = {
        "status": record.get("status"),
        "reason": record.get("reason"),
        "station_coverage": record.get("coverage"),
        "global_wall_status": qualification.get("global_wall_status"),
        "physical_qualification_status": qualification.get("physical_qualification_status"),
        "report": str(output),
    }
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0 if record.get("status") == "PASS_MOTHER_STATION_BINDING" else 2


if __name__ == "__main__":
    raise SystemExit(main())
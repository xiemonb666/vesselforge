"""Portable single-attempt native BREP persistence spike.

This tracked copy was not executed for the 2026-10-03 candidate. The exact
historical invocation and its source snapshot are recorded separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
VOLUME_REFERENCE_MM3 = 26998.301999424355
BBOX_REFERENCE_MM = {
    "xmin_mm": -20.5000001,
    "ymin_mm": -20.5000001,
    "zmin_mm": -1e-7,
    "xmax_mm": 20.5000001,
    "ymax_mm": 20.5000001,
    "zmax_mm": 56.0000001,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_path_key(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return "external_runtime:" + path.resolve().as_posix()


def json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def shape_summary(shape: Any, bbox_fn: Any) -> dict[str, Any]:
    solids = shape.Solids()
    return {
        "valid": bool(shape.isValid()),
        "null": bool(shape.isNull()),
        "shape_type": str(shape.ShapeType()),
        "solid_count": len(solids),
        "shell_count": len(shape.Shells()),
        "volume_mm3": float(shape.Volume()),
        "bbox_mm": bbox_fn(shape),
        "solid_validity": [bool(solid.isValid()) for solid in solids],
        "solid_shell_counts": [len(solid.Shells()) for solid in solids],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new candidate output directory")
    args = parser.parse_args()

    repo_root = args.repository_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        print(json.dumps({"status": "REFUSED_NONEMPTY_OUTPUT", "reason": "--output must be a new or empty directory", "output": str(output)}, ensure_ascii=False))
        return 2
    geometry_dir = output / "geometry"
    brep_path = geometry_dir / "smooth_body.brep"
    marker_path = output / "native_brep_write_attempted.marker"
    report_path = output / "brep_candidate_report.json"
    receipt_path = output / "run_receipt.json"
    started = datetime.now(timezone.utc).isoformat()
    write_attempt_count = 0
    status = "FAIL"
    report: dict[str, Any] = {
        "experiment_id": "vf.native-brep-persistence-candidate/portable-source",
        "candidate_state": "BREP_CANDIDATE_PENDING",
        "candidate_decision": "NOT_PROMOTED; forge.asset.v1 remains canonical STEP",
        "canonical_contract": "Strict canonical STEP remains unchanged; this experiment does not create solid.step or change production APIs/schema.",
        "argv": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "repository_root": str(repo_root),
        "output": str(output),
        "started_utc": started,
        "serialization_policy": {
            "only_operation": "source_solid.exportBrep once, followed by cq.Shape.importBrep once",
            "maximum_body_write_attempts": 1,
            "step_write_or_read": False,
            "automatic_retry": False,
        },
    }

    try:
        if not (repo_root / "vesselforge" / "src" / "vesselforge" / "geometry.py").is_file():
            raise FileNotFoundError("--repository-root must name the ShardForge repository")
        sys.path.insert(0, str(repo_root / "vesselforge" / "src"))
        sys.path.insert(0, str(repo_root / "vesselforge"))
        sys.path.insert(0, str(HERE))
        import cadquery as cq
        import OCP

        import accepted_profile_definition as design
        from brep_persistence_helper import build_exact_profile_candidate
        from experiments.smooth_cad_spike import _shape_bbox

        source_paths = {
            "portable_builder": Path(__file__).resolve(),
            "accepted_profile_definition": HERE / "accepted_profile_definition.py",
            "persistence_helper": HERE / "brep_persistence_helper.py",
            "smooth_cad_spike": repo_root / "vesselforge" / "experiments" / "smooth_cad_spike.py",
            "vesselforge_geometry": repo_root / "vesselforge" / "src" / "vesselforge" / "geometry.py",
            "python_runtime": Path(sys.executable).resolve(),
        }
        report["source_sha256"] = {
            source_path_key(path, repo_root): sha256(path)
            for path in source_paths.values()
            if path.is_file()
        }
        report["runtime"] = {
            "python_executable": sys.executable,
            "cadquery_version": cq.__version__,
            "ocp_version": OCP.__version__,
            "linear_units": "mm",
        }
        source_solid, construction = build_exact_profile_candidate(design, 4.0)
        before = shape_summary(source_solid, _shape_bbox)
        before_bbox = before["bbox_mm"]
        bbox_matches = all(
            abs(float(before_bbox[key]) - expected) <= 0.01
            for key, expected in BBOX_REFERENCE_MM.items()
        )
        if not (
            before["valid"]
            and before["solid_count"] == 1
            and before["shell_count"] == 1
            and before["solid_validity"] == [True]
            and before["solid_shell_counts"] == [1]
            and bbox_matches
            and abs(before["volume_mm3"] - VOLUME_REFERENCE_MM3) <= 0.01
        ):
            raise ValueError("source geometry differs from the accepted one-valid-solid BREP profile")

        geometry_dir.mkdir(parents=True, exist_ok=True)
        with marker_path.open("x", encoding="utf-8") as marker:
            marker.write("One body exportBrep/importBrep sequence authorized; do not repeat.\n")
        report["serialization_policy"]["body_write_attempted"] = True
        report["serialization_policy"]["body_write_attempt_count"] = 1
        write_attempt_count = 1

        writer_returned_true = bool(source_solid.exportBrep(str(brep_path)))
        if not writer_returned_true or not brep_path.is_file():
            raise RuntimeError("the sole BREP export call did not produce a body file")
        restored = cq.Shape.importBrep(str(brep_path))
        after = shape_summary(restored, _shape_bbox)
        bbox_delta = {
            key: float(after["bbox_mm"][key] - before_bbox[key])
            for key in BBOX_REFERENCE_MM
        }
        roundtrip_ok = bool(
            restored.isValid()
            and after["solid_count"] == 1
            and after["shell_count"] == 1
            and after["solid_validity"] == [True]
            and after["solid_shell_counts"] == [1]
            and abs(after["volume_mm3"] - before["volume_mm3"]) <= 0.01
            and max(abs(value) for value in bbox_delta.values()) <= 0.01
        )
        report.update(
            {
                "construction": construction,
                "source_solid": before,
                "reloaded_solid": after,
                "native_BREP_roundtrip": {
                    "one_valid_solid_shell_preserved": roundtrip_ok,
                    "source_volume_mm3": float(before["volume_mm3"]),
                    "volume_delta_mm3": float(after["volume_mm3"] - before["volume_mm3"]),
                    "bbox_bound_deltas_mm": bbox_delta,
                    "writer_returned_true": writer_returned_true,
                    "body_brep_sha256": sha256(brep_path),
                },
                "artifacts": {
                    "body_brep": "geometry/smooth_body.brep",
                    "body_brep_bytes": brep_path.stat().st_size,
                    "body_brep_sha256": sha256(brep_path),
                },
                "artifact": {
                    "path": "geometry/smooth_body.brep",
                    "bytes": brep_path.stat().st_size,
                    "sha256": sha256(brep_path),
                },
                "status": "BREP_PERSISTENCE_PRESERVED_QA_PENDING" if roundtrip_ok else "FAIL_BREP_ROUNDTRIP",
                "candidate_state": "BREP_PERSISTENCE_PRESERVED_QA_PENDING" if roundtrip_ok else "FAIL_BREP_ROUNDTRIP",
                "candidate_decision": "NOT_PROMOTED; native BREP persistence check only; mesh and section QA remain pending; forge.asset.v1 remains canonical STEP",
                "checks": {
                    "source_profile_native_degree5_C2": bool(
                        all(edge["degree"] == 5 and edge["is_C2"] for edge in construction["source_meridian"]["native_edges"])
                        and construction["source_meridian"]["internal_join"]["C2_join"]
                    ),
                    "source_profile_sampled_curvature_radius_at_least_5mm": bool(
                        construction["source_meridian"]["sampled_curvature"]["minimum_sampled_radius_mm"] >= 5.0
                        and construction["source_meridian"]["sampled_curvature"]["samples_below_threshold"] == 0
                    ),
                    "body_native_BREP_one_valid_solid_shell_preserved": roundtrip_ok,
                    "body_native_BREP_volume_bbox_preserved": roundtrip_ok,
                },
            }
        )
        status = report["status"]
    except Exception as exc:
        report["status"] = "FAIL"
        report["candidate_state"] = "FAIL"
        report["candidate_decision"] = "NOT_PROMOTED; no retry is allowed after a BREP write attempt."
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        status = "FAIL"
    finally:
        output.mkdir(parents=True, exist_ok=True)
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["serialization_policy"]["body_write_attempt_count"] = write_attempt_count
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8")
        receipt = {
            "argv": report["argv"],
            "working_directory": str(Path.cwd()),
            "started_utc": started,
            "finished_utc": report["finished_utc"],
            "exit_code": 0 if status == "BREP_PERSISTENCE_PRESERVED_QA_PENDING" else 2,
            "status": status,
            "report": "brep_candidate_report.json",
            "brep_write_attempt_count": write_attempt_count,
            "output_sha256": {
                path.relative_to(output).as_posix(): sha256(path)
                for path in (brep_path, marker_path, report_path)
                if path.is_file()
            },
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"status": status, "report": str(report_path), "brep_write_attempt_count": write_attempt_count}, ensure_ascii=False))
    return 0 if status == "BREP_PERSISTENCE_PRESERVED_QA_PENDING" else 2


if __name__ == "__main__":
    raise SystemExit(main())

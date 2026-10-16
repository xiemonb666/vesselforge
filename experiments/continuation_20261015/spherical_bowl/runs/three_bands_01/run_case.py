from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
from typing import Any


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_inventory(source_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.suffix != ".py":
            continue
        data = path.read_bytes()
        rows.append({
            "path": path.relative_to(source_root.parent.parent).as_posix(),
            "bytes": len(data),
            "sha256": _sha256(data),
        })
    return rows


def _copy_sources(source_root: Path, snapshot_root: Path) -> list[dict[str, Any]]:
    inventory = _source_inventory(source_root)
    for row in inventory:
        relative = Path(row["path"])
        source = source_root.parent.parent / relative
        target = snapshot_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied = target.read_bytes()
        if len(copied) != row["bytes"] or _sha256(copied) != row["sha256"]:
            raise RuntimeError(f"source snapshot mismatch: {relative}")
    return inventory


def _directory_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def main() -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description="Generate and independently validate one spherical-bowl asset case.")
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]
    case_path = args.case.resolve()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory must be created as a new directory before launch: {run_dir}")
    if any(run_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty run directory: {run_dir}")

    case_bytes = case_path.read_bytes()
    case = json.loads(case_bytes.decode("utf-8"))
    case_copy = run_dir / "case.json"
    case_copy.write_bytes(case_bytes)
    if case_copy.read_bytes() != case_bytes:
        raise RuntimeError("case bytes changed while being copied")

    argv = [sys.executable, str(script_path), *sys.argv[1:]]
    _write_json(run_dir / "argv.json", {"argv": argv, "cwd": str(Path.cwd())})
    shutil.copyfile(script_path, run_dir / "run_case.py")
    if _sha256((run_dir / "run_case.py").read_bytes()) != _sha256(script_path.read_bytes()):
        raise RuntimeError("runner source snapshot mismatch")

    source_root = repo_root / "src" / "vesselforge"
    inventory = _copy_sources(source_root, run_dir / "source_snapshot")
    inventory_bytes = _json_bytes(inventory)
    _write_json(run_dir / "source_inventory.json", inventory)
    source_inventory_sha256 = _sha256(inventory_bytes)
    runner_sha256 = _sha256(script_path.read_bytes())
    case_sha256 = _sha256(case_bytes)

    output = (repo_root / Path(case["output_relative"])).resolve()
    if repo_root not in output.parents:
        raise ValueError("case output must remain inside the VesselForge repository")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing asset output: {output}")
    if case["run_bounds"]["wall_seconds_max"] != 60 or case["run_bounds"]["package_bytes_max"] != 33_554_432:
        raise ValueError("case limits differ from the authorized per-run limits")

    receipt: dict[str, Any] = {
        "schema": "vf.spherical_bowl_execution_receipt.v1",
        "case_id": case.get("case_id"),
        "status": "RUNNING",
        "case_sha256": case_sha256,
        "runner_sha256": runner_sha256,
        "source_inventory_sha256": source_inventory_sha256,
        "source_file_count": len(inventory),
        "argv_sha256": _sha256((run_dir / "argv.json").read_bytes()),
        "output_directory": str(output),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "limits": case["run_bounds"],
    }
    try:
        sys.path.insert(0, str(repo_root / "src"))
        import cadquery as cq
        import OCP
        from vesselforge.spherical_bowl import BowlSpec, create_spherical_bowl_asset_package
        from vesselforge.schema import validate_asset

        spec = BowlSpec(**case["spec"])
        package_result = create_spherical_bowl_asset_package(
            output,
            pattern=case["pattern"],
            seed=case["seed"],
            spec=spec,
        )
        validation = validate_asset(output)
        manifest_path = output / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        mechanics = manifest["material"]["mechanics"]
        if mechanics != case["expected_mechanics"]:
            raise ValueError(f"source mechanics do not match frozen case values: {mechanics}")

        # Independent check: derive the exact hemispherical shell volume here,
        # then compare it with volume read back from the exported canonical STEP.
        ro = float(case["spec"]["outer_radius_mm"])
        ri = float(case["spec"]["inner_radius_mm"])
        analytic_volume_mm3 = (2.0 * math.pi / 3.0) * (ro**3 - ri**3)
        canonical = cq.importers.importStep(str(output / manifest["geometry"]["solid_step"])).val()
        step_volume_mm3 = float(canonical.Volume())
        volume_relative_error = abs(step_volume_mm3 - analytic_volume_mm3) / analytic_volume_mm3
        size_bytes = _directory_bytes(output)
        elapsed_seconds = time.monotonic() - started
        checks = {
            "legacy_validator_contract_pass": validation.get("contract_status") == "PASS",
            "legacy_validator_geometry_pass": validation.get("geometry_status") == "PASS",
            "builder_return_validator_contract_pass": package_result["validation"].get("contract_status") == "PASS",
            "analytic_step_volume_relative_error_below_1e_8": volume_relative_error < 1e-8,
            "one_valid_step_solid_and_closed_shell": bool(canonical.isValid() and len(canonical.Solids()) == 1 and len(canonical.Shells()) == 1 and canonical.Shells()[0].Closed()),
            "expected_mechanics_preserved": mechanics == case["expected_mechanics"],
            "output_package_below_32_mib": size_bytes <= case["run_bounds"]["package_bytes_max"],
            "run_completed_within_60_seconds": elapsed_seconds <= case["run_bounds"]["wall_seconds_max"],
        }
        receipt.update({
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "elapsed_seconds": elapsed_seconds,
            "package_bytes": size_bytes,
            "manifest_sha256": _sha256(manifest_bytes),
            "package_validation": validation,
            "independent_analytic_volume": {
                "formula": "2*pi/3*(outer_radius_mm^3-inner_radius_mm^3)",
                "outer_radius_mm": ro,
                "inner_radius_mm": ri,
                "analytic_volume_mm3": analytic_volume_mm3,
                "canonical_step_volume_mm3": step_volume_mm3,
                "relative_error": volume_relative_error,
            },
            "backend": {
                "python": sys.version,
                "cadquery_version": str(cq.__version__),
                "ocp_module_version": str(getattr(OCP, "__version__", "unknown")),
            },
            "package_files": [
                {"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256(path.read_bytes())}
                for path in sorted(output.rglob("*")) if path.is_file()
            ],
        })
        return 0 if receipt["status"] == "PASS" else 1
    except Exception as exc:
        receipt.update({
            "status": "FAIL",
            "elapsed_seconds": time.monotonic() - started,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        return 1
    finally:
        receipt["source_inventory_after_sha256"] = _sha256(_json_bytes(_source_inventory(source_root)))
        receipt["source_unchanged_during_run"] = receipt["source_inventory_after_sha256"] == source_inventory_sha256
        if receipt.get("status") == "PASS" and not receipt["source_unchanged_during_run"]:
            receipt["status"] = "FAIL"
        receipt["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_json(run_dir / "receipt.json", receipt)


if __name__ == "__main__":
    raise SystemExit(main())

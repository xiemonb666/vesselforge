"""Draft, fail-closed copied-asset migration for the preserved v4 wall fixture.

Default invocation prints the reviewed plan and does not touch the source package,
import CAD libraries, or create output.  The migration requires an explicit
``--execute`` after review.  It copies only manifest-listed files by explicit path,
recomputes the B-rep face inventory with the versioned geometry-only policy, then
calls the public read-only wall-binding API.  It never rebuilds, meshes, or exports
geometry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
VF_ROOT = SCRIPT_DIR.parents[2]
REPO_ROOT = VF_ROOT.parent
SOURCE_REL = Path("tmp/review_20261004/wall_mesh_binding/v4_run/cylinder_asset_run01")
SOURCE_ASSET = VF_ROOT / SOURCE_REL
DEST_ASSET = SCRIPT_DIR / "migration_copy" / "cylinder_asset_run01"
RESULT_PATH = SCRIPT_DIR / "migration_binding_result.json"
SOURCE_MANIFEST_SHA256 = "31a6d35ff2ae28780a5c9ec8ca330398039f509ffc69c0f66522e7e0a4ac4d0f"

EXPECTED_PAYLOADS: dict[str, dict[str, Any]] = {
    "fields/surface_fields.npz": {
        "bytes": 5320,
        "sha256": "3526d706c83a37667edefe965c9f9c92d550bdfbd090a88b5b10539a98e0835d",
    },
    "geometry/mesh_lineage.npz": {
        "bytes": 280,
        "sha256": "3c68077ea376e26dc0710068d9deab22423f07f1e04386f1d0ec51271afcad8d",
    },
    "geometry/solid.step": {
        "bytes": 9412,
        "sha256": "5c68bbc29b2b0bc684cc6c551c2769872c4c490d588b9a3ea2cbb98e7f74135e",
    },
    "geometry/surface.npz": {
        "bytes": 9722,
        "sha256": "79e05b8470a9f327cb9c015e6fea873a286e16d2a3c88d9756be0d9d9fcd3117",
    },
    "metadata/face_semantics.json": {
        "bytes": 5709,
        "sha256": "a5c6a26ba37f02dae51c2a8083a38b3548a457fe8555452a3959df8a7101b848",
    },
    "metadata/wall_reference.json": {
        "bytes": 4717,
        "sha256": "a7033bc9f3742677931b6be142d5ed42fd871bc6cbb1f08a12682288e6d06b76",
    },
    "validation/geometry.json": {
        "bytes": 320,
        "sha256": "b3972c50aa99d10f104471fd69280128a90980e15a8dcbb290be171beac6bd61",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                        allow_nan=False) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _file_record(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def _verify_payloads(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative, expected in EXPECTED_PAYLOADS.items():
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError(f"unsafe fixed payload path: {relative}")
        path = root.joinpath(*pure.parts)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"expected regular non-symlink payload: {relative}")
        actual = _file_record(path)
        if actual != expected:
            raise ValueError(f"payload hash/size changed: {relative}: {actual}")
        result[relative] = actual
    return result


def _verify_source() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not SOURCE_ASSET.is_dir() or SOURCE_ASSET.is_symlink():
        raise FileNotFoundError(f"source asset directory missing/unsafe: {SOURCE_ASSET}")
    manifest_path = SOURCE_ASSET / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise FileNotFoundError("source manifest missing/unsafe")
    manifest_sha = _sha256(manifest_path)
    if manifest_sha != SOURCE_MANIFEST_SHA256:
        raise ValueError(f"source manifest SHA changed: {manifest_sha}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != "forge.asset.v1":
        raise ValueError("source asset schema changed")
    declared = manifest.get("files")
    if not isinstance(declared, dict) or declared != EXPECTED_PAYLOADS:
        raise ValueError("source manifest file inventory differs from frozen payload set")
    spec = manifest.get("provenance", {}).get("spec", {})
    if not isinstance(spec, dict):
        raise ValueError("source provenance.spec is invalid")
    if "brep_face_bounds_policy" in spec:
        raise ValueError("source unexpectedly declares a B-rep bounds policy")
    actual_payloads = _verify_payloads(SOURCE_ASSET)
    return manifest, actual_payloads


def _copy_explicit_payloads() -> None:
    if DEST_ASSET.exists():
        raise FileExistsError(f"refusing to overwrite migration destination: {DEST_ASSET}")
    if DEST_ASSET.parent.exists():
        raise FileExistsError(f"refusing to reuse existing migration parent: {DEST_ASSET.parent}")
    DEST_ASSET.parent.mkdir(parents=False, exist_ok=False)
    DEST_ASSET.mkdir(parents=False, exist_ok=False)
    for relative in EXPECTED_PAYLOADS:
        pure = PurePosixPath(relative)
        source = SOURCE_ASSET.joinpath(*pure.parts)
        target = DEST_ASSET.joinpath(*pure.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(SOURCE_ASSET / "manifest.json", DEST_ASSET / "manifest.json")


def _face_inventory(shape: Any, bounds_for: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, face in enumerate(shape.Faces()):
        center = [float(value) for value in face.Center().toTuple()]
        area = float(face.Area())
        bounds = list(bounds_for(face))
        if len(center) != 3 or not all(math.isfinite(value) for value in (*center, area, *bounds)):
            raise ValueError(f"face inventory contains non-finite geometry at index {index}")
        rows.append({
            "index_zero_based": index,
            "geom_type": str(face.geomType()),
            "center_mm": center,
            "area_mm2": area,
            "bbox_mm": bounds,
        })
    return rows


def _execute() -> int:
    source_manifest, source_payload_hashes = _verify_source()
    if RESULT_PATH.exists():
        raise FileExistsError(f"refusing to overwrite migration result: {RESULT_PATH}")

    # Import only after all immutable source checks and output-path checks pass.
    sys.path.insert(0, str(VF_ROOT / "src"))
    import cadquery as cq

    from vesselforge.brep_identity import (
        BREP_FACE_BOUNDS_POLICY_ID,
        brep_bounds_mm,
        brep_face_bounds_policy_record,
    )
    from vesselforge.schema import validate_asset
    from vesselforge.wall_mesh_binding import build_wall_mesh_binding

    _copy_explicit_payloads()
    copied_before = _verify_payloads(DEST_ASSET)
    if copied_before != source_payload_hashes:
        raise ValueError("copied payload bytes differ from the read-only source")

    step_path = DEST_ASSET / "geometry" / "solid.step"
    shape = cq.importers.importStep(str(step_path)).val()
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise ValueError("copied STEP import is not one valid solid")

    manifest = _read_json(DEST_ASSET / "manifest.json")
    source_spec = source_manifest["provenance"]["spec"]
    semantics = _read_json(DEST_ASSET / "metadata" / "face_semantics.json")
    expected_faces = int(semantics["canonical_step_face_count"])
    if len(shape.Faces()) != expected_faces:
        raise ValueError("copied STEP face count differs from canonical semantics")
    if len(source_spec["brep_face_inventory"]) != expected_faces:
        raise ValueError("source B-rep inventory face count differs from semantics")

    inventory = _face_inventory(shape, brep_bounds_mm)
    policy = brep_face_bounds_policy_record()
    provenance = manifest["provenance"]
    if "identity_migration" in provenance:
        raise ValueError("source copy already contains an identity migration record")
    provenance_spec = provenance["spec"]
    provenance_spec["brep_face_bounds_policy"] = policy
    provenance_spec["brep_face_inventory"] = inventory
    provenance["identity_migration"] = {
        "schema": "vf.asset-identity-migration.v1",
        "migration_id": "vf-mig-20261005-v4-brep-bounds-policy-v1",
        "operation": "copied_asset_recompute_brep_identity_then_wall_mesh_bind",
        "source_asset_relative_path": SOURCE_REL.as_posix(),
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_canonical_step_sha256": source_manifest["files"]["geometry/solid.step"]["sha256"],
        "source_bounds_policy_present": False,
        "source_producer": {
            "name": provenance.get("producer"),
            "version": provenance.get("version"),
            "backend": provenance.get("backend"),
            "backend_version": provenance.get("backend_version"),
        },
        "source_payload_files": source_payload_hashes,
        "target_bounds_policy": policy,
        "target_bounds_policy_id": BREP_FACE_BOUNDS_POLICY_ID,
        "recomputed_fields": [
            "provenance.spec.brep_face_bounds_policy",
            "provenance.spec.brep_face_inventory[*].index_zero_based",
            "provenance.spec.brep_face_inventory[*].geom_type",
            "provenance.spec.brep_face_inventory[*].center_mm",
            "provenance.spec.brep_face_inventory[*].area_mm2",
            "provenance.spec.brep_face_inventory[*].bbox_mm",
        ],
        "preserved_payload_sha256": source_payload_hashes,
        "step_exported": False,
        "mesh_generated": False,
        "original_v4_run_rewritten_or_requalified": False,
        "classification": "migration_copy; not retroactive success of original v4 run",
        "performed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = DEST_ASSET / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))

    asset_validation = validate_asset(DEST_ASSET)
    if asset_validation.get("contract_status") != "PASS" or asset_validation.get("geometry_status") != "PASS":
        raise ValueError(f"migrated copy fails forge.asset.v1 validation: {asset_validation}")
    payloads_after = _verify_payloads(DEST_ASSET)
    if payloads_after != source_payload_hashes:
        raise ValueError("migration changed one or more original payload bytes")

    binding = build_wall_mesh_binding(DEST_ASSET, "metadata/wall_reference.json")
    result = {
        "schema": "vf.asset-identity-migration-result.v1",
        "status": binding.get("status"),
        "reason": binding.get("reason"),
        "source_asset_relative_path": SOURCE_REL.as_posix(),
        "destination_asset_relative_path": DEST_ASSET.relative_to(VF_ROOT).as_posix(),
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "destination_manifest_sha256": _sha256(manifest_path),
        "source_payloads_sha256": source_payload_hashes,
        "destination_payloads_sha256": payloads_after,
        "payload_bytes_preserved": payloads_after == source_payload_hashes,
        "step_sha256": _sha256(step_path),
        "bounds_policy": policy,
        "asset_validation": asset_validation,
        "binding_result": binding,
        "expected_step_imports": 2,
        "step_exports": 0,
        "mesh_calls": 0,
        "native_geometry_rebuilds": 0,
        "original_source_modified": False,
        "original_v4_run_requalified": False,
        "result_written_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    RESULT_PATH.write_bytes(_json_bytes(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0 if binding.get("status") == "PASS_MOTHER_STATION_BINDING" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="perform the explicit copied-asset migration and read-only binding")
    args = parser.parse_args()
    plan = {
        "status": "PLAN_ONLY" if not args.execute else "EXECUTE_REQUESTED",
        "source_asset": SOURCE_ASSET.as_posix(),
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "destination_asset": DEST_ASSET.as_posix(),
        "result_path": RESULT_PATH.as_posix(),
        "payload_file_count": len(EXPECTED_PAYLOADS),
        "operation": "explicit file copies; one STEP import for inventory; public binding reimports STEP once",
        "step_exports": 0,
        "mesh_calls": 0,
        "native_geometry_rebuilds": 0,
        "source_write": False,
        "requires_root_review_before_execute": True,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return _execute()


if __name__ == "__main__":
    raise SystemExit(main())

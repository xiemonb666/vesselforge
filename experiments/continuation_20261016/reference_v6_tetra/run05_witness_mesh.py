from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VF = ROOT / "vesselforge"
ASSET = VF / "experiments/continuation_20261015/reference_forms/outputs/daily_aberdeen_108x53_v6_final"
V15 = VF / "experiments/continuation_20261015/named_step/daily_witness_probe_20261016_v15"
BODY_STEP = V15 / "daily_native_named.step"
WITNESS_MANIFEST = V15 / "witness_manifest.json"
IDENTITY = V15 / "native_face_identity.json"
V15_RECEIPT = V15 / "receipt.json"
OUTPUT = HERE / "run05" / "partition_output"
RUN_DIR = OUTPUT.parent
MESH_SIZE_M = 0.0022
TETRAHEDRA_PER_VOLUME_CELL = 20.0
BOUNDARY_SIZE_BY_ROLE_M = {"rim": 0.0005}
CAD_PARTITION_VOLUME_RELATIVE_TOLERANCE = 1e-6
GMSH_LIB = ROOT / "third_party/pgfrag-geometry-runtime/sdk/gmsh-4.15.2-Windows64-sdk/lib"
PYTHON = ROOT / "third_party/vesselforge-runtime/venv/Scripts/python.exe"

sys.path.insert(0, str(VF / "src"))

from vesselforge.named_step import sha256_file  # noqa: E402
from vesselforge.revolved_profile import (  # noqa: E402
    MeridianSection,
    MeridianSegment,
    build_revolved_solid,
    meridian_volume_mm3,
)
from vesselforge.step_partition import ResourceCaps, partition_step_at_x  # noqa: E402
from vesselforge.tetra_audit import audit_tetra_mesh  # noqa: E402


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _section_from_json(path: Path) -> MeridianSection:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != "vf.meridian_section.v1":
        raise ValueError("source section schema is unsupported")
    section = MeridianSection(
        segments=tuple(
            MeridianSegment(
                role=str(row["role"]),
                kind=str(row["curve"]),
                points=tuple(tuple(float(v) for v in point) for point in row["points_rz_mm"]),
            )
            for row in raw["segments"]
        ),
        name=str(raw["name"]),
    )
    section.validate()
    return section


def _section_area_mm2(section: MeridianSection, order: int) -> float:
    nodes, weights = np.polynomial.legendre.leggauss(order)
    integral = 0.0
    for segment in section.segments:
        for node, weight in zip(nodes, weights, strict=True):
            parameter = 0.5 * (float(node) + 1.0)
            radius = float(segment.point(parameter)[0])
            dz = float(segment.derivative(parameter)[1])
            integral += 0.5 * float(weight) * radius * dz
    area = abs(integral)
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError("independent meridian section area is invalid")
    return area


def _identity_map(records: dict[str, Any], label: str) -> dict[tuple[str, tuple[int, ...]], int]:
    result: dict[tuple[str, tuple[int, ...]], int] = {}
    for key, row in records.items():
        identity = (str(row["role"]), tuple(sorted(int(value) for value in row["source_segment_indices"])))
        if not identity[1] or identity in result:
            raise ValueError(f"{label} lineage has missing or duplicate source-segment identity {identity}")
        result[identity] = int(key)
    return result


def _metrics_cq(shape: Any) -> dict[str, Any]:
    box = shape.BoundingBox()
    return {
        "volume_mm3": float(shape.Volume()),
        "bounds_mm": [
            float(box.xmin), float(box.ymin), float(box.zmin),
            float(box.xmax), float(box.ymax), float(box.zmax),
        ],
        "valid": bool(shape.isValid()),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
    }


def _relative_error(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def _load_gmsh() -> Any:
    if not GMSH_LIB.is_dir():
        raise FileNotFoundError(GMSH_LIB)
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(GMSH_LIB))
    sys.path.insert(0, str(GMSH_LIB))
    import gmsh  # type: ignore[import-not-found]

    return gmsh


def _source_identity_preflight() -> dict[str, Any]:
    import cadquery as cq

    section_path = ASSET / "geometry/section.json"
    original_step = ASSET / "geometry/solid.step"
    lineage_path = ASSET / "geometry/face_lineage.json"
    geometry_report_path = ASSET / "geometry_report.json"
    identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    geometry = json.loads(geometry_report_path.read_text(encoding="utf-8"))
    receipt = json.loads(V15_RECEIPT.read_text(encoding="utf-8"))
    hashes = {
        "section.json": sha256_file(section_path),
        "solid.step": sha256_file(original_step),
        "face_lineage.json": sha256_file(lineage_path),
        "geometry_report.json": sha256_file(geometry_report_path),
        "daily_native_named.step": sha256_file(BODY_STEP),
        "witness_manifest.json": sha256_file(WITNESS_MANIFEST),
        "native_face_identity.json": sha256_file(IDENTITY),
        "v15_receipt.json": sha256_file(V15_RECEIPT),
        "label_import_receipt.json": sha256_file(V15 / "label_import_receipt.json"),
    }
    expected_source_hashes = {
        "solid.step": "1cd34bc5f5b3cf8b6b937afeb7345b982c9de01165f0d570ca11b83f3ea31c0e",
        "face_lineage.json": "9e6c789989cb0f5f42ed9c37f0264bc02899a9c29f571254938a4781640bcfd2",
    }
    for name, expected in expected_source_hashes.items():
        if hashes[name].lower() != expected:
            raise ValueError(f"frozen upstream {name} hash differs from the v15 source chain")
    for name, actual in hashes.items():
        if name in identity.get("source_hashes", {}) and identity["source_hashes"][name].lower() != actual.lower():
            raise ValueError(f"v15 native-face identity source hash does not match current {name}")
    if receipt.get("native_body_step_sha256", "").lower() != hashes["daily_native_named.step"].lower():
        raise ValueError("v15 receipt does not bind the supplied canonical named STEP body")
    if receipt.get("native_face_witness_manifest_sha256", "").lower() != hashes["witness_manifest.json"].lower():
        raise ValueError("v15 receipt does not bind the supplied witness manifest")
    if receipt.get("native_face_identity_sha256", "").lower() != hashes["native_face_identity.json"].lower():
        raise ValueError("v15 receipt does not bind its native-face identity table")
    if receipt.get("source_hashes", {}).get("solid.step", "").lower() != hashes["solid.step"].lower():
        raise ValueError("v15 receipt does not bind the source vessel STEP")
    if receipt.get("source_hashes", {}).get("face_lineage.json", "").lower() != hashes["face_lineage.json"].lower():
        raise ValueError("v15 receipt does not bind the source face-lineage JSON")

    section = _section_from_json(section_path)
    rebuilt_shape, rebuilt_lineage = build_revolved_solid(section)
    original_shape = cq.importers.importStep(str(original_step)).val()
    rebuilt = _metrics_cq(rebuilt_shape)
    original = _metrics_cq(original_shape)
    if not rebuilt["valid"] or rebuilt["solid_count"] != 1 or not original["valid"] or original["solid_count"] != 1:
        raise ValueError("rebuilt or original source STEP is not one valid solid")
    volume_error = _relative_error(rebuilt["volume_mm3"], original["volume_mm3"])
    span = max(original["bounds_mm"][i + 3] - original["bounds_mm"][i] for i in range(3))
    bounds_error = max(abs(a - b) for a, b in zip(rebuilt["bounds_mm"], original["bounds_mm"], strict=True)) / span
    if volume_error > 1e-8 or bounds_error > 2e-7:
        raise ValueError(f"rebuilt source solid differs from upstream STEP: volume={volume_error}, bounds={bounds_error}")
    geometry_volume = float(geometry["measurements"]["solid_volume_mm3"])
    if _relative_error(geometry_volume, rebuilt["volume_mm3"]) > 1e-8:
        raise ValueError("rebuilt native volume differs from the frozen geometry report")
    if identity.get("source_hashes") != {
        name: hashes[name]
        for name in ("section.json", "solid.step", "face_lineage.json", "geometry_report.json")
    }:
        raise ValueError("v15 identity does not retain the exact source section, STEP, lineage, and report hashes")

    old_map = _identity_map(lineage["faces"], "frozen source")
    new_map = _identity_map(rebuilt_lineage["faces"], "rebuilt native")
    if old_map.keys() != new_map.keys() or len(old_map) != len(rebuilt_shape.Faces()):
        raise ValueError("rebuilt native faces do not map one-to-one to frozen faces by unique role/segment identity")
    identity_rows = identity.get("faces")
    if not isinstance(identity_rows, list) or len(identity_rows) != len(new_map):
        raise ValueError("v15 native-face identity table is missing or incomplete")
    source_id_by_new_face: dict[int, str] = {}
    identity_rows_by_new_face: dict[int, dict[str, Any]] = {}
    for row in identity_rows:
        new_index = int(row["native_face_index"])
        identity_key = (str(row["role"]), tuple(sorted(int(v) for v in row["source_segment_indices"])))
        if new_map.get(identity_key) != new_index or old_map.get(identity_key) != int(row["source_original_brep_face_index"]):
            raise ValueError("v15 face identity row is inconsistent with rebuilt and frozen segment lineage")
        expected_id = f"original-brep-face-{int(row['source_original_brep_face_index']):03d}"
        if row.get("source_original_brep_face_id") != expected_id:
            raise ValueError("v15 source face ID does not agree with its frozen lineage identity")
        source_id_by_new_face[new_index] = expected_id
        identity_rows_by_new_face[new_index] = row
    if set(source_id_by_new_face) != set(range(len(rebuilt_shape.Faces()))):
        raise ValueError("v15 face identity rows do not cover every rebuilt native face")

    manifest = json.loads(WITNESS_MANIFEST.read_text(encoding="utf-8"))
    manifest_rows = {str(row["source_face_id"]): row for row in manifest["witnesses"]}
    if len(manifest_rows) != len(manifest["witnesses"]) or len(manifest_rows) != len(source_id_by_new_face):
        raise ValueError("witness manifest IDs are missing, duplicate, or do not match the rebuilt source faces")
    for index, face_id in source_id_by_new_face.items():
        row = manifest_rows.get(face_id)
        if row is None or row["role"] != identity_rows_by_new_face[index]["role"]:
            raise ValueError(f"witness manifest role/ID differs from frozen native lineage for {face_id}")
        if row.get("native_face_child_verified") is not True:
            raise ValueError(f"v15 witness does not record direct native child verification for {face_id}")
        witness_path = Path(row["witness_path"]).resolve(strict=True)
        if sha256_file(witness_path).lower() != row["witness_sha256"].lower():
            raise ValueError(f"v15 witness file hash mismatch for {face_id}")
    witness_file_hashes = {
        str(row["source_face_id"]): {
            "path": str(Path(row["witness_path"]).resolve()),
            "sha256": sha256_file(Path(row["witness_path"]).resolve(strict=True)),
            "bytes": Path(row["witness_path"]).stat().st_size,
        }
        for row in manifest["witnesses"]
    }

    return {
        "asset_hashes": hashes,
        "witness_file_hashes": witness_file_hashes,
        "v15_receipt_status": receipt.get("status"),
        "native_face_count": len(source_id_by_new_face),
        "source_identity_basis": "unique (role, sorted source_segment_indices) tuple joined between frozen source lineage and rebuilt native shape",
        "source_face_id_to_native_face_index": {face_id: index for index, face_id in sorted(source_id_by_new_face.items())},
        "source_face_identity_rows": identity_rows,
        "rebuilt_native_metrics_mm": rebuilt,
        "original_source_step_metrics_mm": original,
        "rebuilt_vs_original_volume_relative_error": volume_error,
        "rebuilt_vs_original_bounds_relative_to_body_span": bounds_error,
        "geometry_report_volume_mm3": geometry_volume,
        "geometry_report_vs_rebuilt_volume_relative_error": _relative_error(geometry_volume, rebuilt["volume_mm3"]),
        "source_integrals": {
            "quadrature_orders": [64, 128],
            "independent_meridian_volume_m3_by_order": {
                str(order): meridian_volume_mm3(section, quadrature_order=order) * 1e-9
                for order in (64, 128)
            },
            "independent_positive_radius_section_area_m2_by_order": {
                str(order): _section_area_mm2(section, order) * 1e-6
                for order in (64, 128)
            },
            "independent_complete_x0_cut_area_m2_by_order": {
                str(order): 2.0 * _section_area_mm2(section, order) * 1e-6
                for order in (64, 128)
            },
            "source_geometry_report_integral_volume_m3": float(
                geometry["measurements"]["independent_meridian_integral_volume_mm3"]
            ) * 1e-9,
            "area_method": "Gauss-Legendre integral of r(t) dz/dt around the closed serialized meridian boundary; complete central cut is twice the positive-radius section area",
        },
    }


def _per_source_face_surface_volume_contributions(arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    """Compare outward mesh triangles with exact per-segment meridian integrals.

    Signed per-face contributions use the declared origin at zero; the closed
    surface sum is origin independent. Area differences are reported as local
    diagnostics and do not qualify individual geometric features.
    """
    section = _section_from_json(ASSET / "geometry/section.json")
    xi, wi = np.polynomial.legendre.leggauss(128)
    parameters = (xi + 1.0) / 2.0
    weights = wi / 2.0
    cad_volume_by_segment: list[float] = []
    cad_area_by_segment: list[float] = []
    for segment in section.segments:
        points = np.asarray([segment.point(float(t)) for t in parameters], dtype=np.float64)
        derivatives = np.asarray([segment.derivative(float(t)) for t in parameters], dtype=np.float64)
        radius = points[:, 0]
        radius_derivative = derivatives[:, 0]
        axial_derivative = derivatives[:, 1]
        cad_volume_by_segment.append(float(
            (2.0 * math.pi / 3.0)
            * np.sum(weights * radius * (points[:, 1] * radius_derivative - radius * axial_derivative))
            * 1e-9
        ))
        cad_area_by_segment.append(float(
            2.0 * math.pi * np.sum(weights * radius * np.linalg.norm(derivatives, axis=1)) * 1e-6
        ))

    lineage = json.loads((ASSET / "geometry/face_lineage.json").read_text(encoding="utf-8"))["faces"]
    nodes = np.asarray(arrays["nodes_m"], dtype=np.float64)
    triangles = np.asarray(arrays["exterior_triangles"], dtype=np.int64)
    triangle_points = nodes[triangles]
    mesh_volume_by_triangle = np.einsum(
        "ij,ij->i", triangle_points[:, 0], np.cross(triangle_points[:, 1], triangle_points[:, 2])
    ) / 6.0
    mesh_area_by_triangle = 0.5 * np.linalg.norm(
        np.cross(
            triangle_points[:, 1] - triangle_points[:, 0],
            triangle_points[:, 2] - triangle_points[:, 0],
        ),
        axis=1,
    )
    face_ids = np.asarray(arrays["exterior_source_face_ids"]).astype(str)
    face_roles = np.asarray(arrays["exterior_roles"]).astype(str)
    if len(face_ids) != len(triangles) or len(face_roles) != len(triangles):
        raise ValueError("surface volume contribution ancestry arrays do not align with exterior triangles")

    rows: list[dict[str, Any]] = []
    for index_text, record in lineage.items():
        face_id = f"original-brep-face-{int(index_text):03d}"
        role = str(record["role"])
        mask = face_ids == face_id
        if not np.any(mask) or np.any(face_roles[mask] != role):
            raise ValueError(f"surface volume contribution mesh labels are missing or inconsistent for {face_id}")
        segment_indices = [int(value) for value in record["source_segment_indices"]]
        if not segment_indices or any(value < 0 or value >= len(cad_volume_by_segment) for value in segment_indices):
            raise ValueError(f"source lineage has invalid meridian segment indices for {face_id}")
        cad_volume = float(sum(cad_volume_by_segment[value] for value in segment_indices))
        cad_area = float(sum(cad_area_by_segment[value] for value in segment_indices))
        mesh_volume = float(mesh_volume_by_triangle[mask].sum())
        mesh_area = float(mesh_area_by_triangle[mask].sum())
        rows.append({
            "source_face_id": face_id,
            "role": role,
            "segment_indices": segment_indices,
            "cad_surface_volume_contribution_m3": cad_volume,
            "mesh_surface_volume_contribution_m3": mesh_volume,
            "volume_contribution_error_m3": mesh_volume - cad_volume,
            "cad_area_m2": cad_area,
            "mesh_area_m2": mesh_area,
            "relative_area_error": (mesh_area - cad_area) / cad_area,
            "triangle_count": int(mask.sum()),
        })
    if len(rows) != 16 or {row["source_face_id"] for row in rows} != set(face_ids.tolist()):
        raise ValueError("per-source-face surface volume rows do not exactly match the 16 exterior FIDs")

    cad_volume = float(sum(cad_volume_by_segment))
    mesh_surface_volume = float(mesh_volume_by_triangle.sum())
    tetrahedral_volume = float(np.asarray(arrays["volume_m3"], dtype=np.float64).sum())
    if abs(mesh_surface_volume - tetrahedral_volume) >= 1e-15:
        raise ValueError("outward surface divergence sum disagrees with tetrahedral volume sum")
    signed_residual = mesh_surface_volume - cad_volume
    if abs(sum(row["volume_contribution_error_m3"] for row in rows) - signed_residual) >= 1e-15:
        raise ValueError("per-FID signed volume contributions do not sum to the body residual")
    rows.sort(key=lambda row: abs(row["volume_contribution_error_m3"]), reverse=True)
    return {
        "status": "PASS_DIVERGENCE_THEOREM_CONTRIBUTION_AUDIT",
        "origin_m": [0.0, 0.0, 0.0],
        "cad_volume_m3": cad_volume,
        "mesh_surface_volume_m3": mesh_surface_volume,
        "tetrahedral_volume_m3": tetrahedral_volume,
        "signed_volume_error_m3": signed_residual,
        "relative_volume_error": abs(signed_residual) / cad_volume,
        "per_source_face": rows,
        "scope": "Per-face signed contributions depend on the declared origin. Local area differences are diagnostics and do not qualify individual geometric features.",
    }


def _independent_mesh_audit(result: dict[str, Any], gmsh: Any) -> dict[str, Any]:
    mesh_npz = OUTPUT / "mesh.npz"
    with np.load(mesh_npz, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    audit = audit_tetra_mesh(
        arrays["nodes_m"],
        arrays["tets"],
        arrays["source_partition_volume"],
        arrays["interface_triangles"],
        arrays["interface_parents"],
        stored_volume_m3=arrays["volume_m3"],
        interface_plane_x_m=float(result["plane_x_m"]),
        expected_volume_m3=float(result["cad"]["source_volume_m3"]),
        expected_interface_area_m2=float(result["cad"]["shared_area_m2"]),
        analytic_relative_tolerance=0.01,
    )
    if audit["status"] != "PASS":
        raise ValueError("independent tetra audit failed")

    ancestry = result["source_face_ancestry"]
    cut_report = ancestry.get("cut_witness_ancestry")
    if not isinstance(cut_report, dict) or cut_report.get("status") != "VERIFIED_OCC_WITNESS_ANCESTRY":
        raise ValueError("saved result lacks the verified raw witness cut-parent map")
    if cut_report.get("interface_has_zero_source_face_ancestry") is not True:
        raise ValueError("cut interface does not carry an explicit zero-FID ancestry result")
    shared_tags = {int(tag) for tag in cut_report.get("interface_surface_tags", [])}
    plane_rows = cut_report.get("raw_plane_parent_map")
    if not shared_tags or not isinstance(plane_rows, list):
        raise ValueError("raw cut plane parent map or shared interface tags are missing")
    plane_tags = set()
    for row in plane_rows:
        signed_tag = int(row["signed_tag"])
        if int(row["dim"]) != 2 or signed_tag == 0 or int(row["tag"]) != abs(signed_tag):
            raise ValueError("raw cut plane parent map contains an invalid signed surface descendant")
        plane_tags.add(abs(signed_tag))
    if not shared_tags.issubset(plane_tags):
        raise ValueError("raw cutting-plane ancestry does not cover every shared interface surface")
    raw_map = cut_report.get("raw_cut_parent_map_by_input")
    source_rows = cut_report.get("raw_source_surface_parent_map_rows")
    if not isinstance(raw_map, list) or not isinstance(source_rows, list) or len(raw_map) != len(source_rows) + 2:
        raise ValueError("raw cut parent map is incomplete for the body, source faces, and cutting plane")
    for index, row in enumerate(raw_map):
        if int(row["input_index"]) != index:
            raise ValueError("raw cut parent map input indices are not in original OCC input order")
        expected_dim = 3 if index == 0 else 2
        for descendant in row["raw_descendants"]:
            signed_tag = int(descendant["signed_tag"])
            if (
                int(descendant["dim"]) != expected_dim
                or signed_tag == 0
                or int(descendant["tag"]) != abs(signed_tag)
            ):
                raise ValueError("raw cut parent map lost signed ancestry or has an invalid dimension")
    for row in source_rows:
        raw_tags = {int(item["tag"]) for item in row["raw_descendants"]}
        if raw_tags & shared_tags:
            raise ValueError("raw source-face ancestry contaminates an interface surface")

    n_exterior = len(arrays["exterior_triangles"])
    ids = arrays["exterior_source_face_ids"].astype(str)
    roles = arrays["exterior_roles"].astype(str)
    exact = arrays["exterior_ancestry_exact"].astype(bool)
    if len(ids) != n_exterior or len(roles) != n_exterior or len(exact) != n_exterior:
        raise ValueError("saved exterior triangle ancestry arrays do not align with exterior triangles")
    if not bool(exact.all()) or np.any(ids == "") or np.any(roles == "") or np.any(roles == "unknown"):
        raise ValueError("one or more exterior mesh triangles lack exact source face/role ancestry")
    manifest = json.loads(WITNESS_MANIFEST.read_text(encoding="utf-8"))
    roles_by_id = {str(row["source_face_id"]): str(row["role"]) for row in manifest["witnesses"]}
    if len(roles_by_id) != len(manifest["witnesses"]) or len(roles_by_id) != 16:
        raise ValueError("source witness manifest does not contain 16 unique source face IDs")
    if any(face_id not in roles_by_id or roles_by_id[face_id] != role for face_id, role in zip(ids, roles, strict=True)):
        raise ValueError("saved exterior triangle ancestry does not agree with the source witness manifest")
    if set(ids.tolist()) != set(roles_by_id):
        raise ValueError("saved exterior mesh does not contain every source witness face ID")
    face_area_rows = cut_report.get("source_face_area_conservation")
    if not isinstance(face_area_rows, list):
        raise ValueError("saved cut report lacks per-source-face area conservation rows")
    face_area_by_id = {str(row["source_face_id"]): row for row in face_area_rows}
    if len(face_area_by_id) != len(face_area_rows) or set(face_area_by_id) != set(roles_by_id):
        raise ValueError("per-source-face area rows do not exactly cover the 16 witness IDs")
    for face_id, row in face_area_by_id.items():
        pre_area = float(row["pre_cut_imprinted_exterior_area_m2"])
        post_area = float(row["post_cut_exterior_descendant_area_sum_m2"])
        area_error = float(row["relative_area_error"])
        area_tolerance = float(row["declared_relative_tolerance"])
        recomputed_error = abs(pre_area - post_area) / max(abs(pre_area), abs(post_area), 1e-300)
        if (
            not all(math.isfinite(value) and value > 0.0 for value in (pre_area, post_area))
            or not math.isfinite(area_error)
            or area_error < 0.0
            or not math.isfinite(area_tolerance)
            or area_tolerance <= 0.0
            or area_tolerance > 1e-5
            or area_error > area_tolerance
            or abs(area_error - recomputed_error) > 1e-12
        ):
            raise ValueError(f"source-face area conservation failed for {face_id}")
    parent_parts = arrays["interface_parent_partition"]
    if parent_parts.ndim != 2 or parent_parts.shape[1] != 2 or any(set(row.tolist()) != {0, 1} for row in parent_parts):
        raise ValueError("an interface triangle does not have two distinct source partition parents")
    if len(arrays["interface_triangles"]) != len(parent_parts) or not len(parent_parts):
        raise ValueError("interface triangles/parent rows are missing or inconsistent")
    parent_cells = arrays["interface_parents"]
    if parent_cells.shape != (len(parent_parts), 2) or np.any(parent_cells[:, 0] == parent_cells[:, 1]):
        raise ValueError("interface triangle parent-cell rows are missing or not distinct")
    cad = result["cad"]
    partition_volumes = np.asarray(cad["partition_volume_m3"], dtype=np.float64)
    partition_error = float(cad["partition_volume_conservation_relative_error"])
    partition_tolerance = float(cad["partition_volume_conservation_relative_tolerance"])
    source_volume = float(cad["source_volume_m3"])
    if not math.isfinite(source_volume) or source_volume <= 0.0:
        raise ValueError("CAD source body volume is nonpositive or nonfinite")
    recomputed_partition_error = abs(float(np.sum(partition_volumes)) - source_volume) / source_volume
    if (
        partition_volumes.shape != (2,)
        or not np.isfinite(partition_volumes).all()
        or np.any(partition_volumes <= 0.0)
        or not math.isfinite(partition_error)
        or partition_error < 0.0
        or partition_error > partition_tolerance
        or not math.isfinite(recomputed_partition_error)
        or abs(partition_error - recomputed_partition_error) > 1e-12
        or not math.isfinite(partition_tolerance)
        or partition_tolerance <= 0.0
        or partition_tolerance > CAD_PARTITION_VOLUME_RELATIVE_TOLERANCE
    ):
        raise ValueError("CAD partition volumes do not satisfy the declared OCC conservation tolerance")
    if len(arrays["tets"]) > 100_000:
        raise ValueError("generated mesh exceeds the 100,000 tetrahedron cap")
    points = arrays["nodes_m"][arrays["tets"]]
    face_corners = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))
    face_areas = np.column_stack([
        0.5 * np.linalg.norm(
            np.cross(points[:, corners[1]] - points[:, corners[0]], points[:, corners[2]] - points[:, corners[0]]),
            axis=1,
        )
        for corners in face_corners
    ])
    altitudes_m = np.min(3.0 * np.asarray(arrays["volume_m3"])[:, None] / face_areas, axis=1)
    if not np.isfinite(altitudes_m).all() or np.any(altitudes_m <= 0.0):
        raise ValueError("independent tetrahedron altitude calculation found a degenerate cell")
    altitude_quantiles_mm = {
        name: float(value)
        for name, value in zip(
            ("min", "p1", "p5", "median", "p95", "max"),
            np.quantile(altitudes_m * 1_000.0, [0.0, 0.01, 0.05, 0.5, 0.95, 1.0]),
            strict=True,
        )
    }
    gmsh.clear()
    gmsh.open(str(OUTPUT / "mesh.msh"))
    tetra_element_tags: list[int] = []
    for dim, tag in gmsh.model.getEntities(3):
        kinds, tag_rows, _ = gmsh.model.mesh.getElements(3, int(tag))
        for kind, element_tags in zip(kinds, tag_rows, strict=True):
            if int(kind) == 4:
                tetra_element_tags.extend(int(value) for value in element_tags)
            else:
                raise ValueError(f"independently reopened MSH contains non-T4 volume element type {kind}")
    if len(tetra_element_tags) != len(arrays["tets"]):
        raise ValueError("independently reopened MSH T4 count differs from saved NPZ")
    sicn = np.asarray(gmsh.model.mesh.getElementQualities(tetra_element_tags, "minSICN"), dtype=np.float64)
    if sicn.shape != (len(tetra_element_tags),) or not np.isfinite(sicn).all():
        raise ValueError("Gmsh minSICN returned missing or nonfinite element qualities")
    surface_volume_contributions = _per_source_face_surface_volume_contributions(arrays)
    return {
        "status": "PASS",
        "independent_audit": audit,
        "mesh_npz_sha256": sha256_file(mesh_npz),
        "mesh_npz_bytes": mesh_npz.stat().st_size,
        "msh_sha256": sha256_file(OUTPUT / "mesh.msh"),
        "msh_bytes": (OUTPUT / "mesh.msh").stat().st_size,
        "counts": {
            "nodes": int(len(arrays["nodes_m"])),
            "tetrahedra": int(len(arrays["tets"])),
            "interface_triangles": int(len(arrays["interface_triangles"])),
            "exterior_triangles": int(n_exterior),
            "unique_exterior_source_face_ids": sorted(set(ids.tolist())),
            "source_roles": sorted(set(roles.tolist())),
        },
        "tetrahedron_minimum_altitude_mm": altitude_quantiles_mm,
        "gmsh_minSICN": {
            "min": float(np.min(sicn)),
            "p1": float(np.quantile(sicn, 0.01)),
            "p5": float(np.quantile(sicn, 0.05)),
            "median": float(np.median(sicn)),
            "p95": float(np.quantile(sicn, 0.95)),
            "max": float(np.max(sicn)),
            "method": "Gmsh getElementQualities(..., 'minSICN') on independently reopened MSH 2.2",
        },
        "all_exterior_triangles_have_known_manifest_role": True,
        "all_16_source_face_ids_appear_on_the_exterior_mesh": True,
        "interface_source_face_id_count": 0,
        "raw_cut_plane_ancestry_covers_interface": True,
        "per_source_face_area_conservation": face_area_rows,
        "per_source_face_surface_volume_contributions": surface_volume_contributions,
        "every_interface_triangle_has_two_distinct_partition_parents": True,
        "interface_max_abs_x_deviation_m": float(audit["interface"]["max_abs_x_plane_deviation_m"]),
        "cad_mesh_volume_relative_error": float(audit["volume"]["analytic_relative_error"]),
        "interface_area_relative_error_vs_occ": float(audit["interface"]["relative_area_error"]),
    }


def _validate_prior_attempts() -> None:
    run01 = json.loads((HERE / "run01" / "failure_receipt.json").read_text(encoding="utf-8"))
    if run01.get("status") != "FAIL" or "1.060%" not in run01.get("error", ""):
        raise ValueError("run 01 failure evidence is missing or no longer matches its retained 1% gate failure")
    if (HERE / "run01" / "partition_output").exists():
        raise ValueError("run 01 unexpectedly contains mesh output; refusing to continue")

    run02 = json.loads((HERE / "run02" / "failure_receipt.json").read_text(encoding="utf-8"))
    forecast = run02.get("resource_forecast_from_cap_error") or {}
    if (
        run02.get("status") != "FAIL"
        or not run02.get("error", "").startswith("ResourceCapError:")
        or forecast.get("estimated_tetrahedra") != 105_561
        or forecast.get("estimated_peak_memory_bytes") != 1_729_511_424
    ):
        raise ValueError("run 02 resource-cap failure evidence is missing or has changed")
    if (HERE / "run02" / "partition_output").exists():
        raise ValueError("run 02 unexpectedly contains mesh output; refusing to continue")

    run03 = json.loads((HERE / "run03" / "failure_receipt.json").read_text(encoding="utf-8"))
    if (
        run03.get("status") != "FAIL"
        or "1.232%" not in run03.get("error", "")
        or "tetrahedra=19322" not in run03.get("error", "")
        or "forecast=93844" not in run03.get("error", "")
    ):
        raise ValueError("run 03 failure evidence is missing or no longer matches its retained 1% gate failure")
    if (HERE / "run03" / "partition_output").exists():
        raise ValueError("run 03 unexpectedly contains accepted mesh output; refusing to continue")

    run04 = json.loads((HERE / "run04" / "failure_receipt.json").read_text(encoding="utf-8"))
    if (
        run04.get("status") != "FAIL"
        or "1.125%" not in run04.get("error", "")
        or "tetrahedra=31808" not in run04.get("error", "")
        or not run04.get("failed_mesh_diagnostics")
    ):
        raise ValueError("run 04 failure evidence is missing or no longer matches its retained volume-gate failure")
    if (HERE / "run04" / "partition_output").exists():
        raise ValueError("run 04 unexpectedly contains accepted mesh output; refusing to continue")


def _write_failed_geometry_diagnostics(error: Exception, gmsh: Any, receipt: dict[str, Any]) -> None:
    """Persist only the bounded mesh bundle attached by the unchanged volume gate."""
    diagnostics = getattr(error, "mesh_diagnostics", None)
    if not isinstance(diagnostics, dict):
        diagnostic_error = getattr(error, "mesh_diagnostics_error", None)
        if diagnostic_error:
            receipt["failed_mesh_diagnostics_error"] = diagnostic_error
        return
    try:
        if diagnostics.get("diagnostic_status") != "FAILED_GEOMETRY_NOT_FOR_SIMULATION":
            raise ValueError("mesh diagnostic bundle lacks its rejected-only status")
        tets = np.asarray(diagnostics["tets"], dtype=np.int32)
        nodes = np.asarray(diagnostics["nodes_m"], dtype=np.float64)
        if tets.ndim != 2 or tets.shape[1] != 4 or len(tets) > 100_000:
            raise ValueError("rejected mesh diagnostic T4 array is malformed or exceeds 100,000 cells")
        if nodes.ndim != 2 or nodes.shape[1] != 3 or len(nodes) > np.iinfo(np.int32).max:
            raise ValueError("rejected mesh diagnostic node array is malformed or exceeds int32 indexing")
        if any(np.asarray(diagnostics[key]).dtype == object for key in (
            "interface_triangles", "interface_parents", "interface_parent_partition",
            "interface_surface_tags", "exterior_triangles", "exterior_surface_tags",
            "exterior_source_face_ids", "exterior_roles", "exterior_ancestry_exact",
            "exterior_ancestry_counts", "partition_entity_tags", "volume_m3",
        )):
            raise ValueError("rejected mesh diagnostics contain an object array")

        diagnostic_dir = RUN_DIR / "failed_geometry_not_for_simulation"
        diagnostic_dir.mkdir(parents=True, exist_ok=False)
        msh_path = diagnostic_dir / "FAILED_GEOMETRY_NOT_FOR_SIMULATION.msh"
        npz_path = diagnostic_dir / "FAILED_GEOMETRY_NOT_FOR_SIMULATION.npz"
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 0)
        gmsh.write(str(msh_path))
        np.savez_compressed(
            npz_path,
            **{
                key: np.asarray(diagnostics[key])
                for key in (
                    "nodes_m", "tets", "original_node_tags", "original_cell_tags", "partition", "volume_m3",
                    "interface_triangles", "interface_parents", "interface_parent_partition", "interface_surface_tags",
                    "exterior_triangles", "exterior_surface_tags", "exterior_source_face_ids", "exterior_roles",
                    "exterior_ancestry_exact", "exterior_ancestry_counts", "partition_entity_tags",
                )
            },
        )
        with np.load(npz_path, allow_pickle=False) as archive:
            loaded = {key: archive[key].copy() for key in archive.files}
        tri = loaded["exterior_triangles"].astype(np.int64, copy=False)
        if len(tri):
            points = loaded["nodes_m"][tri]
            cross = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
            area_m2 = 0.5 * np.linalg.norm(cross, axis=1)
            edge_lengths_m = np.column_stack((
                np.linalg.norm(points[:, 1] - points[:, 0], axis=1),
                np.linalg.norm(points[:, 2] - points[:, 1], axis=1),
                np.linalg.norm(points[:, 0] - points[:, 2], axis=1),
            ))
        else:
            area_m2 = np.empty(0, dtype=np.float64)
            edge_lengths_m = np.empty((0, 3), dtype=np.float64)
        face_ids = loaded["exterior_source_face_ids"].astype(str)
        roles = loaded["exterior_roles"].astype(str)
        ancestry_exact = loaded["exterior_ancestry_exact"].astype(bool)
        rows = []
        for face_id in sorted(set(face_ids.tolist())):
            mask = face_ids == face_id
            if not np.any(mask):
                continue
            edges_mm = edge_lengths_m[mask].reshape(-1) * 1_000.0
            rows.append({
                "source_face_id": face_id,
                "roles": sorted(set(roles[mask].tolist())),
                "triangle_count": int(mask.sum()),
                "exact_ancestry_triangle_count": int(ancestry_exact[mask].sum()),
                "diagnostic_surface_area_m2": float(area_m2[mask].sum()),
                "triangle_edge_chord_mm": {
                    name: float(value)
                    for name, value in zip(
                        ("min", "p1", "median", "p95", "max"),
                        np.quantile(edges_mm, [0.0, 0.01, 0.5, 0.95, 1.0]),
                        strict=True,
                    )
                },
            })
        metadata = {
            "status": "FAILED_GEOMETRY_NOT_FOR_SIMULATION",
            "simulation_qualification": "NOT_QUALIFIED",
            "reason": f"{type(error).__name__}: {error}",
            "diagnostic_only": True,
            "geometry_gate_changed": False,
            "mesh_counts": {"nodes": int(len(nodes)), "tetrahedra": int(len(tets))},
            "cad_mesh_volume_relative_error": diagnostics.get("cad_mesh_volume_relative_error"),
            "cad_volume_m3": diagnostics.get("source_volume_m3"),
            "tetrahedral_volume_m3": diagnostics.get("mesh_volume_m3"),
            "resource_forecast": diagnostics.get("resource_forecast"),
            "interface_source_face_id_count": 0,
            "interface_surface_tags": sorted(set(loaded["interface_surface_tags"].tolist())),
            "interface_triangle_count": int(len(loaded["interface_triangles"])),
            "interface_parent_partition_pairs": sorted({tuple(map(int, row)) for row in loaded["interface_parent_partition"]}),
            "exterior_source_face_ids": sorted(set(face_ids.tolist())),
            "per_source_face_area_and_chord_diagnostics": rows,
            "witness_imprint_report": diagnostics.get("witness_imprint_report"),
            "witness_cut_report": diagnostics.get("witness_cut_report"),
            "files": {
                path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                for path in (msh_path, npz_path)
            },
        }
        _write_json(diagnostic_dir / "FAILED_GEOMETRY_NOT_FOR_SIMULATION.json", metadata)
        receipt["failed_mesh_diagnostics"] = {
            "status": metadata["status"],
            "directory": str(diagnostic_dir.resolve()),
            "files": metadata["files"],
            "per_source_face_area_and_chord_diagnostics": rows,
        }
    except Exception as diagnostics_error:
        receipt["failed_mesh_diagnostics_error"] = f"{type(diagnostics_error).__name__}: {diagnostics_error}"


def main() -> None:
    _validate_prior_attempts()
    if RUN_DIR.exists() or OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite v6 witness mesh evidence: {RUN_DIR}")
    RUN_DIR.mkdir(parents=True)
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema": "vesselforge.reference_v6_witness_tetra_run.v1",
        "status": "RUNNING",
        "executed_driver_path": str(Path(__file__).resolve()),
        "executed_driver_sha256": sha256_file(__file__),
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "driver_wall_cap_s": 120,
        "declared_resource_caps": {
            "max_step_bytes": 32 * 1024 * 1024,
            "max_tetrahedra": 100_000,
            "max_forecast_memory_bytes": 2 * 1024**3,
            "process_wall_cap_s": 120,
            "mesh_size_m": MESH_SIZE_M,
            "tetrahedra_per_volume_cell": TETRAHEDRA_PER_VOLUME_CELL,
            "tetrahedra_per_volume_cell_scope": "empirical forecast multiplier for this frozen v6 CAD/mesher configuration only; not a universal bound",
            "boundary_size_by_role_m": BOUNDARY_SIZE_BY_ROLE_M,
        },
        "source_geometry_and_lineage": None,
        "code_hashes": {},
        "execution_environment": None,
        "independent_mesh_audit": None,
    }
    _write_json(RUN_DIR / "run_status.json", receipt)
    gmsh = None
    try:
        source_validation = _source_identity_preflight()
        receipt["source_geometry_and_lineage"] = source_validation
        code_files = {
            "face_witness.py": VF / "src/vesselforge/face_witness.py",
            "step_partition.py": VF / "src/vesselforge/step_partition.py",
            "named_step.py": VF / "src/vesselforge/named_step.py",
            "revolved_profile.py": VF / "src/vesselforge/revolved_profile.py",
            "tetra_audit.py": VF / "src/vesselforge/tetra_audit.py",
            "test_face_witness.py": VF / "tests/test_face_witness.py",
            "test_step_partition.py": VF / "tests/test_step_partition.py",
            "test_named_step.py": VF / "tests/test_named_step.py",
            "run05_witness_mesh.py": Path(__file__).resolve(),
        }
        snapshot = RUN_DIR / "source_snapshot"
        snapshot.mkdir()
        code_hashes = {}
        for name, source in code_files.items():
            copied = snapshot / name
            shutil.copyfile(source, copied)
            code_hashes[name] = {"sha256": sha256_file(source), "snapshot_sha256": sha256_file(copied)}
            if code_hashes[name]["sha256"] != code_hashes[name]["snapshot_sha256"]:
                raise ValueError(f"source snapshot hash mismatch for {name}")
        receipt["code_hashes"] = code_hashes
        receipt["input_hashes"] = source_validation["asset_hashes"]
        _write_json(RUN_DIR / "pre_mesh_receipt.json", receipt)

        caps = ResourceCaps(
            max_step_bytes=32 * 1024 * 1024,
            max_tetrahedra=100_000,
            max_memory_bytes=2 * 1024**3,
            max_source_faces=250,
            tetrahedra_per_volume_cell=TETRAHEDRA_PER_VOLUME_CELL,
        )
        if not PYTHON.is_file():
            raise FileNotFoundError(PYTHON)
        if BODY_STEP.stat().st_size > caps.max_step_bytes:
            raise ValueError("canonical named STEP exceeds byte cap")
        gmsh = _load_gmsh()
        gmsh.initialize()
        gmsh.option.setNumber("Geometry.Tolerance", 1e-8)
        gmsh.option.setNumber("Geometry.OCCBoundsUseStl", 1)
        gmsh.option.setNumber("General.NumThreads", 1)
        receipt["execution_environment"] = {
            "python_version": platform.python_version(),
            "cadquery_version": importlib.metadata.version("cadquery"),
            "opencascade_ocp_version": importlib.metadata.version("cadquery-ocp"),
            "numpy_version": np.__version__,
            "gmsh_python_module_version": str(gmsh.__version__),
            "gmsh_api_version": [
                int(gmsh.GMSH_API_VERSION_MAJOR),
                int(gmsh.GMSH_API_VERSION_MINOR),
                int(gmsh.GMSH_API_VERSION_PATCH),
            ],
            "gmsh_sdk_library_directory": str(GMSH_LIB),
        }
        source_section_areas = source_validation["source_integrals"]["independent_positive_radius_section_area_m2_by_order"]
        source_volumes = source_validation["source_integrals"]["independent_meridian_volume_m3_by_order"]
        expected_section_area_m2 = float(source_section_areas["128"])
        expected_volume_m3 = float(source_volumes["128"])
        manifest = json.loads(WITNESS_MANIFEST.read_text(encoding="utf-8"))
        expected_step_sha = sha256_file(BODY_STEP)
        if manifest.get("native_body_step_sha256", "").lower() != expected_step_sha.lower():
            raise ValueError("witness manifest does not match canonical named STEP hash")
        result = partition_step_at_x(
            gmsh,
            BODY_STEP,
            expected_step_sha,
            OUTPUT,
            resource_caps=caps,
            plane_x_m=0.0,
            expected_volume_m3=expected_volume_m3,
            expected_meridian_section_area_m2=expected_section_area_m2,
            mesh_size_m=MESH_SIZE_M,
            native_face_witness_manifest=WITNESS_MANIFEST,
            expected_witness_source_step_sha256=source_validation["asset_hashes"]["solid.step"],
            expected_witness_source_face_lineage_sha256=source_validation["asset_hashes"]["face_lineage.json"],
            boundary_size_by_role_m=BOUNDARY_SIZE_BY_ROLE_M,
            cad_partition_volume_relative_tolerance=CAD_PARTITION_VOLUME_RELATIVE_TOLERANCE,
        )
        if result["resource_forecast"]["estimated_tetrahedra"] > 100_000:
            raise ValueError("the declared tetrahedron forecast exceeds 100,000")
        if result["resource_forecast"]["estimated_peak_memory_bytes"] > 2 * 1024**3:
            raise ValueError("the declared memory forecast exceeds 2 GiB")
        if result["source_face_ancestry"].get("status") != "VERIFIED_OCC_WITNESS_ANCESTRY":
            raise ValueError("witness ancestry result does not carry the required verified status")
        if "not literal TopoDS identity" not in result["source_face_ancestry"].get("identity_scope", ""):
            raise ValueError("witness ancestry result overstates identity scope")
        receipt["independent_mesh_audit"] = _independent_mesh_audit(result, gmsh)
        receipt["cad_checks"] = {
            "witness_imprint": result["source_face_ancestry"]["witness_imprint"],
            "cut_witness_ancestry": result["source_face_ancestry"]["cut_witness_ancestry"],
            "source_volume_m3": result["cad"]["source_volume_m3"],
            "independent_expected_volume_m3": expected_volume_m3,
            "source_volume_vs_independent_integral_relative_error": result["cad"]["expected_volume_relative_error"],
            "partition_volumes_m3": result["cad"]["partition_volume_m3"],
            "partition_volume_conservation_relative_error": result["cad"]["partition_volume_conservation_relative_error"],
            "partition_volume_conservation_declared_tolerance": result["cad"]["partition_volume_conservation_relative_tolerance"],
            "occ_complete_cut_area_m2": result["cad"]["shared_area_m2"],
            "independent_complete_cut_area_m2_by_quadrature_order": source_validation["source_integrals"]["independent_complete_x0_cut_area_m2_by_order"],
            "occ_vs_independent_complete_cut_area_relative_error": result["cad"]["shared_area_vs_independent_section_relative_error"],
            "independent_cut_area_method": source_validation["source_integrals"]["area_method"],
            "cad_mesh_volume_error_gate": 0.01,
            "occ_vs_independent_cut_area_gate": 0.01,
            "geometry_comparison_interpretation": "declared OCC tolerance diagnostics; small nonzero differences are retained and are not exact metrology claims",
        }
        receipt["result_sha256"] = sha256_file(OUTPUT / "result.json")
        receipt["result_json_bytes"] = (OUTPUT / "result.json").stat().st_size
        receipt["result_summary"] = {
            "status": result["status"],
            "source_face_ancestry_status": result["source_face_ancestry"].get("status"),
            "counts": result["counts"],
            "source_step_sha256": result["source_step_sha256"],
            "global_mesh_size_m": result["global_mesh_size_m"],
            "boundary_size_by_role_m": BOUNDARY_SIZE_BY_ROLE_M,
            "forecast": result["resource_forecast"],
            "cad_mesh_volume_relative_error": result["mesh"]["cad_mesh_volume_relative_error"],
            "interface_area_relative_error_vs_occ": result["mesh"]["occ_mesh_interface_area_relative_error"],
            "source_geometry_section_area_relative_error": result["cad"]["shared_area_vs_independent_section_relative_error"],
            "per_source_face_surface_volume_contributions": receipt["independent_mesh_audit"]["per_source_face_surface_volume_contributions"],
        }
        receipt["status"] = "PASS_WITNESS_ANCESTRY_TETRA_MESH"
        receipt["elapsed_s"] = time.monotonic() - started
        _write_json(RUN_DIR / "audit_receipt.json", receipt)
    except Exception as error:
        _write_failed_geometry_diagnostics(error, gmsh, receipt)
        receipt.update({
            "status": "FAIL",
            "error": f"{type(error).__name__}: {error}",
            "resource_forecast_from_cap_error": getattr(error, "forecast", None),
            "traceback": traceback.format_exc(),
            "elapsed_s": time.monotonic() - started,
        })
        _write_json(RUN_DIR / "failure_receipt.json", receipt)
        raise
    finally:
        if gmsh is not None:
            try:
                gmsh.finalize()
            except Exception:
                pass
    print(json.dumps({"status": receipt["status"], "run_dir": str(RUN_DIR), "summary": receipt.get("result_summary")}, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]
ASSET_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "wall_mesh_binding" / "v4_run" / "cylinder_asset_run01"
ASSET_MANIFEST = ASSET_ROOT / "manifest.json"
RUNNER = REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "wall_mesh_binding" / "run_hollow_cylinder_binding.py"
FROZEN_RUNNER = REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "wall_mesh_binding" / "v4_frozen" / "run_hollow_cylinder_binding.py"
ACTIVE_BINDING = REPO_ROOT / "vesselforge" / "src" / "vesselforge" / "wall_mesh_binding.py"
FROZEN_BINDING = REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "wall_mesh_binding" / "v4_frozen" / "wall_mesh_binding.py"
GEOMETRY_SOURCE = REPO_ROOT / "vesselforge" / "src" / "vesselforge" / "geometry.py"
CADQUERY_ROOT = REPO_ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Lib" / "site-packages" / "cadquery"

sys.path.insert(0, str(REPO_ROOT / "vesselforge" / "src"))

import cadquery as cq
import numpy as np
import OCP
from OCP.BRep import BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.TopLoc import TopLoc_Location

from vesselforge.geometry import VesselSpec, mesh_shape


MESH_LINEAR_MM = 0.05
MESH_ANGULAR_RAD = 0.08
STRICT_COMPARE_TOL_MM = 1e-7


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def callable_info(value: Any) -> dict[str, Any]:
    try:
        signature = str(inspect.signature(value))
        signature_error = None
    except Exception as exc:
        signature = None
        signature_error = f"{type(exc).__name__}: {exc}"
    return {
        "signature": signature,
        "signature_error": signature_error,
        "doc": getattr(value, "__doc__", None),
        "module": getattr(value, "__module__", None),
        "qualname": getattr(value, "__qualname__", None),
    }


def cadquery_bbox_order(face: cq.Face) -> list[float]:
    bounds = face.BoundingBox()
    return [
        float(bounds.xmin), float(bounds.xmax),
        float(bounds.ymin), float(bounds.ymax),
        float(bounds.zmin), float(bounds.zmax),
    ]


def explicit_geometry_bbox(face: cq.Face) -> dict[str, Any]:
    box = Bnd_Box()
    # This is the one explicit stable-bounds call: exclude triangulation cache
    # and shape tolerance. Do not silently fall back to another overload.
    BRepBndLib.AddOptimal_s(face.wrapped, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = (float(value) for value in box.Get())
    return {
        "call": "BRepBndLib.AddOptimal_s(face.wrapped, box, False, False)",
        "flags": {"useTriangulation": False, "useShapeTolerance": False},
        "bnd_box_get_order_xyz": [xmin, ymin, zmin, xmax, ymax, zmax],
        "asset_inventory_order": [xmin, xmax, ymin, ymax, zmin, zmax],
        "is_void": bool(box.IsVoid()),
        "is_whole": bool(box.IsWhole()),
    }


def triangulation_info(face: cq.Face) -> dict[str, Any]:
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
    if triangulation is None:
        return {"present": False, "node_count": 0, "triangle_count": 0, "deflection_mm": None}
    return {
        "present": True,
        "node_count": int(triangulation.NbNodes()),
        "triangle_count": int(triangulation.NbTriangles()),
        "deflection_mm": float(triangulation.Deflection()),
    }


def face_measure(face: cq.Face, index: int) -> dict[str, Any]:
    return {
        "index_zero_based": index,
        "geom_type": face.geomType(),
        "default_cadquery_bbox_asset_order": cadquery_bbox_order(face),
        "explicit_geometry_bbox": explicit_geometry_bbox(face),
        "area_mm2": float(face.Area()),
        "surface_area_centroid_mm": [float(value) for value in face.Center().toTuple()],
        "triangulation_cache": triangulation_info(face),
    }


def max_abs_delta(left: Any, right: Any) -> float | None:
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return None
    return max((abs(float(a) - float(b)) for a, b in zip(left, right)), default=0.0)


def api_report() -> dict[str, Any]:
    return {
        "cadquery_face_BoundingBox": callable_info(cq.Face.BoundingBox),
        "cadquery_boundbox_from_topods": callable_info(cq.occ_impl.geom.BoundBox._fromTopoDS),
        "OCP_BRepBndLib_AddOptimal_s": callable_info(BRepBndLib.AddOptimal_s),
        "OCP_BRepBndLib_Add_s": callable_info(BRepBndLib.Add_s),
        "OCP_Bnd_Box_Get": callable_info(Bnd_Box.Get),
        "OCP_BRepTools_Clean_s": callable_info(BRepTools.Clean_s),
        "OCP_BRepMesh_IncrementalMesh": callable_info(BRepMesh_IncrementalMesh),
        "OCP_BRep_Tool_Triangulation_s": callable_info(BRep_Tool.Triangulation_s),
    }


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "diagnostic_id": "vesselforge.face-bounds-triangulation-cache/2026-10-04",
        "status": "RUNNING",
        "purpose": "Observe canonical STEP face bounds on one imported shape before and after exactly one existing mesh_shape call; no binding, asset write, STEP export, or physics qualification.",
        "argv": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "working_directory": str(Path.cwd()),
        "started_utc": started,
        "scope": {
            "canonical_step_import_count": 0,
            "mesh_shape_call_count": 0,
            "step_export_count": 0,
            "asset_write_count": 0,
            "same_imported_shape_used_before_and_after_mesh": True,
            "wall_binding_or_physics_pass_claimed": False,
        },
        "bbox_order": {
            "runner_and_helper_inventory_order": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
            "OCP_Bnd_Box_Get_order": ["xmin", "ymin", "zmin", "xmax", "ymax", "zmax"],
        },
        "api_signatures_and_docstrings": api_report(),
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "cadquery_version": cq.__version__,
            "ocp_version": OCP.__version__,
            "no_bytecode_writes": bool(sys.dont_write_bytecode),
        },
        "implementation_facts": {
            "runner_order": "run_hollow_cylinder_binding.py imports STEP, calls mesh_shape(canonical, spec), then writes brep_face_inventory using _face_inventory(canonical).",
            "runner_face_bbox": "_face_inventory calls face.BoundingBox() with no arguments and stores [xmin,xmax,ymin,ymax,zmin,zmax].",
            "cadquery_default": "CadQuery BoundBox._fromTopoDS defaults optimal=True and calls BRepBndLib.AddOptimal_s(shape, bbox) without explicit flags; its tolerance default is not used in that optimal branch.",
            "mesh_shape": "geometry.mesh_shape calls BRepTools.Clean_s(shape.wrapped, True), then BRepMesh_IncrementalMesh(shape, linear_deflection_mm, False, angular_tolerance_rad, False), then Perform().",
            "binding_check": "_check_face_inventory recomputes face.BoundingBox() in the same asset inventory order and compares max absolute bound delta against the configured strict tolerance; it also checks face index, geom_type, center and area.",
            "face_area_and_center": "CadQuery face Area/Center use BRepGProp surface properties; shape_properties_LUT maps TopAbs_FACE to BRepGProp.SurfaceProperties_s.",
        },
    }

    step_path: Path | None = None
    step_sha_before: str | None = None
    try:
        if not ASSET_MANIFEST.is_file():
            raise FileNotFoundError(f"missing existing asset manifest: {ASSET_MANIFEST}")
        manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
        step_relative = manifest["geometry"]["solid_step"]
        step_path = (ASSET_ROOT / step_relative).resolve()
        expected_sha = manifest["provenance"]["spec"]["canonical_step_sha256"]
        step_sha_before = sha256(step_path)
        if step_sha_before != expected_sha:
            raise ValueError("existing STEP bytes differ from manifest canonical_step_sha256")

        report["input_asset"] = {
            "asset_root": str(ASSET_ROOT),
            "manifest_path": str(ASSET_MANIFEST),
            "manifest_sha256": sha256(ASSET_MANIFEST),
            "step_path": str(step_path),
            "step_relative_path": step_relative,
            "step_bytes_before": int(step_path.stat().st_size),
            "step_sha256_before": step_sha_before,
            "manifest_step_sha256": expected_sha,
            "recorded_tessellation": manifest["provenance"]["spec"]["tessellation"],
            "recorded_face_inventory": manifest["provenance"]["spec"]["brep_face_inventory"],
        }

        # Exactly one STEP import. The before/after comparison uses this same
        # TopoDS shape, so it isolates mesh-cache state from file reimport.
        shape = cq.importers.importStep(str(step_path)).val()
        report["scope"]["canonical_step_import_count"] = 1
        if not shape.isValid() or len(shape.Solids()) != 1:
            raise ValueError("canonical STEP import is not one valid solid")
        faces_before = shape.Faces()
        recorded_faces = manifest["provenance"]["spec"]["brep_face_inventory"]
        if len(faces_before) != len(recorded_faces):
            raise ValueError("imported BREP face count differs from recorded manifest")

        report["before_mesh"] = {
            "face_count": len(faces_before),
            "faces": [face_measure(face, index) for index, face in enumerate(faces_before)],
        }

        spec_values = manifest["provenance"]["spec"]["parameters"]
        spec = VesselSpec(
            body_width_mm=float(spec_values["body_width_mm"]),
            body_height_mm=float(spec_values["body_height_mm"]),
            wall_mm=float(spec_values["wall_mm"]),
            tessellation_linear_mm=MESH_LINEAR_MM,
            tessellation_angular_rad=MESH_ANGULAR_RAD,
        )
        report["tessellation_call"] = {
            "function": "vesselforge.geometry.mesh_shape",
            "linear_chord_deflection_mm": MESH_LINEAR_MM,
            "is_relative": False,
            "angular_tolerance_rad": MESH_ANGULAR_RAD,
            "parallel": False,
            "source_file": str(GEOMETRY_SOURCE),
            "source_sha256": sha256(GEOMETRY_SOURCE),
        }
        report["scope"]["mesh_shape_call_count"] = 1
        vertices, triangles, triangle_faces = mesh_shape(shape, spec)

        report["after_mesh"] = {
            "face_count": len(shape.Faces()),
            "mesh_node_count": int(len(vertices)),
            "mesh_triangle_count": int(len(triangles)),
            "triangle_source_face_count": int(len(triangle_faces)),
            "faces": [face_measure(face, index) for index, face in enumerate(shape.Faces())],
        }

        comparisons: list[dict[str, Any]] = []
        for index, (before, after, recorded) in enumerate(
            zip(report["before_mesh"]["faces"], report["after_mesh"]["faces"], recorded_faces)
        ):
            recorded_bbox = recorded["bbox_mm"]
            default_before = before["default_cadquery_bbox_asset_order"]
            default_after = after["default_cadquery_bbox_asset_order"]
            exact_before = before["explicit_geometry_bbox"]["asset_inventory_order"]
            exact_after = after["explicit_geometry_bbox"]["asset_inventory_order"]
            comparisons.append(
                {
                    "index_zero_based": index,
                    "geom_type": before["geom_type"],
                    "manifest_bbox_mm": recorded_bbox,
                    "default_bbox_before_mesh_mm": default_before,
                    "default_bbox_after_mesh_mm": default_after,
                    "explicit_geometry_bbox_before_mesh_mm": exact_before,
                    "explicit_geometry_bbox_after_mesh_mm": exact_after,
                    "default_bbox_delta_after_minus_before_mm_by_component": [
                        float(after_value - before_value) for before_value, after_value in zip(default_before, default_after)
                    ],
                    "default_vs_manifest_max_abs_mm_before": max_abs_delta(default_before, recorded_bbox),
                    "default_vs_manifest_max_abs_mm_after": max_abs_delta(default_after, recorded_bbox),
                    "explicit_geometry_vs_manifest_max_abs_mm_before": max_abs_delta(exact_before, recorded_bbox),
                    "explicit_geometry_vs_manifest_max_abs_mm_after": max_abs_delta(exact_after, recorded_bbox),
                    "explicit_geometry_bbox_delta_after_minus_before_max_abs_mm": max_abs_delta(exact_before, exact_after),
                    "area_delta_after_minus_before_mm2": float(after["area_mm2"] - before["area_mm2"]),
                    "surface_area_centroid_delta_after_minus_before_mm": [
                        float(after_value - before_value)
                        for before_value, after_value in zip(before["surface_area_centroid_mm"], after["surface_area_centroid_mm"])
                    ],
                    "triangulation_cache_before": before["triangulation_cache"],
                    "triangulation_cache_after": after["triangulation_cache"],
                }
            )

        default_changes = [
            row["default_bbox_delta_after_minus_before_mm_by_component"]
            for row in comparisons
        ]
        max_default_delta = max((abs(value) for row in default_changes for value in row), default=0.0)
        max_exact_delta = max(
            (row["explicit_geometry_bbox_delta_after_minus_before_max_abs_mm"] or 0.0 for row in comparisons),
            default=0.0,
        )
        cache_counts_before = sum(int(row["triangulation_cache_before"]["present"]) for row in comparisons)
        cache_counts_after = sum(int(row["triangulation_cache_after"]["present"]) for row in comparisons)
        max_after_manifest = max(
            (row["default_vs_manifest_max_abs_mm_after"] or 0.0 for row in comparisons),
            default=0.0,
        )
        max_before_manifest = max(
            (row["default_vs_manifest_max_abs_mm_before"] or 0.0 for row in comparisons),
            default=0.0,
        )
        max_exact_vs_manifest = max(
            (row["explicit_geometry_vs_manifest_max_abs_mm_before"] or 0.0 for row in comparisons),
            default=0.0,
        )
        report["comparisons"] = {
            "per_face": comparisons,
            "strict_observation_threshold_mm": STRICT_COMPARE_TOL_MM,
            "max_default_bbox_delta_after_minus_before_mm": max_default_delta,
            "max_explicit_geometry_bbox_delta_after_minus_before_mm": max_exact_delta,
            "triangulated_face_count_before_mesh": cache_counts_before,
            "triangulated_face_count_after_mesh": cache_counts_after,
            "max_default_bbox_vs_manifest_mm_before_mesh": max_before_manifest,
            "max_default_bbox_vs_manifest_mm_after_mesh": max_after_manifest,
            "max_explicit_geometry_bbox_vs_manifest_mm": max_exact_vs_manifest,
            "default_bbox_changed_after_mesh_over_strict_threshold": bool(max_default_delta > STRICT_COMPARE_TOL_MM),
            "explicit_geometry_bbox_stable_over_strict_threshold": bool(max_exact_delta <= STRICT_COMPARE_TOL_MM),
            "manifest_matches_default_after_mesh_over_strict_threshold": bool(max_after_manifest <= STRICT_COMPARE_TOL_MM),
            "manifest_matches_default_before_mesh_over_strict_threshold": bool(max_before_manifest <= STRICT_COMPARE_TOL_MM),
            "manifest_matches_explicit_geometry_bbox_over_strict_threshold": bool(max_exact_vs_manifest <= STRICT_COMPARE_TOL_MM),
        }
        if comparisons:
            report["face_zero_focus"] = comparisons[0]

        api_optimal_doc = report["api_signatures_and_docstrings"]["OCP_BRepBndLib_AddOptimal_s"].get("doc") or ""
        report["interpretation"] = {
            "observed_cache_effect": bool(
                report["comparisons"]["default_bbox_changed_after_mesh_over_strict_threshold"]
                and cache_counts_after > cache_counts_before
            ),
            "evidence_for_runner_manifest_stage": bool(
                report["comparisons"]["manifest_matches_default_after_mesh_over_strict_threshold"]
                and not report["comparisons"]["manifest_matches_default_before_mesh_over_strict_threshold"]
            ),
            "explicit_geometry_bounds_are_same_shape_cache_invariant": report["comparisons"]["explicit_geometry_bbox_stable_over_strict_threshold"],
            "api_doc_mentions_triangulation_flag": "useTriangulation" in api_optimal_doc,
            "diagnostic_conclusion": "Review raw per-face measurements; this diagnostic does not execute the binding helper or certify the asset.",
            "minimal_contract_guidance": "For persisted face identity, generate and recheck bounds using the same explicit geometry-only call BRepBndLib.AddOptimal_s(face.wrapped, box, False, False); store the resulting asset-order bounds and the canonical STEP SHA. Treat face.BoundingBox() without recorded cache provenance as a cache-sensitive observation. Keep strict tolerance unchanged.",
            "identity_limit": "This process imports the STEP once by design. Stable bounds are shown invariant before/after tessellation on the same imported shape; re-import equality is not claimed by this diagnostic.",
            "not_a_binding_or_physics_pass": True,
        }
        report["status"] = "DIAGNOSTIC_COMPLETE"
    except Exception as exc:
        report["status"] = "DIAGNOSTIC_FAILED"
        report["exception"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        if step_path is not None and step_path.is_file():
            step_sha_after = sha256(step_path)
            report["input_step_unchanged"] = {
                "sha256_before": step_sha_before,
                "sha256_after": step_sha_after,
                "bytes_after": int(step_path.stat().st_size),
                "same_bytes": step_sha_before == step_sha_after,
            }
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        source_paths = {
            "diagnostic_script": Path(__file__).resolve(),
            "asset_manifest": ASSET_MANIFEST,
            "runner": RUNNER,
            "v4_frozen_runner": FROZEN_RUNNER,
            "geometry_source": GEOMETRY_SOURCE,
            "active_binding_helper": ACTIVE_BINDING,
            "v4_frozen_binding_helper": FROZEN_BINDING,
            "cadquery_shapes_py": CADQUERY_ROOT / "occ_impl" / "shapes.py",
            "cadquery_geom_py": CADQUERY_ROOT / "occ_impl" / "geom.py",
        }
        report["source_sha256"] = {
            str(path.relative_to(REPO_ROOT)).replace("\\", "/"): sha256(path)
            for path in source_paths.values()
            if path.is_file()
        }
        report_path = ROOT / "diagnostic_report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "step_sha256_before": step_sha_before,
        "step_sha256_after": report.get("input_step_unchanged", {}).get("sha256_after"),
        "face_count": report.get("before_mesh", {}).get("face_count"),
        "mesh_shape_call_count": report["scope"]["mesh_shape_call_count"],
        "face_zero": report.get("face_zero_focus"),
        "conclusion": report.get("interpretation", {}).get("diagnostic_conclusion"),
        "report": str(ROOT / "diagnostic_report.json"),
    }, ensure_ascii=False))
    return 0 if report["status"] == "DIAGNOSTIC_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

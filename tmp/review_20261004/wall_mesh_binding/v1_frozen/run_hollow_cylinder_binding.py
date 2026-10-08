from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cadquery as cq
import numpy as np


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_inventory(root: Path, relative_paths: list[str]) -> dict[str, dict[str, Any]]:
    return {
        relative: {
            "sha256": _sha256(root / relative),
            "bytes": int((root / relative).stat().st_size),
        }
        for relative in sorted(relative_paths)
    }


def _face_inventory(shape: cq.Shape) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, face in enumerate(shape.Faces()):
        bounds = face.BoundingBox()
        rows.append({
            "index_zero_based": index,
            "geom_type": face.geomType(),
            "center_mm": [float(value) for value in face.Center().toTuple()],
            "area_mm2": float(face.Area()),
            "bbox_mm": [
                float(bounds.xmin), float(bounds.xmax),
                float(bounds.ymin), float(bounds.ymax),
                float(bounds.zmin), float(bounds.zmax),
            ],
        })
    return rows


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one analytic wall-binding fixture once.")
    parser.add_argument("--output", required=True, type=Path,
                        help="new absolute directory for the tiny generated fixture package")
    return parser.parse_args()


def main() -> int:
    args = _args()
    output = args.output
    if not output.is_absolute():
        raise ValueError("--output must be an absolute path")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite any existing output path: {output}")

    vf_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(vf_root / "src"))
    from vesselforge.geometry import mesh_shape
    from vesselforge.schema import sha256_file, validate_asset
    from vesselforge.semantics import CLASSIFIER_VERSION, classify_canonical_faces
    from vesselforge.wall_mesh_binding import _binding_from_loaded_inputs
    from vesselforge.wall_reference import build_wall_reference

    fixture = json.loads((Path(__file__).with_name("fixture_input.json")).read_text(encoding="utf-8"))
    geometry = fixture["geometry"]
    tessellation = fixture["tessellation"]
    output.mkdir(parents=True, exist_ok=False)

    # Exactly one native nested-wire extrusion: the inner wire defines the bore.
    origin = cq.Vector(0.0, 0.0, 0.0)
    axis = cq.Vector(0.0, 0.0, 1.0)
    outer_wire = cq.Wire.makeCircle(float(geometry["outer_radius_mm"]), origin, axis)
    inner_wire = cq.Wire.makeCircle(float(geometry["inner_radius_mm"]), origin, axis)
    constructed = cq.Solid.extrudeLinear(
        outer_wire, [inner_wire], cq.Vector(0.0, 0.0, float(geometry["height_mm"]))
    )

    step_rel = "geometry/solid.step"
    semantics_rel = "metadata/face_semantics.json"
    wall_ref_rel = "metadata/wall_reference.json"
    surface_rel = "geometry/surface.npz"
    lineage_rel = "geometry/mesh_lineage.npz"
    fields_rel = "fields/surface_fields.npz"
    report_rel = "validation/geometry.json"
    step_path = output / step_rel
    step_path.parent.mkdir(parents=True, exist_ok=True)

    # One STEP export and one reimport; the reimport is canonical for semantics and mesh lineage.
    cq.exporters.export(constructed, str(step_path))
    canonical = cq.importers.importStep(str(step_path)).val()
    if not canonical.isValid() or len(canonical.Solids()) != 1:
        raise ValueError("canonical STEP import is not exactly one valid solid")
    step_sha256 = sha256_file(step_path)

    linear_mm = float(tessellation["linear_chord_deflection_mm"])
    angular_rad = float(tessellation["angular_tolerance_rad"])
    spec_values = {
        "body_width_mm": 2.0 * float(geometry["outer_radius_mm"]),
        "body_height_mm": float(geometry["height_mm"]),
        "wall_mm": float(geometry["analytic_radial_wall_thickness_mm"]),
        "handle_radius_mm": 1.0,
        "handle_outreach_mm": 15.0,
        "handle_low_z_mm": 2.0,
        "handle_high_z_mm": 8.0,
        "tessellation_linear_mm": linear_mm,
        "tessellation_angular_rad": angular_rad,
    }
    spec = SimpleNamespace(**spec_values)
    semantics = classify_canonical_faces(canonical, spec, step_sha256)
    if semantics.get("status") != "PASS":
        raise ValueError(f"canonical face semantics is not PASS: {semantics.get('unknown_face_indices')}")
    wall_reference = build_wall_reference(
        semantics,
        source_geometry_sha256=step_sha256,
        units={"length": "mm", "direction": "dimensionless"},
        frame="right_handed_z_up",
        source_scope="analytic_fixture_mother",
    )
    if wall_reference.get("status") != "MOTHER_SOURCE_ONLY":
        raise ValueError("analytic fixture wall reference is not valid mother-source evidence")

    # Exactly one VF tessellation call on the canonical STEP import.
    vertices, faces, triangle_sources = mesh_shape(canonical, spec)
    regions = np.asarray(
        [semantics["faces"][int(face_id)]["region_code"] for face_id in triangle_sources],
        dtype=np.uint8,
    )
    _write_json(output / semantics_rel, semantics)
    _write_json(output / wall_ref_rel, wall_reference)
    surface_path = output / surface_rel
    surface_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(surface_path, vertices_mm=vertices, faces=faces)
    lineage_path = output / lineage_rel
    lineage_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(lineage_path, face_source_brep_index=triangle_sources)
    fields_path = output / fields_rel
    fields_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        fields_path,
        face_region=regions,
        albedo_linear_rgb=np.full((len(faces), 3), 0.5, dtype=np.float32),
        roughness=np.full(len(faces), 0.7, dtype=np.float32),
        vertices_material_xyz_mm=np.asarray(vertices, dtype=np.float64),
    )

    report = {
        "status": "PASS",
        "scope": "geometry_only",
        "fixture_id": fixture["fixture_id"],
        "tessellation_chord_deflection_target_mm": linear_mm,
        "tessellation_angular_tolerance_rad": angular_rad,
        "note": "analytic fixture construction and canonical STEP import; no global wall or physical qualification",
    }
    _write_json(output / report_rel, report)
    payload_paths = [step_rel, semantics_rel, wall_ref_rel, surface_rel,
                     lineage_rel, fields_rel, report_rel]
    manifest = {
        "schema": "forge.asset.v1",
        "units": {"length": "mm", "time": "s", "mass": "kg"},
        "frame": "right_handed_z_up",
        "geometry": {"solid_step": step_rel, "surface_npz": surface_rel},
        "fields": {"surface_fields_npz": fields_rel},
        "material": {
            "id": "analytic-fixture-unvalidated-material",
            "mechanics": {"rho_kg_m3": 2100.0, "E_pa": 5.0e9, "nu": 0.25, "Gc_j_m2": 45.0},
            "calibration_status": "UNVALIDATED_PROTOTYPE",
        },
        "ornament": {
            "kind": "painted",
            "recipe": {
                "material_binding_id": "analytic-fixture-unvalidated-material",
                "geometry_relief_mm": 0.0,
                "historical_style_validation": "NOT_VALIDATED",
                "target_region_codes": [1, 2],
            },
        },
        "files": _file_inventory(output, payload_paths),
        "provenance": {
            "producer": "wall_mesh_binding tiny analytic fixture runner",
            "version": "review-only",
            "backend": "CadQuery/OpenCascade",
            "backend_version": cq.__version__,
            "spec": {
                "parameters": spec_values,
                "face_semantics_report": semantics_rel,
                "face_semantics_classifier": CLASSIFIER_VERSION,
                "canonical_step_sha256": step_sha256,
                "tessellation": {
                    "linear_chord_deflection_mm": linear_mm,
                    "angular_tolerance_rad": angular_rad,
                },
                "mesh_lineage_npz": lineage_rel,
                "brep_face_inventory": _face_inventory(canonical),
            },
        },
        "validation": {"report": report_rel, "status": "PASS", "scope": "geometry_only"},
    }
    _write_json(output / "manifest.json", manifest)
    validation = validate_asset(output)
    if validation.get("contract_status") != "PASS" or validation.get("geometry_status") != "PASS":
        raise ValueError("tiny analytic fixture did not close the forge.asset.v1 package")

    independently_hashed = {
        "canonical_step_file_sha256": sha256_file(output / step_rel),
        "face_semantics_file_sha256": sha256_file(output / semantics_rel),
        "wall_reference_file_sha256": sha256_file(output / wall_ref_rel),
        "parent_surface_file_sha256": sha256_file(output / surface_rel),
        "parent_lineage_file_sha256": sha256_file(output / lineage_rel),
    }
    binding_record = _binding_from_loaded_inputs(
        manifest=manifest,
        asset_root=output,
        wall_reference_path=output / wall_ref_rel,
        canonical_shape=canonical,
        file_hashes=independently_hashed,
    )
    report_path = output / "metadata/wall_mesh_binding.json"
    _write_json(report_path, binding_record)
    print(json.dumps({
        "output": str(output.resolve()),
        "asset_validation": validation,
        "binding_status": binding_record.get("status"),
        "coverage": binding_record.get("coverage"),
        "input_file_sha256": binding_record.get("input_file_sha256"),
        "parent_mesh_content_sha256": binding_record.get("parent_mesh_content_sha256"),
        "global_wall_status": binding_record.get("qualification", {}).get("global_wall_status"),
        "physical_qualification_status": binding_record.get("qualification", {}).get("physical_qualification_status"),
        "report": str(report_path.resolve()),
    }, indent=2, sort_keys=True, allow_nan=False))
    if binding_record.get("status") != "PASS_MOTHER_STATION_BINDING":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

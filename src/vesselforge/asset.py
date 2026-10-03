"""Create self-contained forge.asset.v1 sample packages."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np

from .appearance import PALE_SLIP, make_recipe, per_face_band_coverage, surface_fields
from .geometry import (
    VesselSpec,
    build_components,
    export_step,
    measure_cad_floor_and_handle_roots,
    measure_profile_wall,
    mesh_shape,
    mesh_topology_metrics,
    profile_curvature_metrics,
    sampled_mesh_to_cad_metrics,
    scaled_outer_profile,
)
from .schema import sha256_file, validate_asset
from .semantics import CLASSIFIER_VERSION, REGIONS, classify_canonical_faces, triangle_region_codes


MATERIAL_ID = "vf_prototype_matte_earth_01"


def _write_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(arrays):
            payload = io.BytesIO()
            np.save(payload, arrays[name], allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"):
        relative = path.relative_to(root).as_posix()
        inventory[relative] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return inventory


def _data_dictionary() -> dict[str, Any]:
    return {
        "schema": "forge.asset.v1",
        "units": {"length": "mm", "time": "s", "mass": "kg"},
        "frame": "right_handed_z_up",
        "validity": "geometry_only prototype; no experimental mechanics or historical-style validation",
        "fields": {
            "geometry/surface.npz:vertices_mm": {"dtype": "float64", "shape": "N×3", "meaning": "surface vertex in package frame", "source": "OpenCascade absolute-deflection tessellation"},
            "geometry/surface.npz:faces": {"dtype": "int32", "shape": "F×3", "meaning": "oriented triangle indices", "source": "CadQuery/OCP tessellation"},
            "geometry/mesh_lineage.npz:face_source_brep_index": {"dtype": "int32", "shape": "F", "meaning": "canonical STEP-imported B-rep face enumeration used to tessellate each exported triangle", "validity": "audit lineage; maps every triangle to the same canonical STEP face classified in metadata/face_semantics.json; not a truth or model feature"},
            "metadata/face_semantics.json:faces": {"meaning": "one record for every canonical STEP B-rep face, including classifier version, STEP SHA-256, surface type/parameters, trimmed interior UV sample, outward normal, region, rule and evidence", "validity": "fail-closed prototype semantics for this turned vessel and swept handle; UNKNOWN blocks coloring and generation"},
            "fields/surface.npz:face_region": {"dtype": "uint8", "shape": "F", "meaning": "semantic code projected from each triangle's canonical STEP B-rep face lineage", "codes": {str(code): name for code, name in REGIONS.items()}, "validity": "all source faces must be explicitly classified; code 255 remains reserved for future fracture surfaces and is never assigned to this intact asset"},
            "fields/surface.npz:albedo_linear_rgb": {"dtype": "float32", "shape": "F×3", "meaning": "procedural optical base/slip color", "validity": "preview rule; not measured pigment/glaze"},
            "fields/surface.npz:roughness": {"dtype": "float32", "shape": "F", "meaning": "procedural optical roughness", "validity": "preview placeholder; not measured"},
            "fields/surface.npz:vertices_material_xyz_mm": {"dtype": "float64", "shape": "N×3", "meaning": "immutable asset-local rest/material coordinate for later appearance re-evaluation", "validity": "equals initial vertices; not a model feature or measured material map"},
            "material.mechanics": {"units": {"rho_kg_m3": "kg/m³", "E_pa": "Pa", "nu": "dimensionless", "Gc_j_m2": "J/m²"}, "validity": "illustrative uncalibrated placeholders", "missing_reason": "no specimen-specific mechanical test"},
            "ornament.recipe": {"meaning": "deterministic painted-band rule evaluated in cylindrical rest coordinates", "relief_mm": 0.0, "historical_style_validation": "NOT_VALIDATED", "missing_reason": "not matched to a dated/provenanced historical specimen"},
            "validation.geometry_only": {"meaning": "CAD solid, wall profile, STEP/mesh and package structure checks", "excludes": ["material calibration", "historical type/style authenticity", "impact/fracture validation", "capture/reconstruction accuracy"]},
        },
        "upstream_dependencies": [],
        "parameters": "see manifest.provenance.spec",
        "missing_evidence": {
            "physical_material_calibration": "no real material specimen tests",
            "historical_style_authenticity": "visual reference only; style not validated",
            "aging_or_capture_validation": "outside this VF prototype slice",
        },
    }


def create_asset_package(
    output_dir: str | Path,
    *,
    pattern: str = "four_bands",
    seed: int = 20261003,
    spec: VesselSpec = VesselSpec(),
) -> dict[str, Any]:
    """Build one prototype asset package without overwriting an existing package."""
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output package: {output}")
    output.mkdir(parents=True, exist_ok=True)
    spec.validate()
    body, handle, constructed_shape = build_components(spec)
    recipe = make_recipe(pattern, MATERIAL_ID, spec)

    surface_rel = "geometry/surface.npz"
    lineage_rel = "geometry/mesh_lineage.npz"
    fields_rel = "fields/surface.npz"
    step_rel = "geometry/solid.step"
    report_rel = "validation/geometry.json"
    dictionary_rel = "metadata/data_dictionary.json"
    face_semantics_rel = "metadata/face_semantics.json"
    export_step(constructed_shape, str(output / step_rel))

    # The STEP re-import is canonical for the delivered mesh and its trimmed
    # surface checks, avoiding source-to-imported face-ID heuristics.
    canonical = cq.importers.importStep(str(output / step_rel)).val()
    if not canonical.isValid() or len(canonical.Solids()) != 1 or len(canonical.Shells()) != 1:
        raise ValueError("STEP re-import did not preserve one valid solid/shell")
    canonical_step_sha256 = sha256_file(output / step_rel)
    face_semantics = classify_canonical_faces(canonical, spec, canonical_step_sha256)
    _write_json(output / face_semantics_rel, face_semantics)
    if face_semantics["status"] != "PASS":
        raise ValueError(
            "canonical B-rep contains UNKNOWN/PENDING faces; asset coloring/generation is blocked: "
            f"{face_semantics['unknown_face_indices']}"
        )
    vertices, faces, triangle_sources = mesh_shape(canonical, spec)
    material_xyz = vertices.copy()
    region = triangle_region_codes(face_semantics, triangle_sources)
    _, albedo, roughness = surface_fields(material_xyz, faces, recipe, region)
    appearance_coverage = per_face_band_coverage(material_xyz, faces, region, recipe)
    _write_deterministic_npz(output / surface_rel, {"vertices_mm": vertices, "faces": faces})
    _write_deterministic_npz(output / lineage_rel, {"face_source_brep_index": triangle_sources})
    _write_deterministic_npz(
        output / fields_rel,
        {
            "face_region": region,
            "albedo_linear_rgb": albedo,
            "roughness": roughness,
            "vertices_material_xyz_mm": material_xyz,
        },
    )
    topo = mesh_topology_metrics(vertices, faces)
    wall = measure_profile_wall(spec)
    cad_sections = measure_cad_floor_and_handle_roots(body, handle, constructed_shape, spec)
    curvature = profile_curvature_metrics(spec)
    mesh_step_metrics = sampled_mesh_to_cad_metrics(canonical, vertices, faces, triangle_sources)
    mesh_step_deviation = mesh_step_metrics["max_sampled_deviation_mm"]
    bounds = canonical.BoundingBox()
    construction_bounds = constructed_shape.BoundingBox()
    body_volume = float(canonical.Volume())
    construction_volume = float(constructed_shape.Volume())
    round_trip_bbox_delta_mm = {
        "x": float(abs(construction_bounds.xlen - bounds.xlen)),
        "y": float(abs(construction_bounds.ylen - bounds.ylen)),
        "z": float(abs(construction_bounds.zlen - bounds.zlen)),
    }
    round_trip_volume_delta_mm3 = float(abs(construction_volume - body_volume))
    round_trip_volume_relative_delta = round_trip_volume_delta_mm3 / max(abs(construction_volume), 1e-12)
    round_trip = {
        "construction_solid_valid": bool(constructed_shape.isValid()),
        "canonical_step_solid_valid": bool(canonical.isValid()),
        "construction_solid_count": len(constructed_shape.Solids()),
        "canonical_step_solid_count": len(canonical.Solids()),
        "construction_shell_count": len(constructed_shape.Shells()),
        "canonical_step_shell_count": len(canonical.Shells()),
        "construction_volume_mm3": construction_volume,
        "canonical_step_volume_mm3": body_volume,
        "absolute_volume_delta_mm3": round_trip_volume_delta_mm3,
        "relative_volume_delta": round_trip_volume_relative_delta,
        "bbox_axis_delta_mm": round_trip_bbox_delta_mm,
        "acceptance_limits": {"relative_volume_delta_max": 0.001, "bbox_axis_delta_mm_max": 0.05},
        "canonical_asset_entity": "STEP-imported solid used for delivered surface mesh, triangle lineage, fields, and sampled trimmed-surface QA",
    }
    qa_checks = {
        "cad_valid_positive_volume": bool(canonical.isValid() and body_volume > 0),
        "one_connected_solid_and_shell": bool(len(canonical.Solids()) == 1 and len(canonical.Shells()) == 1),
        "step_round_trip_one_solid": bool(canonical.isValid() and len(canonical.Solids()) == 1),
        "step_round_trip_volume_and_size_within_limits": bool(
            round_trip_volume_relative_delta <= 0.001
            and max(round_trip_bbox_delta_mm.values()) <= 0.05
        ),
        "surface_mesh_watertight": bool(topo["watertight"] and topo["signed_volume_mm3"] > 0),
        "analytic_normal_offset_sidewall_minimum_met": bool(wall["analytic_min_side_profile_separation_mm"] >= spec.wall_mm - 0.02),
        "cad_floor_face_separation_met": bool(cad_sections["cad_floor_face_separation_mm"] >= spec.wall_mm - 0.02),
        "both_handle_roots_cad_connected": all(value["cad_valid"] for value in cad_sections["handle_attachment_windows"].values()),
        "positive_body_handle_intersection": bool(cad_sections["body_handle_intersection_volume_mm3"] > 0),
        "mesh_to_step_sampled_deviation_within_tolerance": bool(
            mesh_step_metrics["unknown_sample_count"] == 0
            and mesh_step_deviation is not None
            and float(mesh_step_deviation) <= spec.tessellation_linear_mm + 1e-8
        ),
        "all_canonical_brep_faces_semantically_classified": bool(
            face_semantics["status"] == "PASS"
            and face_semantics["canonical_step_face_count"] == len(canonical.Faces())
            and not face_semantics["unknown_face_indices"]
        ),
        "triangle_regions_follow_canonical_brep_lineage": bool(
            np.array_equal(region, triangle_region_codes(face_semantics, triangle_sources))
        ),
        "handle_surfaces_excluded_from_paint": bool(
            np.array_equal(
                albedo[region == 5],
                np.tile(np.asarray(PALE_SLIP, dtype=np.float32), (int(np.count_nonzero(region == 5)), 1)),
            )
        ),
        "paint_is_optical_only": recipe["geometry_relief_mm"] == 0.0,
    }
    status = "PASS" if all(qa_checks.values()) else "FAIL"
    report = {
        "status": status,
        "scope": "geometry_only",
        "algorithm": "CadQuery/OCP meridian revolve + miter-normal wall offset + swept round handle + boolean fuse",
        "seed": int(seed),
        "backend": {"name": "CadQuery/OpenCascade", "cadquery_version": cq.__version__},
        "parameters": {**spec.__dict__},
        "measurements": {
            "solid_volume_mm3": body_volume,
            "step_round_trip": round_trip,
            "bbox_mm": {"x": float(bounds.xlen), "y": float(bounds.ylen), "z": float(bounds.zlen)},
            "solid_count": len(canonical.Solids()),
            "shell_count": len(canonical.Shells()),
            "step_solid_count": len(canonical.Solids()),
            "wall": wall,
            "actual_cad_sections": cad_sections,
            "mesh": topo,
            "appearance_coverage": {
                **appearance_coverage,
                "continuous_rest_coordinate_rule": "defined by ornament.recipe; independent of triangulation and ready for material-coordinate shader evaluation",
                "continuous_shader_preview_status": "PENDING",
            },
            "face_semantics": {
                "report": face_semantics_rel,
                "classifier": CLASSIFIER_VERSION,
                "canonical_step_sha256": canonical_step_sha256,
                "status": face_semantics["status"],
                "face_count": face_semantics["canonical_step_face_count"],
                "region_counts": face_semantics["counts"],
                "unknown_face_indices": face_semantics["unknown_face_indices"],
                "handle_triangle_count": int(np.count_nonzero(region == 5)),
            },
            "mesh_to_canonical_step_max_sampled_deviation_mm": mesh_step_deviation,
            "mesh_to_canonical_step_deviation": mesh_step_metrics,
            "tessellation_chord_deflection_target_mm": spec.tessellation_linear_mm,
            "tessellation_deflection_mode": "absolute_mm (OCP BRepMesh_IncrementalMesh isRelative=False)",
            "tessellation_angular_tolerance_rad": spec.tessellation_angular_rad,
            "curvature": curvature,
            "profile_realism_status": "REALISM_PENDING: piecewise-linear meridian corners are not filleted; tessellation does not smooth them",
            "handle_fusion": {
                "method": "round-profile CAD sweep followed by OCC boolean fuse and clean",
                "single_solid_after_fuse": len(constructed_shape.Solids()) == 1,
                "body_handle_intersection_volume_mm3": cad_sections["body_handle_intersection_volume_mm3"],
                "attachment_windows": cad_sections["handle_attachment_windows"],
            },
        },
        "checks": qa_checks,
        "limitations": [
            "No physical impact/fracture test or material calibration was performed.",
            "The meridian is piecewise linear; report identifies unfilleted curvature breaks.",
            "Profile realism remains pending until a sourced smooth spline/fillet profile is implemented and reviewed.",
            "Semantic regions use canonical STEP B-rep surface type, axis/location and face-oriented normal rules for this prototype form; any unknown face blocks coloring and package generation.",
            "Per-triangle color arrays are a low-order rest-coordinate centroid approximation; continuous shader rendering evaluates the rule independently of triangulation.",
            "The pattern is painted-only, optical fields are procedural placeholders, and historical style is NOT_VALIDATED.",
            "Sampled mesh-to-STEP deviation is a finite sample, not a global Hausdorff bound.",
        ],
    }
    _write_json(output / report_rel, report)
    _write_json(output / dictionary_rel, _data_dictionary())

    files = _file_inventory(output)
    manifest = {
        "schema": "forge.asset.v1",
        "units": {"length": "mm", "time": "s", "mass": "kg"},
        "frame": "right_handed_z_up",
        "geometry": {"surface_npz": surface_rel, "solid_step": step_rel},
        "fields": {"surface_fields_npz": fields_rel},
        "material": {
            "id": MATERIAL_ID,
            "appearance": {
                "model": "constant_lambertian_preview",
                "base_albedo_linear_rgb": list(PALE_SLIP),
                "roughness": 0.78,
                "source": "prototype display palette; not measured optical data",
            },
            "mechanics": {"rho_kg_m3": 2100.0, "E_pa": 5.0e9, "nu": 0.25, "Gc_j_m2": 45.0},
            "calibration_status": "UNVALIDATED_PROTOTYPE",
            "provenance": {
                "mechanics_source": "illustrative solver placeholders selected for package/API exercise; no specimen test or calibration; nu=0.25 for BB 3D material API compatibility, never silently coerced by an adapter",
                "appearance_source": "procedural preview palette; no spectrophotometry or glaze measurement",
            },
        },
        "ornament": {"kind": "painted", "recipe": recipe},
        "files": files,
        "provenance": {
            "producer": "VesselForge Core",
            "version": "0.1.1",
            "backend": "CadQuery/OpenCascade",
            "backend_version": cq.__version__,
            "seed": int(seed),
            "spec": {
                "prototype_form": "small_open_turned_vessel_with_swept_fused_handle",
                "historical_type_label": None,
                "parameters": {**spec.__dict__},
                "meridian_profile_mm": [[float(r), float(z)] for r, z in scaled_outer_profile(spec)],
                "wall_offset_method": "mitered normal offset in meridian profile; floor thickness separately set to wall_mm",
                "surface_semantics": {str(code): name for code, name in REGIONS.items()},
                "surface_semantics_validity": "face-level classification from canonical STEP B-rep surface type, axis/location, trimmed-domain interior sample and face-oriented outward normal; UNKNOWN blocks output; code 255 remains reserved for future fracture surfaces",
                "face_semantics_report": face_semantics_rel,
                "face_semantics_classifier": CLASSIFIER_VERSION,
                "canonical_step_sha256": canonical_step_sha256,
                "tessellation": {"linear_chord_deflection_mm": spec.tessellation_linear_mm, "angular_tolerance_rad": spec.tessellation_angular_rad},
                "data_dictionary": dictionary_rel,
                "mesh_lineage_npz": lineage_rel,
                "brep_face_inventory": [
                    {
                        "index_zero_based": index,
                        "geom_type": face.geomType(),
                        "center_mm": [float(value) for value in face.Center().toTuple()],
                        "area_mm2": float(face.Area()),
                        "bbox_mm": [
                            float(face.BoundingBox().xmin), float(face.BoundingBox().xmax),
                            float(face.BoundingBox().ymin), float(face.BoundingBox().ymax),
                            float(face.BoundingBox().zmin), float(face.BoundingBox().zmax),
                        ],
                    }
                        for index, face in enumerate(canonical.Faces())
                ],
                "upstream_dependencies": [],
                "validity": "prototype geometry-only; historical, physical and capture status unknown/unvalidated",
                "missing_reason": "no specimen-specific material, chronology, ornament or capture ground truth",
            },
        },
        "validation": {"report": report_rel, "status": status, "scope": "geometry_only"},
    }
    _write_json(output / "manifest.json", manifest)
    validation = validate_asset(output)
    if status != "PASS":
        raise ValueError(f"generated geometry failed checks: {qa_checks}")
    return {"manifest": manifest, "validation": validation, "report": report}


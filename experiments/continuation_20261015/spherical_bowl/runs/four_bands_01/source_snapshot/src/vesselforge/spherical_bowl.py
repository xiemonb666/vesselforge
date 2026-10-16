"""Analytic concentric hemispherical bowl assets and solver-point sampling.

This is an independent geometry path.  It deliberately leaves the legacy
``VesselSpec`` and ``create_asset_package`` prototype unchanged.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import cadquery as cq
import numpy as np
import OCP
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Sphere

from .appearance import DARK_PAINT, PALE_SLIP, PATTERNS, RED_PAINT, evaluate_continuous_albedo_at_z, per_face_band_coverage, surface_fields
from .asset import _file_inventory, _write_deterministic_npz, _write_json
from .brep_identity import brep_bounds_mm
from .geometry import mesh_shape, mesh_topology_metrics, sampled_mesh_to_cad_metrics
from .schema import sha256_file, validate_asset
from .semantics import _interior_sample, triangle_region_codes


SPHERICAL_BOWL_CLASSIFIER_VERSION = "vf.canonical-step-face-semantics/1.1.0-spherical-bowl"
_REGION_NAMES = {1: "body_outer", 2: "body_inner", 3: "natural_rim", 4: "base", 5: "handle"}
_REGION_CODES = {str(code): name for code, name in _REGION_NAMES.items()}
_GEOMETRY_TOLERANCE_MM = 2e-6
_MATERIAL_ID = "vf_prototype_matte_earth_01"
_MAX_LATTICE_CANDIDATES = 2_000_000


@dataclass(frozen=True)
class BowlSpec:
    """Concentric lower-hemisphere shell, in millimetres and Z-up coordinates."""

    outer_radius_mm: float = 12.0
    inner_radius_mm: float = 8.0
    center_xyz_mm: tuple[float, float, float] = (0.0, 0.0, 12.0)
    tessellation_linear_mm: float = 0.04
    tessellation_angular_rad: float = 0.02

    def validate(self) -> None:
        for name in ("outer_radius_mm", "inner_radius_mm", "tessellation_linear_mm", "tessellation_angular_rad"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
        if self.outer_radius_mm <= 0.0:
            raise ValueError("outer_radius_mm must be positive")
        if self.inner_radius_mm <= 0.0 or self.inner_radius_mm >= self.outer_radius_mm:
            raise ValueError("inner_radius_mm must be positive and smaller than outer_radius_mm")
        if not isinstance(self.center_xyz_mm, (tuple, list)) or len(self.center_xyz_mm) != 3:
            raise ValueError("center_xyz_mm must contain exactly three finite values")
        for coordinate in self.center_xyz_mm:
            if isinstance(coordinate, (bool, np.bool_)) or not isinstance(coordinate, (int, float, np.number)) or not math.isfinite(float(coordinate)):
                raise ValueError("center_xyz_mm must contain exactly three finite values")
        if not 0.04 <= float(self.tessellation_linear_mm) <= 0.25:
            raise ValueError("tessellation_linear_mm must lie in [0.04, 0.25]")
        if not 0.02 <= float(self.tessellation_angular_rad) <= 0.20:
            raise ValueError("tessellation_angular_rad must lie in [0.02, 0.20]")

    @property
    def center(self) -> np.ndarray:
        self.validate()
        return np.asarray(self.center_xyz_mm, dtype=np.float64)

    @property
    def bottom_z_mm(self) -> float:
        return float(self.center_xyz_mm[2]) - float(self.outer_radius_mm)

    @property
    def ideal_wall_thickness_mm(self) -> float:
        return float(self.outer_radius_mm) - float(self.inner_radius_mm)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "shape": "concentric_lower_hemisphere",
            "units": {"length": "mm"},
            "outer_radius_mm": float(self.outer_radius_mm),
            "inner_radius_mm": float(self.inner_radius_mm),
            "center_xyz_mm": [float(value) for value in self.center_xyz_mm],
            "hemisphere": "z <= center_z; open annular rim lies at center_z",
            "ideal_normal_wall_thickness_mm": self.ideal_wall_thickness_mm,
            "wall_status": "ANALYTIC_DESIGN_VALUE_NOT_MEASURED_OR_GLOBALLY_VERIFIED",
            "tessellation_linear_mm": float(self.tessellation_linear_mm),
            "tessellation_angular_rad": float(self.tessellation_angular_rad),
        }


@dataclass(frozen=True)
class SolverPointCloud:
    """Voxel-centroid lattice points and an explicit h-cubed volume estimate."""

    points_mm: np.ndarray
    metadata: dict[str, Any]


def analytic_spherical_bowl_volume_mm3(spec: BowlSpec = BowlSpec()) -> float:
    """Exact solid volume: outer lower hemisphere less its inner cavity."""
    spec.validate()
    return float((2.0 * math.pi / 3.0) * (spec.outer_radius_mm**3 - spec.inner_radius_mm**3))


def build_spherical_bowl_solid(spec: BowlSpec = BowlSpec()) -> cq.Shape:
    """Revolve the exact circular meridian of a concentric hemispherical bowl."""
    spec.validate()
    ro = float(spec.outer_radius_mm)
    ri = float(spec.inner_radius_mm)
    cx, cy, cz = (float(value) for value in spec.center_xyz_mm)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    profile = (
        cq.Workplane("XZ")
        .moveTo(0.0, cz - ro)
        .threePointArc((ro * inv_sqrt2, cz - ro * inv_sqrt2), (ro, cz))
        .lineTo(ri, cz)
        .threePointArc((ri * inv_sqrt2, cz - ri * inv_sqrt2), (0.0, cz - ri))
        .close()
    )
    shape = profile.revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)).val()
    if cx != 0.0 or cy != 0.0:
        shape = shape.translate((cx, cy, 0.0))
    if not shape.isValid() or len(shape.Solids()) != 1 or len(shape.Shells()) != 1:
        raise ValueError("spherical bowl did not produce one valid solid and shell")
    if not shape.Shells()[0].Closed() or not math.isfinite(float(shape.Volume())) or shape.Volume() <= 0.0:
        raise ValueError("spherical bowl shell is open or has non-positive volume")
    return shape


def _point_xyz(value: Any, label: str) -> np.ndarray:
    try:
        point = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite XYZ point in mm") from exc
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError(f"{label} must be a finite XYZ point in mm")
    return point


def contains_material(
    point_xyz_mm: Any,
    spec: BowlSpec = BowlSpec(),
    *,
    tolerance_mm: float = 1e-9,
) -> bool:
    """Boundary-inclusive exact test for the lower hemispherical shell."""
    spec.validate()
    point = _point_xyz(point_xyz_mm, "point_xyz_mm")
    tol = float(tolerance_mm)
    if not math.isfinite(tol) or tol < 0.0:
        raise ValueError("tolerance_mm must be finite and non-negative")
    delta = point - spec.center
    distance = float(np.linalg.norm(delta))
    return bool(
        point[2] <= float(spec.center_xyz_mm[2]) + tol
        and distance <= float(spec.outer_radius_mm) + tol
        and distance >= float(spec.inner_radius_mm) - tol
    )


def segment_in_material(
    start_xyz_mm: Any,
    end_xyz_mm: Any,
    spec: BowlSpec = BowlSpec(),
    *,
    tolerance_mm: float = 1e-9,
) -> bool:
    """Return whether every point of a straight segment lies in the shell.

    The test clips the parameter interval to the lower half-space, checks the
    outer sphere at the clipped endpoints, and checks the closest point to the
    common center against the inner sphere. It is analytic, not sampled.
    """
    spec.validate()
    a = _point_xyz(start_xyz_mm, "start_xyz_mm")
    b = _point_xyz(end_xyz_mm, "end_xyz_mm")
    tol = float(tolerance_mm)
    if not math.isfinite(tol) or tol < 0.0:
        raise ValueError("tolerance_mm must be finite and non-negative")
    direction = b - a
    center = spec.center
    # The full segment must satisfy the non-concave shell's endpoint and
    # half-space constraints. The outer ball and lower half-space are convex,
    # so endpoint containment proves those constraints along the segment.
    if not contains_material(a, spec, tolerance_mm=tol) or not contains_material(b, spec, tolerance_mm=tol):
        return False
    direction_squared = float(np.dot(direction, direction))
    if direction_squared == 0.0:
        return True

    center_projection_t = -float(np.dot(a - center, direction)) / direction_squared
    closest_t = min(max(center_projection_t, 0.0), 1.0)
    closest = a + closest_t * direction
    return bool(np.linalg.norm(closest - center) >= float(spec.inner_radius_mm) - tol)


def generate_solver_points(
    spec: BowlSpec = BowlSpec(),
    *,
    spacing_mm: float = 1.0,
    horizon_mm: float = 3.0,
) -> SolverPointCloud:
    """Sample a voxel-centroid lattice; estimate volume as accepted_count*h³.

    Cells are selected by their centroids only. This does not claim that every
    accepted voxel is wholly inside the solid or that boundary cells are cut.
    """
    spec.validate()
    for name, value in (("spacing_mm", spacing_mm), ("horizon_mm", horizon_mm)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)) or not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"{name} must be a finite positive number")
    spacing = float(spacing_mm)
    horizon = float(horizon_mm)
    if horizon < spacing:
        raise ValueError("horizon_mm must be at least spacing_mm")

    cx, cy, cz = (float(value) for value in spec.center_xyz_mm)
    lower = np.asarray([cx - spec.outer_radius_mm, cy - spec.outer_radius_mm, cz - spec.outer_radius_mm], dtype=np.float64)
    upper = np.asarray([cx + spec.outer_radius_mm, cy + spec.outer_radius_mm, cz], dtype=np.float64)
    axis_cell_counts: list[int] = []
    for lo, hi in zip(lower, upper):
        raw_cell_count = (hi - lo) / spacing
        if not math.isfinite(raw_cell_count):
            raise ValueError("spacing_mm is too small to represent a finite lattice")
        axis_cell_counts.append(int(math.floor(raw_cell_count + 1e-12)))
    candidate_count = math.prod(axis_cell_counts)
    if candidate_count > _MAX_LATTICE_CANDIDATES:
        raise ValueError(
            f"centroid lattice would create {candidate_count} candidates; "
            f"limit is {_MAX_LATTICE_CANDIDATES}"
        )
    if candidate_count == 0:
        raise ValueError("spacing_mm is too large to produce any lattice candidates")

    axis_values = [
        lo + (np.arange(cell_count, dtype=np.float64) + 0.5) * spacing
        for lo, cell_count in zip(lower, axis_cell_counts)
    ]
    xx, yy, zz = np.meshgrid(*axis_values, indexing="ij")
    candidates = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    centered = candidates - spec.center
    distance = np.linalg.norm(centered, axis=1)
    selected = (distance <= spec.outer_radius_mm) & (distance >= spec.inner_radius_mm)
    points = np.asarray(candidates[selected], dtype=np.float64)
    exact_volume = analytic_spherical_bowl_volume_mm3(spec)
    estimate = float(len(points) * spacing**3)
    absolute_error = abs(estimate - exact_volume)
    metadata = {
        "schema": "vf.solver_centroid_lattice.v1",
        "coordinate_units": "mm",
        "coordinate_frame": "right_handed_z_up",
        "point_count": int(len(points)),
        "spacing_mm": spacing,
        "horizon_mm": horizon,
        "horizon_to_spacing_ratio": horizon / spacing,
        "lattice_lower_corner_xyz_mm": lower.tolist(),
        "lattice_cell_centroid_offset_mm": [spacing / 2.0] * 3,
        "selection": "centroid lies in the analytic lower hemispherical shell; boundary-inclusive to 1e-9 mm",
        "volume_estimator": "accepted_centroid_count_times_spacing_cubed",
        "voxel_volume_mm3": spacing**3,
        "estimated_volume_mm3": estimate,
        "analytic_volume_mm3": exact_volume,
        "absolute_volume_error_mm3": absolute_error,
        "relative_volume_error": absolute_error / exact_volume,
        "cell_claim": "centroid-selected cells are not asserted to lie wholly inside the solid; boundary cells are not clipped",
        "spec": spec.to_dict(),
    }
    return SolverPointCloud(points_mm=points, metadata=metadata)


def _pattern_recipe(pattern: str, spec: BowlSpec, seed: int) -> dict[str, Any]:
    if pattern not in PATTERNS:
        raise ValueError(f"unsupported prototype pattern: {pattern}")
    scale = float(spec.outer_radius_mm) / 56.0
    bottom_z = spec.bottom_z_mm
    bands = [
        {
            **band,
            "center_z_mm": bottom_z + float(band["center_z_mm"]) * scale,
            "width_mm": float(band["width_mm"]) * scale,
        }
        for band in PATTERNS[pattern]["bands"]
    ]
    return {
        "pattern_id": pattern,
        "material_binding_id": _MATERIAL_ID,
        "coordinate_map": "world_xyz_rest_mm; band centers use global Z",
        "target_region_codes": [1],
        "fracture_region_codes_excluded": [255],
        "bands": bands,
        "palette_linear_rgb": {"base": list(PALE_SLIP), "dark": list(DARK_PAINT), "red": list(RED_PAINT)},
        "surface_finish": {"model": "constant_lambertian_preview", "roughness": 0.78},
        "geometry_relief_mm": 0.0,
        "historical_style_validation": "NOT_VALIDATED",
        "seed": int(seed),
        "source_note": "Deterministic procedural paint candidate; not matched to a dated or provenanced specimen.",
    }


def evaluate_bowl_paint_at_xyz(xyz_mm: Any, recipe: Mapping[str, Any]) -> np.ndarray:
    """Evaluate continuous bands at arbitrary rest-coordinate XYZ samples."""
    xyz = np.asarray(xyz_mm, dtype=np.float64)
    if xyz.ndim < 1 or xyz.shape[-1] != 3 or not np.isfinite(xyz).all():
        raise ValueError("xyz_mm must be finite coordinates with shape (..., 3)")
    return evaluate_continuous_albedo_at_z(xyz[..., 2], dict(recipe))


def _backend_versions() -> dict[str, str]:
    try:
        ocp_distribution = package_version("cadquery-ocp")
    except PackageNotFoundError:
        ocp_distribution = "unknown"
    return {
        "cadquery_version": str(cq.__version__),
        "ocp_module_version": str(getattr(OCP, "__version__", "unknown")),
        "ocp_distribution_version": str(ocp_distribution),
    }


def classify_spherical_bowl_faces(shape: cq.Shape, spec: BowlSpec, step_sha256: str) -> dict[str, Any]:
    """Fail-closed canonical STEP face classifier for this three-face shape."""
    spec.validate()
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    unknown_indices: list[int] = []
    expected_center = spec.center
    for index, face in enumerate(shape.Faces()):
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        surface_type = adaptor.GetType()
        kind = "sphere" if surface_type == GeomAbs_Sphere else "plane" if surface_type == GeomAbs_Plane else "unsupported"
        sample = _interior_sample(face, adaptor)
        row: dict[str, Any] = {
            "face_index_zero_based": index,
            "status": "UNKNOWN",
            "region_code": None,
            "region_name": "UNKNOWN",
            "surface_type": kind,
            "surface_parameters": {},
            "interior_sample": sample,
            "face_area_mm2": float(face.Area()),
            "classifier_version": SPHERICAL_BOWL_CLASSIFIER_VERSION,
            "canonical_step_sha256": step_sha256,
            "classification_basis": None,
            "reason": None,
        }
        if sample is None:
            row["reason"] = "no valid trimmed-face UV sample with defined oriented normal"
        elif surface_type == GeomAbs_Sphere:
            sphere = adaptor.Sphere()
            center_gp = sphere.Location()
            center = np.asarray([center_gp.X(), center_gp.Y(), center_gp.Z()], dtype=np.float64)
            point = np.asarray(sample["point_mm"], dtype=np.float64)
            normal = np.asarray(sample["oriented_outward_normal"], dtype=np.float64)
            radius = float(sphere.Radius())
            row["surface_parameters"] = {"radius_mm": radius, "center_xyz_mm": center.tolist()}
            radial_dot = float(np.dot(point - center, normal))
            if np.linalg.norm(center - expected_center) > _GEOMETRY_TOLERANCE_MM:
                row["reason"] = "sphere center does not match BowlSpec"
            elif abs(radius - float(spec.outer_radius_mm)) <= _GEOMETRY_TOLERANCE_MM and radial_dot > _GEOMETRY_TOLERANCE_MM:
                row.update({"status": "CLASSIFIED", "region_code": 1, "region_name": _REGION_NAMES[1], "classification_basis": "sphere radius matches outer radius and oriented normal points away from the common center", "classification_evidence": {"radial_normal_dot_mm": radial_dot}})
            elif abs(radius - float(spec.inner_radius_mm)) <= _GEOMETRY_TOLERANCE_MM and radial_dot < -_GEOMETRY_TOLERANCE_MM:
                row.update({"status": "CLASSIFIED", "region_code": 2, "region_name": _REGION_NAMES[2], "classification_basis": "sphere radius matches inner radius and oriented normal points toward the common center", "classification_evidence": {"radial_normal_dot_mm": radial_dot}})
            else:
                row["reason"] = "sphere radius or oriented normal does not match declared inner/outer shell"
        elif surface_type == GeomAbs_Plane:
            plane = adaptor.Plane()
            plane_location = plane.Location()
            origin = np.asarray([plane_location.X(), plane_location.Y(), plane_location.Z()], dtype=np.float64)
            normal = np.asarray(sample["oriented_outward_normal"], dtype=np.float64)
            row["surface_parameters"] = {"origin_xyz_mm": origin.tolist(), "normal_xyz": normal.tolist()}
            if abs(float(origin[2]) - float(spec.center_xyz_mm[2])) <= _GEOMETRY_TOLERANCE_MM and normal[2] > 1.0 - 1e-6:
                row.update({"status": "CLASSIFIED", "region_code": 3, "region_name": _REGION_NAMES[3], "classification_basis": "open horizontal annular rim at the declared sphere center height with outward normal +Z", "classification_evidence": {"rim_z_mm": float(spec.center_xyz_mm[2]), "normal_z": float(normal[2])}})
            else:
                row["reason"] = "plane does not match the declared open annular rim"
        else:
            row["reason"] = f"unsupported canonical B-rep surface type: {kind}"
        if row["status"] == "CLASSIFIED":
            counts[str(row["region_name"])] += 1
        else:
            unknown_indices.append(index)
        rows.append(row)

    return {
        "schema": "vf.brep-face-semantics.v1",
        "status": "PASS" if rows and not unknown_indices else "PENDING",
        "classifier": SPHERICAL_BOWL_CLASSIFIER_VERSION,
        "backend": _backend_versions(),
        "canonical_step_sha256": step_sha256,
        "canonical_step_face_count": len(rows),
        "region_codes": _REGION_CODES,
        "fracture_reserve_code": 255,
        "counts": dict(sorted(counts.items())),
        "unknown_face_indices": unknown_indices,
        "unknown_blocks_coloring_and_generation": True,
        "faces": rows,
    }


def _data_dictionary() -> dict[str, Any]:
    return {
        "schema": "forge.asset.v1",
        "units": {"length": "mm", "time": "s", "mass": "kg"},
        "frame": "right_handed_z_up",
        "validity": "analytic geometry and procedural paint only; no specimen calibration or historical style validation",
        "fields": {
            "geometry/surface.npz:vertices_mm": {"dtype": "float64", "shape": "N×3", "meaning": "canonical STEP surface vertex in millimetres"},
            "geometry/surface.npz:faces": {"dtype": "int32", "shape": "F×3", "meaning": "oriented triangle indices"},
            "geometry/mesh_lineage.npz:face_source_brep_index": {"dtype": "int32", "shape": "F", "meaning": "canonical STEP face index for each triangle"},
            "metadata/face_semantics.json:faces": {"meaning": "auditable outer sphere, inner sphere, and annular-rim classifications bound to the STEP SHA-256"},
            "fields/surface.npz:face_region": {"dtype": "uint8", "shape": "F", "meaning": "semantic region projected through triangle-to-face lineage", "region_codes": _REGION_CODES},
            "fields/surface.npz:albedo_linear_rgb": {"dtype": "float32", "shape": "F×3", "meaning": "paint values sampled at triangle rest-coordinate centroids"},
            "fields/surface.npz:vertices_material_xyz_mm": {"dtype": "float64", "shape": "N×3", "meaning": "immutable source-mother rest coordinates for continuous paint re-evaluation"},
            "solver_points": {"meaning": "generated separately by generate_solver_points; centroid lattice with h-cubed approximate volume; accepted cells are not claimed fully inside"},
            "material.mechanics": {"validity": "illustrative UNVALIDATED_PROTOTYPE placeholders; not experimental calibration"},
            "ornament.recipe": {"meaning": "continuous deterministic painted bands evaluated from rest-coordinate Z", "geometry_relief_mm": 0.0, "historical_style_validation": "NOT_VALIDATED"},
        },
        "parameters": "see manifest.provenance.spec",
        "missing_evidence": {"material_calibration": "no specimen-specific tests", "historical_style": "not matched to a dated/provenanced specimen", "impact_fracture": "outside this geometry-only package"},
    }


def create_spherical_bowl_asset_package(
    output_dir: str | os.PathLike[str],
    *,
    pattern: str = "four_bands",
    seed: int = 20261015,
    spec: BowlSpec = BowlSpec(),
) -> dict[str, Any]:
    """Write one ``forge.asset.v1`` bowl package without replacing existing data."""
    spec.validate()
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be an integer")
    output = Path(output_dir)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError(f"refusing to overwrite non-empty output package: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for directory in ("geometry", "fields", "metadata", "validation"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    recipe = _pattern_recipe(pattern, spec, int(seed))

    step_rel = "geometry/solid.step"
    surface_rel = "geometry/surface.npz"
    lineage_rel = "geometry/mesh_lineage.npz"
    fields_rel = "fields/surface.npz"
    semantics_rel = "metadata/face_semantics.json"
    dictionary_rel = "metadata/data_dictionary.json"
    report_rel = "validation/geometry.json"

    constructed = build_spherical_bowl_solid(spec)
    cq.exporters.export(constructed, str(output / step_rel), exportType="STEP")
    canonical = cq.importers.importStep(str(output / step_rel)).val()
    if not canonical.isValid() or len(canonical.Solids()) != 1 or len(canonical.Shells()) != 1 or not canonical.Shells()[0].Closed():
        raise ValueError("STEP re-import did not preserve one valid solid and closed shell")

    canonical_step_sha256 = sha256_file(output / step_rel)
    semantics = classify_spherical_bowl_faces(canonical, spec, canonical_step_sha256)
    _write_json(output / semantics_rel, semantics)
    if semantics["status"] != "PASS":
        raise ValueError(f"canonical STEP has unclassified faces: {semantics['unknown_face_indices']}")

    vertices, faces, triangle_sources = mesh_shape(canonical, spec)
    region = triangle_region_codes(semantics, triangle_sources)
    _, albedo, roughness = surface_fields(vertices.copy(), faces, recipe, region)
    _write_deterministic_npz(output / surface_rel, {"vertices_mm": vertices, "faces": faces})
    _write_deterministic_npz(output / lineage_rel, {"face_source_brep_index": triangle_sources})
    _write_deterministic_npz(
        output / fields_rel,
        {
            "face_region": region,
            "albedo_linear_rgb": albedo,
            "roughness": roughness,
            "vertices_material_xyz_mm": vertices.copy(),
        },
    )

    topology = mesh_topology_metrics(vertices, faces)
    mesh_step = sampled_mesh_to_cad_metrics(canonical, vertices, faces, triangle_sources)
    analytic_volume = analytic_spherical_bowl_volume_mm3(spec)
    cad_volume = float(canonical.Volume())
    relative_volume_error = abs(cad_volume - analytic_volume) / analytic_volume
    construction_bounds = brep_bounds_mm(constructed)
    canonical_bounds = brep_bounds_mm(canonical)
    bounds_delta = max(abs(a - b) for a, b in zip(construction_bounds, canonical_bounds))
    coverage = per_face_band_coverage(vertices, faces, region, recipe)
    per_face_coverage_pass = coverage["per_face_approximation_status"] == "PASS"
    continuous_heights = np.linspace(spec.bottom_z_mm, float(spec.center_xyz_mm[2]), 257, dtype=np.float64)
    continuous_rgb = evaluate_continuous_albedo_at_z(continuous_heights, recipe)
    continuous_checks = {
        "finite": bool(np.isfinite(continuous_rgb).all()),
        "rgb_bounded": bool(np.all((continuous_rgb >= 0.0) & (continuous_rgb <= 1.0))),
        "rest_coordinate_z_rule_matches_xyz_evaluator": bool(
            np.array_equal(continuous_rgb, evaluate_bowl_paint_at_xyz(np.column_stack((np.zeros_like(continuous_heights), np.zeros_like(continuous_heights), continuous_heights)), recipe))
        ),
        "sample_count": int(len(continuous_heights)),
    }
    round_trip = {
        "construction_valid": bool(constructed.isValid()),
        "canonical_step_valid": bool(canonical.isValid()),
        "construction_solid_count": len(constructed.Solids()),
        "canonical_step_solid_count": len(canonical.Solids()),
        "construction_shell_count": len(constructed.Shells()),
        "canonical_step_shell_count": len(canonical.Shells()),
        "canonical_step_shell_closed": bool(canonical.Shells()[0].Closed()),
        "construction_volume_mm3": float(constructed.Volume()),
        "canonical_step_volume_mm3": cad_volume,
        "analytic_volume_mm3": analytic_volume,
        "analytic_volume_relative_error": relative_volume_error,
        "bbox_max_axis_delta_mm": float(bounds_delta),
        "canonical_step_sha256": canonical_step_sha256,
    }
    checks = {
        "step_one_valid_solid_and_closed_shell": bool(canonical.isValid() and len(canonical.Solids()) == 1 and len(canonical.Shells()) == 1 and canonical.Shells()[0].Closed()),
        "analytic_volume_matches_canonical_cad": relative_volume_error < 1e-8,
        "step_round_trip_bounds_and_volume": bounds_delta <= 0.05 and abs(float(constructed.Volume()) - cad_volume) / max(cad_volume, 1e-12) < 1e-8,
        "surface_mesh_watertight_positive_volume": bool(topology["watertight"] and topology["signed_volume_mm3"] > 0.0),
        "mesh_to_cad_finite_sample_within_deflection": bool(mesh_step["unknown_sample_count"] == 0 and mesh_step["max_sampled_deviation_mm"] is not None and mesh_step["max_sampled_deviation_mm"] <= spec.tessellation_linear_mm + 1e-8),
        "all_canonical_faces_classified": bool(semantics["status"] == "PASS" and not semantics["unknown_face_indices"]),
        "triangle_regions_follow_step_lineage": bool(np.array_equal(region, triangle_region_codes(semantics, triangle_sources))),
        "paint_only_outer_body": bool(set(np.unique(region).astype(int)).issubset({1, 2, 3}) and np.all(albedo[region != 1] == np.asarray(PALE_SLIP, dtype=np.float32))),
        "continuous_paint_coordinates_valid": all(continuous_checks.values()),
        "per_face_band_coverage": per_face_coverage_pass,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "status": status,
        "scope": "geometry_only",
        "algorithm": "exact circular meridian arcs revolved around global Z; canonical STEP import drives mesh, lineage, semantics and sampled QA",
        "seed": int(seed),
        "backend": {"name": "CadQuery/OpenCascade", **_backend_versions()},
        "checks": checks,
        "measurements": {
            "step_round_trip": round_trip,
            "surface_mesh": topology,
            "mesh_to_canonical_step": mesh_step,
            "appearance_coverage": coverage,
            "continuous_paint_coordinate_checks": continuous_checks,
            "ideal_analytic_wall_mm": spec.ideal_wall_thickness_mm,
            "wall_claim": "exact analytic concentric-sphere design separation; no specimen or material validation",
        },
        "limitations": [
            "mechanics values are illustrative and UNVALIDATED_PROTOTYPE",
            "paint recipe is a procedural candidate; historical style is NOT_VALIDATED",
            "triangle-centroid albedo is a finite-mesh preview; continuous shader evaluation uses immutable rest-coordinate Z",
            "sampled mesh deviation is finite deterministic sampling, not a global Hausdorff bound",
            "solver points are produced separately and are not a fracture result",
        ],
    }
    _write_json(output / report_rel, report)
    _write_json(output / dictionary_rel, _data_dictionary())

    profile_record = spec.to_dict()
    profile_record.update({
        "prototype_form": "concentric_lower_hemisphere_bowl",
        "canonical_step_sha256": canonical_step_sha256,
        "face_semantics_report": semantics_rel,
        "face_semantics_classifier": SPHERICAL_BOWL_CLASSIFIER_VERSION,
        "mesh_lineage_npz": lineage_rel,
        "data_dictionary": dictionary_rel,
        "tessellation": {"linear_chord_deflection_mm": spec.tessellation_linear_mm, "angular_tolerance_rad": spec.tessellation_angular_rad},
        "brep_face_inventory": [
            {"index_zero_based": index, "geom_type": face.geomType(), "area_mm2": float(face.Area()), "bbox_mm": list(brep_bounds_mm(face))}
            for index, face in enumerate(canonical.Faces())
        ],
    })
    files = _file_inventory(output)
    manifest = {
        "schema": "forge.asset.v1",
        "units": {"length": "mm", "time": "s", "mass": "kg"},
        "frame": "right_handed_z_up",
        "geometry": {"surface_npz": surface_rel, "solid_step": step_rel},
        "fields": {"surface_fields_npz": fields_rel},
        "material": {
            "id": _MATERIAL_ID,
            "appearance": {"model": "constant_lambertian_preview", "base_albedo_linear_rgb": list(PALE_SLIP), "roughness": 0.78, "source": "procedural display placeholder; not measured optical data"},
            "mechanics": {"rho_kg_m3": 2300.0, "E_pa": 70.0e9, "nu": 0.25, "Gc_j_m2": 7.6},
            "calibration_status": "UNVALIDATED_PROTOTYPE",
            "provenance": {"mechanics_source": "root-selected native-case values; illustrative UNVALIDATED_PROTOTYPE placeholders with no specimen test or calibration", "appearance_source": "procedural preview palette; no spectrophotometry"},
        },
        "ornament": {"kind": "painted", "recipe": recipe},
        "files": files,
        "provenance": {
            "producer": "VesselForge spherical bowl builder",
            "version": "0.1.1",
            "backend": "CadQuery/OpenCascade",
            "backend_version": cq.__version__,
            "seed": int(seed),
            "spec": profile_record,
            "validity": "analytic geometry-only candidate; physical and historical validation absent",
            "upstream_dependencies": [],
            "missing_reason": "no specimen-specific geometry, material, pigment, impact or fracture data",
        },
        "validation": {"report": report_rel, "status": status, "scope": "geometry_only"},
    }
    _write_json(output / "manifest.json", manifest)
    validation = validate_asset(output)
    if status != "PASS":
        raise ValueError(f"spherical bowl geometry failed checks: {checks}")
    return {"manifest": manifest, "validation": validation, "report": report}


__all__ = [
    "BowlSpec",
    "SolverPointCloud",
    "analytic_spherical_bowl_volume_mm3",
    "build_spherical_bowl_solid",
    "classify_spherical_bowl_faces",
    "contains_material",
    "create_spherical_bowl_asset_package",
    "evaluate_bowl_paint_at_xyz",
    "generate_solver_points",
    "segment_in_material",
]

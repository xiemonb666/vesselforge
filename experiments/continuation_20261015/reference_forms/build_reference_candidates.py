"""Build geometry-only bowl candidates from explicit reference and family presets.

Run with the bundled VesselForge Python runtime from the workspace root:

    python vesselforge/experiments/continuation_20261015/reference_forms/build_reference_candidates.py --preset daily
    python vesselforge/experiments/continuation_20261015/reference_forms/build_reference_candidates.py --preset met
    python vesselforge/experiments/continuation_20261015/reference_forms/build_reference_candidates.py --preset daily --overrides-json '{"foot_height_mm": 7.5}'

The output directory is intentionally unique and refuses to overwrite files.
Each output is a source-guided geometry candidate, not a scan or exact profile
reconstruction. Output paths are unique and existing directories are refused.
"""

from __future__ import annotations

import io
import argparse
from dataclasses import asdict, fields
import hashlib
import json
import math
from pathlib import Path
import sys
import zipfile

import cadquery as cq
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from vesselforge.geometry import mesh_shape, mesh_topology_metrics  # noqa: E402
from vesselforge.revolved_profile import (  # noqa: E402
    FootedBowlDesign,
    build_revolved_solid,
    make_footed_bowl_section,
    meridian_volume_mm3,
    normal_offset_point_and_derivative,
    shape_bounds,
)


HERE = Path(__file__).resolve().parent
REGION_CODES = {"body_outer": 1, "body_inner": 2, "rim": 3, "base": 4, "foot": 5}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(arrays):
            payload = io.BytesIO()
            np.save(payload, arrays[name], allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def render_section_svg(path: Path, section: object, width_mm: float, height_mm: float) -> None:
    profile = section.sampled_points(samples_per_bezier=100, samples_per_arc=60)
    margin = 0.07 * max(width_mm, height_mm)
    width_px, height_px = 900, 620
    scale = min((width_px - 2.0 * margin) / width_mm, (height_px - 2.0 * margin) / height_mm)
    left = (width_px - width_mm * scale) / 2.0
    bottom = (height_px - height_mm * scale) / 2.0
    points = []
    for radius, z in profile:
        x = left + (radius + width_mm / 2.0) * scale
        y = height_px - (bottom + z * scale)
        points.append(f"{x:.3f},{y:.3f}")
    polygon = " ".join(points)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}">
  <rect width="100%" height="100%" fill="#fbfaf7"/>
  <line x1="{width_px / 2:.1f}" y1="40" x2="{width_px / 2:.1f}" y2="{height_px - 38:.1f}" stroke="#9a9a9a" stroke-dasharray="5 5"/>
  <polygon points="{polygon}" fill="#d7c9ad" fill-opacity="0.55" stroke="#34495e" stroke-width="2.5" stroke-linejoin="round"/>
  <text x="28" y="32" font-family="sans-serif" font-size="20" fill="#263238">Meridian section · solid region shaded · dimensions and construction assumptions documented</text>
  <text x="28" y="{height_px - 18}" font-family="sans-serif" font-size="17" fill="#52606d">Z-up · axis at center · not a specimen scan or profile reconstruction</text>
</svg>
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def render_four_view_preview(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    section_points: np.ndarray,
    *,
    diameter_mm: float,
    height_mm: float,
    notes_text: str,
) -> None:
    import vtk

    background = (0.985, 0.98, 0.965)
    surface_color = (0.78, 0.70, 0.55)
    bounds_radius = diameter_mm * 0.62
    center_z = height_mm / 2.0

    points = vtk.vtkPoints()
    points.SetNumberOfPoints(len(vertices))
    for index, point in enumerate(vertices):
        points.SetPoint(index, float(point[0]), float(point[1]), float(point[2]))
    polygons = vtk.vtkCellArray()
    for triangle in faces:
        polygons.InsertNextCell(3)
        for vertex_index in triangle:
            polygons.InsertCellPoint(int(vertex_index))
    mesh = vtk.vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(polygons)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(mesh)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.SplittingOff()
    normals.ComputeCellNormalsOff()
    normals.ComputePointNormalsOn()
    normals.Update()

    def make_mesh_actor() -> vtk.vtkActor:
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        mapper.ScalarVisibilityOff()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        material = actor.GetProperty()
        material.SetColor(*surface_color)
        material.SetInterpolationToPhong()
        material.SetAmbient(0.20)
        material.SetDiffuse(0.76)
        material.SetSpecular(0.18)
        material.SetSpecularPower(24.0)
        return actor

    def add_label(renderer: vtk.vtkRenderer, text: str) -> None:
        label = vtk.vtkTextActor()
        label.SetInput(text)
        label.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        label.SetPosition(0.035, 0.93)
        label.GetTextProperty().SetFontSize(15)
        label.GetTextProperty().SetColor(0.14, 0.16, 0.18)
        renderer.AddViewProp(label)

    def orient_camera(
        renderer: vtk.vtkRenderer,
        position: tuple[float, float, float],
        focal_point: tuple[float, float, float],
        view_up: tuple[float, float, float],
        *,
        parallel: bool = True,
    ) -> None:
        camera = renderer.GetActiveCamera()
        camera.SetPosition(*position)
        camera.SetFocalPoint(*focal_point)
        camera.SetViewUp(*view_up)
        if parallel:
            camera.ParallelProjectionOn()
            camera.SetParallelScale(bounds_radius)
        else:
            camera.ParallelProjectionOff()
            camera.SetViewAngle(31.0)
        renderer.ResetCameraClippingRange()

    renderer_specs = [
        ("Side elevation · orthographic", (0.0, -190.0, center_z), (0.0, 0.0, center_z), (0.0, 0.0, 1.0), True),
        ("Top view · orthographic", (0.0, 0.0, 190.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), True),
        ("Lit 3D view", (145.0, -175.0, 142.0), (0.0, 0.0, center_z), (0.0, 0.0, 1.0), False),
        ("Foot underside · orthographic", (0.0, 0.0, -190.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), True),
    ]
    window = vtk.vtkRenderWindow()
    window.SetSize(1560, 1040)
    window.SetOffScreenRendering(1)
    window.SetMultiSamples(0)
    renderer_objects = []
    viewports = [
        (0.0, 0.5, 1.0 / 3.0, 1.0),
        (1.0 / 3.0, 0.5, 2.0 / 3.0, 1.0),
        (2.0 / 3.0, 0.5, 1.0, 1.0),
        (0.0, 0.0, 1.0 / 3.0, 0.5),
        (1.0 / 3.0, 0.0, 2.0 / 3.0, 0.5),
        (2.0 / 3.0, 0.0, 1.0, 0.5),
    ]
    for index, (title, position, focal_point, view_up, parallel) in enumerate(renderer_specs):
        renderer = vtk.vtkRenderer()
        renderer.SetViewport(*viewports[index])
        renderer.SetBackground(*background)
        renderer.AddActor(make_mesh_actor())
        orient_camera(renderer, position, focal_point, view_up, parallel=parallel)
        add_label(renderer, title)
        window.AddRenderer(renderer)
        renderer_objects.append(renderer)

    # Show a complete meridian section in the fifth panel as a lit-independent
    # filled CAD outline, using the same section samples that are exported.
    right_profile = np.asarray(section_points, dtype=np.float64)
    left_profile = np.column_stack((-right_profile[::-1, 0], right_profile[::-1, 1]))
    full_profile = np.vstack((right_profile, left_profile[1:-1]))
    section_points_vtk = vtk.vtkPoints()
    for radius, z in full_profile:
        section_points_vtk.InsertNextPoint(float(radius), 0.0, float(z))
    section_cells = vtk.vtkCellArray()
    section_cells.InsertNextCell(len(full_profile) + 1)
    for index in range(len(full_profile)):
        section_cells.InsertCellPoint(index)
    section_cells.InsertCellPoint(0)
    section_data = vtk.vtkPolyData()
    section_data.SetPoints(section_points_vtk)
    section_data.SetLines(section_cells)
    section_mapper = vtk.vtkPolyDataMapper()
    section_mapper.SetInputData(section_data)
    section_actor = vtk.vtkActor()
    section_actor.SetMapper(section_mapper)
    section_actor.GetProperty().SetColor(0.20, 0.27, 0.34)
    section_actor.GetProperty().SetLineWidth(2.2)
    section_actor.GetProperty().LightingOff()
    section_renderer = vtk.vtkRenderer()
    section_renderer.SetViewport(*viewports[4])
    section_renderer.SetBackground(*background)
    section_renderer.AddActor(section_actor)
    orient_camera(section_renderer, (0.0, -190.0, center_z), (0.0, 0.0, center_z), (0.0, 0.0, 1.0))
    add_label(section_renderer, "Meridian section · complete closed profile")
    window.AddRenderer(section_renderer)
    renderer_objects.append(section_renderer)

    # Keep the final panel for dimensions and the interpretation boundary.
    notes_renderer = vtk.vtkRenderer()
    notes_renderer.SetViewport(*viewports[5])
    notes_renderer.SetBackground(*background)
    notes = vtk.vtkTextActor()
    notes.SetInput(notes_text)
    notes.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
    notes.SetPosition(0.08, 0.56)
    notes.GetTextProperty().SetFontSize(16)
    notes.GetTextProperty().SetColor(0.18, 0.20, 0.23)
    notes_renderer.AddViewProp(notes)
    window.AddRenderer(notes_renderer)
    renderer_objects.append(notes_renderer)

    window.Render()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.ReadFrontBufferOff()
    capture.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(capture.GetOutputPort())
    path.parent.mkdir(parents=True, exist_ok=True)
    writer.Write()
    window.Finalize()


PRESETS: dict[str, dict[str, object]] = {
    "daily": {
        "output_name": "daily_aberdeen_108x53_v6_final",
        "design": {
            "name": "daily_aberdeen_size_reference_candidate_v6",
            "rim_outer_diameter_mm": 108.0,
            "overall_height_mm": 53.0,
            "wall_thickness_mm": 2.0,
            "foot_outer_diameter_mm": 31.0,
            "foot_height_mm": 7.0,
            "body_floor_radius_mm": 10.5,
            "body_floor_z_mm": 10.0,
            "underside_recess_z_mm": 6.5,
            "foot_contact_width_mm": 2.0,
            "rim_tangent_degrees": 75.0,
            "normal_offset_fit_tolerance_mm": 0.005,
            "body_start_handle_fraction": 0.60,
            "body_end_handle_height_fraction": 0.22,
        },
        "record": {
            "title": "Porcelain Small Footed Bowl",
            "collection": "Aberdeen City Museums",
            "object_number": "ABDMS095708.121",
            "object_url": "https://emuseum.aberdeencity.gov.uk/objects/186848/porcelain-small-footed-bowl",
            "period": "2007–2009",
            "medium": "Limoges porcelain and celadon",
            "reported_dimensions_mm": {"overall_height": 53.0, "rim_outer_diameter": 108.0, "foot_outer_diameter": 31.0},
            "dimension_evidence": "Official museum catalog record; the listed dimensions are catalog measurements.",
            "visual_reference_note": "The reference reviewer reports that the lower-angle gallery photo shows a visibly taller foot and raised lower base. The 7 mm candidate foot height is a visual design assumption, not a catalog measurement.",
        },
        "measured_fields": ["overall_height_mm", "rim_outer_diameter_mm", "foot_outer_diameter_mm"],
        "candidate_status": "SIZE_REFERENCE_GEOMETRY_CANDIDATE_ONLY",
        "kind": "reference_anchor",
    },
    "met": {
        "output_name": "met_18_56_44_111x54_v2",
        "design": {
            "name": "met_18_56_44_jun_bowl_size_reference_candidate_v2",
            "rim_outer_diameter_mm": 111.0,
            "overall_height_mm": 54.0,
            "wall_thickness_mm": 3.2,
            "foot_outer_diameter_mm": 54.0,
            "foot_height_mm": 3.5,
            "body_floor_radius_mm": 16.5,
            "body_floor_z_mm": 6.5,
            "underside_recess_z_mm": 3.2,
            "foot_contact_width_mm": 2.4,
            "rim_tangent_degrees": 68.0,
            "normal_offset_fit_tolerance_mm": 0.005,
            "body_start_handle_fraction": 0.70,
            "body_end_handle_height_fraction": 0.20,
        },
        "record": {
            "title": "Bowl",
            "collection": "The Metropolitan Museum of Art",
            "object_number": "18.56.44",
            "object_url": "https://www.metmuseum.org/art/collection/search/52389",
            "period": "Jin dynasty (1115–1234), 12th–13th century",
            "medium": "Stoneware with blue-gray glaze (Jun ware)",
            "reported_dimensions_mm": {"overall_height": 54.0, "rim_outer_diameter": 111.0, "foot_outer_diameter": 54.0},
            "dimension_evidence": "Official Met collection record; listed dimensions are H 5.4 cm, rim diameter 11.1 cm, and foot diameter 5.4 cm.",
            "visual_reference_note": "Reference catalog review describes a continuous round rim, deep rounded body with slight outward rise near the opening, and a low narrow foot ring. The photograph does not establish section, thickness, or foot height.",
        },
        "measured_fields": ["overall_height_mm", "rim_outer_diameter_mm", "foot_outer_diameter_mm"],
        "candidate_status": "SIZE_REFERENCE_GEOMETRY_CANDIDATE_ONLY",
        "kind": "reference_anchor",
    },
    "daily_deep": {
        "output_name": "family_daily_deep_v1",
        "design": {
            "name": "family_daily_deep_bowl_variant",
            "rim_outer_diameter_mm": 108.0,
            "overall_height_mm": 62.0,
            "wall_thickness_mm": 2.0,
            "foot_outer_diameter_mm": 31.0,
            "foot_height_mm": 7.0,
            "body_floor_radius_mm": 10.5,
            "body_floor_z_mm": 10.0,
            "underside_recess_z_mm": 6.5,
            "foot_contact_width_mm": 2.0,
            "rim_tangent_degrees": 75.0,
            "normal_offset_fit_tolerance_mm": 0.005,
            "body_start_handle_fraction": 0.60,
            "body_end_handle_height_fraction": 0.22,
        },
        "record": {"title": "Parametric daily-use bowl family variant", "collection": "VesselForge design candidate", "object_number": "DESIGN-VARIANT-DAILY-DEEP", "object_url": "https://emuseum.aberdeencity.gov.uk/objects/186848/porcelain-small-footed-bowl", "reported_dimensions_mm": {"overall_height": 53.0, "rim_outer_diameter": 108.0, "foot_outer_diameter": 31.0}, "dimension_evidence": "Aberdeen dimensions are the family anchor; only candidate overall height changes here.", "visual_reference_note": "Generated deeper family variant with the daily candidate rim diameter, wall, and foot held fixed."},
        "measured_fields": [],
        "candidate_status": "PARAMETRIC_DAILY_FAMILY_VARIANT_ONLY",
        "kind": "family_variant",
    },
    "daily_full_belly": {
        "output_name": "family_daily_full_belly_v1",
        "design": {
            "name": "family_daily_full_belly_bowl_variant",
            "rim_outer_diameter_mm": 108.0,
            "overall_height_mm": 53.0,
            "wall_thickness_mm": 2.0,
            "foot_outer_diameter_mm": 31.0,
            "foot_height_mm": 7.0,
            "body_floor_radius_mm": 10.5,
            "body_floor_z_mm": 10.0,
            "underside_recess_z_mm": 6.5,
            "foot_contact_width_mm": 2.0,
            "rim_tangent_degrees": 68.0,
            "normal_offset_fit_tolerance_mm": 0.005,
            "body_start_handle_fraction": 0.80,
            "body_end_handle_height_fraction": 0.18,
        },
        "record": {"title": "Parametric daily-use bowl family variant", "collection": "VesselForge design candidate", "object_number": "DESIGN-VARIANT-DAILY-FULL-BELLY", "object_url": "https://emuseum.aberdeencity.gov.uk/objects/186848/porcelain-small-footed-bowl", "reported_dimensions_mm": {"overall_height": 53.0, "rim_outer_diameter": 108.0, "foot_outer_diameter": 31.0}, "dimension_evidence": "Aberdeen dimensions are the family anchor; candidate belly and rim controls are generated design choices.", "visual_reference_note": "Generated fuller belly with altered rim tangent and Bézier handles; candidate dimensions and support match the family anchor."},
        "measured_fields": [],
        "candidate_status": "PARAMETRIC_DAILY_FAMILY_VARIANT_ONLY",
        "kind": "family_variant",
    },
    "daily_broad_foot": {
        "output_name": "family_daily_broad_foot_v2",
        "design": {
            "name": "family_daily_broad_foot_bowl_variant",
            "rim_outer_diameter_mm": 108.0,
            "overall_height_mm": 53.0,
            "wall_thickness_mm": 2.0,
            "foot_outer_diameter_mm": 34.0,
            "foot_height_mm": 7.5,
            "body_floor_radius_mm": 10.5,
            "body_floor_z_mm": 10.0,
            "underside_recess_z_mm": 6.5,
            "foot_contact_width_mm": 2.0,
            "rim_tangent_degrees": 75.0,
            "normal_offset_fit_tolerance_mm": 0.005,
            "body_start_handle_fraction": 0.60,
            "body_end_handle_height_fraction": 0.22,
        },
        "record": {"title": "Parametric daily-use bowl family variant", "collection": "VesselForge design candidate", "object_number": "DESIGN-VARIANT-DAILY-BROAD-FOOT", "object_url": "https://emuseum.aberdeencity.gov.uk/objects/186848/porcelain-small-footed-bowl", "reported_dimensions_mm": {"overall_height": 53.0, "rim_outer_diameter": 108.0, "foot_outer_diameter": 31.0}, "dimension_evidence": "Aberdeen dimensions are the family anchor; only candidate foot diameter, height, and contact width change here.", "visual_reference_note": "Generated broader, taller support ring with the daily candidate body and wall held fixed."},
        "measured_fields": [],
        "candidate_status": "PARAMETRIC_DAILY_FAMILY_VARIANT_ONLY",
        "kind": "family_variant",
    },
}


def read_overrides(spec: str | None) -> dict[str, object]:
    if spec is None:
        return {}
    candidate_path = Path(spec)
    if candidate_path.is_file():
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(spec)
    if not isinstance(payload, dict):
        raise ValueError("--overrides-json must be a JSON object mapping FootedBowlDesign fields to values")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_candidate(preset_name: str, output: Path, overrides: dict[str, object]) -> dict[str, object]:
    preset = PRESETS[preset_name]
    design_values = dict(preset["design"])
    known_fields = {item.name for item in fields(FootedBowlDesign)}
    unknown = sorted(set(overrides) - known_fields)
    if unknown:
        raise ValueError(f"unknown design override fields: {unknown}")
    design_values.update(overrides)
    design = FootedBowlDesign(**design_values)
    section, profile_info = make_footed_bowl_section(design)
    shape, native_lineage = build_revolved_solid(section)

    output = output.resolve()
    if HERE.resolve() not in output.parents:
        raise ValueError(f"candidate output must be inside {HERE}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite candidate output: {output}")
    output.mkdir(parents=True, exist_ok=False)
    geometry_dir = output / "geometry"
    geometry_dir.mkdir(parents=True, exist_ok=False)
    step_path = geometry_dir / "solid.step"
    cq.exporters.export(shape, str(step_path), exportType="STEP")
    step_readback = cq.importers.importStep(str(step_path)).val()
    constructed_bounds = shape_bounds(shape)
    step_bounds = shape_bounds(step_readback)

    tessellation = type("Tessellation", (), {"tessellation_linear_mm": 0.20, "tessellation_angular_rad": 0.14})()
    vertices, triangles, triangle_sources = mesh_shape(shape, tessellation)
    face_roles = {int(index): str(row["role"]) for index, row in native_lineage["faces"].items()}
    triangle_roles = np.asarray([face_roles[int(index)] for index in triangle_sources], dtype="U16")
    triangle_region = np.asarray([REGION_CODES[str(role)] for role in triangle_roles], dtype=np.uint8)
    surface_path = geometry_dir / "surface.npz"
    write_deterministic_npz(
        surface_path,
        {
            "vertices_mm": vertices.astype(np.float64),
            "faces": triangles.astype(np.int32),
            "triangle_source_brep_face_index": triangle_sources.astype(np.int32),
            "triangle_region_code": triangle_region,
        },
    )
    section_path = geometry_dir / "section.json"
    lineage_path = geometry_dir / "face_lineage.json"
    write_json(section_path, section.to_dict())
    write_json(lineage_path, native_lineage)

    record = dict(preset["record"])
    record_dimensions = dict(record["reported_dimensions_mm"])
    measured_fields = set(preset["measured_fields"])
    candidate_dimensions = {
        "overall_height_mm": float(design.overall_height_mm),
        "rim_outer_diameter_mm": float(design.rim_outer_diameter_mm),
        "foot_outer_diameter_mm": float(design.foot_outer_diameter_mm),
    }
    measured_field_map = {
        "overall_height_mm": "overall_height",
        "rim_outer_diameter_mm": "rim_outer_diameter",
        "foot_outer_diameter_mm": "foot_outer_diameter",
    }
    assumptions = {
        key: value
        for key, value in design_values.items()
        if key not in measured_fields and key not in {"name", "normal_offset_fit_tolerance_mm"}
    }
    provenance = {
        "schema": "vf.revolved_profile_candidate_provenance.v1",
        "preset": preset_name,
        "record": record,
        "candidate_status": preset["candidate_status"],
        "source_dimensions_mm": record_dimensions,
        "candidate_dimensions_mm": candidate_dimensions,
        "measured_from_record": [measured_field_map[field] for field in sorted(measured_fields)],
        "design_assumptions": assumptions,
        "numerical_fit_controls": {"normal_offset_fit_tolerance_mm": float(design.normal_offset_fit_tolerance_mm)},
        "parameter_overrides": overrides,
        "source_profile_fidelity": "NOT_ESTABLISHED; dimensions and photographs do not define the complete meridian or construction.",
        "not_claimed": [
            "not a specimen scan or exact profile reconstruction",
            "not a verified match to the maker's exact wall, base, rim or foot construction",
            "not a calibrated physical material or mechanics model",
        ],
        "physical_material_properties": "NOT_SPECIFIED; no ceramic density, modulus, Poisson ratio, strength or toughness is inferred.",
        "image_handling": "Catalog images were not copied into or packaged with the candidate.",
        "section_geometry_details": profile_info,
    }
    provenance_path = output / "provenance.json"
    write_json(provenance_path, provenance)

    metrics = mesh_topology_metrics(vertices, triangles)
    bounds = step_bounds
    expected_volume = meridian_volume_mm3(section)
    support_segment_indices = [
        index
        for index, segment in enumerate(section.segments)
        if segment.role == "foot"
        and segment.kind == "line"
        and abs(segment.start[1]) <= 1e-10
        and abs(segment.end[1]) <= 1e-10
        and segment.start[0] > segment.end[0]
    ]
    support_face_indices = [
        int(face_index)
        for face_index, row in native_lineage["faces"].items()
        if any(index in row["source_segment_indices"] for index in support_segment_indices)
    ]
    support_face_is_planar_at_z0 = False
    if len(support_segment_indices) == 1 and len(support_face_indices) == 1:
        support_surface = BRepAdaptor_Surface(shape.Faces()[support_face_indices[0]].wrapped, True)
        support_face_is_planar_at_z0 = bool(
            support_surface.GetType() == GeomAbs_Plane
            and abs(support_surface.Plane().Location().Z()) <= 1e-7
        )

    inner_body = next(segment for segment in section.segments if segment.role == "body_inner")
    inner_probe = inner_body.point(0.25)
    outer_probe = normal_offset_point_and_derivative(inner_body, 0.25, float(design.wall_thickness_mm))[0]
    wall_probe = 0.5 * (inner_probe + outer_probe)
    contact_radii = profile_info["foot"]["contact_annulus_radii_mm"]
    foot_probe = (0.5 * (float(contact_radii[0]) + float(contact_radii[1])), float(design.foot_height_mm) * 0.5)
    cavity_probe = (0.0, 0.0, 0.5 * (float(design.body_floor_z_mm) + float(design.overall_height_mm)))
    base_probe = (0.0, 0.0, 0.5 * (float(design.body_floor_z_mm) + float(design.underside_recess_z_mm)))
    outside_probe = (float(design.rim_outer_diameter_mm) / 2.0 + 5.0, 0.0, float(design.overall_height_mm) * 0.5)

    checks = {
        "one_valid_solid": bool(shape.isValid() and len(shape.Solids()) == 1),
        "one_closed_shell": bool(len(shape.Shells()) == 1 and shape.Shells()[0].wrapped.Closed()),
        "positive_volume": bool(math.isfinite(float(shape.Volume())) and shape.Volume() > 0.0),
        "all_native_faces_have_one_role": bool(
            native_lineage["face_count"] == len(shape.Faces())
            and native_lineage["region_roles"] == sorted(REGION_CODES)
        ),
        "step_round_trip_one_solid": bool(
            step_readback.isValid()
            and len(step_readback.Solids()) == 1
            and len(step_readback.Shells()) == 1
            and step_readback.Shells()[0].wrapped.Closed()
        ),
        "outer_dimensions_within_0_1mm": bool(
            abs(bounds["diameter_x_mm"] - design.rim_outer_diameter_mm) <= 0.1
            and abs(bounds["diameter_y_mm"] - design.rim_outer_diameter_mm) <= 0.1
            and abs(bounds["height_mm"] - design.overall_height_mm) <= 0.1
        ),
        "foot_contact_touches_z0": bool(
            support_face_is_planar_at_z0 and abs(float(bounds["z_min_mm"])) <= 1e-5
        ),
        "mesh_is_watertight": bool(metrics["watertight"]),
        "cavity_center_is_empty": bool(not shape.isInside(cq.Vector(*cavity_probe), 1e-7)),
        "body_wall_probe_is_material": bool(shape.isInside(cq.Vector(float(wall_probe[0]), 0.0, float(wall_probe[1])), 1e-7)),
        "foot_and_base_probes_are_material": bool(
            shape.isInside(cq.Vector(float(foot_probe[0]), 0.0, float(foot_probe[1])), 1e-7)
            and shape.isInside(cq.Vector(*base_probe), 1e-7)
        ),
        "outside_probe_is_empty": bool(not shape.isInside(cq.Vector(*outside_probe), 1e-7)),
    }

    section_points = section.sampled_points(samples_per_bezier=100, samples_per_arc=60)
    if preset["kind"] == "reference_anchor":
        notes = [
            str(record["collection"]).upper(),
            f"H {design.overall_height_mm:g} · rim Ø{design.rim_outer_diameter_mm:g}",
            f"Foot Ø{design.foot_outer_diameter_mm:g} · wall* {design.wall_thickness_mm:g}",
            f"Foot H* {design.foot_height_mm:g} · θ* {design.rim_tangent_degrees:g}°",
            "*Design assumption · not reconstruction",
        ]
    else:
        notes = [
            "GENERATED FAMILY VARIATION",
            f"H {design.overall_height_mm:g} · rim Ø{design.rim_outer_diameter_mm:g}",
            f"Foot Ø{design.foot_outer_diameter_mm:g} · wall* {design.wall_thickness_mm:g}",
            f"Foot H* {design.foot_height_mm:g} · θ* {design.rim_tangent_degrees:g}°",
            "*Design assumption · not source measurement",
        ]
    notes_text = "\n".join(notes)
    preview_path = output / "preview.png"
    render_four_view_preview(
        preview_path,
        vertices,
        triangles,
        section_points,
        diameter_mm=float(design.rim_outer_diameter_mm),
        height_mm=float(design.overall_height_mm),
        notes_text=notes_text,
    )
    render_section_svg(output / "section.svg", section, float(design.rim_outer_diameter_mm), float(design.overall_height_mm))
    preview_metadata_path = output / "preview_metadata.json"
    write_json(
        preview_metadata_path,
        {
            "view_count": 5,
            "projection": "orthographic for side, top, bottom and section; perspective for the lit 3D view",
            "geometry_source": "same saved candidate B-rep and meridian section",
            "render_is_measurement": False,
            "renderer": "VTK 9.6.2 offscreen with surface lighting",
            "display_notes": notes,
        },
    )
    artifact_paths = {
        "solid.step": step_path,
        "surface.npz": surface_path,
        "section.json": section_path,
        "face_lineage.json": lineage_path,
        "preview.png": preview_path,
    }
    artifact_hashes = {name: _sha256(path) for name, path in artifact_paths.items()}
    report = {
        "schema": "vf.revolved_profile_geometry_candidate_report.v1",
        "preset": preset_name,
        "candidate_geometry_status": "PASS_STRUCTURAL_CAD_ONLY" if all(checks.values()) else "FAIL_STRUCTURAL_CAD",
        "candidate_status": preset["candidate_status"],
        "interpretation": "Structural geometry checks only; no physical, material, or source-profile match claim.",
        "checks": checks,
        "measurements": {
            "candidate_dimensions_mm": candidate_dimensions,
            "brep_bounds": bounds,
            "constructed_brep_bounds_before_tessellation": constructed_bounds,
            "step_round_trip_bounds": step_bounds,
            "solid_volume_mm3": float(shape.Volume()),
            "independent_meridian_integral_volume_mm3": float(expected_volume),
            "relative_volume_delta": abs(float(shape.Volume()) - expected_volume) / expected_volume,
            "native_face_count": len(shape.Faces()),
            "native_foot_support_face_indices": support_face_indices,
            "native_region_counts": {role: sum(1 for row in native_lineage["faces"].values() if row["role"] == role) for role in REGION_CODES},
            "surface_mesh": metrics,
            "triangle_count": int(len(triangles)),
            "vertex_count": int(len(vertices)),
            "normal_offset_max_sampled_curve_fit_deviation_mm": float(profile_info["normal_offset_fit_max_sampled_deviation_mm"]),
            "normal_offset_fit_error_scope": "Finite diagnostic only: three interior samples per accepted cubic subcurve; no continuous or global error bound is claimed.",
            "step_round_trip_volume_delta_mm3": abs(float(step_readback.Volume()) - float(shape.Volume())),
            "probe_points_mm": {
                "cavity_center": list(cavity_probe),
                "body_wall_midpoint": [float(wall_probe[0]), 0.0, float(wall_probe[1])],
                "foot_material": [float(foot_probe[0]), 0.0, float(foot_probe[1])],
                "base_material": list(base_probe),
                "outside": list(outside_probe),
            },
            "artifact_sha256": artifact_hashes,
        },
        "source_profile_fidelity": "NOT_ESTABLISHED: catalog dimensions and photographs do not provide the complete meridian or construction.",
        "physical_material_validity": "NOT_ASSESSED",
    }
    write_json(output / "geometry_report.json", report)
    total_bytes = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    if total_bytes > 64 * 1024 * 1024:
        raise RuntimeError(f"candidate output exceeds 64 MiB: {total_bytes} bytes")
    if not all(checks.values()):
        raise RuntimeError(f"candidate failed structural CAD checks: {checks}")
    print(
        json.dumps(
            {
                "output": str(output),
                "preset": preset_name,
                "candidate_status": report["candidate_geometry_status"],
                "design_parameters": asdict(design),
                "checks": checks,
                "volume_mm3": shape.Volume(),
                "artifact_sha256": artifact_hashes,
                "output_bytes": total_bytes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one geometry-only reference or family-variation candidate.")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="daily")
    parser.add_argument("--output", help="new output directory under reference_forms; existing directories are refused")
    parser.add_argument("--overrides-json", help="JSON object or a path to JSON design-field overrides")
    args = parser.parse_args()
    preset = PRESETS[args.preset]
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = Path.cwd() / output
    else:
        output = HERE / "outputs" / str(preset["output_name"])
    build_candidate(args.preset, output, read_overrides(args.overrides_json))


if __name__ == "__main__":
    main()

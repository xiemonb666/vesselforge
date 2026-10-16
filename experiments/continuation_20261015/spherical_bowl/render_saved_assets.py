from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy


REPO_ROOT = Path(__file__).resolve().parents[3]
ASSET_ROOT = REPO_ROOT / "data" / "continuation_20261015" / "spherical_bowl"
OUTPUT_ROOT = REPO_ROOT / "experiments" / "continuation_20261015" / "spherical_bowl" / "visualization"
OUTPUT_PNG = OUTPUT_ROOT / "spherical_bowl_two_patterns.png"
OUTPUT_RECEIPT = OUTPUT_ROOT / "render_receipt.json"
IMAGE_SIZE = (1800, 1120)
PARALLEL_SCALE_MM = 15.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    return np.where(values <= 0.0031308, 12.92 * values, 1.055 * np.power(values, 1.0 / 2.4) - 0.055)


def load_asset(pattern: str) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    package = ASSET_ROOT / pattern
    manifest_path = package / "manifest.json"
    geometry_path = package / "geometry" / "surface.npz"
    fields_path = package / "fields" / "surface.npz"
    with manifest_path.open("r", encoding="utf-8") as source:
        manifest = json.load(source)
    with np.load(geometry_path, allow_pickle=False) as arrays:
        vertices = np.asarray(arrays["vertices_mm"], dtype=np.float64)
        faces = np.asarray(arrays["faces"], dtype=np.int64)
    with np.load(fields_path, allow_pickle=False) as arrays:
        material_xyz = np.asarray(arrays["vertices_material_xyz_mm"], dtype=np.float64)
        face_rgb = np.asarray(arrays["albedo_linear_rgb"], dtype=np.float64)
        face_region = np.asarray(arrays["face_region"], dtype=np.uint8)
    if vertices.shape != material_xyz.shape or not np.array_equal(vertices, material_xyz):
        raise ValueError(f"{pattern} asset material coordinates do not match its saved rest mesh")
    if faces.ndim != 2 or faces.shape[1] != 3 or face_rgb.shape != (len(faces), 3):
        raise ValueError(f"{pattern} asset has inconsistent face/color arrays")
    if face_region.shape != (len(faces),) or not np.isfinite(face_rgb).all():
        raise ValueError(f"{pattern} asset has invalid region or color values")
    input_record = {
        "package": str(package),
        "manifest_sha256": sha256_file(manifest_path),
        "geometry_surface_sha256": sha256_file(geometry_path),
        "fields_surface_sha256": sha256_file(fields_path),
        "vertex_count": int(len(vertices)),
        "triangle_count": int(len(faces)),
        "band_count": int(len(manifest["ornament"]["recipe"]["bands"])),
        "face_regions": {str(int(code)): int(np.count_nonzero(face_region == code)) for code in np.unique(face_region)},
        "rest_coordinates_equal_mesh_vertices": True,
        "color_source": "fields/surface.npz:albedo_linear_rgb, derived from triangle rest-coordinate centroids",
    }
    return vertices, faces, {"face_rgb_linear": face_rgb, "face_region": face_region, "manifest": manifest, "input_record": input_record}


def make_polydata(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_rgb_linear: np.ndarray,
    face_region: np.ndarray,
) -> vtk.vtkPolyData:
    polydata = vtk.vtkPolyData()
    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices), deep=True))
    polydata.SetPoints(vtk_points)

    offsets = np.arange(len(faces) + 1, dtype=np.int64) * 3
    connectivity = np.ascontiguousarray(faces.reshape(-1), dtype=np.int64)
    vtk_cells = vtk.vtkCellArray()
    vtk_cells.SetData(
        numpy_to_vtkIdTypeArray(offsets, deep=True),
        numpy_to_vtkIdTypeArray(connectivity, deep=True),
    )
    polydata.SetPolys(vtk_cells)

    triangles = vertices[faces]
    raw_normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normal_lengths = np.linalg.norm(raw_normals, axis=1)
    if np.any(normal_lengths <= 1e-14):
        raise ValueError("render input contains a degenerate triangle")
    normals = raw_normals / normal_lengths[:, None]
    centers = triangles.mean(axis=1)
    radial = centers - np.asarray([0.0, 0.0, 12.0])
    radial_lengths = np.linalg.norm(radial, axis=1)
    expected = np.zeros_like(normals)
    outer = face_region == 1
    inner = face_region == 2
    rim = face_region == 3
    expected[outer] = radial[outer] / radial_lengths[outer, None]
    expected[inner] = -radial[inner] / radial_lengths[inner, None]
    expected[rim] = np.asarray([0.0, 0.0, 1.0])
    if np.any(~(outer | inner | rim)) or np.any(np.linalg.norm(expected, axis=1) < 0.99):
        raise ValueError("render input contains an unknown face region")
    orientation = np.einsum("ij,ij->i", normals, expected)
    normals[orientation < 0.0] *= -1.0
    light = np.asarray([38.0, -54.0, 31.0], dtype=np.float64)
    light /= np.linalg.norm(light)
    illumination = 0.56 + 0.44 * np.maximum(np.einsum("ij,j->i", normals, light), 0.0)
    display_rgb = linear_to_srgb(face_rgb_linear * illumination[:, None])
    color_bytes = np.ascontiguousarray(np.round(display_rgb * 255.0).astype(np.uint8))
    colors = numpy_to_vtk(color_bytes, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)
    colors.SetNumberOfComponents(3)
    colors.SetName("asset_rest_coordinate_albedo_srgb")
    polydata.GetCellData().SetScalars(colors)
    return polydata


def add_overlay_text(renderer: vtk.vtkRenderer, text: str, x: int, y: int, size: int, *, bold: bool = False) -> None:
    actor = vtk.vtkTextActor()
    actor.SetInput(text)
    actor.SetDisplayPosition(x, y)
    prop = actor.GetTextProperty()
    prop.SetFontFamilyToArial()
    prop.SetFontSize(size)
    prop.SetBold(bold)
    prop.SetColor(0.15, 0.18, 0.17)
    prop.SetShadow(False)
    renderer.AddViewProp(actor)


def main() -> None:
    started = time.monotonic()
    if OUTPUT_ROOT.exists() or OUTPUT_PNG.exists() or OUTPUT_RECEIPT.exists():
        raise FileExistsError(f"refusing to overwrite visualization output: {OUTPUT_ROOT}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)

    vertices_a, faces_a, data_three = load_asset("three_bands")
    vertices_b, faces_b, data_four = load_asset("four_bands")
    if not np.array_equal(vertices_a, vertices_b) or not np.array_equal(faces_a, faces_b):
        raise ValueError("the saved pattern packages do not share identical rest geometry")
    if data_three["input_record"]["geometry_surface_sha256"] != data_four["input_record"]["geometry_surface_sha256"]:
        raise ValueError("pattern packages reference different geometry payload bytes")

    render_window = vtk.vtkRenderWindow()
    render_window.SetSize(*IMAGE_SIZE)
    render_window.SetOffScreenRendering(1)
    render_window.SetMultiSamples(0)
    render_window.SetAlphaBitPlanes(0)
    render_window.SetBorders(False)
    render_window.SetNumberOfLayers(2)
    background = vtk.vtkRenderer()
    background.SetLayer(0)
    background.SetViewport(0.0, 0.0, 1.0, 1.0)
    background.SetBackground(0.965, 0.953, 0.925)
    background.SetBackground2(0.93, 0.91, 0.86)
    background.GradientBackgroundOn()
    render_window.AddRenderer(background)
    panel_renderers: list[vtk.vtkRenderer] = []
    for index, (data, title) in enumerate(((data_three, "THREE BANDS"), (data_four, "FOUR BANDS"))):
        renderer = vtk.vtkRenderer()
        x0, x1 = (0.0, 0.5) if index == 0 else (0.5, 1.0)
        renderer.SetViewport(x0, 0.15, x1, 0.88)
        renderer.SetBackground(0.965, 0.953, 0.925)
        renderer.SetBackground2(0.93, 0.91, 0.86)
        renderer.GradientBackgroundOn()

        mapper = vtk.vtkPolyDataMapper()
        polydata = make_polydata(vertices_a, faces_a, data["face_rgb_linear"], data["face_region"])
        mapper.SetInputData(polydata)
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().LightingOff()
        renderer.AddActor(actor)

        camera = vtk.vtkCamera()
        camera.SetFocalPoint(0.0, 0.0, 6.0)
        camera.SetPosition(38.0, -54.0, 37.0)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.SetParallelProjection(True)
        camera.SetParallelScale(PARALLEL_SCALE_MM)
        camera.SetClippingRange(0.1, 200.0)
        renderer.SetActiveCamera(camera)
        panel_x = 36 if index == 0 else 936
        add_overlay_text(renderer, title, panel_x, 930, 22, bold=True)
        add_overlay_text(renderer, "Ro 12 mm  |  Ri 8 mm", panel_x, 900, 15)
        add_overlay_text(renderer, "Orthographic view; common scale in mm", panel_x, 875, 13)
        render_window.AddRenderer(renderer)
        panel_renderers.append(renderer)

    overlay = vtk.vtkRenderer()
    overlay.SetViewport(0.0, 0.0, 1.0, 1.0)
    overlay.SetLayer(1)
    overlay.SetInteractive(False)
    overlay.SetPreserveColorBuffer(True)
    overlay.SetPreserveDepthBuffer(False)
    overlay.SetBackground(0.965, 0.953, 0.925)
    overlay.SetBackgroundAlpha(0.0)
    overlay.EraseOff()
    add_overlay_text(overlay, "VESSELFORGE  /  CONCENTRIC LOWER-HEMISPHERE CANDIDATE", 42, 1068, 21, bold=True)
    add_overlay_text(overlay, "Rest-coordinate procedural paint  |  flat per-face asset colors  |  analytic shell Ro 12 mm, Ri 8 mm", 42, 1035, 15)
    add_overlay_text(overlay, "Paint and mechanics are illustrative; material status UNVALIDATED_PROTOTYPE. Geometry preview only.", 42, 23, 15)
    render_window.AddRenderer(overlay)

    render_window.Render()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(render_window)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    capture.Update()
    dims = capture.GetOutput().GetDimensions()
    if max(dims[0], dims[1]) < 1400:
        raise ValueError(f"render resolution is below the requested long-edge size: {dims[0]}x{dims[1]}")
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(OUTPUT_PNG))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()

    reader = vtk.vtkPNGReader()
    reader.SetFileName(str(OUTPUT_PNG))
    reader.Update()
    image_dimensions = reader.GetOutput().GetDimensions()
    image_array = vtk_to_numpy(reader.GetOutput().GetPointData().GetScalars())
    if max(image_dimensions[0], image_dimensions[1]) < 1400 or not np.isfinite(image_array).all():
        raise ValueError("PNG output failed dimension or pixel-finiteness checks")
    rendered_rgb = image_array.reshape(image_dimensions[1], image_dimensions[0], 3)
    red_pixels = (rendered_rgb[:, :, 0].astype(np.int16) > 1.3 * rendered_rgb[:, :, 1]) & (rendered_rgb[:, :, 0] > 80) & (rendered_rgb[:, :, 1] < 150)
    dark_pixels = (rendered_rgb.mean(axis=2) < 90) & (rendered_rgb[:, :, 0] > rendered_rgb[:, :, 1])
    pigment_coverage = {
        "three_bands_red_pixels": int(red_pixels[:, : IMAGE_SIZE[0] // 2].sum()),
        "three_bands_dark_pixels": int(dark_pixels[:, : IMAGE_SIZE[0] // 2].sum()),
        "four_bands_red_pixels": int(red_pixels[:, IMAGE_SIZE[0] // 2 :].sum()),
        "four_bands_dark_pixels": int(dark_pixels[:, IMAGE_SIZE[0] // 2 :].sum()),
    }
    if any(count < 100 for count in pigment_coverage.values()):
        raise ValueError(f"one or more procedural pigment colors are not visibly represented: {pigment_coverage}")

    receipt = {
        "schema": "vf.spherical_bowl_visualization_receipt.v1",
        "status": "PASS",
        "renderer_source": str(Path(__file__).resolve()),
        "renderer_source_sha256": sha256_file(Path(__file__).resolve()),
        "image_path": str(OUTPUT_PNG),
        "image_sha256": sha256_file(OUTPUT_PNG),
        "image_bytes": OUTPUT_PNG.stat().st_size,
        "image_dimensions_px": [int(image_dimensions[0]), int(image_dimensions[1])],
        "render_wall_seconds": time.monotonic() - started,
        "renderer": {"name": "VTK offscreen z-buffer rasterization", "version": vtk.vtkVersion.GetVTKVersion()},
        "visual_method": {
            "geometry": "all saved canonical surface vertices and triangles; no downsampling",
            "color": "per-face albedo read from each asset fields/surface.npz, transformed linear RGB to sRGB for display",
            "rest_coordinates": "verified vertices_material_xyz_mm is elementwise equal to geometry/surface.npz vertices_mm after float64 loading",
            "lighting": "fixed neutral ambient/diffuse factor computed from each mesh triangle normal; no material calibration or physical inference",
            "projection": "orthographic parallel camera; both panes share focal point, view direction, and parallel scale",
            "parallel_scale_mm": PARALLEL_SCALE_MM,
            "camera_focal_point_mm": [0.0, 0.0, 6.0],
            "camera_position_mm": [38.0, -54.0, 37.0],
            "framing": "side-by-side, same orientation and equal mm scale; no geometry or color downsampling",
            "disclaimer": "illustrative procedural paint and unvalidated prototype material; geometry preview only",
        },
        "checks": {
            "both_assets_share_identical_rest_mesh": True,
            "all_faces_rendered": True,
            "long_edge_at_least_1400px": max(image_dimensions[0], image_dimensions[1]) >= 1400,
            "visible_pigment_pixel_counts": pigment_coverage,
        },
        "inputs": {"three_bands": data_three["input_record"], "four_bands": data_four["input_record"]},
    }
    write_json(OUTPUT_RECEIPT, receipt)
    render_window.Finalize()
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

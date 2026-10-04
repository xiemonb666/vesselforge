"""One-shot checker and data-driven renderer for the isolated VF surface fixture.

Imports the frozen prototype once, builds its default hollow-cylinder fixture
once, and samples its default 0.45 mm / 8-motif field once. Raw arrays and check
evidence are saved before rendering. A failed check stops the run; do not rerun.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


EXPECTED_PROTOTYPE_SHA256 = "0f624f8482d4d6540a0594ca1cbebebf1d02179d15a1e9fa05d3924107b12177"
PARAMETERS = {
    "fixture": {
        "outer_radius_mm": 20.0,
        "wall_mm": 3.0,
        "height_mm": 24.0,
        "floor_mm": 2.0,
        "around": 128,
        "side_rows": 25,
        "invocation": "build_closed_cylinder_fixture() using the frozen source defaults",
    },
    "field": {
        "repeat_count": 8,
        "center_z_mm": 13.0,
        "circumferential_half_width_mm": 2.7,
        "vertical_half_height_mm": 2.1,
        "raised_height_mm": 0.45,
        "base_linear_rgb": [0.66, 0.49, 0.34],
        "pigment_linear_rgb": [0.095, 0.032, 0.018],
        "invocation": "sample_and_displace_outer_motifs(fixture) using the frozen source defaults",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def add_check(checks: list[dict[str, object]], name: str, passed: bool, evidence: dict[str, object]) -> None:
    checks.append({"name": name, "status": "PASS" if passed else "FAIL", "evidence": evidence})


def edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def topology_metrics(vertices: np.ndarray, faces: np.ndarray) -> dict[str, object]:
    n_vertices = int(len(vertices))
    edge_dirs: dict[tuple[int, int], list[int]] = defaultdict(list)
    face_keys: Counter[tuple[int, int, int]] = Counter()
    repeated_vertex_faces = 0
    double_areas: list[float] = []
    parent = list(range(n_vertices))
    rank = [0] * n_vertices

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            parent[ra] = rb
        elif rank[ra] > rank[rb]:
            parent[rb] = ra
        else:
            parent[rb] = ra
            rank[ra] += 1

    for face in faces.astype(np.int64, copy=False):
        a, b, c = map(int, face)
        if len({a, b, c}) != 3:
            repeated_vertex_faces += 1
            continue
        face_keys[tuple(sorted((a, b, c)))] += 1
        p0, p1, p2 = vertices[a], vertices[b], vertices[c]
        double_areas.append(float(np.linalg.norm(np.cross(p1 - p0, p2 - p0))))
        for start, end in ((a, b), (b, c), (c, a)):
            edge_dirs[edge_key(start, end)].append(1 if start < end else -1)

    incidence = {key: len(directions) for key, directions in edge_dirs.items()}
    boundary = sum(count == 1 for count in incidence.values())
    not_two = sum(count != 2 for count in incidence.values())
    bad_winding = sum(len(dirs) == 2 and sum(dirs) != 0 for dirs in edge_dirs.values())
    duplicate_faces = sum(count - 1 for count in face_keys.values() if count > 1)
    zero_area = sum(area <= 1e-12 for area in double_areas)
    for face in faces.astype(np.int64, copy=False):
        a, b, c = map(int, face)
        if len({a, b, c}) == 3:
            union(a, b)
            union(b, c)
            union(c, a)
    components = len({find(index) for index in range(n_vertices)})
    volume = float(
        np.einsum(
            "ij,ij->i",
            vertices[faces[:, 0]],
            np.cross(vertices[faces[:, 1]], vertices[faces[:, 2]]),
        ).sum()
        / 6.0
    )
    return {
        "vertex_count": n_vertices,
        "face_count": int(len(faces)),
        "unique_undirected_edge_count": int(len(edge_dirs)),
        "boundary_edge_count": int(boundary),
        "non_two_incidence_edge_count": int(not_two),
        "nonmanifold_edges_count_including_boundary": int(not_two),
        "inconsistent_winding_edge_count": int(bad_winding),
        "duplicated_face_count_unoriented": int(duplicate_faces),
        "repeated_vertex_face_count": int(repeated_vertex_faces),
        "zero_area_face_count_threshold_1e-12_mm2_double_area": int(zero_area),
        "minimum_double_area_mm2": float(min(double_areas)) if double_areas else None,
        "connected_component_count": int(components),
        "signed_volume_mm3": volume,
        "positive_signed_volume": bool(volume > 0.0),
        "closed_two_manifold": bool(not_two == 0),
        "consistent_winding": bool(bad_winding == 0),
    }


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    return np.where(
        values <= 0.0031308,
        12.92 * values,
        1.055 * np.power(values, 1.0 / 2.4) - 0.055,
    )


def face_colors_for_display(
    vertices: np.ndarray,
    faces: np.ndarray,
    outer_ids: np.ndarray,
    outer_linear: np.ndarray,
    base_linear: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    lookup = np.full(len(vertices), -1, dtype=np.int64)
    lookup[outer_ids] = np.arange(len(outer_ids), dtype=np.int64)
    outer_face = np.all(np.isin(faces, outer_ids), axis=1)
    face_linear = np.broadcast_to(base_linear, (len(faces), 3)).copy()
    face_linear[outer_face] = np.mean(outer_linear[lookup[faces[outer_face]]], axis=1)
    tri = vertices[faces]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-30)
    light = np.asarray((-0.35, -0.55, 0.76), dtype=np.float64)
    light /= np.linalg.norm(light)
    lambert = np.maximum(normals @ light, 0.0)
    shaded_linear = np.clip(face_linear * (0.40 + 0.60 * lambert[:, None]), 0.0, 1.0)
    return srgb_encode(shaded_linear), outer_face


def section_segments(
    vertices: np.ndarray,
    faces: np.ndarray,
    y_cut: float,
    display_face_colors: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    segments: list[list[list[float]]] = []
    colors: list[list[float]] = []
    for face_index, face in enumerate(faces):
        tri = vertices[face]
        signed = tri[:, 1] - y_cut
        hits: list[np.ndarray] = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            di, dj = float(signed[i]), float(signed[j])
            if di * dj < 0.0:
                t = di / (di - dj)
                hits.append(tri[i] + t * (tri[j] - tri[i]))
            elif abs(di) <= 1e-12:
                hits.append(tri[i].copy())
        unique: list[np.ndarray] = []
        for point in hits:
            if not any(np.linalg.norm(point - prior) <= 1e-10 for prior in unique):
                unique.append(point)
        if len(unique) < 2:
            continue
        if len(unique) > 2:
            pair = max(
                ((a, b) for k, a in enumerate(unique) for b in unique[k + 1 :]),
                key=lambda item: float(np.linalg.norm(item[0] - item[1])),
            )
            unique = [pair[0], pair[1]]
        segments.append([[float(unique[0][0]), float(unique[0][2])], [float(unique[1][0]), float(unique[1][2])]])
        colors.append([float(channel) for channel in display_face_colors[face_index]])
    if not segments:
        return np.empty((0, 2, 2), dtype=np.float64), np.empty((0, 3), dtype=np.float64)
    return np.asarray(segments, dtype=np.float64), np.asarray(colors, dtype=np.float64)


def render_from_saved_npz(npz_path: Path, params_path: Path, png_path: Path) -> dict[str, object]:
    params = json.loads(params_path.read_text(encoding="utf-8"))
    with np.load(npz_path, allow_pickle=False) as data:
        rest = data["vertices_rest_xyz_mm"].copy()
        relief = data["vertices_relief_xyz_mm"].copy()
        faces = data["faces"].copy()
        outer_ids = data["outer_side_vertex_indices"].copy()
        outer_linear = data["outer_color_linear_rgb"].copy()
        outer_srgb = data["outer_color_srgb_for_display"].copy()
        outer_height = data["outer_relief_height_mm"].copy()
        radius = float(data["outer_radius_mm"])
        body_height = float(data["height_mm"])
        around = int(data["around"])
        rows = int(data["side_rows"])

    base_linear = np.asarray(params["field"]["base_linear_rgb"], dtype=np.float64)
    face_srgb, outer_face = face_colors_for_display(relief, faces, outer_ids, outer_linear, base_linear)
    polygons = [triangle for triangle in relief[faces]]
    max_index = int(np.argmax(outer_height))
    max_vertex = int(outer_ids[max_index])
    rest_point = rest[max_vertex]
    relief_point = relief[max_vertex]
    max_height = float(outer_height[max_index])
    cut_y = 1e-4
    segments, segment_colors = section_segments(relief, faces, cut_y, face_srgb)

    fig = plt.figure(figsize=(15.0, 11.0), constrained_layout=True)
    ax_outside = fig.add_subplot(2, 2, 1, projection="3d")
    ax_detail = fig.add_subplot(2, 2, 2, projection="3d")
    ax_section = fig.add_subplot(2, 2, 3)
    ax_swatch = fig.add_subplot(2, 2, 4)

    ax_outside.add_collection3d(
        Poly3DCollection(polygons, facecolors=face_srgb, linewidths=0, antialiaseds=False, zsort="average")
    )
    margin = 1.8
    ax_outside.set_xlim(-radius - margin, radius + margin)
    ax_outside.set_ylim(-radius - margin, radius + margin)
    ax_outside.set_zlim(-margin, body_height + margin)
    ax_outside.set_box_aspect((2 * radius + 2 * margin, 2 * radius + 2 * margin, body_height + 2 * margin))
    ax_outside.view_init(elev=18, azim=-36)
    ax_outside.set_xlabel("x (mm)")
    ax_outside.set_ylabel("y (mm)")
    ax_outside.set_zlabel("z (mm)")
    ax_outside.set_title("Outside view: saved displaced boundary")

    outer_triangles = faces[outer_face]
    detail_polygons = [relief[triangle] for triangle in outer_triangles]
    ax_detail.add_collection3d(
        Poly3DCollection(
            detail_polygons,
            facecolors=face_srgb[outer_face],
            linewidths=0,
            antialiaseds=False,
            zsort="average",
        )
    )
    bounds = (radius - 4.0, radius + 0.8, -4.5, 4.5, 9.0, 17.0)
    ax_detail.set_xlim(bounds[0], bounds[1])
    ax_detail.set_ylim(bounds[2], bounds[3])
    ax_detail.set_zlim(bounds[4], bounds[5])
    ax_detail.set_box_aspect((bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]))
    ax_detail.view_init(elev=22, azim=-36)
    ax_detail.set_xlabel("x (mm)")
    ax_detail.set_ylabel("y (mm)")
    ax_detail.set_zlabel("z (mm)")
    ax_detail.set_title(f"Outer-wall detail: true mesh height {max_height:.2f} mm")
    ax_detail.scatter([relief_point[0]], [relief_point[1]], [relief_point[2]], s=18, c="white", edgecolors="black")
    ax_detail.text(
        float(relief_point[0]),
        float(relief_point[1]),
        float(relief_point[2] + 0.35),
        f"saved max h = {max_height:.2f} mm",
        fontsize=8,
    )

    if len(segments) == 0:
        raise RuntimeError("saved triangle mesh produced no section segments")
    section_lines = np.stack((segments[:, 0, :], segments[:, 1, :]), axis=1)
    ax_section.add_collection(LineCollection(section_lines, colors=segment_colors, linewidths=1.1))
    ax_section.set_xlim(-radius - 3.0, radius + 3.0)
    ax_section.set_ylim(-1.0, body_height + 1.0)
    ax_section.set_aspect("equal", adjustable="box")
    ax_section.set_xlabel("x (mm)")
    ax_section.set_ylabel("z (mm)")
    ax_section.set_title(f"Triangle-mesh section at y = {cut_y:g} mm (mm scale)")
    ax_section.grid(True, linewidth=0.3, alpha=0.35)

    inset = ax_section.inset_axes([0.56, 0.46, 0.42, 0.48])
    inset.add_collection(LineCollection(section_lines, colors=segment_colors, linewidths=1.2))
    inset.set_xlim(radius - 4.0, radius + 0.8)
    center_z = float(params["field"]["center_z_mm"])
    inset.set_ylim(center_z - 3.5, center_z + 3.5)
    inset.set_aspect("equal", adjustable="box")
    inset.set_title("Relief detail (mm)", fontsize=8)
    inset.tick_params(labelsize=7)
    inset.annotate(
        "",
        xy=(float(relief_point[0]), float(relief_point[2])),
        xytext=(float(rest_point[0]), float(rest_point[2])),
        arrowprops={"arrowstyle": "<->", "color": "black", "linewidth": 1.0},
    )
    inset.text(
        0.03,
        0.91,
        f"saved vertex displacement = {max_height:.2f} mm",
        transform=inset.transAxes,
        fontsize=7,
        va="top",
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 1.5},
    )

    color_grid = outer_srgb.reshape((rows, around, 3))
    ax_swatch.imshow(
        color_grid,
        origin="lower",
        interpolation="nearest",
        extent=(0.0, 2.0 * math.pi * radius, 0.0, body_height),
        aspect="equal",
    )
    ax_swatch.set_xlabel("circumferential arc length R theta (mm)")
    ax_swatch.set_ylabel("z (mm)")
    ax_swatch.set_title("Saved outer color samples, encoded sRGB")
    fig.suptitle(
        "VF analytic cylinder mapping fixture only | physics qualification UNKNOWN | no fracture labels",
        fontsize=13,
    )
    fig.savefig(png_path, dpi=180)
    plt.close(fig)
    return {
        "renderer": "Matplotlib Poly3DCollection and LineCollection from saved NPZ",
        "render_input_npz_sha256": sha256_file(npz_path),
        "png_sha256": sha256_file(png_path),
        "section_cut_y_mm": cut_y,
        "section_segment_count": int(len(segments)),
        "swatch_shape": [rows, around, 3],
        "swatch_input_srgb_min": float(np.min(color_grid)),
        "swatch_input_srgb_max": float(np.max(color_grid)),
        "geometry_source": "vertices_relief_xyz_mm and faces loaded from saved NPZ",
        "color_source": "outer_color_srgb_for_display loaded from saved NPZ",
        "coordinate_scale": "equal millimeter axes; cylinder fixture only",
        "physics_qualification": "UNKNOWN",
        "fracture_labels": "NONE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prototype", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    prototype_path = Path(args.prototype).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()
    params_sha = canonical_sha256(PARAMETERS)
    prototype_sha = sha256_file(prototype_path) if prototype_path.exists() else None
    checker_sha = sha256_file(script_path)
    python_exe = str(Path(sys.executable).resolve())
    write_json(
        output_dir / "execution_argv.json",
        {
            "executable": python_exe,
            "argv": [str(value) for value in sys.argv],
            "full_argv_vector": [python_exe, *[str(value) for value in sys.argv]],
            "working_directory": str(Path.cwd()),
        },
    )
    write_json(output_dir / "fixture_parameters.json", PARAMETERS)
    write_json(
        output_dir / "source_parameter_hashes.json",
        {
            "prototype_sha256_expected": EXPECTED_PROTOTYPE_SHA256,
            "prototype_sha256_actual": prototype_sha,
            "checker_sha256": checker_sha,
            "parameters_sha256": params_sha,
            "hash_algorithm": "SHA-256",
        },
    )
    write_json(
        output_dir / "runtime.json",
        {
            "python_executable": python_exe,
            "python_version": sys.version,
            "numpy_version": np.__version__,
            "matplotlib_version": matplotlib.__version__,
            "cadquery_imported": False,
            "cad_step_solver_used": False,
        },
    )

    checks: list[dict[str, object]] = []
    add_check(
        checks,
        "frozen_prototype_sha256",
        prototype_sha == EXPECTED_PROTOTYPE_SHA256,
        {"expected": EXPECTED_PROTOTYPE_SHA256, "actual": prototype_sha, "path": str(prototype_path)},
    )
    if prototype_sha != EXPECTED_PROTOTYPE_SHA256:
        write_json(output_dir / "checks.json", checks)
        write_json(
            output_dir / "run_status.json",
            {"status": "STOP_FAIL_FROZEN_SOURCE_MISMATCH", "checks": checks, "execution_status": "NOT_RUN_FIXTURE"},
        )
        print("STOP: prototype SHA mismatch; fixture was not built.")
        return 2

    try:
        spec = importlib.util.spec_from_file_location("surface_mapping_prototype", prototype_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load frozen prototype source")
        prototype = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prototype)
        fixture = prototype.build_closed_cylinder_fixture()
        original_rest = fixture.vertices_rest_xyz_mm.copy()
        result = prototype.sample_and_displace_outer_motifs(fixture)

        rest = np.asarray(result["vertices_rest_xyz_mm"], dtype=np.float64)
        relief = np.asarray(result["vertices_relief_xyz_mm"], dtype=np.float64)
        faces = np.asarray(result["faces"], dtype=np.int64)
        outer_ids = np.asarray(result["outer_side_vertex_indices"], dtype=np.int64)
        normals = np.asarray(result["outer_normals_material_outward"], dtype=np.float64)
        heights = np.asarray(result["outer_relief_height_mm"], dtype=np.float64)
        linear = np.asarray(result["outer_color_linear_rgb"], dtype=np.float64)
        srgb = np.asarray(result["outer_color_srgb_for_display"], dtype=np.float64)
        theta = np.asarray(fixture.outer_side_theta_rad, dtype=np.float64)
        z = np.asarray(fixture.outer_side_z_mm, dtype=np.float64)
        around = int(PARAMETERS["fixture"]["around"])
        rows = int(PARAMETERS["fixture"]["side_rows"])
        inner_ids = np.arange(int(np.max(outer_ids)) + 1, int(np.max(outer_ids)) + 1 + rows * around, dtype=np.int64)

        arrays_path = output_dir / "fixture_arrays.npz"
        np.savez_compressed(
            arrays_path,
            vertices_rest_xyz_mm=rest,
            vertices_relief_xyz_mm=relief,
            faces=faces.astype(np.int32),
            outer_side_vertex_indices=outer_ids,
            inner_side_vertex_indices=inner_ids,
            outer_color_linear_rgb=linear,
            outer_color_srgb_for_display=srgb,
            outer_relief_height_mm=heights,
            outer_normals_material_outward=normals,
            outer_side_theta_rad=theta,
            outer_side_z_mm=z,
            outer_radius_mm=np.float64(fixture.outer_radius_mm),
            inner_radius_mm=np.float64(fixture.inner_radius_mm),
            wall_declaration_mm=np.float64(PARAMETERS["fixture"]["wall_mm"]),
            height_mm=np.float64(fixture.height_mm),
            floor_mm=np.float64(fixture.floor_mm),
            around=np.int32(around),
            side_rows=np.int32(rows),
        )
        arrays_sha = sha256_file(arrays_path)

        finite = all(np.isfinite(array).all() for array in (rest, relief, linear, srgb, heights, normals, theta, z))
        add_check(
            checks,
            "all_saved_numeric_arrays_finite",
            bool(finite),
            {
                "rest": bool(np.isfinite(rest).all()),
                "relief": bool(np.isfinite(relief).all()),
                "linear_rgb": bool(np.isfinite(linear).all()),
                "srgb": bool(np.isfinite(srgb).all()),
                "height": bool(np.isfinite(heights).all()),
                "normals": bool(np.isfinite(normals).all()),
            },
        )
        rest_same = np.array_equal(fixture.vertices_rest_xyz_mm, original_rest) and np.array_equal(rest, original_rest)
        add_check(
            checks,
            "immutable_rest_coordinates",
            bool(rest_same),
            {
                "fixture_rest_equals_pre_sample_copy": bool(np.array_equal(fixture.vertices_rest_xyz_mm, original_rest)),
                "saved_rest_equals_pre_sample_copy": bool(np.array_equal(rest, original_rest)),
                "vertex_count": int(len(rest)),
            },
        )

        indices_valid = (
            rest.ndim == 2
            and rest.shape[1] == 3
            and relief.shape == rest.shape
            and faces.ndim == 2
            and faces.shape[1] == 3
            and len(faces) > 0
            and int(np.min(faces)) >= 0
            and int(np.max(faces)) < len(rest)
            and int(np.min(outer_ids)) >= 0
            and int(np.max(outer_ids)) < len(rest)
        )
        add_check(
            checks,
            "array_shapes_and_face_indices",
            bool(indices_valid),
            {
                "rest_shape": list(rest.shape),
                "relief_shape": list(relief.shape),
                "faces_shape": list(faces.shape),
                "outer_id_count": int(len(outer_ids)),
                "face_index_min": int(np.min(faces)),
                "face_index_max": int(np.max(faces)),
            },
        )
        if not indices_valid:
            write_json(output_dir / "checks.json", checks)
            write_json(
                output_dir / "run_status.json",
                {
                    "status": "STOP_FAIL_ARRAY_SHAPES",
                    "checks": checks,
                    "fixture_arrays_npz": arrays_path.name,
                    "fixture_arrays_sha256": arrays_sha,
                    "renderer_status": "NOT_RUN_AFTER_CHECK_FAILURE",
                },
            )
            print("STOP: invalid array shape/index evidence saved.")
            return 3

        movement = relief - rest
        outer_movement = movement[outer_ids]
        normal_projection = np.einsum("ij,ij->i", outer_movement, normals)
        tangent_residual = outer_movement - heights[:, None] * normals
        max_h = float(np.max(heights))
        max_move = float(np.max(np.linalg.norm(outer_movement, axis=1)))
        nonzero = int(np.count_nonzero(np.linalg.norm(outer_movement, axis=1) > 1e-12))
        normal_ok = (
            nonzero > 0
            and abs(max_move - max_h) <= 1e-12
            and float(np.max(np.abs(normal_projection - heights))) <= 1e-12
            and float(np.max(np.linalg.norm(tangent_residual, axis=1))) <= 1e-12
        )
        add_check(
            checks,
            "actual_nonzero_outer_normal_displacement",
            bool(normal_ok),
            {
                "nonzero_outer_vertex_count": nonzero,
                "maximum_saved_height_mm": max_h,
                "maximum_actual_vertex_displacement_mm": max_move,
                "max_normal_projection_error_mm": float(np.max(np.abs(normal_projection - heights))),
                "max_tangential_residual_mm": float(np.max(np.linalg.norm(tangent_residual, axis=1))),
            },
        )

        n_vertices = len(rest)
        outer_mask = np.zeros(n_vertices, dtype=bool)
        outer_mask[outer_ids] = True
        nonouter_same = np.array_equal(relief[~outer_mask], rest[~outer_mask])
        outer_grid = outer_ids.reshape((rows, around))
        height_grid = heights.reshape((rows, around))
        end_rings_same = (
            np.array_equal(relief[outer_grid[[0, -1]]], rest[outer_grid[[0, -1]]])
            and np.all(height_grid[[0, -1]] == 0.0)
        )
        add_check(
            checks,
            "inner_wall_floor_lip_and_outer_rim_unchanged",
            bool(nonouter_same and end_rings_same),
            {
                "all_non_outer_vertices_unchanged": bool(nonouter_same),
                "outer_bottom_and_lip_rings_unchanged": bool(end_rings_same),
                "inner_wall_vertex_count": int(len(inner_ids)),
                "shared_closed_face_mesh_includes_inner_wall_floor_rim": True,
            },
        )

        topology = topology_metrics(relief, faces)
        topology_ok = (
            topology["closed_two_manifold"]
            and topology["boundary_edge_count"] == 0
            and topology["non_two_incidence_edge_count"] == 0
            and topology["duplicated_face_count_unoriented"] == 0
            and topology["repeated_vertex_face_count"] == 0
            and topology["zero_area_face_count_threshold_1e-12_mm2_double_area"] == 0
            and topology["inconsistent_winding_edge_count"] == 0
            and topology["connected_component_count"] == 1
            and topology["positive_signed_volume"]
        )
        add_check(checks, "closed_mesh_incidence_winding_connectivity_volume", bool(topology_ok), topology)

        edge_counts: dict[tuple[int, int], int] = {}
        for face in faces:
            for a, b in ((int(face[0]), int(face[1])), (int(face[1]), int(face[2])), (int(face[2]), int(face[0]))):
                key = edge_key(a, b)
                edge_counts[key] = edge_counts.get(key, 0) + 1
        inner_grid = inner_ids.reshape((rows, around))
        seam_counts = [
            edge_counts.get(edge_key(int(grid[row, -1]), int(grid[row, 0])), 0)
            for grid in (outer_grid, inner_grid)
            for row in range(rows)
        ]
        ring_grids = {
            "outer_underside": outer_grid[0],
            "inner_floor": inner_grid[0],
            "outer_lip": outer_grid[-1],
            "inner_lip": inner_grid[-1],
        }
        ring_counts = {
            name: [
                edge_counts.get(edge_key(int(ring[i]), int(ring[(i + 1) % around])), 0)
                for i in range(around)
            ]
            for name, ring in ring_grids.items()
        }
        unique_theta = all(
            np.unique(rest[grid[row]], axis=0).shape[0] == around
            for grid in (outer_grid, inner_grid)
            for row in range(rows)
        )
        seam_ok = (
            all(count == 2 for count in seam_counts)
            and all(count == 2 for values in ring_counts.values() for count in values)
            and unique_theta
        )
        add_check(
            checks,
            "theta_modulo_seam_and_rim_floor_closure",
            bool(seam_ok),
            {
                "periodic_seam_edge_incidence_counts": seam_counts,
                "all_underside_floor_lip_ring_edges_have_incidence_two": {
                    name: bool(all(count == 2 for count in values)) for name, values in ring_counts.items()
                },
                "no_duplicate_theta_vertices_in_any_ring": bool(unique_theta),
            },
        )

        period_steps = around // int(PARAMETERS["field"]["repeat_count"])
        period_errors = [
            float(
                np.max(
                    np.abs(
                        height_grid
                        - np.roll(height_grid, (multiple * period_steps) % around, axis=1)
                    )
                )
            )
            for multiple in range(1, int(PARAMETERS["field"]["repeat_count"]) + 1)
        ]
        max_period_error = max(period_errors)
        add_check(
            checks,
            "saved_height_rotational_periodicity",
            max_period_error <= 1e-12,
            {
                "repeat_count": int(PARAMETERS["field"]["repeat_count"]),
                "samples_per_repeat": period_steps,
                "maximum_height_period_error_mm": max_period_error,
            },
        )

        radial_wall = np.linalg.norm(relief[outer_ids, :2], axis=1) - float(fixture.inner_radius_mm)
        radial_min = float(np.min(radial_wall))
        declared_wall = float(PARAMETERS["fixture"]["wall_mm"])
        wall_ok = radial_min >= declared_wall - 1e-10
        add_check(
            checks,
            "analytic_fixture_radial_wall_proxy_only",
            bool(wall_ok),
            {
                "minimum_radial_separation_mm": radial_min,
                "declared_radial_wall_mm": declared_wall,
                "scope": "exact only for this concentric analytic cylinder with radial outer displacement",
                "curved_profile_wall": "NOT_ASSESSED",
                "global_minimum_wall": "NOT_ASSESSED",
                "collision_or_self_intersection": "NOT_ASSESSED",
                "general_offset_singularity": "NOT_ASSESSED",
            },
        )

        expected_srgb = srgb_encode(linear)
        srgb_error = float(np.max(np.abs(expected_srgb - srgb)))
        srgb_ok = (
            srgb_error <= 1e-12
            and float(np.min(srgb)) >= 0.0
            and float(np.max(srgb)) <= 1.0
            and float(np.max(np.abs(srgb - linear))) > 0.05
        )
        base_i, peak_i = int(np.argmin(heights)), int(np.argmax(heights))
        rgb_values = {
            "base_linear_rgb": [float(x) for x in linear[base_i]],
            "base_srgb_actual": [float(x) for x in srgb[base_i]],
            "base_srgb_8bit_round": [int(x) for x in np.rint(srgb[base_i] * 255.0)],
            "peak_linear_rgb": [float(x) for x in linear[peak_i]],
            "peak_srgb_actual": [float(x) for x in srgb[peak_i]],
            "peak_srgb_8bit_round": [int(x) for x in np.rint(srgb[peak_i] * 255.0)],
            "maximum_standard_transfer_error": srgb_error,
            "maximum_srgb_vs_linear_difference": float(np.max(np.abs(srgb - linear))),
            "display_array_used": "outer_color_srgb_for_display",
        }
        add_check(checks, "linear_to_srgb_display_values", bool(srgb_ok), rgb_values)
        write_json(output_dir / "display_rgb_values.json", rgb_values)

        write_json(
            output_dir / "geometry_metrics.json",
            {
                "topology": topology,
                "surface_displacement": {
                    "maximum_height_mm": max_h,
                    "maximum_actual_vertex_displacement_mm": max_move,
                    "maximum_normal_projection_error_mm": float(np.max(np.abs(normal_projection - heights))),
                    "maximum_tangential_residual_mm": float(np.max(np.linalg.norm(tangent_residual, axis=1))),
                },
                "analytic_wall_proxy": {
                    "minimum_radial_separation_mm": radial_min,
                    "declared_radial_wall_mm": declared_wall,
                    "scope": "fixture only",
                },
                "curvature_proxy": {
                    "max_height_times_cylinder_curvature": float(max_h / float(fixture.outer_radius_mm)),
                    "scope": "fixture-only scalar proxy; no general offset qualification",
                },
                "height_periodicity": {
                    "repeat_count": int(PARAMETERS["field"]["repeat_count"]),
                    "maximum_period_error_mm": max_period_error,
                },
                "general_geometry_status": {
                    "self_intersection": "NOT_ASSESSED",
                    "offset_validity": "NOT_ASSESSED",
                    "curved_or_global_minimum_wall": "NOT_ASSESSED",
                    "physics_qualification": "UNKNOWN",
                    "fracture_labels": "NONE",
                },
            },
        )

        if any(item["status"] == "FAIL" for item in checks):
            write_json(output_dir / "checks.json", checks)
            write_json(
                output_dir / "run_status.json",
                {
                    "status": "STOP_FAIL_CHECKS",
                    "checks": checks,
                    "fixture_arrays_npz": arrays_path.name,
                    "fixture_arrays_sha256": arrays_sha,
                    "renderer_status": "NOT_RUN_AFTER_CHECK_FAILURE",
                    "physics_qualification": "UNKNOWN",
                    "general_self_intersection_offset_or_global_wall": "NOT_ASSESSED",
                },
            )
            print("STOP: fixture check failure; raw arrays and evidence saved, no rerun.")
            return 3

        png_path = output_dir / "surface_ornament_fixture.png"
        try:
            render_metrics = render_from_saved_npz(arrays_path, output_dir / "fixture_parameters.json", png_path)
            add_check(checks, "data_driven_png_render", True, render_metrics)
        except Exception as exc:
            add_check(
                checks,
                "data_driven_png_render",
                False,
                {"exception": repr(exc), "traceback": traceback.format_exc(), "rerun_policy": "NO_RERUN"},
            )
            write_json(output_dir / "checks.json", checks)
            write_json(
                output_dir / "run_status.json",
                {
                    "status": "STOP_FAIL_RENDER",
                    "checks": checks,
                    "fixture_arrays_npz": arrays_path.name,
                    "fixture_arrays_sha256": arrays_sha,
                    "physics_qualification": "UNKNOWN",
                    "general_self_intersection_offset_or_global_wall": "NOT_ASSESSED",
                },
            )
            print("STOP: renderer failure; raw arrays and evidence saved, no rerun.")
            return 4

        write_json(output_dir / "checks.json", checks)
        write_json(
            output_dir / "run_status.json",
            {
                "status": "PASS_TINY_FIXTURE_LOCAL_CHECKS_ONLY",
                "checks": checks,
                "fixture_arrays_npz": arrays_path.name,
                "fixture_arrays_sha256": arrays_sha,
                "rendered_png": png_path.name,
                "rendered_png_sha256": sha256_file(png_path),
                "physics_qualification": "UNKNOWN",
                "general_self_intersection_offset_or_global_wall": "NOT_ASSESSED",
                "fracture_labels": "NONE",
            },
        )
        print("status=PASS_TINY_FIXTURE_LOCAL_CHECKS_ONLY")
        print(f"prototype_sha256={prototype_sha}")
        print(f"parameters_sha256={params_sha}")
        print(f"fixture_arrays_sha256={arrays_sha}")
        print(f"maximum_height_mm={max_h:.12g}")
        print(f"maximum_actual_vertex_displacement_mm={max_move:.12g}")
        print(f"minimum_radial_wall_proxy_mm={radial_min:.12g}")
        print(f"connected_components={topology['connected_component_count']}")
        print(f"signed_volume_mm3={topology['signed_volume_mm3']:.12g}")
        print(f"rendered_png={png_path}")
        print("physics_qualification=UNKNOWN; general_wall_collision_self_intersection=NOT_ASSESSED")
        return 0
    except Exception as exc:
        failure = {
            "status": "STOP_FAIL_RUNTIME",
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
            "checks_so_far": checks,
            "prototype_sha256": prototype_sha,
            "checker_sha256": checker_sha,
            "parameters_sha256": params_sha,
            "fixture_arrays_exist": (output_dir / "fixture_arrays.npz").exists(),
            "rerun_policy": "NO_RERUN",
        }
        write_json(output_dir / "runtime_failure.json", failure)
        write_json(output_dir / "checks.json", checks)
        write_json(output_dir / "run_status.json", failure)
        print(f"STOP: runtime failure; evidence captured. {exc!r}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

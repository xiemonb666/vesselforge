"""Unexecuted, NumPy-only source sketch for a tiny surface-ornament fixture.

This is a VF-side mapping fixture only. It creates a closed hollow-cylinder
triangle boundary in memory, samples one periodic motif at immutable exterior
rest coordinates, and constructs a separate displaced vertex array along the
analytic material-outward normal. It emits no PG-Frag fragments or ground-truth
labels, A12 observations, or RelicWeave retrievals. It is not a CAD builder,
renderer, test, or physical qualification. No execution is claimed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CylinderFixture:
    """Array bundle; rest-coordinate arrays are made read-only by the builder."""

    vertices_rest_xyz_mm: np.ndarray
    faces: np.ndarray
    outer_side_vertex_indices: np.ndarray
    outer_side_normals: np.ndarray
    outer_side_theta_rad: np.ndarray
    outer_side_z_mm: np.ndarray
    outer_radius_mm: float
    inner_radius_mm: float
    height_mm: float
    floor_mm: float


def _positive(name: str, value: float) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def build_closed_cylinder_fixture(
    *,
    outer_radius_mm: float = 20.0,
    wall_mm: float = 3.0,
    height_mm: float = 24.0,
    floor_mm: float = 2.0,
    around: int = 128,
    side_rows: int = 25,
) -> CylinderFixture:
    """Describe a closed cup boundary mesh with no duplicated angular seam.

    The solid has a full underside disk at z=0, a cavity floor at z=floor_mm,
    an open cavity up to the top, and a top annulus joining both side walls.
    The fixture is a mapping aid; its topology and geometry remain unverified
    until a later owner-run geometry and visual inspection.
    """
    radius = _positive("outer_radius_mm", outer_radius_mm)
    wall = _positive("wall_mm", wall_mm)
    height = _positive("height_mm", height_mm)
    floor = _positive("floor_mm", floor_mm)
    if wall >= radius:
        raise ValueError("wall_mm must be smaller than outer_radius_mm")
    if floor >= height:
        raise ValueError("floor_mm must be smaller than height_mm")
    if isinstance(around, bool) or int(around) != around or around < 8:
        raise ValueError("around must be an integer of at least 8")
    if isinstance(side_rows, bool) or int(side_rows) != side_rows or side_rows < 2:
        raise ValueError("side_rows must be an integer of at least 2")

    n_theta = int(around)
    n_rows = int(side_rows)
    inner_radius = radius - wall
    theta = 2.0 * pi * np.arange(n_theta, dtype=np.float64) / n_theta
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)
    outer_z = np.linspace(0.0, height, n_rows, dtype=np.float64)
    inner_z = np.linspace(floor, height, n_rows, dtype=np.float64)

    outer_xyz = np.stack(
        (
            radius * np.broadcast_to(cos_theta, (n_rows, n_theta)),
            radius * np.broadcast_to(sin_theta, (n_rows, n_theta)),
            np.broadcast_to(outer_z[:, None], (n_rows, n_theta)),
        ),
        axis=-1,
    )
    inner_xyz = np.stack(
        (
            inner_radius * np.broadcast_to(cos_theta, (n_rows, n_theta)),
            inner_radius * np.broadcast_to(sin_theta, (n_rows, n_theta)),
            np.broadcast_to(inner_z[:, None], (n_rows, n_theta)),
        ),
        axis=-1,
    )
    vertices = [point.copy() for point in outer_xyz.reshape((-1, 3))]
    outer_count = n_rows * n_theta
    vertices.extend(point.copy() for point in inner_xyz.reshape((-1, 3)))
    inner_start = outer_count
    bottom_center = len(vertices)
    vertices.append(np.asarray((0.0, 0.0, 0.0), dtype=np.float64))
    floor_center = len(vertices)
    vertices.append(np.asarray((0.0, 0.0, floor), dtype=np.float64))
    faces: list[tuple[int, int, int]] = []

    def outer_id(row: int, col: int) -> int:
        return row * n_theta + (col % n_theta)

    def inner_id(row: int, col: int) -> int:
        return inner_start + row * n_theta + (col % n_theta)

    # Outer side normals point from the material into the outside air.
    for row in range(n_rows - 1):
        for col in range(n_theta):
            nxt = (col + 1) % n_theta
            a, b = outer_id(row, col), outer_id(row, nxt)
            c, d = outer_id(row + 1, nxt), outer_id(row + 1, col)
            faces.extend(((a, b, c), (a, c, d)))

    # The cavity wall's material-outward normals point radially inward.
    for row in range(n_rows - 1):
        for col in range(n_theta):
            nxt = (col + 1) % n_theta
            a, b = inner_id(row, col), inner_id(row, nxt)
            c, d = inner_id(row + 1, nxt), inner_id(row + 1, col)
            faces.extend(((a, c, b), (a, d, c)))

    # Flat underside faces point down; the cavity floor and lip face up.
    for col in range(n_theta):
        nxt = (col + 1) % n_theta
        faces.append((bottom_center, outer_id(0, nxt), outer_id(0, col)))
        faces.append((floor_center, inner_id(0, col), inner_id(0, nxt)))
        top_outer, top_outer_next = outer_id(n_rows - 1, col), outer_id(n_rows - 1, nxt)
        top_inner, top_inner_next = inner_id(n_rows - 1, col), inner_id(n_rows - 1, nxt)
        faces.extend(((top_outer, top_outer_next, top_inner_next), (top_outer, top_inner_next, top_inner)))

    rest = np.asarray(vertices, dtype=np.float64)
    face_array = np.asarray(faces, dtype=np.int32)
    outer_indices = np.arange(outer_count, dtype=np.int64)
    normals = np.zeros_like(outer_xyz)
    normals[..., 0] = cos_theta[None, :]
    normals[..., 1] = sin_theta[None, :]
    theta_grid = np.broadcast_to(theta[None, :], (n_rows, n_theta)).copy()
    z_grid = np.broadcast_to(outer_z[:, None], (n_rows, n_theta)).copy()

    for array in (rest, face_array, outer_indices, normals, theta_grid, z_grid):
        array.setflags(write=False)
    return CylinderFixture(
        vertices_rest_xyz_mm=rest,
        faces=face_array,
        outer_side_vertex_indices=outer_indices,
        outer_side_normals=normals.reshape((-1, 3)),
        outer_side_theta_rad=theta_grid.reshape(-1),
        outer_side_z_mm=z_grid.reshape(-1),
        outer_radius_mm=radius,
        inner_radius_mm=inner_radius,
        height_mm=height,
        floor_mm=floor,
    )


def local_cylinder_metric_mm(
    radius_mm: float,
    theta_rad: np.ndarray,
    z_mm: np.ndarray,
    *,
    anchor_theta_rad: float = 0.0,
    anchor_z_mm: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return local coordinates and the form diag(1, R^2) in (z, theta) order.

    The returned chart uses x=R*wrapped_delta_theta and y=delta_z. The matrix
    is the first fundamental form in parameter order (z, theta), not in (x, y)
    chart order. It is exact for this constant-radius cylinder apart from the
    periodic seam, and is not a global chart for a curved, varying-radius vessel.
    """
    radius = _positive("radius_mm", radius_mm)
    theta = np.asarray(theta_rad, dtype=np.float64)
    z = np.asarray(z_mm, dtype=np.float64)
    if theta.shape != z.shape or not np.isfinite(theta).all() or not np.isfinite(z).all():
        raise ValueError("theta_rad and z_mm must be finite arrays of the same shape")
    delta = np.remainder(theta - anchor_theta_rad + pi, 2.0 * pi) - pi
    x_mm = radius * delta
    y_mm = z - float(anchor_z_mm)
    metric = np.asarray(((1.0, 0.0), (0.0, radius * radius)), dtype=np.float64)
    return x_mm, y_mm, metric


def linear_rgb_to_srgb(linear_rgb: np.ndarray) -> np.ndarray:
    """Encode already-composited linear RGB for display or an sRGB texture."""
    linear = np.clip(np.asarray(linear_rgb, dtype=np.float64), 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )


def sample_and_displace_outer_motifs(
    fixture: CylinderFixture,
    *,
    repeat_count: int = 8,
    center_z_mm: float = 13.0,
    circumferential_half_width_mm: float = 2.7,
    vertical_half_height_mm: float = 2.1,
    raised_height_mm: float = 0.45,
    base_linear_rgb: tuple[float, float, float] = (0.66, 0.49, 0.34),
    pigment_linear_rgb: tuple[float, float, float] = (0.095, 0.032, 0.018),
) -> dict[str, Any]:
    """Sample a ring of motifs on rest XYZ and return actual displaced mesh data.

    `vertices_relief_xyz_mm` is a separate geometry array: this operation goes
    beyond returning a 2D height image. Only outer side vertices move, along the
    analytic outward normal. Reported wall and curvature values are fixture
    proxies, not qualification for a curved vessel or an OCC solid.
    """
    if isinstance(repeat_count, bool) or int(repeat_count) != repeat_count or repeat_count < 1:
        raise ValueError("repeat_count must be a positive integer")
    half_width = _positive("circumferential_half_width_mm", circumferential_half_width_mm)
    half_height = _positive("vertical_half_height_mm", vertical_half_height_mm)
    height = _positive("raised_height_mm", raised_height_mm)
    base = np.asarray(base_linear_rgb, dtype=np.float64)
    pigment = np.asarray(pigment_linear_rgb, dtype=np.float64)
    if base.shape != (3,) or pigment.shape != (3,) or not np.isfinite(base).all() or not np.isfinite(pigment).all():
        raise ValueError("base and pigment colors must each contain three finite linear RGB values")
    if np.any(base < 0.0) or np.any(base > 1.0) or np.any(pigment < 0.0) or np.any(pigment > 1.0):
        raise ValueError("linear RGB values must lie in [0, 1]")

    theta = fixture.outer_side_theta_rad
    z = fixture.outer_side_z_mm
    # At a motif center, the exact cylinder metric converts angular phase to mm.
    cycle_delta = np.remainder(int(repeat_count) * theta / (2.0 * pi) + 0.5, 1.0) - 0.5
    arc_delta_mm = fixture.outer_radius_mm * (2.0 * pi / int(repeat_count)) * cycle_delta
    dz_mm = z - float(center_z_mm)
    normalized_radius = np.sqrt((arc_delta_mm / half_width) ** 2 + (dz_mm / half_height) ** 2)
    ramp = np.clip(1.0 - normalized_radius, 0.0, 1.0)
    coverage = ramp * ramp * (3.0 - 2.0 * ramp)

    # Composite in linear light, then encode only the display copy.
    rgb_linear = base[None, :] * (1.0 - coverage[:, None]) + pigment[None, :] * coverage[:, None]
    rgb_srgb = linear_rgb_to_srgb(rgb_linear)
    height_mm = height * coverage

    rest = fixture.vertices_rest_xyz_mm
    displaced = rest.copy()
    outer_ids = fixture.outer_side_vertex_indices
    displaced[outer_ids] = rest[outer_ids] + height_mm[:, None] * fixture.outer_side_normals
    displaced.setflags(write=False)

    # Exact for this coaxial cylinder under radial normal displacement only.
    outer_radius_after = fixture.outer_radius_mm + height_mm
    residual_radial_wall_mm = outer_radius_after - fixture.inner_radius_mm
    return {
        "vertices_rest_xyz_mm": rest,
        "vertices_relief_xyz_mm": displaced,
        "faces": fixture.faces,
        "outer_side_vertex_indices": outer_ids,
        "outer_color_linear_rgb": rgb_linear,
        "outer_color_srgb_for_display": rgb_srgb,
        "outer_relief_height_mm": height_mm,
        "outer_normals_material_outward": fixture.outer_side_normals,
        "parameter_metric_z_theta_mm2_at_motif_anchor": np.asarray(
            ((1.0, 0.0), (0.0, fixture.outer_radius_mm ** 2)), dtype=np.float64
        ),
        "minimum_radial_wall_proxy_mm": float(np.min(residual_radial_wall_mm)),
        "max_height_times_cylinder_curvature": float(np.max(np.abs(height_mm)) / fixture.outer_radius_mm),
        "geometry_claim": "DISPLACED_CLOSED_TRIANGLE_BOUNDARY_SOURCE_ONLY_NOT_EXECUTED_OR_VALIDATED",
        "proxy_scope": "exact radial separation and normal-curvature magnitude for this analytic coaxial cylinder only",
        "material_calibration": "UNKNOWN",
    }

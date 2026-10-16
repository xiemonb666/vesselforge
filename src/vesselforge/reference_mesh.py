"""Controlled, topology-preserving deformations for reference surface meshes.

The source coordinates, center, axis, and raw-unit calibration remain
caller-owned facts. The deformer never guesses units: callers give a
documented source-unit-to-millimetre scale.
All vertices are evaluated by the same smooth field, so attached handles and
other connected or disconnected details follow the body deformation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]
IntArray = NDArray[np.integer[Any]]


# Relative design ranges are intentionally narrow.  These are useful initial
# exploration bounds, not claims about the full range of historical forms.
EXPLORATION_RANGES: dict[str, tuple[float, float]] = {
    "height_scale": (0.95, 1.05),
    "radial_scale": (0.92, 1.08),
    "belly_fullness": (-0.06, 0.06),
    "upperbody_width": (-0.06, 0.06),
    "mouth_width": (-0.06, 0.06),
    "foot_width": (-0.06, 0.06),
}


@dataclass(frozen=True)
class DeformationControls:
    """Small, interpretable adjustments around one measured source mesh.

    ``height_scale`` and ``radial_scale`` explore a narrow range around a
    caller-supplied source-unit calibration. The four local controls are
    amplitudes in log-radius and therefore combine smoothly and
    multiplicatively.
    """

    height_scale: float = 1.0
    radial_scale: float = 1.0
    belly_fullness: float = 0.0
    upperbody_width: float = 0.0
    mouth_width: float = 0.0
    foot_width: float = 0.0

    def __post_init__(self) -> None:
        for name, limits in EXPLORATION_RANGES.items():
            value = _finite_scalar(name, getattr(self, name))
            if not limits[0] <= value <= limits[1]:
                raise ValueError(f"{name} must be within exploration range {limits}")
            object.__setattr__(self, name, value)

@dataclass(frozen=True)
class SourceProvenance:
    """Attribution and unit evidence attached to each derived mesh receipt."""

    source_name: str
    source_url: str
    license_id: str
    attribution: str
    raw_source_sha256: str
    scale_evidence: str
    source_component_count: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "source_name",
            "source_url",
            "license_id",
            "attribution",
            "scale_evidence",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        digest = self.raw_source_sha256.lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("raw_source_sha256 must be a 64-character SHA-256 hex digest")
        if self.source_component_count is not None and (
            isinstance(self.source_component_count, bool)
            or not isinstance(self.source_component_count, (int, np.integer))
            or self.source_component_count < 1
        ):
            raise ValueError("source_component_count must be a positive integer when supplied")


@dataclass(frozen=True)
class DeformedReferenceMesh:
    """Result arrays and machine-readable evidence for one deformation."""

    vertices_mm: FloatArray
    faces: NDArray[np.integer[Any]]
    vertex_attributes: NDArray[Any] | None
    receipt: dict[str, Any]


_PROFILE_TERMS: tuple[tuple[str, float, float], ...] = (
    ("foot_width", 0.08, 0.12),
    ("belly_fullness", 0.53, 0.21),
    ("upperbody_width", 0.78, 0.17),
    ("mouth_width", 0.96, 0.075),
)


def _finite_scalar(name: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _validate_mesh(
    vertices: NDArray[Any], faces: NDArray[Any]
) -> tuple[FloatArray, NDArray[np.integer[Any]]]:
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
        raise ValueError("vertices must be an N by 3 array with at least two points")
    if not np.isfinite(points).all():
        raise ValueError("vertices must contain only finite coordinates")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("faces must be an M by 3 triangle-index array")
    if triangles.dtype.kind not in "iu":
        raise ValueError("faces must contain integer vertex indices")
    if triangles.size and (triangles.min() < 0 or triangles.max() >= len(points)):
        raise ValueError("faces contain an out-of-range vertex index")
    return points, triangles.copy()


def _validate_frame(center: Any, axis: Any) -> tuple[FloatArray, FloatArray]:
    origin = np.asarray(center, dtype=np.float64)
    direction = np.asarray(axis, dtype=np.float64)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("center must be three finite source-coordinate values")
    if direction.shape != (3,) or not np.isfinite(direction).all():
        raise ValueError("axis must be three finite source-coordinate values")
    length = float(np.linalg.norm(direction))
    if length <= np.finfo(np.float64).eps:
        raise ValueError("axis must have non-zero length")
    return origin, direction / length


def _profile_log_scale(normalized_z: FloatArray, controls: DeformationControls) -> tuple[FloatArray, FloatArray]:
    """Return log-radius adjustment and its derivative by normalized height."""
    log_scale = np.zeros_like(normalized_z)
    derivative = np.zeros_like(normalized_z)
    for control_name, location, width in _PROFILE_TERMS:
        amplitude = float(getattr(controls, control_name))
        if amplitude == 0.0:
            continue
        delta = (normalized_z - location) / width
        gaussian = np.exp(-0.5 * delta * delta)
        log_scale += amplitude * gaussian
        derivative += amplitude * gaussian * (-(normalized_z - location) / (width * width))
    return log_scale, derivative


def _map_and_jacobian(
    points: FloatArray,
    center: FloatArray,
    axis: FloatArray,
    z_min: float,
    z_max: float,
    source_unit_scale_to_mm: float,
    controls: DeformationControls,
    *,
    with_jacobian: bool,
) -> tuple[FloatArray, FloatArray | None, FloatArray, FloatArray]:
    relative = points - center
    axial = relative @ axis
    radial = relative - axial[:, None] * axis
    span = z_max - z_min
    normalized_z = (axial - z_min) / span
    log_local, dlog_dnormalized_z = _profile_log_scale(normalized_z, controls)

    # The source-unit calibration is a common baseline. Height exploration is
    # axial only; width and local profile controls act only in the radial plane.
    radial_factor = source_unit_scale_to_mm * controls.radial_scale * np.exp(log_local)
    axial_scale = source_unit_scale_to_mm * controls.height_scale
    transformed = (
        radial * radial_factor[:, None]
        + (axial * axial_scale)[:, None] * axis
    )
    if not with_jacobian:
        return transformed, None, radial_factor, axial_scale

    d_factor_dz = radial_factor * dlog_dnormalized_z / span
    projector = np.eye(3, dtype=np.float64) - np.outer(axis, axis)
    jacobian = radial_factor[:, None, None] * projector[None, :, :]
    axial_derivative = (
        axial_scale * axis[None, :]
        + d_factor_dz[:, None] * radial
    )
    jacobian += axial_derivative[:, :, None] * axis[None, None, :]
    return transformed, jacobian, radial_factor, axial_scale


def jacobian_at_points(
    points: NDArray[Any],
    *,
    center: tuple[float, float, float] | FloatArray,
    axis: tuple[float, float, float] | FloatArray,
    source_axial_bounds: tuple[float, float],
    source_unit_scale_to_mm: float,
    controls: DeformationControls,
) -> FloatArray:
    """Evaluate the analytic 3x3 deformation Jacobian at source points.

    ``source_axial_bounds`` are projections of the full source mesh relative
    to ``center``. Supplying those bounds keeps pointwise evaluation consistent
    with the original deformation's normalized profile locations.
    """
    source_points = np.asarray(points, dtype=np.float64)
    if source_points.ndim == 1:
        source_points = source_points[None, :]
    if source_points.ndim != 2 or source_points.shape[1] != 3 or not np.isfinite(source_points).all():
        raise ValueError("points must be a finite N by 3 array")
    origin, direction = _validate_frame(center, axis)
    if len(source_axial_bounds) != 2:
        raise ValueError("source_axial_bounds must contain (min, max)")
    z_min, z_max = (_finite_scalar("source_axial_bound", x) for x in source_axial_bounds)
    if z_max <= z_min:
        raise ValueError("source_axial_bounds must have positive span")
    unit_scale = _finite_scalar("source_unit_scale_to_mm", source_unit_scale_to_mm)
    if unit_scale <= 0:
        raise ValueError("source_unit_scale_to_mm must be positive")
    _, jacobian, _, _ = _map_and_jacobian(
        source_points,
        origin,
        direction,
        z_min,
        z_max,
        unit_scale,
        controls,
        with_jacobian=True,
    )
    assert jacobian is not None
    return jacobian


def _array_sha256(vertices: FloatArray, faces: NDArray[np.integer[Any]]) -> str:
    vertex_bytes = np.ascontiguousarray(vertices, dtype="<f8").tobytes()
    face_bytes = np.ascontiguousarray(faces, dtype="<i8").tobytes()
    digest = hashlib.sha256()
    digest.update(b"vesselforge-reference-mesh-v1\0")
    digest.update(np.asarray(vertices.shape, dtype="<i8").tobytes())
    digest.update(vertex_bytes)
    digest.update(np.asarray(faces.shape, dtype="<i8").tobytes())
    digest.update(face_bytes)
    return digest.hexdigest()


def deform_reference_mesh(
    vertices: NDArray[Any],
    faces: NDArray[Any],
    *,
    center: tuple[float, float, float] | FloatArray,
    axis: tuple[float, float, float] | FloatArray,
    source_unit_scale_to_mm: float,
    controls: DeformationControls,
    provenance: SourceProvenance,
    vertex_attributes: NDArray[Any] | None = None,
    metric_sample_limit: int = 20_000,
) -> DeformedReferenceMesh:
    """Scale an actual reference mesh and apply smooth localized radial edits.

    The affine axial map sets the documented physical height. A positive
    smooth radial field modifies every vertex, including handles and other
    attachments. The original triangle array is copied byte-for-byte at its
    dtype and value level; no faces, parts, or vertices are repaired or pruned.
    """
    points, original_faces = _validate_mesh(vertices, faces)
    origin, direction = _validate_frame(center, axis)
    unit_scale = _finite_scalar("source_unit_scale_to_mm", source_unit_scale_to_mm)
    if unit_scale <= 0:
        raise ValueError("source_unit_scale_to_mm must be positive")
    if not isinstance(controls, DeformationControls):
        raise TypeError("controls must be a DeformationControls instance")
    if not isinstance(provenance, SourceProvenance):
        raise TypeError("provenance must be a SourceProvenance instance")
    if (
        isinstance(metric_sample_limit, bool)
        or not isinstance(metric_sample_limit, (int, np.integer))
        or int(metric_sample_limit) < 1
    ):
        raise ValueError("metric_sample_limit must be a positive integer")
    attributes = None
    if vertex_attributes is not None:
        attributes = np.asarray(vertex_attributes)
        if attributes.ndim < 1 or attributes.shape[0] != len(points):
            raise ValueError("vertex_attributes must have one row per source vertex")
        attributes = attributes.copy()

    source_relative = points - origin
    source_axial = source_relative @ direction
    z_min = float(source_axial.min())
    z_max = float(source_axial.max())
    span = z_max - z_min
    if not math.isfinite(span) or span <= np.finfo(np.float64).eps:
        raise ValueError("source mesh must have positive extent along the supplied axis")

    output, _, radial_factors, axial_scale = _map_and_jacobian(
        points,
        origin,
        direction,
        z_min,
        z_max,
        unit_scale,
        controls,
        with_jacobian=False,
    )
    if not np.isfinite(output).all() or not np.isfinite(radial_factors).all():
        raise ValueError("deformation produced non-finite coordinates")
    if float(radial_factors.min()) <= 0.0 or axial_scale <= 0.0:
        raise ValueError("deformation must keep radial and axial scales positive")

    sample_count = min(len(points), int(metric_sample_limit))
    if sample_count == len(points):
        sample_indices = np.arange(len(points), dtype=np.int64)
    else:
        sample_indices = np.linspace(0, len(points) - 1, sample_count, dtype=np.int64)
    sample_jacobian = jacobian_at_points(
        points[sample_indices],
        center=origin,
        axis=direction,
        source_axial_bounds=(z_min, z_max),
        source_unit_scale_to_mm=unit_scale,
        controls=controls,
    )
    singular_values = np.linalg.svd(sample_jacobian, compute_uv=False)
    determinants = np.linalg.det(sample_jacobian)
    if not np.isfinite(singular_values).all() or not np.isfinite(determinants).all():
        raise ValueError("analytic Jacobian evaluation produced non-finite values")

    derived_hash = _array_sha256(output, original_faces)
    attribute_hash = None
    if attributes is not None:
        attribute_digest = hashlib.sha256()
        attribute_digest.update(str(attributes.dtype).encode("utf-8"))
        attribute_digest.update(np.asarray(attributes.shape, dtype="<i8").tobytes())
        attribute_digest.update(np.ascontiguousarray(attributes).tobytes())
        attribute_hash = attribute_digest.hexdigest()
    target_height_mm = span * unit_scale * controls.height_scale
    receipt: dict[str, Any] = {
        "schema": "vesselforge.reference_mesh_deformation.v1",
        "source": asdict(provenance),
        "controls": asdict(controls),
        "transform": {
            "formula": "y = radial * (source_unit_scale_to_mm * radial_scale * exp(local_log_radius(z))) + axis * (source_unit_scale_to_mm * height_scale * axial)",
            "center_source_coordinates": origin.tolist(),
            "axis_unit_vector": direction.tolist(),
            "source_axial_bounds_relative_to_center": [z_min, z_max],
            "source_axial_span": span,
            "source_unit_scale_to_mm": unit_scale,
            "height_scale": controls.height_scale,
            "radial_scale": controls.radial_scale,
            "target_height_mm": target_height_mm,
            "profile_terms": [
                {"control": name, "center_fraction": location, "width_fraction": width}
                for name, location, width in _PROFILE_TERMS
            ],
            "analytic_jacobian_determinant": "radial_factor(z)^2 * source_unit_scale_to_mm * height_scale; positive over the continuous field for every accepted control set",
            "continuous_map_orientation_preserving": True,
        },
        "mesh": {
            "source_vertex_count": int(points.shape[0]),
            "source_face_count": int(original_faces.shape[0]),
            "derived_vertex_count": int(output.shape[0]),
            "derived_face_count": int(original_faces.shape[0]),
            "source_faces_preserved": True,
            "source_vertex_correspondence_preserved": True,
            "parts_discarded": False,
            "source_component_count_reported": provenance.source_component_count,
            "derived_geometry_sha256": derived_hash,
            "vertex_attributes_preserved": attributes is not None,
            "vertex_attributes_sha256": attribute_hash,
            "vertex_attribute_shape": list(attributes.shape) if attributes is not None else None,
        },
        "sampled_jacobian_metrics": {
            "sample_count": int(sample_count),
            "sample_indices_sha256": hashlib.sha256(
                np.ascontiguousarray(sample_indices, dtype="<i8").tobytes()
            ).hexdigest(),
            "determinant_min": float(determinants.min()),
            "determinant_max": float(determinants.max()),
            "singular_value_min_sampled": float(singular_values.min()),
            "singular_value_max_sampled": float(singular_values.max()),
            "radial_scale_min_sampled": float(radial_factors[sample_indices].min()),
            "radial_scale_max_sampled": float(radial_factors[sample_indices].max()),
            "scope_note": "Pointwise analytic Jacobians sampled at deterministic original vertices; these values are not a global wall-thickness or between-vertex certificate.",
        },
        "limitations": [
            "Uniform or localized stretching also stretches wall thickness; constant physical thickness is not claimed.",
            "The source is a surface mesh; this mapping does not repair, fill, smooth, decimate, remesh, or reorient it.",
            "Topological preservation does not establish manifoldness, printability, or physical validity of the source scan.",
        ],
    }
    # Enforce JSON-safe finite values before returning the receipt to callers.
    json.dumps(receipt, allow_nan=False)
    return DeformedReferenceMesh(output, original_faces, attributes, receipt)


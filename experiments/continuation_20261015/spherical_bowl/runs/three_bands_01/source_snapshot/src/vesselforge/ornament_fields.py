"""Continuous ornament layers in immutable asset-local rest coordinates.

This module defines procedural color and signed scalar relief fields. It does
not edit CAD, mesh, STEP, or fracture geometry. Callers should evaluate fields
on the source mother's ``vertices_material_xyz_mm`` (right-handed Z-up mm) and
carry those coordinates through fragment lineage so the pattern does not swim
when a fragment is moved or rotated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

import numpy as np


OrnamentEffect: TypeAlias = Literal["paint", "raised", "engraved"]
DEFAULT_BASE_MATERIAL_COLOR_LINEAR_RGB = (0.66, 0.49, 0.34)
DEFAULT_PIGMENT_COLOR_LINEAR_RGB = (0.095, 0.032, 0.018)
REST_COORDINATE_FRAME = "asset_local_rest_xyz_mm"


def _finite_scalar(name: str, value: float) -> float:
    number = float(value)
    if not np.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _linear_rgb(name: str, value: tuple[float, float, float]) -> tuple[float, float, float]:
    color = np.asarray(value, dtype=np.float64)
    if color.shape != (3,) or not np.isfinite(color).all() or np.any(color < 0.0) or np.any(color > 1.0):
        raise ValueError(f"{name} must be three finite linear RGB values in [0, 1]")
    return tuple(float(channel) for channel in color)


def _smoothstep01(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(value, 0.0, 1.0)
    return clipped * clipped * (3.0 - 2.0 * clipped)


def _coverage_from_signed_distance(signed_distance: np.ndarray, softness: float) -> np.ndarray:
    """Map positive-inside signed distance to a continuous [0, 1] coverage."""
    if softness == 0.0:
        return (signed_distance >= 0.0).astype(np.float64)
    return _smoothstep01(0.5 + signed_distance / softness)


def _validated_coordinates(source_mother_rest_xyz_mm: np.ndarray) -> np.ndarray:
    xyz = np.asarray(source_mother_rest_xyz_mm, dtype=np.float64)
    if xyz.ndim < 1 or xyz.shape[-1] != 3:
        raise ValueError("rest coordinates must have shape (..., 3) in asset-local XYZ mm")
    if not np.isfinite(xyz).all():
        raise ValueError("rest coordinates must contain only finite values")
    return xyz


@dataclass(frozen=True, kw_only=True)
class OrnamentField:
    """Shared independent controls for one procedural ornament layer."""

    field_id: str = "ornament"
    effect: OrnamentEffect = "paint"
    pigment_color_linear_rgb: tuple[float, float, float] = DEFAULT_PIGMENT_COLOR_LINEAR_RGB
    base_material_color_linear_rgb: tuple[float, float, float] = DEFAULT_BASE_MATERIAL_COLOR_LINEAR_RGB
    strength: float = 1.0
    pigment_opacity: float = 1.0
    relief_amplitude_mm: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.field_id, str) or not self.field_id.strip():
            raise ValueError("field_id must be a non-empty string")
        if self.effect not in {"paint", "raised", "engraved"}:
            raise ValueError("effect must be 'paint', 'raised', or 'engraved'")
        object.__setattr__(self, "pigment_color_linear_rgb", _linear_rgb(
            "pigment_color_linear_rgb", self.pigment_color_linear_rgb
        ))
        object.__setattr__(self, "base_material_color_linear_rgb", _linear_rgb(
            "base_material_color_linear_rgb", self.base_material_color_linear_rgb
        ))
        strength = _finite_scalar("strength", self.strength)
        opacity = _finite_scalar("pigment_opacity", self.pigment_opacity)
        relief = _finite_scalar("relief_amplitude_mm", self.relief_amplitude_mm)
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must lie in [0, 1]")
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("pigment_opacity must lie in [0, 1]")
        if self.effect == "paint" and relief != 0.0:
            raise ValueError("paint fields must have zero relief_amplitude_mm")
        if self.effect == "raised" and relief <= 0.0:
            raise ValueError("raised fields require positive relief_amplitude_mm")
        if self.effect == "engraved" and relief >= 0.0:
            raise ValueError("engraved fields require negative relief_amplitude_mm")
        object.__setattr__(self, "strength", strength)
        object.__setattr__(self, "pigment_opacity", opacity)
        object.__setattr__(self, "relief_amplitude_mm", relief)

    def _intrinsic_coverage(self, xyz: np.ndarray) -> np.ndarray:
        raise NotImplementedError


@dataclass(frozen=True, kw_only=True)
class GeometricRingBand(OrnamentField):
    """A level circumferential band centered at ``center_z_mm``."""

    center_z_mm: float = 20.0
    width_mm: float = 2.0
    edge_softness_mm: float = 0.35

    def __post_init__(self) -> None:
        super().__post_init__()
        center = _finite_scalar("center_z_mm", self.center_z_mm)
        width = _finite_scalar("width_mm", self.width_mm)
        softness = _finite_scalar("edge_softness_mm", self.edge_softness_mm)
        if width <= 0.0 or softness < 0.0:
            raise ValueError("width_mm must be positive and edge_softness_mm non-negative")
        object.__setattr__(self, "center_z_mm", center)
        object.__setattr__(self, "width_mm", width)
        object.__setattr__(self, "edge_softness_mm", softness)

    def _intrinsic_coverage(self, xyz: np.ndarray) -> np.ndarray:
        signed_inside_mm = self.width_mm / 2.0 - np.abs(xyz[..., 2] - self.center_z_mm)
        return _coverage_from_signed_distance(signed_inside_mm, self.edge_softness_mm)


@dataclass(frozen=True, kw_only=True)
class WavingBand(OrnamentField):
    """A smooth band whose centerline waves around the cylindrical axis.

    ``repeat_count`` is an integer angular frequency, so the curve closes at
    the theta seam by construction. The path amplitude shifts the band's
    centerline in Z; ``relief_amplitude_mm`` remains a separate control.
    """

    center_z_mm: float = 30.0
    width_mm: float = 1.8
    path_amplitude_mm: float = 3.0
    repeat_count: int = 5
    phase_rad: float = 0.0
    edge_softness_mm: float = 0.35

    def __post_init__(self) -> None:
        super().__post_init__()
        center = _finite_scalar("center_z_mm", self.center_z_mm)
        width = _finite_scalar("width_mm", self.width_mm)
        path = _finite_scalar("path_amplitude_mm", self.path_amplitude_mm)
        phase = _finite_scalar("phase_rad", self.phase_rad)
        softness = _finite_scalar("edge_softness_mm", self.edge_softness_mm)
        if width <= 0.0 or path < 0.0 or softness < 0.0:
            raise ValueError("width_mm must be positive; path amplitude and edge softness must be non-negative")
        if isinstance(self.repeat_count, bool) or not isinstance(self.repeat_count, int) or self.repeat_count < 1:
            raise ValueError("repeat_count must be a positive integer")
        object.__setattr__(self, "center_z_mm", center)
        object.__setattr__(self, "width_mm", width)
        object.__setattr__(self, "path_amplitude_mm", path)
        object.__setattr__(self, "phase_rad", phase)
        object.__setattr__(self, "edge_softness_mm", softness)

    def _intrinsic_coverage(self, xyz: np.ndarray) -> np.ndarray:
        theta = np.arctan2(xyz[..., 1], xyz[..., 0])
        centerline_z = self.center_z_mm + self.path_amplitude_mm * np.sin(
            self.repeat_count * theta + self.phase_rad
        )
        signed_inside_mm = self.width_mm / 2.0 - np.abs(xyz[..., 2] - centerline_z)
        return _coverage_from_signed_distance(signed_inside_mm, self.edge_softness_mm)


@dataclass(frozen=True, kw_only=True)
class RepeatedMotif(OrnamentField):
    """A regular grid of elliptical motifs in cylindrical (theta, Z) space."""

    center_z_mm: float = 18.0
    z_pitch_mm: float = 8.0
    angular_repeats: int = 12
    angular_phase_rad: float = 0.0
    angular_half_width_fraction: float = 0.28
    z_half_height_fraction: float = 0.32
    edge_softness_fraction: float = 0.08

    def __post_init__(self) -> None:
        super().__post_init__()
        center = _finite_scalar("center_z_mm", self.center_z_mm)
        pitch = _finite_scalar("z_pitch_mm", self.z_pitch_mm)
        phase = _finite_scalar("angular_phase_rad", self.angular_phase_rad)
        angular_width = _finite_scalar("angular_half_width_fraction", self.angular_half_width_fraction)
        z_height = _finite_scalar("z_half_height_fraction", self.z_half_height_fraction)
        softness = _finite_scalar("edge_softness_fraction", self.edge_softness_fraction)
        if pitch <= 0.0:
            raise ValueError("z_pitch_mm must be positive")
        if isinstance(self.angular_repeats, bool) or not isinstance(self.angular_repeats, int) or self.angular_repeats < 1:
            raise ValueError("angular_repeats must be a positive integer")
        if not 0.0 < angular_width <= 0.5 or not 0.0 < z_height <= 0.5:
            raise ValueError("motif half-width fractions must be in (0, 0.5]")
        if not 0.0 <= softness <= 0.5:
            raise ValueError("edge_softness_fraction must lie in [0, 0.5]")
        object.__setattr__(self, "center_z_mm", center)
        object.__setattr__(self, "z_pitch_mm", pitch)
        object.__setattr__(self, "angular_phase_rad", phase)
        object.__setattr__(self, "angular_half_width_fraction", angular_width)
        object.__setattr__(self, "z_half_height_fraction", z_height)
        object.__setattr__(self, "edge_softness_fraction", softness)

    def _intrinsic_coverage(self, xyz: np.ndarray) -> np.ndarray:
        theta = np.arctan2(xyz[..., 1], xyz[..., 0])
        angular_cycles = self.angular_repeats * (theta - self.angular_phase_rad) / (2.0 * np.pi)
        angular_delta = np.remainder(angular_cycles + 0.5, 1.0) - 0.5
        z_cycles = (xyz[..., 2] - self.center_z_mm) / self.z_pitch_mm
        z_delta = np.remainder(z_cycles + 0.5, 1.0) - 0.5
        normalized_radius = np.sqrt(
            (angular_delta / self.angular_half_width_fraction) ** 2
            + (z_delta / self.z_half_height_fraction) ** 2
        )
        signed_inside = 1.0 - normalized_radius
        return _coverage_from_signed_distance(signed_inside, self.edge_softness_fraction)


OrnamentFieldSpec: TypeAlias = GeometricRingBand | WavingBand | RepeatedMotif


@dataclass(frozen=True)
class FieldEvaluation:
    """Separate region, pigment, substrate, and signed relief channels."""

    field_id: str
    effect: OrnamentEffect
    coordinate_frame: str
    region_mask: np.ndarray
    region_weight: np.ndarray
    pigment_color_linear_rgb: np.ndarray
    pigment_opacity: np.ndarray
    base_material_color_linear_rgb: np.ndarray
    relief_height_mm: np.ndarray
    geometry_claim: str = "SCALAR_HEIGHT_FIELD_ONLY_NO_MESH_GENERATED"


@dataclass(frozen=True)
class FieldStackEvaluation:
    """Layered evaluation preserving each effect and its individual height."""

    layers: tuple[FieldEvaluation, ...]
    region_mask: np.ndarray
    region_weight: np.ndarray
    pigment_color_linear_rgb: np.ndarray
    pigment_opacity: np.ndarray
    base_material_color_linear_rgb: np.ndarray
    relief_height_mm: np.ndarray
    coordinate_frame: str = REST_COORDINATE_FRAME
    geometry_claim: str = "SCALAR_HEIGHT_FIELD_ONLY_NO_MESH_GENERATED"


def evaluate_ornament_field(
    source_mother_rest_xyz_mm: np.ndarray,
    field_spec: OrnamentFieldSpec,
) -> FieldEvaluation:
    """Evaluate one field on source-mother rest coordinates in mm.

    The returned height is a signed scalar displacement suggestion: paint is
    exactly zero, raised is positive, and engraved is negative. No surface is
    displaced or remeshed here.
    """
    xyz = _validated_coordinates(source_mother_rest_xyz_mm)
    intrinsic = field_spec._intrinsic_coverage(xyz)
    effective_weight = intrinsic * field_spec.strength
    shape = effective_weight.shape
    pigment_rgb = np.broadcast_to(
        np.asarray(field_spec.pigment_color_linear_rgb, dtype=np.float64), (*shape, 3)
    ).copy()
    base_rgb = np.broadcast_to(
        np.asarray(field_spec.base_material_color_linear_rgb, dtype=np.float64), (*shape, 3)
    ).copy()
    relief = effective_weight * field_spec.relief_amplitude_mm
    return FieldEvaluation(
        field_id=field_spec.field_id,
        effect=field_spec.effect,
        coordinate_frame=REST_COORDINATE_FRAME,
        region_mask=effective_weight > 0.0,
        region_weight=effective_weight,
        pigment_color_linear_rgb=pigment_rgb,
        pigment_opacity=effective_weight * field_spec.pigment_opacity,
        base_material_color_linear_rgb=base_rgb,
        relief_height_mm=relief,
    )


def evaluate_ornament_stack(
    source_mother_rest_xyz_mm: np.ndarray,
    fields: tuple[OrnamentFieldSpec, ...] | list[OrnamentFieldSpec],
    *,
    base_material_color_linear_rgb: tuple[float, float, float] | None = None,
) -> FieldStackEvaluation:
    """Evaluate ordered layers; later pigment layers composite over earlier ones.

    Relief heights remain signed and additive, with the per-layer values kept
    in ``layers`` so raised and engraved contributions never lose their mode.
    """
    xyz = _validated_coordinates(source_mother_rest_xyz_mm)
    layer_specs = tuple(fields)
    if base_material_color_linear_rgb is None:
        base = layer_specs[0].base_material_color_linear_rgb if layer_specs else DEFAULT_BASE_MATERIAL_COLOR_LINEAR_RGB
    else:
        base = _linear_rgb("base_material_color_linear_rgb", base_material_color_linear_rgb)
    base = _linear_rgb("base_material_color_linear_rgb", base)
    layers = tuple(evaluate_ornament_field(xyz, item) for item in layer_specs)
    shape = xyz.shape[:-1]
    base_rgb = np.broadcast_to(np.asarray(base, dtype=np.float64), (*shape, 3)).copy()

    composite_rgb = np.zeros((*shape, 3), dtype=np.float64)
    composite_opacity = np.zeros(shape, dtype=np.float64)
    region_weight = np.zeros(shape, dtype=np.float64)
    region_mask = np.zeros(shape, dtype=bool)
    relief = np.zeros(shape, dtype=np.float64)
    for layer in layers:
        alpha = layer.pigment_opacity
        composite_rgb = layer.pigment_color_linear_rgb * alpha[..., None] + composite_rgb * (1.0 - alpha[..., None])
        composite_opacity = alpha + composite_opacity * (1.0 - alpha)
        region_weight = layer.region_weight + region_weight * (1.0 - layer.region_weight)
        region_mask |= layer.region_mask
        relief += layer.relief_height_mm
    composite_rgb = np.divide(
        composite_rgb,
        composite_opacity[..., None],
        out=np.zeros_like(composite_rgb),
        where=composite_opacity[..., None] > 0.0,
    )
    return FieldStackEvaluation(
        layers=layers,
        region_mask=region_mask,
        region_weight=region_weight,
        pigment_color_linear_rgb=composite_rgb,
        pigment_opacity=composite_opacity,
        base_material_color_linear_rgb=base_rgb,
        relief_height_mm=relief,
    )


@dataclass(frozen=True)
class WallThicknessEvidence:
    """Caller-supplied wall map; ``trusted`` is an assertion, not authentication."""

    thickness_mm: np.ndarray | None = None
    source: str | None = None
    trusted: bool = False


@dataclass(frozen=True)
class GeometryQualification:
    status: str
    geometry_qualified: bool
    wall_thickness_status: str
    reason: str
    minimum_residual_wall_mm: float | None = None
    wall_evidence_independently_authenticated: bool = False


def _field_evaluation_error(
    field_spec: OrnamentFieldSpec,
    evaluation: FieldEvaluation,
) -> str | None:
    if not isinstance(field_spec, (GeometricRingBand, WavingBand, RepeatedMotif)):
        return "field specification has an unsupported type"
    if not isinstance(evaluation, FieldEvaluation):
        return "evaluation is not a FieldEvaluation"
    if evaluation.field_id != field_spec.field_id:
        return "evaluation field_id does not match the field specification"
    if evaluation.effect != field_spec.effect:
        return "evaluation effect does not match the field specification"
    if evaluation.coordinate_frame != REST_COORDINATE_FRAME:
        return "evaluation coordinate frame is not the source-mother rest frame"
    try:
        height = np.asarray(evaluation.relief_height_mm, dtype=np.float64)
        region_mask = np.asarray(evaluation.region_mask)
    except (TypeError, ValueError, OverflowError):
        return "evaluation height or region mask cannot be interpreted"
    if region_mask.dtype.kind != "b" or region_mask.shape != height.shape:
        return "evaluation region mask must be boolean and match the height shape"
    if not np.isfinite(height).all():
        return "evaluation height contains a non-finite value"
    if np.any(height[~region_mask] != 0.0):
        return "evaluation has nonzero height outside its ornament region"
    amplitude = float(field_spec.relief_amplitude_mm)
    amplitude_tolerance = max(1e-12, abs(amplitude) * 1e-12)
    if field_spec.effect == "paint":
        if np.any(height != 0.0):
            return "paint evaluation must have exactly zero height"
    elif field_spec.effect == "raised":
        if np.any(height < 0.0) or np.any(height > amplitude + amplitude_tolerance):
            return "raised evaluation height has an invalid sign or exceeds its declared amplitude"
    elif field_spec.effect == "engraved":
        if np.any(height > 0.0) or np.any(height < amplitude - amplitude_tolerance):
            return "engraved evaluation height has an invalid sign or exceeds its declared amplitude"
    return None


def _rejected_evaluation(reason: str) -> GeometryQualification:
    return GeometryQualification(
        status="REJECTED_INVALID_FIELD_EVALUATION",
        geometry_qualified=False,
        wall_thickness_status="UNKNOWN",
        reason=reason,
    )


def _rejected_wall_map(reason: str) -> GeometryQualification:
    return GeometryQualification(
        status="REJECTED_INVALID_WALL_THICKNESS_MAP",
        geometry_qualified=False,
        wall_thickness_status="UNKNOWN",
        reason=reason,
    )


def qualify_geometry_field(
    field_spec: OrnamentFieldSpec,
    evaluation: FieldEvaluation,
    *,
    wall_thickness: WallThicknessEvidence | None = None,
    minimum_residual_wall_mm: float = 0.0,
) -> GeometryQualification:
    """Fail closed where engraving lacks trusted wall evidence.

    Even a passing wall prerequisite never claims generated or validated CAD:
    this package supplies only a height field for a later geometry stage.
    """
    minimum = _finite_scalar("minimum_residual_wall_mm", minimum_residual_wall_mm)
    if minimum < 0.0:
        raise ValueError("minimum_residual_wall_mm must be non-negative")
    invalid_evaluation = _field_evaluation_error(field_spec, evaluation)
    if invalid_evaluation is not None:
        return _rejected_evaluation(invalid_evaluation)
    if field_spec.effect == "paint":
        return GeometryQualification(
            status="NO_GEOMETRIC_EFFECT",
            geometry_qualified=False,
            wall_thickness_status="NOT_REQUIRED",
            reason="paint has zero relief by contract",
        )
    if field_spec.effect == "raised":
        return GeometryQualification(
            status="HEIGHT_FIELD_ONLY_NOT_MESHED",
            geometry_qualified=False,
            wall_thickness_status="NOT_REQUIRED_FOR_RAISED_FIELD",
            reason="positive scalar height is available, but no CAD or mesh geometry was generated",
        )
    if wall_thickness is not None and not isinstance(wall_thickness, WallThicknessEvidence):
        return _rejected_wall_map("wall-thickness evidence has an unsupported type")
    trusted_flag = (
        isinstance(wall_thickness.trusted, (bool, np.bool_)) and bool(wall_thickness.trusted)
        if wall_thickness is not None
        else False
    )
    if (
        wall_thickness is None
        or not trusted_flag
        or not isinstance(wall_thickness.source, str)
        or not wall_thickness.source.strip()
        or wall_thickness.thickness_mm is None
    ):
        return GeometryQualification(
            status="REJECTED_UNKNOWN_WALL_THICKNESS",
            geometry_qualified=False,
            wall_thickness_status="UNKNOWN",
            reason="engraving cannot be qualified without a trusted, sourced wall-thickness map",
        )

    try:
        thickness = np.asarray(wall_thickness.thickness_mm, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return _rejected_wall_map("caller-supplied wall-thickness map cannot be interpreted")
    height = np.asarray(evaluation.relief_height_mm, dtype=np.float64)
    active = np.asarray(evaluation.region_mask, dtype=bool)
    if thickness.shape != height.shape:
        return _rejected_wall_map("caller-supplied wall-thickness map shape does not match evaluated coordinates")
    if not np.isfinite(thickness).all() or np.any(thickness <= 0.0):
        return _rejected_wall_map("caller-supplied wall-thickness map must be finite and positive")
    if not np.any(active):
        return GeometryQualification(
            status="NO_ACTIVE_ENGRAVED_REGION",
            geometry_qualified=False,
            wall_thickness_status="CALLER_ASSERTED_TRUSTED_MAP_NOT_INDEPENDENTLY_AUTHENTICATED",
            reason="the engraved scalar field is inactive at the supplied coordinates",
        )
    residual = thickness[active] + height[active]
    residual_min = float(np.min(residual))
    if residual_min < minimum:
        return GeometryQualification(
            status="REJECTED_INSUFFICIENT_RESIDUAL_WALL",
            geometry_qualified=False,
            wall_thickness_status="CALLER_ASSERTED_TRUSTED_MAP_NOT_INDEPENDENTLY_AUTHENTICATED",
            reason="the caller-supplied map leaves less residual wall than requested; its source was not independently authenticated",
            minimum_residual_wall_mm=residual_min,
        )
    return GeometryQualification(
        status="WALL_PREREQUISITE_PASS_HEIGHT_FIELD_ONLY",
        geometry_qualified=False,
        wall_thickness_status="CALLER_ASSERTED_TRUSTED_MAP_NOT_INDEPENDENTLY_AUTHENTICATED",
        reason="the caller-supplied wall prerequisite passes, but it was not independently authenticated and the scalar height field has not been converted to geometry",
        minimum_residual_wall_mm=residual_min,
    )

from __future__ import annotations

import numpy as np
import pytest

from vesselforge.ornament_fields import (
    GeometricRingBand,
    RepeatedMotif,
    WallThicknessEvidence,
    WavingBand,
    evaluate_ornament_field,
    evaluate_ornament_stack,
    qualify_geometry_field,
)


def _xyz(theta: float, z_mm: float, radius_mm: float = 18.0) -> np.ndarray:
    return np.asarray([radius_mm * np.cos(theta), radius_mm * np.sin(theta), z_mm], dtype=np.float64)


def test_angular_periodicity_closes_the_theta_seam_for_each_field_family() -> None:
    theta = 0.37
    coordinate_pairs = np.stack([_xyz(theta, 24.0), _xyz(theta + 2.0 * np.pi, 24.0)])
    fields = (
        GeometricRingBand(field_id="ring", center_z_mm=24.0, width_mm=2.5),
        WavingBand(field_id="wave", center_z_mm=24.0, width_mm=3.0, path_amplitude_mm=1.5,
                   repeat_count=7, phase_rad=0.23),
        RepeatedMotif(field_id="motif", center_z_mm=24.0, z_pitch_mm=5.0,
                      angular_repeats=13, angular_phase_rad=0.1),
    )
    for field_spec in fields:
        evaluated = evaluate_ornament_field(coordinate_pairs, field_spec)
        np.testing.assert_allclose(evaluated.region_weight[0], evaluated.region_weight[1], atol=1e-12)
        np.testing.assert_allclose(evaluated.relief_height_mm[0], evaluated.relief_height_mm[1], atol=1e-12)
        np.testing.assert_allclose(evaluated.pigment_opacity[0], evaluated.pigment_opacity[1], atol=1e-12)


def test_fields_are_finite_and_keep_colors_in_linear_rgb_domain() -> None:
    xyz = np.stack([_xyz(theta, z) for theta in np.linspace(-np.pi, np.pi, 21)
                    for z in np.linspace(10.0, 34.0, 9)])
    layers = (
        GeometricRingBand(field_id="ring", center_z_mm=22.0, width_mm=2.4,
                          pigment_color_linear_rgb=(0.72, 0.12, 0.06)),
        WavingBand(field_id="wave", effect="raised", relief_amplitude_mm=0.8,
                   center_z_mm=22.0, path_amplitude_mm=2.0, repeat_count=6,
                   pigment_color_linear_rgb=(0.1, 0.3, 0.8)),
        RepeatedMotif(field_id="motif", center_z_mm=22.0, z_pitch_mm=5.0,
                      angular_repeats=10, angular_phase_rad=0.15),
    )
    result = evaluate_ornament_stack(xyz, layers)
    for color in (result.pigment_color_linear_rgb, result.base_material_color_linear_rgb):
        assert np.isfinite(color).all()
        assert np.all((color >= 0.0) & (color <= 1.0))
    for value in (result.region_weight, result.pigment_opacity, result.relief_height_mm):
        assert np.isfinite(value).all()
    with pytest.raises(ValueError, match="linear RGB"):
        GeometricRingBand(pigment_color_linear_rgb=(1.1, 0.0, 0.0))


def test_zero_strength_is_identity_and_effect_modes_have_signed_height() -> None:
    xyz = _xyz(0.0, 20.0)
    base = (0.4, 0.3, 0.2)
    zero_strength = GeometricRingBand(field_id="disabled", effect="raised", relief_amplitude_mm=0.9,
                                      center_z_mm=20.0, strength=0.0,
                                      base_material_color_linear_rgb=base)
    identity = evaluate_ornament_stack(xyz, [zero_strength])
    assert not bool(identity.region_mask)
    assert float(identity.pigment_opacity) == 0.0
    np.testing.assert_array_equal(identity.pigment_color_linear_rgb, np.zeros(3))
    np.testing.assert_array_equal(identity.base_material_color_linear_rgb, np.asarray(base))
    assert float(identity.relief_height_mm) == 0.0

    paint = GeometricRingBand(center_z_mm=20.0, width_mm=4.0)
    raised = GeometricRingBand(effect="raised", relief_amplitude_mm=0.7,
                               center_z_mm=20.0, width_mm=4.0)
    engraved = GeometricRingBand(effect="engraved", relief_amplitude_mm=-0.55,
                                 center_z_mm=20.0, width_mm=4.0)
    assert float(evaluate_ornament_field(xyz, paint).relief_height_mm) == 0.0
    assert float(evaluate_ornament_field(xyz, raised).relief_height_mm) > 0.0
    engraved_result = evaluate_ornament_field(xyz, engraved)
    assert float(engraved_result.relief_height_mm) < 0.0
    gate = qualify_geometry_field(engraved, engraved_result)
    assert gate.status == "REJECTED_UNKNOWN_WALL_THICKNESS"
    assert gate.wall_thickness_status == "UNKNOWN"
    assert gate.geometry_qualified is False

    trusted = WallThicknessEvidence(thickness_mm=np.asarray(2.0), source="fixture wall map", trusted=True)
    safe_gate = qualify_geometry_field(engraved, engraved_result, wall_thickness=trusted,
                                       minimum_residual_wall_mm=1.0)
    assert safe_gate.status == "WALL_PREREQUISITE_PASS_HEIGHT_FIELD_ONLY"
    assert safe_gate.geometry_qualified is False


def test_effect_mode_and_amplitude_must_agree() -> None:
    with pytest.raises(ValueError, match="paint fields"):
        GeometricRingBand(effect="paint", relief_amplitude_mm=0.1)
    with pytest.raises(ValueError, match="positive relief"):
        GeometricRingBand(effect="raised", relief_amplitude_mm=-0.1)
    with pytest.raises(ValueError, match="negative relief"):
        GeometricRingBand(effect="engraved", relief_amplitude_mm=0.1)

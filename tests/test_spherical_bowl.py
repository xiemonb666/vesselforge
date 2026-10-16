from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import vesselforge.spherical_bowl as bowl
from vesselforge.schema import validate_asset


def test_default_bowl_spec_and_analytic_volume() -> None:
    spec = bowl.BowlSpec()
    spec.validate()

    assert spec.to_dict()["shape"] == "concentric_lower_hemisphere"
    assert spec.to_dict()["outer_radius_mm"] == 12.0
    assert spec.to_dict()["inner_radius_mm"] == 8.0
    assert spec.to_dict()["center_xyz_mm"] == [0.0, 0.0, 12.0]
    assert spec.bottom_z_mm == 0.0
    assert spec.ideal_wall_thickness_mm == 4.0
    assert bowl.analytic_spherical_bowl_volume_mm3(spec) == pytest.approx(
        2.0 * np.pi / 3.0 * (12.0**3 - 8.0**3), rel=1e-15
    )


@pytest.mark.parametrize(
    "spec",
    [
        bowl.BowlSpec(outer_radius_mm=0.0),
        bowl.BowlSpec(inner_radius_mm=12.0),
        bowl.BowlSpec(center_xyz_mm=(0.0, float("nan"), 12.0)),
        bowl.BowlSpec(tessellation_linear_mm=0.01),
    ],
)
def test_invalid_bowl_spec_is_rejected(spec: bowl.BowlSpec) -> None:
    with pytest.raises(ValueError):
        spec.validate()


def test_native_solid_is_one_closed_shell_with_exact_analytic_volume() -> None:
    spec = bowl.BowlSpec()
    shape = bowl.build_spherical_bowl_solid(spec)

    expected = bowl.analytic_spherical_bowl_volume_mm3(spec)
    assert shape.isValid()
    assert len(shape.Solids()) == 1
    assert len(shape.Shells()) == 1
    assert shape.Shells()[0].Closed()
    assert shape.Volume() == pytest.approx(expected, rel=1e-8)


def test_material_and_segment_predicates_include_whole_segment_constraints() -> None:
    spec = bowl.BowlSpec()
    assert bowl.contains_material((12.0, 0.0, 12.0), spec)
    assert bowl.contains_material((0.0, 0.0, 0.0), spec)
    assert not bowl.contains_material((0.0, 0.0, 12.0), spec)
    assert not bowl.contains_material((0.0, 0.0, 13.0), spec)

    assert bowl.segment_in_material((9.0, 0.0, 8.0), (10.0, 0.0, 6.0), spec)
    # Both endpoints are in material, but the chord passes through the cavity.
    assert not bowl.segment_in_material((-10.0, 0.0, 11.0), (10.0, 0.0, 11.0), spec)
    # Clipping the segment to z <= center_z must not make an invalid endpoint pass.
    assert not bowl.segment_in_material((9.0, 0.0, 11.0), (9.0, 0.0, 13.0), spec)


def test_solver_point_lattice_matches_declared_centroid_filter() -> None:
    spec = bowl.BowlSpec(center_xyz_mm=(10.0, -3.0, 50.0))
    cloud = bowl.generate_solver_points(spec, spacing_mm=2.0, horizon_mm=4.0)

    assert cloud.points_mm.ndim == 2 and cloud.points_mm.shape[1] == 3
    assert len(cloud.points_mm) > 0
    assert all(bowl.contains_material(point, spec) for point in cloud.points_mm)
    assert cloud.metadata["point_count"] == len(cloud.points_mm)
    assert cloud.metadata["estimated_volume_mm3"] == pytest.approx(len(cloud.points_mm) * 8.0)
    assert cloud.metadata["spec"]["center_xyz_mm"] == [10.0, -3.0, 50.0]


def test_solver_lattice_resource_guard_runs_before_meshgrid(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_meshgrid(*args: object, **kwargs: object) -> None:
        pytest.fail("meshgrid allocated before candidate-count guard")

    monkeypatch.setattr(bowl.np, "meshgrid", forbidden_meshgrid)
    with pytest.raises(ValueError, match="limit is 2000000"):
        bowl.generate_solver_points(spacing_mm=0.01, horizon_mm=0.03)


def test_solver_lattice_rejects_empty_centroid_grid() -> None:
    with pytest.raises(ValueError, match="too large"):
        bowl.generate_solver_points(spacing_mm=25.0, horizon_mm=25.0)


def test_three_band_translated_bowl_asset_passes_legacy_validator(tmp_path: Path) -> None:
    spec = bowl.BowlSpec(center_xyz_mm=(10.0, -3.0, 50.0))
    package = tmp_path / "three_bands"
    result = bowl.create_spherical_bowl_asset_package(
        package, pattern="three_bands", seed=20261015, spec=spec
    )

    validation = validate_asset(package)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((package / "validation" / "geometry.json").read_text(encoding="utf-8"))
    profile = manifest["provenance"]["spec"]
    assert validation["contract_status"] == "PASS"
    assert validation["geometry_status"] == "PASS"
    assert result["validation"]["contract_status"] == "PASS"
    assert profile["shape"] == "concentric_lower_hemisphere"
    assert profile["outer_radius_mm"] == 12.0
    assert profile["inner_radius_mm"] == 8.0
    assert profile["center_xyz_mm"] == [10.0, -3.0, 50.0]
    assert manifest["material"]["mechanics"] == {
        "rho_kg_m3": 2300.0,
        "E_pa": 70.0e9,
        "nu": 0.25,
        "Gc_j_m2": 7.6,
    }
    assert manifest["material"]["calibration_status"] == "UNVALIDATED_PROTOTYPE"
    assert report["status"] == "PASS"
    assert report["checks"]["step_one_valid_solid_and_closed_shell"]
    assert report["checks"]["surface_mesh_watertight_positive_volume"]
    assert report["measurements"]["step_round_trip"]["analytic_volume_mm3"] == pytest.approx(
        bowl.analytic_spherical_bowl_volume_mm3(spec), rel=1e-15
    )

    recipe = manifest["ornament"]["recipe"]
    assert recipe["bands"][0]["center_z_mm"] == pytest.approx(
        spec.bottom_z_mm + 18.0 * spec.outer_radius_mm / 56.0
    )
    expected_red = np.asarray(recipe["palette_linear_rgb"]["red"])
    expected_base = np.asarray(recipe["palette_linear_rgb"]["base"])
    at_band = bowl.evaluate_bowl_paint_at_xyz(
        (spec.center_xyz_mm[0], spec.center_xyz_mm[1], recipe["bands"][0]["center_z_mm"]), recipe
    )
    below_band = bowl.evaluate_bowl_paint_at_xyz(
        (spec.center_xyz_mm[0], spec.center_xyz_mm[1], spec.bottom_z_mm + 0.1), recipe
    )
    assert np.array_equal(at_band, expected_red)
    assert np.array_equal(below_band, expected_base)

    with np.load(package / "fields" / "surface.npz", allow_pickle=False) as fields:
        material_xyz = fields["vertices_material_xyz_mm"]
    with np.load(package / "geometry" / "surface.npz", allow_pickle=False) as surface:
        vertices = surface["vertices_mm"]
    assert np.array_equal(material_xyz, vertices)


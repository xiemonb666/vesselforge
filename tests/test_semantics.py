from __future__ import annotations

import json
import math

import cadquery as cq
import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Torus
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
from OCP.gp import gp_Pnt2d

from vesselforge.semantics import REGIONS, triangle_region_codes


def _oriented_sample(face, row):
    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    sample = row["interior_sample"]
    classifier = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(sample["u"], sample["v"]), 1e-7)
    assert classifier.State() in (TopAbs_IN, TopAbs_ON)
    props = BRepLProp_SLProps(adaptor, sample["u"], sample["v"], 1, 1e-7)
    assert props.IsNormalDefined()
    normal = props.Normal()
    if face.wrapped.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    return np.asarray(sample["point_mm"], dtype=np.float64), np.asarray([normal.X(), normal.Y(), normal.Z()])


def test_classification_uses_actual_canonical_surface_categories_and_excludes_handle_roots(sample_packages):
    asset = sample_packages[0]
    manifest = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
    semantics = json.loads((asset / "metadata" / "face_semantics.json").read_text(encoding="utf-8"))
    shape = cq.importers.importStep(str(asset / "geometry" / "solid.step")).val()
    spec = manifest["provenance"]["spec"]["parameters"]
    assert semantics["status"] == "PASS"
    assert semantics["canonical_step_face_count"] == len(shape.Faces()) == 26
    assert semantics["counts"] == {
        "base": 2,
        "body_inner": 8,
        "body_outer": 9,
        "handle": 6,
        "natural_rim": 1,
    }
    assert {row["region_name"] for row in semantics["faces"]} == set(REGIONS.values())

    actual_handle_sources: set[int] = set()
    base_planes = 0
    rim_planes = 0
    revolution_sources: set[int] = set()
    for index, (face, row) in enumerate(zip(shape.Faces(), semantics["faces"])):
        assert row["face_index_zero_based"] == index
        assert row["status"] == "CLASSIFIED"
        assert row["classification_basis"]
        assert row["classifier_version"] == semantics["classifier"]
        assert row["canonical_step_sha256"] == semantics["canonical_step_sha256"]
        point, normal = _oriented_sample(face, row)
        surface = BRepAdaptor_Surface(face.wrapped, True)
        kind = surface.GetType()
        if kind in (GeomAbs_Cone, GeomAbs_Cylinder):
            axis = surface.Cone().Axis() if kind == GeomAbs_Cone else surface.Cylinder().Axis()
            direction = np.asarray([axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()])
            location = np.asarray([axis.Location().X(), axis.Location().Y(), axis.Location().Z()])
            centered_on_vessel_axis = abs(direction[2]) > 0.99999 and math.hypot(location[0], location[1]) < 1e-4
            if centered_on_vessel_axis:
                revolution_sources.add(index)
                radial_normal_dot = float(np.dot(point[:2], normal[:2]))
                assert row["region_name"] == ("body_outer" if radial_normal_dot > 0 else "body_inner")
            elif kind == GeomAbs_Cylinder:
                geometry = surface.Cylinder()
                radius_matches = math.isclose(geometry.Radius(), spec["handle_radius_mm"], abs_tol=2e-3)
                horizontal_segment = abs(abs(direction[0]) - 1) < 1e-5 and abs(location[1]) < 2e-3 and any(abs(location[2] - spec[z_name]) < 2e-3 for z_name in ("handle_low_z_mm", "handle_high_z_mm"))
                outer_vertical_segment = abs(abs(direction[2]) - 1) < 1e-5 and abs(location[1]) < 2e-3 and abs(location[0] - spec["handle_outreach_mm"]) < 2e-3
                if radius_matches and (horizontal_segment or outer_vertical_segment):
                    assert row["region_name"] == "handle"
                    actual_handle_sources.add(index)
        elif kind == GeomAbs_Torus:
            surface_geometry = surface.Torus()
            center = surface_geometry.Axis().Location()
            center_xyz = np.asarray([center.X(), center.Y(), center.Z()])
            assert math.isclose(surface_geometry.MinorRadius(), spec["handle_radius_mm"], abs_tol=2e-3)
            assert abs(center_xyz[1]) < 2e-3
            assert row["region_name"] == "handle"
            actual_handle_sources.add(index)
        elif kind == GeomAbs_Plane:
            plane = surface.Plane()
            plane_z = plane.Location().Z()
            if abs(plane_z - spec["body_height_mm"]) < 2e-3:
                assert row["region_name"] == "natural_rim"
                rim_planes += 1
            elif abs(plane_z) < 2e-3 or abs(plane_z - spec["wall_mm"]) < 2e-3:
                assert row["region_name"] == "base"
                base_planes += 1
            elif abs(abs(normal[0]) - 1) < 1e-5 and abs(plane.Location().X() - 0.83 * spec["body_width_mm"] / 2) < 2e-3:
                assert row["region_name"] == "handle"
                actual_handle_sources.add(index)

    assert len(revolution_sources) == 17
    assert base_planes == 2
    assert rim_planes == 1
    assert actual_handle_sources == {
        row["face_index_zero_based"] for row in semantics["faces"] if row["region_name"] == "handle"
    }

    with np.load(asset / "geometry" / "mesh_lineage.npz", allow_pickle=False) as lineage:
        sources = lineage["face_source_brep_index"].copy()
    with np.load(asset / "fields" / "surface.npz", allow_pickle=False) as fields:
        regions = fields["face_region"].copy()
        albedo = fields["albedo_linear_rgb"].copy()
    projected = triangle_region_codes(semantics, sources)
    assert np.array_equal(regions, projected)
    assert 255 not in set(regions.astype(int))
    root_triangles = np.isin(sources, sorted(actual_handle_sources))
    assert root_triangles.any()
    assert np.all(regions[root_triangles] == 5)
    np.testing.assert_array_equal(
        albedo[root_triangles],
        np.tile(np.asarray([0.66, 0.49, 0.34], dtype=np.float32), (root_triangles.sum(), 1)),
    )


def test_unknown_canonical_face_blocks_triangle_coloring():
    report = {
        "status": "PENDING",
        "faces": [
            {
                "status": "UNKNOWN",
                "region_code": None,
                "region_name": "UNKNOWN",
            }
        ],
    }
    with pytest.raises(ValueError, match="UNKNOWN/PENDING"):
        triangle_region_codes(report, np.asarray([0], dtype=np.int32))


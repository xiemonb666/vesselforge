from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from vesselforge.schema import validate_asset


def test_same_seed_geometry_and_counterfactual_painted_fields(sample_packages) -> None:
    first, second = sample_packages
    with np.load(first / "geometry" / "surface.npz", allow_pickle=False) as a:
        vertices_a = a["vertices_mm"].copy()
        faces_a = a["faces"].copy()
    with np.load(second / "geometry" / "surface.npz", allow_pickle=False) as b:
        vertices_b = b["vertices_mm"].copy()
        faces_b = b["faces"].copy()
    assert np.array_equal(vertices_a, vertices_b)
    assert np.array_equal(faces_a, faces_b)
    with np.load(first / "fields" / "surface.npz", allow_pickle=False) as a:
        color_a = a["albedo_linear_rgb"].copy()
        region_a = a["face_region"].copy()
        material_xyz = a["vertices_material_xyz_mm"].copy()
    with np.load(second / "fields" / "surface.npz", allow_pickle=False) as b:
        color_b = b["albedo_linear_rgb"].copy()
        region_b = b["face_region"].copy()
    assert np.array_equal(region_a, region_b)
    assert np.array_equal(material_xyz, vertices_a)
    painted = region_a == 1
    assert painted.any()
    assert not np.array_equal(color_a[painted], color_b[painted])
    assert validate_asset(first)["contract_status"] == "PASS"
    assert validate_asset(second)["contract_status"] == "PASS"


def test_report_contains_real_cad_wall_and_joint_checks(sample_packages) -> None:
    asset = sample_packages[0]
    manifest = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((asset / manifest["validation"]["report"]).read_text(encoding="utf-8"))
    measurements = report["measurements"]
    assert measurements["actual_cad_sections"]["cad_floor_face_separation_mm"] >= 3.98
    assert measurements["actual_cad_sections"]["body_handle_intersection_volume_mm3"] > 0
    assert all(item["cad_valid"] for item in measurements["actual_cad_sections"]["handle_attachment_windows"].values())
    assert measurements["profile_realism_status"].startswith("REALISM_PENDING")
    assert report["checks"]["surface_mesh_watertight"]



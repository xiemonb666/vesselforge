from __future__ import annotations

import json

import numpy as np

from vesselforge.appearance import evaluate_continuous_albedo_at_z, make_recipe
from vesselforge.geometry import VesselSpec


def test_continuous_pattern_evaluation_does_not_depend_on_mesh_centroids() -> None:
    recipe = make_recipe("four_bands", "test-material", VesselSpec())
    heights = np.asarray([15.0, 25.0, 34.0, 43.0, 32.0], dtype=np.float64)
    evaluated = evaluate_continuous_albedo_at_z(heights, recipe)
    palette = recipe["palette_linear_rgb"]
    np.testing.assert_allclose(evaluated[0], palette["dark"])
    np.testing.assert_allclose(evaluated[1], palette["dark"])
    np.testing.assert_allclose(evaluated[2], palette["red"])
    np.testing.assert_allclose(evaluated[3], palette["dark"])
    np.testing.assert_allclose(evaluated[4], palette["base"])


def test_report_exposes_missing_band_in_per_face_approximation(sample_packages) -> None:
    asset = sample_packages[0]
    manifest = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((asset / manifest["validation"]["report"]).read_text(encoding="utf-8"))
    coverage = report["measurements"]["appearance_coverage"]
    assert coverage["per_face_approximation_status"] == "FAIL"
    bands = coverage["bands"]
    assert [band["status"] for band in bands] == ["PASS", "PASS", "FAIL", "PASS"]
    assert bands[2]["color"] == "red"
    assert bands[2]["center_z_mm"] == 34.0
    assert bands[2]["covered_face_count"] == 0
    assert "centroid" in bands[2]["reason"]
    assert coverage["continuous_shader_preview_status"] == "PENDING"

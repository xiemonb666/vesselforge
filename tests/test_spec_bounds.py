from __future__ import annotations

import math

import pytest

from vesselforge.geometry import VesselSpec


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("body_width_mm", math.nan, "finite"),
        ("body_height_mm", math.inf, "finite"),
        ("tessellation_linear_mm", 1e-6, "between 0.04 and 0.25"),
        ("tessellation_angular_rad", 1e-6, "between 0.02 and 0.20"),
        ("handle_outreach_mm", 90.0, "at most 45 mm"),
    ],
)
def test_nonfinite_or_unbounded_mesh_specs_fail_closed(field, value, match) -> None:
    with pytest.raises(ValueError, match=match):
        VesselSpec(**{field: value}).validate()

from __future__ import annotations

from vesselforge.geometry import VesselSpec
from experiments.smooth_cad_spike import build_shelled_body


def test_native_c2_meridian_and_inward_shell_are_real_brep_geometry():
    spec = VesselSpec()
    outer, hollow, details = build_shelled_body(spec)
    meridian = details["meridian"]

    assert meridian["edge_type"] == "BSPLINE"
    assert meridian["is_C2_at_all_internal_knots"]
    assert len(meridian["internal_knot_derivative_checks"]) >= 5
    assert max(item["d1_relative_jump"] for item in meridian["internal_knot_derivative_checks"]) < 1e-3
    assert max(item["d2_relative_jump"] for item in meridian["internal_knot_derivative_checks"]) < 1e-3
    assert meridian["start_tangent_dot_flat_floor_direction"] > 0.99
    assert meridian["end_tangent_dot_vertical_lip_direction"] > 0.99

    assert outer.isValid() and len(outer.Solids()) == 1
    assert hollow.isValid() and len(hollow.Solids()) == 1 and len(hollow.Shells()) == 1
    assert hollow.Volume() > 0
    assert hollow.Volume() < outer.Volume()

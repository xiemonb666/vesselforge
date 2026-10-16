"""Stable geometry-only B-rep bounds used to identify canonical faces."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box


BREP_FACE_BOUNDS_POLICY_ID = "vf.brep-face-bounds/geometry-only-addoptimal-false-false/v1"
BREP_FACE_BOUNDS_POLICY_MISSING_REASON = (
    "CANONICAL_BREP_FACE_BOUNDS_POLICY_MISSING_OR_UNSUPPORTED"
)
_BREP_FACE_BOUNDS_POLICY = {
    "policy_id": BREP_FACE_BOUNDS_POLICY_ID,
    "algorithm": "OCP.BRepBndLib.AddOptimal_s",
    "use_triangulation": False,
    "use_shape_tolerance": False,
    "units": "mm",
    "bounds_order": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
}


def brep_face_bounds_policy_record() -> dict[str, Any]:
    """Return a fresh JSON-compatible record of the face-bounds identity policy."""
    return {
        **_BREP_FACE_BOUNDS_POLICY,
        "bounds_order": list(_BREP_FACE_BOUNDS_POLICY["bounds_order"]),
    }


def validate_brep_face_bounds_policy(record: Any) -> None:
    """Require the exact declared policy; legacy or modified records stay unknown."""
    if not isinstance(record, Mapping) or set(record) != set(_BREP_FACE_BOUNDS_POLICY):
        raise ValueError(BREP_FACE_BOUNDS_POLICY_MISSING_REASON)
    if (
        type(record.get("policy_id")) is not str
        or record.get("policy_id") != BREP_FACE_BOUNDS_POLICY_ID
        or type(record.get("algorithm")) is not str
        or record.get("algorithm") != _BREP_FACE_BOUNDS_POLICY["algorithm"]
        or type(record.get("use_triangulation")) is not bool
        or record.get("use_triangulation") is not False
        or type(record.get("use_shape_tolerance")) is not bool
        or record.get("use_shape_tolerance") is not False
        or type(record.get("units")) is not str
        or record.get("units") != "mm"
    ):
        raise ValueError(BREP_FACE_BOUNDS_POLICY_MISSING_REASON)
    order = record.get("bounds_order")
    expected_order = _BREP_FACE_BOUNDS_POLICY["bounds_order"]
    if (
        type(order) is not list
        or any(type(value) is not str for value in order)
        or order != expected_order
    ):
        raise ValueError(BREP_FACE_BOUNDS_POLICY_MISSING_REASON)


def _add_optimal_s(
    shape: Any,
    box: Bnd_Box,
    use_triangulation: bool,
    use_shape_tolerance: bool,
) -> None:
    """Keep the OCP call in one seam so tests can assert the explicit flags."""
    BRepBndLib.AddOptimal_s(shape, box, use_triangulation, use_shape_tolerance)


def brep_bounds_mm(shape_or_face: Any) -> tuple[float, float, float, float, float, float]:
    """Return geometry-only B-rep bounds in ``xmin,xmax,ymin,ymax,zmin,zmax`` order.

    CadQuery objects are unwrapped through ``wrapped``. Raw TopoDS shapes are accepted as-is.
    This helper never uses triangulation, shape tolerance, a default overload, or a fallback.
    """
    wrapped = getattr(shape_or_face, "wrapped", shape_or_face)
    if wrapped is None:
        raise ValueError("CANONICAL_BREP_BOUNDS_SHAPE_INVALID")
    box = Bnd_Box()
    _add_optimal_s(wrapped, box, False, False)
    if box.IsVoid():
        raise ValueError("CANONICAL_BREP_BOUNDS_EMPTY")
    if box.IsWhole():
        raise ValueError("CANONICAL_BREP_BOUNDS_NOT_FINITE")
    try:
        values = tuple(float(value) for value in box.Get())
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("CANONICAL_BREP_BOUNDS_INVALID") from exc
    if len(values) != 6 or not all(math.isfinite(value) for value in values):
        raise ValueError("CANONICAL_BREP_BOUNDS_NOT_FINITE")
    xmin, ymin, zmin, xmax, ymax, zmax = values
    if xmin > xmax or ymin > ymax or zmin > zmax:
        raise ValueError("CANONICAL_BREP_BOUNDS_RANGE_INVALID")
    return xmin, xmax, ymin, ymax, zmin, zmax

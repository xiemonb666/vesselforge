from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

import cadquery as cq

from vesselforge import brep_identity


class _FakeBox:
    def __init__(self, *, void: bool = False, whole: bool = False,
                 values: tuple[float, ...] = ()) -> None:
        self.void = void
        self.whole = whole
        self.values = values

    def IsVoid(self) -> bool:
        return self.void

    def IsWhole(self) -> bool:
        return self.whole

    def Get(self) -> tuple[float, ...]:
        return self.values


def test_brep_bounds_uses_explicit_geometry_only_call_and_asset_order(monkeypatch) -> None:
    boxes: list[_FakeBox] = []
    calls: list[tuple[object, bool, bool]] = []

    def fake_box() -> _FakeBox:
        box = _FakeBox()
        boxes.append(box)
        return box

    def fake_add_optimal(
        shape: object, box: _FakeBox, use_triangulation: bool, use_shape_tolerance: bool,
    ) -> None:
        calls.append((shape, use_triangulation, use_shape_tolerance))
        box.values = (1.0, 3.0, 5.0, 2.0, 4.0, 6.0)

    monkeypatch.setattr(brep_identity, "Bnd_Box", fake_box)
    monkeypatch.setattr(brep_identity, "_add_optimal_s", fake_add_optimal)
    face = SimpleNamespace(wrapped="topods-face")

    assert brep_identity.brep_bounds_mm(face) == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert calls == [("topods-face", False, False)]
    assert len(boxes) == 1


@pytest.mark.parametrize(
    ("box", "message"),
    [
        (_FakeBox(void=True), "CANONICAL_BREP_BOUNDS_EMPTY"),
        (_FakeBox(whole=True), "CANONICAL_BREP_BOUNDS_NOT_FINITE"),
        (_FakeBox(values=(0.0, 0.0, 0.0, 1.0, 1.0)), "CANONICAL_BREP_BOUNDS_NOT_FINITE"),
        (_FakeBox(values=(0.0, 0.0, 0.0, float("nan"), 1.0, 1.0)), "CANONICAL_BREP_BOUNDS_NOT_FINITE"),
        (_FakeBox(values=(2.0, 0.0, 0.0, 1.0, 1.0, 1.0)), "CANONICAL_BREP_BOUNDS_RANGE_INVALID"),
    ],
)
def test_brep_bounds_rejects_empty_nonfinite_or_invalid_ranges(monkeypatch, box, message) -> None:
    monkeypatch.setattr(brep_identity, "Bnd_Box", lambda: box)
    monkeypatch.setattr(brep_identity, "_add_optimal_s", lambda *_args: None)

    with pytest.raises(ValueError, match=message):
        brep_identity.brep_bounds_mm(object())


def test_brep_bounds_rejects_missing_shape() -> None:
    with pytest.raises(ValueError, match="CANONICAL_BREP_BOUNDS_SHAPE_INVALID"):
        brep_identity.brep_bounds_mm(None)


def test_brep_face_bounds_are_stable_before_and_after_triangulation() -> None:
    shape = cq.Solid.makeCylinder(10.0, 10.0)
    faces = shape.Faces()
    whole_shape_before = brep_identity.brep_bounds_mm(shape)
    faces_before = [brep_identity.brep_bounds_mm(face) for face in faces]

    shape.tessellate(0.05, 0.08)

    assert brep_identity.brep_bounds_mm(shape) == whole_shape_before
    assert [brep_identity.brep_bounds_mm(face) for face in shape.Faces()] == faces_before


def test_brep_face_bounds_policy_record_is_fresh_and_validated_exactly() -> None:
    policy = brep_identity.brep_face_bounds_policy_record()
    assert policy == {
        "policy_id": "vf.brep-face-bounds/geometry-only-addoptimal-false-false/v1",
        "algorithm": "OCP.BRepBndLib.AddOptimal_s",
        "use_triangulation": False,
        "use_shape_tolerance": False,
        "units": "mm",
        "bounds_order": ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"],
    }
    brep_identity.validate_brep_face_bounds_policy(policy)
    policy["bounds_order"].reverse()
    assert brep_identity.brep_face_bounds_policy_record()["bounds_order"] == [
        "xmin", "xmax", "ymin", "ymax", "zmin", "zmax",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "unknown_id",
        "numeric_false_flag",
        "wrong_unit",
        "wrong_order",
        "extra_key",
    ],
)
def test_brep_face_bounds_policy_rejects_legacy_and_modified_records(mutation) -> None:
    record = brep_identity.brep_face_bounds_policy_record()
    if mutation == "missing":
        value = None
    else:
        value = deepcopy(record)
        if mutation == "unknown_id":
            value["policy_id"] = "vf.brep-face-bounds/unknown"
        elif mutation == "numeric_false_flag":
            value["use_triangulation"] = 0
        elif mutation == "wrong_unit":
            value["units"] = "inch"
        elif mutation == "wrong_order":
            value["bounds_order"][0] = "ymin"
        elif mutation == "extra_key":
            value["cache_provenance"] = "assumed"

    with pytest.raises(ValueError, match=brep_identity.BREP_FACE_BOUNDS_POLICY_MISSING_REASON):
        brep_identity.validate_brep_face_bounds_policy(value)

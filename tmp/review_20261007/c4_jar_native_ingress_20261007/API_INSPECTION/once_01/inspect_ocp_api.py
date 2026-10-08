"""Read-only OCP binding introspection. Import classes; never instantiate them."""

from __future__ import annotations

import inspect
import json
import time

started = time.perf_counter()
import OCP
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.Geom import Geom_BSplineCurve, Geom_OffsetCurve
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve

import_seconds = time.perf_counter() - started


def clipped_doc(value: object, limit: int) -> dict[str, object]:
    doc = getattr(value, "__doc__", None)
    if not isinstance(doc, str):
        return {"text": None, "truncated": False, "original_chars": 0}
    return {
        "text": doc[:limit],
        "truncated": len(doc) > limit,
        "original_chars": len(doc),
    }


def signature(value: object) -> str:
    try:
        return str(inspect.signature(value))
    except Exception as exc:  # Extension callables may not publish signature metadata.
        return f"UNAVAILABLE:{type(exc).__name__}:{str(exc)[:300]}"


targets = (
    (
        "Geom_BSplineCurve",
        Geom_BSplineCurve,
        ("D0", "D1", "D2", "DN", "FirstParameter", "LastParameter", "NbPoles", "NbKnots"),
    ),
    (
        "Geom_OffsetCurve",
        Geom_OffsetCurve,
        ("D0", "D1", "BasisCurve", "Direction", "Offset", "FirstParameter", "LastParameter", "SetDirection", "SetOffsetValue"),
    ),
    (
        "BRepBuilderAPI_MakeEdge",
        BRepBuilderAPI_MakeEdge,
        ("IsDone", "Edge", "Shape", "Error"),
    ),
    (
        "BRepBuilderAPI_MakeFace",
        BRepBuilderAPI_MakeFace,
        ("IsDone", "Face", "Shape", "Error", "Build"),
    ),
    (
        "BRepPrimAPI_MakeRevol",
        BRepPrimAPI_MakeRevol,
        ("IsDone", "Shape", "FirstShape", "LastShape", "CheckValidity", "Build"),
    ),
    (
        "GeomAPI_ProjectPointOnCurve",
        GeomAPI_ProjectPointOnCurve,
        ("NbPoints", "LowerDistance", "Parameter", "Point", "NearestPoint", "Init", "Perform", "IsDone"),
    ),
)

records: dict[str, object] = {}
for name, cls, method_names in targets:
    methods: dict[str, object] = {}
    for method_name in method_names:
        method = getattr(cls, method_name, None)
        if method is None:
            methods[method_name] = {"present": False}
            continue
        methods[method_name] = {
            "present": True,
            "signature": signature(method),
            "doc": clipped_doc(method, 1100),
        }
    init = getattr(cls, "__init__", None)
    records[name] = {
        "class_doc": clipped_doc(cls, 2600),
        "class_signature": signature(cls),
        "constructor_signature": signature(init) if init is not None else None,
        "constructor_doc": clipped_doc(init, 4200) if init is not None else None,
        "selected_methods": methods,
    }

print(
    json.dumps(
        {
            "schema": "vesselforge.c4_jar_native_ingress.ocp_api_inspection/0.1",
            "read_only": True,
            "geometry_constructed": False,
            "cad_operations_run": False,
            "solver_run": False,
            "ocp_version": getattr(OCP, "__version__", None),
            "import_seconds": import_seconds,
            "class_count": len(records),
            "classes": records,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
)

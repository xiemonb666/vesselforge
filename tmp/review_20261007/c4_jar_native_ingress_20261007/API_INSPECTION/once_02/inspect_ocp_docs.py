import json
import sys

from OCP.Geom import Geom_BSplineCurve, Geom_OffsetCurve
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve

CLASSES = (
    ("Geom_BSplineCurve", Geom_BSplineCurve),
    ("Geom_OffsetCurve", Geom_OffsetCurve),
    ("BRepBuilderAPI_MakeEdge", BRepBuilderAPI_MakeEdge),
    ("BRepBuilderAPI_MakeFace", BRepBuilderAPI_MakeFace),
    ("BRepPrimAPI_MakeRevol", BRepPrimAPI_MakeRevol),
    ("GeomAPI_ProjectPointOnCurve", GeomAPI_ProjectPointOnCurve),
)
DOC_LIMIT = 3500

def captured_doc(value):
    if value is None:
        return {"text": None, "original_chars": 0, "truncated": False}
    text = str(value)
    return {
        "text": text[:DOC_LIMIT],
        "original_chars": len(text),
        "truncated": len(text) > DOC_LIMIT,
    }

records = []
for name, cls in CLASSES:
    class_doc = cls.__doc__
    init_doc = cls.__init__.__doc__
    records.append({
        "class": name,
        "class_doc": captured_doc(class_doc),
        "init_doc": captured_doc(init_doc),
    })

print(json.dumps({
    "schema": "vesselforge.ocp_doc_only_introspection/0.1",
    "inspection_scope": "class.__doc__ and class.__init__.__doc__ only",
    "geometry_constructed": False,
    "records": records,
}, ensure_ascii=True, separators=(",", ":")))
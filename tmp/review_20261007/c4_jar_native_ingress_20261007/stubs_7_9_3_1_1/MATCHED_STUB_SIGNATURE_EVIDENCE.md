# Matched OCP Stub Signatures — Review Only

The installed runtime is `cadquery-ocp` 7.9.3.1.1. Its METADATA requires only `cadquery-ocp-proxy==7.9.3.1.1` and `vtk==9.6.2`; it mentions `cadquery-ocp-stubs` as a separate PyPI option but does not pin it. I downloaded the exact matching Windows wheel to this review directory with `pip download --no-deps --no-index --only-binary=:all: --no-cache-dir`. I did not install it. PyPI lists release 7.9.3.1.1 and the Windows wheel checksum below. The downloaded wheel is 2,899,849 bytes with matching SHA-256 `5ecba090df1ada12c558ff4a1b49c61d5155edc8cb3411067a785e3b43f4b359`. The venv's CadQuery, OCP, OCP proxy, and VTK metadata pins matched before and after; pip rc 0, 1.984 s, captured stdout/stderr 0 bytes. See `download_receipt.json` and `STUB_WHEEL_SOURCE_EVIDENCE.json`. [Official PyPI release page](https://pypi.org/project/cadquery-ocp-stubs/7.9.3.1.1/) lists this exact version, wheel and checksum.

The wheel's embedded METADATA verified `Name: cadquery-ocp-stubs`, `Version: 7.9.3.1.1`. I extracted only the 11 selected `.pyi` modules into `extracted_review_v2/OCP-stubs/`; nothing was copied to `site-packages`. No OCP import, geometry construction, CAD, STEP, or solver ran. The wheel's original 5-second doc import timeout remains preserved in the sibling `API_INSPECTION/once_02` directory.

## Exact declarations in the matched stubs

All paths and line numbers below refer to the extracted wheel files. Their SHA-256 values are recorded in `stub_extract_v2_manifest.json`.

- `Geom/__init__.pyi:1655`: rational `Geom_BSplineCurve.__init__(Poles: TColgp_Array1OfPnt, Weights: TColStd_Array1OfReal, Knots: TColStd_Array1OfReal, Multiplicities: TColStd_Array1OfInteger, Degree: int, Periodic: bool=False, CheckRational: bool=True)`. The non-rational overload is line 1653. This supports 17 point and weight entries, 13 distinct knots and 13 multiplicities for the frozen open degree-5 knot vector.
- `Geom/__init__.pyi:5244`: `Geom_OffsetCurve.__init__(C: Geom_Curve, Offset: float, V: gp_Dir, isNotCheckC0: bool=False)`. Its class contract at line 5051 gives positive direction `T × V` and warns that self-intersections are not removed at construction. Official OCCT V7_9_3 evaluator source resolves the contradictory constructor prose: `CalculateD0` uses `T.Crossed(V)` at one-based source line 182. With the already accepted `V=(0,+1,0)` and signed `+3 mm`, the RZ displacement is inward `(-z′,+r′)`.
- `BRepBuilderAPI/__init__.pyi:616`: `BRepBuilderAPI_MakeEdge(Geom_Curve, p1: float, p2: float)`. The result has `Edge()` and `IsDone()` methods.
- `BRepBuilderAPI/__init__.pyi:1167,1219,1228`: `BRepBuilderAPI_MakeWire()` accepts `Add(TopoDS_Edge)` and returns `Wire() -> TopoDS_Wire`; `IsDone()` is available at line 1203.
- `BRepBuilderAPI/__init__.pyi:838`: `BRepBuilderAPI_MakeFace(gp_Pln, TopoDS_Wire, Inside: bool=True)`; `Face()` is typed as `TopoDS_Face` at line 773.
- `BRepPrimAPI/__init__.pyi:447`: `BRepPrimAPI_MakeRevol(TopoDS_Shape, gp_Ax1, D: float, Copy: bool=False)`. CadQuery’s installed wrapper passes `radians(angleDegrees)`, so the angle argument is in radians.
- `GeomAPI/__init__.pyi:489`: `GeomAPI_ProjectPointOnCurve(gp_Pnt, Geom_Curve, Umin: float, Usup: float)`; `LowerDistanceParameter()` is at line 455 and `NbPoints()` at line 459.
- `TopoDS/TopoDS/__init__.pyi:30,36,60`: `TopoDS.Edge(shape)`, `TopoDS.Face(shape)` and `TopoDS.Wire(shape)` return typed topology handles.
- `gp/__init__.pyi:1510,326,3581`: `gp_Dir(x,y,z)`, `gp_Ax1(gp_Pnt,gp_Dir)` and `gp_Pln(gp_Pnt,gp_Dir)` are declared. `gp_Pnt(x,y,z)` is line 3731.
- `TColgp/__init__.pyi:580,609` and `TColStd/__init__.pyi:649,678,823,852`: point, real and integer 1D arrays support `(lower:int, upper:int)` and `SetValue(index, item)`. CadQuery's installed helper fills these arrays with one-based indices.

These declarations are sufficient to draft the exact-curve source using the 17 rational poles, a direct signed `+3 mm` offset, edge/wire/planar-face closure, and a 360-degree revolve. No geometry source has been frozen yet, pending root review of this signature evidence and gates.

## Limits and gate values for that later source

Use `<=1e-6 mm` for finite offset and endpoint residuals. Keep the existing STEP geometry-bounds identity tolerance `1e-7 mm`; if it is too strict, report the roundtrip gate as failed/flagged instead of relaxing it. Compare section area and solid volume with relative tolerance `1e-8`. Finite samples remain diagnostic only. They do not prove global native B-rep validity, global minimum wall thickness, or physics readiness.
# Local OCP Binding Source Scan

Status: SOURCE-ONLY; no OCP/DLL import, geometry construction, CAD run, STEP operation, solver, or test was performed in this scan. The prior `once_02` import attempt is preserved and was not retried.

## Installed binding material

- Runtime metadata identifies `cadquery-ocp` 7.9.3.1.1. Its METADATA says this package is generated from OCP and that typing stubs are available as a separate PyPI package `cadquery-ocp-stubs`.
- This venv has 325 OCP `.py` files and zero OCP `.pyi` files. The Python files are generated package `__init__.py` re-exports; for example, `OCP/Geom/__init__.py` re-exports `..OCP.Geom`. No `cadquery-ocp-stubs` package directory is installed. Scanning OCP text sources for the six requested class names found no constructor/signature definitions; compiled binding material is not a local text signature source.
- `OCP/TopoDS/__init__.py` contains compatibility aliases such as `TopoDS.Wire_s = TopoDS.Wire`; it does not declare signatures.

## Local Python call-site evidence (examples, not binding declarations)

CadQuery 2.8.0 source provides usage examples for five of the six requested APIs:

- `Geom_BSplineCurve`: `occ_impl/nurbs.py:158-160` calls `(points, unique_knots, multiplicities, order, periodic)`; `occ_impl/importers/dxf.py:96-100` calls rational `(points, weights, knots, multiplicities, degree, periodic)` and non-rational `(points, knots, multiplicities, degree, periodic)`. The helper builds 1-based `TColgp_Array1OfPnt`, `TColStd_Array1OfReal`, and `TColStd_Array1OfInteger` arrays and fills with `SetValue(i + 1, ...)` (`nurbs.py:40-47,65-80`).
- `BRepBuilderAPI_MakeEdge`: used as `MakeEdge(curve).Edge()/Shape()` (`nurbs.py:164`, `dxf.py:102`).
- `BRepBuilderAPI_MakeFace`: examples include `MakeFace(wire, True)` (`shapes.py:3658-3664`) and bounded plane overloads (`shapes.py:3594-3599`).
- `BRepPrimAPI_MakeRevol`: examples use `(face, gp_Ax1, radians(angle), True)` (`shapes.py:4558-4562`) and `(shape, axis, radians(angle))` (`shapes.py:6956-6960`).
- `GeomAPI_ProjectPointOnCurve`: examples use `(point, curve, first_u, last_u)` and call `.LowerDistanceParameter()` (`shapes.py:2163-2165,2194-2196`).
- Supporting topology call sites use `BRepBuilderAPI_MakeWire()`, `.Add(...)`, `.Build()`, `.Wire()` (`shapes.py:2966-2975,3104-3117`) and `TopoDS.Wire(shape)` (`shapes.py:3658`). These are client-code usage patterns only.

A repository-package search found no `Geom_OffsetCurve` call in CadQuery Python sources. The official OCCT V7_9_3 C++ constructor declaration is already captured in `API_INSPECTION/once_02/PRIMARY_SOURCE_EVIDENCE_CORRECTED.json`, but it does not verify OCP’s Python overload binding. Therefore this scan does not authorize or freeze a direct Python `Geom_OffsetCurve` constructor call. No implementation was added because that route’s key binding signature remains unverified.

## Preserved introspection attempt

`API_INSPECTION/once_02/inspect_ocp_docs.py` imports the six named classes and reads only each class `__doc__` and `__init__.__doc__`. `capture_once_02.py` launches it with `subprocess.run(capture_output=True, timeout=5)` and captures byte streams and pre/post pins. The single attempt ended `TIMEOUT_5S`, with `TimeoutExpired`, no child return code, and empty stdout/stderr. Outer elapsed was 6.195 seconds, all source pins matched, and the final directory count was 32,231 bytes. No retry was performed.

## Pinned local source references

| File | SHA-256 |
|---|---|
| `cadquery_ocp-7.9.3.1.1.dist-info/METADATA` | `bd3beda81cf82c2c6eb8453e77c519645f3c9ad6ec51c2c6b54ba8dd8ae7dae6` |
| `OCP/Geom/__init__.py` | `2bea47c4726e49b72052e03ea9c34082050f3ec7d52582a4e166858586f7beba` |
| `OCP/GeomAPI/__init__.py` | `6c7c8d7cf047670010ae217c8a854dc8f7512ce6195761350c5e31fab7acf7cd` |
| `OCP/BRepBuilderAPI/__init__.py` | `061c6a111200b5f95fc6f665bd9248e12a7029c5d5268203ab9692766adfa594` |
| `OCP/BRepPrimAPI/__init__.py` | `69f701995fa6bc495566eb9d53983f7154df7d7a7b8147b0b24b07fc194a130e` |
| `OCP/TopoDS/__init__.py` | `efdaf37a3f177048df89ad745026110b2220b527c78a920d4f16cbd895e4892f` |
| `cadquery/occ_impl/nurbs.py` | `0464ac65ae0aac9e5519ea9e405fbeb3c96751c5450e3ced811601fb5a62a47e` |
| `cadquery/occ_impl/importers/dxf.py` | `e7f4f8e8e76d4e8bce1de18ac398fe7e16103ba6dcef9554b8dfae7c7ba7db60` |
| `cadquery/occ_impl/shapes.py` | `6f6a9136b45177bd9cb00ed1706f90078aab04ea2b1a7eb26ab5b46aa43f6c94` |
| `API_INSPECTION/once_02/inspect_ocp_docs.py` | `89ae2dd64b68d9c6d833ffe2f54b011669fe3e0391d79f4c0fcec4bbe09936b8` |
| `API_INSPECTION/once_02/capture_once_02.py` | `4eb27c299f4cdd5a4a36309533c1fa87a49cb79ad374dbc35aa9ebfe79edb351` |
| `API_INSPECTION/once_02/receipt.json` | `99e87a125956b30e33af4cf34886b1d2099d124a6697cffc710d342825241bf9` |
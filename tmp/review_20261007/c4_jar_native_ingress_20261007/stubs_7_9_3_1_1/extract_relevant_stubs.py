import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
OUT = ROOT / r"vesselforge\tmp\review_20261007\c4_jar_native_ingress_20261007\stubs_7_9_3_1_1"
WHEEL = OUT / "cadquery_ocp_stubs-7.9.3.1.1-py3-none-win_amd64.whl"
EXPECTED_SHA256 = "5ecba090df1ada12c558ff4a1b49c61d5155edc8cb3411067a785e3b43f4b359"
EXTRACT = OUT / "extracted"
TARGET_MODULES = {
    "Geom", "GeomAPI", "BRepBuilderAPI", "BRepPrimAPI", "TopoDS", "gp",
    "TColgp", "TColStd", "GeomAbs",
}
TARGET_SYMBOLS = {
    "Geom_BSplineCurve", "Geom_OffsetCurve", "BRepBuilderAPI_MakeEdge",
    "BRepBuilderAPI_MakeWire", "BRepBuilderAPI_MakeFace", "BRepPrimAPI_MakeRevol",
    "GeomAPI_ProjectPointOnCurve", "TopoDS", "gp_Pnt", "gp_Dir",
    "TColgp_Array1OfPnt", "TColStd_Array1OfReal", "TColStd_Array1OfInteger",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


if digest(WHEEL) != EXPECTED_SHA256:
    raise SystemExit("wheel SHA256 mismatch; refusing extraction")
if EXTRACT.exists():
    raise SystemExit("extraction target already exists; refusing overwrite")
EXTRACT.mkdir()
selected = []
all_pyi = []
metadata_name = None
with zipfile.ZipFile(WHEEL, "r") as zf:
    names = zf.namelist()
    metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
    if len(metadata_names) != 1:
        raise SystemExit("wheel metadata entry count unexpected")
    metadata_name = metadata_names[0]
    metadata = zf.read(metadata_name).decode("utf-8", errors="replace")
    name_match = re.search(r"(?m)^Name: (.+)$", metadata)
    version_match = re.search(r"(?m)^Version: (.+)$", metadata)
    package_name = name_match.group(1) if name_match else None
    package_version = version_match.group(1) if version_match else None
    if package_name != "cadquery-ocp-stubs" or package_version != "7.9.3.1.1":
        raise SystemExit("wheel internal Name/Version mismatch; refusing extraction")
    for info in zf.infolist():
        if not info.filename.endswith(".pyi"):
            continue
        all_pyi.append(info.filename)
        pp = PurePosixPath(info.filename)
        if not pp.parts or pp.parts[0] != "OCP":
            continue
        module = pp.stem if len(pp.parts) == 2 else pp.parts[1]
        if module in TARGET_MODULES or pp.name == "__init__.pyi" and len(pp.parts) == 2:
            if any(part in ("..", "") for part in pp.parts):
                raise SystemExit("unsafe archive path")
            out_path = EXTRACT.joinpath(*pp.parts)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(zf.read(info.filename))
            selected.append({"archive_path": info.filename, "extracted_path": str(out_path.relative_to(OUT)).replace("\\", "/"), "bytes": out_path.stat().st_size, "sha256": digest(out_path)})

symbol_hits = {s: [] for s in sorted(TARGET_SYMBOLS)}
for row in selected:
    path = OUT / Path(row["extracted_path"])
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        continue
    for number, line in enumerate(lines, 1):
        for symbol in symbol_hits:
            if symbol in line:
                symbol_hits[symbol].append({"path": row["extracted_path"], "line": number, "text": line.strip()[:240]})

manifest = {
    "schema": "vesselforge.ocp_stub_extract_manifest/0.1",
    "wheel": str(WHEEL.relative_to(ROOT)).replace("\\", "/"),
    "wheel_sha256": digest(WHEEL),
    "expected_wheel_sha256": EXPECTED_SHA256,
    "wheel_hash_matches": digest(WHEEL) == EXPECTED_SHA256,
    "internal_metadata_path": metadata_name,
    "internal_name": package_name,
    "internal_version": package_version,
    "pyi_archive_count": len(all_pyi),
    "selected_modules": sorted(TARGET_MODULES),
    "selected_stub_count": len(selected),
    "selected_stubs": selected,
    "symbol_occurrences": symbol_hits,
    "OCP_imported": False,
    "geometry_constructed": False,
    "runtime_modified": False,
}
(OUT / "stub_extract_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
print(json.dumps({"status": "EXTRACTED_REVIEW_COPY", "pyi_archive_count": len(all_pyi), "selected_stub_count": len(selected), "manifest": str((OUT / "stub_extract_manifest.json").relative_to(ROOT)).replace("\\", "/")}, separators=(",", ":")))
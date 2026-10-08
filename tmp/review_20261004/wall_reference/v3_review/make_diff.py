from pathlib import Path
import difflib

review = Path(r"vesselforge/tmp/review_20261004/wall_reference/v3_review")
pairs = [
    ("wall_reference.py", Path(r"vesselforge/src/vesselforge/wall_reference.py")),
    ("test_wall_reference.py", Path(r"vesselforge/tests/test_wall_reference.py")),
]
chunks = []
for name, current_path in pairs:
    before = (review / "before" / name).read_text(encoding="utf-8").splitlines(keepends=True)
    after = current_path.read_text(encoding="utf-8").splitlines(keepends=True)
    chunks.extend(difflib.unified_diff(before, after, fromfile=f"v2/{name}", tofile=f"v3/{name}"))
(review / "v3.diff").write_text("".join(chunks), encoding="utf-8")

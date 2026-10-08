"""Single child entry point for the separately authorized exact checker call."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SOURCE_SHA256 = "2466306decc0af17d47c71d8e66b110aa77255f8f9279b94180a86ee7029886d"
root = Path.cwd().resolve()
source = root / "vesselforge/experiments/global_wall_distance_certificate_20261007/global_wall_distance_certificate.py"
if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
    raise SystemExit("pinned global-wall source hash mismatch")
spec = importlib.util.spec_from_file_location("pinned_global_wall_distance_verifier_run01", source)
if spec is None or spec.loader is None:
    raise RuntimeError("could not create pinned-source import spec")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.run_saved_certificate(root_ready=True)
sys.stdout.buffer.write(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))

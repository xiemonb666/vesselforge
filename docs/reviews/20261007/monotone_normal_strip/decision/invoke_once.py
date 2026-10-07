"""One authorized import-and-call of the pinned source verifier."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

root = Path.cwd().resolve()
source = root / "vesselforge/experiments/monotone_normal_strip_certificate_20261007/monotone_normal_strip_certificate.py"
spec = importlib.util.spec_from_file_location("pinned_monotone_strip_verifier", source)
if spec is None or spec.loader is None:
    raise RuntimeError("could not create frozen-source import spec")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.run_saved_certificate(root_ready=True)
sys.stdout.buffer.write(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))

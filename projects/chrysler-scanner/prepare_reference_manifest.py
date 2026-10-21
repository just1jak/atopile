"""Verify copied original CAD bytes and restore their audited reference times."""
from pathlib import Path
import argparse
import hashlib
import json
import os

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=root / ".local-checks/original-source-manifest.json")
args = parser.parse_args()
source = root / "reference/original-source"
manifest = json.loads((root / "reference/original-source-manifest.json").read_text())
for relative, expected in manifest["files"].items():
    path = (source / relative).resolve()
    assert source.resolve() in path.parents
    assert path.stat().st_size == expected["size"], relative
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"], relative
# All content is verified before changing metadata on these bundled copies.
for relative, expected in manifest["files"].items():
    path = source / relative
    os.utime(path, ns=(path.stat().st_atime_ns, expected["mtime_ns"]))
manifest["source_root"] = str(source)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"verified_reference_files": len(manifest["files"]), "manifest": str(args.output)}))

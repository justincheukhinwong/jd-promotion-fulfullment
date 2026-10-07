"""Record input fingerprints and the analysis environment."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
from .config import ROOT, INPUTS


def write_provenance():
    result_dir = ROOT / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    inputs = []
    for name, path in INPUTS.items():
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        inputs.append({"input": name, "path": str(path.relative_to(ROOT)),
                       "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    (result_dir / "input_manifest.json").write_text(json.dumps(inputs, indent=2) + "\n")
    packages = [line.split("==")[0] for line in (ROOT / "requirements.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")]
    environment = {"python": platform.python_version(),
                   "packages": {package: importlib.metadata.version(package) for package in packages}}
    (result_dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")

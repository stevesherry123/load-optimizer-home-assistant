"""Identify Load Optimizer package files without reading Home Assistant data."""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile


PACKAGE = PurePosixPath("custom_components/load_optimizer")
REQUIRED = {"manifest.json", "__init__.py", "legacy/app_runtime.py"}


def installed_files(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected the Load Optimizer package directory, not a link")
    for path in root.iterdir():
        if path.is_symlink():
            raise ValueError("Unexpected link inside the package")
        if path.is_dir():
            if path.name == "__pycache__":
                continue
            for name, content in installed_files(path):
                yield f"{path.name}/{name}", content
        elif path.is_file():
            yield path.name, path.read_bytes()
        else:
            raise ValueError("Unexpected non-file inside the package")


def archive_files(archive: bytes):
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as package:
        for entry in package:
            if entry.isdir():
                continue
            relative = PurePosixPath(entry.name).relative_to(PACKAGE)
            if not entry.isfile() or ".." in relative.parts:
                raise ValueError("Unexpected archive entry inside the package")
            with package.extractfile(entry) as content:
                yield relative.as_posix(), content.read()


def fingerprint(files) -> dict:
    hashes = {}
    version = None
    for name, content in files:
        if name in hashes:
            raise ValueError("Duplicate package file")
        hashes[name] = hashlib.sha256(content).digest()
        if name == "manifest.json":
            manifest = json.loads(content)
            version = manifest.get("version") if isinstance(manifest, dict) else None
            if (not isinstance(version, str) or len(version) > 64
                    or not re.fullmatch(r"[0-9][a-zA-Z0-9.+-]*", version)
                    or manifest.get("domain") != "load_optimizer"):
                raise ValueError("Not a valid Load Optimizer manifest")
    if not REQUIRED <= hashes.keys():
        raise ValueError("Incomplete Load Optimizer package")
    digest = hashlib.sha256()
    for name, value in sorted(hashes.items()):
        digest.update(name.encode("utf-8") + b"\0" + value)
    return {"manifest_version": version, "files": len(hashes), "sha256": digest.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--installed", type=Path, help="Path to custom_components/load_optimizer")
    source.add_argument("--git-ref", help="Commit or tag in the local repository")
    args = parser.parse_args()
    try:
        if args.installed is not None:
            result = fingerprint(installed_files(args.installed))
        else:
            root = Path(__file__).resolve().parents[1]
            commit = subprocess.run(
                ["git", "rev-parse", "--verify", "--end-of-options", args.git_ref + "^{commit}"],
                cwd=root, check=True, capture_output=True, text=True, timeout=15,
            ).stdout.strip()
            archive = subprocess.run(
                ["git", "archive", "--format=tar", commit, "--", str(PACKAGE)],
                cwd=root, check=True, capture_output=True, timeout=30,
            ).stdout
            result = {**fingerprint(archive_files(archive)), "commit": commit}
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Cannot identify package ({type(error).__name__}).\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

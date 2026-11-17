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
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


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
        yield from package_members(package, wrapped=False)


def package_members(archive: tarfile.TarFile, *, wrapped: bool):
    root = None
    total_size = 0
    for entry in archive:
        if entry.isdir():
            continue
        path = PurePosixPath(entry.name)
        if wrapped:
            if path.parts[1:3] != PACKAGE.parts:
                continue
            outer, *parts = path.parts
            if (outer == ".." or not re.fullmatch(r"[A-Za-z0-9._-]+", outer)
                    or root not in {None, outer}):
                raise ValueError("Unexpected release archive root")
            root = outer
            path = PurePosixPath(*parts)
        relative = path.relative_to(PACKAGE)
        if not entry.isfile() or ".." in relative.parts:
            raise ValueError("Unexpected archive entry inside the package")
        total_size += entry.size
        if total_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Package files exceed the size limit")
        with archive.extractfile(entry) as content:
            yield relative.as_posix(), content.read()


def release_archive_files(path: Path):
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Release archive exceeds the size limit")
    # GitHub's source tarballs wrap the repository in one top-level directory.
    # Inspect only integration regular files; never extract archive paths to disk.
    with tarfile.open(path, mode="r:gz") as archive:
        yield from package_members(archive, wrapped=True)


def fingerprint(files) -> dict:
    hashes = {}
    version = None
    for name, content in files:
        if (not re.fullmatch(r"[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*", name)
                or any(part in {".", ".."} for part in name.split("/"))):
            raise ValueError("Unsupported package file name")
        if name in hashes:
            raise ValueError("Duplicate package file")
        hashes[name] = hashlib.sha256(content).hexdigest()
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
        digest.update(f"{value}  ./{name}\n".encode("ascii"))
    return {"manifest_version": version, "files": len(hashes), "sha256": digest.hexdigest()}


def archived_package(ref: str) -> tuple[str, bytes]:
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"],
        cwd=root, check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit, "--", str(PACKAGE)],
        cwd=root, check=True, capture_output=True, timeout=30,
    ).stdout
    return commit, archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--installed", type=Path, help="Path to custom_components/load_optimizer")
    source.add_argument("--git-ref", help="Commit or tag in the local repository")
    source.add_argument("--release-archive", type=Path, help="Downloaded GitHub source tar.gz")
    parser.add_argument("--expect-sha256", help="Fail unless the package has this SHA-256 digest")
    args = parser.parse_args()
    if args.expect_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", args.expect_sha256):
        parser.error("--expect-sha256 must be a 64-digit SHA-256 digest")
    try:
        if args.installed is not None:
            result = fingerprint(installed_files(args.installed))
        elif args.release_archive is not None:
            result = fingerprint(release_archive_files(args.release_archive))
        else:
            commit, archive = archived_package(args.git_ref)
            result = {**fingerprint(archive_files(archive)), "commit": commit}
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Cannot identify package ({type(error).__name__}).\n")
    if args.expect_sha256 is not None and result["sha256"] != args.expect_sha256.lower():
        parser.exit(1, "Package digest does not match the expected SHA-256.\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

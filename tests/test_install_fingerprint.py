"""Package identity checks must detect local patches even at the same version."""

import io
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest

from dev.fingerprint_install import PACKAGE, archive_files, fingerprint, installed_files, release_archive_files


FILES = {
    "manifest.json": json.dumps({"domain": "load_optimizer", "version": "1.5.9"}).encode(),
    "__init__.py": b"startup",
    "legacy/app_runtime.py": b"engine",
    "frontend/chart.js": b"chart",
}


class InstallFingerprintTests(unittest.TestCase):
    def test_digest_is_compatible_with_sorted_sha256sum_output(self):
        stream = "".join(f"{sha256(content).hexdigest()}  ./{name}\n"
                         for name, content in sorted(FILES.items())).encode("ascii")
        self.assertEqual(fingerprint(FILES.items())["sha256"], sha256(stream).hexdigest())
        with self.assertRaisesRegex(ValueError, "Unsupported package file name"):
            fingerprint((*FILES.items(), ("unexpected\nfile", b"data")))

    def test_archive_and_installed_tree_agree_until_locally_patched(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name, content in FILES.items():
                entry = tarfile.TarInfo(str(PACKAGE / name))
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
        expected = fingerprint(archive_files(buffer.getvalue()))
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for name, content in reversed(list(FILES.items())):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            (root / "__pycache__").mkdir()
            (root / "__pycache__/ignored.pyc").write_bytes(b"ignored")
            self.assertEqual(fingerprint(installed_files(root)), expected)

            (root / "frontend/chart.js").write_bytes(b"patched")
            patched = fingerprint(installed_files(root))
            self.assertEqual(patched["manifest_version"], expected["manifest_version"])
            self.assertNotEqual(patched["sha256"], expected["sha256"])
            (root / "frontend/chart.js").write_bytes(FILES["frontend/chart.js"])
            (root / "extra.py").write_bytes(b"extra")
            self.assertNotEqual(fingerprint(installed_files(root))["sha256"], expected["sha256"])

    def test_missing_or_duplicate_files_cannot_be_verified(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            fingerprint((item for item in FILES.items() if item[0] != "__init__.py"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            fingerprint((*FILES.items(), ("__init__.py", b"duplicate")))

    def test_installed_symlinks_are_not_followed(self):
        with TemporaryDirectory() as folder:
            root = Path(folder) / "load_optimizer"
            root.mkdir()
            outside = root.parent / "other_file"
            outside.write_bytes(b"not part of the package")
            (root / "local.py").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "Unexpected link"):
                list(installed_files(root))

    def test_non_regular_archive_members_are_not_read(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            entry = tarfile.TarInfo(str(PACKAGE / "__init__.py"))
            entry.type = tarfile.SYMTYPE
            entry.linkname = "other_file"
            archive.addfile(entry)
        with self.assertRaisesRegex(ValueError, "Unexpected archive entry"):
            list(archive_files(buffer.getvalue()))

    def test_github_archive_matches_only_its_integration_files(self):
        wrapper = Path("repository-1.5.9")
        with TemporaryDirectory() as folder:
            path = Path(folder) / "beta.tar.gz"
            files = {f"{wrapper}/{PACKAGE}/{name}": content for name, content in FILES.items()}
            files[f"{wrapper}/README.md"] = b"Not an installed file"
            with tarfile.open(path, mode="w:gz") as archive:
                for name, content in files.items():
                    entry = tarfile.TarInfo(name)
                    entry.size = len(content)
                    archive.addfile(entry, io.BytesIO(content))
            self.assertEqual(fingerprint(release_archive_files(path)), fingerprint(FILES.items()))

            tool = Path(__file__).resolve().parents[1] / "dev" / "fingerprint_install.py"
            command = [sys.executable, "-B", str(tool), "--release-archive", str(path), "--expect-sha256"]
            expected = fingerprint(FILES.items())
            matched = subprocess.run([*command, expected["sha256"]], capture_output=True, check=True, text=True)
            self.assertEqual(json.loads(matched.stdout), expected)
            mismatch = subprocess.run([*command, "0" * 64], capture_output=True, check=False, text=True)
            self.assertEqual(mismatch.returncode, 1)
            self.assertIn("does not match", mismatch.stderr)

    def test_github_archive_rejects_multiple_package_roots(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "beta.tar.gz"
            with tarfile.open(path, mode="w:gz") as archive:
                for root in ("first", "second"):
                    archive.addfile(tarfile.TarInfo(f"{root}/{PACKAGE}/__init__.py"))
            with self.assertRaisesRegex(ValueError, "Unexpected release archive root"):
                list(release_archive_files(path))

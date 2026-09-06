"""Locked SM83 acquisition rejects substituted network and cache content."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("cpu_vectors", ROOT / "src/dv/cpu/generate_vectors.py")
vectors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vectors)


class LockedVectorSourceTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/vector-source-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name)

    def test_network_substitution_is_not_published(self):
        with patch.object(vectors.urllib.request, "urlopen", return_value=io.BytesIO(b"substituted")) as request:
            with self.assertRaisesRegex(ValueError, "downloaded source archive integrity"):
                vectors.fetch(self.cache)
        request.assert_called_once_with(vectors.URL, timeout=60)
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assertTrue(vectors.URL.endswith(vectors.PIN))
        self.assertEqual(len(vectors.PIN), 40)

    def test_named_cache_is_verified_without_network_fallback(self):
        cached = self.cache / f"{vectors.PIN}.zip"
        cached.write_bytes(b"wrong cache")
        with patch.object(vectors.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "cached source archive integrity"):
                vectors.fetch(self.cache)
        request.assert_not_called()
        self.assertEqual(cached.read_bytes(), b"wrong cache")

    def test_verified_download_then_offline_cache(self):
        # A tiny transport fixture tests publication; actual pinned archive
        # reproducibility is a separate retained generator --fetch --check run.
        payload = b"transport fixture"
        with patch.object(vectors, "ARCHIVE_SHA256", hashlib.sha256(payload).hexdigest()):
            with patch.object(vectors.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
                path = vectors.fetch(self.cache)
            with patch.object(vectors.urllib.request, "urlopen") as request:
                self.assertEqual(vectors.fetch(self.cache), path)
                request.assert_not_called()
        self.assertEqual(path.read_bytes(), payload)

    def test_interrupted_download_leaves_no_usable_archive(self):
        with patch.object(vectors.urllib.request, "urlopen", side_effect=TimeoutError("interrupted")):
            with self.assertRaises(TimeoutError):
                vectors.fetch(self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

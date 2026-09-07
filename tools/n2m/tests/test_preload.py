"""The preload accepts exact pipeline bytes and rejects mismatched artifacts."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.preload import prepare
from sw.package import package

ROOT = Path(__file__).resolve().parents[3]


class PreloadTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'workdir/builds/preload-unit'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='preload space ', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name)
        self.image = package({'image': bytes([255]) * 32768, 'entry': 0x200}, 'PRELOAD TEST', 1)
        self.digest = hashlib.sha256(self.image).hexdigest()

    def test_exact_image_and_intel_files(self):
        record = prepare(self.image, self.digest, self.destination)
        self.assertEqual(record['image_sha256'], self.digest)
        rows = (self.destination / 'preload-rom.mif').read_text().splitlines()[5:-1]
        recovered = bytes(int(row.split(':')[1].strip(' ;'), 16) for row in rows)
        self.assertEqual(recovered, self.image)
        self.assertEqual(len(rows), 32768)
        self.assertIn('[0000..7FFF] : 1;', (self.destination / 'preload-presence.mif').read_text())

    def test_rejects_hash_and_size_before_publication(self):
        for image, digest in ((self.image, '0' * 64), (self.image[:-1], self.digest),
                              (self.image, 'bad')):
            with self.subTest(size=len(image), digest=digest):
                with self.assertRaises(ValueError):
                    prepare(image, digest, self.destination)
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_rejects_invalid_header_even_with_matching_hash(self):
        image = bytearray(self.image)
        image[0x147] = 1
        image = bytes(image)
        with self.assertRaises(Exception):
            prepare(image, hashlib.sha256(image).hexdigest(), self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

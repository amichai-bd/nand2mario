"""Generated Springtrail column table: committed output, corruption and regeneration."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sw import columns
from sw.expressions import AssemblyError
ROOT = Path(__file__).resolve().parents[3]


class ColumnTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'workdir/builds/columns-unit'; parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='space ', dir=parent); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        (self.root / columns.TREE).mkdir(parents=True)
        for name in (columns.WORLD, columns.COLUMNS):
            shutil.copy(ROOT / name, self.root / name)

    def failure(self, **edits):
        for name, text in edits.items():
            (self.root / getattr(columns, name)).write_text(text, encoding='utf-8')
        with self.assertRaises(AssemblyError) as caught:
            columns.validate(self.root)
        return caught.exception.diagnostic

    def test_committed_table_is_generated_from_world(self):
        world = columns.load_world((ROOT / columns.WORLD).read_text(encoding='utf-8'))
        self.assertEqual(columns.render(world), (ROOT / columns.COLUMNS).read_text(encoding='utf-8'))
        decoded = columns.validate(ROOT)
        self.assertEqual(len(decoded), 96)
        self.assertTrue(all(decoded[x][y] == world[y + 2][x] for x in range(96) for y in range(16)))

    def test_encoding_round_trips_and_bounds_runs(self):
        self.assertEqual(columns.encode([0] * 14 + [11] * 2), [14, 0, 2, 11, 0])
        self.assertEqual(columns.encode([5] * 16), [16, 5, 0])
        for column in ([0, 1] * 8, list(range(16)), [11] * 16):
            self.assertEqual(columns.decode(columns.encode(column)), column)
        self.assertEqual(len(columns.encode(list(range(16)))), 33)
        with self.assertRaises(AssemblyError):
            columns.decode([16, 0, 1, 0, 0])
        with self.assertRaises(AssemblyError):
            columns.encode([94] * 16)

    def test_changed_world_tile_fails_stale(self):
        text = (ROOT / columns.WORLD).read_text(encoding='utf-8')
        rows = text.split('DB ')
        # Row 12 (index 12 in the 18 DB rows) column 10 is solid; clear it.
        target = 1 + 12
        values = rows[target].rstrip('\n').split(','); self.assertEqual(values[10], '11'); values[10] = '0'
        rows[target] = ','.join(values) + '\n'
        diagnostic = self.failure(WORLD='DB '.join(rows))
        self.assertEqual(diagnostic['code'], 'COLUMN_STALE')
        self.assertEqual(diagnostic['span'], {'file': 'springtrail/columns.asm', 'line': 3 + 96 + 2 * 10 + 2, 'column': 1})
        self.assertIn('run python tools/sw/columns.py', diagnostic['cause'])

    def test_corrupt_table_line_fails_stale(self):
        text = (ROOT / columns.COLUMNS).read_text(encoding='utf-8')
        corrupted = text.replace('DisplayColumn50:\nDB 14,0,2,11,0', 'DisplayColumn50:\nDB 13,0,3,11,0')
        self.assertNotEqual(corrupted, text)
        diagnostic = self.failure(COLUMNS=corrupted)
        self.assertEqual((diagnostic['code'], diagnostic['span']['line']), ('COLUMN_STALE', 3 + 96 + 2 * 50 + 2))
        for broken in (text.replace('DW DisplayColumn95\n', ''), text + 'DB 0\n', text.rstrip('\n'), ''):
            self.assertEqual(self.failure(COLUMNS=broken)['code'], 'COLUMN_STALE')

    def test_malformed_world_fails_world(self):
        text = (ROOT / columns.WORLD).read_text(encoding='utf-8')
        lines = text.splitlines(keepends=True)
        for broken in (''.join(lines[:-1]), text.replace('DB 11,11', 'DB 11,94', 1), text.replace('DB 0,0', 'DB x,0', 1),
                       text.replace('DB 11,11,', 'DB 11,', 1)):
            self.assertEqual(self.failure(WORLD=broken)['code'], 'COLUMN_WORLD')

    def test_regeneration_restores_committed_bytes_and_line_endings(self):
        path = self.root / columns.COLUMNS
        original = path.read_bytes()
        crlf = b'\r\n' in original
        path.write_bytes(original.replace(b'DB 14,0,2,11,0', b'DB 1,0,15,0,0', 1))
        with self.assertRaises(AssemblyError):
            columns.generate(self.root, check=True)
        columns.generate(self.root)
        self.assertEqual(path.read_bytes(), original)
        path.write_bytes(original.replace(b'\r\n', b'\n') if crlf else original.replace(b'\n', b'\r\n'))
        columns.generate(self.root)
        self.assertEqual(path.read_bytes(), original.replace(b'\r\n', b'\n') if crlf else original.replace(b'\n', b'\r\n'))
        columns.generate(self.root, check=True)

    def test_script_entry_reports_pass_and_fail(self):
        self.assertIsNone(columns.main(['--check', '--root', str(self.root)]))
        (self.root / columns.COLUMNS).write_text('', encoding='utf-8')
        with self.assertRaises(SystemExit) as failed:
            columns.main(['--check', '--root', str(self.root)])
        self.assertEqual(failed.exception.code, 1)


if __name__ == '__main__':
    unittest.main()

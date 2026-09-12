"""Focused regressions for presentation and statistics documentation UX."""

from pathlib import Path
import unittest

from tools.wiki import repository_stats as stats
from tools.wiki.statistics_report import render


ROOT = Path(__file__).resolve().parents[2]


def minimal_source():
    source = dict(
        revision='a' * 40,
        totals=stats.sums([]),
        files=[],
        by_discipline={},
        by_extension={},
        by_top_directory={},
        skipped_nonregular=[],
        history=dict(
            reachable_commits=1,
            first_parent_commits=1,
            first_commit=None,
            last_commit=None,
            daily=[dict(date='2026-01-01', sha='a' * 40, commits=1)],
        ),
    )
    return source


class DocumentationQualityTests(unittest.TestCase):
    def test_presentation_runtime_keeps_deep_links_and_print_complete(self):
        javascript = (ROOT / 'tools/wiki/assets/presentation.js').read_text(encoding='utf-8')
        stylesheet = (ROOT / 'tools/wiki/assets/presentation.css').read_text(encoding='utf-8')

        self.assertIn('function indexFromFragment()', javascript)
        self.assertIn("window.addEventListener('hashchange'", javascript)
        self.assertIn('show(indexFromFragment());', javascript)

        print_rules = stylesheet.split('@media print', 1)[1]
        self.assertIn('[data-slide][hidden]', print_rules)
        self.assertIn('display: block', print_rules)
        self.assertIn('.deck-controls', print_rules)
        self.assertIn('display: none !important', print_rules)

    def test_animated_diagrams_gate_motion_and_stay_complete_without_it(self):
        stylesheet = (ROOT / 'wiki/presentations/assets/concepts.css').read_text(encoding='utf-8')
        decks = ('cpu-execution', 'graphics-pipeline', 'uart-debugging', 'springtrail-software')
        lessons = ('reproducible-builds', 'uart-debugging', 'verification')

        motion = stylesheet.split('@media screen and (prefers-reduced-motion: no-preference)', 1)
        self.assertEqual(len(motion), 2, 'Motion must be gated behind screen and no-preference')
        self.assertNotIn('animation:', motion[0], 'Animation outside the gate would run in print')
        for deck in decks:
            markup = (ROOT / f'wiki/presentations/{deck}.html').read_text(encoding='utf-8')
            self.assertIn('data-animated', markup, deck)
            self.assertNotIn('<animate', markup, deck)
            self.assertNotIn('opacity="0"', markup, deck)
            self.assertNotIn('<style', markup, deck)
        # A lesson terminal session is one generated SVG image inside a scroll
        # region; the deck adds no motion of its own to it.
        for deck in lessons:
            markup = (ROOT / f'wiki/presentations/{deck}.html').read_text(encoding='utf-8')
            self.assertEqual(markup.count('class="terminal-session"'), 1, deck)
            self.assertIn(f'<img class="terminal-session" src="../showcase/{deck}.svg" alt="', markup, deck)
            self.assertIn('data-scroll-region tabindex="0" role="region" aria-label="Terminal session:', markup, deck)

    def test_showcases_are_self_contained_and_match_their_generator(self):
        import posixpath
        from tools.wiki import showcase
        generated = showcase.documents()
        self.assertEqual(sorted(generated), sorted(showcase.EMBEDS))
        for name, page in showcase.EMBEDS.items():
            markup = (ROOT / f'wiki/showcase/{name}.svg').read_text(encoding='utf-8')
            self.assertEqual(markup, generated[name], f'{name}.svg differs from tools/wiki/showcase.py output')
            link = posixpath.relpath(f'wiki/showcase/{name}.svg', posixpath.dirname(page))
            self.assertIn(link, (ROOT / page).read_text(encoding='utf-8'), f'{page} does not embed {name}.svg')
            forbidden = ['<script', '<foreignObject', 'url(', '<animate', '@import']
            # A board loop embeds each captured frame as an indexed-PNG data
            # URI, measured in tools/wiki/board_frames.py as two orders of
            # magnitude smaller than the rect runs paths() draws. That is still
            # self-contained: no href may name anything but inline PNG data.
            if name in showcase.BOARD_LOOPS:
                self.assertEqual(markup.count('href="'), markup.count('href="data:image/png;base64,'), name)
            else:
                forbidden.append('href=')
            for token in forbidden:
                self.assertNotIn(token, markup, name)
            gate = markup.split('@media (prefers-reduced-motion:no-preference){', 1)
            self.assertEqual(len(gate), 2, 'Motion must be gated behind no-preference')
            self.assertNotIn('animation:', gate[0], 'Animation outside the gate would ignore reduced motion')

    def test_board_loops_declare_their_capture_sessions(self):
        """Each board loop names where its frames came from, and holds only frames."""
        from tools.wiki import board_frames, showcase
        for name in showcase.BOARD_LOOPS:
            archive = board_frames.load(name)
            provenance, encoding = archive['provenance'], archive['encoding']
            for field in ('note', 'program', 'driver', 'command', 'checked', 'wire_build_id'):
                self.assertTrue(str(provenance.get(field, '')).strip(), f'{name}: {field}')
            self.assertEqual(encoding['chosen'], 'indexed-png-data-uri', name)
            self.assertLess(encoding['bytes_indexed_png'], encoding['bytes_path_runs'], name)
            self.assertEqual(encoding['frames'], len(archive['frames']), name)
            for frame in archive['frames']:
                self.assertTrue(frame['png'].startswith('data:image/png;base64,'), name)
                self.assertRegex(frame['crc32'], r'^[0-9a-f]{8}$')
                self.assertIn(frame['mask'], range(256), name)
            seqs = [frame['seq'] for frame in archive['frames']]
            self.assertEqual(seqs, sorted(seqs), f'{name}: frames must be in capture order')
            # Every frame the archive holds is drawn, and the last one is the
            # authored still a reduced-motion reader sees.
            markup = (ROOT / f'wiki/showcase/{name}.svg').read_text(encoding='utf-8')
            for index, frame in enumerate(archive['frames']):
                self.assertIn(f'class="f{index}" opacity="{1 if index == len(seqs) - 1 else 0}"', markup)
                self.assertIn(frame['png'], markup, f'{name}: frame {index} is not drawn')

    def test_statistics_renderer_marks_snapshot_and_links_back_to_docs(self):
        html = render(minimal_source())

        self.assertIn('Frozen manual snapshot.', html)
        self.assertIn('href="index.md"', html)
        self.assertIn('href="presentations/README.md"', html)
        self.assertIn('href="project-statistics.md"', html)
        self.assertIn('class="chart-scroll"', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<link', html)


if __name__ == '__main__':
    unittest.main()

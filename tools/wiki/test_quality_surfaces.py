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

        motion = stylesheet.split('@media screen and (prefers-reduced-motion: no-preference)', 1)
        self.assertEqual(len(motion), 2, 'Motion must be gated behind screen and no-preference')
        self.assertNotIn('animation:', motion[0], 'Animation outside the gate would run in print')
        for deck in decks:
            markup = (ROOT / f'wiki/presentations/{deck}.html').read_text(encoding='utf-8')
            self.assertIn('data-animated', markup, deck)
            self.assertNotIn('<animate', markup, deck)
            self.assertNotIn('opacity="0"', markup, deck)
            self.assertNotIn('<style', markup, deck)

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

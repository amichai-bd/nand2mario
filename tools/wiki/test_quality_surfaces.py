"""Focused regressions for presentation and statistics documentation UX."""

from pathlib import Path
import re
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
            if name in showcase.BOARD_FRAME_SURFACES:
                self.assertEqual(markup.count('href="'), markup.count('href="data:image/png;base64,'), name)
            else:
                forbidden.append('href=')
            for token in forbidden:
                self.assertNotIn(token, markup, name)
            gate = markup.split('@media (prefers-reduced-motion:no-preference){', 1)
            self.assertEqual(len(gate), 2, 'Motion must be gated behind no-preference')
            self.assertNotIn('animation:', gate[0], 'Animation outside the gate would ignore reduced motion')

    def test_board_loops_declare_their_capture_sessions(self):
        """Each board surface names where its frames came from, and holds only frames."""
        from tools.wiki import board_frames, showcase
        for name in showcase.BOARD_ARCHIVE_SURFACES:
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
            # Every frame the archive holds is drawn. In a flipbook the last one
            # is the authored still a reduced-motion reader sees; a homebrew
            # panel is already a still, so every frame stays visible.
            markup = (ROOT / f'wiki/showcase/{name}.svg').read_text(encoding='utf-8')
            visible = len(seqs) - 1 if name in showcase.BOARD_LOOPS else None
            for index, frame in enumerate(archive['frames']):
                shown = 1 if visible is None or index == visible else 0
                self.assertIn(f'class="f{index}" opacity="{shown}"', markup)
                self.assertIn(frame['png'], markup, f'{name}: frame {index} is not drawn')

    def test_games_gallery_draws_archived_frames_and_reads_its_credits(self):
        """The landing page gallery adds no pixels and retypes no metadata."""
        from tools.wiki import board_frames, showcase
        markup = (ROOT / 'wiki/showcase/games-gallery.svg').read_text(encoding='utf-8')
        pins = showcase.pinned_images()
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        drawn = 0
        for position, (archive_name, pin, chosen) in enumerate(showcase.GALLERY_GAMES):
            self.assertIn(archive_name, showcase.BOARD_ARCHIVE_SURFACES, archive_name)
            frames = board_frames.load(archive_name)['frames']
            for index, source in enumerate(chosen):
                # Every pixel comes from a committed archive, none from here.
                self.assertIn(frames[source]['png'], markup, f'{archive_name} frame {source}')
                shown = 1 if index == len(chosen) - 1 else 0
                self.assertIn(f'class="t{position}f{index}" opacity="{shown}"', markup)
                drawn += 1
            if pin:
                # Author and licence are read from the manifest, and stay out of
                # the README, which links the library page instead.
                for field in ('name', 'author', 'license'):
                    self.assertIn(pins[pin][field], markup, f'{pin}: {field}')
                    self.assertNotIn(pins[pin][field], readme, f'{pin}: {field} retyped into the README')
        self.assertEqual(markup.count('<image '), drawn)
        # The two pinned images that never draw are named where the tiles are,
        # and their metadata stays out of the README with every other pin's.
        for pin in ('wyrmhole', 'rex-run'):
            for field in ('author', 'license'):
                self.assertNotIn(pins[pin][field], readme, f'{pin}: {field} retyped into the README')
        for game in ('Wyrmhole', 'Rex Run'):
            self.assertIn(game, markup)
        # Nine tiles are still not the whole set, and the gallery says so itself.
        self.assertIn('Stackdrop', markup)
        self.assertNotIn('Eight Game Boy games run on this hardware', readme)
        # Nine tiles fill the grid and push the note into a band of its own, so
        # nothing may overlap the footer rows anchored to the bottom.
        height = int(re.search(r'height="(\d+)" viewBox', markup).group(1))
        baselines = sorted(int(y) for y in re.findall(r'<text[^>]*y="(\d+)"', markup))
        footer_top = height - 12 - 2 * showcase.LINE
        self.assertLess(max(y for y in baselines if y < footer_top) + showcase.LINE, footer_top)
        self.assertLess(max(baselines), height)
        self.assertIn('not emulator screenshots', markup)
        self.assertIn('homebrew-library.md#wyrmhole-and-rex-run-never-turn-the-lcd-on', readme)

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

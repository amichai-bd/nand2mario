"""Exercise the generated wiki with owned Chromium and a loopback server."""

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
from threading import Thread

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'workdir/wiki/browser'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


@contextmanager
def session(executable=None):
    """Close resources in reverse order, including when an assertion raises."""
    handler = partial(QuietHandler, directory=str(ROOT / 'workdir/wiki/site'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=executable)
            try:
                yield browser, f'http://127.0.0.1:{server.server_port}'
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Owned server thread did not stop'
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(('127.0.0.1', server.server_port)) != 0, 'Owned port still listens'


def interactions(browser, base):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    context.tracing.start(screenshots=True, snapshots=True)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    # Browsers request a favicon even though it is not a wiki asset.
    page.route('**/favicon.ico', lambda route: route.fulfill(status=204))
    try:
        page.goto(base)
        expect(page.locator('#path')).to_have_text('README.md')
        page.locator('[data-home="AGENTS.md"]').click()
        expect(page.locator('#path')).to_have_text('AGENTS.md')
        expect(page.locator('[data-home="AGENTS.md"]')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#document')).to_contain_text('Agent rules')
        page.locator('[data-home="README.md"]').click()
        expect(page.locator('#path')).to_have_text('README.md')
        for category in ('Src', 'Agents/Skills', 'Tools', 'Presentations', 'Home'):
            page.locator('#tabs').get_by_role('button', name=category, exact=True).click()
            expect(page.locator('#tabs [aria-current="page"]')).to_have_text(category)
            expect(page.locator('#tree a').first).to_be_visible()
        page.locator('#tabs').get_by_role('button', name='Cfg', exact=True).click()
        expect(page.locator('#path')).to_have_text('wiki/cfg/interfaces.md')
        expect(page.locator('#document')).to_contain_text('DO NOT EDIT')
        expect(page.locator('#document table').first).to_be_visible()
        expect(page.locator('#document')).to_contain_text('GB_ADDRESS_BITS')
        page.screenshot(path=str(OUTPUT / 'interface-tables.png'), full_page=False)
        page.locator('#document').get_by_role('link', name='interface contracts', exact=True).click()
        expect(page.locator('#path')).to_have_text('wiki/src/rtl/interfaces/MAS_interfaces.md')
        expect(page.locator('#document')).to_contain_text('This shared interface contract governs RTL, host software, and verification')
        page.screenshot(path=str(OUTPUT / 'interface-contract.png'), full_page=False)
        page.locator('#document').get_by_role('link', name='generator specification', exact=True).click()
        expect(page.locator('#path')).to_have_text('wiki/tools/n2m/SPEC.md')
        expect(page.locator('#interface-generation')).to_be_in_viewport()
        page.locator('#tabs').get_by_role('button', name='Src', exact=True).click()
        page.locator('#filter').fill('project-charter.md')
        expect(page.locator('#tree a')).to_have_count(1)
        page.locator('#tree a').click()
        expect(page.locator('#path')).to_have_text('wiki/src/project-charter.md')
        page.locator('#source').click()
        expect(page.locator('#source-dialog')).to_be_visible()
        expect(page.locator('#source-title')).to_have_text('wiki/src/project-charter.md')
        expect(page.locator('#source-lines')).to_contain_text('DMG')
        page.locator('#close-source').click()

        page.goto(base + '/?page=wiki/presentations/scaffold-tour.html')
        frame = page.frame_locator('#document iframe')
        expect(frame.locator('.deck.is-ready')).to_be_visible()
        frame.get_by_role('button', name='Next', exact=True).press('Enter')
        expect(frame.locator('[data-progress]')).to_have_text('2 / 3')
        source_link = frame.get_by_role('link', name='Inspect src/rtl/README.md')
        expect(source_link).to_have_attribute('href', 'https://github.com/amichai-bd/nand2mario/blob/main/src/rtl/README.md#L1')
        expect(source_link).to_have_attribute('target', '_blank')
        expect(frame.locator('[data-source]')).to_have_count(0)
        context.route('https://github.com/amichai-bd/nand2mario/blob/main/src/rtl/README.md*', lambda route: route.fulfill(status=200, body='Repository source'))
        with context.expect_page() as opened:
            source_link.click()
        popup = opened.value
        expect(popup).to_have_url('https://github.com/amichai-bd/nand2mario/blob/main/src/rtl/README.md#L1')
        popup.close()
        standalone = context.new_page()
        standalone.goto(base + '/files/wiki/presentations/scaffold-tour.html')
        standalone.get_by_role('button', name='Next', exact=True).click()
        expect(standalone.get_by_role('link', name='Inspect src/rtl/README.md')).to_have_attribute('href', 'https://github.com/amichai-bd/nand2mario/blob/main/src/rtl/README.md#L1')
        standalone.close()
        expect(page.locator('#source-dialog')).not_to_be_visible()
        frame.get_by_role('button', name='Previous', exact=True).focus()
        page.keyboard.press('Home')
        expect(frame.locator('[data-progress]')).to_have_text('1 / 3')
        page.keyboard.press('End')
        expect(frame.locator('[data-progress]')).to_have_text('3 / 3')
        fullscreen = 'unsupported'
        if page.evaluate('document.fullscreenEnabled'):
            page.locator('#fullscreen').click()
            page.wait_for_function('document.fullscreenElement?.id === "stage"')
            frame.get_by_role('button', name='Previous', exact=True).press('Enter')
            expect(frame.locator('[data-progress]')).to_have_text('2 / 3')
            expect(source_link).to_be_visible()
            expect(page.locator('#source-dialog')).not_to_be_visible()
            page.locator('#fullscreen').click()
            page.wait_for_function('!document.fullscreenElement')
            frame.get_by_role('button', name='Next', exact=True).press('Enter')
            expect(frame.locator('[data-progress]')).to_have_text('3 / 3')
            fullscreen = 'passed'
        else:
            print('Fullscreen unsupported by this browser; other interactions remain required.')
        frame.get_by_role('link', name='Read the presentation contract').click()
        expect(page.locator('#path')).to_have_text('wiki/presentations/README.md')

        # Longer educational slides must grow instead of covering source links
        # with their controls; scrolling diagrams retain native keyboard input.
        page.goto(base + '/?page=wiki/presentations/cpu-execution.html')
        frame = page.frame_locator('#document iframe')
        frame.get_by_role('button', name='Next', exact=True).click()
        frame.get_by_role('link', name='Source: Time, bus and retirement').click()
        expect(page.locator('#source-title')).to_have_text('wiki/src/rtl/cpu/MAS_cpu.md')
        expect(page.locator('#source-lines .selected')).to_contain_text('## Time, bus and retirement')
        page.locator('#close-source').click()
        page.goto(base + '/files/wiki/presentations/cpu-execution.html')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.get_by_role('button', name='Next', exact=True).click()
        region = page.locator('[data-scroll-region]')
        region.focus()
        page.keyboard.press('ArrowRight')
        page.wait_for_function('document.querySelector("[data-scroll-region]").scrollLeft > 0')
        expect(page.locator('[data-progress]')).to_have_text('2 / 6')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Deck causes page overflow'
        page.locator('[data-slide]:not([hidden]) summary').click()
        source_bottom = page.locator('[data-slide]:not([hidden]) .sources').evaluate('e => e.getBoundingClientRect().bottom')
        controls_top = page.locator('.deck-controls').evaluate('e => e.getBoundingClientRect().top')
        assert source_bottom < controls_top, 'Expanded reasoning overlaps controls'
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.goto(base + '/?page=wiki/presentations/README.md')

        page.screenshot(path=str(OUTPUT / 'documentation.png'), full_page=True)
        page.goto(base + '/?page=wiki/src/dv/baseline/SPEC.md')
        expect(page.locator('#document')).to_contain_text('Harness boundaries')
        expect(page.locator('#document')).to_contain_text('Future adapter plans')
        page.screenshot(path=str(OUTPUT / 'verification-baseline.png'))
        page.goto(base + '/?page=src/rtl/README.md')
        expect(page.locator('#document')).to_have_text('Document not found: src/rtl/README.md')
        expect(page.locator('#source')).to_be_disabled()
        page.goto(base + '/?page=missing.md')
        expect(page.locator('#document')).to_have_text('Document not found: missing.md')
        expect(page.locator('#source')).to_be_disabled()
        page.locator('#tabs').get_by_role('button', name='Home', exact=True).click()
        expect(page.locator('#path')).to_have_text('README.md')
        expect(page.locator('#source')).to_be_enabled()
        expect(page.locator('#document')).not_to_have_class('error')
        assert not errors, '\n'.join(errors)
        return {'fullscreen': fullscreen}
    except BaseException:
        page.screenshot(path=str(OUTPUT / 'failure.png'), full_page=True)
        raise
    finally:
        context.tracing.stop(path=str(OUTPUT / 'trace.zip'))
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ('failure.png', 'trace.zip'):
        (OUTPUT / name).unlink(missing_ok=True)
    report = {'status': 'running', 'executable': args.browser_executable or 'pinned Chromium'}
    # Exercise the same cleanup path after a forced test failure.
    class ProbeFailure(Exception):
        pass
    try:
        try:
            with session(args.browser_executable) as (probe, _):
                raise ProbeFailure()
        except ProbeFailure:
            assert not probe.is_connected(), 'Browser remained connected after failure'
        with session(args.browser_executable) as (browser, base):
            report['browser'] = browser.version
            report.update(interactions(browser, base))
        assert not browser.is_connected(), 'Browser remained connected after success'
        report.update(status='passed', cleanup='success and failure')
        print(f'Browser interactions and cleanup passed (Chromium {browser.version}).')
    except BaseException:
        report['status'] = 'failed'
        raise
    finally:
        (OUTPUT / 'result.json').write_text(json.dumps(report), encoding='utf-8')


if __name__ == '__main__':
    main()

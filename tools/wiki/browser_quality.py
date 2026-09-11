"""Browser regressions for slide fragments, animated and printable diagrams, and chart layout."""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'workdir/wiki/browser'
sys.path.insert(0, str(ROOT / 'tools'))
from n2m import generated_interfaces as abi, interface_codec as codec  # noqa: E402


def step_frame():
    """The COBS frame the codec produces for the STEP request drawn on the UART slide."""
    frame = codec.encode_packet(7, abi.COMMAND_STEP, codec.pack_record('word', {'value': 24}))
    return frame.hex(' ').upper()


def placement(figure, selector):
    """Horizontal centre of a diagram part, as a fraction of the diagram width."""
    return figure.evaluate("""(svg, selector) => {
        const frame = svg.getBoundingClientRect();
        const part = svg.querySelector(selector).getBoundingClientRect();
        return (part.left + part.width / 2 - frame.left) / frame.width;
    }""", selector)


def check_views(browser, base):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    context.tracing.start(screenshots=True, snapshots=True)
    context.route('**/favicon.ico', lambda route: route.fulfill(status=204))
    errors = []
    page = None

    def new_page():
        view = context.new_page()
        view.on('pageerror', lambda error: errors.append(str(error)))
        view.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        return view

    try:
        for name, count in (('cpu-execution', 6), ('scaffold-tour', 3)):
            page = new_page()
            # Heading IDs differ between the series and scaffold; both are valid.
            path = f'/files/wiki/presentations/{name}.html'
            page.goto(base + path)
            headings = page.locator('[data-slide] h1, [data-slide] h2')
            target = headings.nth(1).get_attribute('id')
            page.evaluate('id => { location.hash = id; }', target)
            expect(page.locator('[data-progress]')).to_have_text(f'2 / {count}')
            page.get_by_role('button', name='Previous', exact=True).click()
            expect(page.locator('[data-progress]')).to_have_text(f'1 / {count}')
            page.get_by_role('button', name='Next', exact=True).focus()
            page.keyboard.press('End')
            expect(page.locator('[data-progress]')).to_have_text(f'{count} / {count}')
            page.evaluate("location.hash = '#%E0%A4%A'")
            expect(page.locator('[data-progress]')).to_have_text(f'1 / {count}')
            page.evaluate("document.querySelectorAll('[data-slide]')[1].id = 'section-target'; location.hash = '#section-target'")
            expect(page.locator('[data-progress]')).to_have_text(f'2 / {count}')
            page.emulate_media(media='print')
            expect(page.locator('[data-slide]:visible')).to_have_count(count)
            expect(page.locator('.deck-controls')).not_to_be_visible()
            for slide in page.locator('[data-slide]').all():
                expect(slide).to_have_css('min-height', '0px')
            if name == 'cpu-execution':
                # Diagram text must not inherit the pale screen palette on white paper.
                expect(page.locator('svg text').first).to_have_css('fill', 'rgb(17, 17, 17)')
                page.screenshot(path=str(OUTPUT / 'quality-print.png'))
            page.emulate_media(media='screen')
            expect(page.locator('[data-slide]:visible')).to_have_count(1)
            page.close()

        page = new_page()
        page.goto(base + '/files/wiki/presentations/uart-debugging.html#slide-1')
        figure = page.locator('[data-animated]').first
        expect(figure).to_be_visible()
        request, ack = figure.locator('.uart-request'), figure.locator('.uart-ack')
        assert request.evaluate('e => getComputedStyle(e).animationName') == 'n2m-uart-request'
        assert ack.evaluate('e => getComputedStyle(e).animationName') == 'n2m-uart-ack'
        # Suppressed motion must leave the arrived packet and its returned reply, not a mid-flight frame.
        page.emulate_media(reduced_motion='reduce')
        for part in (request, ack, figure.locator('.uart-check')):
            assert part.evaluate('e => getComputedStyle(e).animationName') == 'none'
            expect(part).to_be_visible()
        assert placement(figure, '.uart-request') > 0.55, 'Request packet did not reach the endpoint'
        assert placement(figure, '.uart-ack') < 0.45, 'Reply did not return to the host'
        expect(figure).to_contain_text('CRC-16 matched')
        # The drawn frame must be the codec's own STEP output, delimiter included.
        expect(figure).to_contain_text(step_frame()[:-3])
        expect(figure).to_contain_text(step_frame()[-2:])
        # Diagram text must not inherit the pale screen palette on white paper.
        page.emulate_media(media='print')
        expect(figure.locator('text').first).to_have_css('fill', 'rgb(17, 17, 17)')
        expect(figure.locator('.tiny').first).to_have_css('fill', 'rgb(68, 68, 68)')
        assert request.evaluate('e => getComputedStyle(e).animationName') == 'none'
        page.screenshot(path=str(OUTPUT / 'quality-animated-print.png'), full_page=True)
        page.close()

        for fragment, expected in (('#slide-4', '4 / 6'), ('#missing', '1 / 6'), ('#%E0%A4%A', '1 / 6')):
            page = new_page()
            page.goto(base + '/files/wiki/presentations/cpu-execution.html' + fragment)
            expect(page.locator('[data-progress]')).to_have_text(expected)
            page.close()

        for width in (1440, 390):
            page = new_page()
            page.set_viewport_size({'width': width, 'height': 844})
            page.goto(base + '/files/wiki/statistics.html')
            expect(page.locator('.snapshot')).to_contain_text('Frozen manual snapshot.')
            expect(page.get_by_role('navigation', name='Project documentation')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Statistics page overflows'
            plot = page.locator('.chart-scroll').first
            expect(plot).to_have_attribute('tabindex', '0')
            expect(plot).to_have_attribute('role', 'region')
            if width == 390:
                assert plot.evaluate('e => e.scrollWidth > e.clientWidth'), 'Chart shrank instead of scrolling'
                plot.focus()
                page.keyboard.press('ArrowRight')
                page.wait_for_function("document.querySelector('.chart-scroll').scrollLeft > 0")
            page.screenshot(path=str(OUTPUT / f'quality-statistics-{width}.png'))
            page.emulate_media(media='print')
            expect(plot.locator('svg')).to_have_css('min-width', '0px')
            page.close()
        assert not errors, '\n'.join(errors)
        return {'status': 'passed', 'browser': browser.version, 'viewports': [1440, 390],
                'checks': ['slide fragments', 'malformed fragments', 'keyboard', 'print visibility and contrast', 'animated diagram motion, completeness and print contrast', 'chart scrolling']}
    except BaseException:
        if page is not None and not page.is_closed():
            page.screenshot(path=str(OUTPUT / 'failure.png'), full_page=True)
        raise
    finally:
        context.tracing.stop(path=str(OUTPUT / 'quality-trace.zip'))
        context.close()


def main():
    from browser_tests import session
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {'status': 'failed'}
    try:
        with session(args.browser_executable) as (browser, base):
            result = check_views(browser, base)
        print(json.dumps(result))
    finally:
        (OUTPUT / 'quality-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

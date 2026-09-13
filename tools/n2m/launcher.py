"""One window that lists every game this board can run, loads the chosen one and plays it.

The launcher is the host entry point for playing on this hardware: pick a game,
watch it load, then play it on the board's own VGA output through the pad this
module reuses rather than reimplements. There is exactly one UART session for
the whole window, so the load and the play are the same owner.

The catalogue is read from the manifests that already hold these facts —
`tools/n2m/dependencies.json` for the pinned external images and
`src/sw/targets.json` for the two built here — so no author, licence or pin name
is retyped in this source and the window cannot drift from the pins.

As in the pad, the logic lives apart from the widgets: `Launcher`, `BootWatch`
and `explain` need no display and are tested headless against a fake endpoint.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

from . import generated_interfaces as abi
from .gui_pad import (Driver, ESCAPE, FACE, HELD, IDLE, KEY, PANEL, PadPanel, TEXT,
                      explain_conflict, own_session, preflight)
from .host.external import read_external
from .host.package import read_package

PIN_FILE = 'tools/n2m/dependencies.json'
TARGET_FILE = 'src/sw/targets.json'
# The two games built from source here, in the order the menu shows them.
SOURCE_TARGETS = ('stackdrop', 'springtrail')
# One fixed tag, so `sw build`'s own fingerprint cache reuses the current
# attempt instead of relinking unchanged sources on every selection.
BUILD_TAG = 'gb-launcher-sw'
LIBRARY = 'wiki/showcase/homebrew-library.md#wyrmhole-and-rex-run-never-turn-the-lcd-on'
BLANK_REASON = ('Waits for the LCD before enabling it, so it never draws: `dmg-direct-v1` '
                'has no boot ROM and starts with the LCD off.')
# Known not to boot on this hardware, with the disassembly in the library page.
BLANK = {'wyrmhole': BLANK_REASON, 'rex-run': BLANK_REASON}
# How long a started game may leave the LCD off before the window says so.
BOOT_GRACE = 4.0
LCD_ENABLE = 0x80


class LauncherError(RuntimeError):
    """A failure already phrased for someone who wants to play a game."""


def games(root):
    """The whole catalogue, read from the manifests that already describe it."""
    root = Path(root)
    targets = json.loads((root / TARGET_FILE).read_text(encoding='utf-8'))['targets']
    images = json.loads((root / PIN_FILE).read_text(encoding='utf-8'))['external_roms']['images']
    listed = []
    for key in SOURCE_TARGETS:
        target = targets[key]
        listed.append({'key': key, 'kind': 'package', 'name': target['title'].title(),
                       'origin': 'built here', 'author': None, 'license': None,
                       'target': key, 'boots': True, 'note': None, 'link': None})
    pinned = []
    for key, pin in images.items():
        pinned.append({'key': key, 'kind': 'external', 'name': pin['name'],
                       'origin': 'third party', 'author': pin['author'], 'license': pin['license'],
                       'pin': key, 'boots': key not in BLANK, 'note': BLANK.get(key),
                       'link': LIBRARY if key in BLANK else None})
    # Manifest order, except that the two known not to boot sort to the end:
    # they are listed because hiding them would hide the finding, not because
    # they are somewhere to start.
    pinned.sort(key=lambda game: not game['boots'])
    return listed + pinned


def blank_text(game):
    """What to say when a started game leaves the monitor blank."""
    if game['note']:
        return (f'{game["name"]} is running but has not enabled the LCD, so the monitor stays '
                f'blank. {game["note"]} This is the documented limit, not a failure of the load: '
                f'see {LIBRARY}. Back returns to the menu.')
    return (f'{game["name"]} is running but the LCD is still off, so the monitor shows nothing. '
            'Press Start, or go back and pick another game.')


def explain(game, error):
    """Turn one failure into a sentence a player can act on."""
    conflict = explain_conflict(error)
    if conflict:
        return conflict
    text = str(error)
    name = game['name']
    if 'hash mismatch' in text or 'size mismatch' in text:
        return (f'{name} does not match its pinned digest, so nothing was loaded. The cached copy '
                'under workdir/private/external-roms is wrong or damaged; delete it and retry.')
    if 'readback mismatch' in text:
        return (f'{name} was sent but the board read different bytes back, so it was not started. '
                'Check the UART wiring and the selected port, then retry.')
    if text.startswith('build failed'):
        return (f'{name} did not build, so nothing was loaded. Run '
                f'`python tools/build.py sw build {game.get("target", game["key"])}` to see why.')
    if 'urlopen' in text or 'URLError' in type(error).__name__ or 'getaddrinfo' in text:
        return (f'{name} is not cached locally and could not be fetched from its pinned URL. '
                'Connect to the network once, or copy the cached image in place, then retry.')
    if 'neutral effective input required' in text:
        return (f'The board still has a button held, so {name} was not loaded. Release every key, '
                'let go of the mouse, and pick it again.')
    if 'uncertain completion' in text:
        return (f'The link stopped answering while {name} was loading, so this session cannot send '
                'anything more. Close the window and recover the session before playing.')
    return f'{name} could not be started: {text}'


def run_build(root, target):
    """Build one source target through the ordinary tool, reusing its cache."""
    root = Path(root)
    command = [sys.executable, str(root / 'tools/build.py'), 'sw', 'build', target,
               '--tag', BUILD_TAG, '--json']
    finished = subprocess.run(command, cwd=str(root), capture_output=True, text=True)
    try:
        return json.loads(finished.stdout.strip().splitlines()[-1])
    except Exception:
        raise LauncherError(f'build failed: {target}: the build tool printed no result') from None


def entry_preflight(client, expected_build):
    """What must hold before the launcher may load anything.

    The pad's preflight also requires a valid image; the launcher is what puts
    one there, so it checks identity and input authority only. Once a game is
    loaded and running, the pad's own preflight is what hands over.
    """
    identity = client.identify()
    if identity['build_id'] != expected_build:
        raise ValueError('build mismatch')
    if client.read_host(abi.HOST_REG_INPUT_SOURCE) != abi.INPUT_SOURCE_UART:
        raise ValueError('UART input authority required')
    if client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) != 0:
        raise ValueError('neutral effective input required')
    return identity


class Launcher:
    """Everything the launcher does apart from drawing itself.

    The window owns widgets and scheduling; this owns the catalogue, the build,
    the load and the failure text. Keeping them apart is what lets the flow be
    tested without a display.
    """

    def __init__(self, client, root, *, expected_build, runner=None, progress=None, record=None):
        self.client = client
        self.root = Path(root)
        self.expected_build = expected_build
        self.runner = runner or run_build
        self.progress = progress or (lambda text: None)
        self.record = record or (lambda row: None)
        self.games = games(self.root)
        self.loaded = None

    def game(self, key):
        return next(game for game in self.games if game['key'] == key)

    def manifest(self, game):
        """Reuse the current build attempt; relink only when its inputs changed.

        `sw build` already decides that from a fingerprint over every input, so
        the launcher asks for the target and never passes `--rebuild`. A player
        waits for a build only after the sources actually changed.
        """
        self.progress(f'Building {game["name"]}…')
        report = self.runner(self.root, game['target'])
        if report.get('status') != 'PASS' or not report.get('rom'):
            raise LauncherError(f'build failed: {game["target"]}: {report.get("error", "no image")}')
        manifest = self.root / Path(report['rom']).parent / 'result.json'
        return manifest, report.get('cache')

    def image(self, game):
        """The verified bytes for one game, with its public provenance."""
        if game['kind'] == 'package':
            manifest, cache = self.manifest(game)
            self.progress(f'Reading the built image ({str(cache).lower()})…')
            image, provenance = read_package(self.root, manifest)
            return image, {'package': provenance, 'cache': cache}
        self.progress('Fetching and verifying the pinned image…')
        image, provenance = read_external(self.root, game['pin'])
        return image, {'external': provenance}

    def start(self, game):
        """Load one game, reset, run, and leave the board ready for the pad."""
        try:
            # Check the preconditions before loading, not after: a refused
            # precondition must not first destroy the game already running.
            entry_preflight(self.client, self.expected_build)
            image, provenance = self.image(game)
            self.progress(f'Sending {len(image)} bytes and verifying the readback…')
            loaded = self.client.load(image)
            self.progress('Resetting…')
            self.client.control('RESET')
            self.progress('Starting…')
            self.client.control('RUN')
            identity = preflight(self.client, self.expected_build)
        except Exception as error:
            self.loaded = None
            self.record({'event': 'launcher-failed', 'game': game['key'], 'reason': str(error)})
            raise LauncherError(explain(game, error)) from error
        self.loaded = game['key']
        self.record({'event': 'launcher-start', 'game': game['key'], 'kind': game['kind'],
                     'bytes': loaded['verified_bytes']})
        return {'game': game['key'], 'provenance': provenance, 'load': loaded, 'identity': identity}


def leave_pad(driver, to_menu, to_failure):
    """Back: release every held button, then return to the menu.

    The release has to happen here, on the way out. Back takes the pad out of
    the window and with it the two paths that would otherwise clear a held
    button: the key-up is dropped once the panel is gone, and the focus-loss
    release is switched off with it. Without this write the mask stays applied
    on the board, the player's character keeps walking, and nothing left on
    screen can clear it.

    One write, through the driver's guard, so a failed release ends the session
    truthfully instead of returning to a menu that lies about the board.
    """
    driver.focus_lost()
    if driver.failure is not None:
        return to_failure(driver.failure_text())
    return to_menu()


class BootWatch:
    """Say so when a started game leaves the LCD off and the monitor blank."""

    def __init__(self, game, *, grace=BOOT_GRACE, clock=time.monotonic):
        self.game = game
        self.deadline = clock() + grace
        self.clock = clock
        self.done = False

    def update(self, lcdc):
        """None while undecided or drawing; the player-facing text once it is not."""
        if self.done:
            return None
        if lcdc & LCD_ENABLE:
            self.done = True
            return None
        if self.clock() < self.deadline:
            return None
        self.done = True
        return blank_text(self.game)


def launcher_loop(client, root, *, expected_build, window=None, record=None,
                  seconds=None, runner=None):
    """Own one session for the whole launcher: preflight, window, then release.

    `window(launcher, controller, seconds)` blocks until the player closes it.
    Tests pass a scripted window; the tkinter one is the default.
    """
    launcher = Launcher(client, root, expected_build=expected_build, runner=runner, record=record)
    result = own_session(client, lambda: entry_preflight(client, expected_build),
                         lambda controller: (window or tk_launcher)(launcher, controller, seconds),
                         record)
    result['loaded'] = launcher.loaded
    return result


MUTED, CARD, MARK = '#9aa4b1', '#22262d', '#ffc46b'
BOOT_POLL_SECONDS = 0.5


def tk_launcher(launcher, controller, seconds=None, *, clock=time.monotonic):
    """Draw the menu, load the chosen game, then hand over to the pad.

    One Tk root and one Driver for the whole session: the menu and the pad are
    two screens in the same window, so the lease and the UART owner never change
    when a game starts or when Back returns to the menu.
    """
    import tkinter as tk

    driver = Driver(controller, seconds, clock=clock)
    root = tk.Tk()
    root.title('Game Boy launcher')
    root.configure(bg=PANEL)
    screen = {'panel': None, 'frame': None, 'watch': None, 'game': None}

    def clear():
        if screen['panel'] is not None:
            screen['panel'].polling = False
        if screen['frame'] is not None:
            screen['frame'].destroy()
        screen.update(panel=None, frame=None, watch=None)

    def quit_after(delay=0):
        root.after(delay, root.destroy)

    def show_menu():
        clear()
        screen['game'] = None
        screen['frame'] = menu = tk.Frame(root, bg=PANEL)
        menu.pack(fill='both', expand=True)
        tk.Label(menu, text='GAME BOY', bg=PANEL, fg=FACE, font=('Segoe UI', 18, 'bold')
                 ).grid(row=0, column=0, columnspan=2, pady=(14, 0))
        tk.Label(menu, text='Pick a game. It loads and starts on the board; watch the VGA screen.',
                 bg=PANEL, fg=KEY, font=('Segoe UI', 10)).grid(row=1, column=0, columnspan=2, pady=(2, 10))
        row = 2
        for origin, heading in (('built here', 'Built from source in this repository'),
                                ('third party', 'Other people’s games, pinned by digest and '
                                                'fetched at run time; each stays under its own licence')):
            tk.Label(menu, text=heading, bg=PANEL, fg=MUTED, font=('Segoe UI', 9, 'bold'),
                     wraplength=520, justify='left').grid(row=row, column=0, columnspan=2,
                                                          sticky='w', padx=18, pady=(8, 2))
            row += 1
            chosen = [item for item in launcher.games if item['origin'] == origin]
            for index, game in enumerate(chosen):
                card(menu, game).grid(row=row + index // 2, column=index % 2,
                                      sticky='nsew', padx=8, pady=4)
            row += (len(chosen) + 1) // 2
        tk.Label(menu, text='Escape or closing the window releases input and exits.',
                 bg=PANEL, fg=KEY, font=('Segoe UI', 9), wraplength=540
                 ).grid(row=row, column=0, columnspan=2, padx=16, pady=(8, 12))
        menu.grid_columnconfigure(0, weight=1, uniform='card')
        menu.grid_columnconfigure(1, weight=1, uniform='card')

    def card(parent, game):
        """One selectable game: its name, where it came from, and any known limit."""
        frame = tk.Frame(parent, bg=CARD, relief='raised', borderwidth=2)
        title = game['name'] + ('' if game['boots'] else '   ⚠ does not boot')
        tk.Label(frame, text=title, bg=CARD, fg=FACE if game['boots'] else MARK,
                 font=('Segoe UI', 11, 'bold'), anchor='w', wraplength=250, justify='left'
                 ).pack(fill='x', padx=10, pady=(8, 0))
        credit = (' · '.join([game['author'], game['license']]) if game['author']
                  else 'This repository, built from source')
        tk.Label(frame, text=credit, bg=CARD, fg=MUTED, font=('Segoe UI', 9), anchor='w',
                 wraplength=250, justify='left').pack(fill='x', padx=10, pady=(0, 8))
        if game['note']:
            tk.Label(frame, text=game['note'] + ' See ' + LIBRARY, bg=CARD, fg=MARK,
                     font=('Segoe UI', 8), anchor='w', wraplength=250, justify='left'
                     ).pack(fill='x', padx=10, pady=(0, 8))
        for widget in (frame, *frame.winfo_children()):
            widget.bind('<Button-1>', lambda _event, chosen=game: choose(chosen))
        return frame

    def choose(game):
        """Load one game with its progress visible, then show the pad."""
        clear()
        screen['frame'] = loading = tk.Frame(root, bg=PANEL)
        loading.pack(fill='both', expand=True)
        tk.Label(loading, text=game['name'], bg=PANEL, fg=FACE, font=('Segoe UI', 15, 'bold')
                 ).pack(pady=(40, 6))
        line = tk.Label(loading, text='Starting…', bg=PANEL, fg=TEXT, font=('Consolas', 11),
                        wraplength=520, justify='left')
        line.pack(padx=20, pady=(0, 40))
        launcher.progress = lambda text: (line.configure(text=text), root.update_idletasks())
        try:
            launcher.start(game)
        except LauncherError as error:
            line.configure(text=str(error), fg=MARK)
            tk.Button(loading, text='◀  Back to the menu', command=show_menu, bg=IDLE, fg=FACE,
                      activebackground=HELD, font=('Segoe UI', 10, 'bold')).pack(pady=(0, 20))
            return
        finally:
            launcher.progress = lambda text: None
        show_pad(game)

    def failed_release(text):
        if screen['panel'] is not None:
            screen['panel'].stop(text, '#ff9393')

    def show_pad(game):
        clear()
        screen['game'] = game
        panel = PadPanel(root, driver, on_exit=quit_after,
                         back=lambda: leave_pad(driver, show_menu, failed_release))
        panel.frame.pack()
        screen.update(panel=panel, frame=panel.frame, watch=BootWatch(game, clock=clock))
        panel.start()
        root.after(int(BOOT_POLL_SECONDS * 1000), boot_poll)

    def boot_poll():
        """Ask the board whether the LCD came on; stop as soon as it is decided."""
        watch, panel = screen['watch'], screen['panel']
        if watch is None or panel is None or watch.done or driver.failure is not None:
            return
        status = driver.guard(launcher.client.read_lcd_status, 'UART read')
        if status is None:
            return panel.paint()
        blank = watch.update(status['lcdc'])
        if blank:
            return panel.message(blank, MARK)
        root.after(int(BOOT_POLL_SECONDS * 1000), boot_poll)

    def key_event(event, down):
        panel = screen['panel']
        if down and event.keycode == ESCAPE:
            return root.destroy()
        if panel is not None and panel.key_event(event, down) == 'exit':
            root.destroy()

    def focus_out(event):
        if screen['panel'] is not None:
            screen['panel'].focus_out(event)

    def lease_tick():
        if driver.expired():
            return root.destroy()
        root.after(1000, lease_tick)

    show_menu()
    root.bind('<KeyPress>', lambda event: key_event(event, True))
    root.bind('<KeyRelease>', lambda event: key_event(event, False))
    # Key-up goes to whichever window takes the focus, so release here instead.
    root.bind('<FocusOut>', focus_out)
    root.protocol('WM_DELETE_WINDOW', root.destroy)
    root.after(1000, lease_tick)
    root.focus_force()
    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    driver.raise_failure()

"""Local on-screen Game Boy pad: one UART owner, no frame readback.

The player watches the board's own VGA output, so this window reads no frames
and takes no SNAPSHOT. Every mouse or key edge becomes at most one ordinary
INPUT write, exactly as `host keyboard` does, which is why the board can stay in
free-run at native speed while it is played.

The input logic here is deliberately separate from the window: `Controller` and
`pad_loop` need no display and are tested headless against a fake endpoint.
"""
import time

from . import generated_interfaces as abi
from .host.keyboard import KEYS
from .host.library import return_to_menu

PAD_KEYS = dict(KEYS)
PAD_KEYS.update({0x57: abi.BUTTON_UP, 0x41: abi.BUTTON_LEFT, 0x53: abi.BUTTON_DOWN,
                 0x44: abi.BUTTON_RIGHT, 0x4a: abi.BUTTON_A, 0x4b: abi.BUTTON_B})

# Legacy `KEYS` and the desktop aliases use Windows virtual-key codes. Tk reports
# that same code in `event.keycode` on Windows, except for the shift keys, which
# both arrive as VK_SHIFT and are told apart only by keysym.
KEYSYMS = {'Right': 0x27, 'Left': 0x25, 'Up': 0x26, 'Down': 0x28,
           'z': 0x5a, 'Z': 0x5a, 'x': 0x58, 'X': 0x58,
           'Shift_R': 0xa1, 'Return': 0x0d, 'KP_Enter': 0x0d}
KEYSYMS.update({letter: ord(letter.upper()) for letter in 'wasdjkWASDJK'})
# Control (0x4) and Alt (0x20000) in a Tk key event state, and nothing else.
# Mod1 (0x8) is not Alt here: Windows latches NumLock into Mod1, so filtering it
# would drop every key-down while NumLock is on.
MODIFIERS = 0x4 | 0x20000
ESCAPE = 0x1b
# Both shift keys arrive on this one keycode; only the right one is Select.
VK_SHIFT, SELECT = 0x10, 0xa1
# Display order and the key each control names on its face.
FACES = (('Right', 0x27, 'D / →'), ('Left', 0x25, 'A / ←'),
         ('Up', 0x26, 'W / ↑'), ('Down', 0x28, 'S / ↓'),
         ('A', 0x5a, 'J / Z'), ('B', 0x58, 'K / X'),
         ('Select', 0xa1, 'R-Shift'), ('Start', 0x0d, 'Enter'))
FACE_BY_CODE = {code: (name, key) for name, code, key in FACES}


def virtual_key(keysym, keycode=None):
    """The mapped virtual-key code for one Tk key event, or None."""
    code = KEYSYMS.get(keysym)
    if code is None and keycode in PAD_KEYS:
        code = keycode
    return code if code in PAD_KEYS else None


def edge(keysym, keycode, state, down):
    """One (code, down) input edge from a Tk key event, or None to ignore it.

    Ctrl/Alt-modified downs are ignored and releases still clear a held key,
    matching `host keyboard`. Auto-repeat needs no filter here: a repeated down
    leaves the held union unchanged and writes nothing.

    Any release on the shift keycode clears Select, whichever keysym Tk attaches.
    Windows reports the press as `Shift_R` and its release as `Shift_L` on the
    same keycode, so resolving a release by keysym alone leaves Select held until
    focus loss or exit. Only the press still requires `Shift_R`, so left Shift
    never presses Select; a release with nothing held changes no union and writes
    nothing, which is why clearing on either keysym is safe and pressing is not.
    """
    code = virtual_key(keysym, keycode)
    if code is None and not down and keycode == VK_SHIFT:
        code = SELECT
    if code is None or (down and state & MODIFIERS):
        return None
    return code, down


def names(mask):
    return [name for name, code, _ in FACES if mask & KEYS[code]]


def explain_conflict(error):
    """Name the actual cause when the board is already held by someone else."""
    text = str(error)
    if 'trusted controller already running' in text:
        return ('Another trusted controller already holds this machine. The live viewer, '
                'a host command or a second pad is running; stop it and retry.')
    if isinstance(error, FileExistsError):
        return ('Another session holds this device lock. Stop the live viewer, '
                '`host keyboard` or a second pad on this board and retry.')
    if 'previous completion is uncertain' in text:
        return ('The durable session for this device is uncertain. Recover it explicitly '
                'before opening the pad; no input was sent.')
    if 'UART input authority required' in text:
        return 'The board is not taking UART input. Select the UART input source, then retry.'
    return None


def preflight(client, expected_build):
    """Same preconditions the viewer checks, then free-run.

    Stepped mode is not offered: with no frame readback there is nothing to
    resynchronize, and pausing the core would only stop the picture the player
    is watching.
    """
    identity = client.identify()
    if identity['build_id'] != expected_build:
        raise ValueError('build mismatch')
    if client.read_host(abi.HOST_REG_IMAGE_VALID) != 1:
        raise ValueError('no valid existing image')
    if client.read_host(abi.HOST_REG_INPUT_SOURCE) != abi.INPUT_SOURCE_UART:
        raise ValueError('UART input authority required')
    if client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) != 0:
        raise ValueError('neutral effective input required')
    state = client.read_host(abi.HOST_REG_STATE)
    if state not in (abi.STATE_PAUSED, abi.STATE_RUNNING):
        raise ValueError('existing image must be paused or running')
    if state == abi.STATE_PAUSED:
        client.control('RUN')
        if client.read_host(abi.HOST_REG_STATE) != abi.STATE_RUNNING:
            raise ValueError('core did not resume')
    return identity


class Controller:
    """The held button union and the only path that writes it.

    Sources are tracked separately so releasing one alias or a mouse button
    cannot clear another source that still holds the same Game Boy button.
    """

    def __init__(self, client, record=None):
        self.client = client
        self.record = record or (lambda row: None)
        self.held = {}
        self.changes = 0
        self.dot = None

    @property
    def mask(self):
        mask = 0
        for code in self.held.values():
            mask |= PAD_KEYS[code]
        return mask

    def held_names(self):
        return names(self.mask)

    def press(self, code):
        return self.apply(code, True)

    def release(self, code):
        return self.apply(code, False)

    def apply(self, code, down, source=None):
        """Write the changed union once; an unchanged union sends nothing."""
        if code not in PAD_KEYS:
            return False
        source = ('button', code) if source is None else source
        previous = self.mask
        if down and source not in self.held:
            self.held[source] = code
        elif not down and source in self.held:
            del self.held[source]
        else:
            return False
        if previous == self.mask:
            return False
        applied = self.client.control('INPUT', self.mask)
        self.dot = applied['dot']
        self.changes += 1
        self.record(dict(event='pad-mask', mask=self.mask, dot=self.dot))
        return True

    def main_menu(self):
        """Release, return once, and verify the running neutral loader."""
        if self.client.uncertain:
            raise RuntimeError('uncertain; no further traffic')
        self.release_all()
        report = return_to_menu(self.client, wait=True)
        endpoint = report['endpoint']
        if (report['library_status']['result'] != 'OK' or
                endpoint['PROFILE'] != abi.PROFILE_LOADER_ID or
                endpoint['IMAGE_VALID'] != 1 or endpoint['STATE'] != abi.STATE_RUNNING):
            raise ValueError('Main menu did not return to a valid running loader')
        for address, expected in ((abi.HOST_REG_INPUT_SOURCE, abi.INPUT_SOURCE_UART),
                                  (abi.HOST_REG_INPUT, 0), (abi.HOST_REG_INPUT_EFFECTIVE, 0)):
            if self.client.read_host(address) != expected:
                raise ValueError('Main menu did not restore neutral UART input')
        self.record(dict(event='pad-main-menu', result=report))
        return report

    def release_all(self):
        """Drop every held button in one write; nothing held sends nothing.

        Focus loss uses this: the key-up for a held direction is delivered to
        whatever window took the focus, so without it the board would keep the
        button and the player, who is watching the monitor, would see their
        character walk on by itself.
        """
        if not self.held:
            return False
        self.held.clear()
        applied = self.client.control('INPUT', 0)
        self.dot = applied['dot']
        self.changes += 1
        self.record(dict(event='pad-release-all', mask=0, dot=self.dot))
        return True

    def close(self):
        """Release input, verify 0 and report whether the session stayed certain."""
        result = {'changes': self.changes, 'released': False}
        if self.client.uncertain:
            result['cleanup'] = {'verified': False, 'reason': 'uncertain; no further traffic'}
        else:
            try:
                applied = self.client.control('INPUT', 0)
                effective = self.client.read_host(abi.HOST_REG_INPUT_EFFECTIVE)
                if effective != 0:
                    raise ValueError('input did not release')
                self.held.clear()
                self.record(dict(event='pad-release', mask=0, dot=applied['dot']))
                result['released'] = True
                result['cleanup'] = {'verified': True, 'input_effective': 0, 'dot': applied['dot']}
            except Exception as error:
                result['cleanup'] = {'verified': False, 'reason': str(error)}
                result['release_error'] = str(error)
        result['uncertain'] = self.client.uncertain
        result['sequence'] = getattr(self.client, 'sequence', None)
        return result


def own_session(client, preflight_action, run_window, record=None):
    """Preflight, run one window, then always release. Shared by pad and launcher.

    `preflight_action()` returns the endpoint identity and must send no control
    traffic when it refuses. `run_window(controller)` blocks until the player
    closes the window. The release below runs whatever ended it.
    """
    result = {'status': 'FAIL', 'reason': 'preflight not completed', 'changes': 0}
    controller = None
    try:
        result['identity'] = preflight_action()
        controller = Controller(client, record)
        run_window(controller)
        result['status'] = 'PASS'
        result.pop('reason', None)
    except BaseException as error:
        # Ctrl+C included: the release below must run whatever ended the window.
        result['status'] = 'FAIL'
        result['reason'] = type(error).__name__
        result['error'] = str(error)
    finally:
        if controller is None:
            # No control traffic after a failed precondition.
            result['released'] = False
            result['cleanup'] = {'verified': False, 'reason': 'preconditions failed; no control sent'}
        else:
            result.update(controller.close())
            if not result['released']:
                result['status'] = 'FAIL'
                result.setdefault('reason', 'release not verified')
    return result


def pad_loop(client, *, expected_build, window=None, record=None, seconds=None):
    """Own the pad session: preflight, run the window, then always release.

    `window(controller, seconds)` blocks until the player closes it. Tests pass
    a scripted window; the tkinter one is the default.
    """
    return own_session(client, lambda: preflight(client, expected_build),
                       lambda controller: (window or tk_window)(controller, seconds), record)


POLL_SECONDS = 0.4


class Driver:
    """Everything the pad window does apart from drawing itself.

    The window owns widgets and scheduling; this owns the input edges, the
    board poll, the lease and the failure that ends a session. Keeping them
    apart is what lets the pad's behavior be tested without a display.
    """

    def __init__(self, controller, seconds=None, *, clock=time.monotonic):
        self.controller = controller
        self.clock = clock
        self.deadline = None if seconds is None else clock() + seconds
        self.failure = None

    @property
    def remaining(self):
        return None if self.deadline is None else max(0, int(self.deadline - self.clock()))

    def expired(self):
        return self.deadline is not None and self.clock() >= self.deadline

    def guard(self, action, what):
        """Run one UART action; the first failure ends the session, truthfully."""
        if self.failure is not None:
            return None
        try:
            return action()
        except Exception as error:
            self.failure = (what, error)
            return None

    def key(self, keysym, keycode, state, down):
        """Route one key event: 'exit' for Escape, otherwise apply any edge."""
        if down and keycode == ESCAPE:
            return 'exit'
        found = edge(keysym, keycode, state, down)
        if found is None:
            return None
        code, down = found
        return 'applied' if self.button(code, down, source=('key', code)) else None

    def button(self, code, down, source=None):
        """One control edge, from a click or a key; they are the same path."""
        return bool(self.guard(lambda: self.controller.apply(code, down, source), 'UART write'))

    def main_menu(self):
        return self.guard(self.controller.main_menu, 'Main menu')

    def focus_lost(self):
        """Release everything when the window stops receiving key events.

        The key-up for a held button goes to whichever window took the focus,
        so a held union would otherwise stay on the board with nothing on
        screen to explain it. The session stays open and playable.
        """
        return bool(self.guard(self.controller.release_all, 'UART write'))

    def poll(self):
        """Ask the board what it is doing. Answers only; never a host guess."""
        readings = self.guard(lambda: (self.controller.client.read_host(abi.HOST_REG_STATE),
                                       self.controller.client.read_host(abi.HOST_REG_INPUT_EFFECTIVE)),
                              'UART read')
        if readings is None:
            return None
        state, effective = readings
        return {'state': state, 'effective': effective, 'text': self.core_text(state, effective)}

    def core_text(self, state, effective):
        label = {abi.STATE_RUNNING: 'RUNNING', abi.STATE_PAUSED: 'PAUSED'}.get(state, 'UNKNOWN')
        text = 'Core: ' + label
        if effective != self.controller.mask:
            text += '  |  board reports ' + (' + '.join(names(effective)) or 'none')
        if self.remaining is not None:
            text += f'  |  lease {self.remaining}s'
        return text

    def held_text(self):
        held = self.controller.held_names()
        return ('Held: ' + (' + '.join(held) if held else 'none') +
                f'  (mask {self.controller.mask:#04x}, {self.controller.changes} writes,'
                f' dot {self.controller.dot})')

    def failure_text(self):
        return None if self.failure is None else '%s failed: %s' % self.failure

    def raise_failure(self):
        if self.failure is not None:
            raise self.failure[1]


IDLE, HELD, FACE, KEY, PANEL, TEXT = '#2b3038', '#77baff', '#f2f5f8', '#aeb6c0', '#17191c', '#e8ecf1'
SHELL, INK, MUTED = '#d8d8df', '#202638', '#4e526a'
ACTION = '#8c2857'


class PadPanel:
    """The pad's controls inside any container; every behavior stays in `Driver`.

    The launcher reuses this frame so a chosen game hands over to the same pad
    inside the same window and the same UART session.
    """

    def __init__(self, parent, driver, *, on_exit, back=None):
        import tkinter as tk
        self.driver, self.controller, self.on_exit = driver, driver.controller, on_exit
        self.widgets = {}
        self.polling = False
        self.frame = frame = tk.Frame(parent, bg=SHELL)
        tk.Label(frame, text='nand2mario  /  GAME PAD',
                 bg=SHELL, fg=INK, font=('Segoe UI', 16, 'bold')).grid(row=0, column=0, columnspan=2, pady=(20, 12))
        pad = tk.Frame(frame, bg=SHELL)
        pad.grid(row=1, column=0, padx=16, pady=6)
        self.control(tk, pad, 0x26, row=0, column=1)
        self.control(tk, pad, 0x25, row=1, column=0)
        self.control(tk, pad, 0x27, row=1, column=2)
        self.control(tk, pad, 0x28, row=2, column=1)
        tk.Label(pad, text='●', bg=IDLE, fg=KEY, width=7, height=2,
                 font=('Segoe UI', 11, 'bold')).grid(row=1, column=1, sticky='nsew')
        face = tk.Frame(frame, bg=SHELL)
        face.grid(row=1, column=1, padx=16, pady=6)
        self.control(tk, face, 0x58, row=1, column=0)
        self.control(tk, face, 0x5a, row=0, column=1)
        centre = tk.Frame(frame, bg=SHELL)
        centre.grid(row=2, column=0, columnspan=2, pady=(0, 6))
        self.control(tk, centre, 0xa1, row=0, column=0)
        self.control(tk, centre, 0x0d, row=0, column=1)
        self.menu = tk.Button(frame, text='Main menu', command=self.main_menu,
                              bg=IDLE, fg=FACE, activebackground=HELD,
                              font=('Segoe UI', 11, 'bold'), padx=18, pady=7)
        self.menu.grid(row=3, column=0, columnspan=2, pady=12)
        self.held = tk.Label(frame, text=driver.held_text(), bg=SHELL, fg=INK, font=('Consolas', 10))
        self.held.grid(row=4, column=0, columnspan=2, padx=14)
        self.core = tk.Label(frame, text='Core: checking', bg=SHELL, fg=INK, font=('Consolas', 10))
        self.core.grid(row=5, column=0, columnspan=2)
        self.note = tk.Label(frame, text=HINT, bg=SHELL, fg=MUTED, font=('Segoe UI', 9), wraplength=480)
        self.note.grid(row=6, column=0, columnspan=2, padx=12, pady=(8, 18))
        if back is not None:
            tk.Button(frame, text='◀  Game library (desktop)', command=back, bg=IDLE, fg=FACE,
                      activebackground=HELD, relief='raised', borderwidth=2,
                      font=('Segoe UI', 10, 'bold')).grid(row=7, column=0, columnspan=2, pady=(0, 10))
        self.paint()

    def control(self, tk, parent, code, **grid):
        name, key = FACE_BY_CODE[code]
        round_button = code in (0x5a, 0x58)
        small = code in (0xa1, 0x0d)
        width, height = (88, 88) if round_button else ((104, 55) if small else (72, 64))
        widget = tk.Canvas(parent, bg=SHELL, width=width, height=height, highlightthickness=0)
        if round_button:
            widget.create_oval(4, 4, 84, 84, fill=ACTION, outline='#64203f', width=3, tags='face')
        elif small:
            widget.create_oval(4, 8, 38, 45, fill=IDLE, outline=IDLE, tags='face')
            widget.create_oval(66, 8, 100, 45, fill=IDLE, outline=IDLE, tags='face')
            widget.create_rectangle(21, 8, 83, 45, fill=IDLE, outline=IDLE, tags='face')
        else:
            widget.create_rectangle(0, 0, width, height, fill=IDLE, outline=IDLE, tags='face')
        widget.create_text(width / 2, height / 2 - 9, text=name, fill=FACE,
                           font=('Segoe UI', 12, 'bold'), tags='caption')
        widget.create_text(width / 2, height / 2 + 11, text=key, fill=FACE,
                           font=('Segoe UI', 9), tags='caption')
        widget.bind('<ButtonPress-1>', lambda _event, c=code: self.button(c, True))
        widget.bind('<ButtonRelease-1>', lambda _event, c=code: self.button(c, False))
        widget.grid(padx=4 if round_button or small else 0, pady=3 if round_button or small else 0, **grid)
        self.widgets[code] = widget
        return widget

    def message(self, text, colour=MUTED):
        self.note.configure(text=text, fg=colour)

    def stop(self, reason, colour=KEY, delay=1200):
        self.polling = False
        self.message(reason, colour)
        self.on_exit(delay)

    def paint(self):
        for code, widget in self.widgets.items():
            held = bool(self.controller.mask & KEYS[code])
            idle = ACTION if code in (0x5a, 0x58) else IDLE
            widget.itemconfigure('face', fill=HELD if held else idle)
            widget.itemconfigure('caption', fill=INK if held else FACE)
        self.held.configure(text=self.driver.held_text())
        if self.driver.failure is not None:
            self.stop(self.driver.failure_text(), '#ff9393')

    def button(self, code, down):
        self.driver.button(code, down)
        self.paint()

    def main_menu(self):
        self.message('Returning to the FPGA main menu…')
        self.menu.configure(state='disabled')
        self.frame.update_idletasks()
        report = self.driver.main_menu()
        if report is not None:
            self.message('FPGA main menu ready. Choose a game with the D-pad and A.')
            self.menu.configure(state='normal')
        self.paint()

    def start(self):
        """Begin polling the board; the panel schedules itself from here on."""
        self.polling = True
        self.frame.after(10, self.poll)

    def poll(self):
        if not self.polling:
            return
        reading = self.driver.poll()
        if reading is None:
            return self.stop(self.driver.failure_text(), '#ff9393')
        self.core.configure(text=reading['text'])
        self.watch(reading)
        if self.driver.expired():
            return self.stop('Lease expired; releasing input and closing.', KEY, 200)
        self.frame.after(int(POLL_SECONDS * 1000), self.poll)

    def watch(self, reading):
        """Hook for an owner that wants each poll; the pad itself wants none."""

    def key_event(self, event, down):
        """Route one key event; 'exit' means the player asked to leave."""
        if self.driver.key(event.keysym, event.keycode, event.state, down) == 'exit':
            return 'exit'
        self.paint()
        return None

    def focus_out(self, _event=None):
        if self.driver.focus_lost():
            self.message('Focus left the window; every held button was released.')
        self.paint()


HINT = ('Each control names its button and, in brackets, the key that presses it. '
        'Mouse and keyboard do the same thing; hold means hold. '
        'Leaving the window releases every held button. '
        'Esc or closing the window releases input and exits.')


def tk_window(controller, seconds=None, *, clock=time.monotonic):
    """Draw the pad and bind it to a Driver; all behavior lives in the Driver."""
    import tkinter as tk

    driver = Driver(controller, seconds, clock=clock)
    root = tk.Tk()
    root.title('Game Boy pad')
    root.configure(bg=PANEL)
    root.resizable(False, False)
    panel = PadPanel(root, driver, on_exit=lambda delay: root.after(delay, root.destroy))
    panel.frame.pack()

    def key_event(event, down):
        if panel.key_event(event, down) == 'exit':
            root.destroy()

    root.bind('<KeyPress>', lambda event: key_event(event, True))
    root.bind('<KeyRelease>', lambda event: key_event(event, False))
    # Key-up goes to whichever window takes the focus, so release here instead.
    root.bind('<FocusOut>', panel.focus_out)
    root.protocol('WM_DELETE_WINDOW', root.destroy)
    panel.start()
    root.focus_force()
    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    driver.raise_failure()

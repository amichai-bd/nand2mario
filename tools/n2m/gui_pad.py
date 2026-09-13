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

# `KEYS` is the one mapping; it is keyed by Windows virtual-key code. Tk reports
# that same code in `event.keycode` on Windows, except for the shift keys, which
# both arrive as VK_SHIFT and are told apart only by keysym.
KEYSYMS = {'Right': 0x27, 'Left': 0x25, 'Up': 0x26, 'Down': 0x28,
           'z': 0x5a, 'Z': 0x5a, 'x': 0x58, 'X': 0x58,
           'Shift_R': 0xa1, 'Return': 0x0d, 'KP_Enter': 0x0d}
# Control and Alt modifiers in a Tk key event state.
MODIFIERS = 0x4 | 0x8 | 0x20000
ESCAPE = 0x1b
# Display order and the key each control names on its face.
FACES = (('Right', 0x27, '→'), ('Left', 0x25, '←'),
         ('Up', 0x26, '↑'), ('Down', 0x28, '↓'),
         ('A', 0x5a, 'Z'), ('B', 0x58, 'X'),
         ('Select', 0xa1, 'R-Shift'), ('Start', 0x0d, 'Enter'))
FACE_BY_CODE = {code: (name, key) for name, code, key in FACES}


def virtual_key(keysym, keycode=None):
    """The mapped virtual-key code for one Tk key event, or None."""
    code = KEYSYMS.get(keysym)
    if code is None and keycode in KEYS:
        code = keycode
    return code if code in KEYS else None


def edge(keysym, keycode, state, down):
    """One (code, down) input edge from a Tk key event, or None to ignore it.

    Ctrl/Alt-modified downs are ignored and releases still clear a held key,
    matching `host keyboard`. Auto-repeat needs no filter here: a repeated down
    leaves the held union unchanged and writes nothing.
    """
    code = virtual_key(keysym, keycode)
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

    A clicked control and a pressed key call `press`/`release` with the same
    virtual-key code, so the board cannot tell them apart.
    """

    def __init__(self, client, record=None):
        self.client = client
        self.record = record or (lambda row: None)
        self.held = []
        self.changes = 0
        self.dot = None

    @property
    def mask(self):
        return sum(KEYS[code] for code in self.held)

    def held_names(self):
        return names(self.mask)

    def press(self, code):
        return self.apply(code, True)

    def release(self, code):
        return self.apply(code, False)

    def apply(self, code, down):
        """Write the changed union once; an unchanged union sends nothing."""
        if code not in KEYS:
            return False
        if down and code not in self.held:
            self.held.append(code)
        elif not down and code in self.held:
            self.held.remove(code)
        else:
            return False
        applied = self.client.control('INPUT', self.mask)
        self.dot = applied['dot']
        self.changes += 1
        self.record(dict(event='pad-mask', mask=self.mask, dot=self.dot))
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


def pad_loop(client, *, expected_build, window=None, record=None, seconds=None):
    """Own the pad session: preflight, run the window, then always release.

    `window(controller, seconds)` blocks until the player closes it. Tests pass
    a scripted window; the tkinter one is the default.
    """
    result = {'status': 'FAIL', 'reason': 'preflight not completed', 'changes': 0}
    controller = None
    try:
        result['identity'] = preflight(client, expected_build)
        controller = Controller(client, record)
        (window or tk_window)(controller, seconds)
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


IDLE, HELD, FACE, KEY, PANEL, TEXT = '#2b3038', '#77baff', '#f2f5f8', '#aeb6c0', '#17191c', '#e8ecf1'


def tk_window(controller, seconds=None, *, clock=time.monotonic):
    """The local pad window. Mouse and keyboard drive the same controller."""
    import tkinter as tk

    root = tk.Tk()
    root.title('Game Boy pad')
    root.configure(bg=PANEL)
    root.resizable(False, False)
    widgets = {}
    failure = {}
    deadline = None if seconds is None else clock() + seconds

    def status(text, colour=KEY):
        message.configure(text=text, fg=colour)

    def drive(code, down):
        try:
            controller.apply(code, down)
        except Exception as error:  # A failed write ends the session; never play on blind.
            failure['error'] = error
            status('UART write failed: ' + str(error), '#ff9393')
            root.after(1200, root.destroy)
            return
        for key, widget in widgets.items():
            widget.configure(bg=HELD if key in controller.held else IDLE,
                             fg=PANEL if key in controller.held else FACE)
        refresh()

    def control(parent, code, **grid):
        name, key = FACE_BY_CODE[code]
        widget = tk.Label(parent, text=f'{name}\n[ {key} ]', bg=IDLE, fg=FACE, width=7, height=2,
                          font=('Segoe UI', 11, 'bold'), relief='raised', borderwidth=2)
        widget.bind('<ButtonPress-1>', lambda _event, c=code: drive(c, True))
        widget.bind('<ButtonRelease-1>', lambda _event, c=code: drive(c, False))
        widget.grid(padx=3, pady=3, **grid)
        widgets[code] = widget
        return widget

    tk.Label(root, text='Watch the board’s VGA screen — this window only sends buttons',
             bg=PANEL, fg=KEY, font=('Segoe UI', 10)).grid(row=0, column=0, columnspan=2, pady=(10, 4))

    pad = tk.Frame(root, bg=PANEL)
    pad.grid(row=1, column=0, padx=16, pady=6)
    control(pad, 0x26, row=0, column=1)
    control(pad, 0x25, row=1, column=0)
    control(pad, 0x27, row=1, column=2)
    control(pad, 0x28, row=2, column=1)
    tk.Label(pad, text='', bg=PANEL, width=7, height=2).grid(row=1, column=1)

    face = tk.Frame(root, bg=PANEL)
    face.grid(row=1, column=1, padx=16, pady=6)
    control(face, 0x58, row=1, column=0)
    control(face, 0x5a, row=0, column=1)

    centre = tk.Frame(root, bg=PANEL)
    centre.grid(row=2, column=0, columnspan=2, pady=(0, 6))
    control(centre, 0xa1, row=0, column=0)
    control(centre, 0x0d, row=0, column=1)

    held = tk.Label(root, text='Held: none', bg=PANEL, fg=TEXT, font=('Consolas', 11))
    held.grid(row=3, column=0, columnspan=2)
    core = tk.Label(root, text='Core: checking', bg=PANEL, fg=TEXT, font=('Consolas', 11))
    core.grid(row=4, column=0, columnspan=2)
    message = tk.Label(root, text='Each control names its button and, in brackets, the key that presses it. '
                                  'Mouse and keyboard do the same thing; hold means hold. '
                                  'Esc or closing the window releases input and exits.',
                       bg=PANEL, fg=KEY, font=('Segoe UI', 9), wraplength=420)
    message.grid(row=5, column=0, columnspan=2, padx=12, pady=(4, 10))

    def refresh():
        names_held = controller.held_names()
        held.configure(text='Held: ' + (' + '.join(names_held) if names_held else 'none') +
                       f'  (mask {controller.mask:#04x}, {controller.changes} writes, dot {controller.dot})')

    def poll():
        """Ask the board what it is actually doing; never show a guess."""
        if failure:
            return
        try:
            state = controller.client.read_host(abi.HOST_REG_STATE)
            effective = controller.client.read_host(abi.HOST_REG_INPUT_EFFECTIVE)
        except Exception as error:
            failure['error'] = error
            status('UART read failed: ' + str(error), '#ff9393')
            root.after(1200, root.destroy)
            return
        label = 'RUNNING' if state == abi.STATE_RUNNING else ('PAUSED' if state == abi.STATE_PAUSED else 'UNKNOWN')
        remaining = '' if deadline is None else f'  |  lease {max(0, int(deadline - clock()))}s'
        agrees = '' if effective == controller.mask else f'  |  board reports {" + ".join(names(effective)) or "none"}'
        core.configure(text=f'Core: {label}' + agrees + remaining)
        if deadline is not None and clock() >= deadline:
            status('Lease expired; releasing input and closing.')
            root.after(200, root.destroy)
            return
        root.after(400, poll)

    def key_event(event, down):
        if down and event.keycode == ESCAPE:
            root.destroy()
            return
        found = edge(event.keysym, event.keycode, event.state, down)
        if found is not None:
            drive(*found)

    root.bind('<KeyPress>', lambda event: key_event(event, True))
    root.bind('<KeyRelease>', lambda event: key_event(event, False))
    root.protocol('WM_DELETE_WINDOW', root.destroy)
    refresh()
    root.after(10, poll)
    root.focus_force()
    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    if failure:
        raise failure['error']

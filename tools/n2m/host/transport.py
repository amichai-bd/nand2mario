"""Explicit healthy Windows selection before any serial object is opened."""
from contextlib import contextmanager
import hashlib
import json
import os
import time
from pathlib import Path

from .. import generated_interfaces as abi
from ..doctor import uart
from ..records import atomic_json


class SerialTransport:
    """Keep line configuration fixed while the Client changes read deadlines.

    pyserial's Windows timeout setter reapplies SetCommState, including baud,
    even during a pending packet write. Configure nonblocking reads once and
    wait here instead; use only the supported serial API.
    """
    def __init__(self, connection, *, clock=time.monotonic, sleep=time.sleep):
        self.connection = connection
        self.timeout = abi.WIRE_RESPONSE_TIMEOUT_MS / 1000
        self.clock = clock
        self.sleep = sleep

    def write(self, packet):
        return self.connection.write(packet)

    def read(self, count):
        deadline = self.clock() + self.timeout
        while True:
            if self.clock() >= deadline:
                return b''
            data = self.connection.read(count)
            if self.clock() >= deadline:
                return b''
            if data:
                return data
            remaining = deadline - self.clock()
            if remaining <= 0:
                return b''
            self.sleep(min(0.001, remaining))

    def close(self):
        self.connection.close()

    def observe(self, seconds):
        """CRC diagnostic silence window: never drop bytes returned at its edge."""
        deadline = self.clock() + seconds
        while True:
            data = self.connection.read(1)
            if data:
                return data
            remaining = deadline - self.clock()
            if remaining <= 0:
                return b''
            self.sleep(min(0.001, remaining))


def open_serial(port):
    import serial
    if serial.VERSION != '3.5':
        raise RuntimeError('install the pinned pyserial 3.5 dependency before serial access')
    connection = serial.Serial(port=None, baudrate=abi.WIRE_BAUD,
                               bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                               stopbits=serial.STOPBITS_ONE, timeout=0,
                               write_timeout=abi.WIRE_RESPONSE_TIMEOUT_MS / 1000,
                               xonxoff=False, rtscts=False, dsrdtr=False)
    connection.dtr = False
    connection.rts = False
    connection.port = port
    try:
        connection.open()
    except Exception:
        connection.close()
        raise
    return SerialTransport(connection)


@contextmanager
def session(folder, args, state_root, *, discover=uart, opener=open_serial):
    selection = discover(folder, args)
    selected = selection.get('selected')
    if not selected:
        raise ValueError('explicit healthy Windows UART selection required before opening')
    # Discovery provides the same identity/health rules as doctor. Retain that
    # evidence privately and serialize across tags/worktrees using shared state.
    atomic_json(folder / 'device.json', selection)
    identity = selected['PNPDeviceID']
    key = hashlib.sha256(identity.casefold().encode()).hexdigest()
    state_root = Path(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    lock = state_root / (key + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, 'w') as stream:
        stream.write(f'pid={os.getpid()}\n')
    connection = None
    try:
        state_path = state_root / (key + '.json')
        state = json.loads(state_path.read_text()) if state_path.exists() else {'next_sequence': 0, 'pending': False}
        if args.endpoint_restarted:
            # Explicit operator statement: a separately completed endpoint global
            # reset invalidated outstanding effects/cache. No reset is sent here.
            state['pending'] = False
            atomic_json(state_path, state)
        if state['pending']:
            raise RuntimeError('previous completion is uncertain; recover the endpoint session explicitly before opening')
        def persist(sequence, pending):
            atomic_json(state_path, {'next_sequence': sequence, 'pending': pending})
        connection = opener(selected['DeviceID'])
        yield connection, state['next_sequence'], persist, selected
    finally:
        if connection is not None:
            connection.close()
        lock.unlink()

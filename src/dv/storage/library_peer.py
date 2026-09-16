"""The product library loader over the simulated UART bridge.

The builder starts this peer beside the Verilator run. It packages our own
software targets with the ordinary `sw build` stage into the attempt folder,
admits them through the host tool's immutable package reader, and drives
`library.load_library` and `library.read_catalogue` with the live Client, so
the bytes on the wire are exactly what `host library load` sends to a board.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

# Slots 0..N-1 and the menu image, all built from src/sw/targets.json.
SLOT_TARGETS = ('linker-basic', 'assets-basic')
MENU_TARGET = 'v05'


class Transport:
    """Byte transport over the bridge's TX/RX line protocol; sim time is the clock."""
    def __init__(self, channel):
        self.channel = channel
        self.pending = bytearray()
        self.sim_time = 0.0
        self.timeout = 1.0

    def send(self, line):
        self.channel.write((line + '\n').encode('ascii'))
        self.channel.flush()

    def receive(self, kind):
        raw = self.channel.readline(4096)
        if not raw.endswith(b'\n'):
            raise OSError('simulation bridge closed or oversized reply')
        fields = raw.decode('ascii').strip().split()
        if len(fields) < 2 or fields[0] != kind:
            raise ValueError('unexpected simulation bridge response')
        self.sim_time = int(fields[1]) * 1e-9
        return fields[2:]

    def write(self, data):
        if self.pending:
            raise ValueError('unconsumed simulated reply')
        self.send('TX ' + data.hex())
        return len(data)

    def read(self, count):
        if count != 1:
            raise ValueError('only bounded byte reads are supported')
        if not self.pending:
            fields = self.receive('RX')
            if len(fields) != 1:
                raise ValueError('missing serial response bytes')
            self.pending.extend(bytes.fromhex(fields[0]))
        if not self.pending:
            raise ValueError('empty serial response')
        return bytes([self.pending.pop(0)])


def packages(root, attempt):
    """Build every fixture target into the attempt and admit it as a host package."""
    from n2m.host.package import read_package
    from sw.rom_build import build_target
    admitted = []
    for target in (*SLOT_TARGETS, MENU_TARGET):
        built = build_target(root, attempt, SimpleNamespace(target=target, rebuild=True), {})
        if built['status'] != 'PASS':
            raise RuntimeError(f"sw build {target} failed: {built.get('error')}")
        admitted.append(read_package(root, (root / built['rom']).parent / 'result.json'))
    return admitted[:-1], admitted[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--attempt', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / 'tools'))
    from n2m.host import library
    from n2m.host.client import Client
    slots, menu = packages(args.root, args.attempt)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(30)
        ready = args.attempt / 'peer-ready.json'
        temporary = args.attempt / 'peer-ready.tmp'
        temporary.write_text(json.dumps({'host': '127.0.0.1', 'port': listener.getsockname()[1]}))
        temporary.replace(ready)
        connection, address = listener.accept()
        if address[0] != '127.0.0.1':
            raise OSError('non-loopback simulation client')
        with connection, connection.makefile('rwb') as channel:
            # Wall time bounds a stalled bridge; Client separately checks its
            # generated response budget against returned simulation time.
            connection.settimeout(120)
            transport = Transport(channel)
            records = []
            client = Client(transport, clock=lambda: transport.sim_time, record=records.append)
            progress = []
            try:
                identity = client.identify()
                result = library.load_library(
                    client, [(image, metadata['profile']) for image, metadata in slots],
                    (menu[0], menu[1]['profile']), progress=progress.append)
                raw, rows = library.read_catalogue(client)
                (args.attempt / 'catalogue.bin').write_bytes(raw)
                expected = library.build_catalogue({index: library.image_entry(image, library.profile_id(metadata['profile']))
                                                    for index, (image, metadata) in enumerate([*slots])}
                                                   | {library.MENU_INDEX: library.image_entry(menu[0], library.profile_id(menu[1]['profile']))})
                if result['mismatch_count']:
                    transport.send('FAIL LIBRARY_MISMATCH')
                    raise RuntimeError('library readback mismatch: ' + ', '.join(result['mismatches']))
                if raw != expected:
                    transport.send('FAIL LIBRARY_STATUS_CATALOGUE')
                    raise RuntimeError('host library status read a catalogue differing from the one written')
                # `host library return`: the whitelisted LIBRARY_CONTROL write on the
                # wire. This fixture has no loader, so LIBRARY_STATUS reads as the
                # driven zero word; the testbench counts the endpoint's return pulse.
                try:
                    returned = library.return_to_menu(client)
                except Exception:
                    transport.send('FAIL LIBRARY_RETURN_REFUSED')
                    raise
                if returned['library_status']['word'] != 0 or returned['endpoint']['state_name'] == 'LOADING':
                    transport.send('FAIL LIBRARY_RETURN_STATUS')
                    raise RuntimeError('host library return read an unexpected status or endpoint state')
            finally:
                (args.attempt / 'client.json').write_text(json.dumps({'requests': records}, indent=2) + '\n')
                (args.attempt / 'library-progress.json').write_text(json.dumps(progress) + '\n')
            (args.attempt / 'library.json').write_text(json.dumps(
                {'identity': identity, 'load': result, 'status': rows, 'return': returned,
                 'packages': {library.slot_name(i): m for i, (_img, m) in enumerate(slots)} | {'menu': menu[1]}},
                indent=2) + '\n')
            transport.send('DONE')
    print(f"PASS library peer live Client images={len(slots) + 1} slots={len(slots)} "
          f"verified={result['images']} status_rows={len(rows)} return={returned['endpoint']['state_name']}", flush=True)


if __name__ == '__main__':
    main()

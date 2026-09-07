"""Live product Client over a byte-only simulated UART bridge."""
import argparse
import json
from pathlib import Path
import socket
import sys

from image import build


class Transport:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--attempt', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / 'tools'))
    from n2m.host.client import Client
    from n2m import generated_interfaces as abi
    image = build(args.root, args.attempt)
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
            from n2m.host_play import play, PlayFailure
            from n2m.host.client import RejectedCommand
            def wait(dots):
                connection.settimeout(300)
                try:
                    transport.send('WAIT ' + str(dots))
                    transport.receive('WAITED')
                finally:
                    connection.settimeout(120)
            def retain(stage, item, packed, pixels):
                (args.attempt / f'frame-{stage}.2bpp').write_bytes(packed)
                grayscale = bytes(255 - value * 85 for value in pixels)
                (args.attempt / f'frame-{stage}.pgm').write_bytes(b'P5\n160 144\n255\n' + grayscale)
                (args.attempt / f'frame-{stage}.json').write_text(json.dumps(item, indent=2) + '\n')
            try:
                result = play(client, image, wait, retain, expected_epoch=2)
            except (PlayFailure, RejectedCommand) as error:
                (args.attempt / 'play-error.json').write_text(json.dumps({'error': str(error), 'requests': records}, indent=2))
                if isinstance(error, RejectedCommand) and (error.command != 'SNAPSHOT' or error.status != abi.STATUS_NO_FRAME):
                    raise
                reason = str(error).split()[0] if isinstance(error, PlayFailure) else 'PLAY_MISSING_FRAME'
                transport.send('FAIL ' + reason)
                raise
            finally:
                (args.attempt / 'client.json').write_text(json.dumps({'requests': records}, indent=2) + '\n')
            (args.attempt / 'play.json').write_text(json.dumps(result, indent=2) + '\n')
            transport.send('DONE')
    print('PASS host play live Client five images', flush=True)


if __name__ == '__main__':
    main()

"""Live product Client over a byte-only simulated UART bridge."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

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


def main(*, preloaded=False):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--attempt', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / 'tools'))
    from n2m.host.client import Client
    from n2m import generated_interfaces as abi
    image = build(args.root, args.attempt)
    if preloaded:
        from n2m.preload import prepare
        preload = prepare(image, hashlib.sha256((args.attempt / 'program.gb').read_bytes()).hexdigest(), args.attempt)
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
            identity = client.identify()
            setup_wall = time.monotonic()
            setup_sim = transport.sim_time
            if preloaded:
                from n2m.preload import adopt
                loaded = adopt(client, preload)
            else:
                loaded = client.load(image)
                from n2m.preload import observe_initial
                loaded['initial_state'] = observe_initial(client)
            timings = {'setup_wall_seconds': time.monotonic() - setup_wall,
                       'setup_sim_seconds': transport.sim_time - setup_sim}
            execution_wall = time.monotonic()
            execution_sim = transport.sim_time
            client.control('INPUT', 0)
            client.control('RUN')
            transport.send('WAIT 136280')
            transport.receive('WAITED')
            client.control('HALT')
            if client.read_host(abi.HOST_REG_STATE) != abi.STATE_PAUSED:
                raise ValueError('integration did not pause after selected frame')
            timings.update(execution_wall_seconds=time.monotonic() - execution_wall,
                           execution_sim_seconds=transport.sim_time - execution_sim)
            result = {'identity': identity, 'load': loaded, 'requests': records, 'timings': timings}
            (args.attempt / 'client.json').write_text(json.dumps(result, indent=2) + '\n')
            transport.send('DONE')
    print('PASS integration live Client load and control', flush=True)


if __name__ == '__main__':
    main()

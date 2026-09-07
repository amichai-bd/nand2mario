"""Prepare the pipeline image for the bounded installed-model loader fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--attempt', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / 'tools'))
    sys.path.insert(0, str(args.root / 'src/dv/integration'))
    from image import build
    from n2m.preload import prepare
    image = build(args.root, args.attempt)
    prepare(image, hashlib.sha256((args.attempt / 'program.gb').read_bytes()).hexdigest(), args.attempt)
    (args.attempt / 'preload-bytes.hex').write_text(''.join(f'{value:02x}\n' for value in image), encoding='ascii')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(30)
        ready = args.attempt / 'peer-ready.json'
        temporary = args.attempt / 'peer-ready.tmp'
        temporary.write_text(json.dumps({'host': '127.0.0.1', 'port': listener.getsockname()[1]}))
        temporary.replace(ready)
        connection, address = listener.accept()
        with connection:
            if address[0] != '127.0.0.1':
                raise ValueError('non-loopback preparation acknowledgement')
    print('PASS preload preparation acknowledged; runtime result is separate', flush=True)


if __name__ == '__main__':
    main()

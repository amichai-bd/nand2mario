"""Python peer for the Verilator peer fixture: known requests through the live bridge."""
import argparse
import json
from pathlib import Path
import socket
import sys
import time

# Request lengths cover a single byte, an ordinary packet and the 271-byte
# maximum whose zero-terminated reply fills the 272-byte mailbox.
LENGTHS = (1, 19, 271)


def exchange(channel, line, kind):
    channel.write((line + "\n").encode("ascii"))
    channel.flush()
    raw = channel.readline(4096)
    if not raw.endswith(b"\n"):
        raise OSError("simulation bridge closed or oversized reply")
    fields = raw.decode("ascii").strip().split()
    if len(fields) < 2 or fields[0] != kind:
        raise ValueError(f"unexpected simulation bridge response: {raw!r}")
    return int(fields[1]), fields[2:]


def main(*, fault=False):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(30)
        ready = args.attempt / "peer-ready.json"
        temporary = args.attempt / "peer-ready.tmp"
        temporary.write_text(json.dumps({"host": "127.0.0.1", "port": listener.getsockname()[1]}))
        temporary.replace(ready)
        connection, address = listener.accept()
        if address[0] != "127.0.0.1":
            raise OSError("non-loopback simulation client")
        with connection, connection.makefile("rwb") as channel:
            connection.settimeout(120)
            records = []
            last_ns = -1
            for index, length in enumerate(LENGTHS):
                payload = bytes((index * 37 + n * 11) % 255 + 1 for n in range(length))
                sim_ns, fields = exchange(channel, "TX " + payload.hex(), "RX")
                if len(fields) != 1:
                    raise ValueError("missing serial response bytes")
                reply = bytes.fromhex(fields[0])
                expected = bytes(byte ^ 0x5A for byte in payload) + b"\0"
                if reply != expected:
                    raise ValueError(f"PEER_CHECK_REPLY index={index} expected={expected.hex()} actual={reply.hex()}")
                if sim_ns <= last_ns:
                    raise ValueError(f"PEER_CHECK_TIME index={index} previous={last_ns} actual={sim_ns}")
                last_ns = sim_ns
                records.append({"index": index, "request": payload.hex(), "reply": reply.hex(), "sim_ns": sim_ns})
                if fault and index == 0:
                    # A WAIT outside the declared set is a protocol fault the
                    # driver must report by name; the bridge then closes.
                    exchange(channel, "WAIT 5", "WAITED")
            sim_ns, fields = exchange(channel, "WAIT 136280", "WAITED")
            if sim_ns <= last_ns or fields:
                raise ValueError(f"PEER_CHECK_WAIT previous={last_ns} actual={sim_ns}")
            records.append({"wait": 136280, "sim_ns": sim_ns})
            (args.attempt / "client.json").write_text(json.dumps(
                {"requests": records, "timings": {"wall_seconds": time.monotonic() - started}}, indent=2) + "\n")
            channel.write(b"DONE\n")
            channel.flush()
    print(f"PASS peer-check transactions={len(LENGTHS)} waits=1", flush=True)


if __name__ == "__main__":
    main()

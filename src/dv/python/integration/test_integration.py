"""Public-pin reproduction of the preloaded run-control diagnostic (#174)."""
import json
from datetime import datetime, timezone
from pathlib import Path
import struct
import sys
import zlib

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time
from cocotb.queue import Queue

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
from n2m.generated_interfaces import RECORDS
# Re-exported for the testbenches that import it from here.
from n2m.interface_codec import decode_record


def packet(sequence, command, payload=b""):
    """Independent wire encoding: little-endian header, CCITT CRC and COBS."""
    raw = struct.pack("<BBIBBH", 1, 0, sequence, command, 0, len(payload)) + payload
    crc = 0xffff
    for byte in raw:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    raw += crc.to_bytes(2, "little")
    encoded = bytearray([0])
    position, count = 0, 1
    for byte in raw:
        if byte:
            encoded.append(byte)
            count += 1
        if not byte or count == 255:
            encoded[position] = count
            position, count = len(encoded), 1
            encoded.append(0)
    encoded[position] = count
    return bytes(encoded) + b"\0"


def requests(image):
    # Timestamps select the retained bare diagnostic, not the live Client path.
    plan = [(1000, 1, b"")]
    for index, address in enumerate((0, 0x30, 0x34, 0x38, 0x3c)):
        plan.append((201000 + index * 200000, 2, struct.pack("<I", 0x10000 + address)))
    plan += [(1201000, 7, struct.pack("<BII", 1, len(image), zlib.crc32(image))),
             (1701000, 9, b"")]
    for index, address in enumerate((4, 8, 12, 16, 20, 24, 28, 32, 68, 76, 36)):
        plan.append((4801000 + index * 200000, 2, struct.pack("<I", 0x10000 + address)))
    return plan + [(150001000, 11, b"\0"), (150201000, 4, b"")]


def response(frame):
    raw = bytearray()
    offset = 0
    while offset < len(frame):
        count = frame[offset]
        assert count and offset + count <= len(frame), "INTEGRATION_RESPONSE_COBS"
        raw.extend(frame[offset + 1:offset + count])
        offset += count
        if count != 255 and offset < len(frame):
            raw.append(0)
    assert len(raw) >= 12, "INTEGRATION_RESPONSE_SIZE"
    version, kind, sequence, command, status, length = struct.unpack("<BBIBBH", raw[:10])
    crc = 0xffff
    for byte in raw[:-2]:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    assert crc == int.from_bytes(raw[-2:], "little"), "INTEGRATION_RESPONSE_CRC"
    assert (version, kind, status, len(raw) - 12) == (1, 1, 0, length), "INTEGRATION_RESPONSE_HEADER"
    return sequence, command, raw[10:-2].hex()


def known(signal):
    value = signal.value
    assert value.is_resolvable, f"INTEGRATION_UNKNOWN signal={signal._name} value={value}"
    return int(value)


async def run_contract(dut, *, real_uart=False, client_preloaded=False):
    test_entry = datetime.now(timezone.utc).isoformat()
    expected = json.loads((ROOT / "src/dv/integration/retirement.json").read_text())
    assert len(expected) == 69 and expected[0]["fields"]["dot"] == 8
    assert expected[-1]["fields"]["dot"] == 600
    if real_uart and not client_preloaded:
        sys.path.insert(0, str(ROOT / "src/dv/integration"))
        from image import build
        build(ROOT, Path.cwd())
    image = Path("program.gb").read_bytes()
    counts = dict(records=0, pixels=0, bus=0)
    writes = []
    replies = []
    received = Queue()
    with Path("transactions.jsonl").open("w") as trace, \
         Path("retirement.csv").open("w") as records, \
         Path("pixels.csv").open("w") as pixels, Path("bus.csv").open("w") as bus:
        records.write("seq,record\n")
        pixels.write("frame,index,dot,shade\n")
        bus.write("dot,address,write,data\n")

        def observation(kind, **values):
            trace.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit="ps")), **values)) + "\n")

        async def monitor_record():
            while True:
                await ValueChange(dut.record_event)
                await ReadOnly()
                raw = known(dut.record_sample)
                actual = decode_record(raw)
                index = counts["records"]
                assert index < len(expected), "INTEGRATION_EXTRA_RECORD"
                observation("retirement", expected=expected[index]["fields"], actual=actual)
                assert actual == expected[index]["fields"], f"INTEGRATION_RECORD seq={index} expected={expected[index]['fields']} actual={actual}"
                records.write(f"{index},{raw:096x}\n")
                counts["records"] += 1

        async def monitor_pixel():
            while True:
                await ValueChange(dut.pixel_event)
                await ReadOnly()
                raw = known(dut.pixel_sample)
                eligible, abort, start = raw & 1, (raw >> 1) & 1, (raw >> 2) & 1
                shade, y, x = (raw >> 3) & 3, (raw >> 5) & 255, (raw >> 13) & 255
                epoch, dot = (raw >> 21) & 0xffffffff, raw >> 53
                frame, index = divmod(counts["pixels"], 23040)
                want = 0 if frame == 0 else index % 4
                actual = dict(frame=frame, index=index, dot=dot, shade=shade, x=x, y=y,
                              epoch=epoch, start=start, abort=abort, eligible=eligible)
                observation("pixel", expected_shade=want, actual=actual)
                assert frame < 2 and (x, y, epoch, start, abort, eligible) == (index % 160, index // 160, 2, int(index == 0), 0, frame), f"INTEGRATION_PIXEL_ORDER {actual}"
                assert shade == want, f"INTEGRATION_PIXEL frame={frame} index={index} expected={want} actual={shade}"
                if frame == 1:
                    assert dot == 70908 + 456 * y + x, f"INTEGRATION_PIXEL_DOT {actual}"
                pixels.write(f"{frame},{index},{dot},{shade}\n")
                counts["pixels"] += 1

        async def monitor_bus():
            while True:
                await ValueChange(dut.bus_event)
                await ReadOnly()
                raw = known(dut.bus_sample)
                data, write, address, dot = raw & 255, (raw >> 8) & 1, (raw >> 9) & 65535, raw >> 25
                observation("bus", dot=dot, address=address, write=write, data=data)
                bus.write(f"{dot},{address:04x},{write},{data:02x}\n")
                if write:
                    writes.append((address, data))
                counts["bus"] += 1

        async def monitor_uart():
            from client_transport import frames
            async for encoded in frames(dut):
                decoded = response(encoded[:-1])
                observation("response", encoded=encoded.hex(), decoded=decoded)
                assert decoded[0] == len(replies), "INTEGRATION_RESPONSE_SEQUENCE"
                replies.append(decoded)
                received.put_nowait(encoded)

        # HDL initial assignments can produce event-toggle transitions at time
        # zero. Arm only after they settle while reset is still asserted.
        await Timer(1, unit="ns")
        tasks = [cocotb.start_soon(fn()) for fn in (monitor_record, monitor_pixel, monitor_bus, monitor_uart)]
        await Timer(319, unit="ns")
        dut.reset_sys.value = 0
        observation("reset", asserted=0)
        if real_uart:
            from client_transport import execute
            await execute(dut, image, received, observation, counts,
                          preloaded=client_preloaded, test_entry=test_entry)
        else:
            for sequence, (time_ns, command, payload) in enumerate(requests(image)):
                await Timer(time_ns * 1000 + 1 - int(get_sim_time(unit="ps")), unit="ps")
                if sequence == 19:
                    assert (known(dut.epoch), known(dut.dot_count), known(dut.paused)) == (2, 0, 1), "INTEGRATION_INITIAL_STATE"
                    assert counts == dict(records=0, pixels=0, bus=0), "INTEGRATION_PAUSED_ACTIVITY"
                encoded = packet(sequence, command, payload)
                observation("request", sequence=sequence, command=command, payload=payload.hex(), encoded=encoded.hex())
                # Original starts on the next falling clock edge. Byte-to-byte has
                # one extra system edge after the ten serial bits.
                start_ns = time_ns + 40
                for index, byte in enumerate(encoded):
                    for bit, value in enumerate([0, *[(byte >> n) & 1 for n in range(8)], 1]):
                        when = (start_ns + index * 3240 + bit * 320) * 1000
                        await Timer(when - int(get_sim_time(unit="ps")), unit="ps")
                        dut.uart_rx.value = value
                        await ReadOnly()
                        actual = known(dut.uart_rx)
                        observation("uart_rx", sequence=sequence, byte=index, bit=bit, intended=value, actual=actual)
                        assert actual == value, "INTEGRATION_DRIVE_MISMATCH"
            # Polling is in simulation time and does not invoke finite simulator runs.
            while known(dut.dot_count) < 136280:
                await Timer(1, unit="us")
                assert not known(dut.fault), "INTEGRATION_OWNER_FAULT"
        for task in tasks:
            if task.done():
                task.result()
            task.cancel()
        assert counts == dict(records=69, pixels=46080, bus=145), f"INTEGRATION_COUNTS {counts}"
        if not real_uart:
            assert len(replies) == 21 and replies[-1][1] == 4, f"INTEGRATION_REPLIES {replies}"
        selected = [(address, data) for address, data in writes if 0xc000 <= address <= 0xc002]
        assert selected == [(0xc000, 0x3c), (0xc001, 0x41), (0xc002, 0xa7)], f"INTEGRATION_RAM {selected}"
        assert [(a, d) for a, d in writes if 0xdffa <= a <= 0xdffd] == [(0xdffd, 2), (0xdffc, 0x22), (0xdffb, 1), (0xdffa, 0x20)], "INTEGRATION_STACK"
        assert [(a, d) for a, d in writes if 0x8000 <= a <= 0x800f] == [(0x8000 + i, 0x55 if i % 2 == 0 else 0x33) for i in range(16)], "INTEGRATION_TILE"
        observation("complete", counts=counts, dot=known(dut.dot_count))
    dut._log.info("PASS python-integration records=69 pixels=46080 bus=145")


@cocotb.test(timeout_time=210, timeout_unit="ms")
async def integration_contract(dut):
    await run_contract(dut)

"""Product Client adapter over actual UART pins, with simulation-time waits."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time

from cocotb.task import bridge, resume
from cocotb.triggers import FallingEdge, ReadOnly, Timer, with_timeout
from cocotb.utils import get_sim_time

from n2m import generated_interfaces as abi
from n2m.preload import adopt, observe_initial, verify


async def frames(dut):
    """Receive complete encoded responses at the existing eight-clock bit rate."""
    frame = bytearray()
    while True:
        await FallingEdge(dut.uart_tx)
        await Timer(480, unit="ns")
        byte = 0
        for bit in range(8):
            await ReadOnly()
            assert dut.uart_tx.value.is_resolvable, "INTEGRATION_RESPONSE_UNKNOWN"
            byte |= int(dut.uart_tx.value) << bit
            await Timer(320, unit="ns")
        await ReadOnly()
        assert int(dut.uart_tx.value) == 1, "INTEGRATION_RESPONSE_STOP"
        if byte:
            frame.append(byte)
            assert len(frame) < 272, "INTEGRATION_RESPONSE_BOUND"
        else:
            yield bytes(frame) + b"\0"
            frame.clear()


def connect(dut, received, observation, entries):
    from n2m.host.client import Client

    class Transport:
        def __init__(self):
            self.pending = bytearray()
            self.timeout = abi.WIRE_RESPONSE_TIMEOUT_MS / 1000
            self.sim_time = float(get_sim_time(unit="sec"))

        @resume
        async def exchange(self, packet):
            assert received.empty(), "INTEGRATION_UNCONSUMED_RESPONSE"
            # Start after the next falling edge, in a writable simulation phase.
            now = int(get_sim_time(unit="ps"))
            start = (now // 40000 + 1) * 40000 + 1
            observation("client_request", encoded=packet.hex())
            for index, byte in enumerate(packet):
                for bit, value in enumerate([0, *[(byte >> n) & 1 for n in range(8)], 1]):
                    when = start + index * 3240000 + bit * 320000
                    await Timer(when - int(get_sim_time(unit="ps")), unit="ps")
                    dut.uart_rx.value = value
                    await ReadOnly()
                    assert int(dut.uart_rx.value) == value, "INTEGRATION_DRIVE_MISMATCH"
                    observation("uart_rx", byte=index, bit=bit, intended=value, actual=value)
            # Finish the complete stop bit before returning control to Client.
            await Timer(start + len(packet) * 3240000 - int(get_sim_time(unit="ps")), unit="ps")
            reply = await with_timeout(received.get(), abi.WIRE_RESPONSE_TIMEOUT_MS, "ms")
            self.sim_time = float(get_sim_time(unit="sec"))
            observation("client_wire_reply", encoded=reply.hex())
            return reply

        def write(self, packet):
            assert not self.pending, "INTEGRATION_UNREAD_RESPONSE"
            self.pending.extend(self.exchange(packet))
            return len(packet)

        def read(self, count):
            assert count == 1, "INTEGRATION_READ_SIZE"
            assert self.pending, "INTEGRATION_MISSING_RESPONSE"
            return bytes([self.pending.pop(0)])

    transport = Transport()
    client = Client(transport, clock=lambda: transport.sim_time, record=entries.append)
    return client


async def execute(dut, image, received, observation, counts, *, preloaded=False, test_entry=None):
    started = time.monotonic()
    entries = []
    stamps = {'test_entry': test_entry or datetime.now(timezone.utc).isoformat()}

    client = connect(dut, received, observation, entries)

    @bridge
    def load():
        stamps['loader_start'] = datetime.now(timezone.utc).isoformat()
        identity = client.identify()
        if preloaded:
            loaded = adopt(client, verify(Path.cwd()))
            initial = loaded['initial_state']
        else:
            loaded = client.load(image)
            initial = observe_initial(client)
        return identity, loaded, initial

    identity, loaded, initial = await load()
    await Timer(1, unit="ns")
    await ReadOnly()
    assert (int(dut.epoch.value), int(dut.dot_count.value), int(dut.paused.value),
            int(dut.core_reset.value)) == (2, 0, 1, 0), "INTEGRATION_INITIAL_STATE"
    assert counts == dict(records=0, pixels=0, bus=0), "INTEGRATION_PAUSED_ACTIVITY"
    boundary = {name: int(getattr(dut, name).value) for name in ('reset_sys', 'core_reset', 'paused', 'fault')}
    boundary.update(counts)
    assert boundary == dict(reset_sys=0, core_reset=0, paused=1, fault=0, records=0, pixels=0, bus=0)
    loaded_wall = time.monotonic()
    stamps['loaded'] = datetime.now(timezone.utc).isoformat()
    observation("loaded", identity=identity, loaded=loaded, initial=initial)
    Path("initial-state.json").write_text(json.dumps(dict(epoch=2, public=initial,
        boundary=boundary, image_sha256=hashlib.sha256(image).hexdigest()), indent=2))

    @bridge
    def start():
        client.control("INPUT", 0)
        stamps['run'] = datetime.now(timezone.utc).isoformat()
        client.control("RUN")

    await start()
    while int(dut.dot_count.value) < 136280:
        await Timer(1, unit="us")
        assert not int(dut.fault.value), "INTEGRATION_OWNER_FAULT"

    @bridge
    def halt():
        client.control("HALT")
        assert client.read_host(abi.HOST_REG_STATE) == abi.STATE_PAUSED, "INTEGRATION_FINAL_STATE"

    await halt()
    await Timer(1, unit="ns")
    assert int(dut.paused.value) == 1, "INTEGRATION_FINAL_PAUSED"
    stamps['paused'] = datetime.now(timezone.utc).isoformat()
    Path("client.json").write_text(json.dumps(dict(identity=identity, load=loaded,
        initial=initial, requests=entries, final_dot=int(dut.dot_count.value),
        final_state=abi.STATE_PAUSED, checkpoints_utc=stamps,
        timings=dict(test_to_loaded_wall_seconds=loaded_wall-started,
                     loaded_to_paused_wall_seconds=time.monotonic()-loaded_wall)), indent=2))

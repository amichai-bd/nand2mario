"""Product Client adapter over actual UART pins, with simulation-time waits."""
from pathlib import Path
import json
import time

from cocotb.task import bridge, resume
from cocotb.triggers import ReadOnly, Timer, with_timeout
from cocotb.utils import get_sim_time

from n2m import generated_interfaces as abi
from n2m.host.client import Client
from n2m.preload import observe_initial


async def execute(dut, image, received, observation, counts):
    started = time.monotonic()
    entries = []

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

    @bridge
    def load():
        identity = client.identify()
        loaded = client.load(image)
        initial = observe_initial(client)
        return identity, loaded, initial

    identity, loaded, initial = await load()
    await Timer(1, unit="ns")
    await ReadOnly()
    assert (int(dut.epoch.value), int(dut.dot_count.value), int(dut.paused.value),
            int(dut.core_reset.value)) == (2, 0, 1, 0), "INTEGRATION_INITIAL_STATE"
    assert counts == dict(records=0, pixels=0, bus=0), "INTEGRATION_PAUSED_ACTIVITY"
    loaded_wall = time.monotonic()
    observation("loaded", identity=identity, loaded=loaded, initial=initial)
    Path("initial-state.json").write_text(json.dumps(dict(epoch=2, public=initial, load=loaded), indent=2))

    @bridge
    def start():
        client.control("INPUT", 0)
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
    Path("client.json").write_text(json.dumps(dict(identity=identity, load=loaded,
        initial=initial, requests=entries, final_dot=int(dut.dot_count.value),
        timings=dict(test_to_loaded_wall_seconds=loaded_wall-started,
                     loaded_to_paused_wall_seconds=time.monotonic()-loaded_wall)), indent=2))

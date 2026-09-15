"""Byte-only live bridge between the builder's Python peer and a Verilator run.

The Verilator peer replaces the Questa Tcl driver. It speaks the unchanged
line protocol to the unchanged Python peer (TX/RX, WAIT/WAITED, DONE) and
touches only the top-level signals named in the target's `driver.access`
list. Protocol faults are raised by name; the builder reports the name.
"""
import re
import socket
import time

TX = re.compile(r"^TX ([0-9a-f]+)$")
WAIT = re.compile(r"^WAIT ([0-9]+)$")
FAIL = re.compile(r"^FAIL ([A-Z][A-Z_]*)$")
MAILBOX = 272
LINE_SIZE = 1024
PEER_IDLE_SECONDS = 30
RESPONSE_SECONDS = 120


class Access:
    """Observe and deposit only the declared top-level DV objects."""

    def __init__(self, dut, names):
        self.handles = {}
        for name in names:
            try:
                self.handles[name] = getattr(dut, name)
            except AttributeError:
                raise RuntimeError(f"SMOKE_DRIVER_ACCESS {name}") from None

    def handle(self, name, index=None):
        if name not in self.handles:
            raise RuntimeError(f"SMOKE_DRIVER_ACCESS {name}")
        return self.handles[name] if index is None else self.handles[name][index]

    def observe(self, name, index=None):
        value = self.handle(name, index).value
        if not value.is_resolvable:
            raise RuntimeError(f"SMOKE_DRIVER_UNKNOWN {name}")
        return int(value)

    def deposit(self, name, value, index=None):
        self.handle(name, index).value = value


class Bridge:
    """The protocol, independent of cocotb: the caller supplies access and time.

    `advance` is an awaitable step of simulation time between polls; `clock`
    is the wall clock in seconds.
    """

    def __init__(self, access, advance, *, waits, relative=False, fail_prefix=None, settle=None,
                 wait_seconds=RESPONSE_SECONDS, clock=time.monotonic, progress_log=None):
        self.access, self.advance, self.clock = access, advance, clock
        self.settle = settle
        self.waits, self.relative, self.fail_prefix = set(waits), relative, fail_prefix
        self.wait_seconds, self.progress_log = wait_seconds, progress_log
        self.ordinal = 0
        self.started = clock()
        self.transactions = []

    def progress(self, phase):
        fields = {name: self.access.observe(name) for name in
                  ("simulation_ns", "dot_count", "tx_count", "tx_busy", "rx_count", "rx_done")}
        line = (f"SMOKE_DRIVER phase={phase} ordinal={self.ordinal} "
                f"wall_ms={int((self.clock() - self.started) * 1000)} sim_ns={fields['simulation_ns']} "
                f"dot={fields['dot_count']} tx_count={fields['tx_count']} tx_busy={fields['tx_busy']} "
                f"rx_count={fields['rx_count']} rx_done={fields['rx_done']}")
        print(line, flush=True)
        if self.progress_log is not None:
            self.progress_log.write(line + "\n")
            self.progress_log.flush()

    async def bounded_wait(self, condition, seconds):
        deadline = self.clock() + seconds
        advances = 0
        while not condition():
            if self.clock() >= deadline:
                raise RuntimeError("SMOKE_DRIVER_RESPONSE_TIMEOUT")
            await self.advance()
            advances += 1
            if advances % 50 == 0:
                self.progress("waiting")

    async def transmit(self, hex_bytes):
        self.ordinal += 1
        self.progress("received")
        length = len(hex_bytes) // 2
        if len(hex_bytes) % 2 or not 1 <= length <= MAILBOX or self.access.observe("tx_busy"):
            raise RuntimeError("SMOKE_DRIVER_TX_SIZE")
        payload = bytes.fromhex(hex_bytes)
        self.access.deposit("rx_count", 0)
        self.access.deposit("rx_done", 0)
        for index, byte in enumerate(payload):
            self.access.deposit("tx_bytes", byte, index)
        self.access.deposit("tx_count", length)
        self.progress("prepared")
        self.access.deposit("tx_go", 1)
        if self.settle is not None:
            # Deposits apply at the end of this time step; observe them before
            # the first poll so a previous reply is never mistaken for this one.
            await self.settle()
        await self.bounded_wait(lambda: self.access.observe("rx_done") and not self.access.observe("tx_busy"),
                                RESPONSE_SECONDS)
        self.progress("response")
        count = self.access.observe("rx_count")
        if not 1 <= count <= MAILBOX:
            raise RuntimeError("SMOKE_DRIVER_RX_SIZE")
        reply = bytes(self.access.observe("rx_bytes", index) for index in range(count))
        self.progress("extracted")
        sim_ns = self.access.observe("simulation_ns")
        self.transactions.append({"ordinal": self.ordinal, "request": payload.hex(),
                                  "reply": reply.hex(), "sim_ns": sim_ns})
        return f"RX {sim_ns} {reply.hex()}"

    async def wait_dots(self, wanted):
        if wanted not in self.waits:
            raise RuntimeError("SMOKE_DRIVER_WAIT_RANGE")
        target = self.access.observe("dot_count") + wanted if self.relative else wanted
        self.progress("wait_start")
        await self.bounded_wait(lambda: self.access.observe("dot_count") >= target, self.wait_seconds)
        self.progress("wait_complete")
        return f"WAITED {self.access.observe('simulation_ns')}"

    async def handle(self, line):
        """Return the reply line, or None when the peer is done."""
        if len(line) > LINE_SIZE:
            raise RuntimeError("SMOKE_DRIVER_LINE_SIZE")
        if match := TX.match(line):
            return await self.transmit(match[1])
        if match := WAIT.match(line):
            return await self.wait_dots(int(match[1]))
        if self.fail_prefix and (match := FAIL.match(line)) and match[1].startswith(self.fail_prefix):
            raise RuntimeError(match[1])
        if line == "DONE":
            return None
        raise RuntimeError("SMOKE_DRIVER_MESSAGE")

    async def serve(self, channel):
        """Answer the peer until DONE, then request the testbench's completion."""
        # The first advance mirrors the retired driver's `run 1 us`.
        await self.advance(1)
        while True:
            line = read_line(channel)
            reply = await self.handle(line)
            if reply is None:
                break
            channel.write((reply + "\n").encode("ascii"))
            channel.flush()
        channel.close()
        self.access.deposit("finish_request", 1)
        # The testbench prints its signature and calls $finish inside this
        # window; the run ends when this test completes. A testbench that
        # never finishes leaves the signature missing, which fails the attempt.
        await self.advance(1)


def read_line(channel):
    """One ASCII line from the peer; the socket timeout bounds peer idle time."""
    try:
        raw = channel.readline(LINE_SIZE + 2)
    except socket.timeout:
        raise RuntimeError("SMOKE_DRIVER_PEER_TIMEOUT") from None
    if not raw:
        raise RuntimeError("SMOKE_DRIVER_PEER_EOF")
    if not raw.endswith(b"\n"):
        raise RuntimeError("SMOKE_DRIVER_LINE_SIZE")
    return raw[:-1].decode("ascii")


def connect(port):
    connection = socket.create_connection(("127.0.0.1", port), timeout=PEER_IDLE_SECONDS)
    connection.settimeout(PEER_IDLE_SECONDS)
    return connection


async def run(dut, **options):
    """The cocotb entry shared by the driver modules; one test per target."""
    import json
    import os
    from cocotb.triggers import ReadOnly, Timer

    access = Access(dut, [name for name in os.environ["N2M_DRIVER_ACCESS"].split(",") if name])

    async def advance(microseconds=100):
        await Timer(microseconds, unit="us")

    async def settle():
        await ReadOnly()

    progress_log = options.pop("progress_log", None)
    log = open(progress_log, "w", encoding="utf-8") if progress_log else None
    bridge = Bridge(access, advance, settle=settle, progress_log=log, **options)
    connection = connect(int(os.environ["N2M_PEER_PORT"]))
    try:
        with connection, connection.makefile("rwb") as channel:
            await bridge.serve(channel)
    finally:
        with open("driver-transactions.json", "w", encoding="utf-8") as stream:
            json.dump(bridge.transactions, stream, indent=2)
        if log is not None:
            log.close()

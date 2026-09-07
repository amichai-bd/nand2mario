"""Original five-image play contract over the unchanged continuous UART Client."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge, resume
from cocotb.triggers import ReadOnly, Timer
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src/dv/python/integration'))
sys.path.insert(0, str(ROOT / 'src/dv/host_play'))
from client_transport import connect, frames
from image import build
from n2m.host_play import play
from n2m.host.client import RejectedCommand
from n2m import generated_interfaces as abi


@cocotb.test(timeout_time=1, timeout_unit='sec')
async def host_play_contract(dut):
    started = time.monotonic()
    stamps = {'test_entry': datetime.now(timezone.utc).isoformat()}

    def mark(phase, **values):
        with Path('progress.jsonl').open('a') as progress:
            progress.write(json.dumps(dict(phase=phase, wall_seconds=time.monotonic()-started,
                                          **values))+'\n')
            progress.flush()

    mark('entry')
    image = build(ROOT, Path.cwd())
    mark('image_built', bytes=len(image))
    received = Queue()
    entries = []
    waits = []
    request_wall = None
    with Path('transactions.jsonl').open('w') as trace:
        def observation(kind, **values):
            nonlocal request_wall
            wall = time.monotonic()
            if kind == 'client_request':
                request_wall = wall
            elif kind == 'client_wire_reply':
                assert request_wall is not None and wall-request_wall <= 120, 'PLAY_RESPONSE_WALL_BOUND'
            trace.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit='ps')), **values)) + '\n')

        async def receive():
            async for encoded in frames(dut):
                observation('uart_response', encoded=encoded.hex())
                received.put_nowait(encoded)

        async def guard():
            last = time.monotonic()
            while True:
                await Timer(1, unit='us')
                await ReadOnly()
                assert int(dut.fault.value) == 0, 'PLAY_OWNER_FAULT'
                assert int(dut.dot_count.value) <= 1000000, 'PLAY_DOT_TIMEOUT'
                if time.monotonic()-last >= 30:
                    mark('heartbeat', simulation_ns=int(get_sim_time(unit='ns')),
                         dot=int(dut.dot_count.value), completed_waits=len(waits))
                    last = time.monotonic()

        await Timer(320, unit='ns')
        dut.reset_sys.value = 0
        mark('reset_released')
        observation('reset', asserted=0)
        receiver = cocotb.start_soon(receive())
        watcher = cocotb.start_soon(guard())
        client = connect(dut, received, observation, entries)

        @resume
        async def wait(dots):
            assert dots == (200000 if not waits else 150000), 'PLAY_WAIT_RANGE'
            begin = int(dut.dot_count.value)
            wall = time.monotonic()
            mark('wait_start', stage=len(waits), dot=begin, requested=dots)
            while int(dut.dot_count.value) < begin+dots:
                await Timer(1, unit='us')
                assert time.monotonic()-wall <= 300, 'PLAY_WAIT_WALL_BOUND'
            item = dict(start=begin, requested=dots, finish=int(dut.dot_count.value),
                        wall_seconds=time.monotonic()-wall)
            waits.append(item)
            observation('waited', **item)
            mark('wait_complete', stage=len(waits)-1, start=begin,
                 finish=item['finish'], requested=dots, wait_wall_seconds=item['wall_seconds'])

        def retain(stage, item, packed, pixels):
            Path(f'frame-{stage}.2bpp').write_bytes(packed)
            grayscale = bytes(255-value*85 for value in pixels)
            Path(f'frame-{stage}.pgm').write_bytes(b'P5\n160 144\n255\n'+grayscale)
            Path(f'frame-{stage}.json').write_text(json.dumps(item, indent=2)+'\n')
            if 'object' in item:
                mark('image_checked', stage=stage, object=item['object'], frame=item['frame'])

        @bridge
        def scenario():
            return play(client, image, wait, retain, expected_epoch=2)

        try:
            mark('scenario_start')
            result = await scenario()
            await Timer(1, unit='ns')
            assert int(dut.paused.value) == 1 and int(dut.epoch.value) == 2, 'PLAY_COMPLETION'
            assert len(result['observations']) == 5 and len(waits) == 5, 'PLAY_OBSERVATION_COUNT'
            assert sum(item['requested'] for item in waits) == 800000, 'PLAY_WAIT_TOTAL'
            stamps['paused'] = datetime.now(timezone.utc).isoformat()
            Path('play.json').write_text(json.dumps(dict(result=result, waits=waits,
                checkpoints_utc=stamps, wall_seconds=time.monotonic()-started), indent=2))
            mark('complete')
        except Exception as error:
            mark('failure', error=str(error))
            Path('play-error.json').write_text(json.dumps({'error': str(error), 'waits': waits}, indent=2))
            if (isinstance(error, RejectedCommand) and error.command == 'SNAPSHOT' and
                    error.status == abi.STATUS_NO_FRAME):
                raise AssertionError('PLAY_MISSING_FRAME') from error
            raise
        finally:
            Path('client.json').write_text(json.dumps({'requests': entries}, indent=2))
            for task in (receiver, watcher):
                if task.done():
                    task.result()
                task.cancel()
    dut._log.info('PASS python-host-play five immutable images four transitions')

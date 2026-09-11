"""Complete paused frame batches; expectations are supplied before UART access.

Bound to the retired image `b551c562...8ba667` (`BASELINE_ROM`) and its LCD
anchor 76964; it refuses the image the repository builds today, whose paused
captures are `frame_proofs.py`.
"""
import hashlib
import json
from pathlib import Path

from n2m import generated_interfaces as abi
from n2m.records import atomic_json, file_hash

LCD = 76964
BASELINE_ROM = 'b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667'
PERIOD = 70224
PIXELS = 23040


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_plan(plan, reference):
    captures = plan['captures']
    assert captures and plan['normal_frames'] == len(captures), 'CAPTURE_PLAN_COUNT'
    assert len(reference) == (len(captures)+2)*PIXELS and all(v < 4 for v in reference), 'CAPTURE_REFERENCE_SIZE'
    inputs = []
    for index, row in enumerate(captures):
        assert set(row) == {'seq', 'pause_dot', 'reference_offset', 'input_after'}, 'CAPTURE_PLAN_FIELDS'
        assert row['seq'] == index and row['pause_dot'] == LCD+(index+1)*PERIOD+4096, 'CAPTURE_PLAN_INDEX'
        assert row['reference_offset'] == (index+2)*PIXELS, 'CAPTURE_PLAN_REFERENCE'
        mask = row['input_after']
        assert mask is None or type(mask) is int and 0 <= mask <= 255, 'CAPTURE_PLAN_INPUT'
        if mask is not None:
            inputs.append(dict(dot=row['pause_dot'], buttons=mask))
    assert inputs == plan['inputs'] and plan['end_dot'] == captures[-1]['pause_dot'], 'CAPTURE_PLAN_HISTORY'


def public_state(client):
    def wide(low, high):
        return client.read_host(low) | client.read_host(high) << 32
    state = dict(dot=wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI),
                 retired=wide(abi.HOST_REG_RETIRE_LO, abi.HOST_REG_RETIRE_HI),
                 state=client.read_host(abi.HOST_REG_STATE),
                 image=client.read_host(abi.HOST_REG_IMAGE_VALID),
                 source=client.read_host(abi.HOST_REG_INPUT_SOURCE),
                 mask=client.read_host(abi.HOST_REG_INPUT),
                 effective=client.read_host(abi.HOST_REG_INPUT_EFFECTIVE))
    assert state['state'] == abi.STATE_PAUSED and state['image'] == 1, 'CAPTURE_PAUSED_IMAGE'
    assert state['source'] == abi.INPUT_SOURCE_UART and state['mask'] == state['effective'], 'CAPTURE_INPUT_SOURCE'
    return state


def check_frame(metadata, packed, row, epoch, reference):
    assert set(metadata) == {'epoch', 'seq', 'dot', 'size'}, 'CAPTURE_METADATA_FIELDS'
    assert metadata['epoch'] == epoch and metadata['seq'] == row['seq'], 'CAPTURE_FRAME_IDENTITY'
    low = LCD+row['seq']*PERIOD+143*456
    assert low <= metadata['dot'] < low+456, 'CAPTURE_FRAME_DOT'
    assert metadata['size'] == abi.FRAME_BYTES and len(packed) == abi.FRAME_BYTES, 'CAPTURE_FRAME_SIZE'
    pixels = bytes((byte >> shift) & 3 for byte in packed for shift in (0, 2, 4, 6))
    offset = row['reference_offset']
    expected = reference[offset:offset+PIXELS]
    assert len(pixels) == len(expected) == PIXELS, 'CAPTURE_PIXEL_COUNT'
    mismatch = next((i for i, (actual, want) in enumerate(zip(pixels, expected)) if actual != want), None)
    assert mismatch is None, f'CAPTURE_PIXELS frame={row["seq"]} pixel={mismatch}'


def acquire(client, root, plan, reference, identity, stop, *, origin=None, previous=None,
            previous_sha256=None):
    """Caller owns the verified setup, session lock and existing total supervisor.

    origin binds a separately verified full load. previous is a completed local
    checkpoint, never an instruction to recover an uncertain endpoint. The
    caller also verifies the preceding whole-supervisor success before resume.
    """
    root = Path(root).resolve()
    validate_plan(plan, reference)
    assert set(identity) == {'rom_sha256', 'build_id', 'epoch'}, 'CAPTURE_IDENTITY_FIELDS'
    # This retained #263 schedule is not a current-game timing oracle.
    assert identity['rom_sha256'] == BASELINE_ROM, 'CAPTURE_BASELINE_ROM'
    assert type(identity['epoch']) is int and 0 <= identity['epoch'] < 2**32, 'CAPTURE_EPOCH'
    binding = dict(plan_sha256=digest(plan), reference_sha256=hashlib.sha256(reference).hexdigest(), **identity)
    assert (origin is None) != (previous is None), 'CAPTURE_ORIGIN'
    artifacts, frames, inputs = {}, [], []
    start = 0
    if previous is not None:
        previous = Path(previous).resolve()
        assert previous.parent.parent == root and previous.name == 'checkpoint.json', 'CAPTURE_CHECKPOINT_PATH'
        assert file_hash(previous) == previous_sha256, 'CAPTURE_CHECKPOINT_HASH'
        checkpoint = json.loads(previous.read_text())
        assert checkpoint['status'] == 'PASS' and checkpoint['binding'] == binding, 'CAPTURE_CHECKPOINT_BINDING'
        artifacts = dict(checkpoint['artifacts'])
        for name, expected in artifacts.items():
            path = root/name
            assert not path.is_symlink() and path.resolve().is_relative_to(root), 'CAPTURE_ARTIFACT_PATH'
            assert file_hash(path) == expected, 'CAPTURE_ARTIFACT_HASH'
        artifacts[previous.relative_to(root).as_posix()] = file_hash(previous)
        frames, inputs = checkpoint['frames'], checkpoint['inputs']
        assert checkpoint['next_input'] == len(inputs), 'CAPTURE_CHECKPOINT_INPUT_INDEX'
        start = checkpoint['next_frame']
        assert start == len(frames) and [f['metadata']['seq'] for f in frames] == list(range(start)), 'CAPTURE_CHECKPOINT_ORDER'
        assert [dict(dot=i['dot'], buttons=i['buttons']) for i in inputs] == [
            i for i in plan['inputs'] if i['dot'] <= plan['captures'][start-1]['pause_dot']], 'CAPTURE_CHECKPOINT_INPUTS'
        frontier, sequence = checkpoint['frontier'], checkpoint['next_sequence']
    else:
        assert origin['binding'] == identity, 'CAPTURE_LOAD_IDENTITY'
        frontier, sequence = origin['frontier'], origin['next_sequence']
        assert frontier == dict(dot=0, retired=0, state=0, image=1, source=0, mask=0, effective=0), 'CAPTURE_LOAD_FRONTIER'
    assert type(stop) is int and start < stop <= len(plan['captures']), 'CAPTURE_BATCH_RANGE'
    assert not client.uncertain and client.sequence == sequence, 'CAPTURE_SESSION_FRONTIER'
    folder = root/f'batch-{start:04d}'
    folder.mkdir(parents=True, exist_ok=False)
    result = dict(status='FAIL', binding=binding, start=start, stop=stop)
    original_record = client.record
    try:
        with (folder/'packets.jsonl').open('w') as packets:
            def record(entry):
                original_record(entry)
                packets.write(json.dumps(entry)+'\n'); packets.flush()
            client.record = record
            assert client.identify()['build_id'] == identity['build_id'], 'CAPTURE_BUILD_ID'
            assert public_state(client) == frontier, 'CAPTURE_PUBLIC_FRONTIER'
            if start:
                metadata, packed = client.snapshot()
                check_frame(metadata, packed, plan['captures'][start-1], identity['epoch'], reference)
                assert metadata == frames[-1]['metadata'], 'CAPTURE_RETAINED_FRAME'
            dot, mask = frontier['dot'], frontier['mask']
            for row in plan['captures'][start:stop]:
                while dot < row['pause_dot']:
                    count = min(PERIOD, row['pause_dot']-dot)
                    expected = dot+count
                    assert client.run_dots(count) == dict(dot=expected, executed=count, reason=0), 'CAPTURE_RUN_DOTS'
                    dot = expected
                    observed = public_state(client)
                    assert observed['dot'] == dot and observed['mask'] == mask, 'CAPTURE_ADVANCE_STATE'
                assert dot == row['pause_dot'], 'CAPTURE_CHECKPOINT_DOT'
                metadata, packed = client.snapshot()
                path = folder/f'frame-{row["seq"]:04d}.2bpp'
                path.write_bytes(packed)
                check_frame(metadata, packed, row, identity['epoch'], reference)
                frames.append(dict(metadata=metadata, pause_dot=dot, reference_offset=row['reference_offset'],
                                   packed_file=path.relative_to(root).as_posix(), pixels=PIXELS))
                if row['input_after'] is not None:
                    mask = row['input_after']
                    input_sequence = client.sequence
                    assert client.control('INPUT', mask) == {'dot': dot}, 'CAPTURE_INPUT_DOT'
                    applied = public_state(client)
                    assert applied['dot'] == dot and applied['mask'] == mask, 'CAPTURE_INPUT_VALUE'
                    inputs.append(dict(dot=dot, buttons=mask, sequence=input_sequence))
            frontier = public_state(client)
            assert frontier['dot'] == dot and frontier['mask'] == mask, 'CAPTURE_END_FRONTIER'
            assert public_state(client) == frontier, 'CAPTURE_END_HOLD'
            assert not client.uncertain, 'CAPTURE_END_UNCERTAIN'
            if stop == len(plan['captures']):
                assert mask == 0, 'CAPTURE_FINAL_INPUT'
        for path in folder.iterdir():
            if path.is_file(): artifacts[path.relative_to(root).as_posix()] = file_hash(path)
        result.update(status='PASS', frames=frames, inputs=inputs, frontier=frontier,
                      next_frame=stop, next_input=len(inputs), next_sequence=client.sequence, artifacts=artifacts)
        atomic_json(folder/'checkpoint.json', result)
        return result
    except BaseException as error:
        result.update(error=f'{type(error).__name__}: {error}', next_sequence=client.sequence,
                      uncertain=client.uncertain)
        atomic_json(folder/'failure.json', result)
        raise
    finally:
        client.record = original_record

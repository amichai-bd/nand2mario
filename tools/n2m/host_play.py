"""Original-game pixel recognition and bounded Client play sequence."""
import hashlib
from . import generated_interfaces as abi


class PlayFailure(ValueError):
    pass


def decode_frame(metadata, packed, previous=None, epoch=2):
    if len(packed) != abi.FRAME_BYTES or metadata.get('size') != abi.FRAME_BYTES:
        raise PlayFailure('PLAY_FRAME_SIZE')
    if metadata.get('epoch') != epoch or metadata.get('seq', -1) < 1:
        raise PlayFailure('PLAY_FRAME_IDENTITY')
    sequence = metadata['seq']
    if previous is not None and (sequence <= previous['sequence'] or metadata['dot'] <= previous['dot']):
        raise PlayFailure('PLAY_FRAME_STALE')
    pixels = bytes((value >> shift) & 3 for value in packed for shift in (0, 2, 4, 6))
    return pixels, {'epoch': epoch, 'sequence': sequence, 'dot': metadata['dot']}


def locate(pixels):
    if len(pixels) != 160 * 144:
        raise PlayFailure('PLAY_IMAGE_SIZE')
    points = [(i % 160, i // 160) for i, shade in enumerate(pixels) if shade]
    if len(points) != 64:
        raise PlayFailure('PLAY_OBJECT_COUNT')
    left = min(x for x, _ in points)
    top = min(y for _, y in points)
    if set(points) != {(left + x, top + y) for x in range(8) for y in range(8)}:
        raise PlayFailure('PLAY_OBJECT_SHAPE')
    shades = {pixels[y * 160 + x] for x, y in points}
    if len(shades) != 1:
        raise PlayFailure('PLAY_OBJECT_SHADE')
    return left, top, shades.pop()


def check_image(pixels, expected):
    observed = locate(pixels)
    if observed != expected:
        raise PlayFailure(f'PLAY_IMAGE expected={expected} actual={observed}')
    x, y, shade = expected
    for i, actual in enumerate(pixels):
        wanted = shade if x <= i % 160 < x + 8 and y <= i // 160 < y + 8 else 0
        if actual != wanted:
            raise PlayFailure(f'PLAY_PIXEL index={i} expected={wanted} actual={actual}')
    return observed


def play(client, image, wait, retain, *, expected_epoch=None):
    """wait(dots) advances bounded run time; retain stores immutable observations."""
    identity = client.identify()
    loaded = client.load(image)
    client.select_input_source(abi.INPUT_SOURCE_UART)
    if client.read_host(abi.HOST_REG_INPUT_SOURCE) != abi.INPUT_SOURCE_UART:
        raise PlayFailure('PLAY_SOURCE')
    previous = None
    observed = None
    results = []
    expectations = [(64, 64, 1), (72, 64, 3), (72, 64, 1), (64, 64, 3), (64, 64, 1)]
    for stage, expected in enumerate(expectations):
        # Choose from the observed screen, not a presumed private game variable.
        mask = 0 if stage % 2 == 0 else (1 if observed[0] == 64 else 2)
        applied = client.write_host(abi.HOST_REG_INPUT, mask)
        if client.read_host(abi.HOST_REG_INPUT) != mask or client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) != mask:
            raise PlayFailure('PLAY_INPUT')
        client.control('RUN')
        wait(200000 if stage == 0 else 150000)
        halted = client.control('HALT')
        metadata, packed = client.snapshot()
        pixels, current = decode_frame(metadata, packed, previous,
            epoch=metadata['epoch'] if expected_epoch is None else expected_epoch)
        expected_epoch = current['epoch']
        retain(stage, {'metadata': metadata, 'expected': expected, 'checked': False}, packed, pixels)
        observed = check_image(pixels, expected)
        item = {'stage': stage, 'input': mask, 'applied': applied, 'halted': halted,
                'frame': current, 'object': observed, 'packed_sha256': hashlib.sha256(packed).hexdigest()}
        retain(stage, item, packed, pixels)
        results.append(item)
        previous = current
    return {'identity': identity, 'load': loaded, 'observations': results}

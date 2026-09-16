"""Completion selected from the locked link map of the running fixture, not any LD B,B."""
PASS = (3, 5, 8, 13, 21, 34)


def completion(record, pc=0x4a81):
    """True at the locked completion instruction; the register fingerprint must be the pass tuple."""
    if record['pc_before'] != pc or record['opcode'] != 0x40:
        return False
    # The completion address is in the switched bank 1 of each selected image.
    assert (record['pc_after'], record['opcode'], record['opcode_length']) == (pc + 1, 0x40, 1), 'MOONEYE_COMPLETION_INSTRUCTION'
    actual = tuple(record[name] for name in ('b', 'c', 'd', 'e', 'h', 'l'))
    assert actual == PASS, f'MOONEYE_COMPLETION_REGISTERS expected={PASS} actual={actual}'
    return True

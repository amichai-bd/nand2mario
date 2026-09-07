"""Completion selected from the locked reg_f link map, not any LD B,B."""
PASS = (3, 5, 8, 13, 21, 34)


def completion(record):
    if record['pc_before'] != 0x4a81 or record['opcode'] != 0x40:
        return False
    # 4A81 is in fixed bank 1 of the selected ROM-only 32 KiB image.
    assert (record['pc_after'], record['opcode'], record['opcode_length']) == (0x4a82, 0x40, 1), 'MOONEYE_COMPLETION_INSTRUCTION'
    actual = tuple(record[name] for name in ('b', 'c', 'd', 'e', 'h', 'l'))
    assert actual == PASS, f'MOONEYE_COMPLETION_REGISTERS expected={PASS} actual={actual}'
    return True

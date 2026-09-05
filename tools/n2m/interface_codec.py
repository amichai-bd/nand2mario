"""Pure byte codecs for the interface ABI. No device discovery or transport I/O."""
from . import generated_interfaces as abi


def uint(value, bits):
    if type(value) is not int or not 0 <= value < (1 << bits):
        raise ValueError(f'expected unsigned {bits}-bit integer')
    return value


def pack_record(name, values):
    fields = abi.RECORDS[name]
    if set(values) != {field['name'] for field in fields}:
        raise ValueError('record fields differ from schema')
    return b''.join(uint(values[f['name']], f['bits']).to_bytes(f['bits']//8, 'little') for f in fields)


def unpack_record(name, raw):
    fields = abi.RECORDS[name]
    if len(raw) != sum(f['bits']//8 for f in fields):
        raise ValueError('record length differs from schema')
    result, offset = {}, 0
    for field in fields:
        size = field['bits']//8
        result[field['name']] = int.from_bytes(raw[offset:offset+size], 'little')
        offset += size
    return result


def crc16(raw):
    crc = abi.WIRE_CRC_INIT
    for byte in raw:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (abi.WIRE_CRC_POLY if crc & 0x8000 else 0)) & 0xffff
    return crc


def cobs_encode(raw):
    result = bytearray([0])
    code_at, code = 0, 1
    for byte in raw:
        if byte == 0:
            result[code_at] = code
            code_at, code = len(result), 1
            result.append(0)
        else:
            result.append(byte)
            code += 1
            if code == 255:
                result[code_at] = code
                code_at, code = len(result), 1
                result.append(0)
    result[code_at] = code
    return bytes(result)


def cobs_decode(raw):
    if not raw or 0 in raw:
        raise ValueError('invalid COBS frame')
    result, offset = bytearray(), 0
    while offset < len(raw):
        code = raw[offset]
        end = offset + code
        if end > len(raw):
            raise ValueError('truncated COBS block')
        result.extend(raw[offset+1:end])
        if code != 255 and end < len(raw):
            result.append(0)
        offset = end
    return bytes(result)


def encode_packet(sequence, command, payload=b'', *, kind=abi.WIRE_REQUEST, status=abi.STATUS_OK):
    if len(payload) > abi.WIRE_MAX_PAYLOAD:
        raise ValueError('payload too large')
    header = pack_record('packet_header', dict(version=abi.WIRE_VERSION, kind=kind,
                         seq=sequence, command=command, status=status, length=len(payload)))
    _header_semantics(unpack_record('packet_header', header))
    body = header + payload
    return cobs_encode(body + crc16(body).to_bytes(2, 'little')) + b'\0'


def _header_semantics(header):
    if header['version'] != abi.WIRE_VERSION:
        raise ValueError('unsupported wire version')
    if header['kind'] not in (abi.WIRE_REQUEST, abi.WIRE_RESPONSE):
        raise ValueError('invalid packet kind')
    if header['kind'] == abi.WIRE_REQUEST and header['status'] != abi.STATUS_OK:
        raise ValueError('request status must be zero')


def decode_packet(frame):
    max_raw = abi.PACKET_HEADER_BYTES + abi.WIRE_MAX_PAYLOAD + 2
    if not frame or frame[-1] != 0 or len(frame) > max_raw + max_raw//254 + 2:
        raise ValueError('missing delimiter or oversized frame')
    raw = cobs_decode(frame[:-1])
    if len(raw) < abi.PACKET_HEADER_BYTES + 2:
        raise ValueError('truncated packet')
    if crc16(raw[:-2]) != int.from_bytes(raw[-2:], 'little'):
        raise ValueError('CRC mismatch')
    header = unpack_record('packet_header', raw[:abi.PACKET_HEADER_BYTES])
    _header_semantics(header)
    payload = raw[abi.PACKET_HEADER_BYTES:-2]
    if header['length'] != len(payload) or len(payload) > abi.WIRE_MAX_PAYLOAD:
        raise ValueError('payload length mismatch')
    return header, payload


def host_address(address):
    uint(address, abi.HOST_ADDRESS_BITS)
    if address not in abi.HOST_REGISTERS:
        raise ValueError('unknown or unaligned host address')
    return address


def rom_offset(address):
    uint(address, abi.GB_ADDRESS_BITS)
    if not abi.GB_ROM0_START <= address <= abi.GB_ROM1_END:
        raise ValueError('CPU address is outside direct-profile ROM')
    return address - abi.GB_ROM0_START


def checked_range(offset, count, size):
    uint(offset, 32)
    uint(count, 16)
    if not 1 <= count <= abi.WIRE_MAX_PAYLOAD or offset + count > size:
        raise ValueError('range exceeds storage or payload limit')
    return slice(offset, offset + count)


def pack_pixels(pixels):
    if len(pixels) != abi.FRAME_WIDTH * abi.FRAME_HEIGHT:
        raise ValueError('wrong frame size')
    return bytes(sum(uint(pixels[i+j], abi.FRAME_PIXEL_BITS) << (j*abi.FRAME_PIXEL_BITS)
                     for j in range(4)) for i in range(0, len(pixels), 4))

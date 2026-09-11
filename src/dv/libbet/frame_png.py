"""Decode a packed 2bpp 160x144 host frame to PNG without third-party modules."""
import struct
import sys
import zlib

SHADES = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]

def unpack(packed):
    return bytes((value >> shift) & 3 for value in packed for shift in (0, 2, 4, 6))

def png(path, rgb_rows, width, height):
    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    raw = b''.join(b'\x00' + row for row in rgb_rows)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    with open(path, 'wb') as stream:
        stream.write(data)

def write_frame(pixels, path, scale=1):
    rows = []
    for y in range(144):
        row = bytearray()
        for x in range(160):
            row += bytes(SHADES[pixels[y * 160 + x]]) * scale
        rows += [bytes(row)] * scale
    png(path, rows, 160 * scale, 144 * scale)

def write_diff(a, b, path, scale=1):
    """Red where the two frames differ, greyscale frame b elsewhere."""
    rows = []
    for y in range(144):
        row = bytearray()
        for x in range(160):
            i = y * 160 + x
            row += (bytes((255, 0, 0)) if a[i] != b[i] else bytes(SHADES[b[i]])) * scale
        rows += [bytes(row)] * scale
    png(path, rows, 160 * scale, 144 * scale)

if __name__ == '__main__':
    packed = open(sys.argv[1], 'rb').read()
    write_frame(unpack(packed), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1)

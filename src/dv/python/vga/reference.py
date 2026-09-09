"""Original canonical frames and a public-pin raster checker; no DUT imports."""
import zlib

EXPECTED_CRC = (0x357AB3D9, 0x388B975E)
GRAY = (15, 10, 5, 0)


def frame(number):
    return bytes(((x // 11) ^ (y // 7) ^ ((x * y) // 13)
                  ^ ((x + 3 * y + number * 17) // 19) ^ (number * 3)) & 3
                 for y in range(144) for x in range(160))


def crc(data):
    return zlib.crc32(data)


class Raster:
    """Schedule from reset-relative pixel edges, independent of display state."""
    def __init__(self):
        assert crc(b'123456789') == 0xCBF43926
        self.frames = (frame(0), frame(1))
        assert tuple(map(crc, self.frames)) == EXPECTED_CRC
        self.edge = 0
        self.canonical = [bytearray(), bytearray()]
        self.replicas = [0, 0]
        self.completed = []

    def sample(self, public):
        # The two-stage output pipeline exposes coordinate zero on edge two.
        self.edge += 1
        if self.edge < 2:
            assert public == 3, f'VGA_CRC_RESET expected=3 actual={public}'
            return None
        raster, point = divmod(self.edge - 2, 800 * 525)
        y, x = divmod(point, 800)
        identity = raster - 1
        image = 0 <= identity < 2 and 80 <= x < 560 and 24 <= y < 456
        hs, vs = int(not 656 <= x < 752), int(not 490 <= y < 492)
        shade = 0
        if image:
            index = ((y - 24) // 3) * 160 + (x - 80) // 3
            shade = GRAY[self.frames[identity][index]]
        expected = (shade << 10) | (shade << 6) | (shade << 2) | (hs << 1) | vs
        assert public == expected, (f'VGA_CRC_RGB raster={raster} x={x} y={y} '
                                    f'expected={expected:04x} actual={public:04x}')
        if image:
            self.replicas[identity] += 1
            if (x - 80) % 3 == 0 and (y - 24) % 3 == 0:
                # Decode actual observed red; equality above checked every replica/channel.
                self.canonical[identity].append(GRAY.index((public >> 10) & 15))
            if x == 559 and y == 455:
                data = self.canonical[identity]
                assert len(data) == 23040 and self.replicas[identity] == 207360
                observed = crc(data)
                assert observed == EXPECTED_CRC[identity], 'VGA_CRC_FRAME'
                self.completed.append(identity)
                return {'frame': identity, 'canonical_pixels': len(data),
                        'replicas': self.replicas[identity], 'crc32': f'{observed:08x}'}
        return None

    def finish(self):
        assert self.completed == [0, 1], f'VGA_CRC_INCOMPLETE frames={self.completed}'
        assert [len(data) for data in self.canonical] == [23040, 23040]

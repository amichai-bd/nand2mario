"""Independent byte vectors and schema mutations; no hardware or DUT model."""
import copy
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m import interface_codec as codec
from n2m import interfaces

ROOT = Path(__file__).resolve().parents[3]


class InterfaceTests(unittest.TestCase):
    def test_generation_and_each_export_drift(self):
        interfaces.generate(ROOT, check=True)
        base = ROOT / 'workdir/builds/interface-unit'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base, prefix='path with spaces ') as temporary:
            root = Path(temporary)
            (root/'cfg').mkdir()
            (root/interfaces.SOURCE).write_bytes((ROOT/interfaces.SOURCE).read_bytes())
            interfaces.generate(root)
            interfaces.generate(root, check=True)
            for path in interfaces.OUTPUTS:
                original = (root/path).read_text()
                (root/path).write_text(original + 'drift\n')
                with self.assertRaisesRegex(ValueError, 'generation drift'):
                    interfaces.generate(root, check=True)
                (root/path).write_text(original)
            (root/interfaces.OUTPUTS[0]).unlink()
            with self.assertRaisesRegex(ValueError, 'generation drift'):
                interfaces.generate(root, check=True)

    def test_schema_rejects_mutations(self):
        original = interfaces.load(ROOT/interfaces.SOURCE)
        mutations = [
            lambda d: d.update(extra=1),
            lambda d: d.update(schema_version=True),
            lambda d: d.update(byte_order='native'),
            lambda d: d['groups']['button'][0].update(value=256),
            lambda d: d['groups']['button'][0].update(value=1.0),
            lambda d: d['groups']['host_reg'][0].update(value=0xff00),
            lambda d: d['groups']['host_reg'][0].update(value=0x10001),
            lambda d: d['groups']['gb_reg'][0].update(value=0x10000),
            lambda d: d['groups']['command'][1].update(value=1),
            lambda d: d['groups']['gb'][2].update(value=1),
            lambda d: d['records']['retirement'][0].update(bits=7),
            lambda d: d['records']['retirement'][1].update(name='version'),
            lambda d: d['commands'][0].update(request='unknown'),
            lambda d: d['groups']['frame'][-1].update(value=5761),
            lambda d: d['references'][0].update(revision='main'),
        ]
        for mutate in mutations:
            data = copy.deepcopy(original)
            mutate(data)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises(ValueError):
                interfaces.validate(data)
        base=ROOT/'workdir/builds/interface-unit';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            path=Path(temporary)/'duplicate.json';path.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                interfaces.load(path)

    def test_independent_header_vector(self):
        fields = dict(version=1, kind=0, seq=0x12345678, command=7, status=0, length=0x0100)
        expected = bytes.fromhex('01 00 78 56 34 12 07 00 00 01')
        self.assertEqual(codec.pack_record('packet_header', fields), expected)
        self.assertEqual(codec.unpack_record('packet_header', expected), fields)
        self.assertEqual(abi.PACKET_HEADER_BYTES, 10)
        self.assertEqual(abi.PACKET_HEADER_SEQ_OFFSET, 2)
        self.assertEqual(abi.PACKET_HEADER_LENGTH_OFFSET, 8)
        with self.assertRaises(ValueError):
            codec.unpack_record('packet_header', expected[:-1])

    def test_crc_and_cobs_independent_vectors(self):
        self.assertEqual(codec.crc16(b'123456789'), 0x29b1)
        vectors = [(b'', b'\x01'), (b'\0', b'\x01\x01'),
                   (b'\x11\x22\0\x33', b'\x03\x11\x22\x02\x33'),
                   (b'\x55'*254, b'\xff'+b'\x55'*254+b'\x01')]
        for raw, encoded in vectors:
            self.assertEqual(codec.cobs_encode(raw), encoded)
            self.assertEqual(codec.cobs_decode(encoded), raw)
        for raw in (b'',b'\0',b'\x04\x01',b'\x01\0'):
            with self.assertRaises(ValueError):
                codec.cobs_decode(raw)

    def test_full_byte_alphabet_and_random_packets(self):
        rng=random.Random(30)
        for count in [0,1,253,254,255,256]+[rng.randrange(257) for _ in range(20)]:
            payload=bytes(range(256))[:count] if count==256 else rng.randbytes(count)
            packet=codec.encode_packet(0x10203040, abi.COMMAND_READ_ROM, payload)
            self.assertNotIn(0,packet[:-1])
            header,actual=codec.decode_packet(packet)
            self.assertEqual(actual,payload)
            self.assertEqual(header['seq'],0x10203040)
        with self.assertRaisesRegex(ValueError,'too large'):
            codec.encode_packet(0,1,b'X'*257)

    def test_corrupt_packets_fail_for_reason(self):
        valid=codec.encode_packet(1,1)
        raw=bytearray(codec.cobs_decode(valid[:-1]));raw[-1]^=1
        with self.assertRaisesRegex(ValueError,'CRC mismatch'):
            codec.decode_packet(codec.cobs_encode(raw)+b'\0')
        for index,value,reason in [(0,2,'version'),(1,2,'kind'),(7,1,'request status'),(8,1,'length')]:
            raw=bytearray(codec.cobs_decode(valid[:-1]));raw[index]=value
            raw[-2:]=codec.crc16(raw[:-2]).to_bytes(2,'little')
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                codec.decode_packet(codec.cobs_encode(raw)+b'\0')
        with self.assertRaisesRegex(ValueError,'delimiter'):
            codec.decode_packet(valid[:-1])

    def test_widths_and_trace_layout(self):
        for record,fields in abi.RECORDS.items():
            maximum={f['name']:(1<<f['bits'])-1 for f in fields}
            raw=codec.pack_record(record,maximum)
            self.assertEqual(raw,b'\xff'*sum(f['bits']//8 for f in fields))
            for field in fields:
                for bad in (-1,1<<field['bits'],True,0.5):
                    values=maximum|{field['name']:bad}
                    with self.assertRaises(ValueError):codec.pack_record(record,values)
        self.assertEqual(abi.RETIREMENT_BYTES,48)
        fields={f['name']:0 for f in abi.RECORDS['retirement']}
        fields.update(version=1,epoch=0x12345678,pc_before=0x1234,opcode=0xabcdef,opcode_length=3)
        raw=codec.pack_record('retirement',fields)
        self.assertEqual(raw[:6],bytes.fromhex('01 00 78 56 34 12'))
        self.assertEqual(raw[22:30],bytes.fromhex('34 12 00 00 ef cd ab 03'))

    def test_address_spaces_and_range_neighbors(self):
        self.assertEqual(codec.host_address(0x10000),0x10000)
        for bad in (0xff00,0xffff,0x10001,0x10050,-1,1<<32):
            with self.assertRaises(ValueError):codec.host_address(bad)
        for address in (0,0x3fff,0x4000,0x7fff):self.assertEqual(codec.rom_offset(address),address)
        for bad in (-1,0x8000,0xff00,0x10000):
            with self.assertRaises(ValueError):codec.rom_offset(bad)
        self.assertEqual(codec.checked_range(32767,1,32768),slice(32767,32768))
        for offset,count in ((32768,1),(32767,2),(0,0),(0,257),(0xffffffff,2)):
            with self.assertRaises(ValueError):codec.checked_range(offset,count,32768)

    def test_host_write_permissions_and_wire_layout(self):
        for value in range(256):
            self.assertEqual(codec.host_write(0x10020, value),
                             bytes.fromhex('20 00 01 00') + value.to_bytes(4, 'little'))
        for value in (0, 1):
            self.assertEqual(codec.host_write(0x10044, value),
                             bytes.fromhex('44 00 01 00') + value.to_bytes(4, 'little'))
        for address, value in ((0x10000, 0), (0x10048, 0), (0x1004c, 0),
                               (0x10050, 0), (0xff00, 0), (0x10021, 0),
                               (0x10020, 256), (0x10044, 2), (0x10020, -1),
                               (0x10044, True), (True, 0)):
            with self.assertRaises(ValueError):
                codec.host_write(address, value)

    def test_button_and_pixel_mapping(self):
        self.assertEqual([abi.BUTTON_RIGHT,abi.BUTTON_LEFT,abi.BUTTON_UP,abi.BUTTON_DOWN,
                          abi.BUTTON_A,abi.BUTTON_B,abi.BUTTON_SELECT,abi.BUTTON_START],
                         [1,2,4,8,16,32,64,128])
        pixels=[0,1,2,3]*5760
        self.assertEqual(codec.pack_pixels(pixels),b'\xe4'*5760)
        pixels[-1]=4
        with self.assertRaises(ValueError):codec.pack_pixels(pixels)


if __name__=='__main__':unittest.main()

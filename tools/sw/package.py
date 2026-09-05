"""Owned direct-entry cartridge header construction and strict image validation."""
import re
from n2m import generated_interfaces as hw
from .linker import mapping_profile
from .expressions import AssemblyError


def fail(code, cause):
    error = AssemblyError(code, cause, {"file": "targets.json", "line": 1, "column": 1})
    error.diagnostic["stage"] = "package"
    raise error


def metadata(title, version, profile):
    mapping_profile(profile)
    if type(title) is not str or not re.fullmatch('[A-Z0-9 ]{1,15}', title):
        fail('METADATA', 'title requires 1..15 uppercase ASCII letters/digits/spaces')
    if type(version) is not int or not 0 <= version <= 255:
        fail('METADATA', 'version must be an explicit byte')


def package(linked, title, version, profile='dmg-direct-v1'):
    metadata(title, version, profile)
    rom = bytearray(linked['image'])
    if len(rom) != hw.PROFILE_ROM_BYTES or any(b != 255 for b in rom[0x100:0x150]):
        fail('RESERVATION', 'packager requires an exclusive unfilled header')
    entry = linked['entry']
    rom[0x100:0x150] = bytes(0x50)
    rom[0x100:0x104] = bytes([0, 0xc3, entry & 255, entry >> 8])
    rom[0x134:0x144] = title.encode('ascii').ljust(16, b'\0')
    rom[0x14a] = 1
    rom[0x14c] = version
    rom[0x14d] = (-sum(rom[0x134:0x14d]) - 25) & 255
    checksum = sum(rom) & 65535
    rom[0x14e:0x150] = checksum.to_bytes(2, 'big')
    validate_image(rom, entry, title, version, profile)
    return bytes(rom)


def validate_image(rom, entry, title, version, profile='dmg-direct-v1'):
    metadata(title, version, profile)
    if len(rom) != hw.PROFILE_ROM_BYTES:
        fail('IMAGE_SIZE', 'direct image must have the exact generated size')
    if rom[0x100:0x104] != bytes([0, 0xc3, entry & 255, entry >> 8]):
        fail('ENTRY', 'entry stub differs from selected instruction boundary')
    expected = bytearray(0x49)
    expected[0x30:0x40] = title.encode('ascii').ljust(16, b'\0')
    expected[0x46] = 1
    expected[0x48] = version
    if rom[0x104:0x14d] != expected:
        fail('METADATA', 'header/logo/profile metadata differs from requested direct image')
    if rom[0x14d] != (-sum(rom[0x134:0x14d]) - 25) & 255:
        fail('HEADER_CHECKSUM', 'header checksum mismatch')
    if int.from_bytes(rom[0x14e:0x150], 'big') != (sum(rom[:0x14e]) + sum(rom[0x150:])) & 65535:
        fail('GLOBAL_CHECKSUM', 'global checksum mismatch')
    return True

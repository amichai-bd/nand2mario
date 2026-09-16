"""The package profiles: one table of name, generated runtime ID and exact image length.

The linker, packager, host tool and preload builder all consume this module so
a profile is named in one place. The IDs and lengths are the generated
interface constants (wiki/src/rtl/interfaces/MAS_interfaces.md).
"""
from . import generated_interfaces as abi

DIRECT_PROFILE_NAME = abi.PROFILE_NAME
LOADER_PROFILE_NAME = 'dmg-loader-v1'
MBC1_PROFILE_NAME = 'dmg-mbc1-v1'

# Profile name -> generated runtime profile ID.
PROFILE_IDS = {DIRECT_PROFILE_NAME: abi.PROFILE_DIRECT_ID, LOADER_PROFILE_NAME: abi.PROFILE_LOADER_ID,
               MBC1_PROFILE_NAME: abi.PROFILE_MBC1_ID}
# Profile name -> exact image length the load session and packager require.
IMAGE_BYTES = {DIRECT_PROFILE_NAME: abi.PROFILE_ROM_BYTES, LOADER_PROFILE_NAME: abi.PROFILE_ROM_BYTES,
               MBC1_PROFILE_NAME: abi.MBC1_ROM_BYTES}
# Generated runtime profile ID -> exact image length.
PROFILE_IMAGE_BYTES = {PROFILE_IDS[name]: IMAGE_BYTES[name] for name in PROFILE_IDS}
# Header bytes $0147-$0149 (cartridge type, ROM size code, RAM size code) the packager writes.
CARTRIDGE_BYTES = {DIRECT_PROFILE_NAME: bytes(3), LOADER_PROFILE_NAME: bytes(3), MBC1_PROFILE_NAME: bytes([0x01, 0x01, 0x00])}

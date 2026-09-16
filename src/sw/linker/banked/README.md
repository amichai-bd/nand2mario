# Original MBC1 linker fixture

These independently authored sources exercise the `dmg-mbc1-v1` profile of the
[software toolchain](../../../../wiki/tools/sw/SPEC.md#implemented-linker-and-packager):
fixed ROM0 code, a bank 1 and a bank 2 section at the same CPU address `4000`
in different banks, a floating bank 3 section, and allocation-only WRAM. The
code selects bank 2 through the `BANK1` register and reads the signature the
bank-2 unit exports; the cross-bank reference resolves to the CPU address of
the switched window, and the bank-2 bytes land at file offset `8000`.

The packager writes cartridge type `01`, ROM size code `01` and RAM size `00`
into the 64 KiB image. The linker test suite checks the exact bytes and file
offsets. This fixture is tooling evidence, not a CPU or Game Boy program
acceptance result; the [MBC1 profile](../../../../wiki/src/rtl/cartridge/MAS_mbc1_profile.md)
fixtures prove the hardware.

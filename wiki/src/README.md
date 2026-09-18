Hardware and software specifications belong in this directory.

- [Board bring-up](board-bring-up.md): verified DE10-Lite wiring, checked
  programming, and the UART-readable heartbeat, frame, ping and CRC proofs.
- [DE10-Nano board](de10-nano-board.md): the second board's device, JTAG chain,
  pin data with provenance, and the resources it lacks against the DE10-Lite.
- [DMG tile pixel](rtl/display/MAS_display.md): first isolated display unit.
- [VGA frame bridge](rtl/vga/MAS_vga.md): immutable frame ownership and scaled scanout.
- [Interface contracts](rtl/interfaces/MAS_interfaces.md): generated addresses, packets,
  direct-entry state and retirement records.
- [Verification baseline](dv/baseline/SPEC.md): shared harness, regressions and future adapters.

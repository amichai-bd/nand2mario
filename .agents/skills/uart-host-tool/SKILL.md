---
name: uart-host-tool
description: Design or maintain nand2mario host-side UART protocol tools. Use for framing, transport, MMIO commands, discovery, and tests; do not transmit to hardware without approval.
---

# UART host tool

Read the UART and host-register contracts before editing.
Use the [ownership map](../../../wiki/ownership.md) for the tool's PRD/SPEC and
shared interface authorities. Review wiki/code/test alignment for `tools/` and
its `src/` consumers; retain evidence without duplicating generated constants.

1. Separate packet encoding, transport, commands, and CLI output.
2. Make byte order, bounds, timeout, retry, checksum, and error behavior exact.
3. Require explicit port selection or verified device identity.
4. Test codecs without hardware and transport with a fake serial endpoint.
5. Record commit, port identity, command, protocol version, and response for
   approved physical tests.

Use [the command record](templates/command.md) for physical evidence. Read
[the scenarios](examples/scenarios.md) before serial access. Stop on protocol,
port, voltage, wiring, direction, permission, or register-map uncertainty.

Follow the [authorized hardware preference](../../../wiki/agents/bootstrap-plan.md#verification-and-hardware-authorization)
for bounded original-game checks. Standing authorization covers routine work
within that scope; verify the documented setup and build before physical access.

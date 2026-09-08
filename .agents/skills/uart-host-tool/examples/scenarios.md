# Scenarios

Good: Unit-test a write-MMIO packet and CRC failure with a fake transport before
an approved run on a verified adapter and port.

Bad: Guess `COM3`, retry writes forever, or treat received text as a valid framed
response.

Not a trigger: Implement the FPGA UART receiver or define an unknown register.

## Physical timeout diagnosis

For a silent response timeout, preserve the transmitted packet and any received
bytes before classifying it as an RTL failure. Compare a bounded ordinary write
with a clearly labeled diagnostic transport; pacing is not normal loading proof.
Use an actual endpoint global reset before recovering an uncertain session.

In pyserial 3.5 on Windows, changing `timeout` reapplies line configuration.
Do not apply that setter during an exchange. The
[host transport contract](../../../../wiki/tools/n2m/host/SPEC.md#transport-and-recovery)
owns the supported deadline behavior. A successful bulk write alone does not
prove the pin waveform. Use the existing serial fixture for physical baud and
contiguous 8N1 checks, with independently decoded packets and Intel models.

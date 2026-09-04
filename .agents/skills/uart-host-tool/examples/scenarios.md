# Scenarios

Good: Unit-test a write-MMIO packet and CRC failure with a fake transport before
an approved run on a verified adapter and port.

Bad: Guess `COM3`, retry writes forever, or treat received text as a valid framed
response.

Not a trigger: Implement the FPGA UART receiver or define an unknown register.

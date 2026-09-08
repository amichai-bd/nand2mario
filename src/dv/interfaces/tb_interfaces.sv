`timescale 1ns/1ps
module tb_interfaces;
  n2m_interfaces_pkg::packet_header_t header;
  n2m_interfaces_pkg::retirement_t retired;
  logic [79:0] expected;
  initial begin
    $dumpfile("interfaces.vcd");
    $dumpvars(0, tb_interfaces);
    header = '0;
    retired = '0;
    #1;
    header.version = 1;
    header.kind = 0;
    header.seq = 32'h12345678;
    header.command = 7;
    header.status = 0;
    header.length = 16'h0100;
    expected = 80'h01000007123456780001;
    if ($test$plusargs("corrupt")) expected[16] = ~expected[16];
    #1;
    if (header !== expected)
      $fatal(1, "INTERFACE_MISMATCH expected=%h actual=%h", expected, header);
    if ($bits(header) != 80 || n2m_interfaces_pkg::PACKET_HEADER_BYTES != 10 ||
        n2m_interfaces_pkg::PACKET_HEADER_SEQ_OFFSET != 2 || n2m_interfaces_pkg::PACKET_HEADER_LENGTH_OFFSET != 8)
      $fatal(1, "INTERFACE_WIDTH_MISMATCH header");
    if ($bits(retired) != 384 || n2m_interfaces_pkg::RETIREMENT_BYTES != 48)
      $fatal(1, "INTERFACE_WIDTH_MISMATCH retirement bits=%0d", $bits(retired));
    if (n2m_interfaces_pkg::GB_REG_JOYP != 16'hff00 || n2m_interfaces_pkg::HOST_REG_ABI != 32'h00010000 ||
        $bits(n2m_interfaces_pkg::GB_REG_JOYP) != 16 || $bits(n2m_interfaces_pkg::HOST_REG_ABI) != 32 ||
        n2m_interfaces_pkg::HOST_REG_ABI <= 32'hffff || n2m_interfaces_pkg::PROFILE_PC != 16'h0100 ||
        n2m_interfaces_pkg::PROFILE_SP != 16'hfffe || n2m_interfaces_pkg::PROFILE_ROM_BYTES != 32768)
      $fatal(1, "INTERFACE_ADDRESS_MISMATCH");
    retired.version = 1;
    retired.epoch = 32'h12345678;
    retired.pc_before = 16'h1234;
    retired.opcode = 24'habcdef;
    retired.opcode_length = 3;
    #1;
    if (retired[47:0] !== 48'h123456780001 ||
        retired[239:176] !== 64'h03abcdef00001234)
      $fatal(1, "INTERFACE_RETIREMENT_MISMATCH");
    $display("PASS interface vectors widths spaces");
    $finish;
  end
  initial begin
    #100;
    $fatal(1, "INTERFACE_TIMEOUT");
  end
endmodule

`timescale 1ns/1ps
`default_nettype none
module tb_memory_ram;
    logic clk_sys, reset, a_read, a_write, b_read;
    logic [7:0] a_address, b_address, a_wdata, a_rdata, b_rdata;
    logic a_valid, b_valid;
    logic [7:0] reference_bytes [0:159];
    logic [7:0] expected_a, expected_b, retained_a, retained_b;
    integer checks, index;
    bit corrupt;
    n2m_memory_ram #(.DEPTH(160), .ADDRESS_BITS(8)) dut (.*);

    task automatic edge_cycle;
        clk_sys = 0;
        expected_a = a_read && !reset ? reference_bytes[a_address] : retained_a;
        expected_b = b_read && !reset ? reference_bytes[b_address] : retained_b;
        #5;
        clk_sys = 1;
        #1;
        if (a_valid !== (a_read && !reset) || b_valid !== (b_read && !reset))
            $fatal(1, "MEMORY_RAM_VALID check=%0d", checks);
        if (a_read && !reset && a_rdata !== expected_a)
            $fatal(1, "MEMORY_RAM_READ_A check=%0d address=%0d expected=%02h actual=%02h",
                checks, a_address, expected_a, a_rdata);
        if (b_read && !reset && b_rdata !== expected_b)
            $fatal(1, "MEMORY_RAM_READ_B check=%0d address=%0d expected=%02h actual=%02h",
                checks, b_address, expected_b, b_rdata);
        if (!reset && a_write) reference_bytes[a_address] = a_wdata;
        retained_a = a_rdata;
        retained_b = b_rdata;
        checks = checks + 1;
        #4;
        clk_sys = 0;
    endtask

    initial begin
        $dumpfile("memory-ram.vcd");
        $dumpvars(0, tb_memory_ram);
        clk_sys = 0;
        reset = 1;
        a_read = 0; a_write = 0; b_read = 0;
        a_address = 0; b_address = 0; a_wdata = 0;
        checks = 0;
        retained_a = 0; retained_b = 0;
        corrupt = $test$plusargs("corrupt");
        edge_cycle();
        reset = 0;
        for (index = 0; index < 160; index = index + 1) begin
            a_write = 1; a_address = 8'(index); a_wdata = 8'(index * 37 + 19);
            edge_cycle();
        end
        a_write = 0; a_read = 1; b_read = 1;
        for (index = 0; index < 160; index = index + 1) begin
            a_address = 8'(index); b_address = 8'(159 - index);
            if (corrupt && index == 5) force dut.b_rdata = 8'hff;
            edge_cycle();
        end
        // Both simultaneous readers must see the old byte, then the next read
        // sees the new write. This is a storage policy, not a DMA bus model.
        a_address = 159; b_address = 159; a_write = 1; a_wdata = 8'hc7;
        edge_cycle();
        a_write = 0;
        edge_cycle();
        // Reset cancels an enabled write and both valid flags without erasing
        // already initialized storage. Exercise assertion between clock edges.
        #2; reset = 1; a_write = 1; a_wdata = 8'h4d;
        #1;
        if (a_valid || b_valid) $fatal(1, "MEMORY_RAM_ASYNC_VALID");
        edge_cycle();
        reset = 0; a_write = 0;
        edge_cycle();
        a_read = 0; b_read = 0;
        edge_cycle();
        $display("PASS memory RAM bytes=160 dual_reads=320 old_data=2 reset_retention=1");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "MEMORY_RAM_WATCHDOG");
    end
endmodule

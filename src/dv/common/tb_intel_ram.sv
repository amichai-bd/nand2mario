`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module intel_ram_case #(
    parameter integer DATA_BITS = 8,
    parameter integer DEPTH = 160,
    parameter integer LANES = 1,
    parameter bit DUAL_CLOCK = 0,
    parameter integer CASE_ID = 0
) (output logic done);
    localparam integer ADDRESS_BITS = $clog2(DEPTH);
    logic clk_a, clk_b, reset_a, reset_b, a_read, a_write, a_valid, b_read, b_valid;
    logic [ADDRESS_BITS-1:0] a_address, b_address;
    logic [DATA_BITS-1:0] a_wdata, a_rdata, b_rdata;
    logic [LANES-1:0] a_byte_enable;
    logic [DATA_BITS-1:0] expected [0:DEPTH-1];
    logic [DATA_BITS-1:0] held_a, held_b, delayed_data;
    bit have_a, have_b, corrupt, late, collision;
    integer index, lane, checks;
    n2m_intel_ram #(.DEPTH(DEPTH), .DATA_BITS(DATA_BITS), .ADDRESS_BITS(ADDRESS_BITS),
        .BYTE_LANES(LANES), .DUAL_CLOCK(DUAL_CLOCK)) dut (.*);

    // Deliberate latency mutation takes the previous primitive result, then
    // forces the actual wrapper output. The independent checker stays unchanged.
    `DFF(delayed_data, dut.ram_data_a, clk_a)
    task automatic check_b;
        if (b_valid !== (b_read && !reset_b))
            $fatal(1, "INTEL_RAM_VALID_B case=%0d check=%0d", CASE_ID, checks);
        if (b_read && !reset_b) begin held_b = expected[b_address]; have_b = 1; end
        if (have_b && b_rdata !== held_b)
            $fatal(1, "INTEL_RAM_DATA_B case=%0d check=%0d expected=%h actual=%h", CASE_ID, checks, held_b, b_rdata);
    endtask
    task automatic cycle;
        #5; clk_a = 1;
        #1;
        if (a_write && !reset_a) begin
            if (LANES == 1) begin
                if (a_byte_enable[0]) expected[a_address] = a_wdata;
            end else begin
                for (lane = 0; lane < LANES; lane = lane + 1)
                    if (a_byte_enable[lane]) expected[a_address][lane*8 +: 8] = a_wdata[lane*8 +: 8];
            end
        end
        if (a_valid !== (a_read && !reset_a))
            $fatal(1, "INTEL_RAM_VALID_A case=%0d check=%0d", CASE_ID, checks);
        if (a_read && !reset_a) begin held_a = expected[a_address]; have_a = 1; end
        if (have_a && a_rdata !== held_a)
            $fatal(1, "INTEL_RAM_DATA_A case=%0d check=%0d expected=%h actual=%h", CASE_ID, checks, held_a, a_rdata);
        if (!DUAL_CLOCK) check_b();
        #4; clk_a = 0;
        if (DUAL_CLOCK) begin
            #3; clk_b = 1;
            #1; check_b();
            #6; clk_b = 0;
        end
        checks = checks + 1;
    endtask
    initial begin
        done = 0; clk_a = 0; clk_b = 0; reset_a = 1; reset_b = 1;
        a_read = 0; a_write = 0; a_address = 0; a_wdata = 0; a_byte_enable = '1;
        b_read = 0; b_address = 0; have_a = 0; have_b = 0; checks = 0;
        corrupt = CASE_ID == 0 && $test$plusargs("corrupt");
        late = CASE_ID == 0 && $test$plusargs("late");
        collision = CASE_ID == 0 && $test$plusargs("collision");
        cycle(); reset_a = 0; reset_b = 0;
        // Populate all words only through real public write controls.
        a_write = 1;
        for (index = 0; index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); a_wdata = DATA_BITS'(index * 37 + 19);
            cycle();
        end
        a_address = 0; a_wdata = DATA_BITS'('hA5); cycle();
        a_address = ADDRESS_BITS'(DEPTH-1); a_wdata = DATA_BITS'('h3C); cycle();
        a_write = 0; a_read = 1; b_read = 1;
        for (index = 0; index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index);
            if (index == 1 && corrupt) force dut.a_rdata = '1;
            if (index == 1 && late) force dut.a_rdata = delayed_data;
            cycle();
        end
        // Disabled reads must retain their data even while A writes other words.
        a_read = 0; b_read = 0; a_write = 1;
        for (index = 0; index < 16; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index);
            a_wdata = DATA_BITS'(index * 11 + 7); cycle();
        end
        a_read = 1; a_address = ADDRESS_BITS'(DEPTH-1); a_wdata = DATA_BITS'('h69); cycle();
        a_read = 0;
        if (LANES == 4) begin
            a_address = ADDRESS_BITS'(3); a_wdata = DATA_BITS'('h11223344); cycle();
            a_wdata = DATA_BITS'('h0000AA00); a_byte_enable = LANES'(2); cycle();
            a_write = 0; a_read = 1; cycle();
            if (a_rdata !== DATA_BITS'('h1122AA44)) $fatal(1, "INTEL_RAM_BYTE_LANES");
            a_byte_enable = '1;
        end
        a_write = 0; a_read = 1; b_read = 1; a_address = 0; b_address = ADDRESS_BITS'(DEPTH-1); cycle();
        if (collision) begin
            a_write = 1; b_address = a_address; cycle();
            $fatal(1, "INTEL_RAM_COLLISION_ESCAPED");
        end
        reset_a = 1; reset_b = 1;
        #1;
        if (a_valid || b_valid) $fatal(1, "INTEL_RAM_RESET_VISIBLE");
        a_write = 1; a_wdata = 0; cycle();
        a_write = 0; a_read = 0; b_read = 0; reset_a = 0; reset_b = 0; cycle();
        a_read = 1; b_read = 1;
        for (index = 0; index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index); cycle();
        end
        $display("PASS Intel RAM case=%0d width=%0d depth=%0d lanes=%0d dual_clock=%0d checks=%0d", CASE_ID, DATA_BITS, DEPTH, LANES, DUAL_CLOCK, checks);
        done = 1;
    end
endmodule

module tb_intel_ram;
    logic done_byte, done_pair, done_lanes, done_frame;
    intel_ram_case byte_case (.done(done_byte));
    intel_ram_case #(.DATA_BITS(16), .DEPTH(80), .CASE_ID(1)) pair_case (.done(done_pair));
    intel_ram_case #(.DATA_BITS(32), .DEPTH(64), .LANES(4), .CASE_ID(2)) lanes_case (.done(done_lanes));
    intel_ram_case #(.DATA_BITS(2), .DEPTH(23040), .DUAL_CLOCK(1), .CASE_ID(3)) frame_case (.done(done_frame));
    initial begin
        $dumpfile("intel-memory.vcd");
        $dumpvars(1, tb_intel_ram.byte_case.dut);
        $dumpvars(1, tb_intel_ram.pair_case.dut);
        $dumpvars(1, tb_intel_ram.lanes_case.dut);
        $dumpvars(1, tb_intel_ram.frame_case.dut);
        wait (done_byte && done_pair && done_lanes && done_frame);
        $display("PASS Intel memory configurations=4 initialized_words=23344 latency=1");
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "INTEL_RAM_WATCHDOG");
    end
endmodule

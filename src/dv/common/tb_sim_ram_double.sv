`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Unit test for the n2m_sim_dual_port_ram double behind n2m_intel_ram in
// simulation. Contract: wiki/src/rtl/common/MAS_memory_primitives.md.
// Plan: src/dv/common/README.md.

// Expected preload images. The top writes the files from these same functions;
// the double must read them back through its own parser.
package sim_ram_double_pkg;
    function automatic logic [7:0] byte_image(input integer index);
        return index >= 240 ? 8'h5A : 8'((index * 7 + 3) % 256);
    endfunction
    function automatic logic [0:0] presence_image(input integer index);
        return index < 32 ? 1'b1 : 1'b0;
    endfunction
    function automatic logic [15:0] word_image(input integer index);
        return 16'((index * 613 + 41) % 65536);
    endfunction
endpackage

// One wrapper shape. Every access goes through the public n2m_intel_ram ports.
module sim_ram_wrapper_case #(
    parameter integer DATA_BITS = 8,
    parameter integer DEPTH = 160,
    parameter integer LANES = 1,
    parameter bit DUAL_CLOCK = 0,
    parameter string INIT_FILE = "UNUSED",
    parameter integer CASE_ID = 0
) (output logic done, output integer checks);
    localparam integer ADDRESS_BITS = $clog2(DEPTH);
    logic clk_a, clk_b, reset_a, reset_b, a_read, a_write, a_valid, b_read, b_valid;
    logic [ADDRESS_BITS-1:0] a_address, b_address;
    logic [DATA_BITS-1:0] a_wdata, a_rdata, b_rdata;
    logic [LANES-1:0] a_byte_enable;
    logic [DATA_BITS-1:0] expected [0:DEPTH-1];
    logic [DATA_BITS-1:0] held_a, held_b, before_edge_a, sample_a, distinct_first;
    bit have_a, have_b, corrupt, collision, partial_lanes;
    integer index, lane, distinct;
    n2m_intel_ram #(.DEPTH(DEPTH), .DATA_BITS(DATA_BITS), .ADDRESS_BITS(ADDRESS_BITS),
        .BYTE_LANES(LANES), .DUAL_CLOCK(DUAL_CLOCK), .INIT_FILE(INIT_FILE)) dut (.*);

    function automatic logic [DATA_BITS-1:0] preload_value(input integer at);
        if (DATA_BITS == 8) return DATA_BITS'(sim_ram_double_pkg::byte_image(at));
        if (DATA_BITS == 1) return DATA_BITS'(sim_ram_double_pkg::presence_image(at));
        return DATA_BITS'(sim_ram_double_pkg::word_image(at));
    endfunction

    task automatic fail(input string name);
        $fatal(1, "%s case=%0d check=%0d", name, CASE_ID, checks);
    endtask

    task automatic check_b;
        if (b_valid !== (b_read && !reset_b)) fail("SIM_RAM_VALID_B");
        if (b_read && !reset_b) begin held_b = expected[b_address]; have_b = 1; end
        if (have_b && b_rdata !== held_b)
            $fatal(1, "SIM_RAM_DATA_B case=%0d check=%0d expected=%h actual=%h", CASE_ID, checks, held_b, b_rdata);
    endtask

    // One A edge (and one B edge in dual-clock mode) with the contract checks:
    // outputs are unchanged before the edge and hold the request result after it.
    task automatic cycle;
        before_edge_a = a_rdata;
        #5;
        if (a_rdata !== before_edge_a) fail("SIM_RAM_EARLY_A");
        clk_a = 1;
        #1;
        if (a_write && !reset_a) begin
            for (lane = 0; lane < LANES; lane = lane + 1)
                if (a_byte_enable[lane])
                    expected[a_address][lane*(DATA_BITS/LANES) +: (DATA_BITS/LANES)] = a_wdata[lane*(DATA_BITS/LANES) +: (DATA_BITS/LANES)];
        end
        if (a_valid !== (a_read && !reset_a)) fail("SIM_RAM_VALID_A");
        if (a_read && !reset_a) begin held_a = expected[a_address]; have_a = 1; end
        if (have_a && a_rdata !== held_a)
            $fatal(1, "SIM_RAM_DATA_A case=%0d check=%0d expected=%h actual=%h", CASE_ID, checks, held_a, a_rdata);
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
        done = 0; checks = 0; clk_a = 0; clk_b = 0; reset_a = 1; reset_b = 1;
        a_read = 0; a_write = 0; a_address = 0; a_wdata = 0; a_byte_enable = '1;
        b_read = 0; b_address = 0; have_a = 0; have_b = 0; distinct = 0;
        corrupt = CASE_ID == 0 && $test$plusargs("corrupt");
        collision = CASE_ID == 0 && $test$plusargs("collision");
        partial_lanes = CASE_ID == 2 && $test$plusargs("partial_lanes");
        // Reset masks valid at once, before any edge, and requests during reset
        // neither read nor write.
        a_read = 1; a_write = 1; a_wdata = '1; #1;
        if (a_valid || b_valid) fail("SIM_RAM_RESET_VALID");
        cycle(); cycle();
        a_read = 0; a_write = 0; reset_a = 0; reset_b = 0; cycle();
        if (INIT_FILE == "UNUSED") begin
            // Power-up words come from the seeded random fill: read every word
            // and require more than one distinct value across the array. The
            // vendor attribute this instance states must leave them so.
            if (dut.POWER_UP_UNINITIALIZED != "TRUE") fail("SIM_RAM_POWER_UP_ATTRIBUTE");
            a_read = 1;
            for (index = 0; index <= DEPTH; index = index + 1) begin
                if (index < DEPTH) a_address = ADDRESS_BITS'(index);
                #5; clk_a = 1; #1;
                if (index > 0) begin
                    if (index == 1) distinct_first = a_rdata;
                    else if (a_rdata !== distinct_first) distinct = distinct + 1;
                end
                if (!a_valid) fail("SIM_RAM_POWER_UP_VALID");
                #4; clk_a = 0;
                if (DUAL_CLOCK) begin #3; clk_b = 1; #7; clk_b = 0; end
                checks = checks + 1;
            end
            a_read = 0;
            if (distinct == 0) fail("SIM_RAM_POWER_UP_UNIFORM");
        end else begin
            // Preload: every word matches the image the top wrote to the file,
            // and the instance must not state the power-up that would discard it.
            if (dut.POWER_UP_UNINITIALIZED != "FALSE") fail("SIM_RAM_POWER_UP_ATTRIBUTE");
            for (index = 0; index < DEPTH; index = index + 1) expected[index] = preload_value(index);
            a_read = 1; b_read = 1;
            for (index = 0; index < DEPTH; index = index + 1) begin
                a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index); cycle();
            end
            a_read = 0; b_read = 0;
        end
        // A word written during reset must not have landed: write a known value
        // to address 0, then repeat the reset-masked write and read it back.
        a_write = 1; a_address = 0; a_wdata = DATA_BITS'('h5A); cycle();
        a_write = 0; a_read = 1; cycle();
        sample_a = a_rdata;
        reset_a = 1; a_write = 1; a_wdata = ~DATA_BITS'('h5A); #1;
        if (a_valid) fail("SIM_RAM_RESET_MASK");
        cycle();
        if (a_rdata !== sample_a) fail("SIM_RAM_RESET_DATA_CHANGED");
        reset_a = 0; a_write = 0; cycle();
        if (a_rdata !== DATA_BITS'('h5A)) fail("SIM_RAM_RESET_WRITE_LANDED");
        a_read = 0;
        // Populate all words through public writes, then read them back on both
        // ports with exactly one edge of latency.
        a_write = 1;
        for (index = 0; index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); a_wdata = DATA_BITS'(index * 37 + 19); cycle();
        end
        a_write = 0; a_read = 1; b_read = 1;
        for (index = 0; index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index);
            if (index == 1 && corrupt) begin force dut.a_rdata = '1; #1; end
            cycle();
        end
        // Disabled reads hold their data and drop valid while other words change.
        a_read = 0; b_read = 0; a_write = 1;
        for (index = 1; index < 16 && index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index);
            a_wdata = DATA_BITS'(index * 11 + 7); cycle();
        end
        // Same-port read during a full-lane write returns the new word at that edge.
        a_read = 1; a_address = ADDRESS_BITS'(DEPTH-1); a_wdata = DATA_BITS'('h69); cycle();
        a_read = 0;
        if (LANES == 1) begin
            // Masked whole-word write leaves storage and held outputs unchanged.
            a_wdata = ~DATA_BITS'('h69); a_byte_enable = '0; cycle();
            a_write = 0; a_read = 1; a_byte_enable = '1; cycle();
            if (a_rdata !== DATA_BITS'('h69)) fail("SIM_RAM_MASKED_WORD");
            a_read = 0;
        end else begin
            // Each lane and each lane pair writes only its own bytes.
            a_address = ADDRESS_BITS'(3); a_wdata = DATA_BITS'('h11223344); a_byte_enable = '1; cycle();
            for (lane = 0; lane < LANES; lane = lane + 1) begin
                a_wdata = DATA_BITS'('hA0A1A2A3) ^ DATA_BITS'(lane); a_byte_enable = LANES'(1 << lane); cycle();
            end
            a_wdata = DATA_BITS'('hC0C1C2C3); a_byte_enable = LANES'('b0101); cycle();
            a_wdata = DATA_BITS'('hD0D1D2D3); a_byte_enable = LANES'('b1010); cycle();
            a_write = 0; a_read = 1; a_byte_enable = '1; cycle();
            if (a_rdata !== DATA_BITS'('hD0C1D2C3)) fail("SIM_RAM_BYTE_LANES");
            if (partial_lanes) begin
                a_write = 1; a_byte_enable = LANES'('b0010); cycle();
                $fatal(1, "SIM_RAM_PARTIAL_LANES_ESCAPED");
            end
            a_read = 0;
        end
        // Simultaneous reads on both ports are allowed; a same-address A write
        // against an active B read is the forbidden collision.
        a_write = 0; a_read = 1; b_read = 1; a_address = 0; b_address = ADDRESS_BITS'(DEPTH-1); cycle();
        if (collision) begin
            a_write = 1; b_address = a_address; cycle();
            $fatal(1, "SIM_RAM_COLLISION_ESCAPED");
        end
        // Reset masks both valids at once; the array survives reset.
        reset_a = 1; reset_b = 1; #1;
        if (a_valid || b_valid) fail("SIM_RAM_RESET_VISIBLE");
        a_write = 1; a_wdata = 0; cycle();
        a_write = 0; a_read = 0; b_read = 0; reset_a = 0; reset_b = 0; cycle();
        a_read = 1; b_read = 1;
        for (index = 0; index < DEPTH; index = index + 1) begin
            a_address = ADDRESS_BITS'(index); b_address = ADDRESS_BITS'(DEPTH-1-index); cycle();
        end
        $display("PASS RAM double case=%0d width=%0d depth=%0d lanes=%0d dual_clock=%0d preload=%s checks=%0d",
            CASE_ID, DATA_BITS, DEPTH, LANES, DUAL_CLOCK, INIT_FILE, checks);
        done = 1;
    end
endmodule

// Primitive rules the wrapper forbids or masks are proved on the double itself.
module sim_ram_direct_case #(
    parameter bit DUAL_CLOCK = 0,
    parameter integer CASE_ID = 10
) (output logic done, output integer checks);
    localparam integer DEPTH = 32;
    localparam integer DATA_BITS = 16;
    localparam integer LANES = 2;
    logic clock0, clock1, wren_a, rden_a, rden_b;
    logic [4:0] address_a, address_b;
    logic [DATA_BITS-1:0] data_a, q_a, q_b;
    logic [LANES-1:0] byteena_a;
    integer collisions;
    n2m_sim_dual_port_ram #(.DEPTH(DEPTH), .DATA_BITS(DATA_BITS), .ADDRESS_BITS(5), .LANES(LANES),
        .DUAL_CLOCK(DUAL_CLOCK)) dut (.*);

    task automatic fail(input string name);
        $fatal(1, "%s case=%0d check=%0d", name, CASE_ID, checks);
    endtask
    task automatic edge_a;
        #5; clock0 = 1; #5; clock0 = 0; checks = checks + 1;
    endtask
    task automatic edge_b;
        if (DUAL_CLOCK) begin #3; clock1 = 1; #5; clock1 = 0; end
        else edge_a();
        checks = checks + 1;
    endtask

    initial begin
        done = 0; checks = 0; clock0 = 0; clock1 = 0; wren_a = 0; rden_a = 0; rden_b = 0;
        address_a = 0; address_b = 0; data_a = 0; byteena_a = '1; collisions = 0;
        #20;
        wren_a = 1; address_a = 5; data_a = 16'h1111; edge_a();
        if (!DUAL_CLOCK) begin
            // OLD_DATA: a B read at the same edge as the A write sees the old word.
            rden_b = 1; address_b = 5; data_a = 16'h2222; edge_a();
            if (q_b !== 16'h1111) fail("SIM_RAM_OLD_DATA");
            wren_a = 0; edge_a();
            if (q_b !== 16'h2222) fail("SIM_RAM_OLD_DATA_NEXT");
            rden_b = 0;
        end else begin
            // DONT_CARE: a B read of the word A is writing has no defined result;
            // the double returns unspecified data. The next clean read is exact.
            rden_b = 1; address_b = 5; data_a = 16'h2222; edge_b(); edge_a();
            if (q_b === 16'h1111 || q_b === 16'h2222) collisions = collisions + 1;
            wren_a = 0; edge_b();
            if (q_b !== 16'h2222) fail("SIM_RAM_DONT_CARE_NEXT");
            // A different-address write beside a B read is ordinary service.
            wren_a = 1; address_a = 6; data_a = 16'h3333; edge_b();
            if (q_b !== 16'h2222) fail("SIM_RAM_DUAL_CLOCK_READ");
            edge_a(); wren_a = 0; rden_b = 0;
        end
        // NEW_DATA_NO_NBE_READ: a same-port partial write returns the written
        // lane as new data and stores the merged word.
        wren_a = 1; rden_a = 1; address_a = 3; data_a = 16'h1234; byteena_a = '1; edge_a();
        if (q_a !== 16'h1234) fail("SIM_RAM_NEW_DATA");
        data_a = 16'hAABB; byteena_a = 2'b01; edge_a();
        if (q_a[7:0] !== 8'hBB) fail("SIM_RAM_NEW_DATA_LANE");
        wren_a = 0; byteena_a = '1; edge_a();
        if (q_a !== 16'h12BB) fail("SIM_RAM_MERGED_WORD");
        rden_a = 0;
        $display("PASS RAM double direct case=%0d dual_clock=%0d checks=%0d", CASE_ID, DUAL_CLOCK, checks);
        done = 1;
    end
endmodule

module tb_sim_ram_double;
    logic done_byte, done_pair, done_lanes, done_frame, done_preload_bytes, done_preload_bits,
        done_preload_words, done_direct, done_direct_dual;
    integer checks_byte, checks_pair, checks_lanes, checks_frame, checks_preload_bytes, checks_preload_bits,
        checks_preload_words, checks_direct, checks_direct_dual;
    integer fd, index;
    sim_ram_wrapper_case byte_case (.done(done_byte), .checks(checks_byte));
    sim_ram_wrapper_case #(.DATA_BITS(16), .DEPTH(80), .CASE_ID(1)) pair_case (.done(done_pair), .checks(checks_pair));
    sim_ram_wrapper_case #(.DATA_BITS(32), .DEPTH(64), .LANES(4), .CASE_ID(2)) lanes_case (.done(done_lanes), .checks(checks_lanes));
    sim_ram_wrapper_case #(.DATA_BITS(2), .DEPTH(600), .DUAL_CLOCK(1), .CASE_ID(3)) frame_case (.done(done_frame), .checks(checks_frame));
    sim_ram_wrapper_case #(.DATA_BITS(8), .DEPTH(256), .INIT_FILE("sim-ram-preload-bytes.mif"), .CASE_ID(4))
        preload_bytes_case (.done(done_preload_bytes), .checks(checks_preload_bytes));
    sim_ram_wrapper_case #(.DATA_BITS(1), .DEPTH(64), .INIT_FILE("sim-ram-preload-presence.mif"), .CASE_ID(5))
        preload_bits_case (.done(done_preload_bits), .checks(checks_preload_bits));
    sim_ram_wrapper_case #(.DATA_BITS(16), .DEPTH(32), .INIT_FILE("sim-ram-preload-words.hex"), .CASE_ID(6))
        preload_words_case (.done(done_preload_words), .checks(checks_preload_words));
    sim_ram_direct_case direct_case (.done(done_direct), .checks(checks_direct));
    sim_ram_direct_case #(.DUAL_CLOCK(1), .CASE_ID(11)) direct_dual_case (.done(done_direct_dual), .checks(checks_direct_dual));

    // Fixture files are written at time zero; the doubles read them at 1 ps.
    // +bad_preload writes one row with a non-hex digit, which the parser rejects.
    initial begin
        fd = $fopen("sim-ram-preload-bytes.mif", "w");
        $fwrite(fd, "DEPTH = 256;\nWIDTH = 8;\nADDRESS_RADIX = HEX;\nDATA_RADIX = HEX;\nCONTENT BEGIN\n");
        for (index = 0; index < 240; index = index + 1)
            $fwrite(fd, "%02x : %02x;\n", index, sim_ram_double_pkg::byte_image(index));
        if ($test$plusargs("bad_preload")) $fwrite(fd, "F0 : 0G;\n");
        $fwrite(fd, "[F0..FF] : 5A;\nEND;\n");
        $fclose(fd);
        fd = $fopen("sim-ram-preload-presence.mif", "w");
        $fwrite(fd, "-- presence bitmap fixture\nDEPTH = 64;\nWIDTH = 1;\nADDRESS_RADIX = HEX;\nDATA_RADIX = BIN;\n");
        $fwrite(fd, "CONTENT BEGIN\n[00..1F] : 1;\n[20..3F] : 0;\nEND;\n");
        $fclose(fd);
        fd = $fopen("sim-ram-preload-words.hex", "w");
        for (index = 0; index < 32; index = index + 1) $fwrite(fd, "%04x\n", sim_ram_double_pkg::word_image(index));
        $fclose(fd);
    end
    initial begin
        wait (done_byte && done_pair && done_lanes && done_frame && done_preload_bytes && done_preload_bits &&
            done_preload_words && done_direct && done_direct_dual);
        $display("PASS Intel RAM double cases=9 checks=%0d", checks_byte + checks_pair + checks_lanes + checks_frame +
            checks_preload_bytes + checks_preload_bits + checks_preload_words + checks_direct + checks_direct_dual);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "SIM_RAM_WATCHDOG");
    end
endmodule

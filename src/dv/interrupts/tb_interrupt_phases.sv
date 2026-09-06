`timescale 1ns/1ps
`default_nettype none
module tb_interrupt_phases;
    logic clk_sys, reset_sys, core_reset, gb_tick, io_commit, io_write;
    logic [15:0] io_address;
    logic [7:0] io_wdata, io_rdata, ie_stored, ie_observe;
    logic [4:0] source_level, irq_ack, if_stored, if_observe;
    logic io_selected, capture_b;
    logic [4:0] captured_if, frozen_vector;
    logic [7:0] captured_ie;
    integer checks, trace_file, policy, arrival, scenario;
    logic [4:0] expected_b, expected_after;
    bit observation_fault;
    n2m_interrupts dut (.source_event(5'd0), .*);

    // Sample the public pre-B observation exactly as the CPU recorder does.
    // Scripted expectations below never use the DUT's operation or history.
    always @(posedge clk_sys) begin
        if (capture_b) begin
            captured_if = if_observe;
            captured_ie = ie_observe;
        end
    end
    task automatic edge_cycle;
        #4; clk_sys = 1; #1; clk_sys = 0;
    endtask
    task automatic check(input logic [4:0] flags, input logic [7:0] enables);
        #1;
        $fdisplay(trace_file, "%0d,%0d,%02h,%02h,%02h,%02h,%02h,%02h", scenario, checks,
            flags, if_observe, enables, ie_observe, if_stored, ie_stored);
        if (if_observe !== flags || ie_observe !== enables)
            $fatal(1, "INTERRUPT_PHASE_OBSERVE case=%0d check=%0d expected_if=%02h actual_if=%02h expected_ie=%02h actual_ie=%02h",
                scenario, checks, flags, if_observe, enables, ie_observe);
        checks = checks + 1;
    endtask
    task automatic reset_case;
        core_reset = 1; gb_tick = 0; io_commit = 0; io_write = 0;
        irq_ack = 0; source_level = 0; capture_b = 0;
        edge_cycle(); core_reset = 0; edge_cycle(); check(0,0);
    endtask
    task automatic begin_a(input bit write_register, input logic [15:0] address,
                           input logic [7:0] data, input logic [4:0] ack);
        gb_tick = 1; io_commit = write_register; io_write = write_register;
        io_address = address; io_wdata = data; irq_ack = ack;
        edge_cycle();
        gb_tick = 0; io_commit = 0; io_write = 0; irq_ack = 0;
    endtask
    task automatic finish_b(input logic [4:0] flags, input logic [7:0] enables);
        check(flags,enables); capture_b = 1; edge_cycle(); capture_b = 0;
        if (captured_if !== flags || captured_ie !== enables)
            $fatal(1, "INTERRUPT_PHASE_CAPTURE case=%0d expected_if=%02h actual_if=%02h", scenario,flags,captured_if);
        check(flags,enables);
    endtask
    task automatic select_t3(input logic [4:0] literal_vector);
        frozen_vector = if_observe & ie_observe[4:0];
        if (frozen_vector !== literal_vector)
            $fatal(1, "INTERRUPT_T3_VECTOR case=%0d expected=%02h actual=%02h",scenario,literal_vector,frozen_vector);
        edge_cycle();
    endtask
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,io_commit,io_write,io_address,
            io_wdata,source_level,irq_ack,io_rdata,if_stored,ie_stored,if_observe,ie_observe,
            capture_b,captured_if,captured_ie,frozen_vector);
        trace_file = $fopen("trace.csv","w");
        if (!trace_file) $fatal(1,"INTERRUPT_PHASE_TRACE");
        $fdisplay(trace_file,"case,check,expected_if,actual_if,expected_ie,actual_ie,stored_if,stored_ie");
        clk_sys = 0; reset_sys = 1; core_reset = 0; gb_tick = 0;
        io_commit = 0; io_write = 0; io_address = 0; io_wdata = 0;
        source_level = 0; irq_ack = 0; capture_b = 0; frozen_vector = 0;
        captured_if = 0; captured_ie = 0; checks = 0; scenario = 0;
        observation_fault = $test$plusargs("observation_fault");
        edge_cycle(); reset_sys = 0;
        // Source placement: pre-A, NBA-at-A, post-A, just-before-B,
        // NBA-at-B, post-B. Policies: no operation, IF clear, acknowledge.
        for (policy = 0; policy < 3; policy = policy + 1)
            for (arrival = 0; arrival < 6; arrival = arrival + 1) begin
                reset_case();
                if (arrival == 0) source_level = 1;
                gb_tick = 1; io_commit = policy == 1; io_write = policy == 1;
                io_address = 16'hFF0F; io_wdata = 0; irq_ack = policy == 2 ? 5'd1 : 5'd0;
                #4; clk_sys = 1;
                if (arrival == 1) source_level <= 1;
                #1; clk_sys = 0;
                gb_tick = 0; io_commit = 0; io_write = 0; irq_ack = 0;
                if (arrival == 2) source_level = 1;
                #2;
                if (arrival == 3) source_level = 1;
                expected_b = policy == 0 && arrival < 4 ? 5'd1 : 5'd0;
                expected_after = arrival >= 4 ? 5'd1 : expected_b;
                if (observation_fault && scenario == 0) force dut.if_observe = 5'd0;
                check(expected_b,0);
                capture_b = 1;
                #4; clk_sys = 1;
                if (arrival == 4) source_level <= 1;
                #1; clk_sys = 0; capture_b = 0;
                if (captured_if !== expected_b || captured_ie !== 0)
                    $fatal(1,"INTERRUPT_PHASE_CAPTURE case=%0d",scenario);
                if (arrival == 5) begin
                    check(expected_b,0); source_level = 1;
                end
                check(expected_after,0);
                // No later gb_tick: B and source-history processing complete
                // while emulated time is paused, including held levels.
                repeat (3) begin edge_cycle(); check(expected_after,0); end
                scenario = scenario + 1;
            end

        // Public CPU-boundary scripts. These do not execute a CPU or claim
        // peripheral collision internals; every expected mask is literal.
        reset_case();
        source_level = 5'h1F; edge_cycle();
        begin_a(1,16'hFFFF,8'hA5,0); finish_b(5'h1F,8'hA5);
        select_t3(5'h05);
        begin_a(0,0,0,5'h04); finish_b(5'h1B,8'hA5);
        if (frozen_vector !== 5'h05) $fatal(1,"INTERRUPT_SNAPSHOT_CHANGED");
        scenario = scenario + 1;

        // High stack write changes IE before the next T3: canceled vector.
        reset_case();
        begin_a(1,16'hFF0F,8'h05,0); finish_b(5'h05,0);
        begin_a(1,16'hFFFF,8'h05,0); finish_b(5'h05,8'h05);
        select_t3(5'h05);
        begin_a(1,16'hFFFF,8'h02,0);
        if (ie_stored !== 8'h05 || io_rdata !== 8'h05) $fatal(1,"INTERRUPT_PREWRITE_IE");
        finish_b(5'h05,8'h02); select_t3(0);
        begin_a(0,0,0,0); finish_b(5'h05,8'h02);
        scenario = scenario + 1;

        // High stack IE reselects STAT. A low-stack IF write after T3 changes
        // retirement flags, but must not change the previously held vector.
        reset_case();
        begin_a(1,16'hFF0F,8'h03,0); finish_b(5'h03,0);
        begin_a(1,16'hFFFF,8'h03,0); finish_b(5'h03,8'h03);
        select_t3(5'h03);
        begin_a(1,16'hFFFF,8'h02,0); finish_b(5'h03,8'h02);
        select_t3(5'h02);
        begin_a(1,16'hFF0F,8'h1F,5'h02);
        if (if_stored !== 5'h03 || io_rdata !== 8'hE3) $fatal(1,"INTERRUPT_PREWRITE_IF");
        finish_b(5'h1D,8'h02);
        if (frozen_vector !== 5'h02) $fatal(1,"INTERRUPT_SNAPSHOT_CHANGED");
        scenario = scenario + 1;

        // A low IE write can disable selection for a later boundary, while
        // the already frozen vector and chosen acknowledgement remain valid.
        begin_a(1,16'hFF0F,8'h03,0); finish_b(5'h03,8'h02);
        select_t3(5'h02);
        begin_a(1,16'hFFFF,8'h00,5'h02); finish_b(5'h01,8'h00);
        if (frozen_vector !== 5'h02) $fatal(1,"INTERRUPT_SNAPSHOT_CHANGED");
        select_t3(0);
        scenario = scenario + 1;
        // A committed service read must have no write side effect.
        gb_tick = 1; io_commit = 1; io_write = 0; io_address = 16'hFF0F; io_wdata = 0;
        edge_cycle(); gb_tick = 0; io_commit = 0;
        finish_b(5'h01,8'h00);
        scenario = scenario + 1;
        $display("PASS interrupt phase and CPU snapshot scripts cases=%0d checks=%0d",scenario,checks);
        $fclose(trace_file); $finish;
    end
    initial begin
        #100000; $fatal(1,"INTERRUPT_PHASE_WATCHDOG");
    end
endmodule

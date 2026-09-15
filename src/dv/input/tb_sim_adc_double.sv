`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Unit test for the ADC control and PLL doubles behind n2m_adc_backend in
// simulation. Contract: wiki/src/fpga-controls.md. Plan: src/dv/input/README.md.
//
// The test drives the backend's public ports directly, with the reference
// clock, PLL reset and system reset under its own control, and writes the
// two-column channel stimulus files at time zero in the builder's format.
module tb_sim_adc_double;
    localparam integer LOCK_CYCLES = 64;
    localparam integer CONVERSION_ADC_CYCLES = 80;
    logic clk_sys;
    logic clk_reference;
    logic clk_adc;
    logic pll_areset;
    logic reset_sys;
    logic pll_locked;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    integer fd, channel, replies, c0_edges;
    integer accepted_cycle, cycle_count, latency_cycles;
    real lock_release_ns, lock_rise_ns;
    bit corrupt, bad_channel, missing;
    bit response_seen;
    bit accepted;
    logic [4:0] seen_channel;
    logic [11:0] seen_data;

    n2m_adc_backend u_adc (
        .clk_sys(clk_sys), .clk_adc_reference(clk_reference), .pll_areset(pll_areset), .reset_sys(reset_sys),
        .command_valid(command_valid), .command_channel(command_channel), .command_ready(command_ready),
        .response_valid(response_valid), .response_channel(response_channel), .response_data(response_data),
        .clk_adc(clk_adc), .pll_locked(pll_locked)
    );

    initial begin clk_sys = 1'b0; forever #20 clk_sys = !clk_sys; end
    initial begin clk_reference = 1'b0; forever #50 clk_reference = !clk_reference; end

    always @(posedge clk_adc) c0_edges = c0_edges + 1;
    // Monitor: samples the public handshake at the edge the backend samples it.
    // Registers hold seeded random values until the first reset edge, so the
    // handshake is observed only outside system reset.
    always @(posedge clk_sys) begin
        cycle_count = cycle_count + 1;
        if (reset_sys) ;
        else if (command_valid && command_ready) begin
            if (accepted) $fatal(1, "ADC_DOUBLE_DUPLICATE_ACCEPT cycle=%0d", cycle_count);
            accepted = 1'b1; accepted_cycle = cycle_count;
        end
        if (!reset_sys && response_valid) begin
            if (response_seen) $fatal(1, "ADC_DOUBLE_DUPLICATE_RESPONSE cycle=%0d", cycle_count);
            response_seen = 1'b1; seen_channel = response_channel; seen_data = response_data;
            replies = replies + 1;
        end
    end
    always @(negedge clk_sys) begin
        if (corrupt && response_valid && response_channel == 5'd1) force response_data = 12'd0;
    end

    // Hold one command until accepted, then wait for exactly one tagged response
    // and compare it with the independent expected code.
    task automatic issue(input logic [4:0] channel_id);
        response_seen = 1'b0; accepted = 1'b0;
        @(negedge clk_sys); command_valid = 1'b1; command_channel = channel_id;
        wait (accepted);
        @(negedge clk_sys); command_valid = 1'b0;
    endtask

    task automatic convert(input logic [4:0] channel_id, input logic [11:0] expected_code);
        issue(channel_id);
        // Ready stays low for the whole conversion; the response is one cycle.
        while (!response_seen) begin
            @(negedge clk_sys);
            if (command_ready && !response_seen) $fatal(1, "ADC_DOUBLE_READY_WHILE_BUSY channel=%0d", channel_id);
        end
        latency_cycles = cycle_count - accepted_cycle;
        if (seen_channel !== channel_id || seen_data !== expected_code)
            $fatal(1, "ADC_DOUBLE_DATA expected=%0d,%0d actual=%0d,%0d", channel_id, expected_code, seen_channel, seen_data);
        // 80 ADC cycles at 10 MHz is 8 us, or 200 system cycles at 25 MHz.
        if (latency_cycles < 195 || latency_cycles > 206)
            $fatal(1, "ADC_DOUBLE_LATENCY channel=%0d cycles=%0d", channel_id, latency_cycles);
    endtask

    initial begin
        pll_areset = 1'b1; reset_sys = 1'b1; command_valid = 1'b0; command_channel = 5'd1;
        replies = 0; c0_edges = 0; cycle_count = 0;
        response_seen = 1'b0; accepted = 1'b0;
        corrupt = $test$plusargs("corrupt");
        bad_channel = $test$plusargs("bad_channel");
        missing = $test$plusargs("missing_stimulus");
        // Builder-format stimulus: "time voltage" rows. Channel 2 carries four
        // rows to prove cyclic replay and clamping; channel 1 matches the product
        // fixture. +missing_stimulus truncates channel 5 so the load fails.
        for (channel = 0; channel < 17; channel = channel + 1) begin
            fd = $fopen($sformatf("adc_ch%0d.txt", channel), "w");
            if (channel == 1) $fwrite(fd, "0 0.625\n");
            else if (channel == 2) $fwrite(fd, "0 1.25\n8 2.0\n16 3.3\n24 -0.5\n");
            else if (channel != 5 || !missing) $fwrite(fd, "0 0.0\n");
            $fclose(fd);
        end
        // PLL reset: c0 stays low and locked stays low. The time-zero X-to-value
        // transition under --x-initial-edge is not a clock edge; count after it.
        #1; c0_edges = 0; #999;
        if (c0_edges != 0 || pll_locked) $fatal(1, "ADC_DOUBLE_PLL_RESET c0_edges=%0d locked=%0b", c0_edges, pll_locked);
        // Release: c0 runs at the 1:1 ratio, 10 MHz, and locked rises after
        // LOCK_CYCLES reference edges.
        @(negedge clk_reference); pll_areset = 1'b0; lock_release_ns = $realtime;
        c0_edges = 0;
        #1000;
        if (c0_edges != 10) $fatal(1, "ADC_DOUBLE_PLL_RATIO edges=%0d", c0_edges);
        if (pll_locked) $fatal(1, "ADC_DOUBLE_PLL_EARLY_LOCK");
        wait (pll_locked); lock_rise_ns = $realtime;
        // Release at a falling edge: the first reference edge is 50 ns later and
        // locked rises on the edge after LOCK_CYCLES counted edges.
        if (lock_rise_ns - lock_release_ns < 6400.0 || lock_rise_ns - lock_release_ns > 6500.0)
            $fatal(1, "ADC_DOUBLE_PLL_LOCK_DELAY ns=%f", lock_rise_ns - lock_release_ns);
        // Control reset: the command port is not ready.
        repeat (4) @(negedge clk_sys);
        if (command_ready) $fatal(1, "ADC_DOUBLE_READY_IN_RESET");
        reset_sys = 1'b0;
        repeat (2) @(negedge clk_sys);
        if (!command_ready) $fatal(1, "ADC_DOUBLE_NOT_READY");
        // Channel tagging, expected codes and replay order.
        convert(5'd1, 12'd1024);
        convert(5'd2, 12'd2048);
        convert(5'd2, 12'd3276);
        convert(5'd2, 12'd4095);
        convert(5'd2, 12'd0);
        convert(5'd2, 12'd2048);
        convert(5'd1, 12'd1024);
        if (bad_channel) begin
            @(negedge clk_sys); command_valid = 1'b1; command_channel = 5'd3;
            repeat (2) @(negedge clk_sys);
            $fatal(1, "ADC_DOUBLE_BAD_CHANNEL_ESCAPED");
        end
        // System reset during a conversion abandons it: no response arrives.
        issue(5'd1);
        repeat (50) @(negedge clk_sys);
        reset_sys = 1'b1; repeat (3) @(negedge clk_sys); reset_sys = 1'b0;
        repeat (400) @(negedge clk_sys);
        if (response_seen) $fatal(1, "ADC_DOUBLE_RESET_RESPONSE");
        convert(5'd2, 12'd3276);
        // Lock loss during a conversion abandons it and blocks the port until
        // lock returns; c0 stops while areset is high.
        issue(5'd1);
        repeat (50) @(negedge clk_sys);
        pll_areset = 1'b1;
        #10;
        if (pll_locked) $fatal(1, "ADC_DOUBLE_LOCK_HOLDS_THROUGH_RESET");
        #200; c0_edges = 0; #1000;
        if (c0_edges != 0) $fatal(1, "ADC_DOUBLE_C0_RUNS_IN_RESET");
        repeat (300) @(negedge clk_sys);
        if (response_seen || command_ready) $fatal(1, "ADC_DOUBLE_LOCK_LOSS response=%0b ready=%0b", response_seen, command_ready);
        @(negedge clk_reference); pll_areset = 1'b0;
        wait (pll_locked);
        repeat (2) @(negedge clk_sys);
        if (response_seen) $fatal(1, "ADC_DOUBLE_LOCK_LOSS_RESPONSE");
        convert(5'd1, 12'd1024);
        convert(5'd2, 12'd4095);
        $display("PASS ADC doubles replies=%0d codes=1024,2048,3276,4095,0 pll_ratio=1/1 lock_cycles=%0d latency_cycles=%0d",
            replies, LOCK_CYCLES, latency_cycles);
        $finish;
    end
    initial begin #4000000; $fatal(1, "ADC_DOUBLE_WATCHDOG"); end
endmodule

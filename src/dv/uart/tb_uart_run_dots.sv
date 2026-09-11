`timescale 1ns/1ps
`default_nettype none
module tb_uart_run_dots;
    logic clk_sys, reset_sys, start, gb_tick, emulated_tick, paused, pause_request, core_reset;
    logic core_initialized, instruction_complete, retirement_valid, cpu_stopped;
    logic [7:0] command, status;
    logic [31:0] step_budget, epoch;
    logic [63:0] dot_count, retirement_count, completed_dot;
    logic busy, done;
    n2m_input_pkg::input_write_t input_write, accepted_input;
    n2m_interfaces_pkg::run_dots_t run_dots_result;
    integer ticks, phase, checks, cycles, before_ticks;
    bit corrupt;
    // Model the composition: STOP withholds the emulated tick from every owner,
    // so a sleeping oscillator delivers no further dot to this countdown.
    n2m_timebase u_timebase (.clk_sys, .reset_sys, .core_reset, .pause_request,
        .gb_tick(emulated_tick), .paused);
    assign gb_tick = emulated_tick && !cpu_stopped;
    n2m_uart_core_control u_control (.*);
    assign retirement_valid = gb_tick && instruction_complete;
    always #20 clk_sys = !clk_sys;
    // Independent rational-clock equation uses only public pause/reset inputs.
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) begin ticks = 0; phase = 0; end
        else if (!paused) begin
            if (emulated_tick !== (phase+65536 >= 390625)) $fatal(1,"RUN_DOTS_PHASE");
            if (gb_tick !== (emulated_tick && !cpu_stopped)) $fatal(1,"RUN_DOTS_STOP_GATE");
            phase = phase+65536;
            if (phase >= 390625) begin
                phase = phase-390625;
                if (!cpu_stopped) ticks = ticks+1;
            end
        end else if (gb_tick) $fatal(1,"RUN_DOTS_PAUSED_TICK");
    end
    task automatic request(input logic [7:0] op, input integer budget,
                           input integer stop_after, input integer expected_ticks,
                           input integer expected_reason, input integer expected_status);
        @(negedge clk_sys); before_ticks=ticks; command=op; step_budget=32'(budget); start=1;
        @(negedge clk_sys); start=0; cycles=0;
        while (!done && cycles < budget*7+30) begin
            if (stop_after >= 0 && ticks-before_ticks >= stop_after) cpu_stopped=1;
            @(negedge clk_sys); cycles=cycles+1;
        end
        if (!done || status !== 8'(expected_status) || !paused) $fatal(1,"RUN_DOTS_COMPLETION");
        if (ticks-before_ticks != expected_ticks || completed_dot !== 64'(ticks)) $fatal(1,"RUN_DOTS_COUNT");
        if (op == 15) begin
            if (corrupt) force u_control.run_dots_result.executed=0;
            #1;
            if (run_dots_result.executed !== 32'(expected_ticks) ||
                run_dots_result.reason !== 8'(expected_reason) || run_dots_result.dot !== 64'(ticks))
                $fatal(1,"RUN_DOTS_RESULT");
        end
        before_ticks=ticks;
        repeat(12) @(negedge clk_sys);
        if (ticks != before_ticks || dot_count !== 64'(ticks)) $fatal(1,"RUN_DOTS_SETTLED");
        checks=checks+1;
    endtask
    initial begin
        clk_sys=0; reset_sys=1; start=0; command=0; step_budget=1; input_write='0;
        core_initialized=1; instruction_complete=0; cpu_stopped=0;
        ticks=0; phase=0; checks=0; cycles=0; before_ticks=0;
        corrupt=$test$plusargs("CORRUPT_RESULT");
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,reset_sys,start,command,step_budget,gb_tick,emulated_tick,paused,pause_request,
            core_reset,cpu_stopped,instruction_complete,retirement_valid,dot_count,retirement_count,
            completed_dot,run_dots_result,busy,done,status,ticks,phase,checks);
        repeat(5) @(negedge clk_sys); reset_sys=0;
        request(15,1,-1,1,0,0);
        instruction_complete=1; request(15,7,-1,7,0,0);
        instruction_complete=0; request(15,70224,-1,70224,0,0);
        request(15,10,3,3,1,0);
        request(15,70224,-1,0,1,0);
        cpu_stopped=0; request(15,4,-1,4,0,0);
        cpu_stopped=0; instruction_complete=1; request(6,10,-1,1,0,0);
        instruction_complete=0; request(6,5,-1,5,0,8);
        // Global reset aborts an in-flight operation and resets the timebase.
        @(negedge clk_sys); command=15; step_budget=70224; start=1;
        @(negedge clk_sys); start=0;
        repeat(25) @(negedge clk_sys); reset_sys=1;
        repeat(3) @(negedge clk_sys); reset_sys=0;
        repeat(12) @(negedge clk_sys);
        if (busy || done || !paused || dot_count != 0 || retirement_count != 0) $fatal(1,"RUN_DOTS_RESET");
        checks=checks+1;
        if (checks != 9) $fatal(1,"RUN_DOTS_COVERAGE");
        $display("PASS UART RUN_DOTS cases=9 exact_ticks phase STOP settlement reset STEP"); $finish;
    end
    initial begin #30000000; $fatal(1,"RUN_DOTS_WATCHDOG"); end
endmodule
`default_nettype wire

`timescale 1ns/1ps
`default_nettype none

module tb_cpu_bus;
    logic clk_sys;
    logic reset_sys;
    logic core_reset;
    logic gb_tick;
    logic active;
    logic [15:0] plan_address;
    logic [7:0] plan_write_data;
    logic plan_write;
    n2m_cpu_pkg::access_kind_t plan_kind;
    logic response_valid;
    logic [1:0] phase;
    logic request_valid;
    logic [15:0] address;
    logic [7:0] write_data;
    logic write_enable;
    n2m_cpu_pkg::access_kind_t access_kind;
    logic commit;
    logic cycle_end;
    logic fault;
    integer expected_phase;
    integer expected_commits;
    integer cycles;
    integer iteration;
    integer t;
    integer pause_phase;
    integer trace;
    bit expected_commit;
    bit missing_response;
    bit late_active;
    bit change_after_t1;

    n2m_cpu_bus dut (.*);

    task automatic edge_cycle(input bit tick);
        clk_sys = 0;
        gb_tick = tick;
        #4;
        expected_commit = tick && expected_phase == 3 && active && !core_reset && !reset_sys && plan_kind != 0 && (plan_write || response_valid);
        if (commit !== expected_commit)
            $fatal(1, "CPU_BUS_MISMATCH commit cycle=%0d phase=%0d expected=%0d actual=%0d", cycles, expected_phase, expected_commit, commit);
        if (request_valid && (address !== plan_address || write_data !== plan_write_data || write_enable !== plan_write || access_kind !== plan_kind))
            $fatal(1, "CPU_BUS_MISMATCH request payload");
        $fdisplay(trace, "%0d,%0d,%0d,%0d,%0d,%04h,%0d", cycles, expected_phase, active, tick, core_reset, address, commit);
        if (expected_commit) expected_commits = expected_commits + 1;
        #1 clk_sys = 1;
        if (core_reset || reset_sys) expected_phase = 0;
        else if (tick) expected_phase = (expected_phase + 1) % 4;
        #1;
        if (phase !== 2'(expected_phase))
            $fatal(1, "CPU_BUS_MISMATCH phase cycle=%0d expected=%0d actual=%0d", cycles, expected_phase, phase);
        if (fault) $fatal(1, "CPU_BUS_MISMATCH unexpected fault");
        #4;
        clk_sys = 0;
        cycles = cycles + 1;
    endtask

    initial begin
        clk_sys = 0;
        reset_sys = 1;
        core_reset = 0;
        gb_tick = 0;
        active = 0;
        plan_address = 16'hc123;
        plan_write_data = 8'h96;
        plan_write = 0;
        plan_kind = n2m_cpu_pkg::ACCESS_DATA;
        response_valid = 1;
        expected_phase = 0;
        expected_commits = 0;
        cycles = 0;
        missing_response = $test$plusargs("missing_response");
        late_active = $test$plusargs("late_active");
        change_after_t1 = $test$plusargs("change_after_t1");
        trace = $fopen("bus-trace.csv", "w");
        if (!trace) $fatal(1, "CPU_BUS_TRACE_OPEN");
        $fdisplay(trace, "cycle,phase,active,tick,reset,address,commit");
        $dumpfile("waves/cpu-bus.vcd");
        $dumpvars(0, tb_cpu_bus);
        edge_cycle(0);
        reset_sys = 0;
        if (late_active) begin
            edge_cycle(1);
            active = 1;
            edge_cycle(0);
            $fatal(1, "CPU_BUS_NEGATIVE_DID_NOT_FAIL active");
        end
        active = 1;
        if (change_after_t1) begin
            edge_cycle(1);
            plan_address = 16'hc999;
            edge_cycle(0);
            $fatal(1, "CPU_BUS_NEGATIVE_DID_NOT_FAIL T1 payload");
        end
        if (missing_response) begin
            edge_cycle(1);
            edge_cycle(1);
            edge_cycle(1);
            response_valid = 0;
            edge_cycle(1);
            $fatal(1, "CPU_BUS_NEGATIVE_DID_NOT_FAIL response");
        end
        // Both directions and every possible host-pause phase retain one
        // complete four-tick transaction. Idle system edges cannot commit.
        for (iteration = 0; iteration < 8; iteration = iteration + 1) begin
            plan_write = iteration >= 4;
            plan_address = 16'hc123 + 16'(iteration);
            pause_phase = iteration % 4;
            for (t = 0; t < 4; t = t + 1) begin
                if (t == pause_phase) begin
                    edge_cycle(0);
                    edge_cycle(0);
                    edge_cycle(0);
                end
                edge_cycle(1);
            end
        end
        // Inactive HALT cycles retain phase but never access memory. Reactivate
        // only at the next full M boundary, regardless of when wake is noticed.
        active = 0;
        for (iteration = 0; iteration < 4; iteration = iteration + 1) begin
            for (t = 0; t < 4; t = t + 1) edge_cycle(1);
            edge_cycle(0);
        end
        active = 1;
        for (t = 0; t < 4; t = t + 1) edge_cycle(1);
        // Reset cancels preparation at each phase, including the would-be T4.
        for (iteration = 0; iteration < 4; iteration = iteration + 1) begin
            for (t = 0; t < iteration; t = t + 1) edge_cycle(1);
            core_reset = 1;
            edge_cycle(1);
            core_reset = 0;
            for (t = 0; t < 4; t = t + 1) edge_cycle(1);
        end
        if (expected_commits != 13) $fatal(1, "CPU_BUS_COVERAGE expected=13 actual=%0d", expected_commits);
        $fclose(trace);
        $display("PASS CPU bus commits=13 pause_phases=4 reset_phases=4 inactive_cycles=4");
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "CPU_BUS_TIMEOUT");
    end
endmodule

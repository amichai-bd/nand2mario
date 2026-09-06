`timescale 1ns/1ps
`default_nettype none
module tb_cpu_step;
    logic clk_sys, reset_sys, core_reset, gb_tick, paused, pause_request, step_active;
    logic instruction_complete, retirement_valid, fault, initialized;
    logic request_valid, write_enable, bus_commit;
    logic [15:0] address;
    logic [7:0] write_data, read_data, ie;
    logic [4:0] iflags, irq_ack;
    logic response_valid;
    logic [63:0] dot_before;
    n2m_cpu_pkg::access_kind_t access_kind;
    n2m_interfaces_pkg::retirement_t retirement;
    logic [7:0] memory [65536];
    integer item, scenario, steps, events, irq_events, ticks, system_edges, trace;
    logic [63:0] stop_dot;
    logic [15:0] stop_pc;
    bit suppress, missing;
    n2m_timebase u_timebase (.*);
    n2m_cpu dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .profile_id(8'd1), .epoch(32'd1), .dot_before(dot_before), .ie(ie), .iflags(iflags),
        .buttons(8'd0), .read_data(read_data), .response_valid(response_valid),
        .joyp_selected_active(1'b0), .wake_request(1'b0),
        .request_valid(request_valid), .address(address), .write_data(write_data),
        .write_enable(write_enable), .access_kind(access_kind), .bus_commit(bus_commit),
        .address_effect(), .address_effect_resolved(), .address_effect_sample(), .address_effect_phase(),
        .irq_ack(irq_ack), .halted(), .stopped(), .locked(), .initialized(initialized), .fault(fault),
        .ime_observe(), .ime_delay_observe(), .stop_execute(), .divider_reset_request(),
        .instruction_complete(instruction_complete), .retirement_valid(retirement_valid), .retirement(retirement)
    );
    assign pause_request = !step_active || instruction_complete;
    assign read_data = memory[address];
    assign response_valid = !(missing && scenario == 0 && dot_before == 7);
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
        if (instruction_complete) step_active <= 0;
    end
    task automatic edge_cycle;
        #4;
        if (!reset_sys && !core_reset) begin
            if (gb_tick) ticks = ticks + 1;
            if (missing && scenario == 0 && gb_tick && dot_before == 7) begin
                if (instruction_complete) $fatal(1,"CPU_STEP_FALSE_MISSING_COMPLETE");
                $display("CPU_STEP_MISSING_SUPPRESSED dot=8");
            end else if (instruction_complete !== (gb_tick && dot_before + 1 == stop_dot && step_active))
                $fatal(1,"CPU_STEP_COMPLETE case=%0d dot=%0d expected=%0d actual=%0d",scenario,dot_before+1,
                    gb_tick && dot_before+1 == stop_dot && step_active,instruction_complete);
        end
        clk_sys = 1; #2;
        if (!reset_sys && !core_reset && retirement_valid) begin
            $fdisplay(trace,"%0d,%0d,%0d,%0d,%04h,%0d",scenario,events,retirement.kind,retirement.dot,retirement.pc_after,paused);
            if (retirement.kind == 1) begin
                if (scenario != 1 || retirement.dot != 32 || retirement.pc_after != 16'h0040 || paused)
                    $fatal(1,"CPU_STEP_INTERRUPT_EVENT");
                irq_events = irq_events + 1;
            end else begin
                if (retirement.dot != stop_dot || retirement.pc_after != stop_pc || !paused || dot_before != stop_dot)
                    $fatal(1,"CPU_STEP_RETIRE case=%0d expected_dot=%0d actual_dot=%0d expected_pc=%04h actual_pc=%04h paused=%0d",
                        scenario,stop_dot,retirement.dot,stop_pc,retirement.pc_after,paused);
            end
            events = events + 1;
        end
        #1; clk_sys = 0;
    endtask
    task automatic step_one(input logic [63:0] expected_dot, input logic [15:0] expected_pc);
        stop_dot = expected_dot; stop_pc = expected_pc;
        step_active = 1; system_edges = 0;
        while (step_active || !paused || retirement_valid) begin
            edge_cycle(); system_edges = system_edges + 1;
            if (system_edges > 1000) $fatal(1,"CPU_STEP_TIMEOUT");
        end
        // B is permitted after pause: wait enough system clocks to publish,
        // then prove no extra T enable over more than a full divider period.
        repeat (30) edge_cycle();
        if (dot_before != expected_dot || !paused) $fatal(1,"CPU_STEP_EXTRA_DOT");
        steps = steps + 1;
    endtask
    initial begin
        clk_sys = 0; reset_sys = 1; core_reset = 0; step_active = 0;
        dot_before = 0; ie = 0; iflags = 0; steps = 0; events = 0; irq_events = 0; ticks = 0;
        stop_dot = 0; stop_pc = 0; scenario = 0;
        suppress = $test$plusargs("suppress"); missing = $test$plusargs("missing");
        trace = $fopen("trace.csv","w"); if (!trace) $fatal(1,"CPU_STEP_TRACE");
        $fdisplay(trace,"case,event,kind,dot,pc_after,paused");
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,paused,pause_request,step_active,
            instruction_complete,retirement_valid,retirement,dot_before,request_valid,address,
            write_data,write_enable,bus_commit,ie,iflags,irq_ack,response_valid,fault);
        for (item = 0; item < 65536; item = item + 1) memory[item] = 0;
        memory['h100] = 0; memory['h101] = 'h3E; memory['h102] = 'h12;
        memory['h103] = 'h06; memory['h104] = 'h34; memory['h105] = 'h76;
        edge_cycle(); reset_sys = 0; core_reset = 1; edge_cycle(); core_reset = 0; edge_cycle();
        if (suppress) force dut.instruction_complete = 1'b0;
        step_one(8,16'h0101); step_one(16,16'h0103); step_one(24,16'h0105); step_one(28,16'h0106);
        scenario = 1; core_reset = 1; edge_cycle(); core_reset = 0;
        memory['h100] = 'hFB; memory['h101] = 0; memory['h102] = 0; memory['h40] = 0;
        ie = 1; iflags = 1; edge_cycle();
        step_one(8,16'h0101); step_one(12,16'h0102); step_one(36,16'h0041);
        if (steps != 7 || events != 8 || irq_events != 1 || ticks != 64)
            $fatal(1,"CPU_STEP_COUNTS steps=%0d events=%0d irq=%0d ticks=%0d",steps,events,irq_events,ticks);
        $display("PASS CPU STEP timebase steps=7 records=8 interrupts=1 ticks=64");
        $fclose(trace); $finish;
    end
    initial begin
        #100000; $fatal(1,"CPU_STEP_WATCHDOG");
    end
endmodule

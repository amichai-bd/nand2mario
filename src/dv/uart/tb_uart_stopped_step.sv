`timescale 1ns/1ps
`default_nettype none
module tb_uart_stopped_step;
    logic clk_sys, reset_sys, start, gb_tick, paused, pause_request, core_reset;
    logic core_initialized, instruction_complete, retirement_valid, cpu_stopped;
    logic [7:0] command, input_buttons, buttons, status;
    logic [31:0] step_budget, epoch;
    logic [63:0] dot_count, retirement_count, completed_dot;
    logic busy, done, request_valid, write_enable, bus_commit, fault;
    logic [15:0] address;
    logic [7:0] write_data, read_data;
    logic [4:0] irq_ack;
    n2m_cpu_pkg::access_kind_t access_kind;
    n2m_interfaces_pkg::retirement_t retirement;
    logic pending_wake, wake_request;
    integer wakes, checks, cycles, trace;
    logic [63:0] frozen_dot, frozen_retire;
    logic [31:0] frozen_epoch;
    bit asleep_check, release_pause;
    n2m_timebase u_timebase (.*);
    n2m_uart_core_control u_control (.*);
    // Original two-byte STOP followed by NOPs, through a public read responder.
    // No ROM/presence acceptance is claimed by this focused control fixture.
    assign read_data = address == 16'h0100 ? 8'h10 : 8'h00;
    assign wake_request = pending_wake && !paused && cpu_stopped;
    n2m_cpu u_cpu (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .profile_id(8'd1),.epoch(epoch),.dot_before(dot_count),.ie(8'd0),.iflags(5'd0),.buttons(buttons),
        .read_data(read_data),.response_valid(1'b1),.joyp_selected_active(1'b0),.wake_request(wake_request),
        .request_valid(request_valid),.address(address),.write_data(write_data),.write_enable(write_enable),
        .access_kind(access_kind),.bus_commit(bus_commit),.irq_ack(irq_ack),.halted(),.stopped(cpu_stopped),
        .locked(),.initialized(core_initialized),.fault(fault),.ime_observe(),.ime_delay_observe(),
        .stop_execute(),.divider_reset_request(),.instruction_complete(instruction_complete),
        .retirement_valid(retirement_valid),.retirement(retirement),.address_effect(),
        .address_effect_resolved(),.address_effect_sample(),.address_effect_phase()
    );
    always #5 clk_sys = !clk_sys;
    // Explicit queued-wake boundary: only a later RUN may deliver the event.
    // Its analog restart delay and JOYP detector are separate owners.
    always @(posedge clk_sys) begin
        if(wake_request) begin pending_wake <= 0;wakes = wakes+1;end
        #1;
        if(asleep_check) begin
            if(!paused || !pause_request || gb_tick)$fatal(1,"UART_STOP_STEP_PAUSED");
            if(!cpu_stopped || dot_count!==frozen_dot || retirement_count!==frozen_retire || epoch!==frozen_epoch)
                $fatal(1,"UART_STOP_STEP_FROZEN");
            if(wakes!=0 || bus_commit || instruction_complete || retirement_valid || core_reset)
                $fatal(1,"UART_STOP_STEP_EFFECT");
        end
        if(!reset_sys && fault)$fatal(1,"UART_STOP_STEP_CPU_FAULT");
    end
    task automatic issue(input logic [7:0] selected_command, input logic [7:0] expected_status);
        @(negedge clk_sys);command=selected_command;start=1;
        @(negedge clk_sys);start=0;cycles=0;
        while(!done && cycles<2000)begin @(negedge clk_sys);cycles=cycles+1;end
        if(!done || status!==expected_status)$fatal(1,"UART_STOP_STEP_RESULT expected=%0d actual=%0d cycles=%0d",expected_status,status,cycles);
        if(asleep_check && cycles!=0)$fatal(1,"UART_STOP_STEP_NOT_IMMEDIATE cycles=%0d",cycles);
        @(negedge clk_sys);repeat(30)@(negedge clk_sys);
    endtask
    initial begin
        integer scenario;
        clk_sys=0;reset_sys=1;start=0;command=0;input_buttons=0;step_budget=70224;
        pending_wake=0;wakes=0;checks=0;cycles=0;asleep_check=0;
        frozen_dot=0;frozen_retire=0;frozen_epoch=0;
        release_pause=$test$plusargs("release_pause");
        trace=$fopen("stopped-step.csv","w");if(!trace)$fatal(1,"UART_STOP_STEP_TRACE");
        $fdisplay(trace,"case,budget,input,pending,dots,retirements,status");
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,reset_sys,start,command,step_budget,input_buttons,buttons,gb_tick,paused,
            pause_request,core_reset,core_initialized,cpu_stopped,instruction_complete,retirement_valid,
            dot_count,retirement_count,epoch,status,done,pending_wake,wake_request,wakes,bus_commit,checks);
        repeat(5)@(negedge clk_sys);reset_sys=0;
        issue(3,0);issue(6,0);
        if(!cpu_stopped || !paused || retirement_count!=1)$fatal(1,"UART_STOP_STEP_ENTRY");
        frozen_dot=dot_count;frozen_retire=retirement_count;frozen_epoch=epoch;
        for(scenario=0;scenario<4;scenario=scenario+1)begin
            input_buttons=scenario<2 ? 8'ha5 : 8'hff;issue(11,0);
            pending_wake=scenario[1];step_budget=scenario[0] ? 70224 : 1;
            asleep_check=1;
            if(release_pause)force u_control.pause_request=0;
            issue(6,8);
            if(buttons!==input_buttons || pending_wake!==scenario[1])$fatal(1,"UART_STOP_STEP_INPUT_WAKE");
            $fdisplay(trace,"%0d,%0d,%02h,%0d,%0d,%0d,%0d",scenario,step_budget,buttons,pending_wake,dot_count,retirement_count,status);
            asleep_check=0;checks=checks+1;
        end
        issue(4,0);
        if(cpu_stopped || pending_wake || wakes!=1)$fatal(1,"UART_STOP_STEP_WAKE_PRESERVED");
        $fclose(trace);$display("PASS UART stopped STEP immediate cases=4 zero_dots input_preserved queued_wake=1");$finish;
    end
    initial begin #1000000;$fatal(1,"UART_STOP_STEP_WATCHDOG");end
endmodule
`default_nettype wire

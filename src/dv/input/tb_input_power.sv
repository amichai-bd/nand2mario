`timescale 1ns/1ps
`default_nettype none
module tb_input_power;
    logic clk_sys, reset_sys, gb_tick, paused, pause_request, core_reset;
    logic start, core_initialized, instruction_complete, retirement_valid, cpu_stopped, cpu_halted;
    logic [7:0] command, status, host_buttons, physical_buttons, effective_buttons;
    logic [31:0] epoch;
    logic [63:0] dot_count, retirement_count, completed_dot;
    logic busy, done, physical_commit;
    n2m_input_pkg::input_write_t input_write, accepted_input;
    n2m_input_pkg::input_update_t effective_update;
    logic request_valid, write_enable, bus_commit, fault, selected_active, request_event;
    logic [15:0] address;
    logic [7:0] write_data, read_data, joyp_data;
    logic [4:0] irq_ack, if_stored, if_observe;
    n2m_cpu_pkg::access_kind_t access_kind;
    n2m_interfaces_pkg::retirement_t retirement;
    logic wake_request, stop_case, observed_successor;
    logic [63:0] frozen_dot, frozen_retire;
    integer source_case, power_case, checks, cycles, trace;
    n2m_timebase u_timebase (.*);
    n2m_uart_core_control u_control (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.start(start),.command(command),.step_budget(32'd70224),
        .input_write(input_write),.gb_tick(gb_tick),.paused(paused),.core_initialized(core_initialized),
        .instruction_complete(instruction_complete),.retirement_valid(retirement_valid),.cpu_stopped(cpu_stopped),
        .pause_request(pause_request),.core_reset(core_reset),.accepted_input(accepted_input),.epoch(epoch),
        .dot_count(dot_count),.retirement_count(retirement_count),.busy(busy),.done(done),.status(status),.completed_dot(completed_dot),.run_dots_result()
    );
    n2m_input dut (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .host_write(accepted_input),.physical_commit(physical_commit),.physical_buttons(physical_buttons),
        .host_buttons(host_buttons),.physical_observe(),.source_observe(),
        .effective_buttons(effective_buttons),.effective_update(effective_update)
    );
    n2m_joypad u_joypad (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .input_commit(effective_update.valid),.input_buttons(effective_update.buttons),
        .io_commit(bus_commit && write_enable && address==16'hff00),.io_write(write_enable),
        .io_address(16'hff00),.io_wdata(write_data),.io_selected(),.io_rdata(joyp_data),
        .buttons_observe(),.selected_active(selected_active),.request_event(request_event)
    );
    n2m_interrupts u_interrupts (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .io_commit(1'b0),.io_write(1'b0),.io_address(16'hff0f),.io_wdata(8'd0),
        .source_level(5'd0),.source_event({request_event,4'd0}),.irq_ack(irq_ack),
        .io_selected(),.io_rdata(),.ie_stored(),.if_stored(if_stored),.ie_observe(),.if_observe(if_observe)
    );
    assign wake_request=cpu_stopped && selected_active && !paused;
    always_comb begin
        case(address)
            16'h0100:read_data=8'h3e;
            16'h0101:read_data=8'h20;
            16'h0102:read_data=8'he0;
            16'h0103:read_data=8'h00;
            16'h0104:read_data=stop_case ? 8'h10 : 8'h76;
            default:read_data=8'h00;
        endcase
    end
    n2m_cpu u_cpu (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .profile_id(8'd1),.epoch(epoch),.dot_before(dot_count),.ie(8'h10),.iflags(if_observe),
        .buttons(effective_buttons),.read_data(read_data),.response_valid(1'b1),
        .joyp_selected_active(selected_active),.wake_request(wake_request),.request_valid(request_valid),
        .address(address),.write_data(write_data),.write_enable(write_enable),.access_kind(access_kind),
        .bus_commit(bus_commit),.irq_ack(irq_ack),.halted(cpu_halted),.stopped(cpu_stopped),.locked(),
        .initialized(core_initialized),.fault(fault),.ime_observe(),.ime_delay_observe(),.stop_execute(),
        .divider_reset_request(),.instruction_complete(instruction_complete),.retirement_valid(retirement_valid),
        .retirement(retirement),.address_effect(),.address_effect_resolved(),.address_effect_sample(),.address_effect_phase()
    );
    always #5 clk_sys=!clk_sys;
    always @(posedge clk_sys) begin
        #1;
        if(!reset_sys && fault)$fatal(1,"INPUT_POWER_CPU_FAULT");
        if(retirement_valid && retirement.pc_before==(stop_case ? 16'h0106 : 16'h0105)) begin
            if(retirement.buttons!==8'h01 || retirement.opcode!==24'd0 || retirement.iflags!==8'h10)
                $fatal(1,"INPUT_POWER_RECORD buttons=%02h opcode=%06h IF=%02h",retirement.buttons,retirement.opcode,retirement.iflags);
            observed_successor=1;
        end
    end
    task automatic issue(input logic [7:0] selected_command);
        @(negedge clk_sys);command=selected_command;start=1;
        @(negedge clk_sys);start=0;cycles=0;
        while(!done && cycles<2000)begin @(negedge clk_sys);cycles=cycles+1;end
        if(!done || status!=0)$fatal(1,"INPUT_POWER_COMMAND command=%0d status=%0d",selected_command,status);
        @(negedge clk_sys);repeat(30)@(negedge clk_sys);
    endtask
    task automatic host_update(input logic source_write, input logic [7:0] value);
        input_write='{valid:1'b1,source_write:source_write,value:value};issue(11);input_write='0;
    endtask
    task automatic physical_update(input logic [7:0] value);
        @(negedge clk_sys);while(gb_tick)@(negedge clk_sys);
        physical_buttons=value;physical_commit=1;@(negedge clk_sys);physical_commit=0;
        repeat(3)@(negedge clk_sys);
    endtask
    initial begin
        clk_sys=0;reset_sys=1;start=0;command=0;input_write='0;physical_commit=0;physical_buttons=0;
        stop_case=0;observed_successor=0;checks=0;cycles=0;
        trace=$fopen("power.csv","w");
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,paused,command,start,accepted_input,
            physical_commit,physical_buttons,host_buttons,effective_buttons,effective_update,selected_active,
            request_event,if_stored,if_observe,cpu_halted,cpu_stopped,wake_request,address,bus_commit,
            dot_count,retirement_count,retirement_valid,retirement,observed_successor);
        for(power_case=0;power_case<2;power_case=power_case+1)
        for(source_case=0;source_case<2;source_case=source_case+1)begin
            reset_sys=1;stop_case=power_case[0];physical_buttons=0;observed_successor=0;
            repeat(5)@(negedge clk_sys);reset_sys=0;
            issue(3);issue(6);issue(6);issue(6);
            if(!paused || retirement_count!=3 || (stop_case ? !cpu_stopped : !cpu_halted))
                $fatal(1,"INPUT_POWER_ENTRY stop=%0d halted=%0d stopped=%0d retire=%0d",stop_case,cpu_halted,cpu_stopped,retirement_count);
            frozen_dot=dot_count;frozen_retire=retirement_count;
            if(source_case)begin host_update(1,1);host_update(0,8'hff);end
            else physical_update(8'hff);
            if(effective_buttons!=0 || selected_active || if_stored!=0 || dot_count!=frozen_dot)
                $fatal(1,"INPUT_POWER_ISOLATION");
            if(source_case)physical_update(1);else host_update(0,1);
            if(effective_buttons!=1 || !selected_active || if_stored!=16 || dot_count!=frozen_dot || retirement_count!=frozen_retire)
                $fatal(1,"INPUT_POWER_PAUSED_EVENT");
            issue(4);cycles=0;
            while(!observed_successor && cycles<2000)begin @(negedge clk_sys);cycles=cycles+1;end
            if(!observed_successor || cpu_stopped || cpu_halted)$fatal(1,"INPUT_POWER_WAKE");
            $fdisplay(trace,"%0d,%0d,%0d,%0d,%02h,%02h",power_case,source_case,frozen_dot,dot_count,effective_buttons,if_stored);
            issue(5);checks=checks+1;
        end
        $fclose(trace);$display("PASS INPUT_POWER cases=4 actual_HALT_STOP effective_records");$finish;
    end
    initial begin #2000000;$fatal(1,"INPUT_POWER_TIMEOUT");end
endmodule

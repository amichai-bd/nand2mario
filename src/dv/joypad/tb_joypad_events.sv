`timescale 1ns/1ps
`default_nettype none
module tb_joypad_events;
    logic clk_sys, reset_sys, core_reset, gb_tick;
    logic input_commit, io_commit, io_write, io_selected, selected_active, request_event;
    logic [7:0] input_buttons, io_wdata, io_rdata, buttons_observe;
    logic [15:0] io_address;
    logic if_commit, if_write;
    logic [7:0] if_data;
    logic [4:0] irq_ack, if_stored, if_observe;
    logic [4:0] expected_flags;
    logic expected_event, pending_clear, pending_ack;
    logic host_pause, cpu_halted, cpu_stopped;
    integer checks, events, trace, item, policy, placement;
    bit lost, duplicate;
    n2m_joypad dut (.*);
    n2m_interrupts u_interrupts (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .io_commit(if_commit), .io_write(if_write),
        .io_address(16'hff0f), .io_wdata(if_data), .source_level(5'd0),
        .source_event({request_event,4'd0}), .irq_ack(irq_ack),
        .io_selected(), .io_rdata(), .ie_stored(), .if_stored(if_stored),
        .ie_observe(), .if_observe(if_observe)
    );
    // Literal event expectation is supplied by each stimulus row. IF is checked
    // independently from the previous event and the previously accepted A command.
    task automatic step(input logic fall);
        if (reset_sys || core_reset) begin
            expected_flags=0; expected_event=0; pending_clear=0; pending_ack=0;
        end else begin
            if (expected_event) expected_flags=expected_flags | 5'h10;
            if (pending_clear || pending_ack) expected_flags=0;
            pending_clear=gb_tick && if_commit && if_write;
            pending_ack=gb_tick && irq_ack[4];
            expected_event=fall;
        end
        clk_sys=0; #5 clk_sys=1; #2;
        if (request_event!==expected_event)
            $fatal(1,"JOYP_EVENT case=%0d expected=%0d actual=%0d",checks,expected_event,request_event);
        if (if_stored!==expected_flags)
            $fatal(1,"JOYP_IF case=%0d expected=%02h actual=%02h",checks,expected_flags,if_stored);
        $fdisplay(trace,"%0d,%0d,%02h,%0d,%02h,%0d,%0d,%02h,%02h",checks,gb_tick,input_buttons,io_commit,io_wdata,fall,request_event,expected_flags,if_stored);
        checks=checks+1; if(fall) events=events+1;
        #3 clk_sys=0;
    endtask
    task automatic update(input logic [7:0] buttons, input logic fall);
        input_commit=1; input_buttons=buttons; step(fall); input_commit=0;
    endtask
    task automatic select_row(input logic [7:0] value, input logic fall);
        gb_tick=1; io_commit=1; io_write=1; io_wdata=value; step(fall);
        gb_tick=0; io_commit=0; io_write=0; step(0);
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0;
        input_commit=0; input_buttons=0; io_commit=0; io_write=0;
        io_address=16'hff00; io_wdata=0; if_commit=0; if_write=0; if_data=0;
        irq_ack=0; expected_flags=0; expected_event=0; pending_clear=0; pending_ack=0;
        host_pause=0; cpu_halted=0; cpu_stopped=0; checks=0; events=0;
        lost=$test$plusargs("lost"); duplicate=$test$plusargs("duplicate");
        trace=$fopen("events.csv","w"); if(!trace) $fatal(1,"JOYP_TRACE");
        $fdisplay(trace,"case,tick,buttons,select_commit,select_data,expected_event,event,expected_if,if");
        $dumpfile("waves/joypad-events.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,input_commit,input_buttons,
            io_commit,io_write,io_address,io_wdata,io_selected,io_rdata,buttons_observe,
            selected_active,request_event,if_commit,if_write,if_data,irq_ack,
            if_stored,if_observe,host_pause,cpu_halted,cpu_stopped);
        step(0); reset_sys=0; step(0);
        // Each button, held value, release and repress in its selected row.
        for(item=0;item<8;item=item+1) begin
            select_row(item<4 ? 8'h20 : 8'h10,0);
            if(lost && item==0) force dut.request_event=1'b0;
            update(8'(1<<item),1);
            if(duplicate && item==0) force dut.request_event=1'b1;
            update(8'(1<<item),0); update(0,0);
            update(8'(1<<item),1); update(0,0); step(0);
        end
        // Both rows: a shared held line is not a new fall; different lines are.
        select_row(0,0); update(8'h01,1); update(8'h11,0);
        update(8'h12,1); update(8'h24,1); update(8'h48,1); update(8'h81,1);
        update(8'hff,1); update(0,0); step(0);
        select_row(8'h30,0); update(8'h81,0); select_row(8'h20,1);
        select_row(8'h10,1); select_row(8'h30,0); update(0,0);
        // Atomic select/input: compare old lines to final combined state.
        input_commit=1; input_buttons=8'h01; select_row(8'h20,1); input_commit=0;
        input_commit=1; input_buttons=8'h10; select_row(8'h10,0); input_commit=0;
        update(0,0);
        // Event before A, at A, or at B versus IF clear and acknowledgment.
        // At-B event survives at C even when the preceding event lost to B clear.
        for(policy=0;policy<3;policy=policy+1) begin
            for(placement=0;placement<3;placement=placement+1) begin
                update(0,0); select_row(0,0);
                if(placement==0) update(1,1); else step(0);
                gb_tick=1; if_commit=policy==1; if_write=policy==1;
                irq_ack=policy==2 ? 5'h10 : 5'd0;
                input_commit=placement==1; input_buttons=2; step(placement==1);
                gb_tick=0; if_commit=0; if_write=0; irq_ack=0;
                input_commit=placement==2; input_buttons=4; step(placement==2);
                input_commit=0; step(0); step(0);
            end
        end
        update(0,0);
        gb_tick=1; if_commit=1; if_write=1; update(1,1);
        gb_tick=0; if_commit=0; if_write=0; update(2,1);
        step(0); step(0);
        // No mode input gates this owner. These labels identify withheld-dot
        // environments, not execution of CPU or oscillator circuitry.
        update(0,0); host_pause=1; update(1,1); update(2,1); update(0,0);
        cpu_halted=1; update(4,1); update(0,0); cpu_halted=0;
        cpu_stopped=1; update(8,1); update(0,0); cpu_stopped=0; host_pause=0;
        for(item=0;item<2;item=item+1) begin
            update(1,1);
            if(item==0) core_reset=1; else reset_sys=1;
            #1; if(request_event!==0 || selected_active!==0) $fatal(1,"JOYP_RESET_EVENT");
            input_commit=1; input_buttons=255; gb_tick=1; io_commit=1; io_write=1; io_wdata=0;
            step(0); input_commit=0; gb_tick=0; io_commit=0; io_write=0;
            core_reset=0; reset_sys=0; step(0); select_row(0,0);
        end
        $fclose(trace); $display("PASS JOYP events checks=%0d events=%0d",checks,events); $finish;
    end
    initial begin #100000; $fatal(1,"JOYP_EVENT_TIMEOUT"); end
endmodule

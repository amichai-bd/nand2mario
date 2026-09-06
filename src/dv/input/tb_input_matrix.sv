`timescale 1ns/1ps
`default_nettype none
module tb_input_matrix;
    logic clk_sys, reset_sys, core_reset, gb_tick, physical_commit;
    logic [7:0] physical_buttons, host_buttons, physical_observe, source_observe, effective_buttons;
    n2m_input_pkg::input_write_t host_write;
    n2m_input_pkg::input_update_t effective_update;
    logic io_commit, io_write, io_selected, selected_active, request_event;
    logic [7:0] io_wdata, io_rdata, buttons_observe;
    logic [4:0] if_stored;
    integer source_index, row_index, mask_index, checks, cases, trace;
    logic [7:0] expected_host, expected_physical, expected_effective;
    logic [1:0] expected_select;
    logic expected_source, previous_event;
    logic [3:0] previous_lines;
    logic [4:0] expected_if;
    bit data_fault, source_fault, event_fault, boundary_fault;
    n2m_input dut (.*);
    n2m_joypad u_joypad (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .input_commit(effective_update.valid), .input_buttons(effective_update.buttons),
        .io_commit(io_commit), .io_write(io_write), .io_address(16'hff00), .io_wdata(io_wdata),
        .io_selected(io_selected), .io_rdata(io_rdata), .buttons_observe(buttons_observe),
        .selected_active(selected_active), .request_event(request_event)
    );
    n2m_interrupts u_interrupts (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .io_commit(1'b0), .io_write(1'b0), .io_address(16'hff0f), .io_wdata(8'd0),
        .source_level(5'd0), .source_event({request_event,4'd0}), .irq_ack(5'd0),
        .io_selected(), .io_rdata(), .ie_stored(), .if_stored(if_stored), .ie_observe(), .if_observe()
    );
    function automatic logic [3:0] lines(input logic [7:0] mask, input logic [1:0] row);
        logic [3:0] result;
        result = 4'hf;
        for (integer lane=0; lane<4; lane=lane+1) begin
            if (!row[0] && mask[lane]) result[lane]=0;
            if (!row[1] && mask[lane+4]) result[lane]=0;
        end
        return result;
    endfunction
    task automatic step;
        logic [3:0] current_lines;
        logic fall;
        if (reset_sys || core_reset) begin
            expected_host=0; expected_source=0; expected_select=3;
            if (reset_sys) expected_physical=0;
            else if(physical_commit) expected_physical=physical_buttons;
            expected_if=0; previous_event=0; previous_lines=15;
        end else begin
            if (previous_event) expected_if=5'h10;
            if (host_write.valid) begin
                if (host_write.source_write) expected_source=host_write.value[0];
                else expected_host=host_write.value;
            end
            if (physical_commit) expected_physical=physical_buttons;
            if (io_commit) expected_select=io_wdata[5:4];
        end
        expected_effective=expected_source ? expected_physical : expected_host;
        current_lines=lines(expected_effective,expected_select);
        fall=!(reset_sys || core_reset) && |(previous_lines & ~current_lines);
        clk_sys=0; #5; clk_sys=1; #2;
        if ({host_buttons,physical_observe,source_observe,effective_buttons} !==
            {expected_host,expected_physical,7'd0,expected_source,expected_effective})
            $fatal(1,"INPUT_MATRIX_STATE case=%0d check=%0d",cases,checks);
        if (io_rdata !== {2'b11,expected_select,current_lines} || buttons_observe !== expected_effective)
            $fatal(1,"INPUT_MATRIX_JOYP case=%0d check=%0d",cases,checks);
        if (request_event !== fall || selected_active !== (current_lines != 15))
            $fatal(1,"INPUT_MATRIX_EVENT case=%0d check=%0d",cases,checks);
        if (if_stored !== expected_if) $fatal(1,"INPUT_MATRIX_IF case=%0d check=%0d",cases,checks);
        $fdisplay(trace,"%0d,%0d,%02h,%02h,%0d,%02h,%02h,%0d,%02h",cases,checks,
            host_buttons,physical_observe,source_observe,effective_buttons,io_rdata,request_event,if_stored);
        previous_lines=current_lines; previous_event=fall; checks=checks+1;
        #3; clk_sys=0;
    endtask
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,physical_commit,physical_buttons,
            host_write,host_buttons,physical_observe,source_observe,effective_buttons,effective_update,
            io_commit,io_wdata,io_rdata,buttons_observe,selected_active,request_event,if_stored);
        trace=$fopen("input.csv","w");
        data_fault=$test$plusargs("data_fault"); source_fault=$test$plusargs("source_fault");
        event_fault=$test$plusargs("event_fault"); boundary_fault=$test$plusargs("boundary_fault");
        clk_sys=0;reset_sys=1;core_reset=0;gb_tick=0;physical_commit=0;physical_buttons=0;
        host_write='0;io_commit=0;io_write=1;io_wdata=0;checks=0;cases=0;
        expected_physical=0;
        for(source_index=0;source_index<2;source_index=source_index+1)
        for(row_index=0;row_index<4;row_index=row_index+1)
        for(mask_index=0;mask_index<256;mask_index=mask_index+1) begin
            reset_sys=1; host_write='0;physical_commit=0;io_commit=0;gb_tick=0;step();
            reset_sys=0;gb_tick=1;io_commit=1;io_wdata=8'(row_index*16);step();
            gb_tick=0;io_commit=0;
            host_write='{valid:1'b1,source_write:1'b1,value:8'(source_index)};step();
            host_write='{valid:1'b1,source_write:1'b0,value:source_index ? ~8'(mask_index) : 8'(mask_index)};
            physical_commit=1;physical_buttons=source_index ? 8'(mask_index) : ~8'(mask_index);
            if(cases==1) begin
                if(data_fault) force dut.effective_buttons=8'h00;
                if(source_fault) force dut.host_q.physical_source=1'b1;
                if(event_fault) force u_joypad.request_event=1'b0;
                if(boundary_fault) gb_tick=1;
            end
            step();host_write='0;physical_commit=0;step();
            cases=cases+1;
        end
        $display("PASS INPUT_MATRIX cases=2048");$fclose(trace);$finish;
    end
    initial begin #1000000;$fatal(1,"INPUT_MATRIX_TIMEOUT");end
endmodule

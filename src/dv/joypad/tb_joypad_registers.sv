`timescale 1ns/1ps
`default_nettype none
module tb_joypad_registers;
    logic clk_sys, reset_sys, core_reset, gb_tick;
    logic input_commit, io_commit, io_write, io_selected, selected_active;
    logic [7:0] input_buttons, io_wdata, io_rdata, buttons_observe;
    logic [15:0] io_address;
    logic [7:0] expected_buttons, expected_data;
    logic [1:0] expected_select;
    integer item, case_number, checks, trace;
    bit corrupt, boundary_fault;
    n2m_joypad dut (.request_event(), .*);
    task automatic check_state;
        case(expected_select)
            0: expected_data=8'hc0 | (8'h0f & ~(expected_buttons | (expected_buttons >> 4)));
            1: expected_data=8'hd0 | (8'h0f & ~(expected_buttons >> 4));
            2: expected_data=8'he0 | (8'h0f & ~expected_buttons);
            3: expected_data=8'hff;
        endcase
        if(io_selected!==(io_address==16'hff00) ||
            io_rdata!==(io_address==16'hff00 ? expected_data : 8'd0) ||
            buttons_observe!==expected_buttons || selected_active!==(expected_data[3:0]!=4'hf))
            $fatal(1,"JOY_REG_READ case=%0d expected=%02h actual=%02h buttons=%02h",case_number,expected_data,io_rdata,buttons_observe);
        $fdisplay(trace,"%0d,%02h,%0d,%04h,%02h,%02h",case_number,expected_buttons,expected_select,io_address,expected_data,io_rdata);
        checks=checks+1;
    endtask
    task automatic edge_cycle;
        clk_sys=0; #5 clk_sys=1; #2; check_state(); #3 clk_sys=0;
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0;
        input_commit=0; input_buttons=0; io_commit=0; io_write=0;
        io_address=16'hff00; io_wdata=0; expected_buttons=0; expected_select=3;
        case_number=0; checks=0;
        corrupt=$test$plusargs("corrupt"); boundary_fault=$test$plusargs("boundary_fault");
        trace=$fopen("registers.csv","w"); if(!trace) $fatal(1,"JOY_REG_TRACE");
        $fdisplay(trace,"case,buttons,select,address,expected,actual");
        $dumpfile("waves/joypad-registers.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,input_commit,input_buttons,
            io_commit,io_write,io_address,io_wdata,io_selected,io_rdata,buttons_observe,selected_active);
        edge_cycle(); reset_sys=0; edge_cycle();
        input_commit=1; input_buttons=8'ha5; expected_buttons=8'ha5; edge_cycle(); input_commit=0;
        if(boundary_fault) begin
            io_commit=1; io_write=0; edge_cycle(); $fatal(1,"JOY_REG_BOUNDARY_NOT_DETECTED");
        end
        for(item=0;item<256;item=item+1) begin
            case_number=item; io_commit=1; io_write=1; gb_tick=1; io_wdata=8'(item);
            expected_select=2'(item >> 4);
            if(corrupt && item==0) force dut.io_commit=1'b0;
            edge_cycle(); io_commit=0; io_write=0; gb_tick=0; edge_cycle();
        end
        // Atomic replacement while the emulated clock is held, preserving all buttons.
        io_commit=1; io_write=1; gb_tick=1; io_wdata=0; expected_select=0; edge_cycle();
        io_commit=0; io_write=0; gb_tick=0;
        for(item=0;item<256;item=item+1) begin
            case_number=256+item; input_commit=1; input_buttons=8'(item); expected_buttons=8'(item);
            edge_cycle(); input_commit=0; repeat(2) edge_cycle();
        end
        // Prepared/uncommitted writes and committed reads do not alter state.
        io_wdata=8'h30; io_write=1; repeat(4) edge_cycle();
        io_address=16'hff01; repeat(4) edge_cycle(); io_address=16'hff00;
        io_write=0; io_commit=1; gb_tick=1; edge_cycle(); io_commit=0; gb_tick=0;
        // Both independent state changes are accepted together; reset wins over both.
        input_commit=1; input_buttons=8'h81; io_commit=1; io_write=1; gb_tick=1; io_wdata=8'h20;
        expected_buttons=8'h81; expected_select=2; edge_cycle();
        input_commit=0; io_commit=0; io_write=0; gb_tick=0; edge_cycle();
        for(item=0;item<2;item=item+1) begin
            case_number=512+item; input_commit=1; input_buttons=8'hff;
            io_commit=1; io_write=1; gb_tick=1; io_wdata=0;
            if(item==0) core_reset=1; else reset_sys=1;
            expected_buttons=0; expected_select=3; #1; check_state(); edge_cycle();
            input_commit=0; io_commit=0; io_write=0; gb_tick=0; core_reset=0; reset_sys=0; edge_cycle();
        end
        $fclose(trace); $display("PASS JOYP registers writes=256 inputs=256 resets=2"); $finish;
    end
    initial begin
        #100000;
        $fatal(1,"JOY_REG_TIMEOUT");
    end
endmodule

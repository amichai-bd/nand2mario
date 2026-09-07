`timescale 1ns/1ps
`default_nettype none

// A DUT-side broken read line proves that the unchanged Python checker fails.
module joypad_fault (
    input logic clk_sys, reset_sys, core_reset, gb_tick,
    input logic input_commit,
    input logic [7:0] input_buttons,
    input logic io_commit, io_write,
    input logic [15:0] io_address,
    input logic [7:0] io_wdata,
    output wire io_selected,
    output wire [7:0] io_rdata, buttons_observe,
    output wire selected_active, request_event
);
    wire [7:0] correct_read;
    n2m_joypad dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .input_commit(input_commit), .input_buttons(input_buttons),
        .io_commit(io_commit), .io_write(io_write), .io_address(io_address), .io_wdata(io_wdata),
        .io_selected(io_selected), .io_rdata(correct_read), .buttons_observe(buttons_observe),
        .selected_active(selected_active), .request_event(request_event)
    );
    assign io_rdata = correct_read | 8'h01;
endmodule

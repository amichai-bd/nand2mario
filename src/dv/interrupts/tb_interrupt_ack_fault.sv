`timescale 1ns/1ps
`default_nettype none
module tb_interrupt_ack_fault;
    logic clk_sys, reset_sys, gb_tick;
    logic [4:0] irq_ack;
    n2m_interrupts dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(1'b0), .gb_tick(gb_tick),
        .io_commit(1'b0), .io_write(1'b0), .io_address(16'h0000), .io_wdata(8'h00),
        .source_event(5'd0), .source_level(5'h00), .irq_ack(irq_ack), .io_selected(), .io_rdata(),
        .ie_stored(), .if_stored(), .ie_observe(), .if_observe()
    );
    initial begin
        $dumpfile("waves.vcd"); $dumpvars(0,clk_sys,reset_sys,gb_tick,irq_ack);
        clk_sys = 0; reset_sys = 1; gb_tick = 0; irq_ack = 0;
        #5; clk_sys = 1; #5; clk_sys = 0; reset_sys = 0;
        // An actual invalid public acknowledgement at A must hit its local
        // named assertion. No expected-value mutation or oracle is involved.
        gb_tick = 1; irq_ack = 5'h03;
        #5; clk_sys = 1; #5;
        $fatal(1,"INTERRUPT_ACK_FAULT_UNDETECTED");
    end
endmodule

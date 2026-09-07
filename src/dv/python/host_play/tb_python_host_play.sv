`timescale 1ns/1ps
`default_nettype none
// Public composed boundary; Python owns serial stimulus and image verdicts.
module tb_python_host_play;
    logic clk_sys, reset_sys, uart_rx, uart_tx;
    logic gb_tick, paused, core_reset, retirement_valid, bus_commit, write_enable;
    logic [31:0] epoch;
    logic [63:0] dot_count;
    n2m_interfaces_pkg::retirement_t retirement;
    logic [15:0] address;
    logic [7:0] write_data, read_data;
    logic [4:0] irq_ack;
    logic source_valid, source_start, source_abort, source_display_eligible, fault;
    logic [1:0] source_shade;
    logic [7:0] source_x, source_y;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;

    n2m_smoke_system #(.HOST_PLAY(1)) dut (.*);
    always #20 clk_sys = !clk_sys;
    initial begin
        clk_sys = 0;
        reset_sys = 1;
        uart_rx = 1;
        fork
            begin if ($test$plusargs("frame_fault")) begin
                wait(dut.frame_read);
                force dut.frame_data = 8'hff;
            end end
            begin if ($test$plusargs("missing_frame")) begin
                force dut.g_play.u_snapshot.observe_complete = 1'b0;
            end end
            begin if ($test$plusargs("input_fault")) begin
                wait(dut.effective_update.valid && dut.effective_update.buttons == 1);
                force dut.g_play.u_joypad.input_buttons = 8'd2;
            end end
            begin if ($test$plusargs("release_fault")) begin
                wait(dut.effective_update.valid && dut.effective_update.buttons == 1);
                wait(!dut.effective_update.valid);
                wait(dut.effective_update.valid && dut.effective_update.buttons == 0);
                force dut.g_play.u_joypad.input_commit = 1'b0;
            end end
        join_none
    end
endmodule

`timescale 1ns/1ps
`default_nettype none
// Passive owner-boundary samples. Python owns stimulus and all expectations.
module tb_python_v05;
    logic clk_sys, clk_pix, reset_sys, reset_pix, uart_rx, uart_tx;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    logic [63:0] display_sequence, dot_count;
    logic [31:0] display_epoch, epoch;
    logic gb_tick, paused, core_reset, retirement_valid, bus_commit, write_enable;
    n2m_interfaces_pkg::retirement_t retirement;
    logic [15:0] address;
    logic [7:0] write_data, read_data;
    logic [4:0] irq_ack;
    logic source_valid, source_start, source_abort, source_display_eligible, fault;
    logic [1:0] source_shade;
    logic [7:0] source_x, source_y;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    logic record_event, pixel_event, input_event, write_event;
    n2m_interfaces_pkg::retirement_t record_sample;
    logic [116:0] pixel_sample;
    logic [103:0] input_sample;
    logic [87:0] write_sample;

    n2m_v05_system #(.UART_BAUD(3125000)) dut (.*);
    always #20 clk_sys = !clk_sys;
    always #19.841 clk_pix = !clk_pix;

    always @(posedge clk_sys) begin
        if (!reset_sys && bus_commit && write_enable) begin
            write_sample <= {64'(dot_count + 1), address, write_data};
            write_event <= !write_event;
        end
        // Effective update is consumed by JOYP on this edge, off gb_tick.
        if (!reset_sys && !core_reset && dut.effective_update.valid) begin
            input_sample <= {epoch, dot_count, dut.effective_update.buttons};
            input_event <= !input_event;
        end
        #1;
        if (!reset_sys && retirement_valid) begin
            record_sample <= retirement;
            record_event <= !record_event;
        end
        if (!reset_sys && source_valid) begin
            pixel_sample <= {source_dot, source_epoch, source_x, source_y,
                             source_shade, source_start, source_abort, source_display_eligible};
            pixel_event <= !pixel_event;
        end
    end

    initial begin
        clk_sys = 0;
        clk_pix = 0;
        reset_sys = 1;
        reset_pix = 1;
        uart_rx = 1;
        record_event = 0;
        pixel_event = 0;
        input_event = 0;
        write_event = 0;
        if ($test$plusargs("pixel_fault")) begin
            wait(source_display_eligible && source_x == 0 && source_y == 0);
            force dut.source_shade = 2'd0;
        end
    end
endmodule

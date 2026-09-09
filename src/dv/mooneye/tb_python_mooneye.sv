`timescale 1ns/1ps
`default_nettype none
// Clock, public observation latches and supported memory initialization only.
// All stimulus, expectations and verdicts belong to the Python test.
module tb_python_mooneye;
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
    logic bus_event, record_event, pixel_event;
    logic [88:0] bus_sample;
    logic [383:0] record_sample;
    logic [116:0] pixel_sample;

    n2m_smoke_system dut (.*);
    defparam dut.u_stores.rom.SIM_INIT_FILE = "preload-rom.mif";
    defparam dut.u_uart.u_commands.u_load.u_presence.u_presence.SIM_INIT_FILE = "preload-presence.mif";
    defparam dut.u_uart.u_commands.u_load.SIM_PRELOAD = 1;
    always #20 clk_sys = !clk_sys;

    // Bus commits describe the consumed pre-edge transaction. Retirement and
    // pixel outputs use the integration contract's settled 1 ns boundary.
    always @(posedge clk_sys) begin
        if (!reset_sys && bus_commit) begin
            bus_sample <= {64'(dot_count + 1), address, write_enable,
                           write_enable ? write_data : read_data};
            bus_event <= !bus_event;
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
        reset_sys = 1;
        uart_rx = 1;
        bus_event = 0;
        record_event = 0;
        pixel_event = 0;
        fork
            begin if ($test$plusargs("completion_fault")) begin
                wait(retirement_valid && retirement.pc_before == 16'h4a81);
                force dut.retirement.b = 8'h42;
                force dut.retirement.c = 8'h42;
                force dut.retirement.d = 8'h42;
                force dut.retirement.e = 8'h42;
                force dut.retirement.h = 8'h42;
                force dut.retirement.l = 8'h42;
            end end
            begin if ($test$plusargs("missing_completion")) begin
                // Replace the actual fetched instruction, not the completion checker.
                wait(address == 16'h4a81);
                force dut.read_data = 8'h76;
            end end
        join_none
    end
endmodule

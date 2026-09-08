`timescale 1ns/1ps
`default_nettype none
// Real board clocks and owners; Python drives only board pins and UART.
module tb_python_controls;
    logic clk_reference;
    logic clk_adc_reference;
    logic board_reset_n;
    logic [3:0] buttons_n;
    logic uart_rx;
    logic uart_tx;
    logic [9:0] leds;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n, paused, fault;
    logic [63:0] display_sequence;
    logic [31:0] display_epoch;
    logic corrupt;
    logic injection_done;
    initial begin
        clk_reference = 0;
        clk_adc_reference = 0;
        board_reset_n = 0;
        buttons_n = 4'hF;
        uart_rx = 1;
        corrupt = 0;
        injection_done = 0;
    end
    v05_controls_proof #(.UART_BAUD(3125000)) dut (.*);
    defparam dut.u_system.u_stores.rom.SIM_INIT_FILE = "preload-rom.mif";
    defparam dut.u_system.u_uart.u_commands.u_load.u_presence.u_presence.SIM_INIT_FILE = "preload-presence.mif";
    defparam dut.u_system.u_uart.u_commands.u_load.SIM_PRELOAD = 1;
    always #10 clk_reference = !clk_reference;
    always #50 clk_adc_reference = !clk_adc_reference;
    always @(posedge corrupt) begin
        // Actual consumer input corruption; expected masks stay unchanged.
        @(negedge dut.clk_sys);
        while (!dut.physical_commit) @(negedge dut.clk_sys);
        if (dut.reset_sys || dut.gb_tick || dut.input_source != 8'd1 || dut.physical_buttons != 8'h08)
            $fatal(1, "CONTROLS_SYSTEM_INJECTION_BOUNDARY");
        $display("CONTROLS_SYSTEM_INJECTION time=%0t original=08 injected=00 commit=1 source=1", $time);
        force dut.u_system.physical_buttons = 8'h00;
        @(posedge dut.clk_sys);
        @(negedge dut.clk_sys);
        release dut.u_system.physical_buttons;
        injection_done = 1;
    end
    initial begin
        #45000000;
        $fatal(1, "CONTROLS_SYSTEM_WATCHDOG");
    end
endmodule
`default_nettype wire

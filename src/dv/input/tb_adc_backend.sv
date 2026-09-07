`timescale 1ns/1ps
module tb_adc_backend;
    logic clk_sys;
    logic clk_board_reference;
    logic clk_reference;
    logic clk_adc;
    logic board_reset_n;
    logic global_reset;
    logic pll_reset;
    logic pll_locked;
    logic adc_ready;
    logic adc_reset;
    logic adc_domain_reset;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic fresh;
    logic fault;
    logic pending;
    logic [4:0] next_channel;
    logic [4:0] pending_channel;
    integer commands;
    integer replies;
    bit corrupt;
    n2m_reset_control u_reset (
        .clk_reference(clk_board_reference), .clk_sys(clk_sys), .clk_pix(clk_adc), .board_reset_n(board_reset_n), .pll_locked(pll_locked),
        .pll_areset(pll_reset), .ready(adc_ready), .reset_sys(adc_reset), .reset_pix(adc_domain_reset)
    );
    n2m_adc_backend u_adc (
        .clk_sys(clk_sys), .clk_adc_reference(clk_reference), .pll_areset(pll_reset), .reset_sys(adc_reset),
        .command_valid(command_valid), .command_channel(command_channel), .command_ready(command_ready),
        .response_valid(response_valid), .response_channel(response_channel), .response_data(response_data),
        .clk_adc(clk_adc), .pll_locked(pll_locked)
    );
    n2m_physical_controls u_controls (
        .clk_sys(clk_sys), .reset_sys(global_reset), .gb_tick(1'b0), .buttons_n(4'hF),
        .adc_available(!adc_reset), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid),
        .response_channel(response_channel), .response_data(response_data),
        .physical_commit(physical_commit), .physical_buttons(physical_buttons), .adc_fresh(fresh), .adc_fault(fault)
    );
    initial begin clk_sys = 1'b0; forever #20 clk_sys = !clk_sys; end
    initial begin clk_board_reference = 1'b0; forever #10 clk_board_reference = !clk_board_reference; end
    initial begin clk_reference = 1'b0; forever #50 clk_reference = !clk_reference; end
    always @(posedge clk_sys) begin
        if (global_reset || adc_reset) begin pending = 1'b0; next_channel = 5'd1; end
        else begin
            if (command_valid && command_ready) begin
                if (pending || command_channel !== next_channel)
                    $fatal(1, "ADC_VENDOR_COMMAND expected=%0d actual=%0d pending=%0b", next_channel, command_channel, pending);
                pending = 1'b1; pending_channel = next_channel;
                next_channel = next_channel == 5'd1 ? 5'd2 : 5'd1;
                commands = commands + 1;
            end
            if (response_valid) begin
                if (!pending || response_channel !== pending_channel ||
                    response_data !== (pending_channel == 5'd1 ? 12'd1024 : 12'd2048))
                    $fatal(1, "ADC_VENDOR_DATA expected=%0d,%0d actual=%0d,%0d pending=%0b",
                        pending_channel, pending_channel == 5'd1 ? 1024 : 2048, response_channel, response_data, pending);
                pending = 1'b0; replies = replies + 1;
            end
        end
    end
    always @(negedge clk_sys) begin
        if (corrupt && response_valid && response_channel == 5'd2) force response_data = 12'd0;
    end
    initial begin
        board_reset_n = 1'b0; global_reset = 1'b1;
        pending = 1'b0; next_channel = 5'd1; pending_channel = 5'd0;
        commands = 0; replies = 0; corrupt = $test$plusargs("CORRUPT_ADC");
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, clk_board_reference, clk_reference, clk_adc, board_reset_n, global_reset, pll_reset,
            pll_locked, adc_ready, adc_reset, command_valid, command_channel, command_ready,
            response_valid, response_channel, response_data, physical_commit, physical_buttons, fresh, fault);
        repeat (10) @(negedge clk_sys);
        board_reset_n = 1'b1; global_reset = 1'b0;
        wait (replies == 4); @(negedge clk_sys);
        if (!fresh || physical_buttons !== 8'h08 || fault) $fatal(1, "ADC_VENDOR_EFFECTIVE");
        // The fifth command is an outstanding X when lock loss cancels it.
        wait (commands == 5); @(negedge clk_sys); force pll_locked = 1'b0;
        repeat (8) @(negedge clk_sys);
        if (fresh || physical_buttons !== 8'h00 || !adc_reset) $fatal(1, "ADC_VENDOR_LOCK_CANCEL");
        release pll_locked;
        wait (replies == 8); @(negedge clk_sys);
        if (!fresh || physical_buttons !== 8'h08 || fault) $fatal(1, "ADC_VENDOR_RECOVERY");
        $display("PASS actual ADC model replies=%0d commands=%0d lock-cancel", replies, commands);
        $finish;
    end
    initial begin #40000000; $fatal(1, "ADC_VENDOR_WATCHDOG"); end
endmodule

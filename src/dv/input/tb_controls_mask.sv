`timescale 1ns/1ps
module tb_controls_mask;
    logic clk;
    logic reset;
    logic core_reset;
    logic gb_tick;
    logic [3:0] buttons_n;
    logic [3:0] pressed;
    logic [3:0] accepted_pressed;
    logic pair_valid;
    logic [11:0] pair_x;
    logic [11:0] pair_y;
    logic fresh;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic reverse_commit;
    logic [7:0] reverse_buttons;
    logic [7:0] physical_observe;
    logic [7:0] host_observe;
    logic [7:0] source_observe;
    logic [7:0] effective_buttons;
    n2m_input_pkg::input_write_t host_write;
    n2m_input_pkg::input_update_t effective_update;
    integer checks;
    bit corrupt;
    n2m_button_filter #(.STABLE_CYCLES(3)) u_buttons (
        .clk_sys(clk), .reset_sys(reset), .buttons_n(buttons_n), .pressed(pressed), .accepted_pressed(accepted_pressed)
    );
    n2m_controls_mask u_mask (
        .clk_sys(clk), .reset_sys(reset), .gb_tick(gb_tick), .buttons_pressed(accepted_pressed),
        .pair_valid(pair_valid), .pair_x(pair_x), .pair_y(pair_y), .fresh(fresh),
        .physical_commit(physical_commit), .physical_buttons(physical_buttons)
    );
    n2m_controls_mask #(.X_REVERSE(1'b1), .Y_REVERSE(1'b1)) u_reverse (
        .clk_sys(clk), .reset_sys(reset), .gb_tick(gb_tick), .buttons_pressed(accepted_pressed),
        .pair_valid(pair_valid), .pair_x(pair_x), .pair_y(pair_y), .fresh(fresh),
        .physical_commit(reverse_commit), .physical_buttons(reverse_buttons)
    );
    n2m_input u_input (
        .clk_sys(clk), .reset_sys(reset), .core_reset(core_reset), .gb_tick(gb_tick),
        .host_write(host_write), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .host_buttons(host_observe), .physical_observe(physical_observe), .source_observe(source_observe),
        .effective_buttons(effective_buttons), .effective_update(effective_update)
    );
    initial begin clk = 1'b0; forever #10 clk = !clk; end
    task automatic step;
        @(posedge clk); #1; @(negedge clk);
    endtask
    task automatic check(input logic [7:0] expected_physical, input logic [7:0] expected_effective);
        if (physical_observe !== expected_physical || effective_buttons !== expected_effective)
            $fatal(1, "CONTROLS_MASK expected=%02h,%02h actual=%02h,%02h check=%0d",
                expected_physical, expected_effective, physical_observe, effective_buttons, checks);
        checks = checks + 1;
    endtask
    task automatic host(input logic source, input logic [7:0] value);
        host_write.valid = 1'b1; host_write.source_write = source; host_write.value = value;
        step(); host_write = '0;
    endtask
    task automatic pair(input logic [11:0] x, input logic [11:0] y, input logic [7:0] expected);
        pair_x = x; pair_y = y; pair_valid = 1'b1; fresh = 1'b1;
        step(); pair_valid = 1'b0; check(expected, expected);
    endtask
    initial begin
        reset = 1'b1; core_reset = 1'b0; gb_tick = 1'b0; buttons_n = 4'hF;
        pair_valid = 1'b0; pair_x = 12'd0; pair_y = 12'd0; fresh = 1'b0;
        host_write = '0; checks = 0; corrupt = $test$plusargs("CORRUPT_MASK");
        $dumpfile("waves.vcd");
        $dumpvars(0, clk, reset, core_reset, gb_tick, buttons_n, pressed, accepted_pressed, pair_valid,
            pair_x, pair_y, fresh, physical_commit, physical_buttons, reverse_commit,
            reverse_buttons, physical_observe, host_observe, source_observe, effective_buttons);
        @(negedge clk); step(); reset = 1'b0; step(); check(8'h00, 8'h00);
        host(1'b1, 8'h01);
        if (corrupt) force physical_buttons = 8'h00;
        pair(12'd0, 12'd2703, 8'h0A);
        if (reverse_buttons !== 8'h05) $fatal(1, "CONTROLS_POLARITY");
        pair(12'd1000, 12'd1700, 8'h0A);
        pair(12'd1014, 12'd1689, 8'h00);
        pair(12'd902, 12'd1802, 8'h0A);
        pair(12'd2703, 12'd0, 8'h05);
        pair(12'd1700, 12'd1000, 8'h05);
        pair(12'd1689, 12'd1014, 8'h00);

        // One sampled bounce cannot satisfy three consecutive filtered samples.
        buttons_n = 4'hE; step(); buttons_n = 4'hF; repeat (5) step(); check(8'h00, 8'h00);
        buttons_n = 4'hE; repeat (4) step();
        if (pressed !== 4'h0) $fatal(1, "CONTROLS_BUTTON_EARLY");
        // On the exact fifth edge (2 synchronizers + 3 stable samples),
        // debounce and the complete pair must reach the shared owner together.
        pair_x = 12'd0; pair_y = 12'd2703; pair_valid = 1'b1;
        step(); pair_valid = 1'b0; check(8'h1A, 8'h1A);
        if (pressed !== 4'h1) $fatal(1, "CONTROLS_BUTTON_THRESHOLD");
        step(); check(8'h1A, 8'h1A);
        fresh = 1'b0; step(); check(8'h10, 8'h10);
        buttons_n = 4'h0; repeat (6) step(); check(8'hF0, 8'hF0);
        pair(12'd2703, 12'd0, 8'hF5);

        // Complete pair changes on a tick are deferred as one whole mask.
        gb_tick = 1'b1; pair_x = 12'd0; pair_y = 12'd2703; pair_valid = 1'b1;
        step(); pair_valid = 1'b0; check(8'hF5, 8'hF5);
        gb_tick = 1'b0; step(); check(8'hFA, 8'hFA);
        fresh = 1'b0; step(); check(8'hF0, 8'hF0);

        // Actual shared owner keeps both shadows and chooses the new source.
        host(1'b1, 8'h00); host(1'b0, 8'h20); check(8'hF0, 8'h20);
        pair_x = 12'd2703; pair_y = 12'd0; pair_valid = 1'b1; fresh = 1'b1;
        step(); pair_valid = 1'b0; check(8'hF5, 8'h20);
        host_write.valid = 1'b1; host_write.source_write = 1'b1; host_write.value = 8'h01;
        pair_x = 12'd0; pair_y = 12'd2703; pair_valid = 1'b1;
        step(); host_write = '0; pair_valid = 1'b0; check(8'hFA, 8'hFA);
        core_reset = 1'b1; step(); check(8'hFA, 8'h00);
        core_reset = 1'b0; host(1'b1, 8'h01); check(8'hFA, 8'hFA);
        buttons_n = 4'hF; repeat (6) step(); check(8'h0A, 8'h0A);
        reset = 1'b1; #1; check(8'h00, 8'h00);
        $display("PASS controls mask checks=%0d", checks); $finish;
    end
    initial begin #100000; $fatal(1, "CONTROLS_MASK_WATCHDOG"); end
endmodule

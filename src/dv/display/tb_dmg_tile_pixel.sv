`timescale 1ns/1ps
`default_nettype none
module tb_dmg_tile_pixel;
    logic clk;
    logic reset, enable, valid_s0;
    logic [7:0] row_low_s0, row_high_s0, palette_s0;
    logic [2:0] pixel_x_s0;
    wire valid_s1;
    wire [1:0] color_index_s1, shade_s1;
    logic [4:0] expected;
    integer cycle;
    integer pixel_cases;
    integer palette_cases;
    bit corrupt;

    dmg_tile_pixel dut (.*);

    // Arithmetic oracle deliberately uses neither DUT selectors nor hierarchy.
    function automatic integer decode(input integer low_row, high_row, x);
        integer divisor;
        begin
            divisor = 128;
            repeat (x) divisor = divisor / 2;
            decode = (low_row / divisor) % 2 + 2 * ((high_row / divisor) % 2);
        end
    endfunction

    function automatic integer map_shade(input integer palette, index);
        integer remaining;
        begin
            remaining = palette;
            repeat (index) remaining = remaining / 4;
            map_shade = remaining % 4;
        end
    endfunction

    task automatic check_output(input string phase_name);
        logic [4:0] observed;
        begin
            observed = {valid_s1, color_index_s1, shade_s1};
            // Exercise the same checker with a deliberately corrupted observation.
            if (corrupt && cycle == 5) observed[0] = ~observed[0];
            assert (observed === expected) else
                $fatal(1, "MISMATCH cycle=%0d phase=%s expected=%b actual=%b low=%h high=%h x=%0d palette=%h seed=none",
                       cycle, phase_name, expected, observed, row_low_s0,
                       row_high_s0, pixel_x_s0, palette_s0);
        end
    endtask

    task automatic step(input logic rst, en, valid_in,
                        input logic [7:0] low_row, high_row,
                        input logic [2:0] x, input logic [7:0] palette);
        integer index, shade;
        begin
            clk = 0;
            reset = rst; enable = en; valid_s0 = valid_in;
            row_low_s0 = low_row; row_high_s0 = high_row;
            pixel_x_s0 = x; palette_s0 = palette;
            #4;
            if (cycle != 0) check_output("between-edges");
            if (rst) expected = 0;
            else if (en) begin
                if (valid_in) begin
                    index = decode(int'(low_row), int'(high_row), int'(x));
                    shade = map_shade(int'(palette), index);
                    expected = {1'b1, index[1:0], shade[1:0]};
                end else expected = 0;
            end
            clk = 1;
            #1;
            cycle = cycle + 1;
            check_output("after-edge");
            #5;
        end
    endtask

    initial begin : stimulus
        integer low_row, high_row, x, palette, index, rst, en, valid_in;
        corrupt = $test$plusargs("corrupt");
        $dumpfile("waves.vcd");
        $dumpvars(0, tb_dmg_tile_pixel);
        step(1, 0, 0, 'x, 'z, 'x, 'x);
        // Exhaust all binary control combinations from a populated stage.
        for (rst = 0; rst < 2; rst = rst + 1)
            for (en = 0; en < 2; en = en + 1)
                for (valid_in = 0; valid_in < 2; valid_in = valid_in + 1) begin
                    step(0, 1, 1, 8'h80, 8'h00, 0, 8'h1b);
                    step(rst[0], en[0], valid_in[0], 8'h00, 8'h01, 7, 8'he4);
                end
        step(0, 0, 'x, 'x, 'z, 'x, 'z);
        step(0, 0, 0, 'z, 'x, 'z, 'x);
        step(0, 1, 0, 'x, 'z, 'x, 'z);
        step(1, 'x, 'x, 'z, 'x, 'z, 'x);
        for (x = 0; x < 8; x = x + 1) begin
            step(0, 1, 1, 8'h3c, 8'h7e, x[2:0], 8'he4);
            step(0, 1, 1, 8'h80 >> x, 8'h01 << x, x[2:0], 8'h1b);
        end
        // Keep the useful control trace; exhaustive loops need no huge wave file.
        $dumpoff;
        for (low_row = 0; low_row < 256; low_row = low_row + 1)
            for (high_row = 0; high_row < 256; high_row = high_row + 1)
                for (x = 0; x < 8; x = x + 1) begin
                    step(0, 1, 1, low_row[7:0], high_row[7:0], x[2:0], 8'he4);
                    pixel_cases = pixel_cases + 1;
                end
        for (palette = 0; palette < 256; palette = palette + 1)
            for (index = 0; index < 4; index = index + 1)
                for (x = 0; x < 8; x = x + 1) begin
                    step(0, 1, 1, index[0] ? 8'hff : 8'h00,
                         index[1] ? 8'hff : 8'h00, x[2:0], palette[7:0]);
                    palette_cases = palette_cases + 1;
                end
        $dumpon;
        step(0, 0, 1, 0, 0, 0, 0);
        step(1, 0, 1, 0, 0, 0, 0);
        step(0, 1, 1, 8'h01, 8'h00, 7, 8'hff);
        step(0, 1, 0, 'x, 'z, 'x, 'z);
        $display("PASS pixel_cases=%0d palette_cases=%0d cycles=%0d seed=none",
                 pixel_cases, palette_cases, cycle);
        $finish;
    end

    initial begin
        clk = 0;
        expected = 0;
        cycle = 0;
        pixel_cases = 0;
        palette_cases = 0;
        #6000000;
        $fatal(1, "TIMEOUT seed=none");
    end
endmodule
`default_nettype wire

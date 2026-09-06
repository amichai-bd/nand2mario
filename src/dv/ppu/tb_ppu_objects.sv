`timescale 1ns/1ps
`default_nettype none
module tb_ppu_objects;
    logic clk_sys, reset, gb_tick, lcd_on, size16, object_enable;
    logic [7:0] line_y, pixel_position;
    logic scan_reset, fetch_mode, fetch_phase1, fetch_done, dma_active;
    logic [15:0] oam_data;
    logic oam_valid;
    logic [6:0] oam_pair_address;
    logic [1:0] oam_phase;
    logic [5:0] scan_index;
    logic scan_active, scan_done, object_found;
    logic [10:0] tile_row_address;
    logic [7:0] object_attributes;
    logic [3:0] selected_index;
    logic fault;
    integer entry;
    n2m_ppu_objects dut (.*);
    task automatic tick;
        #5; clk_sys = 1;
        #1;
        #4; clk_sys = 0;
    endtask
    task automatic begin_scan;
        reset = 1;
        tick();
        reset = 0;
        scan_reset = 1;
        fetch_mode = 0;
        fetch_done = 0;
        fetch_phase1 = 0;
        dma_active = 0;
        tick();
        scan_reset = 0;
    endtask
    task automatic fetch_check(input logic [3:0] index_value,
        input logic [6:0] pair_value, input logic [15:0] data_value, input logic [10:0] row_value);
        fetch_mode = 1;
        #1;
        if (!object_found || selected_index !== index_value || oam_phase !== 2 || oam_pair_address !== pair_value)
            $fatal(1, "PPU_OBJECT_SELECTION index=%0d actual=%0d", index_value, selected_index);
        fetch_phase1 = 1;
        oam_data = data_value;
        tick();
        fetch_phase1 = 0;
        if (tile_row_address !== row_value || object_attributes !== data_value[15:8])
            $fatal(1, "PPU_OBJECT_ROW_OR_ATTRIBUTE");
        fetch_done = 1;
        tick();
        fetch_done = 0;
        tick();
    endtask
    initial begin
        clk_sys = 0;
        reset = 1;
        gb_tick = 1;
        lcd_on = 1;
        size16 = 1;
        object_enable = 1;
        line_y = 0;
        pixel_position = 8;
        scan_reset = 0;
        fetch_mode = 0;
        fetch_phase1 = 0;
        fetch_done = 0;
        dma_active = 0;
        oam_data = 0;
        oam_valid = 1;
        begin_scan();
        for (entry = 0; entry < 40; entry = entry + 1) begin
            tick();
            if (oam_pair_address !== 7'(2 * entry) || oam_phase !== 1)
                $fatal(1, "PPU_OBJECT_SCAN_ADDRESS entry=%0d", entry);
            if (entry < 2) oam_data = 16'h0810;
            else if (entry < 10) oam_data = 16'h0010; // hidden X still consumes a slot
            else oam_data = 16'h1010;
            if ($test$plusargs("missing") && entry == 0) oam_valid = 0;
            tick();
        end
        tick(); // final saved pair follows its capture
        if (!scan_done) $fatal(1, "PPU_OBJECT_SCAN_END");
        fetch_check(0, 7'd1, 16'hd023, 11'h11f); // 8x16 ignores tilebit0, vertical flip
        fetch_check(1, 7'd3, 16'h0024, 11'h120);
        pixel_position = 16;
        #1;
        if (object_found) $fatal(1, "PPU_OBJECT_FIRST_TEN_HIDDEN_X");
        begin_scan();
        pixel_position = 8;
        for (entry = 0; entry < 40; entry = entry + 1) begin
            tick();
            dma_active = entry == 1;
            oam_data = entry == 0 ? 16'h0810 : 16'h20c8;
            tick();
        end
        dma_active = 0;
        tick();
        fetch_check(0, 7'd1, 16'h0020, 11'h100);
        fetch_check(1, 7'd3, 16'h0022, 11'h110); // DMA suppression retained prior Y/X pair
        begin_scan();
        for (entry = 0; entry < 40; entry = entry + 1) begin
            tick();
            oam_data = entry == 39 ? 16'h0810 : 16'h20c8;
            tick();
        end
        fetch_mode = 1;
        #1;
        if (!scan_done || object_found) $fatal(1, "PPU_OBJECT_FINAL_CAPTURE_ORDER");
        tick(); // only now can the captured final OAM entry be admitted
        fetch_check(0, 7'd79, 16'h0026, 11'h130);
        gb_tick = 0;
        reset = 1;
        tick();
        if (fault || scan_index !== 0 || object_found) $fatal(1, "PPU_OBJECT_PAUSED_RESET");
        $display("PASS PPU objects first_ten_dma_priority");
        $finish;
    end
    initial begin
        #5000;
        $fatal(1, "PPU_OBJECT_TIMEOUT");
    end
endmodule

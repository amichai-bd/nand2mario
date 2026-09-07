`timescale 1ns/1ps
`default_nettype none
module tb_memory_stores;
    import n2m_memory_pkg::*;
    logic clk_sys, reset_sys, core_reset, init_done;
    logic access_read, access_write, access_valid, host_read, host_write, host_valid;
    memory_store_t access_store;
    logic [14:0] access_address;
    logic [7:0] access_wdata, access_rdata, host_wdata, host_rdata;
    logic [31:0] host_offset;
    logic ppu_vram_read, ppu_vram_valid, ppu_oam_read, ppu_oam_valid, wave_read, wave_valid;
    logic [12:0] ppu_vram_address;
    logic [7:0] ppu_vram_rdata, wave_rdata;
    logic [6:0] ppu_oam_pair;
    logic [15:0] ppu_oam_rdata;
    logic [3:0] wave_address;
    integer index, store_number, size, inspected;
    bit early;
    bit range_probe, range_fault;
    n2m_memory_stores dut (.*);

    function automatic integer bytes_in_store(input integer number);
        case (number)
            1, 3: return 8192;
            2: return 127;
            4: return 160;
            5: return 16;
            default: return 32768;
        endcase
    endfunction
    task automatic inspect_enables(input bit writing);
        logic [5:0] selected;
        begin
            selected = 0;
            if (store_number < 6 && index < bytes_in_store(store_number)) selected[store_number] = 1;
            if ({dut.wave_ram.a_read, dut.oam_low.a_read, dut.vram.a_read,
                 dut.hram.a_read, dut.wram.a_read, dut.rom.b_read} !== (writing ? 6'd0 : selected) ||
                dut.oam_high.a_read !== (!writing && selected[4]) ||
                dut.rom.a_write !== 1'b0 ||
                dut.wram.a_write !== (writing && selected[1]) ||
                dut.hram.a_write !== (writing && selected[2]) ||
                dut.vram.a_write !== (writing && selected[3]) ||
                dut.oam_low.a_write !== (writing && selected[4] && index%2==0) ||
                dut.oam_high.a_write !== (writing && selected[4] && index%2==1) ||
                dut.wave_ram.a_write !== (writing && selected[5]))
                $fatal(1,"MEMORY_BANK_ENABLE store=%0d address=%04h",store_number,access_address);
        end
    endtask
    function automatic logic [7:0] pattern(input integer number, offset);
        return 8'(number * 41 + offset * 29 + offset / 256);
    endfunction
    task automatic edge_cycle;
        #5; clk_sys = 1;
        #1;
        #4; clk_sys = 0;
    endtask
    task automatic wait_clear;
        for (index = 0; index < 8192; index = index + 1) begin
            if (init_done) $fatal(1, "MEMORY_STORES_EARLY_INIT edge=%0d", index);
            if (early && index == 7) force dut.init_done = 1'b1;
            // Observe public primitive write ports; expectations come from the
            // independently counted sweep edge, not the DUT's clear counter.
            if (dut.wram.a_write !== 1'b1 || dut.vram.a_write !== 1'b1
                || dut.wram.a_address !== 13'(index) || dut.vram.a_address !== 13'(index)
                || dut.wram.a_wdata !== 8'd0 || dut.vram.a_wdata !== 8'd0
                || dut.hram.a_write !== (index < 127)
                || dut.oam_low.a_write !== (index < 160 && index % 2 == 0)
                || dut.oam_high.a_write !== (index < 160 && index % 2 == 1)
                || dut.wave_ram.a_write !== (index < 16))
                $fatal(1, "MEMORY_STORES_CLEAR_WRITES edge=%0d", index);
            if ((index < 127 && (dut.hram.a_address !== 7'(index) || dut.hram.a_wdata !== 8'd0))
                || (index < 160 && (dut.oam_low.a_address !== 7'(index / 2)
                    || dut.oam_high.a_address !== 7'(index / 2)
                    || dut.oam_low.a_wdata !== 8'd0 || dut.oam_high.a_wdata !== 8'd0))
                || (index < 16 && (dut.wave_ram.a_address !== 4'(index) || dut.wave_ram.a_wdata !== 8'd0)))
                $fatal(1, "MEMORY_STORES_CLEAR_ADDRESS_DATA edge=%0d", index);
            edge_cycle();
        end
        if (!init_done) $fatal(1, "MEMORY_STORES_LATE_INIT");
    endtask
    task automatic inspect_ram(input bit patterned);
        for (store_number = 1; store_number <= 5; store_number = store_number + 1) begin
            access_store = memory_store_t'(store_number);
            access_read = 1;
            size = bytes_in_store(store_number);
            for (index = 0; index < size; index = index + 1) begin
                access_address = 15'(index);
                edge_cycle();
                if (!access_valid || access_rdata !== (patterned ? pattern(store_number, index) : 8'd0))
                    $fatal(1, "MEMORY_STORES_READ store=%0d offset=%0d expected=%02h actual=%02h valid=%0d",
                        store_number, index, patterned ? pattern(store_number, index) : 8'd0, access_rdata, access_valid);
                inspected = inspected + 1;
            end
        end
        access_read = 0;
        edge_cycle();
        if (access_valid) $fatal(1, "MEMORY_STORES_STALE_VALID");
    endtask
    initial begin
        $dumpfile("memory-stores.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, init_done, access_read, access_write,
            access_store, access_address, access_wdata, access_rdata, access_valid,
            host_read, host_write, host_offset, host_wdata, host_rdata, host_valid,
            ppu_vram_read, ppu_vram_address, ppu_vram_rdata, ppu_vram_valid,
            ppu_oam_read, ppu_oam_pair, ppu_oam_rdata, ppu_oam_valid,
            wave_read, wave_address, wave_rdata, wave_valid,
            dut.rom.b_read, dut.rom.a_write, dut.wram.a_read, dut.wram.a_write,
            dut.hram.a_read, dut.hram.a_write, dut.vram.a_read, dut.vram.a_write,
            dut.oam_low.a_read, dut.oam_low.a_write, dut.oam_high.a_read,
            dut.oam_high.a_write, dut.wave_ram.a_read, dut.wave_ram.a_write);
        clk_sys = 0; reset_sys = 1; core_reset = 0;
        access_read = 0; access_write = 0; access_store = STORE_ROM;
        access_address = 0; access_wdata = 0;
        host_read = 0; host_write = 0; host_offset = 0; host_wdata = 0;
        ppu_vram_read = 0; ppu_vram_address = 0;
        ppu_oam_read = 0; ppu_oam_pair = 0;
        wave_read = 0; wave_address = 0;
        inspected = 0;
        early = $test$plusargs("early");
        range_probe = $test$plusargs("range_probe");
        range_fault = $test$plusargs("range_fault");
        edge_cycle();
        reset_sys = 0;
        wait_clear();
        if (range_probe) begin
            // Inspect the real primitive ports with the clock stopped. Invalid
            // requests never reach an edge; normal tests exercise storage data.
            for (store_number=0; store_number<8; store_number=store_number+1) begin
                access_store=memory_store_t'(store_number);
                for (index=0; index<32768; index=index+1) begin
                    access_address=15'(index); access_read=1; access_write=0;
                    if (range_fault && store_number==6 && index==0) force dut.wram.a_write=1'b1;
                    #1; inspect_enables(0);
                    access_read=0; access_write=1;
                    #1; inspect_enables(1);
                    access_write=0;
                end
            end
            $display("PASS memory bank enables selectors=8 addresses=32768 directions=2");
            $finish;
        end
        inspect_ram(0);
        for (store_number = 1; store_number <= 5; store_number = store_number + 1) begin
            access_store = memory_store_t'(store_number);
            access_write = 1;
            size = bytes_in_store(store_number);
            for (index = 0; index < size; index = index + 1) begin
                access_address = 15'(index);
                access_wdata = pattern(store_number, index);
                edge_cycle();
            end
        end
        access_write = 0;
        inspect_ram(1);
        ppu_vram_read = 1; ppu_oam_read = 1; wave_read = 1;
        for (index = 0; index < 8192; index = index + 1) begin
            ppu_vram_address = 13'(index);
            ppu_oam_pair = 7'(index % 80);
            wave_address = 4'(index % 16);
            edge_cycle();
            if (!ppu_vram_valid || ppu_vram_rdata !== pattern(3, index)
                || !ppu_oam_valid || ppu_oam_rdata !== {pattern(4, (index % 80) * 2 + 1), pattern(4, (index % 80) * 2)}
                || !wave_valid || wave_rdata !== pattern(5, index % 16))
                $fatal(1, "MEMORY_STORES_PARALLEL offset=%0d", index);
        end
        ppu_vram_read = 0; ppu_oam_read = 0; wave_read = 0;
        host_write = 1;
        for (index = 0; index < 32768; index = index + 1) begin
            host_offset = 32'(index); host_wdata = pattern(0, index);
            edge_cycle();
        end
        host_write = 0;
        // CPU/store writes to ROM cannot perform loading.
        access_store = STORE_ROM; access_write = 1; access_address = 15'd32767; access_wdata = 8'h33;
        edge_cycle();
        access_write = 0;
        // Cancel actual outstanding valid responses between clock edges.
        access_read = 1; host_read = 1;
        ppu_vram_read = 1; ppu_oam_read = 1; wave_read = 1;
        edge_cycle();
        if (!access_valid || !host_valid || !ppu_vram_valid || !ppu_oam_valid || !wave_valid)
            $fatal(1, "MEMORY_STORES_RESET_SETUP");
        core_reset = 1;
        #1;
        if (init_done || access_valid || host_valid || ppu_vram_valid || ppu_oam_valid || wave_valid)
            $fatal(1, "MEMORY_STORES_RESET_RESPONSE");
        edge_cycle();
        access_read = 0; host_read = 0;
        ppu_vram_read = 0; ppu_oam_read = 0; wave_read = 0;
        core_reset = 0;
        wait_clear();
        inspect_ram(0);
        host_read = 1; access_read = 1; access_store = STORE_ROM;
        for (index = 0; index < 32768; index = index + 1) begin
            host_offset = 32'(index); access_address = 15'(32767 - index);
            edge_cycle();
            if (!host_valid || host_rdata !== pattern(0, index)
                || !access_valid || access_rdata !== pattern(0, 32767 - index))
                $fatal(1, "MEMORY_STORES_ROM_RETAIN offset=%0d", index);
        end
        // Global reset cancels prepared ROM responses and retains every loaded
        // byte. A sampled core reset partway through clearing restarts all 8192
        // write edges; the previous partial sweep cannot shorten completion.
        reset_sys = 1;
        #1;
        if (init_done || access_valid || host_valid)
            $fatal(1, "MEMORY_STORES_GLOBAL_RESET_RESPONSE");
        edge_cycle();
        access_read = 0; host_read = 0; reset_sys = 0;
        for (index = 0; index < 17; index = index + 1) begin
            if (init_done) $fatal(1, "MEMORY_STORES_INTERRUPTED_CLEAR");
            edge_cycle();
        end
        core_reset = 1; edge_cycle(); core_reset = 0;
        wait_clear();
        inspect_ram(0);
        host_read = 1; access_read = 1; access_store = STORE_ROM;
        for (index = 0; index < 32768; index = index + 1) begin
            host_offset = 32'(index); access_address = 15'(32767 - index);
            edge_cycle();
            if (!host_valid || host_rdata !== pattern(0, index)
                || !access_valid || access_rdata !== pattern(0, 32767 - index))
                $fatal(1, "MEMORY_STORES_GLOBAL_ROM_RETAIN offset=%0d", index);
        end
        $display("PASS memory stores RAM_inspected=%0d ROM_bytes=32768 clear_edges=8192", inspected);
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "MEMORY_STORES_WATCHDOG");
    end
endmodule

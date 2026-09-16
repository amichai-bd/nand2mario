`timescale 1ns/1ps
`default_nettype none
// Loader profile fixtures against the real memory owner, core control owner,
// SDRAM controller and device model, with a bus driver in place of the CPU.
// Contract: wiki/src/rtl/cartridge/MAS_loader_profile.md#verification.
// Test plan: README.md. One fixture per run, selected with +fixture=<name>:
// map, window, swap, swap-fault, key1. Expectations come from the contract
// and the fixture's own library image, never from DUT state.
// Lint waiver: integer arithmetic on byte and address values.
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
module tb_loader #(
    // Real KEY1 timing by default; the queue fixture shortens both so its
    // ordering cases run inside the wall budget.
    parameter int unsigned KEY1_DEBOUNCE_EDGES = 125000,
    parameter int unsigned KEY1_HOLD_EDGES = 12500000
);
    import n2m_interfaces_pkg::*;
    localparam int IMAGES = 17;
    localparam int SLOT = 32768;
    // The library plus the rest of catalogue bank 34 (zero) and bank 63 (a
    // pattern), so every window bank the fixtures select is defined.
    localparam int LIBRARY_BYTES = 32'h8C000;
    localparam int BANK63_START = 32'hFC000;
    localparam int BANK63_END = 32'h100000;
    localparam int MENU = 16;
    localparam int FILL_BOUND = 40000;
    localparam int SWAP_BOUND = 80000;
    localparam int DEBOUNCE = int'(KEY1_DEBOUNCE_EDGES);
    localparam int HOLD = int'(KEY1_HOLD_EDGES);
    localparam int MS = 25000;

    logic clk_sys, reset_sys, sdram_reset;
    // Endpoint state the command owner would hold.
    logic [7:0] profile;
    logic image_valid, host_session, host_port_busy, host_return;
    // Memory owner and CPU port.
    logic init_done, request_valid, write_enable, bus_commit, response_valid, contract_fault;
    logic [15:0] address;
    logic [7:0] write_data, port_read_data, cpu_read_data;
    logic storage_read, storage_write, storage_valid;
    n2m_memory_pkg::memory_store_t storage_store;
    logic [14:0] storage_offset;
    logic [7:0] storage_wdata, storage_rdata;
    logic owner_prepare, owner_commit, owner_write;
    logic [15:0] owner_address;
    logic [7:0] owner_wdata;
    n2m_memory_pkg::memory_destination_t owner_destination;
    logic rom_host_write, rom_host_read, rom_host_valid;
    logic [31:0] rom_host_offset;
    logic [7:0] rom_host_wdata, rom_host_rdata;
    // Loader.
    logic read_override, copy_busy, swap_busy, window_busy, sdram_ready;
    logic [7:0] loader_read_data;
    logic [31:0] library_status, library_key1;
    logic key1_n;
    logic engine_pause, engine_reset_request, engine_reset_accept, engine_reset_done;
    logic image_invalidate, image_publish;
    logic [7:0] image_profile;
    // Host SDRAM client.
    logic host_sdram_valid, host_sdram_write, host_sdram_ready, host_sdram_response_valid;
    logic [25:0] host_sdram_address;
    logic [127:0] host_sdram_data;
    // Storage.
    logic sdram_request_valid, sdram_request_write, sdram_request_ready, sdram_response_valid;
    logic sdram_idle, sdram_initialized;
    logic [25:0] sdram_request_address;
    logic [127:0] sdram_request_data, sdram_response_data;
    logic [12:0] dram_addr;
    logic [1:0] dram_ba;
    logic dram_cas_n, dram_cke, dram_clk, dram_cs_n, dram_dqml, dram_dqmh, dram_ras_n, dram_we_n;
    tri [15:0] dram_dq;
    logic [31:0] model_refreshes, model_reads, model_writes;
    // Core control (host client driven by the fixture) and timebase.
    logic core_start, core_busy, core_done, pause_request, core_reset, gb_tick, paused;
    logic [7:0] core_command, core_status;
    logic [31:0] core_budget;
    logic [31:0] epoch;
    logic [63:0] dot_count, retirement_count, completed_dot;
    n2m_input_pkg::input_write_t accepted_input;
    n2m_interfaces_pkg::run_dots_t run_dots_result;
    // Fixture bookkeeping.
    string fixture;
    logic [255:0] entries [0:IMAGES-1];
    logic [31:0] image_crc [0:IMAGES-1];
    integer checks, engine_writes, swaps, fills, invalid_writes;
    logic saw_invalid_write;

    n2m_loader #(.KEY1_DEBOUNCE_EDGES(KEY1_DEBOUNCE_EDGES), .KEY1_HOLD_EDGES(KEY1_HOLD_EDGES)) dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .profile(profile), .image_valid(image_valid),
        .host_session(host_session), .host_loading(host_session), .host_port_busy(host_port_busy), .host_return(host_return),
        .paused(paused), .sdram_initialized(sdram_initialized),
        // No boot copier in this testbench: the client hook stays idle.
        .copier_busy(1'b0), .copier_pending(1'b0), .copier_valid(1'b0), .copier_write(1'b0), .copier_address('0), .copier_data('0),
        .copier_ready(), .copier_response_valid(), .flash_boot(1'b0), .boot_return(1'b0),
        .rom_commit(storage_write && storage_store == n2m_memory_pkg::STORE_ROM),
        .commit_offset(storage_offset), .commit_data(storage_wdata),
        .cpu_address(address), .read_override(read_override), .read_data(loader_read_data),
        .key1_n(key1_n),
        .uart_rom_write(1'b0), .uart_rom_read(1'b0), .uart_rom_address(15'd0), .uart_rom_wdata(8'd0),
        .rom_host_write(rom_host_write), .rom_host_read(rom_host_read),
        .rom_host_offset(rom_host_offset), .rom_host_wdata(rom_host_wdata),
        .host_sdram_valid(host_sdram_valid), .host_sdram_write(host_sdram_write),
        .host_sdram_address(host_sdram_address), .host_sdram_data(host_sdram_data),
        .host_sdram_ready(host_sdram_ready), .host_sdram_response_valid(host_sdram_response_valid),
        .sdram_request_valid(sdram_request_valid), .sdram_request_write(sdram_request_write),
        .sdram_request_address(sdram_request_address), .sdram_request_data(sdram_request_data),
        .sdram_request_ready(sdram_request_ready), .sdram_response_valid(sdram_response_valid),
        .sdram_response_data(sdram_response_data),
        .engine_pause(engine_pause), .engine_reset_request(engine_reset_request), .boot_run(1'b0),
        .engine_reset_accept(engine_reset_accept), .engine_reset_done(engine_reset_done),
        .image_invalidate(image_invalidate), .image_publish(image_publish), .image_profile(image_profile),
        .copy_busy(copy_busy), .swap_busy(swap_busy), .window_busy(window_busy), .sdram_ready(sdram_ready),
        .library_status(library_status), .library_key1(library_key1)
    );
    n2m_memory_cpu_port u_port (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .init_done(init_done),
        .request_valid(request_valid), .address(address), .write_enable(write_enable),
        .write_data(write_data), .bus_commit(bus_commit), .read_data(port_read_data),
        .response_valid(response_valid), .contract_fault(contract_fault),
        .storage_read(storage_read), .storage_write(storage_write), .storage_store(storage_store),
        .storage_offset(storage_offset), .storage_wdata(storage_wdata), .storage_rdata(storage_rdata),
        .storage_valid(storage_valid), .owner_prepare(owner_prepare), .owner_commit(owner_commit),
        .owner_destination(owner_destination), .owner_address(owner_address), .owner_write(owner_write),
        .owner_wdata(owner_wdata), .owner_rdata(8'h5A), .owner_valid(1'b1), .owner_service_available(1'b1)
    );
    n2m_memory_stores u_stores (.oam_request('0), .oam_response(),
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .init_done(init_done),
        .access_read(storage_read), .access_write(storage_write), .access_store(storage_store),
        .access_address(storage_offset), .access_wdata(storage_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(rom_host_read), .host_write(rom_host_write), .host_offset(rom_host_offset),
        .host_wdata(rom_host_wdata), .host_rdata(rom_host_rdata), .host_valid(rom_host_valid),
        .core_paused(paused), .oam_sequence_active(1'b0), .peek_ready(), .peek_read(1'b0),
        .peek_select(8'd0), .peek_offset(13'd0), .peek_rdata(), .peek_valid(),
        .ppu_vram_read(1'b0), .ppu_vram_address(13'd0), .ppu_vram_rdata(), .ppu_vram_valid(),
        .ppu_oam_read(1'b0), .ppu_oam_pair(7'd0), .ppu_oam_rdata(), .ppu_oam_valid(),
        .wave_read(1'b0), .wave_write(1'b0), .wave_address(4'd0), .wave_wdata(8'd0), .wave_rdata(), .wave_valid()
    );
    assign cpu_read_data = read_override ? loader_read_data : port_read_data;
    n2m_uart_core_control u_core (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .start(core_start), .command(core_command),
        .step_budget(core_budget), .input_write('0), .gb_tick(gb_tick), .paused(paused),
        .core_initialized(init_done), .instruction_complete(1'b0), .retirement_valid(1'b0), .cpu_stopped(1'b0),
        .engine_pause(engine_pause), .engine_reset_request(engine_reset_request), .boot_run(1'b0),
        .engine_reset_accept(engine_reset_accept), .engine_reset_done(engine_reset_done),
        .pause_request(pause_request), .core_reset(core_reset), .accepted_input(accepted_input),
        .epoch(epoch), .dot_count(dot_count), .retirement_count(retirement_count), .busy(core_busy),
        .done(core_done), .status(core_status), .completed_dot(completed_dot), .run_dots_result(run_dots_result)
    );
    n2m_timebase u_timebase (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(pause_request), .gb_tick(gb_tick), .paused(paused));
    // The controller has its own reset so a fixture can hold the SDRAM
    // uninitialized after the memory owner is ready.
    n2m_sdram_ctrl u_sdram (
        .clk_sys(clk_sys), .reset_sys(reset_sys || sdram_reset),
        .request_valid(sdram_request_valid), .request_write(sdram_request_write),
        .request_address(sdram_request_address), .request_data(sdram_request_data),
        .request_ready(sdram_request_ready), .response_valid(sdram_response_valid),
        .response_data(sdram_response_data), .idle(sdram_idle), .initialized(sdram_initialized),
        .DRAM_ADDR(dram_addr), .DRAM_BA(dram_ba), .DRAM_CAS_N(dram_cas_n), .DRAM_CKE(dram_cke),
        .DRAM_CLK(dram_clk), .DRAM_CS_N(dram_cs_n), .DRAM_DQ(dram_dq), .DRAM_DQML(dram_dqml),
        .DRAM_DQMH(dram_dqmh), .DRAM_RAS_N(dram_ras_n), .DRAM_WE_N(dram_we_n)
    );
    n2m_sim_sdram u_device (
        .dram_clk(dram_clk), .dram_addr(dram_addr), .dram_ba(dram_ba),
        .dram_ras_n(dram_ras_n), .dram_cas_n(dram_cas_n), .dram_we_n(dram_we_n),
        .dram_cke(dram_cke), .dram_cs_n(dram_cs_n), .dram_dqml(dram_dqml), .dram_dqmh(dram_dqmh),
        .dram_dq(dram_dq), .refreshes(model_refreshes), .reads(model_reads), .writes(model_writes)
    );
    always #20 clk_sys = !clk_sys;

    // The command owner's image_valid/PROFILE rules, modelled by the fixture.
    always @(posedge clk_sys) begin
        if (image_invalidate) begin image_valid <= 0; profile <= 0; end
        if (image_publish) begin image_valid <= 1; profile <= image_profile; end
    end
    // Independent observation of the engine's writes.
    always @(posedge clk_sys) if (!reset_sys && rom_host_write) begin
        engine_writes <= engine_writes + 1;
        if (swap_busy && image_valid) saw_invalid_write <= 1;
    end

    // The library: image i byte o, and the catalogue built from it.
    function automatic logic [7:0] image_byte(input int index, input int offset);
        return 8'((index * 37 + offset * 11 + (offset >> 7) * 5 + (index ^ offset) + 3) ^ (offset >> 12));
    endfunction
    function automatic logic [7:0] library_byte(input int address);
        int entry, offset;
        if (address < IMAGES * SLOT) return image_byte(address / SLOT, address % SLOT);
        if (address < 32'h88000 + IMAGES * 32) begin
            entry = (address - 32'h88000) / 32;
            offset = (address - 32'h88000) % 32;
            return entries[entry][offset*8 +: 8];
        end
        if (address >= BANK63_START && address < BANK63_END) return 8'(address * 3 + 1);
        return 8'h00;
    endfunction
    task automatic build_library;
        int index, offset, k;
        logic [31:0] crc;
        logic [255:0] entry;
        for (index = 0; index < IMAGES; index = index + 1) begin
            crc = WIRE_CRC32_INIT;
            for (offset = 0; offset < SLOT; offset = offset + 1)
                crc = n2m_uart_pkg::crc32_byte(crc, image_byte(index, offset));
            image_crc[index] = crc ^ WIRE_CRC32_INIT;
            entry = '0;
            entry[7:0] = LIBRARY_CATALOGUE_VALID;
            entry[15:8] = index == MENU ? PROFILE_LOADER_ID : PROFILE_DIRECT_ID;
            entry[31:16] = 16'(SLOT);
            entry[63:32] = image_crc[index];
            for (k = 0; k < 16; k = k + 1) entry[64 + k*8 +: 8] = image_byte(index, 32'h134 + k);
            // Fault slots: 3 empty, 5 wrong length, 7 unknown profile, 9 wrong CRC.
            if (index == 3) entry[7:0] = 8'h00;
            if (index == 5) entry[31:16] = 16'h4000;
            if (index == 7) entry[15:8] = 8'h09;
            if (index == 9) entry[63:32] = image_crc[index] ^ 32'h1;
            entries[index] = entry;
        end
    endtask
    task automatic preload_library;
        int address;
        for (address = 0; address < LIBRARY_BYTES; address = address + 2)
            u_device.preload_word(26'(address), {library_byte(address + 1), library_byte(address)});
        for (address = BANK63_START; address < BANK63_END; address = address + 2)
            u_device.preload_word(26'(address), {library_byte(address + 1), library_byte(address)});
    endtask

    // Bus driver: the memory owner's CPU port protocol, one access per call,
    // never while the core is paused (the CPU has no tick then).
    task automatic edge_cycle;
        @(negedge clk_sys);
    endtask
    task automatic wait_running;
        while (paused) edge_cycle();
    endtask
    task automatic cpu_write(input logic [15:0] target, input logic [7:0] value);
        wait_running();
        address = target; write_data = value; write_enable = 1; request_valid = 1;
        repeat (3) edge_cycle();
        bus_commit = 1;
        edge_cycle();
        bus_commit = 0; request_valid = 0; write_enable = 0;
    endtask
    task automatic cpu_read(output logic [7:0] value, input logic [15:0] target);
        wait_running();
        address = target; write_enable = 0; request_valid = 1;
        edge_cycle();
        #1;
        if (!response_valid) $fatal(1, "LOADER_TB_NO_RESPONSE address=%04h", target);
        value = cpu_read_data;
        bus_commit = 1;
        edge_cycle();
        bus_commit = 0; request_valid = 0;
    endtask
    task automatic expect_read(input logic [15:0] target, input logic [7:0] expected, input string what);
        logic [7:0] actual;
        cpu_read(actual, target);
        if (actual != expected)
            $fatal(1, "LOADER_TB_READ %s address=%04h expected=%02h actual=%02h", what, target, expected, actual);
        checks = checks + 1;
    endtask
    task automatic expect_status(input logic [7:0] expected_status, input logic [7:0] expected_result,
                                 input logic [7:0] expected_index, input string what);
        expect_read(16'hA000, expected_status, {what, " status"});
        expect_read(16'hA002, expected_result, {what, " result"});
        expect_read(16'hA003, expected_index, {what, " index"});
        if (library_status[7:0] != expected_status || library_status[15:8] != expected_result ||
            library_status[23:16] != expected_index)
            $fatal(1, "LOADER_TB_LIBRARY_STATUS %s value=%08h", what, library_status);
    endtask
    // Wait for copy_busy to fall and return the edges since the commit.
    task automatic wait_copy(output int edges, input int bound, input string what);
        edges = 0;
        while (copy_busy) begin
            edge_cycle();
            edges = edges + 1;
            if (edges > bound) $fatal(1, "LOADER_TB_BOUND %s edges=%0d bound=%0d", what, edges, bound);
        end
        checks = checks + 1;
    endtask
    task automatic host_command(input logic [7:0] command_value);
        edge_cycle();
        core_command = command_value; core_start = 1;
        edge_cycle();
        core_start = 0;
        while (!core_done) edge_cycle();
        edge_cycle();
    endtask
    // Start a host command and return at once; the fixture watches core_done.
    task automatic host_start(input logic [7:0] command_value, input logic [31:0] budget);
        edge_cycle();
        core_budget = budget; core_command = command_value; core_start = 1;
        edge_cycle();
        core_start = 0;
    endtask
    task automatic check_upper_half(input int bank);
        int offset;
        logic [7:0] actual;
        for (offset = 0; offset < 16384; offset = offset + 1) begin
            cpu_read(actual, 16'h4000 + 16'(offset));
            if (actual != library_byte(bank * 16384 + offset))
                $fatal(1, "LOADER_TB_WINDOW bank=%0d offset=%04h expected=%02h actual=%02h",
                    bank, offset, library_byte(bank * 16384 + offset), actual);
        end
        checks = checks + 1;
    endtask
    task automatic check_rom_image(input int index);
        int offset;
        logic [7:0] actual;
        for (offset = 0; offset < SLOT; offset = offset + 1) begin
            cpu_read(actual, 16'(offset));
            if (actual != image_byte(index, offset))
                $fatal(1, "LOADER_TB_IMAGE index=%0d offset=%04h expected=%02h actual=%02h",
                    index, offset, image_byte(index, offset), actual);
        end
        checks = checks + 1;
    endtask
    // A swap through the select register from the menu; checks the sequence.
    task automatic select_swap(input int index, input logic [7:0] expected_profile);
        int edges;
        logic [31:0] epoch_before;
        logic [7:0] status_before;
        epoch_before = epoch;
        saw_invalid_write = 0;
        cpu_write(16'h6000 + 16'(index * 7), 8'(index));
        // Accepted on the commit edge: busy at once, then the pause.
        #1;
        if (!copy_busy || !swap_busy) $fatal(1, "LOADER_TB_SWAP_BUSY index=%0d", index);
        while (!paused) begin edge_cycle(); if (rom_host_write) $fatal(1, "LOADER_TB_WRITE_BEFORE_PAUSE"); end
        wait_copy(edges, SWAP_BOUND, "swap");
        if (saw_invalid_write) $fatal(1, "LOADER_TB_VALID_DURING_WRITE index=%0d", index);
        if (!image_valid || profile != expected_profile)
            $fatal(1, "LOADER_TB_SWAP_PROFILE index=%0d profile=%02h valid=%b", index, profile, image_valid);
        if (epoch != epoch_before + 1) $fatal(1, "LOADER_TB_SWAP_EPOCH before=%0d after=%0d", epoch_before, epoch);
        if (library_status[15:8] != LIBRARY_RESULT_OK || library_status[23:16] != 8'(index))
            $fatal(1, "LOADER_TB_SWAP_RESULT status=%08h", library_status);
        // Running again without a host RUN.
        edges = 0;
        while (paused) begin edge_cycle(); edges = edges + 1; if (edges > 100) $fatal(1, "LOADER_TB_SWAP_STILL_PAUSED"); end
        swaps = swaps + 1;
        checks = checks + 1;
    endtask
    // The menu return through the host control write (same path as KEY1).
    task automatic host_menu_return;
        int edges;
        edge_cycle();
        host_return = 1;
        edge_cycle();
        host_return = 0;
        #1;
        if (!swap_busy) $fatal(1, "LOADER_TB_RETURN_BUSY");
        wait_copy(edges, SWAP_BOUND, "return");
        if (profile != PROFILE_LOADER_ID || !image_valid) $fatal(1, "LOADER_TB_RETURN_PROFILE profile=%02h", profile);
        while (paused) edge_cycle();
        swaps = swaps + 1;
    endtask
    task automatic press_key1(input int edges);
        key1_n = 0;
        repeat (edges) edge_cycle();
        key1_n = 1;
    endtask

    // Host client of the storage arbiter: one line read during a fill.
    task automatic host_line_read(input logic [25:0] line_address);
        int k;
        edge_cycle();
        host_sdram_valid = 1; host_sdram_write = 0; host_sdram_address = line_address;
        while (!host_sdram_ready) edge_cycle();
        edge_cycle();
        host_sdram_valid = 0;
        while (!host_sdram_response_valid) edge_cycle();
        for (k = 0; k < 16; k = k + 1)
            if (sdram_response_data[k*8 +: 8] != library_byte(line_address + k))
                $fatal(1, "LOADER_TB_HOST_LINE address=%07h byte=%0d", line_address, k);
        checks = checks + 1;
    endtask

    task automatic fixture_map;
        int a;
        logic [7:0] value;
        // A swap of the menu gives the ROM store a known image.
        select_swap(MENU, PROFILE_LOADER_ID);
        expect_status(8'h20, LIBRARY_RESULT_OK, 8'd16, "after menu");
        // Every address reads per the map: ROM low half, upper half (bank 33
        // after a fill), VRAM/WRAM/HRAM through the memory owner, the four
        // status bytes, $FF above them, and the fixed owner byte elsewhere.
        cpu_write(16'h2000, 8'd33);
        wait_copy(a, FILL_BOUND, "map fill");
        for (a = 0; a < 65536; a = a + 1) begin
            cpu_read(value, 16'(a));
            if (a < 16'h4000) begin if (value != image_byte(MENU, a)) $fatal(1, "LOADER_TB_MAP_ROM0 %04h", a); end
            else if (a < 16'h8000) begin if (value != library_byte(33 * 16384 + a - 16'h4000)) $fatal(1, "LOADER_TB_MAP_WINDOW %04h", a); end
            else if (a == 16'hA000) begin if (value != 8'h60) $fatal(1, "LOADER_TB_MAP_STATUS %02h", value); end
            else if (a == 16'hA001) begin if (value != 8'd33) $fatal(1, "LOADER_TB_MAP_BANK %02h", value); end
            else if (a == 16'hA002) begin if (value != LIBRARY_RESULT_OK) $fatal(1, "LOADER_TB_MAP_RESULT %02h", value); end
            else if (a == 16'hA003) begin if (value != 8'd16) $fatal(1, "LOADER_TB_MAP_INDEX %02h", value); end
            else if (a < 16'hC000 && a >= 16'hA000) begin if (value != 8'hFF) $fatal(1, "LOADER_TB_MAP_FF %04h=%02h", a, value); end
            else if (a >= 16'hFEA0 && a < 16'hFF00 || a >= 16'h8000 && a < 16'hA000 || a >= 16'hFE00 && a < 16'hFEA0 || a == 16'hFFFF) begin
                if (value != 8'h5A) $fatal(1, "LOADER_TB_MAP_OWNER %04h=%02h", a, value);
            end
        end
        checks = checks + 1;
        // Writes outside the two registers change nothing in the loader.
        for (a = 0; a < 65536; a = a + 1) begin
            if ((a >= 16'h2000 && a < 16'h4000) || (a >= 16'h6000 && a < 16'h8000)) continue;
            if (a >= 16'h8000 && a < 16'hA000 || a >= 16'hC000) continue;
            cpu_write(16'(a), 8'(a));
            #1;
            if (copy_busy || library_status != {2'b0, 6'd33, 8'd16, LIBRARY_RESULT_OK, 8'h60})
                $fatal(1, "LOADER_TB_MAP_WRITE_EFFECT %04h status=%08h", a, library_status);
        end
        checks = checks + 1;
        expect_read(16'h0000, image_byte(MENU, 0), "rom after writes");
        expect_read(16'h7FFF, library_byte(33 * 16384 + 16383), "window after writes");
        // Register range ends: both bank ends start a fill, both select ends a swap.
        cpu_write(16'h3FFF, 8'd2); wait_copy(a, FILL_BOUND, "bank end"); expect_read(16'hA001, 8'd2, "bank end");
        cpu_write(16'h2000, 8'd3); wait_copy(a, FILL_BOUND, "bank start"); expect_read(16'hA001, 8'd3, "bank start");
        // An out-of-range select is ignored: result and index unchanged.
        cpu_write(16'h7FFF, 8'd17);
        #1;
        if (copy_busy) $fatal(1, "LOADER_TB_MAP_SELECT_17");
        expect_status(8'h60, LIBRARY_RESULT_OK, 8'd16, "select 17");
        cpu_write(16'h7FFF, 8'd0);
        while (!paused) edge_cycle();
        wait_copy(a, SWAP_BOUND, "select end");
        while (paused) edge_cycle();
        // In DIRECT_ID the registers are absent: no fill, no status bytes, no mask.
        if (profile != PROFILE_DIRECT_ID) $fatal(1, "LOADER_TB_MAP_DIRECT profile=%02h", profile);
        cpu_write(16'h2000, 8'd5); cpu_write(16'h6000, 8'd16);
        #1;
        if (copy_busy || library_status[29:24] != 6'd3) $fatal(1, "LOADER_TB_MAP_DIRECT_EFFECT");
        for (a = 16'hA000; a < 16'hC000; a = a + 1) begin
            cpu_read(value, 16'(a));
            if (value != 8'hFF) $fatal(1, "LOADER_TB_MAP_DIRECT_FF %04h=%02h", a, value);
        end
        check_rom_image(0);
        checks = checks + 1;
    endtask

    task automatic fixture_window;
        int banks [0:4];
        int b, edges, max_edges;
        logic [7:0] value;
        banks = '{0, 1, 33, 34, 63};
        max_edges = 0;
        expect_status(8'h20, LIBRARY_RESULT_NONE, 8'hFF, "reset");
        for (b = 0; b < 5; b = b + 1) begin
            cpu_write(16'h2000 + 16'(b * 1023), 8'(banks[b]));
            #1;
            if (!copy_busy || !window_busy || library_status[6]) $fatal(1, "LOADER_TB_WINDOW_BUSY bank=%0d", banks[b]);
            // Window reads return $FF while busy; a second commit is ignored.
            expect_read(16'h4000, 8'hFF, "window busy");
            expect_read(16'h7FFF, 8'hFF, "window busy end");
            expect_read(16'hA000, 8'hA0, "busy status");
            cpu_write(16'h2000, 8'd7);
            if (b == 2) host_line_read(26'h0088000);
            wait_copy(edges, FILL_BOUND, "fill");
            if (edges > max_edges) max_edges = edges;
            expect_read(16'hA001, 8'(banks[b]), "bank register");
            expect_read(16'hA000, 8'h60, "ready status");
            expect_read(16'hA002, LIBRARY_RESULT_NONE, "fill result");
            check_upper_half(banks[b]);
            fills = fills + 1;
        end
        $display("LOADER_TB fill_max_edges=%0d", max_edges);
    endtask

    task automatic fixture_swap;
        int edges;
        expect_status(8'h20, LIBRARY_RESULT_NONE, 8'hFF, "reset");
        select_swap(0, PROFILE_DIRECT_ID);
        check_rom_image(0);
        host_menu_return();
        check_rom_image(MENU);
        select_swap(15, PROFILE_DIRECT_ID);
        check_rom_image(15);
        host_menu_return();
        // The window is invalid after a swap until the next bank commit.
        expect_read(16'hA000, 8'h20, "window after swap");
        select_swap(MENU, PROFILE_LOADER_ID);
        check_rom_image(MENU);
        expect_status(8'h20, LIBRARY_RESULT_OK, 8'd16, "after menu restart");
        // A host HALT held across a swap keeps the console paused afterwards.
        host_command(COMMAND_HALT);
        edge_cycle();
        host_return = 1; edge_cycle(); host_return = 0;
        wait_copy(edges, SWAP_BOUND, "halted return");
        repeat (200) edge_cycle();
        if (!paused) $fatal(1, "LOADER_TB_HALT_HELD");
        host_command(COMMAND_RUN);
        if (paused) $fatal(1, "LOADER_TB_RUN_AFTER_HALT");
        checks = checks + 1;
    endtask

    task automatic fixture_swap_fault;
        int edges, writes_before;
        logic [7:0] value;
        // A filled window first: window_ready must survive every refused select.
        cpu_write(16'h2000, 8'd1); wait_copy(edges, FILL_BOUND, "fill before faults");
        expect_read(16'hA000, 8'h60, "filled window");
        fills = fills + 1;
        // Refused selects: exact codes, index recorded, no ROM byte written.
        writes_before = engine_writes;
        cpu_write(16'h6000, 8'd3); wait_copy(edges, SWAP_BOUND, "empty slot");
        expect_status(8'h60, LIBRARY_RESULT_INVALID_SLOT, 8'd3, "empty slot");
        cpu_write(16'h6000, 8'd5); wait_copy(edges, SWAP_BOUND, "wrong length");
        expect_status(8'h60, LIBRARY_RESULT_INVALID_SLOT, 8'd5, "wrong length");
        cpu_write(16'h6000, 8'd7); wait_copy(edges, SWAP_BOUND, "bad profile");
        expect_status(8'h60, LIBRARY_RESULT_INVALID_SLOT, 8'd7, "bad profile");
        if (engine_writes != writes_before || paused || !image_valid || profile != PROFILE_LOADER_ID)
            $fatal(1, "LOADER_TB_REFUSED_EFFECT writes=%0d paused=%b", engine_writes - writes_before, paused);
        check_upper_half(1);
        // CRC mismatch: paused with no valid image, PROFILE 0, LOADING for the host.
        // The accepted swap keeps window_ready through its catalogue check and
        // clears it once the core is paused, before the first ROM write.
        cpu_write(16'h6000, 8'd9);
        while (!paused) begin
            edge_cycle();
            if (!library_status[6]) $fatal(1, "LOADER_TB_WINDOW_READY_EARLY");
        end
        repeat (2) edge_cycle();
        if (library_status[6]) $fatal(1, "LOADER_TB_WINDOW_READY_HELD");
        checks = checks + 1;
        wait_copy(edges, SWAP_BOUND, "crc mismatch");
        if (!paused || image_valid || profile != 8'd0 || library_status[15:8] != LIBRARY_RESULT_CRC_MISMATCH ||
            library_status[23:16] != 8'd9)
            $fatal(1, "LOADER_TB_CRC_MISMATCH paused=%b valid=%b profile=%02h status=%08h", paused, image_valid, profile, library_status);
        repeat (1000) edge_cycle();
        if (!paused) $fatal(1, "LOADER_TB_CRC_MISMATCH_RUNS");
        // Recovery through the return.
        host_menu_return();
        // The return is not a select commit, so $A003 keeps the refused index.
        expect_status(8'h20, LIBRARY_RESULT_OK, 8'd9, "recovered");
        check_rom_image(MENU);
        checks = checks + 1;
    endtask

    // A swap while a stepping host command runs: the command completes on the
    // engine's pause (STEP_LIMIT / STOPPED), the swap proceeds and the host
    // pause the step leaves behind keeps the console paused afterwards.
    task automatic fixture_swap_host;
        int edges;
        logic [31:0] epoch_before;
        // RUN_DOTS with a large budget from the paused console, then a select
        // from the menu it lets run.
        host_command(COMMAND_HALT);
        host_start(COMMAND_RUN_DOTS, WIRE_RUN_DOTS_MAX);
        epoch_before = epoch;
        cpu_write(16'h6000, 8'd1);
        edges = 0;
        while (!core_done) begin edge_cycle(); edges = edges + 1; if (edges > 2000) $fatal(1, "LOADER_TB_DOTS_NO_COMPLETION"); end
        if (run_dots_result.reason != WIRE_RUN_DOTS_STOPPED || !paused) $fatal(1, "LOADER_TB_DOTS_REASON reason=%0d paused=%b", run_dots_result.reason, paused);
        wait_copy(edges, SWAP_BOUND, "swap during RUN_DOTS");
        if (profile != PROFILE_DIRECT_ID || epoch != epoch_before + 1) $fatal(1, "LOADER_TB_DOTS_SWAP");
        repeat (300) edge_cycle();
        if (!paused) $fatal(1, "LOADER_TB_DOTS_HOST_PAUSE_LOST");
        host_command(COMMAND_RUN);
        if (paused) $fatal(1, "LOADER_TB_DOTS_RUN");
        check_rom_image(1);
        checks = checks + 1;
        // STEP with the maximum budget and no completing instruction, then the
        // menu return: STEP_LIMIT, the swap, and the console paused afterwards.
        host_command(COMMAND_HALT);
        host_start(COMMAND_STEP, WIRE_STEP_MAX_DOTS);
        wait_running();
        epoch_before = epoch;
        host_return = 1; edge_cycle(); host_return = 0;
        edges = 0;
        while (!core_done) begin edge_cycle(); edges = edges + 1; if (edges > 2000) $fatal(1, "LOADER_TB_STEP_NO_COMPLETION"); end
        if (core_status != STATUS_STEP_LIMIT || !paused) $fatal(1, "LOADER_TB_STEP_STATUS status=%0d", core_status);
        wait_copy(edges, SWAP_BOUND, "return during STEP");
        if (profile != PROFILE_LOADER_ID || epoch != epoch_before + 1) $fatal(1, "LOADER_TB_STEP_SWAP");
        repeat (300) edge_cycle();
        if (!paused) $fatal(1, "LOADER_TB_STEP_HOST_PAUSE_LOST");
        host_command(COMMAND_RUN);
        if (paused) $fatal(1, "LOADER_TB_STEP_RUN");
        swaps = swaps + 2;
        checks = checks + 1;
    endtask

    task automatic fixture_not_ready;
        // Before the controller initializes, both commits are refused NOT_READY.
        int edges;
        if (sdram_initialized) $fatal(1, "LOADER_TB_EARLY_INIT");
        cpu_write(16'h2000, 8'd1);
        #1;
        if (copy_busy) $fatal(1, "LOADER_TB_NOT_READY_FILL");
        expect_status(8'h00, LIBRARY_RESULT_NOT_READY, 8'hFF, "bank not ready");
        cpu_write(16'h6000, 8'd4);
        #1;
        if (copy_busy) $fatal(1, "LOADER_TB_NOT_READY_SWAP");
        expect_status(8'h00, LIBRARY_RESULT_NOT_READY, 8'd4, "select not ready");
        expect_read(16'hA001, 8'd0, "bank unchanged");
    endtask

    task automatic fixture_key1;
        int edges;
        logic [31:0] epoch_before;
        // A 4 ms glitch never changes the debounced level or the hold counter.
        press_key1(4 * MS);
        repeat (6 * MS) edge_cycle();
        if (library_key1 != 0 || copy_busy) $fatal(1, "LOADER_TB_KEY1_GLITCH hold=%0d", library_key1);
        checks = checks + 1;
        // 0.49 s: a debounced press, no return.
        press_key1(490 * MS);
        repeat (6 * MS) edge_cycle();
        if (copy_busy || library_status[15:8] != LIBRARY_RESULT_NONE) $fatal(1, "LOADER_TB_KEY1_SHORT");
        checks = checks + 1;
        // 0.51 s: exactly one return, at the debounce plus hold threshold;
        // holding on raises nothing more and the counter stays saturated.
        epoch_before = epoch;
        key1_n = 0;
        edges = 0;
        while (!copy_busy) begin
            edge_cycle(); edges = edges + 1;
            if (edges > 520 * MS) $fatal(1, "LOADER_TB_KEY1_NO_RETURN");
        end
        if (edges < DEBOUNCE + HOLD || edges > DEBOUNCE + HOLD + 8 || library_key1 != HOLD)
            $fatal(1, "LOADER_TB_KEY1_THRESHOLD edges=%0d hold=%0d", edges, library_key1);
        wait_copy(edges, SWAP_BOUND, "key1 return");
        if (profile != PROFILE_LOADER_ID || epoch != epoch_before + 1) $fatal(1, "LOADER_TB_KEY1_SWAP");
        repeat (100 * MS) edge_cycle();
        if (copy_busy || epoch != epoch_before + 1 || library_key1 != HOLD) $fatal(1, "LOADER_TB_KEY1_REPEAT epoch=%0d", epoch);
        key1_n = 1;
        repeat (6 * MS) edge_cycle();
        if (library_key1 != 0) $fatal(1, "LOADER_TB_KEY1_RELEASE");
        checks = checks + 1;
    endtask

    // Ordering cases with shortened thresholds: the return queued behind a
    // swap, dropped in a host session, and repeated after a release.
    task automatic fixture_key1_queue;
        int edges;
        logic [31:0] epoch_before;
        // Press, then commit a select so the threshold lands inside the swap:
        // key1_pending, then the menu swap follows the game swap.
        key1_n = 0;
        repeat (DEBOUNCE + HOLD - 2000) edge_cycle();
        cpu_write(16'h6000, 8'd2);
        edges = 0;
        while (!library_status[4]) begin
            edge_cycle(); edges = edges + 1;
            if (!copy_busy) $fatal(1, "LOADER_TB_KEY1_PENDING_MISSED");
            if (edges > 4000) $fatal(1, "LOADER_TB_KEY1_NO_PENDING");
        end
        checks = checks + 1;
        // The game swap completes first, then the queued return swaps the menu;
        // the loader stays busy in between, and the held key raises no more.
        edges = 0;
        while (profile != PROFILE_DIRECT_ID) begin
            edge_cycle(); edges = edges + 1;
            if (edges > SWAP_BOUND) $fatal(1, "LOADER_TB_KEY1_GAME_SWAP");
        end
        if (!copy_busy || !library_status[4]) $fatal(1, "LOADER_TB_KEY1_PENDING_HELD");
        wait_copy(edges, 2 * SWAP_BOUND, "queued return");
        if (profile != PROFILE_LOADER_ID || library_status[23:16] != 8'd2 || library_status[4])
            $fatal(1, "LOADER_TB_KEY1_PENDING_SWAP status=%08h", library_status);
        repeat (HOLD + 2000) edge_cycle();
        if (copy_busy) $fatal(1, "LOADER_TB_KEY1_HELD_REPEAT");
        key1_n = 1;
        repeat (DEBOUNCE + 100) edge_cycle();
        checks = checks + 1;
        // In a host session the return is dropped and nothing is queued.
        while (paused) edge_cycle();
        host_session = 1;
        press_key1(DEBOUNCE + HOLD + 2000);
        repeat (DEBOUNCE + 100) edge_cycle();
        if (copy_busy || library_status[4]) $fatal(1, "LOADER_TB_KEY1_SESSION");
        host_session = 0;
        checks = checks + 1;
        // Release and press again: a fresh count and a second return.
        epoch_before = epoch;
        press_key1(DEBOUNCE + HOLD + 2000);
        wait_copy(edges, SWAP_BOUND, "second return");
        if (epoch != epoch_before + 1) $fatal(1, "LOADER_TB_KEY1_SECOND");
        checks = checks + 1;
        // A return on the very edge the engine finishes a swap starts the menu
        // swap directly and leaves nothing pending.
        while (paused) edge_cycle();
        epoch_before = epoch;
        cpu_write(16'h6000, 8'd4);
        while (!dut.engine_done) edge_cycle();
        host_return = 1; edge_cycle(); host_return = 0;
        #1;
        if (!copy_busy || library_status[4]) $fatal(1, "LOADER_TB_KEY1_DONE_EDGE busy=%b pending=%b", copy_busy, library_status[4]);
        wait_copy(edges, SWAP_BOUND, "done-edge return");
        if (profile != PROFILE_LOADER_ID || epoch != epoch_before + 2 || library_status[4]) $fatal(1, "LOADER_TB_KEY1_DONE_EDGE_SWAP");
        checks = checks + 1;
    endtask

    initial begin
        clk_sys = 0; reset_sys = 1; sdram_reset = 0; key1_n = 1; host_session = 0; host_port_busy = 0; host_return = 0;
        request_valid = 0; write_enable = 0; bus_commit = 0; address = 0; write_data = 0;
        core_start = 0; core_command = 0; core_budget = 32'd1; host_sdram_valid = 0; host_sdram_write = 0;
        host_sdram_address = 0; host_sdram_data = 0;
        profile = PROFILE_LOADER_ID; image_valid = 1;
        checks = 0; engine_writes = 0; swaps = 0; fills = 0; invalid_writes = 0; saw_invalid_write = 0;
        if (!$value$plusargs("fixture=%s", fixture)) fixture = "window";
        build_library();
        // The real-timing KEY1 fixture simulates over a second; its wave dump
        // would dominate the wall budget, so it keeps the FST trace only.
        if (fixture != "key1") begin
            $dumpfile("waves.vcd");
            $dumpvars(0, reset_sys, profile, image_valid, paused, copy_busy, swap_busy, window_busy,
                library_status, library_key1, epoch, address, cpu_read_data, bus_commit, rom_host_write,
                sdram_request_valid, sdram_request_ready, sdram_response_valid, key1_n);
        end
        // The fault fixture holds the SDRAM in reset past memory initialization
        // so the NOT_READY refusals are observable through the CPU port.
        if (fixture == "swap-fault") sdram_reset = 1;
        repeat (5) edge_cycle();
        reset_sys = 0;
        while (!init_done) edge_cycle();
        // The host releases its power-up pause, as after LOAD_END and RUN.
        host_command(COMMAND_RUN);
        if (paused) $fatal(1, "LOADER_TB_RUN");
        if (fixture == "swap-fault") fixture_not_ready();
        sdram_reset = 0;
        repeat (3) edge_cycle();
        preload_library();
        while (!sdram_initialized) edge_cycle();
        repeat (4) edge_cycle();
        case (fixture)
            "map": fixture_map();
            "window": fixture_window();
            "swap": fixture_swap();
            "swap-fault": fixture_swap_fault();
            "key1": fixture_key1();
            "key1-queue": fixture_key1_queue();
            "swap-host": fixture_swap_host();
            default: $fatal(1, "LOADER_TB_FIXTURE %s", fixture);
        endcase
        if (contract_fault) $fatal(1, "LOADER_TB_CPU_PORT_FAULT");
        $display("PASS loader-%s checks=%0d swaps=%0d fills=%0d engine_writes=%0d", fixture, checks, swaps, fills, engine_writes);
        $finish;
    end
    // 4 s of simulated time covers the KEY1 fixture's real 0.5 s presses.
    initial begin #4000000000; $fatal(1, "LOADER_TB_WATCHDOG"); end
endmodule
`default_nettype wire

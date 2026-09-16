`timescale 1ns/1ps
`default_nettype none
// MBC1 profile fixtures against the real memory owner and CPU port, with a
// bus driver in place of the CPU and the fixture driving the ROM host port.
// Contract: wiki/src/rtl/cartridge/MAS_mbc1_profile.md#verification.
// Test plan: README.md. One fixture per run, selected with +fixture=<name>:
// map, bank, reset, fault. Expectations come from the contract and the
// fixture's own 64 KiB signature image, never from DUT state: every bank
// carries its own byte pattern, so a wrong bank is a byte mismatch.
// Lint waiver: integer arithmetic on byte and address values.
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
module tb_mbc1;
    import n2m_interfaces_pkg::*;
    localparam int IMAGE = 65536;
    localparam int BANK = 16384;
    localparam int BANKS = 4;

    logic clk_sys, reset_sys, core_reset;
    logic [7:0] profile;
    // Memory owner and CPU port.
    logic init_done, request_valid, write_enable, bus_commit, response_valid, contract_fault;
    logic [15:0] address;
    logic [7:0] write_data, cpu_read_data;
    logic storage_read, storage_write, storage_valid;
    n2m_memory_pkg::memory_store_t storage_store;
    logic [14:0] storage_offset;
    logic [15:0] store_offset;
    logic [7:0] storage_wdata, storage_rdata;
    logic owner_prepare, owner_commit, owner_write;
    logic [15:0] owner_address;
    logic [7:0] owner_wdata;
    n2m_memory_pkg::memory_destination_t owner_destination;
    // ROM host port, driven by the fixture as the UART load owner would.
    logic rom_host_write, rom_host_read, rom_host_valid;
    logic [31:0] rom_host_offset;
    logic [7:0] rom_host_wdata, rom_host_rdata;
    // Fixture bookkeeping.
    string fixture;
    int checks, reads, image_seed;
    bit wrong_reference;

    n2m_mbc1 dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .profile(profile),
        .rom_commit(storage_write && storage_store == n2m_memory_pkg::STORE_ROM),
        .commit_offset(storage_offset), .commit_data(storage_wdata),
        .access_store(storage_store), .access_offset(storage_offset), .store_offset(store_offset)
    );
    n2m_memory_cpu_port u_port (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .init_done(init_done),
        .request_valid(request_valid), .address(address), .write_enable(write_enable),
        .write_data(write_data), .bus_commit(bus_commit), .read_data(cpu_read_data),
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
        .access_address(store_offset), .access_wdata(storage_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(rom_host_read), .host_write(rom_host_write), .host_offset(rom_host_offset),
        .host_wdata(rom_host_wdata), .host_rdata(rom_host_rdata), .host_valid(rom_host_valid),
        .core_paused(1'b0), .oam_sequence_active(1'b0), .peek_ready(), .peek_read(1'b0),
        .peek_select(8'd0), .peek_offset(13'd0), .peek_rdata(), .peek_valid(),
        .ppu_vram_read(1'b0), .ppu_vram_address(13'd0), .ppu_vram_rdata(), .ppu_vram_valid(),
        .ppu_oam_read(1'b0), .ppu_oam_pair(7'd0), .ppu_oam_rdata(), .ppu_oam_valid(),
        .wave_read(1'b0), .wave_write(1'b0), .wave_address(4'd0), .wave_wdata(8'd0), .wave_rdata(), .wave_valid()
    );
    always #20 clk_sys = !clk_sys;

    // The signature image: bank b, bank offset k. The XOR constant differs per
    // bank, so the same k reads differently in every bank; the seed lets the
    // reset fixture load a second, distinguishable image.
    function automatic logic [7:0] image_byte(input int seed, input int offset);
        int b, k;
        b = offset / BANK; k = offset % BANK;
        return 8'((k * 13 + (k >> 7) + seed * 101) ^ (8'h5A + b * 8'h41));
    endfunction
    // Contract: zero translation on the whole five-bit value, then the mask.
    function automatic int effective_bank(input logic [7:0] bank1_value);
        int five;
        five = int'(bank1_value[4:0]);
        return (five == 0 ? int'(MBC1_RESET_BANK) : five) & int'(MBC1_BANK_MASK);
    endfunction
    task automatic edge_cycle;
        @(negedge clk_sys);
    endtask
    task automatic host_load(input int seed);
        int offset;
        for (offset = 0; offset < IMAGE; offset = offset + 1) begin
            rom_host_offset = offset; rom_host_wdata = image_byte(seed, offset); rom_host_write = 1;
            edge_cycle();
        end
        rom_host_write = 0; rom_host_offset = 0;
        edge_cycle();
    endtask
    task automatic cpu_write(input logic [15:0] target, input logic [7:0] value);
        address = target; write_data = value; write_enable = 1; request_valid = 1;
        repeat (3) edge_cycle();
        bus_commit = 1;
        edge_cycle();
        bus_commit = 0; request_valid = 0; write_enable = 0;
    endtask
    task automatic cpu_read(output logic [7:0] value, input logic [15:0] target);
        address = target; write_enable = 0; request_valid = 1;
        edge_cycle();
        #1;
        if (!response_valid) $fatal(1, "MBC1_TB_NO_RESPONSE address=%04h", target);
        value = cpu_read_data;
        bus_commit = 1;
        edge_cycle();
        bus_commit = 0; request_valid = 0;
        reads = reads + 1;
    endtask
    task automatic expect_read(input logic [15:0] target, input logic [7:0] expected, input string what);
        logic [7:0] actual;
        cpu_read(actual, target);
        if (actual != expected)
            $fatal(1, "MBC1_TB_READ %s address=%04h expected=%02h actual=%02h", what, target, expected, actual);
    endtask
    // The whole fixed window is bank 0; the whole switched window is `bank`.
    task automatic check_windows(input int seed, input int bank, input string what);
        int offset;
        for (offset = 0; offset < 2 * BANK; offset = offset + 1)
            expect_read(16'(offset), image_byte(seed, offset < BANK ? offset : bank * BANK + (offset - BANK)), what);
        checks = checks + 1;
    endtask
    // A spread sample of both windows: both ends, each 1 KiB boundary and a
    // stride through the bank. The reference bank comes from the contract.
    task automatic sample_windows(input int seed, input logic [7:0] bank1_value, input string what);
        int bank, k, step;
        bank = effective_bank(bank1_value);
        if (wrong_reference) bank = (bank + 1) % BANKS;
        for (step = 0; step < 64; step = step + 1) begin
            k = step < 16 ? step * 1024 : (step < 32 ? (step - 16) * 1024 + 1023 : (step - 32) * 509 + 3);
            expect_read(16'(k), image_byte(seed, k), what);
            expect_read(16'(BANK + k), image_byte(seed, bank * BANK + k), what);
        end
        expect_read(16'h7FFF, image_byte(seed, bank * BANK + BANK - 1), what);
        checks = checks + 1;
    endtask

    // All 65,536 addresses after reset: bank 0 below $4000, bank 1 above, $FF
    // cartridge RAM; then the same bytes read as the identity in DIRECT_ID
    // where a BANK1 write changes nothing.
    task automatic fixture_map;
        int target;
        logic [7:0] value;
        check_windows(1, 1, "reset map");
        for (target = 16'hA000; target <= 16'hBFFF; target = target + 1) expect_read(16'(target), 8'hFF, "cartridge RAM");
        checks = checks + 1;
        cpu_write(16'h0000, 8'h0A);
        cpu_write(16'h1FFF, 8'h0A);
        cpu_write(16'hA000, 8'h33);
        cpu_write(16'hBFFF, 8'hCC);
        for (target = 16'hA000; target <= 16'hBFFF; target = target + 1) expect_read(16'(target), 8'hFF, "RAMG ignored");
        checks = checks + 1;
        // The other windows of the CPU map still route: WRAM round trip.
        cpu_write(16'hC123, 8'h77);
        expect_read(16'hC123, 8'h77, "WRAM");
        checks = checks + 1;
        profile = PROFILE_DIRECT_ID;
        cpu_write(16'h2000, 8'h03);
        cpu_write(16'h3FFF, 8'h02);
        for (target = 0; target < 2 * BANK; target = target + 1) expect_read(16'(target), image_byte(1, target), "direct identity");
        checks = checks + 1;
        profile = PROFILE_LOADER_ID;
        for (target = 0; target < 2 * BANK; target = target + 1) expect_read(16'(target), image_byte(1, target), "loader identity");
        checks = checks + 1;
        profile = PROFILE_MBC1_ID;
        // Returning to the profile: the registers were never written here.
        check_windows(1, 1, "back in MBC1_ID");
    endtask
    // BANK1 values 0-63 through both ends of the alias range; BANK2, MODE and
    // RAMG values change nothing; the read after the commit sees the bank.
    task automatic fixture_bank;
        int value;
        logic [7:0] byte_value;
        for (value = 0; value < 64; value = value + 1) begin
            cpu_write(value[0] ? 16'h3FFF : 16'h2000, 8'(value));
            sample_windows(1, 8'(value), "BANK1 sweep");
        end
        cpu_write(16'h2ABC, 8'hE3);
        sample_windows(1, 8'hE3, "high data bits");
        cpu_write(16'h2000, 8'h02);
        for (value = 0; value < 4; value = value + 1) begin
            cpu_write(value[0] ? 16'h5FFF : 16'h4000, 8'(value));
            sample_windows(1, 8'h02, "BANK2 without effect");
        end
        cpu_write(16'h6000, 8'h01);
        sample_windows(1, 8'h02, "MODE 1 without effect");
        cpu_write(16'h7FFF, 8'h00);
        sample_windows(1, 8'h02, "MODE 0 without effect");
        cpu_write(16'h6000, LIBRARY_GAME_EXIT_VALUE);
        sample_windows(1, 8'h02, "exit value leaves the bank");
        cpu_write(16'h0000, 8'h0A);
        cpu_write(16'h1FFF, 8'h00);
        sample_windows(1, 8'h02, "RAMG without effect");
        // A whole-bank check of each bank closes the sweep.
        for (value = 0; value < BANKS; value = value + 1) begin
            cpu_write(16'h2000, 8'(value));
            check_windows(1, effective_bank(8'(value)), "whole bank");
        end
        // The commit and a switched read on consecutive edges.
        cpu_write(16'h2000, 8'h03);
        expect_read(16'h4000, image_byte(1, 3 * BANK), "next read after commit");
        cpu_write(16'h2000, 8'h01);
        expect_read(16'h4000, image_byte(1, 1 * BANK), "next read after commit");
        checks = checks + 1;
    endtask
    // Bank 3 selected, then a core reset: bank 1 at the first read and the
    // store retained; then a fresh image replaces every byte.
    task automatic fixture_reset;
        cpu_write(16'h3000, 8'h03);
        cpu_write(16'h4000, 8'h03);
        cpu_write(16'h6000, 8'h01);
        sample_windows(1, 8'h03, "before reset");
        core_reset = 1; edge_cycle(); core_reset = 0;
        while (!init_done) edge_cycle();
        check_windows(1, 1, "after core reset");
        cpu_write(16'h2000, 8'h02);
        sample_windows(1, 8'h02, "bank 2 after reset");
        host_load(2);
        core_reset = 1; edge_cycle(); core_reset = 0;
        while (!init_done) edge_cycle();
        check_windows(2, 1, "second image");
        cpu_write(16'h2000, 8'h03);
        check_windows(2, 3, "second image bank 3");
    endtask

    initial begin
        clk_sys = 0; reset_sys = 1; core_reset = 0; profile = PROFILE_MBC1_ID;
        request_valid = 0; write_enable = 0; bus_commit = 0; address = 0; write_data = 0;
        rom_host_write = 0; rom_host_read = 0; rom_host_offset = 0; rom_host_wdata = 0;
        checks = 0; reads = 0; wrong_reference = 0;
        if (!$value$plusargs("fixture=%s", fixture)) fixture = "bank";
        $dumpfile("waves.vcd");
        $dumpvars(0, reset_sys, core_reset, profile, address, cpu_read_data, bus_commit, storage_offset, store_offset,
            rom_host_write, rom_host_offset);
        repeat (5) edge_cycle();
        reset_sys = 0;
        while (!init_done) edge_cycle();
        host_load(1);
        // LOAD_END resets the core into the profile: registers zero, bank 1.
        core_reset = 1; edge_cycle(); core_reset = 0;
        while (!init_done) edge_cycle();
        case (fixture)
            "map": fixture_map();
            "bank": fixture_bank();
            "reset": fixture_reset();
            // The deliberate fault: the reference names the wrong bank, so the
            // first switched-window sample must fail with expected/actual bytes.
            "fault": begin wrong_reference = 1; fixture_bank(); end
            default: $fatal(1, "MBC1_TB_FIXTURE %s", fixture);
        endcase
        if (contract_fault) $fatal(1, "MBC1_TB_CPU_PORT_FAULT");
        $display("PASS mbc1-%s checks=%0d reads=%0d", fixture, checks, reads);
        $finish;
    end
    initial begin #200000000; $fatal(1, "MBC1_TB_WATCHDOG"); end
endmodule
`default_nettype wire

`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_memory_service;
    logic clk_sys, reset_sys, core_reset, init_done;
    logic request_valid, write_enable, bus_commit, response_valid, contract_fault;
    logic [15:0] address, owner_address;
    logic [7:0] write_data, read_data, storage_wdata, storage_rdata, owner_wdata, owner_rdata;
    logic storage_read, storage_write, storage_valid;
    n2m_memory_pkg::memory_store_t storage_store, resolved_store;
    logic [14:0] storage_offset, resolved_offset;
    logic owner_prepare, owner_commit, owner_write, owner_valid, owner_service_available;
    n2m_memory_pkg::memory_destination_t owner_destination;
    logic policy_blocked, policy_ram, policy_read, policy_write, previous_owner;
    logic [15:0] previous_owner_address;
    logic [7:0] resolved_wdata;
    logic ppu_vram_read, ppu_vram_valid, ppu_oam_read, ppu_oam_valid;
    logic [12:0] ppu_vram_address;
    logic [6:0] ppu_oam_pair;
    logic [7:0] ppu_vram_rdata, expected_vram, unused_host, unused_wave;
    logic [15:0] ppu_oam_rdata, expected_oam;
    logic unused_host_valid, unused_wave_valid;
    bit observe_ppu, previous_vram, previous_oam, corrupt_response;
    integer index, writes, ppu_checks, before_writes;
    n2m_memory_cpu_port dut (.*);

    // Synthetic selected-policy adapter: explicit test of the external132
    // boundary, not a DMA engine or transition-edge arbitration implementation.
    assign policy_ram = owner_destination == n2m_memory_pkg::MEMORY_VRAM || owner_destination == n2m_memory_pkg::MEMORY_OAM;
    assign owner_service_available = policy_ram || owner_destination == n2m_memory_pkg::MEMORY_UNUSABLE;
    assign policy_read = owner_prepare && !owner_write && policy_ram && !policy_blocked;
    assign policy_write = owner_commit && owner_write && policy_ram && !policy_blocked;
    assign owner_rdata = policy_blocked ? 8'hFF :
        (owner_destination == n2m_memory_pkg::MEMORY_UNUSABLE ? 8'h00 : storage_rdata);
    assign owner_valid = owner_prepare && !owner_write &&
        (policy_blocked || owner_destination == n2m_memory_pkg::MEMORY_UNUSABLE ||
         (previous_owner && previous_owner_address == owner_address && storage_valid));
    `DFF_ARST_VAL(previous_owner, policy_read, clk_sys, reset_sys, 1'b0)
    `DFF_EN(previous_owner_address, owner_address, clk_sys, policy_read)
    assign resolved_store = owner_prepare ?
        (owner_destination == n2m_memory_pkg::MEMORY_VRAM ? n2m_memory_pkg::STORE_VRAM : n2m_memory_pkg::STORE_OAM) : storage_store;
    assign resolved_offset = owner_prepare ? (owner_destination == n2m_memory_pkg::MEMORY_VRAM
        ? {2'b0, owner_address[12:0]} : {7'b0, owner_address[7:0]}) : storage_offset;
    assign resolved_wdata = owner_prepare ? owner_wdata : storage_wdata;

    n2m_memory_stores stores (.oam_request('0), .oam_response(),
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .init_done(init_done),
        .access_read(storage_read || policy_read), .access_write(storage_write || policy_write),
        .access_store(resolved_store), .access_address(resolved_offset), .access_wdata(resolved_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(1'b0), .host_write(1'b0), .host_offset(32'd0), .host_wdata(8'd0),
        .host_rdata(unused_host), .host_valid(unused_host_valid),
        .ppu_vram_read(ppu_vram_read), .ppu_vram_address(ppu_vram_address),
        .ppu_vram_rdata(ppu_vram_rdata), .ppu_vram_valid(ppu_vram_valid),
        .ppu_oam_read(ppu_oam_read), .ppu_oam_pair(ppu_oam_pair),
        .ppu_oam_rdata(ppu_oam_rdata), .ppu_oam_valid(ppu_oam_valid),
        .wave_read(1'b0), .wave_address(4'd0), .wave_rdata(unused_wave), .wave_valid(unused_wave_valid)
    );

    task automatic edge_cycle;
        #4;
        // This is the pre-A observation: data must still belong to the prior
        // request even though the next request's address has already changed.
        if (observe_ppu) begin
            if (ppu_vram_valid !== previous_vram || ppu_oam_valid !== previous_oam)
                $fatal(1, "MEMORY_SERVICE_PPU_VALID");
            if (previous_vram && ppu_vram_rdata !== expected_vram)
                $fatal(1, "MEMORY_SERVICE_VRAM_PRE_A expected=%02h actual=%02h", expected_vram, ppu_vram_rdata);
            if (previous_oam && ppu_oam_rdata !== expected_oam)
                $fatal(1, "MEMORY_SERVICE_OAM_PRE_A expected=%04h actual=%04h", expected_oam, ppu_oam_rdata);
            if (previous_vram && previous_oam) ppu_checks = ppu_checks + 1;
        end
        if ((storage_write || policy_write) && !bus_commit) $fatal(1, "MEMORY_SERVICE_UNCOMMITTED_WRITE");
        if (storage_write && policy_write) $fatal(1, "MEMORY_SERVICE_TWO_WRITERS");
        if (storage_write || policy_write) writes = writes + 1;
        expected_vram = 8'(int'(ppu_vram_address) ^ 'h96);
        expected_oam = {8'((int'(ppu_oam_pair) * 2 + 1) ^ 'h69), 8'((int'(ppu_oam_pair) * 2) ^ 'h69)};
        previous_vram = ppu_vram_read;
        previous_oam = ppu_oam_read;
        clk_sys = 1;
        #1;
        clk_sys = 0;
    endtask

    task automatic write_byte(input logic [15:0] target, input logic [7:0] value);
        address = target; write_data = value; write_enable = 1; request_valid = 1;
        bus_commit = 0; edge_cycle();
        bus_commit = 1; edge_cycle(); bus_commit = 0;
    endtask
    task automatic read_byte(input logic [15:0] target, input logic [7:0] value);
        address = target; write_enable = 0; request_valid = 1;
        edge_cycle();
        if (!response_valid || read_data !== value)
            $fatal(1, "MEMORY_SERVICE_CPU_READ address=%04h expected=%02h actual=%02h", target, value, read_data);
        bus_commit = 1; edge_cycle(); bus_commit = 0;
    endtask

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, init_done, request_valid, address, write_enable, write_data,
                  bus_commit, read_data, response_valid, owner_destination, owner_prepare,
                  owner_commit, policy_blocked, policy_read, policy_write, resolved_store,
                  resolved_offset, ppu_vram_read, ppu_vram_address, ppu_vram_rdata,
                  ppu_vram_valid, ppu_oam_read, ppu_oam_pair, ppu_oam_rdata, ppu_oam_valid,
                  expected_vram, expected_oam);
        clk_sys = 0; reset_sys = 1; core_reset = 0; request_valid = 0;
        address = 0; write_enable = 0; write_data = 0; bus_commit = 0; policy_blocked = 0;
        ppu_vram_read = 0; ppu_oam_read = 0; ppu_vram_address = 0; ppu_oam_pair = 0;
        observe_ppu = 0; previous_vram = 0; previous_oam = 0;
        expected_vram = 0; expected_oam = 0; writes = 0; ppu_checks = 0;
        corrupt_response = $test$plusargs("corrupt_response");
        edge_cycle(); reset_sys = 0;
        repeat (8192) edge_cycle();
        if (!init_done) $fatal(1, "MEMORY_SERVICE_INIT");
        for (index = 0; index < 64; index = index + 1)
            write_byte(16'('h8000 + index), 8'(index ^ 'h96));
        for (index = 0; index < 160; index = index + 1)
            write_byte(16'('hFE00 + index), 8'(index ^ 'h69));
        if (writes != 224) $fatal(1, "MEMORY_SERVICE_LOAD_COUNT");
        ppu_vram_read = 1; ppu_oam_read = 1; observe_ppu = 1;
        for (index = 0; index < 128; index = index + 1) begin
            ppu_vram_address = 13'(index % 64); ppu_oam_pair = 7'(index % 80);
            if (corrupt_response && index == 7) force stores.ppu_vram_rdata = 8'h00;
            write_byte(16'('hC000 + index), 8'(index ^ 'hD3));
            read_byte(16'('hE000 + index), 8'(index ^ 'hD3));
            read_byte(16'('h8000 + (index % 64)), 8'((index % 64) ^ 'h96));
            read_byte(16'('hFE00 + (index % 160)), 8'((index % 160) ^ 'h69));
        end
        before_writes = writes;
        policy_blocked = 1;
        write_byte(16'h8005, 8'h00); write_byte(16'hFE06, 8'h00);
        read_byte(16'h8005, 8'hFF); read_byte(16'hFE06, 8'hFF); read_byte(16'hFEA0, 8'hFF);
        if (writes != before_writes) $fatal(1, "MEMORY_SERVICE_BLOCKED_WRITE");
        policy_blocked = 0;
        read_byte(16'h8005, 8'h93); read_byte(16'hFE06, 8'h6F); read_byte(16'hFEFF, 8'h00);
        ppu_vram_read = 0; ppu_oam_read = 0;
        edge_cycle(); edge_cycle();
        if (writes != 352 || ppu_checks != 1040 || contract_fault) $fatal(1, "MEMORY_SERVICE_COUNTS writes=%0d pairs=%0d", writes, ppu_checks);
        $display("PASS memory concurrent CPU PPU writes=352 preA_pairs=1040 blocked unusable");
        $finish;
    end
    initial begin
        #200000;
        $fatal(1, "MEMORY_SERVICE_WATCHDOG");
    end
endmodule

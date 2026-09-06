`timescale 1ns/1ps
`default_nettype none
module tb_memory_cpu_port;
    import n2m_memory_pkg::*;
    logic clk_sys, reset_sys, core_reset, init_done;
    logic request_valid, write_enable, bus_commit, response_valid, contract_fault;
    logic [15:0] address, owner_address;
    logic [7:0] write_data, read_data, storage_wdata, storage_rdata, owner_wdata, owner_rdata;
    logic storage_read, storage_write, storage_valid;
    memory_store_t storage_store;
    logic [14:0] storage_offset;
    logic owner_prepare, owner_commit, owner_write, owner_valid, owner_service_available;
    memory_destination_t owner_destination;
    logic [7:0] host_rdata, unused_vram, unused_wave;
    logic [15:0] unused_oam;
    logic host_valid, unused_vram_valid, unused_oam_valid, unused_wave_valid;
    logic host_write, host_read;
    logic [31:0] host_offset;
    logic [7:0] host_wdata;
    integer index, phase, writes, owner_commits, fixed_reads, reset_phase, direction, reset_kind;
    bit duplicate_fault, missing_fault, write_fault, endpoint_loading;
    n2m_memory_cpu_port dut (.*);
    n2m_memory_stores stores (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .init_done(init_done),
        .access_read(storage_read), .access_write(storage_write), .access_store(storage_store),
        .access_address(storage_offset), .access_wdata(storage_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(host_read), .host_write(host_write), .host_offset(host_offset), .host_wdata(host_wdata),
        .host_rdata(host_rdata), .host_valid(host_valid),
        .ppu_vram_read(1'b0), .ppu_vram_address(13'd0), .ppu_vram_rdata(unused_vram), .ppu_vram_valid(unused_vram_valid),
        .ppu_oam_read(1'b0), .ppu_oam_pair(7'd0), .ppu_oam_rdata(unused_oam), .ppu_oam_valid(unused_oam_valid),
        .wave_read(1'b0), .wave_address(4'd0), .wave_rdata(unused_wave), .wave_valid(unused_wave_valid)
    );

    task automatic edge_cycle;
        #4;
        if (endpoint_loading && (request_valid || bus_commit || storage_write || owner_commit))
            $fatal(1, "MEMORY_CPU_LOAD_PROGRESS");
        // Observe effects before the edge independently of DUT state.
        if (storage_write) begin
            if (!bus_commit || !request_valid || !write_enable || !init_done)
                $fatal(1, "MEMORY_CPU_DUPLICATE_WRITE");
            writes = writes + 1;
        end
        if (owner_commit) begin
            if (!bus_commit || !owner_prepare || !owner_service_available || (!write_enable && !response_valid))
                $fatal(1, "MEMORY_CPU_OWNER_COMMIT");
            owner_commits = owner_commits + 1;
        end
        clk_sys = 1;
        #1;
        clk_sys = 0;
    endtask

    task automatic initialize;
        index = 0;
        while (!init_done && index < 8193) begin
            if (storage_read || storage_write || owner_prepare || response_valid)
                $fatal(1, "MEMORY_CPU_INIT_LEAK");
            edge_cycle();
            index = index + 1;
        end
        if (!init_done || index != 8192) $fatal(1, "MEMORY_CPU_INIT_BOUND");
    endtask

    task automatic write_byte(input logic [15:0] target, input logic [7:0] value);
        address = target; write_data = value; write_enable = 1; request_valid = 1;
        for (phase = 0; phase < 4; phase = phase + 1) begin
            // Three held system edges per T-state model a pause without commit.
            repeat (3) begin
                edge_cycle();
                if (storage_write || owner_commit) $fatal(1, "MEMORY_CPU_PREPARE_EFFECT");
            end
            bus_commit = phase == 3;
            edge_cycle();
            bus_commit = 0;
        end
    endtask

    task automatic read_byte(input logic [15:0] target, input logic [7:0] value);
        address = target; write_enable = 0; request_valid = 1;
        #1;
        edge_cycle();
        if (!response_valid || read_data !== value) $fatal(1, "MEMORY_CPU_READ address=%04h expected=%02h actual=%02h", target, value, read_data);
        // Sleeping/HALT-style preparation has no commit and can refresh data.
        repeat (4) edge_cycle();
        bus_commit = 1; edge_cycle(); bus_commit = 0;
    endtask

    task automatic reset_prepared(input bit writing, input integer cancel_phase, input bit global_reset);
        integer current_phase, before_writes, before_owners;
        before_writes = writes; before_owners = owner_commits;
        address = 16'hC123; write_enable = writing; write_data = 8'h7E;
        request_valid = 1; bus_commit = 0;
        edge_cycle();
        for (current_phase = 0; current_phase <= cancel_phase; current_phase = current_phase + 1) begin
            repeat (3) edge_cycle();
            if (writes != before_writes || owner_commits != before_owners)
                $fatal(1, "MEMORY_CPU_PHASE_PAUSE_EFFECT phase=%0d", current_phase);
            if (current_phase == cancel_phase) begin
                // At T4, reset wins over a coincident accepted-commit input.
                // At earlier T states it cancels the already prepared read.
                bus_commit = current_phase == 3;
                if (global_reset) reset_sys = 1;
                else core_reset = 1;
                #1;
                if (response_valid || storage_read || storage_write || owner_prepare || owner_commit)
                    $fatal(1, "MEMORY_CPU_PHASE_RESET_CANCEL phase=%0d write=%0d", current_phase, writing);
            end
            edge_cycle();
        end
        bus_commit = 0; core_reset = 0; reset_sys = 0;
        initialize();
        read_byte(16'hC123, 8'h00);
        if (writes != before_writes || owner_commits != before_owners || contract_fault)
            $fatal(1, "MEMORY_CPU_PHASE_RESET_EFFECT phase=%0d write=%0d", cancel_phase, writing);
    endtask

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, init_done, request_valid, address,
                  write_enable, write_data, bus_commit, read_data, response_valid,
                  storage_read, storage_write, storage_offset, storage_rdata, storage_valid,
                  owner_prepare, owner_commit, owner_destination, owner_rdata, owner_valid,
                  owner_service_available, contract_fault, host_read, host_write, host_offset,
                  host_wdata, host_rdata, host_valid, endpoint_loading);
        clk_sys = 0; reset_sys = 1; core_reset = 0; request_valid = 0;
        address = 0; write_enable = 0; write_data = 0; bus_commit = 0;
        host_write = 0; host_read = 0; host_offset = 0; host_wdata = 0; endpoint_loading = 1;
        owner_rdata = 0; owner_valid = 0; owner_service_available = 0;
        writes = 0; owner_commits = 0; fixed_reads = 0;
        duplicate_fault = $test$plusargs("duplicate_fault");
        missing_fault = $test$plusargs("missing_fault");
        write_fault = $test$plusargs("write_fault");
        edge_cycle(); reset_sys = 0; initialize();
        // Model only endpoint91's stop/reset/load coordination, not its
        // framing, CRC, presence bitmap or command acceptance implementation.
        host_write = 1;
        for (index = 0; index < 17; index = index + 1) begin
            host_offset = 32'(index); host_wdata = 8'(index ^ 'h5A); edge_cycle();
        end
        host_write = 0; core_reset = 1; edge_cycle(); core_reset = 0;
        initialize();
        // Readback of bytes already loaded is legal before a complete image.
        host_read = 1; host_offset = 0; edge_cycle();
        if (!host_valid || host_rdata !== 8'h5A) $fatal(1, "MEMORY_CPU_PARTIAL_LOAD_FIRST");
        host_offset = 16; edge_cycle();
        if (!host_valid || host_rdata !== 8'h4A) $fatal(1, "MEMORY_CPU_PARTIAL_LOAD_LAST");
        host_read = 0; host_write = 1;
        for (index = 17; index < 32768; index = index + 1) begin
            host_offset = 32'(index); host_wdata = index == 'h123 ? 8'h5A : 8'(index ^ 'h5A); edge_cycle();
        end
        host_write = 0; host_read = 1; host_offset = 32767; edge_cycle();
        if (!host_valid || host_rdata !== 8'hA5) $fatal(1, "MEMORY_CPU_COMPLETE_LOAD_LAST");
        host_read = 0; endpoint_loading = 0;
        read_byte(16'h0123, 8'h5A);
        write_byte(16'h0123, 8'hC3);
        read_byte(16'h0123, 8'h5A);
        write_byte(16'hC000, 8'h13);
        write_byte(16'hDDFF, 8'h79);
        write_byte(16'hDFFF, 8'hAC);
        write_byte(16'hFF80, 8'h25);
        write_byte(16'hFFFE, 8'hE8);
        if (writes != 6) $fatal(1, "MEMORY_CPU_WRITE_COUNT");
        read_byte(16'hE000, 8'h13);
        read_byte(16'hFDFF, 8'h79);
        write_byte(16'hE000, 8'h62);
        read_byte(16'hC000, 8'h62);
        read_byte(16'hDFFF, 8'hAC);
        read_byte(16'hFF80, 8'h25);
        read_byte(16'hFFFE, 8'hE8);
        address = 16'hC001;
        #1;
        if (response_valid) $fatal(1, "MEMORY_CPU_STALE_ADDRESS");
        edge_cycle();
        if (!response_valid || read_data !== 0) $fatal(1, "MEMORY_CPU_NEW_ADDRESS");
        if (duplicate_fault) begin
            write_enable = 1;
            force dut.storage_write = 1'b1;
            edge_cycle();
            $fatal(1, "MEMORY_CPU_DUPLICATE_NOT_DETECTED");
        end
        // Enumerate the exact source-backed unused/boot table independently
        // of the DUT's destination enum. Known peripheral registers excluded.
        for (index = 'hFF00; index < 'hFF80; index = index + 1) begin
            if (index == 'hFF03 || (index >= 'hFF08 && index <= 'hFF0E)
                || index == 'hFF15 || index == 'hFF1F
                || (index >= 'hFF27 && index <= 'hFF2F) || index >= 'hFF4C) begin
                address = 16'(index); write_enable = 1; write_data = 8'(index); bus_commit = 1;
                #1;
                if (owner_prepare || owner_commit || storage_read || storage_write)
                    $fatal(1, "MEMORY_CPU_FIXED_WRITE_EFFECT address=%04h", address);
                edge_cycle(); bus_commit = 0; write_enable = 0;
                #1;
                if (!response_valid || read_data !== 8'hFF || owner_prepare || storage_read)
                    $fatal(1, "MEMORY_CPU_FIXED_READ address=%04h", address);
                bus_commit = 1; edge_cycle(); bus_commit = 0;
                fixed_reads = fixed_reads + 1;
            end
        end
        if (fixed_reads != 71 || contract_fault) $fatal(1, "MEMORY_CPU_FIXED_INVENTORY");
        // A synthetic selected-owner endpoint proves dispatch only. It is
        // not a timer, DMA or PPU implementation or its acceptance evidence.
        address = 16'hFF46; write_enable = 0; owner_service_available = 1; owner_valid = 1;
        owner_rdata = 8'h35; #1;
        if (owner_destination != MEMORY_DMA || !owner_prepare || !response_valid || read_data !== 8'h35)
            $fatal(1, "MEMORY_CPU_OWNER_PREPARE");
        owner_rdata = 8'hC7; #1;
        if (read_data !== 8'hC7) $fatal(1, "MEMORY_CPU_OWNER_PRE_T4");
        bus_commit = 1; edge_cycle(); bus_commit = 0;
        owner_valid = 0; #1;
        if (response_valid) $fatal(1, "MEMORY_CPU_MISSING_RESPONSE");
        if (missing_fault) begin
            bus_commit = 1; edge_cycle();
            $fatal(1, "MEMORY_CPU_MISSING_NOT_DETECTED");
        end
        if (write_fault) begin
            write_enable = 1; owner_service_available = 0; bus_commit = 1;
            #1;
            if (owner_commit || storage_write) $fatal(1, "MEMORY_CPU_UNAVAILABLE_WRITE_EFFECT");
            edge_cycle();
`ifdef SYNTHESIS
            if (!contract_fault || owner_prepare || response_valid || owner_commit || storage_write)
                $fatal(1, "MEMORY_CPU_STICKY_FAULT");
            owner_service_available = 1; owner_valid = 1;
            repeat (3) edge_cycle();
            address = 16'hC000;
            repeat (3) edge_cycle();
            if (!contract_fault || storage_read || storage_write || owner_prepare || response_valid || owner_commits != 1)
                $fatal(1, "MEMORY_CPU_POST_FAULT_EFFECT");
            bus_commit = 0; core_reset = 1; edge_cycle(); core_reset = 0;
            initialize();
            if (contract_fault) $fatal(1, "MEMORY_CPU_FAULT_RESET");
            read_byte(16'hC000, 8'h00);
            $display("PASS memory CPU synthesized sticky fault no same-edge or later effects reset");
            $finish;
`else
            $fatal(1, "MEMORY_CPU_WRITE_FAULT_NOT_DETECTED");
`endif
        end
        // CPU cancellation leaves commit low, without adding a retry here.
        edge_cycle();
        if (contract_fault || owner_commits != 1) $fatal(1, "MEMORY_CPU_CANCEL_EFFECT");
        owner_valid = 1; #1;
        core_reset = 1; #1;
        if (response_valid || owner_prepare || owner_commit || storage_write)
            $fatal(1, "MEMORY_CPU_RESET_CANCEL");
        edge_cycle(); core_reset = 0; initialize();
        read_byte(16'hC000, 8'h00);
        read_byte(16'hFFFE, 8'h00);
        for (reset_kind = 0; reset_kind < 2; reset_kind = reset_kind + 1)
            for (direction = 0; direction < 2; direction = direction + 1)
                for (reset_phase = 0; reset_phase < 4; reset_phase = reset_phase + 1)
                    reset_prepared(direction != 0, reset_phase, reset_kind != 0);
        if (writes != 7 || owner_commits != 1 || contract_fault) $fatal(1, "MEMORY_CPU_FINAL_COUNTS");
        $display("PASS memory CPU port writes=7 owner_commits=1 fixed_io=71 reset_phases=16 echo ROM stale pause");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1, "MEMORY_CPU_WATCHDOG");
    end
endmodule

`timescale 1ns/1ps
`default_nettype none
module tb_oam_late_write;
    logic clk_sys, reset_sys, core_reset, init_done;
    logic prepare, commit, late_window, busy, late_commit, fault;
    logic [15:0] address;
    logic [7:0] data;
    n2m_memory_pkg::memory_oam_request_t request;
    n2m_memory_pkg::memory_oam_response_t response;
    logic raw_read, raw_write, access_read, access_write, access_valid;
    logic [14:0] raw_address;
    logic [7:0] raw_data, access_rdata;
    logic ppu_read, ppu_read_allowed, ppu_valid;
    logic [6:0] ppu_pair;
    logic [15:0] ppu_data;
    integer checks, read_requests, index;
    logic [7:0] expected [0:159];

    n2m_oam_late_write dut (
        .clk_sys, .reset_sys, .core_reset, .prepare, .commit, .late_window,
        .address, .data, .ppu_read, .ppu_pair, .response, .request,
        .raw_oam_busy(busy), .late_commit, .ppu_read_allowed, .sequence_active(), .fault
    );
    assign access_read = raw_read && !busy;
    assign access_write = raw_write && !busy;
    n2m_memory_stores stores (
        .clk_sys, .reset_sys, .core_reset, .init_done,
        .access_read, .access_write, .access_store(n2m_memory_pkg::STORE_OAM),
        .access_address(raw_address), .access_wdata(raw_data), .access_rdata, .access_valid,
        .oam_request(request), .oam_response(response),
        .host_read(1'b0), .host_write(1'b0), .host_offset(32'd0), .host_wdata(8'd0),
        .host_rdata(), .host_valid(),
        .ppu_vram_read(1'b0), .ppu_vram_address(13'd0), .ppu_vram_rdata(), .ppu_vram_valid(),
        .ppu_oam_read(ppu_read_allowed), .ppu_oam_pair(ppu_pair),
        .ppu_oam_rdata(ppu_data), .ppu_oam_valid(ppu_valid),
        .wave_read(1'b0), .wave_write(1'b0), .wave_wdata(8'd0), .wave_address(4'd0), .wave_rdata(), .wave_valid()
    ,
        .core_paused(1'b0), .oam_sequence_active(1'b0), .peek_ready(), .peek_read(1'b0), .peek_select(8'd0), .peek_offset(13'd0),
        .peek_rdata(), .peek_valid());
    task automatic edge_cycle;
        #20; clk_sys = 1;
        #1;
        #19; clk_sys = 0;
    endtask
    always @(posedge clk_sys) if (request.read) read_requests = read_requests + 1;
    task automatic initialize;
        integer i;
        prepare = 0; commit = 0; late_window = 0;
        raw_read = 0; ppu_read = 0;
        for (i = 0; i < 160; i = i + 1) begin
            expected[i] = 8'(37*i+11);
            raw_address = 15'(i); raw_data = expected[i]; raw_write = 1;
            edge_cycle();
        end
        raw_write = 0;
    endtask
    task automatic inspect;
        integer i;
        raw_read = 1;
        for (i = 0; i < 160; i = i + 1) begin
            raw_address = 15'(i); edge_cycle();
            if (!access_valid || access_rdata !== expected[i])
                $fatal(1, "OAM_LATE_DATA byte=%0d expected=%02h actual=%02h", i, expected[i], access_rdata);
        end
        raw_read = 0; checks = checks + 1;
    endtask
    task automatic write_late(input logic [15:0] target, input logic [7:0] value);
        integer reads_before;
        reads_before = read_requests;
        address = target; data = value; prepare = 1;
        // Preparation runs while no emulated tick advances.
        repeat (12) edge_cycle();
        if (read_requests - reads_before != 5) $fatal(1, "OAM_LATE_FRESH_OPERANDS");
        ppu_pair = 78; ppu_read = 1; late_window = 1; commit = 1;
        #1;
        if (!late_commit || request.pair !== target[7:1] || request.write_enable !== 2'b11)
            $fatal(1, "OAM_LATE_T4");
        if (target[7:1] == 78 && ppu_read_allowed) $fatal(1, "OAM_LATE_COLLISION_GATE");
        if ($test$plusargs("collision")) force dut.ppu_read_allowed = 1'b1;
        edge_cycle();
        commit = 0; late_window = 0; prepare = 0;
        // A following raw read prepares immediately, before the drain ends.
        raw_read = 1; raw_address = {7'd0,target[7:0]};
        repeat (3) begin
            #1; if (access_read) $fatal(1, "OAM_LATE_RAW_DRAIN");
            edge_cycle();
        end
        edge_cycle(); // A+4 reread is complete before the A+5 capture.
        if (!ppu_valid || ppu_data !== {expected[157],expected[156]})
            $fatal(1, "OAM_LATE_CAPTURE expected=%04h actual=%04h", {expected[157],expected[156]}, ppu_data);
        if (!access_valid || access_rdata !== value) $fatal(1, "OAM_LATE_NEXT_READ");
        edge_cycle(); raw_read = 0; ppu_read = 0;
        if (fault) $fatal(1, "OAM_LATE_FAULT");
        checks = checks + 1;
    endtask
    initial begin
        $dumpfile("waves/oam-late.vcd");
        $dumpvars(0, tb_oam_late_write);
        clk_sys = 0; reset_sys = 1; core_reset = 0;
        prepare = 0; commit = 0; late_window = 0; address = 0; data = 0;
        raw_read = 0; raw_write = 0; raw_address = 0; raw_data = 0;
        ppu_read = 0; ppu_pair = 0; checks = 0; read_requests = 0;
        edge_cycle(); reset_sys = 0;
        repeat (8192) edge_cycle();
        if (!init_done) $fatal(1, "OAM_LATE_INIT");
        initialize(); expected[156] = 8'h81;
        write_late(16'hfe9c, 8'h81); inspect();
        initialize(); expected[157] = 8'h81;
        write_late(16'hfe9d, 8'h81); inspect();
        initialize();
        // Frozen independent conditional A0 projection, not DUT state.
        expected[32] = 8'h81; expected[33] = 8'h90;
        expected[34] = 8'h4d; expected[35] = 8'h72;
        expected[36] = 8'h97; expected[37] = 8'hbc;
        expected[38] = 8'he1; expected[39] = 8'h06;
        write_late(16'hfe20, 8'h81); inspect();
        write_late(16'hfe20, 8'h81); inspect();
        // Blocked ordinary commit does not create pair writes or change RAM.
        prepare = 1; address = 16'hfe20; data = 8'h22;
        repeat (12) edge_cycle(); commit = 1; late_window = 0;
        #1; if (busy || late_commit) $fatal(1, "OAM_LATE_BLOCKED");
        edge_cycle(); commit = 0; prepare = 0; inspect();
        // An ordinary allowed byte uses the unchanged raw port at its T4.
        prepare = 1; address = 16'hfe20; data = 8'h22;
        repeat (12) edge_cycle(); commit = 1;
        raw_write = 1; raw_address = 15'h20; raw_data = 8'h22;
        edge_cycle(); raw_write = 0; commit = 0; prepare = 0;
        expected[32] = 8'h22; inspect();
        // Reset after A cancels the drain; the existing clear owns both banks.
        prepare = 1; address = 16'hfe20; data = 8'h81;
        repeat (12) edge_cycle(); commit = 1; late_window = 1; edge_cycle();
        commit = 0; prepare = 0; late_window = 0; core_reset = 1; edge_cycle();
        core_reset = 0; repeat (8192) edge_cycle();
        for (index = 0; index < 160; index = index + 1) expected[index] = 0;
        inspect();
        // Reset drops a partially prepared transaction; no stale completion.
        prepare = 1; address = 16'hfe9c; data = 8'h81;
        repeat (3) edge_cycle(); core_reset = 1; edge_cycle();
        prepare = 0; core_reset = 0; repeat (8192) edge_cycle();
        for (index = 0; index < 160; index = index + 1) expected[index] = 0;
        inspect();
        if (fault || checks != 12) $fatal(1, "OAM_LATE_CHECKS count=%0d", checks);
        $display("PASS OAM late owner checks=12");
        $finish;
    end
    initial begin #2000000; $fatal(1, "OAM_LATE_TIMEOUT"); end
endmodule

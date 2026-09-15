// Original pin-level simulation model of the DE10-Lite SDRAM (ISSI
// IS42S16320D: 4 banks x 8192 rows x 1024 columns x 16 bits) for the Verilator
// fixtures in src/dv/storage. Contract: wiki/src/rtl/storage/MAS_sdram.md.
// Written against the datasheet edge counts, not the controller's constants.
// Quartus never sees it; the Questa compile gate compiles it with the RTL.
//
// The model samples every command on its own rising clock edge, keeps one open
// row per bank, stores words in a sparse map keyed by {bank, row, column},
// drives read bursts CL2 edges after READ with a tAC delay and fails with a
// named fatal on every protocol or timing violation listed in the contract.
`timescale 1ns/1ps
`default_nettype none

module n2m_sim_sdram #(
    // A never-written word reads as seeded random data unless a fixture opts
    // in to one defined fill value.
    parameter bit DEFINED_FILL = 1'b0,
    parameter logic [15:0] FILL_VALUE = 16'hcafe,
    // Device edges after READ at which DQ starts driving beat 0: CL-1 per the
    // datasheet ("the DQs start driving as a result of edge n+m-1"). Fixtures
    // move it to reproduce a misaligned controller.
    parameter int READ_LAUNCH_EDGES = 1
) (
    input var logic dram_clk,
    input var logic [12:0] dram_addr,
    input var logic [1:0] dram_ba,
    input var logic dram_ras_n,
    input var logic dram_cas_n,
    input var logic dram_we_n,
    input var logic dram_cke,
    input var logic dram_cs_n,
    input var logic dram_dqml,
    input var logic dram_dqmh,
    inout tri [15:0] dram_dq,
    output logic [31:0] refreshes,
    output logic [31:0] reads,
    output logic [31:0] writes
);
    // Datasheet minimums in 40 ns device clock edges (IS42S16320D -7):
    // tRCD 15 ns, tRP 15 ns, tRC 60 ns, tMRD 2 clocks, tWR 2 clocks,
    // tRAS 37 ns checked as 2 edges, tREF 64 ms / 8192 rows = 195 edges,
    // power-up 200 us = 5000 edges, CL2, BL8, tAC 6 ns.
    localparam int TRCD_EDGES = 1;
    localparam int TRP_EDGES = 1;
    localparam int TRC_EDGES = 2;
    localparam int TMRD_EDGES = 2;
    localparam int TWR_EDGES = 2;
    localparam int TRAS_EDGES = 2;
    localparam int REFRESH_DEADLINE_EDGES = 195;
    localparam int POWERUP_EDGES = 5000;
    localparam int CAS_LATENCY = 2;
    localparam int BURST_BEATS = 8;
    localparam int INIT_REFRESHES = 8;
    localparam logic [12:0] MODE_VALUE = 13'h023;
    localparam realtime ACCESS_TIME = 6ns;

    typedef enum logic [2:0] {
        NOP = 3'b111, READ = 3'b101, WRITE = 3'b100, ACTIVATE = 3'b011,
        PRECHARGE = 3'b010, REFRESH = 3'b001, MODE = 3'b000, TERMINATE = 3'b110
    } command_t;

    logic [15:0] words [int unsigned];
    logic [12:0] open_row [4];
    bit bank_open [4];
    int last_activate [4];
    int last_precharge [4];
    int edge_index;
    int last_refresh;
    int last_mode;
    int last_write_beat;
    bit initialized;
    int refresh_count;
    int read_count;
    int write_count;
    // One burst at a time: the block base, the start column and the beat index.
    int unsigned burst_block;
    int burst_start;
    int burst_index;
    int write_remaining;
    int read_remaining;
    int read_due;
    logic device_drive;
    logic [15:0] device_data;

    assign dram_dq = device_drive ? device_data : 16'hzzzz;
    assign refreshes = 32'(refresh_count);
    assign reads = 32'(read_count);
    assign writes = 32'(write_count);

    function automatic int unsigned word_key(input logic [1:0] bank, input logic [12:0] row, input logic [9:0] column);
        return {7'd0, bank, row, column};
    endfunction

    // Sequential BL8 wraps inside the aligned eight-word block it started in.
    function automatic int unsigned beat_key(input int unsigned block, input int start, input int beat);
        int unsigned offset;
        offset = (start + beat) % BURST_BEATS;
        return block | offset;
    endfunction

    function automatic logic [15:0] stored(input int unsigned key);
        if (words.exists(key)) return words[key];
        return DEFINED_FILL ? FILL_VALUE : 16'($urandom);
    endfunction

    task automatic device_reset();
        int bank;
        for (bank = 0; bank < 4; bank = bank + 1) begin
            bank_open[bank] = 1'b0;
            open_row[bank] = '0;
            last_activate[bank] = -1000;
            last_precharge[bank] = -1000;
        end
        edge_index = -1;
        last_refresh = -1000;
        last_mode = -1000;
        last_write_beat = -1000;
        initialized = 1'b0;
        refresh_count = 0;
        read_count = 0;
        write_count = 0;
        write_remaining = 0;
        read_remaining = 0;
        read_due = 0;
        burst_block = 0;
        burst_start = 0;
        burst_index = 0;
        words.delete();
    endtask

    initial begin
        device_reset();
        device_drive = 1'b0;
        device_data = '0;
    end

    // Fixture preload: one 16-bit word at an even device byte address, byte
    // `address` in bits 7:0. Call after the controller raises CKE, because
    // CKE low restarts the device with empty storage.
    task automatic preload_word(input logic [25:0] address, input logic [15:0] value);
        words[word_key(address[25:24], address[23:11], address[10:1])] = value;
    endtask

    always @(posedge dram_clk) begin : device
        command_t command;
        logic drive_now;
        logic [15:0] data_now;
        int bank;
        if (!dram_cke) begin
            // CKE low is the reset state of the controller: contents and open
            // rows are undefined afterwards, so the model starts over.
            device_reset();
            device_drive = 1'b0;
        end else begin
            edge_index = edge_index + 1;
            command = dram_cs_n ? NOP : command_t'({dram_ras_n, dram_cas_n, dram_we_n});
            if (initialized && edge_index - last_refresh > REFRESH_DEADLINE_EDGES)
                $fatal(1, "SDRAM_MODEL_REFRESH_DEADLINE edge=%0d gap=%0d limit=%0d",
                    edge_index, edge_index - last_refresh, REFRESH_DEADLINE_EDGES);
            // A write burst samples one beat on every edge after its command.
            if (write_remaining != 0) begin
                if ($isunknown(dram_dq))
                    $fatal(1, "SDRAM_MODEL_WRITE_UNKNOWN edge=%0d beat=%0d", edge_index, burst_index);
                if (dram_dqml || dram_dqmh)
                    $fatal(1, "SDRAM_MODEL_WRITE_MASKED edge=%0d beat=%0d", edge_index, burst_index);
                words[beat_key(burst_block, burst_start, burst_index)] = dram_dq;
                burst_index = burst_index + 1;
                write_remaining = write_remaining - 1;
                last_write_beat = edge_index;
            end
            if (command != NOP && edge_index < POWERUP_EDGES)
                $fatal(1, "SDRAM_MODEL_POWERUP edge=%0d command=%b minimum=%0d", edge_index, command, POWERUP_EDGES);
            case (command)
                NOP: begin end
                PRECHARGE: begin
                    for (bank = 0; bank < 4; bank = bank + 1) begin
                        if (dram_addr[10] || bank == int'(dram_ba)) begin
                            if (bank_open[bank] && edge_index - last_activate[bank] < TRAS_EDGES)
                                $fatal(1, "SDRAM_MODEL_TRAS edge=%0d bank=%0d activate=%0d", edge_index, bank, last_activate[bank]);
                            if (bank_open[bank] && (write_remaining != 0 || edge_index - last_write_beat < TWR_EDGES))
                                $fatal(1, "SDRAM_MODEL_TWR edge=%0d bank=%0d last_beat=%0d", edge_index, bank, last_write_beat);
                            bank_open[bank] = 1'b0;
                            last_precharge[bank] = edge_index;
                        end
                    end
                end
                REFRESH: begin
                    for (bank = 0; bank < 4; bank = bank + 1) begin
                        if (bank_open[bank])
                            $fatal(1, "SDRAM_MODEL_REFRESH_OPEN_BANK edge=%0d bank=%0d", edge_index, bank);
                        if (edge_index - last_precharge[bank] < TRP_EDGES)
                            $fatal(1, "SDRAM_MODEL_TRP edge=%0d bank=%0d precharge=%0d", edge_index, bank, last_precharge[bank]);
                    end
                    if (edge_index - last_refresh < TRC_EDGES)
                        $fatal(1, "SDRAM_MODEL_TRC edge=%0d refresh=%0d", edge_index, last_refresh);
                    if (edge_index - last_mode < TMRD_EDGES)
                        $fatal(1, "SDRAM_MODEL_TMRD edge=%0d mode=%0d", edge_index, last_mode);
                    last_refresh = edge_index;
                    refresh_count = refresh_count + 1;
                end
                MODE: begin
                    for (bank = 0; bank < 4; bank = bank + 1) begin
                        if (bank_open[bank])
                            $fatal(1, "SDRAM_MODEL_MODE_OPEN_BANK edge=%0d bank=%0d", edge_index, bank);
                        if (edge_index - last_precharge[bank] < TRP_EDGES)
                            $fatal(1, "SDRAM_MODEL_TRP edge=%0d bank=%0d precharge=%0d", edge_index, bank, last_precharge[bank]);
                    end
                    if (edge_index - last_refresh < TRC_EDGES)
                        $fatal(1, "SDRAM_MODEL_TRC edge=%0d refresh=%0d", edge_index, last_refresh);
                    if (refresh_count < INIT_REFRESHES)
                        $fatal(1, "SDRAM_MODEL_INIT_SEQUENCE edge=%0d refreshes=%0d required=%0d", edge_index, refresh_count, INIT_REFRESHES);
                    if (dram_addr != MODE_VALUE || dram_ba != 2'd0)
                        $fatal(1, "SDRAM_MODEL_MODE edge=%0d value=%h bank=%0d expected=%h", edge_index, dram_addr, dram_ba, MODE_VALUE);
                    initialized = 1'b1;
                    last_mode = edge_index;
                end
                ACTIVATE: begin
                    if (!initialized)
                        $fatal(1, "SDRAM_MODEL_BEFORE_INIT edge=%0d command=ACTIVATE", edge_index);
                    if (bank_open[dram_ba])
                        $fatal(1, "SDRAM_MODEL_BANK_OPEN edge=%0d bank=%0d row=%0d", edge_index, dram_ba, open_row[dram_ba]);
                    if (edge_index - last_precharge[dram_ba] < TRP_EDGES)
                        $fatal(1, "SDRAM_MODEL_TRP edge=%0d bank=%0d precharge=%0d", edge_index, dram_ba, last_precharge[dram_ba]);
                    if (edge_index - last_refresh < TRC_EDGES)
                        $fatal(1, "SDRAM_MODEL_TRC edge=%0d refresh=%0d", edge_index, last_refresh);
                    if (edge_index - last_mode < TMRD_EDGES)
                        $fatal(1, "SDRAM_MODEL_TMRD edge=%0d mode=%0d", edge_index, last_mode);
                    bank_open[dram_ba] = 1'b1;
                    open_row[dram_ba] = dram_addr;
                    last_activate[dram_ba] = edge_index;
                end
                READ, WRITE: begin
                    if (!initialized)
                        $fatal(1, "SDRAM_MODEL_BEFORE_INIT edge=%0d command=%s", edge_index, command == READ ? "READ" : "WRITE");
                    if (!bank_open[dram_ba])
                        $fatal(1, "SDRAM_MODEL_ROW_CLOSED edge=%0d bank=%0d", edge_index, dram_ba);
                    if (edge_index - last_activate[dram_ba] < TRCD_EDGES)
                        $fatal(1, "SDRAM_MODEL_TRCD edge=%0d bank=%0d activate=%0d", edge_index, dram_ba, last_activate[dram_ba]);
                    if (dram_addr[10])
                        $fatal(1, "SDRAM_MODEL_AUTO_PRECHARGE edge=%0d", edge_index);
                    // A second column command while a burst is on the bus is
                    // the pin-level form of two drivers on DQ.
                    if (read_remaining != 0 || write_remaining != 0)
                        $fatal(1, "SDRAM_MODEL_BURST_OVERLAP edge=%0d reads_left=%0d writes_left=%0d", edge_index, read_remaining, write_remaining);
                    burst_block = word_key(dram_ba, open_row[dram_ba], {dram_addr[9:3], 3'd0});
                    burst_start = int'(dram_addr[2:0]);
                    if (command == WRITE) begin
                        // Beat 0 is on the bus with the command.
                        if ($isunknown(dram_dq))
                            $fatal(1, "SDRAM_MODEL_WRITE_UNKNOWN edge=%0d beat=0", edge_index);
                        if (dram_dqml || dram_dqmh)
                            $fatal(1, "SDRAM_MODEL_WRITE_MASKED edge=%0d beat=0", edge_index);
                        words[beat_key(burst_block, burst_start, 0)] = dram_dq;
                        burst_index = 1;
                        write_remaining = BURST_BEATS - 1;
                        last_write_beat = edge_index;
                        write_count = write_count + 1;
                    end else begin
                        burst_index = 0;
                        read_due = edge_index + READ_LAUNCH_EDGES;
                        read_remaining = BURST_BEATS;
                        read_count = read_count + 1;
                    end
                end
                default: $fatal(1, "SDRAM_MODEL_COMMAND edge=%0d command=%b", edge_index, command);
            endcase
            // Read data leaves the device tAC after the edge that launches it
            // (edge READ+CL-1 for beat 0, valid by edge READ+CL) and the bus is
            // released the same way after the last beat.
            drive_now = 1'b0;
            data_now = device_data;
            if (read_remaining != 0 && edge_index >= read_due) begin
                drive_now = 1'b1;
                data_now = stored(beat_key(burst_block, burst_start, burst_index));
                burst_index = burst_index + 1;
                read_remaining = read_remaining - 1;
            end
            #(ACCESS_TIME);
            device_drive = drive_now;
            device_data = data_now;
        end
    end
endmodule
`default_nettype wire

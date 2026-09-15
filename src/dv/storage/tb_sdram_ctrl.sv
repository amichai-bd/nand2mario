`timescale 1ns/1ps
`default_nettype none
// SDRAM controller fixtures against the pin-level device model.
// Contract: wiki/src/rtl/storage/MAS_sdram.md#verification. Test plan: README.md.
//
// One clock is 40 ns. Clock 0 is the first clock after reset release; the
// monitor samples mid-clock (the device's edge), so "at clock c" means the
// value the device sees during clock c. Every expectation is computed from
// the contract and the fixture's own request record, never from DUT state.
module tb_sdram_ctrl #(
    parameter int REFRESH_INTERVAL = 160
);
    import n2m_sdram_pkg::*;

    localparam int CLOCK_NS = 40;
    localparam int RESPONSE_CLOCKS = 17;
    localparam int OCCUPANCY_CLOCKS = 18;
    localparam int REFRESH_STALL = 5;
    localparam int ACCEPT_LATENCY = 5;
    localparam int WORST_AGE = REFRESH_INTERVAL + OCCUPANCY_CLOCKS;
    localparam int INITIALIZED_CLOCK = 5036;
    localparam int IDLE_CLOCK = 5038;
    localparam int THROUGHPUT_LINES = 2048;
    localparam int THROUGHPUT_CLOCKS = 38100;
    localparam int REFRESH_RUN_CLOCKS = 40000;

    logic clk_sys;
    logic reset_sys;
    logic request_valid;
    logic request_write;
    logic [25:0] request_address;
    logic [127:0] request_data;
    logic request_ready;
    logic response_valid;
    logic [127:0] response_data;
    logic idle;
    logic initialized;
    logic [12:0] dram_addr;
    logic [1:0] dram_ba;
    logic dram_cas_n, dram_cke, dram_clk, dram_cs_n, dram_dqml, dram_dqmh, dram_ras_n, dram_we_n;
    tri [15:0] dram_dq;
    logic [31:0] model_refreshes, model_reads, model_writes;

    n2m_sdram_ctrl #(.REFRESH_INTERVAL(REFRESH_INTERVAL)) dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .request_valid(request_valid), .request_write(request_write),
        .request_address(request_address), .request_data(request_data),
        .request_ready(request_ready), .response_valid(response_valid),
        .response_data(response_data), .idle(idle), .initialized(initialized),
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

    // Fixture selection and bookkeeping.
    string fixture;
    integer seed;
    int clock_index;
    int accepted_lines;
    int completed_reads;
    int writes_issued;
    int reads_issued;
    int refresh_commands;
    int max_age;
    int worst_age_hits;
    int max_accept_latency;
    int response_hold_checks;
    bit idle_seen;
    bit initialized_seen;
    int initialized_clock;
    int idle_clock;
    int precharge_clock;
    int mode_clock;
    int init_refresh_clocks [8];
    logic [127:0] memory [int unsigned];

    int accept_clock;
    int request_raised_clock;
    bit request_raised_idle;
    // The accepted request the monitor checks pins against.
    logic accepted_write;
    logic [25:0] accepted_address;
    logic [127:0] accepted_data;
    bit outstanding;
    bit write_burst;
    int write_beats;
    bit response_pending;
    logic [127:0] held_response;
    bit response_held;
    int refresh_clock;
    logic [7:0] ready_history;
    int pending_refresh_check;

    always #(CLOCK_NS / 2) clk_sys = ~clk_sys;
    always @(posedge clk_sys) clock_index = clock_index + 1;

    function automatic int unsigned line_key(input logic [25:0] address);
        return {10'd0, address[25:4]};
    endfunction

    function automatic logic [127:0] pattern(input logic [25:0] address, input int salt);
        logic [127:0] value;
        int i;
        value = 128'hfedcba98765432100123456789abcdef ^ {102'd0, address};
        for (i = 0; i < 16; i = i + 1)
            value[i*8 +: 8] = value[i*8 +: 8] ^ 8'(i * 37 + salt * 11 + int'(address[10:4]));
        return value;
    endfunction

    // Pin-level monitor at the device edge.
    always @(negedge clk_sys) begin : monitor
        logic [2:0] command;
        if (reset_sys) begin end
        else begin
            command = dram_cs_n ? 3'b111 : {dram_ras_n, dram_cas_n, dram_we_n};
            ready_history = {ready_history[6:0], request_ready};
            // Initialization schedule and guards.
            if (initialized && !initialized_seen) begin
                initialized_seen = 1'b1;
                initialized_clock = clock_index;
            end
            if (initialized_seen && !initialized)
                $fatal(1, "SDRAM_TB_INITIALIZED_DROPPED clock=%0d", clock_index);
            if (idle && !idle_seen) begin
                idle_seen = 1'b1;
                idle_clock = clock_index;
            end
            if ((dram_dqml || dram_dqmh) != !initialized)
                $fatal(1, "SDRAM_TB_DQM clock=%0d dqml=%b dqmh=%b initialized=%b", clock_index, dram_dqml, dram_dqmh, initialized);
            if (!idle_seen && (command == 3'b011 || command == 3'b101 || command == 3'b100))
                $fatal(1, "SDRAM_TB_EARLY_ACCESS clock=%0d command=%b", clock_index, command);
            case (command)
                3'b010: if (!initialized_seen) precharge_clock = clock_index;
                3'b001: begin
                    if (!initialized_seen) begin
                        if (refresh_commands < 8) init_refresh_clocks[refresh_commands] = clock_index;
                    end else begin
                        if (refresh_clock >= 0) begin
                            if (clock_index - refresh_clock - 1 > max_age) max_age = clock_index - refresh_clock - 1;
                            if (clock_index - refresh_clock - 1 == WORST_AGE) worst_age_hits = worst_age_hits + 1;
                            if (clock_index - refresh_clock - 1 > WORST_AGE)
                                $fatal(1, "SDRAM_TB_REFRESH_AGE clock=%0d age=%0d limit=%0d", clock_index, clock_index - refresh_clock - 1, WORST_AGE);
                        end
                        // A refresh from IDLE stalls the requester exactly five clocks:
                        // ready fell the clock before the command and returns four after it.
                        if (ready_history[1])
                            $fatal(1, "SDRAM_TB_REFRESH_READY clock=%0d ready was high before the refresh", clock_index);
                        pending_refresh_check = clock_index;
                    end
                    refresh_clock = clock_index;
                    refresh_commands = refresh_commands + 1;
                end
                3'b000: mode_clock = clock_index;
                3'b011: begin
                    if (!outstanding) $fatal(1, "SDRAM_TB_UNEXPECTED_ACTIVATE clock=%0d", clock_index);
                    if (dram_ba != accepted_address[25:24] || dram_addr != accepted_address[23:11])
                        $fatal(1, "SDRAM_TB_ROW_MAP clock=%0d address=%h bank=%0d/%0d row=%h/%h", clock_index,
                            accepted_address, dram_ba, accepted_address[25:24], dram_addr, accepted_address[23:11]);
                    if (clock_index != accept_clock + 1)
                        $fatal(1, "SDRAM_TB_ACTIVATE_CLOCK clock=%0d accepted=%0d", clock_index, accept_clock);
                end
                3'b101, 3'b100: begin
                    if (!outstanding) $fatal(1, "SDRAM_TB_UNEXPECTED_COLUMN clock=%0d", clock_index);
                    if (dram_ba != accepted_address[25:24] || dram_addr[9:0] != accepted_address[10:1] || dram_addr[10])
                        $fatal(1, "SDRAM_TB_COLUMN_MAP clock=%0d address=%h bank=%0d column=%h/%h a10=%b", clock_index,
                            accepted_address, dram_ba, dram_addr[9:0], accepted_address[10:1], dram_addr[10]);
                    if ((command == 3'b100) != accepted_write)
                        $fatal(1, "SDRAM_TB_DIRECTION clock=%0d write=%b command=%b", clock_index, accepted_write, command);
                    if (clock_index != accept_clock + 4)
                        $fatal(1, "SDRAM_TB_COLUMN_CLOCK clock=%0d accepted=%0d", clock_index, accept_clock);
                    if (accepted_write) begin
                        write_burst = 1'b1;
                        write_beats = 0;
                    end
                end
                default: begin end
            endcase
            if (pending_refresh_check >= 0 && clock_index == pending_refresh_check + REFRESH_STALL - 1) begin
                if (ready_history[3:1] != 3'b000 || !request_ready)
                    $fatal(1, "SDRAM_TB_REFRESH_STALL clock=%0d history=%b ready=%b", clock_index, ready_history, request_ready);
                pending_refresh_check = -1;
            end
            // Write beats: word k carries line bytes 2k and 2k+1, little-endian.
            if (write_burst) begin
                if (dram_dq !== accepted_data[write_beats*16 +: 16])
                    $fatal(1, "SDRAM_TB_WRITE_BEAT clock=%0d beat=%0d expected=%h actual=%h", clock_index, write_beats,
                        accepted_data[write_beats*16 +: 16], dram_dq);
                write_beats = write_beats + 1;
                if (write_beats == 8) write_burst = 1'b0;
            end
            // Latency bounds from the accepting edge.
            if (response_valid) begin
                if (!response_pending || clock_index != accept_clock + RESPONSE_CLOCKS)
                    $fatal(1, "SDRAM_TB_RESPONSE_LATENCY clock=%0d accepted=%0d pending=%b", clock_index, accept_clock, response_pending);
                if (response_data !== memory[line_key(accepted_address)])
                    $fatal(1, "SDRAM_TB_READBACK clock=%0d address=%h expected=%h actual=%h", clock_index,
                        accepted_address, memory[line_key(accepted_address)], response_data);
                completed_reads = completed_reads + 1;
                response_pending = 1'b0;
                held_response = response_data;
                response_held = 1'b1;
            end else if (response_pending && clock_index == accept_clock + RESPONSE_CLOCKS)
                $fatal(1, "SDRAM_TB_RESPONSE_MISSING clock=%0d accepted=%0d", clock_index, accept_clock);
            if (outstanding) begin
                if (clock_index > accept_clock && clock_index < accept_clock + OCCUPANCY_CLOCKS && idle)
                    $fatal(1, "SDRAM_TB_EARLY_IDLE clock=%0d accepted=%0d", clock_index, accept_clock);
                if (clock_index == accept_clock + OCCUPANCY_CLOCKS) begin
                    if (!idle) $fatal(1, "SDRAM_TB_IDLE_LATENCY clock=%0d accepted=%0d", clock_index, accept_clock);
                    outstanding = 1'b0;
                end
            end
            if (response_held && response_data != held_response)
                $fatal(1, "SDRAM_TB_RESPONSE_CHANGED clock=%0d expected=%h actual=%h", clock_index, held_response, response_data);
            if (response_held) response_hold_checks = response_hold_checks + 1;
            // Acceptance happens at the edge ending this clock.
            if (request_valid && request_ready) begin
                if (outstanding) $fatal(1, "SDRAM_TB_OVERLAP clock=%0d", clock_index);
                if (clock_index - request_raised_clock > max_accept_latency) max_accept_latency = clock_index - request_raised_clock;
                if (request_raised_idle && clock_index - request_raised_clock > ACCEPT_LATENCY)
                    $fatal(1, "SDRAM_TB_ACCEPT_LATENCY clock=%0d raised=%0d limit=%0d", clock_index, request_raised_clock, ACCEPT_LATENCY);
                accept_clock = clock_index;
                accepted_write = request_write;
                accepted_address = request_address;
                accepted_data = request_data;
                outstanding = 1'b1;
                accepted_lines = accepted_lines + 1;
                if (request_write) begin
                    memory[line_key(request_address)] = request_data;
                    writes_issued = writes_issued + 1;
                end else begin
                    reads_issued = reads_issued + 1;
                    response_pending = 1'b1;
                    // The held line may change once the next read is accepted.
                    response_held = 1'b0;
                end
            end
        end
    end

    // Load one request just after a rising edge; the monitor records it at
    // acceptance and every stream keeps the fields stable until then.
    task automatic present(input bit write, input logic [25:0] address, input logic [127:0] data);
        request_raised_clock = clock_index;
        request_raised_idle = idle;
        request_write = write;
        request_address = address;
        request_data = data;
        request_valid = 1'b1;
    endtask

    task automatic wait_accept();
        forever begin
            @(negedge clk_sys);
            if (request_valid && request_ready) break;
        end
        @(posedge clk_sys);
        #1;
    endtask

    // Present one request just after a rising edge and hold it until accepted.
    task automatic issue(input bit write, input logic [25:0] address, input logic [127:0] data);
        @(posedge clk_sys);
        #1;
        present(write, address, data);
        wait_accept();
        request_valid = 1'b0;
    endtask

    // The next request replaces the accepted one on the very next clock, so
    // valid stays high across the whole stream without a payload change
    // while a request is waiting.
    task automatic issue_back_to_back(input bit write, input logic [25:0] address, input logic [127:0] data);
        present(write, address, data);
        wait_accept();
    endtask

    task automatic wait_response();
        forever begin
            @(negedge clk_sys);
            if (response_valid) break;
        end
    endtask

    task automatic wait_idle();
        forever begin
            @(negedge clk_sys);
            if (idle && !outstanding) break;
        end
    endtask

    task automatic write_then_read(input logic [25:0] address, input int salt);
        issue(1'b1, address, pattern(address, salt));
        wait_idle();
        issue(1'b0, address, '0);
        wait_response();
        wait_idle();
    endtask

    task automatic wait_initialized();
        forever begin
            @(negedge clk_sys);
            if (idle_seen) break;
        end
        repeat (4) @(posedge clk_sys);
    endtask

    // Wait in IDLE until the tb-measured age reaches the value, then request,
    // so the accepted transaction pushes the next refresh to the worst age.
    task automatic request_at_age(input int age, input logic [25:0] address);
        forever begin
            @(posedge clk_sys);
            #1;
            if (clock_index - refresh_clock - 1 == age && idle) break;
        end
        present(1'b1, address, pattern(address, 7));
        @(negedge clk_sys);
        if (!(request_valid && request_ready))
            $fatal(1, "SDRAM_TB_AGE_REQUEST clock=%0d age=%0d ready=%b", clock_index, age, request_ready);
        @(posedge clk_sys);
        #1;
        request_valid = 1'b0;
        wait_idle();
    endtask

    task automatic run_init();
        int k;
        wait_initialized();
        if (initialized_clock != INITIALIZED_CLOCK)
            $fatal(1, "SDRAM_TB_INIT_CLOCK expected=%0d actual=%0d", INITIALIZED_CLOCK, initialized_clock);
        if (idle_clock != IDLE_CLOCK)
            $fatal(1, "SDRAM_TB_IDLE_CLOCK expected=%0d actual=%0d", IDLE_CLOCK, idle_clock);
        if (precharge_clock != 5000 || mode_clock != 5035)
            $fatal(1, "SDRAM_TB_INIT_ORDER precharge=%0d mode=%0d", precharge_clock, mode_clock);
        for (k = 0; k < 8; k = k + 1)
            if (init_refresh_clocks[k] != 5003 + 4 * k)
                $fatal(1, "SDRAM_TB_INIT_REFRESH k=%0d expected=%0d actual=%0d", k, 5003 + 4 * k, init_refresh_clocks[k]);
        if (refresh_commands != 8 || model_refreshes != 8)
            $fatal(1, "SDRAM_TB_INIT_REFRESH_COUNT tb=%0d model=%0d", refresh_commands, model_refreshes);
        $display("PASS sdram-init initialized=%0d idle=%0d precharge=%0d mode=%0d refreshes=%0d",
            initialized_clock, idle_clock, precharge_clock, mode_clock, model_refreshes);
    endtask

    task automatic run_line();
        logic [25:0] addresses [0:15];
        int i;
        wait_initialized();
        // Slot boundaries, catalogue, row boundaries, one line per bank.
        addresses[0] = 26'h0000000;
        addresses[1] = 26'h0007ff0;
        addresses[2] = 26'h0078000;
        addresses[3] = 26'h007fff0;
        addresses[4] = 26'h0080000;
        addresses[5] = 26'h0087ff0;
        addresses[6] = 26'h0088000;
        addresses[7] = 26'h00883f0;
        addresses[8] = 26'h1002800;
        addresses[9] = 26'h1002ff0;
        addresses[10] = 26'h0000010;
        addresses[11] = 26'h1abc800;
        addresses[12] = 26'h2000ff0;
        addresses[13] = 26'h3fffff0;
        addresses[14] = 26'h0fff800;
        addresses[15] = 26'h2fff7f0;
        for (i = 0; i < 16; i = i + 1) write_then_read(addresses[i], i);
        // Every line again after the others: rows and banks do not alias.
        for (i = 15; i >= 0; i = i - 1) begin
            issue(1'b0, addresses[i], '0);
            wait_response();
            wait_idle();
        end
        // Same-line write then read back to back: acceptance orders them.
        issue(1'b1, addresses[3], pattern(addresses[3], 99));
        issue(1'b0, addresses[3], '0);
        wait_response();
        wait_idle();
        // A request raised right after a write acceptance waits for it.
        issue(1'b1, addresses[9], pattern(addresses[9], 98));
        issue(1'b0, addresses[9], '0);
        wait_response();
        // The held read line survives a following write.
        issue(1'b1, addresses[10], pattern(addresses[10], 97));
        wait_idle();
        if (response_data !== memory[line_key(addresses[9])])
            $fatal(1, "SDRAM_TB_RESPONSE_HOLD expected=%h actual=%h", memory[line_key(addresses[9])], response_data);
        if (max_accept_latency > ACCEPT_LATENCY + OCCUPANCY_CLOCKS)
            $fatal(1, "SDRAM_TB_BUSY_ACCEPT_LATENCY worst=%0d", max_accept_latency);
        if (completed_reads != 34 || model_reads != 34 || model_writes != 19 || response_hold_checks == 0)
            $fatal(1, "SDRAM_TB_LINE_COVERAGE reads=%0d/%0d writes=%0d holds=%0d", completed_reads, model_reads, model_writes, response_hold_checks);
        $display("PASS sdram-line lines=16 reads=%0d writes=%0d worst_accept=%0d refreshes=%0d",
            model_reads, model_writes, max_accept_latency, model_refreshes);
    endtask

    task automatic run_refresh();
        int start_clock;
        int throughput_lines;
        int i;
        int j;
        logic [25:0] address;
        wait_initialized();
        // Back-to-back traffic with valid held high: 64 lines spread across
        // banks and rows, written in one pass and read back in the next.
        @(posedge clk_sys);
        #1;
        start_clock = clock_index;
        throughput_lines = 0;
        i = 0;
        while (clock_index - start_clock < REFRESH_RUN_CLOCKS) begin
            j = i % 64;
            address = {2'(j[5:4]), 13'(j[3:0] * 547), 7'(j[5:2] * 7), 4'd0};
            if ((i / 64) % 2 == 0) issue_back_to_back(1'b1, address, pattern(address, i / 128));
            else issue_back_to_back(1'b0, address, '0);
            if (clock_index - start_clock <= THROUGHPUT_CLOCKS) throughput_lines = throughput_lines + 1;
            i = i + 1;
        end
        request_valid = 1'b0;
        wait_idle();
        if (throughput_lines < THROUGHPUT_LINES)
            $fatal(1, "SDRAM_TB_THROUGHPUT lines=%0d clocks=%0d required=%0d", throughput_lines, THROUGHPUT_CLOCKS, THROUGHPUT_LINES);
        // Directed: accept at the last ready age so the refresh lands at the
        // worst age, three times.
        for (i = 0; i < 3; i = i + 1) request_at_age(REFRESH_INTERVAL - 1, 26'h0100000 + 26'(i * 16));
        wait_idle();
        repeat (REFRESH_INTERVAL + 8) @(posedge clk_sys);
        if (worst_age_hits < 3 || max_age != WORST_AGE)
            $fatal(1, "SDRAM_TB_WORST_AGE max=%0d expected=%0d hits=%0d", max_age, WORST_AGE, worst_age_hits);
        if (pending_refresh_check >= 0)
            $fatal(1, "SDRAM_TB_REFRESH_STALL_UNCHECKED clock=%0d", pending_refresh_check);
        if (completed_reads != reads_issued || completed_reads == 0)
            $fatal(1, "SDRAM_TB_REFRESH_READS completed=%0d issued=%0d", completed_reads, reads_issued);
        $display("PASS sdram-refresh clocks=%0d lines=%0d reads=%0d throughput=%0d/%0d refreshes=%0d max_age=%0d worst_hits=%0d",
            REFRESH_RUN_CLOCKS, accepted_lines, completed_reads, throughput_lines, THROUGHPUT_CLOCKS, model_refreshes, max_age, worst_age_hits);
    endtask

    task automatic run_fault_misaligned();
        wait_initialized();
        issue(1'b1, 26'h0000008, pattern(26'h0000008, 1));
        wait_idle();
        $fatal(1, "SDRAM_TB_FAULT_NOT_CAUGHT misaligned request accepted");
    endtask

    task automatic run_fault_before_init();
        repeat (100) @(posedge clk_sys);
        #1;
        request_valid = 1'b1;
        request_write = 1'b1;
        request_address = '0;
        request_data = '0;
        repeat (4) @(posedge clk_sys);
        $fatal(1, "SDRAM_TB_FAULT_NOT_CAUGHT request before initialization tolerated");
    endtask

    initial begin
        clk_sys = 1'b0;
        reset_sys = 1'b1;
        request_valid = 1'b0;
        request_write = 1'b0;
        request_address = '0;
        request_data = '0;
        clock_index = -1;
        accepted_lines = 0;
        completed_reads = 0;
        writes_issued = 0;
        reads_issued = 0;
        refresh_commands = 0;
        max_age = 0;
        worst_age_hits = 0;
        max_accept_latency = 0;
        response_hold_checks = 0;
        idle_seen = 1'b0;
        initialized_seen = 1'b0;
        initialized_clock = -1;
        idle_clock = -1;
        precharge_clock = -1;
        mode_clock = -1;
        accept_clock = -1000;
        request_raised_clock = 0;
        request_raised_idle = 1'b0;
        accepted_write = 1'b0;
        accepted_address = '0;
        accepted_data = '0;
        outstanding = 1'b0;
        write_burst = 1'b0;
        write_beats = 0;
        response_pending = 1'b0;
        held_response = '0;
        response_held = 1'b0;
        refresh_clock = -1;
        ready_history = '0;
        pending_refresh_check = -1;
        seed = 1;
        if ($value$plusargs("seed=%d", seed)) begin end
        if (!$value$plusargs("fixture=%s", fixture)) fixture = "init";
        $dumpfile("waves/sdram.vcd");
        $dumpvars(0, tb_sdram_ctrl);
        // Reset held across three edges, released just after a rising edge so
        // the next rising edge is clock 0 and the device sees CKE rise cleanly.
        repeat (3) @(posedge clk_sys);
        #1;
        reset_sys = 1'b0;
        clock_index = -1;
        case (fixture)
            "init": run_init();
            "line": run_line();
            "refresh": run_refresh();
            "fault-misaligned": run_fault_misaligned();
            "fault-before-init": run_fault_before_init();
            default: $fatal(1, "SDRAM_TB_FIXTURE unknown fixture %s", fixture);
        endcase
        $finish;
    end

    initial begin
        #(120000 * CLOCK_NS);
        $fatal(1, "SDRAM_TB_WATCHDOG fixture=%s clock=%0d", fixture, clock_index);
    end
endmodule
`default_nettype wire

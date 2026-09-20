`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// The composed controls path with the timebase running. `controls-wire` already
// instantiates these three actual modules, but only with the timebase paused, so
// `gb_tick` never asserts there and no JOYP bus cycle ever happens; the same is
// true of the board's own `controls_proof`, which ties `io_commit` low. This
// fixture is the missing case: the actual physical producer drives the actual
// shared input owner with no host, ticks run, and a bus owner selects rows and
// reads FF00 the way prepared CPU service does.
// Eight-cycle debounce and a 32-cycle acquisition interval bound DV; the board's
// own filter and interval values are fit separately.
module tb_controls_running;
    logic clk_sys;
    logic reset_sys;
    logic core_reset;
    logic pause_request;
    logic gb_tick;
    logic paused;
    logic [3:0] buttons_n;
    logic [11:0] sample_x;
    logic [11:0] sample_y;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic adc_fresh;
    logic adc_fault;
    n2m_input_pkg::input_write_t host_write;
    n2m_input_pkg::input_update_t effective_update;
    logic [7:0] host_buttons;
    logic [7:0] physical_observe;
    logic [7:0] source_observe;
    logic [7:0] effective_buttons;
    logic io_commit;
    logic io_write;
    logic [7:0] io_wdata;
    logic io_selected;
    logic [7:0] io_rdata;
    logic [7:0] buttons_observe;
    logic selected_active;
    logic request_event;
    logic joyp_write;
    logic [9:0] observed_state;
    logic [9:0] state_history;
    logic commit_history;
    logic write_history;
    logic monitor_armed;
    logic [7:0] published;
    logic [3:0] seen_lines;
    bit corrupt_read;
    bit corrupt_state;
    integer ticks;
    integer commits;
    integer updates;
    integer deferrals;
    integer writes;
    integer reads;
    integer checks;
    integer coincident;
    integer sweep_index;
    integer trace;
    logic [11:0] sweep [0:9];

    n2m_physical_controls #(.BUTTON_CYCLES(8), .INTERVAL_CYCLES(32), .LIMIT_CYCLES(256)) u_physical (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .gb_tick(gb_tick), .buttons_n(buttons_n),
        .adc_available(1'b1), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid), .response_channel(response_channel),
        .response_data(response_data), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .adc_fresh(adc_fresh), .adc_fault(adc_fault)
    );
    // No host is present, so the composition selects the physical producer out of
    // reset exactly as a host-free board image does.
    n2m_input #(.PHYSICAL_SOURCE_DEFAULT(1'b1)) u_input (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .host_write(host_write), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .host_buttons(host_buttons), .physical_observe(physical_observe), .source_observe(source_observe),
        .effective_buttons(effective_buttons), .effective_update(effective_update)
    );
    n2m_timebase u_timebase (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(pause_request), .gb_tick(gb_tick), .paused(paused)
    );
    n2m_joypad u_joypad (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .input_commit(effective_update.valid), .input_buttons(effective_update.buttons),
        .io_commit(io_commit), .io_write(io_write), .io_address(n2m_interfaces_pkg::GB_REG_JOYP),
        .io_wdata(io_wdata), .io_selected(io_selected), .io_rdata(io_rdata),
        .buttons_observe(buttons_observe), .selected_active(selected_active), .request_event(request_event)
    );

    assign host_write = '0;
    assign command_ready = 1'b1;
    assign joyp_write = io_commit && io_write;
    // The public projection of the JOYP register: its button field and its two
    // writable select bits.
    assign observed_state = {buttons_observe, io_rdata[5:4]};
    // Accepted command produces a next-edge sample; no vendor module is substituted.
    `DFF_ARST_VAL(response_valid, command_valid && command_ready, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(response_channel, command_channel, clk_sys, reset_sys, 5'd0)
    `DFF_ARST_VAL(response_data, command_channel == 5'd1 ? sample_x : sample_y, clk_sys, reset_sys, 12'd0)

    always #5 clk_sys = !clk_sys;

    // The commit rule, the opposing-axes rule and the tick census, sampled at the
    // same edge the owners' own assertions sample.
    always @(posedge clk_sys) if (!reset_sys) begin
        if (physical_commit && gb_tick)
            $fatal(1, "CONTROLS_RUNNING_TICK_COMMIT mask=%02h", physical_buttons);
        if (joyp_write && !gb_tick)
            $fatal(1, "CONTROLS_RUNNING_OFF_TICK_WRITE wdata=%02h", io_wdata);
        if ((&physical_buttons[1:0]) || (&physical_buttons[3:2]))
            $fatal(1, "CONTROLS_RUNNING_OPPOSING_PHYSICAL mask=%02h", physical_buttons);
        if ((&buttons_observe[1:0]) || (&buttons_observe[3:2]))
            $fatal(1, "CONTROLS_RUNNING_OPPOSING_JOYPAD mask=%02h", buttons_observe);
        // With only the direction row selected the four read lines are the four
        // directions, so opposing directions would be two low bits in one pair.
        if (io_rdata[5:4] == 2'b10 && (io_rdata[1:0] == 2'b00 || io_rdata[3:2] == 2'b00))
            $fatal(1, "CONTROLS_RUNNING_OPPOSING_READ rdata=%02h", io_rdata);
        if (adc_fault) $fatal(1, "CONTROLS_RUNNING_ADC_FAULT");
        if (gb_tick) ticks = ticks + 1;
        if (effective_update.valid) updates = updates + 1;
        if (effective_update.valid && joyp_write) coincident = coincident + 1;
        if (gb_tick && physical_buttons != published) deferrals = deferrals + 1;
        if (physical_commit) begin
            commits = commits + 1;
            published = physical_buttons;
        end
        seen_lines = seen_lines | buttons_observe[3:0];
    end

    // The testbench's own witness for JOYP_STATE_STABLE, on public outputs only:
    // the register may change only across an edge where the owner accepted a mask
    // or the bus wrote the select bits.
    always @(negedge clk_sys) begin
        if (monitor_armed && !corrupt_read && !commit_history && !write_history &&
            observed_state !== state_history)
            $fatal(1, "CONTROLS_RUNNING_JOYP_STATE previous=%03h now=%03h",
                state_history, observed_state);
        state_history <= observed_state;
        commit_history <= effective_update.valid;
        write_history <= joyp_write;
        monitor_armed <= !reset_sys;
    end

    function automatic logic [3:0] row_lines(input logic [7:0] mask, input logic [1:0] row);
        logic [3:0] pressed;
        pressed = 4'd0;
        if (!row[0]) pressed = pressed | {mask[3], mask[2], mask[1], mask[0]};
        if (!row[1]) pressed = pressed | {mask[7], mask[6], mask[5], mask[4]};
        return ~pressed;
    endfunction

    // Every bus cycle happens on a tick, which is the only boundary JOYP accepts.
    task automatic tick_edge;
        @(negedge clk_sys);
        while (!gb_tick) @(negedge clk_sys);
    endtask

    task automatic write_select(input logic [1:0] row);
        tick_edge();
        io_commit = 1'b1; io_write = 1'b1; io_wdata = {2'b00, row, 4'b0000};
        @(negedge clk_sys);
        io_commit = 1'b0; io_write = 1'b0; io_wdata = 8'd0;
        writes = writes + 1;
    endtask

    // Reads are side-effect free and return the pre-edge value, so the value the
    // program receives is io_rdata while its commit is presented.
    task automatic read_expect(input logic [1:0] row, input logic [7:0] mask);
        logic [7:0] expected;
        tick_edge();
        io_commit = 1'b1; io_write = 1'b0;
        expected = {2'b11, row, row_lines(mask, row)};
        if (corrupt_read && row == 2'b01 && mask == 8'h10) force io_rdata = 8'hdf;
        if (io_rdata !== expected)
            $fatal(1, "CONTROLS_RUNNING_JOYP row=%0d expected=%02h actual=%02h check=%0d",
                row, expected, io_rdata, checks);
        if (buttons_observe !== mask || effective_buttons !== mask || physical_observe !== mask)
            $fatal(1, "CONTROLS_RUNNING_MASK expected=%02h joypad=%02h effective=%02h physical=%02h check=%0d",
                mask, buttons_observe, effective_buttons, physical_observe, checks);
        if (selected_active !== (row_lines(mask, row) != 4'hf))
            $fatal(1, "CONTROLS_RUNNING_ACTIVE check=%0d", checks);
        if (source_observe !== n2m_interfaces_pkg::INPUT_SOURCE_PHYSICAL || host_buttons !== 8'd0)
            $fatal(1, "CONTROLS_RUNNING_SOURCE source=%02h host=%02h", source_observe, host_buttons);
        if (paused || !adc_fresh) $fatal(1, "CONTROLS_RUNNING_STATE paused=%b fresh=%b", paused, adc_fresh);
        $fdisplay(trace, "%0d,%0d,%02h,%02h,%02h,%0d", checks, row, mask, io_rdata, physical_buttons, ticks);
        reads = reads + 1;
        checks = checks + 1;
        @(negedge clk_sys);
        io_commit = 1'b0;
    endtask

    // One held mask read through every row selection, which is what the program
    // does to tell directions from actions.
    task automatic expect_all_rows(input logic [7:0] mask);
        integer row_index;
        for (row_index = 0; row_index < 4; row_index = row_index + 1) begin
            write_select(2'(row_index));
            read_expect(2'(row_index), mask);
        end
    endtask

    task automatic settle;
        repeat (140) @(negedge clk_sys);
    endtask

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, paused, buttons_n, sample_x, sample_y,
            command_valid, command_channel, response_valid, response_channel, response_data,
            physical_commit, physical_buttons, adc_fresh, adc_fault, effective_update,
            physical_observe, source_observe, effective_buttons, io_commit, io_write, io_wdata,
            io_rdata, buttons_observe, selected_active, request_event);
        trace = $fopen("running.csv", "w");
        clk_sys = 1'b0; reset_sys = 1'b1; core_reset = 1'b0; pause_request = 1'b0;
        buttons_n = 4'hF; sample_x = 12'd1352; sample_y = 12'd1352;
        io_commit = 1'b0; io_write = 1'b0; io_wdata = 8'd0;
        state_history = 10'd0; commit_history = 1'b0; write_history = 1'b0; monitor_armed = 1'b0;
        published = 8'd0; seen_lines = 4'd0;
        ticks = 0; commits = 0; updates = 0; deferrals = 0; writes = 0; reads = 0;
        checks = 0; coincident = 0;
        corrupt_read = $test$plusargs("CORRUPT_READ");
        corrupt_state = $test$plusargs("CORRUPT_STATE");
        sweep[0] = 12'd1352; sweep[1] = 12'd902;  sweep[2] = 12'd0;    sweep[3] = 12'd950;
        sweep[4] = 12'd1014; sweep[5] = 12'd1802; sweep[6] = 12'd2703; sweep[7] = 12'd1750;
        sweep[8] = 12'd1689; sweep[9] = 12'd1352;
        repeat (8) @(negedge clk_sys);
        reset_sys = 1'b0;
        // The timebase releases its reset pause, so the core this composition
        // feeds is running rather than held.
        settle();
        if (paused) $fatal(1, "CONTROLS_RUNNING_STILL_PAUSED");
        if (ticks == 0) $fatal(1, "CONTROLS_RUNNING_NO_TICK");

        // Released buttons and a centred joystick read as all lines high.
        expect_all_rows(8'h00);
        // One action button, then all four, reach the action row.
        buttons_n = 4'hE; settle(); expect_all_rows(8'h10);
        buttons_n = 4'h0; settle(); expect_all_rows(8'hF0);
        buttons_n = 4'hF; settle();
        // Each axis extreme, the hysteresis band that holds it, and the centre.
        sample_x = 12'd0;    settle(); expect_all_rows(8'h02);
        sample_x = 12'd950;  settle(); expect_all_rows(8'h02);
        sample_x = 12'd1014; settle(); expect_all_rows(8'h00);
        sample_x = 12'd2703; settle(); expect_all_rows(8'h01);
        sample_x = 12'd1750; settle(); expect_all_rows(8'h01);
        // A full reversal in one published pair must never show both directions;
        // the concurrent read monitor is what proves it.
        sample_x = 12'd0;    settle(); expect_all_rows(8'h02);
        sample_x = 12'd1352; sample_y = 12'd0;    settle(); expect_all_rows(8'h04);
        sample_y = 12'd950;  settle(); expect_all_rows(8'h04);
        sample_y = 12'd2703; settle(); expect_all_rows(8'h08);
        // Both axes and an action button at once, across all four selections.
        sample_x = 12'd0; buttons_n = 4'hD; settle(); expect_all_rows(8'h2A);

        // Now move both axes across the whole calibrated range while the core
        // ticks, with nothing compared: this is for the concurrent commit,
        // opposing-axes and register-stability monitors, and it is what puts a
        // pending mask change on a tick cycle.
        buttons_n = 4'hF;
        // Hold the direction row selected so the read-side opposing check is live
        // across the whole sweep, not only at the compared reads.
        write_select(2'b10);
        for (sweep_index = 0; sweep_index < 10; sweep_index = sweep_index + 1) begin
            sample_x = sweep[sweep_index];
            sample_y = sweep[9 - sweep_index];
            repeat (41) @(negedge clk_sys);
        end
        sample_x = 12'd1352; sample_y = 12'd1352; settle();
        expect_all_rows(8'h00);

        // Sensitize the register-stability witness: the JOYP button field moving
        // with no accepted mask and no select write.
        if (corrupt_state) begin
            force buttons_observe = 8'h20;
            repeat (3) @(negedge clk_sys);
            release buttons_observe;
        end

        if (commits == 0) $fatal(1, "CONTROLS_RUNNING_NO_COMMIT");
        if (updates == 0) $fatal(1, "CONTROLS_RUNNING_NO_UPDATE");
        if (deferrals == 0) $fatal(1, "CONTROLS_RUNNING_NO_DEFERRAL");
        if (seen_lines != 4'hF) $fatal(1, "CONTROLS_RUNNING_LINES seen=%0h", seen_lines);
        if (checks != 56) $fatal(1, "CONTROLS_RUNNING_COUNT actual=%0d", checks);
        $display("CONTROLS_RUNNING_CENSUS ticks=%0d commits=%0d updates=%0d deferrals=%0d coincident=%0d writes=%0d",
            ticks, commits, updates, deferrals, coincident, writes);
        $fclose(trace);
        $display("PASS CONTROLS_RUNNING reads=%0d checks=%0d lines=f", reads, checks);
        $finish;
    end
    initial begin #1000000; $fatal(1, "CONTROLS_RUNNING_WATCHDOG"); end
endmodule

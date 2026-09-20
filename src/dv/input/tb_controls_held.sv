`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// A button held across a core reset, on a composition with no host.
//
// `controls-running` composes the same actual producer, shared input owner, JOYP
// and running timebase, but assigns `core_reset` low once and never drives it, so
// the one arbitration this fixture exists for never happens there: the two owners
// do not lose the same state at a core reset. JOYP clears its button field; the
// input owner's physical shadow survives. The update that carries a mask between
// them is a difference, so a mask that did not change across the reset has to be
// re-offered from the level, or the held buttons stay invisible to the program.
//
// Two separate questions, both settled here by simulation.
//
// The mechanism: with a mask already published and read at FF00, a core reset must
// not lose it. Five phases pulse `core_reset` at different alignments and from
// different scheduling regions, because a missing event and a race would look the
// same in one phase only.
//
// The power-up ordering: on a host-free board the single power-up core reset lands
// before the button filter has accepted anything, so a switch held from power-on
// is delivered by the ordinary commit that follows. This fixture keeps that
// ordering in miniature and checks it, so the two cases stay distinguishable.
//
// Both inputs are the same actual module with the two values of
// PHYSICAL_SOURCE_DEFAULT, driven by one producer and one reset. The host-default
// instance is the qualified path: every reset exit must leave it released, which is
// what makes the physical instance's new update visibly local to the physical case.
// Eight-cycle debounce and a 32-cycle acquisition interval bound DV; the board's
// own filter and interval values are fit separately.
module tb_controls_held;
    logic clk_sys;
    logic reset_sys;
    logic core_reset;
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
    n2m_input_pkg::input_update_t physical_update;
    n2m_input_pkg::input_update_t host_update;
    logic [7:0] physical_host_buttons;
    logic [7:0] physical_shadow;
    logic [7:0] physical_source_observe;
    logic [7:0] physical_effective;
    logic [7:0] host_host_buttons;
    logic [7:0] host_shadow;
    logic [7:0] host_source_observe;
    logic [7:0] host_effective;
    logic io_commit;
    logic io_write;
    logic [7:0] io_wdata;
    logic physical_io_selected;
    logic [7:0] physical_rdata;
    logic [7:0] physical_observe;
    logic physical_active;
    logic physical_event;
    logic host_io_selected;
    logic [7:0] host_rdata;
    logic [7:0] host_observe;
    logic host_active;
    logic host_event;
    bit corrupt_held;
    integer cycle;
    integer reset_release_cycle;
    integer power_reset_cycle;
    integer first_commit_cycle;
    integer physical_updates;
    integer host_updates;
    integer reset_exits;
    integer checks;
    integer phase;
    integer trace;

    n2m_physical_controls #(.BUTTON_CYCLES(8), .INTERVAL_CYCLES(32), .LIMIT_CYCLES(256)) u_physical (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .gb_tick(gb_tick), .buttons_n(buttons_n),
        .adc_available(1'b1), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid), .response_channel(response_channel),
        .response_data(response_data), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .adc_fresh(adc_fresh), .adc_fault(adc_fault)
    );
    // The host-free composition: the physical producer is selected out of reset.
    n2m_input #(.PHYSICAL_SOURCE_DEFAULT(1'b1)) u_physical_input (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .host_write(host_write), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .host_buttons(physical_host_buttons), .physical_observe(physical_shadow),
        .source_observe(physical_source_observe), .effective_buttons(physical_effective),
        .effective_update(physical_update)
    );
    // The qualified composition every existing image uses: the host owns the
    // selection, so reset selects the host's own mask.
    n2m_input #(.PHYSICAL_SOURCE_DEFAULT(1'b0)) u_host_input (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .host_write(host_write), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .host_buttons(host_host_buttons), .physical_observe(host_shadow),
        .source_observe(host_source_observe), .effective_buttons(host_effective),
        .effective_update(host_update)
    );
    n2m_timebase u_timebase (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(1'b0), .gb_tick(gb_tick), .paused(paused)
    );
    n2m_joypad u_physical_joypad (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .input_commit(physical_update.valid), .input_buttons(physical_update.buttons),
        .io_commit(io_commit), .io_write(io_write), .io_address(n2m_interfaces_pkg::GB_REG_JOYP),
        .io_wdata(io_wdata), .io_selected(physical_io_selected), .io_rdata(physical_rdata),
        .buttons_observe(physical_observe), .selected_active(physical_active),
        .request_event(physical_event)
    );
    n2m_joypad u_host_joypad (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .input_commit(host_update.valid), .input_buttons(host_update.buttons),
        .io_commit(io_commit), .io_write(io_write), .io_address(n2m_interfaces_pkg::GB_REG_JOYP),
        .io_wdata(io_wdata), .io_selected(host_io_selected), .io_rdata(host_rdata),
        .buttons_observe(host_observe), .selected_active(host_active),
        .request_event(host_event)
    );

    assign command_ready = 1'b1;
    // Accepted command produces a next-edge sample; no vendor module is substituted.
    `DFF_ARST_VAL(response_valid, command_valid && command_ready, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(response_channel, command_channel, clk_sys, reset_sys, 5'd0)
    `DFF_ARST_VAL(response_data, command_channel == 5'd1 ? sample_x : sample_y, clk_sys, reset_sys, 12'd0)

    always #5 clk_sys = !clk_sys;

    // The census and the two rules the producer owes, sampled at the same edge the
    // owners' own assertions sample.
    always @(posedge clk_sys) if (!reset_sys) begin
        cycle = cycle + 1;
        if (physical_commit && gb_tick) $fatal(1, "CONTROLS_HELD_TICK_COMMIT mask=%02h", physical_buttons);
        if (adc_fault) $fatal(1, "CONTROLS_HELD_ADC_FAULT");
        if (core_reset && gb_tick) $fatal(1, "CONTROLS_HELD_TICK_IN_RESET");
        if (physical_commit && first_commit_cycle < 0) first_commit_cycle = cycle;
        if (core_reset && power_reset_cycle < 0) power_reset_cycle = cycle;
        if (physical_update.valid) physical_updates = physical_updates + 1;
        if (host_update.valid) host_updates = host_updates + 1;
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
    endtask

    // One read of FF00 on each owner: the physical composition must report the
    // mask it is holding, and the host composition must report released, because
    // nothing has selected the physical producer there.
    task automatic read_expect(input logic [1:0] row, input logic [7:0] mask,
                              input logic [7:0] host_mask);
        logic [7:0] expected;
        logic [7:0] host_expected;
        tick_edge();
        io_commit = 1'b1; io_write = 1'b0;
        expected = {2'b11, row, row_lines(mask, row)};
        host_expected = {2'b11, row, row_lines(host_mask, row)};
        if (corrupt_held && phase == 1 && row == 2'b00) force physical_observe = 8'h00;
        if (physical_rdata !== expected)
            $fatal(1, "CONTROLS_HELD_JOYP phase=%0d row=%0d expected=%02h actual=%02h check=%0d",
                phase, row, expected, physical_rdata, checks);
        if (physical_observe !== mask || physical_effective !== mask || physical_shadow !== mask)
            $fatal(1, "CONTROLS_HELD_MASK phase=%0d expected=%02h joypad=%02h effective=%02h shadow=%02h check=%0d",
                phase, mask, physical_observe, physical_effective, physical_shadow, checks);
        if (host_rdata !== host_expected || host_observe !== host_mask || host_effective !== host_mask)
            $fatal(1, "CONTROLS_HELD_HOST phase=%0d expected=%02h rdata=%02h joypad=%02h effective=%02h check=%0d",
                phase, host_mask, host_rdata, host_observe, host_effective, checks);
        // The host instance keeps the same physical shadow whichever source it
        // reports, which is the retention the contract already states.
        if (host_shadow !== mask)
            $fatal(1, "CONTROLS_HELD_HOST_SHADOW phase=%0d expected=%02h actual=%02h",
                phase, mask, host_shadow);
        if (physical_source_observe !== n2m_interfaces_pkg::INPUT_SOURCE_PHYSICAL)
            $fatal(1, "CONTROLS_HELD_SOURCE phase=%0d source=%02h", phase, physical_source_observe);
        if (paused || !adc_fresh)
            $fatal(1, "CONTROLS_HELD_STATE phase=%0d paused=%b fresh=%b", phase, paused, adc_fresh);
        $fdisplay(trace, "%0d,%0d,%0d,%02h,%02h,%02h,%0d,%0d", checks, phase, row, mask,
            physical_rdata, host_rdata, physical_updates, host_updates);
        checks = checks + 1;
        @(negedge clk_sys);
        io_commit = 1'b0;
        if (corrupt_held && phase == 1 && row == 2'b00) release physical_observe;
    endtask

    // One held mask read through every row selection, which is what the program
    // does to tell directions from actions.
    task automatic expect_all_rows(input logic [7:0] mask, input logic [7:0] host_mask);
        integer row_index;
        for (row_index = 0; row_index < 4; row_index = row_index + 1) begin
            write_select(2'(row_index));
            read_expect(2'(row_index), mask, host_mask);
        end
    endtask

    task automatic settle;
        repeat (140) @(negedge clk_sys);
    endtask

    // The four alignments. A lost update and a race would both show up as a lost
    // mask in one alignment, so the reset is driven from this initial block on a
    // negedge, from the same block one delay past a posedge, released between
    // edges, and as a single cycle. The mask is also changed while the reset is
    // held, because the producer never sees core reset and commits through it.
    task automatic reset_pulse(input integer alignment);
        case (alignment)
            0: begin
                @(negedge clk_sys); core_reset = 1'b1;
                repeat (4) @(negedge clk_sys); core_reset = 1'b0;
            end
            1: begin
                @(posedge clk_sys); #1 core_reset = 1'b1;
                repeat (4) @(posedge clk_sys); #1 core_reset = 1'b0;
            end
            2: begin
                @(negedge clk_sys); core_reset = 1'b1;
                repeat (4) @(negedge clk_sys); #2 core_reset = 1'b0;
            end
            3: begin
                @(negedge clk_sys); core_reset = 1'b1;
                @(negedge clk_sys); core_reset = 1'b0;
            end
            default: $fatal(1, "CONTROLS_HELD_ALIGNMENT %0d", alignment);
        endcase
        reset_exits = reset_exits + 1;
    endtask

    // A core reset with a mask held must cost exactly one update: the mask is
    // re-offered once and then stays quiet, because a repeated identical value
    // still creates no update.
    task automatic held_across_reset(input integer alignment, input logic [7:0] mask);
        integer before_physical;
        integer before_host;
        before_physical = physical_updates;
        before_host = host_updates;
        reset_pulse(alignment);
        settle();
        if (physical_updates - before_physical != 1)
            $fatal(1, "CONTROLS_HELD_UPDATES phase=%0d actual=%0d", phase,
                physical_updates - before_physical);
        if (host_updates != before_host)
            $fatal(1, "CONTROLS_HELD_HOST_UPDATES phase=%0d actual=%0d", phase,
                host_updates - before_host);
        expect_all_rows(mask, 8'h00);
    endtask

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, paused, buttons_n, sample_x, sample_y,
            physical_commit, physical_buttons, adc_fresh, adc_fault, host_write,
            physical_update, physical_shadow, physical_source_observe, physical_effective,
            host_update, host_shadow, host_source_observe, host_effective,
            io_commit, io_write, io_wdata, physical_rdata, physical_observe, physical_active,
            physical_event, host_rdata, host_observe, host_active, host_event);
        trace = $fopen("held.csv", "w");
        clk_sys = 1'b0; reset_sys = 1'b1; core_reset = 1'b0;
        // The button is held before power is applied, which is what a slide switch
        // left up means, and the axes stay centred throughout.
        buttons_n = 4'hE; sample_x = 12'd1352; sample_y = 12'd1352;
        io_commit = 1'b0; io_write = 1'b0; io_wdata = 8'd0;
        host_write = '0;
        cycle = 0; reset_release_cycle = -1; power_reset_cycle = -1; first_commit_cycle = -1;
        physical_updates = 0; host_updates = 0; reset_exits = 0; checks = 0; phase = 0;
        corrupt_held = $test$plusargs("CORRUPT_HELD");
        repeat (8) @(negedge clk_sys);
        reset_sys = 1'b0;
        reset_release_cycle = 0;

        // Phase 0, the power-up ordering. The host-free start path issues its one
        // core reset two cycles after the global reset releases, and the button
        // filter cannot have accepted anything by then: on the board the window is
        // 125000 cycles against those 2, and here 8 against the same 2. So the
        // held switch arrives on the ordinary commit that follows, and this is why
        // the DE2-115 power-up case is not the case the mechanism breaks.
        @(negedge clk_sys); @(negedge clk_sys);
        core_reset = 1'b1;
        @(negedge clk_sys);
        core_reset = 1'b0;
        reset_exits = reset_exits + 1;
        settle();
        if (paused) $fatal(1, "CONTROLS_HELD_STILL_PAUSED");
        if (power_reset_cycle < 0 || first_commit_cycle < 0)
            $fatal(1, "CONTROLS_HELD_NO_ORDER reset=%0d commit=%0d",
                power_reset_cycle, first_commit_cycle);
        if (first_commit_cycle <= power_reset_cycle)
            $fatal(1, "CONTROLS_HELD_ORDER reset=%0d commit=%0d",
                power_reset_cycle, first_commit_cycle);
        expect_all_rows(8'h10, 8'h00);

        // Phases 1 to 4, the mechanism, at four alignments with the same mask.
        for (phase = 1; phase <= 4; phase = phase + 1)
            held_across_reset(phase - 1, 8'h10);

        // Phase 5: the mask changes while the reset is held. The producer never
        // sees core reset, so it commits through it, and the reset exit must carry
        // the new mask rather than the old one.
        phase = 5;
        @(negedge clk_sys); core_reset = 1'b1;
        repeat (2) @(negedge clk_sys);
        buttons_n = 4'h0;
        repeat (20) @(negedge clk_sys);
        core_reset = 1'b0;
        reset_exits = reset_exits + 1;
        settle();
        expect_all_rows(8'hF0, 8'h00);

        // Phase 6: the host path is still the host's. A source write selects the
        // physical producer on the host-default instance, which is the change that
        // has always carried the mask there, and a mask write then replaces it.
        phase = 6;
        @(negedge clk_sys);
        while (gb_tick) @(negedge clk_sys);
        host_write = '{valid: 1'b1, source_write: 1'b1, value: 8'd1};
        @(negedge clk_sys);
        host_write = '0;
        settle();
        if (host_source_observe !== n2m_interfaces_pkg::INPUT_SOURCE_PHYSICAL)
            $fatal(1, "CONTROLS_HELD_HOST_SELECT source=%02h", host_source_observe);
        expect_all_rows(8'hF0, 8'hF0);

        // Phase 7: and a core reset takes that selection back to the host's own
        // mask, which is released, exactly as it did before. The physical
        // composition beside it keeps reporting the held buttons.
        phase = 7;
        held_across_reset(0, 8'hF0);
        if (host_source_observe !== n2m_interfaces_pkg::INPUT_SOURCE_UART)
            $fatal(1, "CONTROLS_HELD_HOST_DEFAULT source=%02h", host_source_observe);

        // Released buttons read as all lines high on both, and the reset exit then
        // costs no update at all, because there is nothing held to re-offer.
        phase = 8;
        buttons_n = 4'hF;
        settle();
        expect_all_rows(8'h00, 8'h00);
        begin
            integer before_physical;
            before_physical = physical_updates;
            reset_pulse(0);
            settle();
            if (physical_updates != before_physical)
                $fatal(1, "CONTROLS_HELD_IDLE_UPDATE actual=%0d",
                    physical_updates - before_physical);
            expect_all_rows(8'h00, 8'h00);
        end

        if (reset_exits != 8) $fatal(1, "CONTROLS_HELD_RESETS actual=%0d", reset_exits);
        if (checks != 40) $fatal(1, "CONTROLS_HELD_COUNT actual=%0d", checks);
        $display("CONTROLS_HELD_CENSUS power_reset=%0d first_commit=%0d resets=%0d physical_updates=%0d host_updates=%0d",
            power_reset_cycle, first_commit_cycle, reset_exits, physical_updates, host_updates);
        $fclose(trace);
        $display("PASS CONTROLS_HELD resets=%0d checks=%0d", reset_exits, checks);
        $finish;
    end
    initial begin #1000000; $fatal(1, "CONTROLS_HELD_WATCHDOG"); end
endmodule

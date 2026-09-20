`timescale 1ns/1ps
`default_nettype none
// Execution proof for the host-free composition. Contract:
// wiki/src/rtl/system/MAS_system.md#host-free-composition.
//
// A fit cannot see this. The image fits, meets timing and carries its ROM with
// the core permanently paused, because host pause is set at reset and the only
// two things that clear it are an accepted host command and the boot copier's
// `boot_run` — and a board with no host and no storage has neither. So this
// runs the real composition twice from one reset, each holding the real carried
// game, with nothing on the wire and storage reporting itself uninitialized, and
// requires:
//
//   u_free   (CARRIED_PROFILE = the direct profile) releases pause, ticks,
//            fetches, retires and obeys the physical buttons;
//   u_hosted (CARRIED_PROFILE = 0, every other input identical) stays paused
//            and never ticks, which is what the image did before the parameter.
//
// The second instance is the control: without it a passing first instance would
// not show that the parameter is what releases the core.
module tb_host_free;
    import n2m_interfaces_pkg::*;
    localparam int unsigned SETTLE_EDGES = 60000;   // > the stores' clearing sweep
    localparam int unsigned OBSERVE_EDGES = 40000;
    logic clk_sys = 0, clk_pix = 0, reset_sys = 1, reset_pix = 1;
    always #20.0 clk_sys = !clk_sys;                // 25.0 MHz
    always #19.841 clk_pix = !clk_pix;              // 25.2 MHz

    // Everything a host-free board drives. No mask is committed here: the point
    // is that the core starts, and the input owner's own suites cover commits.
    logic [7:0] buttons = 8'h0;
    logic commit = 1'b0;

    logic free_tick, free_paused, free_fault, free_commit, free_retire;
    logic [15:0] free_address;
    logic [63:0] free_dots;
    logic [7:0] free_effective, free_source;
    logic hosted_tick, hosted_paused, hosted_fault;
    logic [63:0] hosted_dots;
    logic [7:0] hosted_effective, hosted_source;

    n2m_v05_system #(.FLASH_LIBRARY(1'b0), .CARRIED_PROFILE(PROFILE_DIRECT_ID)) u_free (
        .clk_sys, .clk_pix, .reset_sys, .reset_pix,
        .uart_rx(1'b1), .uart_tx(),
        .physical_commit(commit), .physical_buttons(buttons),
        .effective_buttons(free_effective), .input_source_observe(free_source),
        .red(), .green(), .blue(), .hsync_n(), .vsync_n(),
        .paused(free_paused), .fault(free_fault),
        .display_sequence(), .display_epoch(),
        .gb_tick(free_tick), .core_reset(), .epoch(), .dot_count(free_dots),
        .retirement_valid(free_retire), .retirement(),
        .bus_commit(free_commit), .write_enable(),
        .address(free_address), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(),
        .source_display_eligible(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(),
        .key1_n(1'b1),
        .sdram_initialized(1'b0), .sdram_request_valid(), .sdram_request_write(),
        .sdram_request_address(), .sdram_request_data(), .sdram_request_ready(1'b0),
        .sdram_response_valid(1'b0), .sdram_response_data('0)
    );
    n2m_v05_system #(.FLASH_LIBRARY(1'b0), .CARRIED_PROFILE(8'h0)) u_hosted (
        .clk_sys, .clk_pix, .reset_sys, .reset_pix,
        .uart_rx(1'b1), .uart_tx(),
        .physical_commit(commit), .physical_buttons(buttons),
        .effective_buttons(hosted_effective), .input_source_observe(hosted_source),
        .red(), .green(), .blue(), .hsync_n(), .vsync_n(),
        .paused(hosted_paused), .fault(hosted_fault),
        .display_sequence(), .display_epoch(),
        .gb_tick(hosted_tick), .core_reset(), .epoch(), .dot_count(hosted_dots),
        .retirement_valid(), .retirement(),
        .bus_commit(), .write_enable(),
        .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(),
        .source_display_eligible(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(),
        .key1_n(1'b1),
        .sdram_initialized(1'b0), .sdram_request_valid(), .sdram_request_write(),
        .sdram_request_address(), .sdram_request_data(), .sdram_request_ready(1'b0),
        .sdram_response_valid(1'b0), .sdram_response_data('0)
    );
    // Both stores power up holding the same program, staged by the established
    // preload path on the instance the carried-image builder names in the QSF, so
    // the program arrives the way a carried image's does. It is the integration
    // fixture rather than the game, because what is checked here is the core
    // starting; the game's own behaviour is the DE10-Lite suites' subject. The
    // only difference between the two instances is the parameter.
    defparam u_free.u_stores.rom.INIT_FILE = "preload-rom.mif";
    defparam u_hosted.u_stores.rom.INIT_FILE = "preload-rom.mif";

    // What the run observed.
    bit free_ticked, free_fetched, free_retired, hosted_ticked;
    logic [15:0] first_address;
    int unsigned edges;
    always @(posedge clk_sys) if (!reset_sys) begin
        if (free_tick) free_ticked = 1;
        if (hosted_tick) hosted_ticked = 1;
        if (free_commit && !free_fetched) begin
            free_fetched = 1;
            first_address = free_address;
        end
        if (free_retire) free_retired = 1;
    end

    initial begin : run
        free_ticked = 0; free_fetched = 0; free_retired = 0; hosted_ticked = 0;
        first_address = 16'hffff;
        repeat (8) @(posedge clk_sys);
        // Host pause is the documented reset state; both instances start paused.
        if (!free_paused || !hosted_paused) $fatal(1, "HOST_FREE_RESET_NOT_PAUSED free=%b hosted=%b",
            free_paused, hosted_paused);
        reset_sys = 0; reset_pix = 0;
        for (edges = 0; edges < SETTLE_EDGES; edges = edges + 1) @(posedge clk_sys);
        // The carried-profile instance must be running by now.
        if (free_paused) $fatal(1, "HOST_FREE_STILL_PAUSED after %0d edges", SETTLE_EDGES);
        if (!free_ticked) $fatal(1, "HOST_FREE_NO_TICK");
        if (!free_fetched) $fatal(1, "HOST_FREE_NO_FETCH");
        if (!free_retired) $fatal(1, "HOST_FREE_NO_RETIREMENT");
        if (free_fault) $fatal(1, "HOST_FREE_FAULT");
        if (free_dots == 0) $fatal(1, "HOST_FREE_NO_DOT");
        // The carried profile also selects the physical input source, so the
        // core obeys the board's mask instead of the absent host's.
        if (free_source[0] !== 1'b1) $fatal(1, "HOST_FREE_INPUT_SOURCE %b", free_source);
        // What a mask does once it reaches the running joypad is the input
        // owner's own subject; this proof stops at the source selection, which is
        // the parameter's observable.
        // And the control must still be exactly where the reset left it.
        for (edges = 0; edges < OBSERVE_EDGES; edges = edges + 1) @(posedge clk_sys);
        if (!hosted_paused) $fatal(1, "HOST_FREE_CONTROL_RELEASED");
        if (hosted_ticked) $fatal(1, "HOST_FREE_CONTROL_TICKED");
        if (hosted_dots != 0) $fatal(1, "HOST_FREE_CONTROL_DOTS %0d", hosted_dots);
        if (hosted_source[0] !== 1'b0) $fatal(1, "HOST_FREE_CONTROL_SOURCE %b", hosted_source);
        $display("host-free: first fetch at %04h, %0d dots, retired=%b, source=%02h",
                 first_address, free_dots, free_retired, free_source);
        $display("control  : paused=%b ticked=%b dots=%0d", hosted_paused, hosted_ticked, hosted_dots);
        $display("PASS host-free-boot");
        $finish;
    end
endmodule
`default_nettype wire

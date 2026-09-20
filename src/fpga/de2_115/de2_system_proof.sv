`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// DE2-115 system image: the Game Boy composition bound to this board's pins,
// carrying its own program, with no host connection of any kind.
//
// `n2m_v05_system` is board-independent and is instantiated unchanged. ALTPLL
// serves Cyclone IV E, so `u_clocking` is the DE10-Lite's
// src/fpga/de10_lite/n2m_clocking.sv in place, the same instance and hierarchy
// every clocking check names (src/fpga/de2_115/README.md).
//
// What this top owns is the board side, and only that:
//   - the picture on the ADV7123 video DAC, the alignment and control values of
//     wiki/src/de2-115-board.md#driving-the-vga-dac, identical to de2_vga_proof;
//   - the controls, from this board's own KEY buttons and SW switches;
//   - the readout, 32 bits of hexadecimal on HEX0 to HEX7;
//   - termination of the two interfaces this board does not have, the host UART
//     and SDRAM, each driven to its inactive value rather than left floating.
//
// Pins and their provenance: wiki/src/de2-115-board.md.
// Readout and control scheme: wiki/src/de2-115-board.md#the-on-board-readout.
module de2_system_proof #(
`ifdef N2M_V05_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_V05_BUILD_ID,
`else
    parameter logic [127:0] BUILD_ID = 128'h88000000000000000000000000000001,
`endif
`ifdef N2M_DE2_ROM_CRC32
    parameter logic [31:0] ROM_CRC32 = `N2M_DE2_ROM_CRC32,
`else
    parameter logic [31:0] ROM_CRC32 = 32'h00000000,
`endif
    // 5 ms at 25 MHz, the debounce the physical control producer uses.
    parameter int unsigned BUTTON_CYCLES = 125000
) (
    input var logic clk_reference,          // CLOCK_50
    input var logic board_reset_n,          // KEY[0], low while pressed
    input var logic [1:0] key_action_n,     // KEY[2], KEY[3], low while pressed
    input var logic [7:0] sw_buttons,       // SW[7:0], high while away from the edge
    input var logic [2:0] sw_view,          // SW[10:8], high while away from the edge
    output logic [6:0] hex0_n, hex1_n, hex2_n, hex3_n,
    output logic [6:0] hex4_n, hex5_n, hex6_n, hex7_n,
    output logic [7:0] vga_r, vga_g, vga_b,
    output logic vga_hs, vga_vs,
    output logic vga_clk, vga_blank_n, vga_sync_n,
    output logic paused, fault,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch
);
    logic clk_sys, clk_pix, reset_sys, reset_pix;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    n2m_clocking u_clocking (
        .clk_reference, .board_reset_n, .clk_sys, .clk_pix,
        .reset_sys, .reset_pix, .ready()
    );

    // ---- Controls: this board's own buttons and switches -------------------
    // Every asynchronous control input reaches the system through the shared
    // button filter, and KEY[0] reaches the reset controller's own checked
    // stages instead: two forced synchronizer stages and the same 5 ms stable
    // window the physical control producer requires. The vendor states these
    // slide switches "are not debounced" and the FPGA pin is the contact, so
    // without that window a switch's bounce would present half-formed masks to
    // the input owner; the push-buttons are debounced on the board and pass the
    // same filter unharmed. The filter takes four active-low inputs, so the
    // thirteen inputs use four instances and the unused slots are held released.
    logic [3:0] switch_low, switch_high, key_pressed, view_pressed;
    n2m_button_filter #(.STABLE_CYCLES(BUTTON_CYCLES)) u_switch_low (
        .clk_sys, .reset_sys, .buttons_n(~sw_buttons[3:0]),
        .pressed(), .accepted_pressed(switch_low));
    n2m_button_filter #(.STABLE_CYCLES(BUTTON_CYCLES)) u_switch_high (
        .clk_sys, .reset_sys, .buttons_n(~sw_buttons[7:4]),
        .pressed(), .accepted_pressed(switch_high));
    n2m_button_filter #(.STABLE_CYCLES(BUTTON_CYCLES)) u_keys (
        .clk_sys, .reset_sys, .buttons_n({2'b11, key_action_n}),
        .pressed(), .accepted_pressed(key_pressed));
    n2m_button_filter #(.STABLE_CYCLES(BUTTON_CYCLES)) u_view (
        .clk_sys, .reset_sys, .buttons_n({1'b1, ~sw_view}),
        .pressed(), .accepted_pressed(view_pressed));

    // The shared mask is R, L, U, D, A, B, Select, Start
    // (n2m_interfaces_pkg::BUTTON_*). SW[7:0] hold the eight of them in that
    // order; KEY[3] and KEY[2] add momentary A and B, because a platformer's
    // jump is a press rather than a position.
    logic [7:0] switch_mask, key_mask, requested, desired;
    logic [7:0] published_q;
    logic gb_tick, physical_commit;
    logic [7:0] physical_buttons, effective_buttons, input_source_observe;
    logic [31:0] epoch;
    logic [63:0] dot_count;
    assign switch_mask = {switch_high, switch_low};
    assign key_mask = {2'b0, key_pressed[0], key_pressed[1], 4'b0};
    assign requested = switch_mask | key_mask;
    // A d-pad cannot present both of an opposing pair and the DMG's own matrix
    // never reports one; two slide switches can. Both are dropped, which is the
    // rule the physical control producer asserts (controls_opposing_axes).
    always_comb begin
        desired = requested;
        if (&requested[1:0]) desired[1:0] = 2'b00;
        if (&requested[3:2]) desired[3:2] = 2'b00;
    end
    // The input owner accepts a whole mask on an edge that carries no emulated
    // tick, so the commit is the change itself, off the tick.
    assign physical_buttons = reset_sys ? 8'd0 : desired;
    assign physical_commit = !reset_sys && !gb_tick && desired != published_q;
    `DFF_ARST_VAL(published_q, physical_commit ? desired : published_q, clk_sys, reset_sys, 8'd0)

    // ---- The composition --------------------------------------------------
    // Interfaces this board does not have, and how each is terminated.
    //
    // uart_rx: held at the line's idle mark. A UART receiver reads a start bit
    // as a fall from mark, so a constant 1 is the one value that can never
    // begin a frame. Floating it would let board noise assemble a command.
    // uart_tx is left unconnected: this board's RS-232 port has no cable on
    // this bench, and placing a pin on it would state a link that is not there.
    //
    // key1_n: held released. It is the loader profile's return-to-menu button,
    // and this image carries one program with no library to return to; a return
    // request would invalidate the running image with no path to restore it.
    // Not exposing it is what keeps that unreachable.
    //
    // sdram_initialized low and sdram_request_ready low: this board's SDRAM is
    // not placed, so there is no storage. Reporting it uninitialized is what
    // keeps the loader's copy engine, the boot copier and the host bridge idle;
    // refusing every request is what makes a request that did reach the bus
    // stall visibly instead of being accepted and dropped. The request outputs
    // are left unconnected, and the project reserves every unused package pin
    // as a tri-stated input, so the board's SDRAM devices meet high impedance.
    n2m_v05_system #(.BUILD_ID(BUILD_ID)) u_system (
        .clk_sys, .clk_pix, .reset_sys, .reset_pix,
        .uart_rx(1'b1), .uart_tx(),
        .physical_commit, .physical_buttons, .effective_buttons, .input_source_observe,
        .red, .green, .blue, .hsync_n, .vsync_n, .paused, .fault,
        .display_sequence, .display_epoch,
        .gb_tick, .core_reset(), .epoch, .dot_count,
        .retirement_valid(), .retirement(), .bus_commit(), .write_enable(),
        .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(),
        .source_display_eligible(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(),
        .key1_n(1'b1),
        .sdram_initialized(1'b0), .sdram_request_valid(), .sdram_request_write(),
        .sdram_request_address(), .sdram_request_data(), .sdram_request_ready(1'b0),
        .sdram_response_valid(1'b0), .sdram_response_data('0)
    );

    // ---- The on-board readout ---------------------------------------------
    // Eight digits are 32 bits of hexadecimal, and this board has no host to
    // ask, so the switches choose which 32 bits. Every one of the eight
    // selections is defined, so no switch position leaves the display stating
    // something undefined. HEX7 carries the most significant nibble and HEX0 the
    // least; which physical digit each of those is on the board is not
    // established by the vendor manual, so which end to start reading from is a
    // bring-up observation (wiki/src/de2-115-board.md#the-on-board-readout).
    //
    // 0 to 3 are the 128-bit build identity, most significant word first: this
    // answers which image is running, the question the host `ping` answers on a
    // board that has a host. 4 is the CRC-32 of the ROM the build put in the
    // bitstream, to compare against the build record. 5 to 7 are the three
    // running facts a person at the board cannot otherwise see.
    logic [31:0] view_value, view_q;
    always_comb begin
        case (view_pressed[2:0])
            3'd0: view_value = BUILD_ID[127:96];
            3'd1: view_value = BUILD_ID[95:64];
            3'd2: view_value = BUILD_ID[63:32];
            3'd3: view_value = BUILD_ID[31:0];
            3'd4: view_value = ROM_CRC32;
            // Emulated dots elapsed: a still number means the core is not
            // running, whatever the monitor shows. This and the epoch are the
            // composition's own system-domain counters, not the frame bridge's
            // pixel-domain ones: these digits are clocked in clk_sys, and
            // sampling a 32-bit pixel-domain counter here would be an
            // unsynchronized crossing between two unrelated clocks, which both
            // tears the number and adds a path the analysis cannot meet.
            3'd5: view_value = dot_count[31:0];
            3'd6: view_value = epoch;
            // {fault, paused, which input source the core obeys, the mask it
            // obeys}. A lit fault digit explains a frozen picture on its own.
            3'd7: view_value = {14'b0, fault, paused, input_source_observe, effective_buttons};
            default: view_value = 32'h0;
        endcase
    end
    `DFF_ARST_VAL(view_q, view_value, clk_sys, reset_sys, 32'h0)
    de2_hex_digit u_hex0 (.value(view_q[3:0]),   .segments_n(hex0_n));
    de2_hex_digit u_hex1 (.value(view_q[7:4]),   .segments_n(hex1_n));
    de2_hex_digit u_hex2 (.value(view_q[11:8]),  .segments_n(hex2_n));
    de2_hex_digit u_hex3 (.value(view_q[15:12]), .segments_n(hex3_n));
    de2_hex_digit u_hex4 (.value(view_q[19:16]), .segments_n(hex4_n));
    de2_hex_digit u_hex5 (.value(view_q[23:20]), .segments_n(hex5_n));
    de2_hex_digit u_hex6 (.value(view_q[27:24]), .segments_n(hex6_n));
    de2_hex_digit u_hex7 (.value(view_q[31:28]), .segments_n(hex7_n));

    // ---- The picture on the video DAC -------------------------------------
    // Identical to de2_vga_proof's board side, and for the same reasons; the
    // derivation of every value here is
    // wiki/src/de2-115-board.md#driving-the-vga-dac. Four bits of shade become
    // eight DAC bits by repeating the nibble, which is the exact linear map
    // b(v) = 17v. BLANK stays high because a Logic 0 makes the DAC ignore the
    // pixel inputs and the scan already blanks by driving zero; SYNC is tied low
    // because sync leaves on its own pins; CLOCK is the pixel clock inverted, so
    // the DAC's latching edge falls half a pixel period after the data.
    assign vga_r = {red, red};
    assign vga_g = {green, green};
    assign vga_b = {blue, blue};
    assign vga_hs = hsync_n;
    assign vga_vs = vsync_n;
    assign vga_clk = ~clk_pix;
    assign vga_blank_n = 1'b1;
    assign vga_sync_n = 1'b0;
endmodule
`default_nettype wire

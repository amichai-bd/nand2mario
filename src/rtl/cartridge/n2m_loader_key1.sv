`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// KEY1 return-to-menu detector. Contract:
// wiki/src/rtl/cartridge/MAS_loader_profile.md#key1-return.
// Two clk_sys flops synchronize the active-low pin, the level must hold for
// DEBOUNCE_EDGES before the debounced level changes, and a debounced press
// of exactly HOLD_EDGES raises one return_event; the hold counter then stops
// until release. Global reset clears every stage.
module n2m_loader_key1 #(
    parameter int unsigned DEBOUNCE_EDGES = 32'(n2m_interfaces_pkg::LIBRARY_KEY1_DEBOUNCE_EDGES),
    parameter int unsigned HOLD_EDGES = 32'(n2m_interfaces_pkg::LIBRARY_KEY1_HOLD_EDGES)
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic key1_n,
    output logic pressed,
    output logic return_event,
    output logic [31:0] hold_count
);
    localparam int unsigned DEBOUNCE_BITS = $clog2(DEBOUNCE_EDGES + 1);
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic key_meta;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic key_sync;
    logic [DEBOUNCE_BITS-1:0] stable_count, stable_next;
    logic pressed_next;
    logic [31:0] hold_next;
    logic event_next;

    `DFF_ARST_VAL(key_meta, key1_n, clk_sys, reset_sys, 1'b1)
    `DFF_ARST_VAL(key_sync, key_meta, clk_sys, reset_sys, 1'b1)
    // The synchronized level is pressed when low. The count restarts on every
    // return to the debounced level, so a shorter glitch changes nothing.
    always_comb begin
        stable_next = stable_count;
        pressed_next = pressed;
        if ((!key_sync) == pressed) stable_next = '0;
        else if (stable_count == DEBOUNCE_BITS'(DEBOUNCE_EDGES - 1)) begin
            pressed_next = !key_sync;
            stable_next = '0;
        end else stable_next = stable_count + DEBOUNCE_BITS'(1);
    end
    `DFF_ARST_VAL(stable_count, stable_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(pressed, pressed_next, clk_sys, reset_sys, 1'b0)
    // The hold counter counts debounced press edges and saturates at
    // HOLD_EDGES; the edge that reaches it is the one return event.
    always_comb begin
        hold_next = hold_count;
        event_next = 1'b0;
        if (!pressed) hold_next = '0;
        else if (hold_count < HOLD_EDGES) begin
            hold_next = hold_count + 32'd1;
            event_next = hold_count == HOLD_EDGES - 1;
        end
    end
    `DFF_ARST_VAL(hold_count, hold_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(return_event, event_next, clk_sys, reset_sys, 1'b0)
    `N2M_ASSERT(LOADER_KEY1_THRESHOLD, clk_sys, reset_sys,
        return_event |-> hold_count == HOLD_EDGES && $past(hold_count) == HOLD_EDGES - 1)
    `N2M_ASSERT(LOADER_KEY1_HOLD_RANGE, clk_sys, reset_sys, hold_count <= HOLD_EDGES)
    `N2M_ASSERT(LOADER_KEY1_DEBOUNCE_RANGE, clk_sys, reset_sys,
        stable_count < DEBOUNCE_BITS'(DEBOUNCE_EDGES))
endmodule
`default_nettype wire

`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Contract: wiki/src/clocks-resets-cdc.md (reset and run control).
module n2m_reset_control (
    input  logic clk_sys,
    input  logic clk_pix,
    input  logic board_reset_n,
    input  logic pll_locked,
    output logic pll_areset,
    output logic ready,
    output logic reset_sys,
    output logic reset_pix
);
    // Constant initialization is part of the MAX 10 configuration contract.
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] board_release;
    logic [18:0] release_count;
    logic [18:0] release_count_next;
    logic pll_areset_next;
    always_comb begin
        release_count_next = release_count;
        pll_areset_next = pll_areset;
        if (pll_areset) begin
            if (release_count == 19'd499999) pll_areset_next = 1'b0;
            else release_count_next = release_count + 19'd1;
        end
    end
    `DFF_INIT_ARST_N_VAL(board_release, {board_release[0], 1'b1}, clk_sys, board_reset_n, 2'b00)
    `DFF_INIT_ARST_N_VAL(release_count, release_count_next, clk_sys, board_release[1], 19'd0)
    `DFF_INIT_ARST_N_VAL(pll_areset, pll_areset_next, clk_sys, board_release[1], 1'b1)

    wire lock_reset;
    assign lock_reset = pll_areset || !pll_locked;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] lock_samples;
    logic [9:0] lock_count;
    logic [9:0] lock_count_next;
    logic ready_next;
    always_comb begin
        lock_count_next = lock_count;
        ready_next = ready;
        if (!ready) begin
            if (lock_count == 10'd1023) ready_next = 1'b1;
            else lock_count_next = lock_count + 10'd1;
        end
    end
    `DFF_INIT_ARST_VAL(lock_samples, {lock_samples[0], 1'b1}, clk_sys, lock_reset, 2'b00)
    `DFF_INIT_ARST_N_VAL(lock_count, lock_count_next, clk_sys, lock_samples[1], 10'd0)
    `DFF_INIT_ARST_N_VAL(ready, ready_next, clk_sys, lock_samples[1], 1'b0)

    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] sys_release;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] pix_release;
    `DFF_INIT_ARST_N_VAL(sys_release, {sys_release[0], 1'b1}, clk_sys, ready, 2'b00)
    `DFF_INIT_ARST_N_VAL(pix_release, {pix_release[0], 1'b1}, clk_pix, ready, 2'b00)
    assign reset_sys = !sys_release[1];
    assign reset_pix = !pix_release[1];
    `N2M_ASSERT(release_count_in_range, clk_sys, !board_release[1], release_count <= 19'd499999)
    `N2M_ASSERT_KNOWN(reset_control_known, clk_sys, !board_release[1], {release_count, pll_areset, lock_count, ready})
    `N2M_ASSERT_NEVER(no_ready_during_pll_reset, clk_sys, !board_release[1], ready && pll_areset)
    `N2M_ASSERT_STABLE_WHEN(release_count_holds, clk_sys, !board_release[1], !pll_areset, release_count)
    `N2M_ASSERT_STABLE_WHEN(lock_count_holds, clk_sys, !lock_samples[1], ready, lock_count)
endmodule

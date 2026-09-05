`timescale 1ns/1ps
// Contract: wiki/src/clocks-resets-cdc.md (reset and run control).
module n2m_reset_control (
    input  logic clk_sys,
    input  logic clk_pix,
    input  logic board_reset_n,
    input  logic pll_locked,
    output logic pll_areset = 1'b1,
    output logic ready = 1'b0,
    output logic reset_sys,
    output logic reset_pix
);
    // Constant initialization is part of the MAX 10 configuration contract.
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] board_release = 2'b00;
    logic [18:0] release_count = 19'd0;
    always_ff @(posedge clk_sys or negedge board_reset_n) begin
        if (!board_reset_n) board_release <= 2'b00;
        else board_release <= {board_release[0], 1'b1};
    end
    always_ff @(posedge clk_sys or negedge board_release[1]) begin
        if (!board_release[1]) begin
            release_count <= 19'd0;
            pll_areset <= 1'b1;
        end else if (pll_areset) begin
            if (release_count == 19'd499999) pll_areset <= 1'b0;
            else release_count <= release_count + 19'd1;
        end
    end

    wire lock_reset = pll_areset || !pll_locked;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] lock_samples = 2'b00;
    logic [9:0] lock_count = 10'd0;
    always_ff @(posedge clk_sys or posedge lock_reset) begin
        if (lock_reset) lock_samples <= 2'b00;
        else lock_samples <= {lock_samples[0], 1'b1};
    end
    always_ff @(posedge clk_sys or negedge lock_samples[1]) begin
        if (!lock_samples[1]) begin
            lock_count <= 10'd0;
            ready <= 1'b0;
        end else if (!ready) begin
            if (lock_count == 10'd1023) ready <= 1'b1;
            else lock_count <= lock_count + 10'd1;
        end
    end

    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] sys_release = 2'b00;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] pix_release = 2'b00;
    always_ff @(posedge clk_sys or negedge ready) begin
        if (!ready) sys_release <= 2'b00;
        else sys_release <= {sys_release[0], 1'b1};
    end
    always_ff @(posedge clk_pix or negedge ready) begin
        if (!ready) pix_release <= 2'b00;
        else pix_release <= {pix_release[0], 1'b1};
    end
    assign reset_sys = !sys_release[1];
    assign reset_pix = !pix_release[1];
endmodule

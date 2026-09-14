`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Simulation double for the generated n2m_adc_pll (altpll) selected by
// n2m_adc_backend under the predefined VERILATOR macro. Quartus never sees it.
// Contract: wiki/src/fpga-controls.md.
//
// c0 runs at INPUT_PERIOD_PS * DIVIDE / MULTIPLY while areset is low and is
// held low during areset. locked rises LOCK_CYCLES input edges after areset
// falls and drops at once when areset rises. The input clock must match the
// configured period; a different reference clock is a named failure.
module n2m_sim_adc_pll #(
    parameter integer INPUT_PERIOD_PS = 100000,
    parameter integer MULTIPLY = 1,
    parameter integer DIVIDE = 1,
    parameter integer LOCK_CYCLES = 64
) (
    input var logic areset,
    input var logic inclk0,
    output logic c0,
    output logic locked
);
    localparam real INPUT_PERIOD_NS = INPUT_PERIOD_PS / 1000.0;
    localparam real HALF_PERIOD_NS = INPUT_PERIOD_PS * DIVIDE / (2000.0 * MULTIPLY);
    logic [31:0] lock_count;
    logic [31:0] lock_count_next;
    logic locked_next;
    real last_edge_ns;
    real period_ns;

    // Output clock: statically known half period so the schedule is exact.
    initial begin
        c0 = 1'b0;
        forever begin
            if (areset) begin
                c0 = 1'b0;
                @(negedge areset);
            end else begin
                #(HALF_PERIOD_NS);
                if (!areset) c0 = !c0;
            end
        end
    end

    assign lock_count_next = locked ? lock_count : lock_count + 32'd1;
    assign locked_next = locked || lock_count >= 32'(LOCK_CYCLES);
    `DFF_ARST_VAL(lock_count, lock_count_next, inclk0, areset, 32'd0)
    `DFF_ARST_VAL(locked, locked_next, inclk0, areset, 1'b0)

    // Reference period observation. The first edge has no predecessor, and a
    // time-zero X-to-value edge under --x-initial-edge is not a clock edge.
    initial begin
        last_edge_ns = 0.0;
        period_ns = INPUT_PERIOD_NS;
    end
    always @(posedge inclk0) begin
        if ($realtime > 0.0) begin
            if (last_edge_ns > 0.0) period_ns = $realtime - last_edge_ns;
            last_edge_ns = $realtime;
        end
    end
    `N2M_ASSERT_NO_RST(SIM_PLL_INPUT_PERIOD, inclk0,
        period_ns > INPUT_PERIOD_NS * 0.99 && period_ns < INPUT_PERIOD_NS * 1.01)
    `N2M_ASSERT_NO_RST(SIM_PLL_CONFIGURATION, inclk0,
        INPUT_PERIOD_PS > 0 && MULTIPLY > 0 && DIVIDE > 0 && LOCK_CYCLES > 0)
endmodule

`default_nettype none
`include "src/rtl/common/macros.svh"

// Digital CPU transaction boundary. Preparation has no architectural effects.
module n2m_cpu_bus (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic active,
    input var logic complete_enable,
    input var logic [15:0] plan_address,
    input var logic [7:0] plan_write_data,
    input var logic plan_write,
    input var n2m_cpu_pkg::access_kind_t plan_kind,
    input var logic response_valid,
    output logic [1:0] phase,
    output logic request_valid,
    output logic [15:0] address,
    output logic [7:0] write_data,
    output logic write_enable,
    output n2m_cpu_pkg::access_kind_t access_kind,
    output logic commit,
    output logic cycle_end,
    output logic fault
);
    import n2m_cpu_pkg::*;
    logic [1:0] phase_next;
    logic fault_next;
    logic required_read;
    logic terminal;
    logic hold_plan;

    always_comb begin
        phase_next = phase;
        fault_next = fault;
        if (core_reset) begin
            phase_next = 0;
            fault_next = 0;
        end else if (gb_tick && !fault) begin
            phase_next = phase + 2'd1;
            if (terminal && complete_enable && required_read && !response_valid) fault_next = 1;
        end
    end

    assign request_valid = active && !fault && !reset_sys && !core_reset && plan_kind != ACCESS_IDLE;
    assign address = plan_address;
    assign write_data = plan_write_data;
    assign write_enable = plan_write;
    assign access_kind = plan_kind;
    assign required_read = request_valid && !plan_write;
    assign terminal = gb_tick && phase == 3 && active && !fault && !reset_sys && !core_reset;
    assign cycle_end = terminal && complete_enable && (!required_read || response_valid);
    assign commit = cycle_end && request_valid;
    assign hold_plan = active && (phase != 0 || gb_tick) && !terminal;

    `DFF_ARST_VAL(phase, phase_next, clk_sys, reset_sys, 2'b0)
    `DFF_ARST_VAL(fault, fault_next, clk_sys, reset_sys, 1'b0)

    // The M-phase continues during HALT. The front end activates/deactivates
    // only after a completed T4; a wake cannot shorten the first request.
    `N2M_ASSERT(CPU_BUS_ACTIVE_BOUNDARY, clk_sys, reset_sys || core_reset,
        $changed(active) |-> phase == 0)
    `N2M_ASSERT(CPU_BUS_RESPONSE, clk_sys, reset_sys || core_reset,
        (terminal && complete_enable && required_read) |-> (response_valid === 1'b1))
    `N2M_ASSERT(CPU_BUS_WRITE_KIND, clk_sys, reset_sys || core_reset,
        (request_valid && plan_write) |-> (plan_kind == ACCESS_DATA || plan_kind == ACCESS_STACK))
    `N2M_ASSERT_KNOWN(CPU_BUS_REQUEST_KNOWN, clk_sys, reset_sys || core_reset,
        {active, complete_enable, gb_tick, plan_kind, plan_address, plan_write, plan_write_data})
    `N2M_ASSERT_STABLE_WHEN(CPU_BUS_PLAN_STABLE, clk_sys, reset_sys || core_reset,
        hold_plan, {plan_kind, plan_address, plan_write, plan_write_data})
endmodule

`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// A captures the CPU operation. B stores its resolution with post-A sources;
// the combinational observation is already available for retirement before B.
module n2m_interrupts (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    input var logic [4:0] source_level,
    input var logic [4:0] source_event,
    input var logic [4:0] irq_ack,
    output logic io_selected,
    output logic [7:0] io_rdata,
    output logic [7:0] ie_stored,
    output logic [4:0] if_stored,
    output logic [7:0] ie_observe,
    output logic [4:0] if_observe
);
    logic reset, pending;
    logic [4:0] source_history, source_rise, flags_q, flags_next;
    logic [7:0] enable_q, enable_next;
    n2m_interrupts_pkg::interrupt_operation_t operation_a, operation_b;

    assign reset = reset_sys || core_reset;
    assign io_selected = io_address == n2m_interfaces_pkg::GB_REG_IF || io_address == n2m_interfaces_pkg::GB_REG_IE;
    assign source_rise = source_level & ~source_history;
    always_comb begin
        operation_a = '0;
        operation_a.write_if = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_IF;
        operation_a.write_ie = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_IE;
        operation_a.data = io_wdata;
        operation_a.ack = irq_ack;

        flags_next = flags_q | source_rise | source_event;
        enable_next = enable_q;
        if (pending) begin
            if (operation_b.write_if) flags_next = operation_b.data[4:0];
            flags_next = flags_next & ~operation_b.ack;
            if (operation_b.write_ie) enable_next = operation_b.data;
        end
    end

    `DFF_ARST_VAL(pending, gb_tick, clk_sys, reset, 1'b0)
    `DFF_ARST_VAL(operation_b, gb_tick ? operation_a : operation_b, clk_sys, reset, '0)
    `DFF_ARST_VAL(source_history, source_level, clk_sys, reset, 5'd0)
    `DFF_ARST_VAL(flags_q, flags_next, clk_sys, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[4:0])
    `DFF_ARST_VAL(enable_q, enable_next, clk_sys, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)

    assign if_stored = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[4:0] : flags_q;
    assign ie_stored = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : enable_q;
    assign if_observe = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[4:0] : flags_next;
    assign ie_observe = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : enable_next;
    assign io_rdata = io_address == n2m_interfaces_pkg::GB_REG_IF ? {3'b111, if_stored} :
        (io_address == n2m_interfaces_pkg::GB_REG_IE ? ie_stored : 8'd0);

    `N2M_ASSERT(INTERRUPT_CAPTURE_SPACING, clk_sys, reset, !(pending && gb_tick))
    `N2M_ASSERT(INTERRUPT_COMMIT_BOUNDARY, clk_sys, reset,
        !io_commit || (gb_tick && io_selected))
    `N2M_ASSERT(INTERRUPT_ACK_BOUNDARY, clk_sys, reset,
        irq_ack == 0 || gb_tick)
    `N2M_ASSERT(INTERRUPT_ACK_ONEHOT, clk_sys, reset, $onehot0(irq_ack))
    `N2M_ASSERT_KNOWN(INTERRUPT_CONTROLS, clk_sys, reset,
        {gb_tick, io_commit, io_write, source_level, source_event, irq_ack})
    `N2M_ASSERT(INTERRUPT_WRITE_KNOWN, clk_sys, reset,
        !(io_commit && io_write) || !$isunknown({io_address, io_wdata}))
    `N2M_ASSERT_KNOWN(INTERRUPT_OBSERVATION, clk_sys, reset,
        {if_stored, ie_stored, if_observe, ie_observe})
endmodule

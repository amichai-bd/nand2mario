`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Transfer events enter the arbiter; this module never writes a backing store.
module n2m_dma_engine (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic [1:0] cpu_phase,
    input var logic progress_enable,
    input var logic ff46_write,
    input var logic [7:0] ff46_wdata,
    input var logic [7:0] source_data,
    input var logic source_valid,
    output logic [7:0] ff46_rdata,
    output logic source_request,
    output logic [15:0] source_address,
    output logic write_valid,
    output logic [7:0] write_offset,
    output logic [7:0] write_data,
    output logic active,
    output logic fault
);
    n2m_dma_pkg::dma_state_t state_q, state_next, reset_value;
    logic reset, advance, missing_response;
    logic [7:0] source_page;
    assign reset = reset_sys || core_reset;
    assign reset_value = {n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL, 8'd0, 3'b000};
    assign advance = !reset && !state_q.fault && gb_tick &&
        cpu_phase == 2'd3 && progress_enable;
    assign missing_response = advance && state_q.active && !source_valid;
    assign source_page = state_q.page >= 8'he0 ? state_q.page - 8'h20 : state_q.page;
    assign source_address = {source_page, state_q.offset};
    assign source_request = !reset && !state_q.fault && state_q.active;
    assign active = source_request;
    assign fault = !reset && state_q.fault;
    assign ff46_rdata = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.page;
    assign write_valid = advance && state_q.active && source_valid;
    assign write_offset = state_q.offset;
    assign write_data = source_data;
    always_comb begin
        state_next = state_q;
        if (missing_response) state_next.fault = 1'b1;
        else if (advance) begin
            if (state_q.active) begin
                if (state_q.offset == 8'd159) state_next.active = 1'b0;
                else state_next.offset = state_q.offset + 8'd1;
            end
            // M1 consumes the M0 trigger after any old-transfer byte. LENE
            // resets both counter and completion; restart wins over terminal.
            if (state_q.pending) begin
                state_next.offset = 8'd0;
                state_next.active = 1'b1;
            end
            state_next.pending = ff46_write;
            if (ff46_write) state_next.page = ff46_wdata;
        end
    end
    `DFF_ARST_VAL(state_q, state_next, clk_sys, reset, reset_value)
    `N2M_ASSERT(DMA_FF46_BOUNDARY, clk_sys, reset,
        !ff46_write || (advance && !missing_response))
    `N2M_ASSERT(DMA_SOURCE_SERVICE, clk_sys, reset, !missing_response)
    `N2M_ASSERT(DMA_OFFSET_RANGE, clk_sys, reset,
        !state_q.active || state_q.offset < 8'd160)
    `N2M_ASSERT_KNOWN(DMA_CONTROLS, clk_sys, reset,
        {gb_tick, cpu_phase, progress_enable, ff46_write, source_valid})
    `N2M_ASSERT(DMA_SOURCE_KNOWN, clk_sys, reset,
        !write_valid || !$isunknown(source_data))
    `N2M_ASSERT(DMA_PAGE_KNOWN, clk_sys, reset,
        !ff46_write || !$isunknown(ff46_wdata))
    `N2M_ASSERT_STABLE_WHEN(DMA_SUSPEND_HOLD, clk_sys, reset,
        !advance, state_q)
endmodule

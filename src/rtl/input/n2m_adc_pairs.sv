`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
module n2m_adc_pairs #(
    parameter int unsigned INTERVAL_CYCLES = 25000,
    parameter int unsigned LIMIT_CYCLES = 500000
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic adc_available,
    output logic command_valid,
    output logic [4:0] command_channel,
    input var logic command_ready,
    input var logic response_valid,
    input var logic [4:0] response_channel,
    input var logic [11:0] response_data,
    output logic pair_valid,
    output logic [11:0] pair_x,
    output logic [11:0] pair_y,
    output logic fresh,
    output logic protocol_fault
);
    localparam int unsigned AGE_BITS = $clog2(LIMIT_CYCLES + 1);
    localparam int unsigned INTERVAL_BITS = $clog2(INTERVAL_CYCLES + 1);
    n2m_controls_pkg::pair_state_t state_q;
    n2m_controls_pkg::pair_state_t state_next;
    logic [AGE_BITS-1:0] pair_age_q;
    logic [AGE_BITS-1:0] pair_age_next;
    logic [AGE_BITS-1:0] fresh_age_q;
    logic [AGE_BITS-1:0] fresh_age_next;
    logic [INTERVAL_BITS-1:0] interval_q;
    logic [INTERVAL_BITS-1:0] interval_next;
    logic [11:0] x_q;
    logic [11:0] x_next;
    logic [4:0] expected_q;
    logic [4:0] expected_next;
    logic fresh_q;
    logic fresh_next;
    logic fault_next;
    logic outstanding;
    logic expired;
    logic bad_response;

    assign outstanding = state_q == n2m_controls_pkg::PAIR_WAIT_X || state_q == n2m_controls_pkg::PAIR_WAIT_Y || state_q == n2m_controls_pkg::PAIR_DRAIN;
    assign command_valid = adc_available && !reset_sys && !protocol_fault &&
        ((state_q == n2m_controls_pkg::PAIR_IDLE && interval_q == INTERVAL_BITS'(INTERVAL_CYCLES)) || state_q == n2m_controls_pkg::PAIR_REQUEST_Y);
    assign command_channel = state_q == n2m_controls_pkg::PAIR_REQUEST_Y ? 5'd2 : 5'd1;
    assign expired = (fresh_q && fresh_age_q == AGE_BITS'(LIMIT_CYCLES - 1)) ||
        ((state_q == n2m_controls_pkg::PAIR_WAIT_X || state_q == n2m_controls_pkg::PAIR_REQUEST_Y || state_q == n2m_controls_pkg::PAIR_WAIT_Y) &&
         pair_age_q == AGE_BITS'(LIMIT_CYCLES - 1));
    assign bad_response = response_valid && (!outstanding || response_channel != expected_q);
    assign pair_valid = adc_available && !reset_sys && !protocol_fault && !bad_response && !expired &&
        state_q == n2m_controls_pkg::PAIR_WAIT_Y && response_valid;
    // Expiry removes the old pair before the consumer commits this edge.
    assign fresh = adc_available && !reset_sys && !protocol_fault && !bad_response && !expired &&
        (fresh_q || pair_valid);
    assign pair_x = x_q;
    assign pair_y = response_data;

    always_comb begin
        state_next = state_q;
        pair_age_next = pair_age_q;
        fresh_age_next = fresh_age_q;
        interval_next = interval_q;
        x_next = x_q;
        expected_next = expected_q;
        fresh_next = fresh_q;
        fault_next = protocol_fault;
        if (interval_q < INTERVAL_BITS'(INTERVAL_CYCLES)) interval_next = interval_q + INTERVAL_BITS'(1);
        if (fresh_q && fresh_age_q < AGE_BITS'(LIMIT_CYCLES - 1)) fresh_age_next = fresh_age_q + AGE_BITS'(1);
        if (state_q == n2m_controls_pkg::PAIR_WAIT_X || state_q == n2m_controls_pkg::PAIR_REQUEST_Y || state_q == n2m_controls_pkg::PAIR_WAIT_Y)
            pair_age_next = pair_age_q + AGE_BITS'(1);
        if (command_valid && command_ready) begin
            expected_next = command_channel;
            if (state_q == n2m_controls_pkg::PAIR_IDLE) begin
                state_next = n2m_controls_pkg::PAIR_WAIT_X;
                pair_age_next = '0;
                interval_next = '0;
            end else state_next = n2m_controls_pkg::PAIR_WAIT_Y;
        end
        if (response_valid && !bad_response) begin
            case (state_q)
                n2m_controls_pkg::PAIR_WAIT_X: begin x_next = response_data; state_next = n2m_controls_pkg::PAIR_REQUEST_Y; end
                n2m_controls_pkg::PAIR_WAIT_Y: begin
                    state_next = n2m_controls_pkg::PAIR_IDLE;
                    fresh_next = 1'b1;
                    fresh_age_next = '0;
                end
                n2m_controls_pkg::PAIR_DRAIN: state_next = n2m_controls_pkg::PAIR_IDLE;
                default: state_next = state_q;
            endcase
        end
        if (expired) begin
            fresh_next = 1'b0;
            x_next = '0;
            pair_age_next = '0;
            if ((outstanding && !response_valid) || (command_valid && command_ready)) state_next = n2m_controls_pkg::PAIR_DRAIN;
            else state_next = n2m_controls_pkg::PAIR_IDLE;
        end
        if (bad_response && adc_available) begin
            state_next = n2m_controls_pkg::PAIR_FAULT;
            fault_next = 1'b1;
            fresh_next = 1'b0;
            x_next = '0;
        end
        if (!adc_available) begin
            state_next = protocol_fault ? n2m_controls_pkg::PAIR_FAULT : n2m_controls_pkg::PAIR_IDLE;
            fresh_next = 1'b0;
            x_next = '0;
            pair_age_next = '0;
        end
    end
    `DFF_ARST_VAL(state_q, state_next, clk_sys, reset_sys, n2m_controls_pkg::PAIR_IDLE)
    `DFF_ARST_VAL(pair_age_q, pair_age_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(fresh_age_q, fresh_age_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(interval_q, interval_next, clk_sys, reset_sys, INTERVAL_BITS'(INTERVAL_CYCLES))
    `DFF_ARST_VAL(x_q, x_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(expected_q, expected_next, clk_sys, reset_sys, 5'd1)
    `DFF_ARST_VAL(fresh_q, fresh_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(protocol_fault, fault_next, clk_sys, reset_sys, 1'b0)
    `N2M_ASSERT_NEVER(adc_pair_response_contract, clk_sys, reset_sys, adc_available && bad_response)
    `N2M_ASSERT(adc_pair_parameters, clk_sys, reset_sys, INTERVAL_CYCLES >= 1 && LIMIT_CYCLES > INTERVAL_CYCLES)
    `N2M_ASSERT_NEVER(adc_pair_no_expired_publish, clk_sys, reset_sys, pair_valid && expired)
endmodule

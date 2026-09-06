`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

module n2m_uart_tx #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer BAUD = n2m_interfaces_pkg::WIRE_BAUD
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic byte_valid,
    input var logic [7:0] byte_data,
    output logic byte_ready,
    output logic uart_tx
);
    localparam integer PHASE_BITS = $clog2(CLOCK_HZ + BAUD);
    logic [PHASE_BITS-1:0] phase;
    logic [PHASE_BITS-1:0] phase_next;
    logic [PHASE_BITS-1:0] sum;
    logic [9:0] shift;
    logic [9:0] shift_next;
    logic [3:0] remaining;
    logic [3:0] remaining_next;
    assign sum = phase + PHASE_BITS'(BAUD);
    assign byte_ready = remaining == 0 && !reset_sys;
    assign uart_tx = shift[0];
    always_comb begin
        phase_next = phase;
        shift_next = shift;
        remaining_next = remaining;
        if (remaining == 0) begin
            phase_next = '0;
            if (byte_valid) begin
                shift_next = {1'b1, byte_data, 1'b0};
                remaining_next = 10;
            end
        end else if (sum >= CLOCK_HZ) begin
            phase_next = sum - PHASE_BITS'(CLOCK_HZ);
            shift_next = {1'b1, shift[9:1]};
            remaining_next = remaining - 1'b1;
        end else phase_next = sum;
    end
    `DFF_ARST_VAL(phase, phase_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(shift, shift_next, clk_sys, reset_sys, 10'h3ff)
    `DFF_ARST_VAL(remaining, remaining_next, clk_sys, reset_sys, '0)
    `N2M_ASSERT_NO_RST(UART_TX_RATE, clk_sys, BAUD > 0 && CLOCK_HZ >= 8 * BAUD)
    `N2M_ASSERT(UART_TX_PHASE, clk_sys, reset_sys, phase < CLOCK_HZ)
    `N2M_ASSERT(UART_TX_COUNT, clk_sys, reset_sys, remaining <= 10)
    `N2M_ASSERT(UART_TX_IDLE_HIGH, clk_sys, reset_sys, remaining == 0 |-> uart_tx)
    `N2M_ASSERT_KNOWN(UART_TX_OUTPUT, clk_sys, reset_sys, ({byte_ready, uart_tx}))
    `N2M_ASSERT_STABLE_WHEN(UART_TX_BYTE_HELD, clk_sys, reset_sys,
        byte_valid && !byte_ready, ({byte_valid, byte_data}))
endmodule
`default_nettype wire

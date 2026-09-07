`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Original 8N1 receiver. Sampling uses only the second synchronizer stage.
module n2m_uart_rx #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer BAUD = n2m_interfaces_pkg::WIRE_BAUD
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic uart_rx,
    output logic byte_valid,
    output logic [7:0] byte_data,
    output logic frame_error
);
    localparam integer PHASE_BITS = $clog2(CLOCK_HZ + BAUD);
    typedef enum logic [1:0] { IDLE, START, DATA, STOP } state_t;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic rx_meta;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic rx_sync;
    state_t state;
    state_t state_next;
    logic [PHASE_BITS-1:0] phase;
    logic [PHASE_BITS-1:0] phase_next;
    logic [PHASE_BITS-1:0] sum;
    logic [2:0] bit_index;
    logic [2:0] bit_index_next;
    logic [7:0] data;
    logic [7:0] data_next;
    logic valid_next;
    logic error_next;
    assign sum = phase + PHASE_BITS'(BAUD);
    assign byte_data = data;

    always_comb begin
        state_next = state;
        phase_next = phase;
        bit_index_next = bit_index;
        data_next = data;
        valid_next = 1'b0;
        error_next = 1'b0;
        if (state == IDLE) begin
            // Half-bit preload places start validation at its midpoint.
            phase_next = PHASE_BITS'(CLOCK_HZ / 2);
            bit_index_next = '0;
            if (!rx_sync) state_next = START;
        end else if (sum >= CLOCK_HZ) begin
            // Retain fractional residue across all bits in this byte.
            phase_next = sum - PHASE_BITS'(CLOCK_HZ);
            case (state)
                START: state_next = rx_sync ? IDLE : DATA;
                DATA: begin
                    data_next[bit_index] = rx_sync;
                    if (bit_index == 7) state_next = STOP;
                    else bit_index_next = bit_index + 1'b1;
                end
                STOP: begin
                    valid_next = rx_sync;
                    error_next = !rx_sync;
                    state_next = IDLE;
                end
                default: state_next = IDLE;
            endcase
        end else phase_next = sum;
    end
    `DFF_ARST_VAL(rx_meta, uart_rx, clk_sys, reset_sys, 1'b1)
    `DFF_ARST_VAL(rx_sync, rx_meta, clk_sys, reset_sys, 1'b1)
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(phase, phase_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(bit_index, bit_index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(data, data_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(byte_valid, valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(frame_error, error_next, clk_sys, reset_sys, 1'b0)
    `N2M_ASSERT_NO_RST(UART_RX_RATE, clk_sys, BAUD > 0 && CLOCK_HZ >= 8 * BAUD)
    `N2M_ASSERT(UART_RX_PHASE, clk_sys, reset_sys, phase < CLOCK_HZ)
    `N2M_ASSERT_NEVER(UART_RX_ERROR_VALID, clk_sys, reset_sys, frame_error && byte_valid)
    `N2M_ASSERT_KNOWN(UART_RX_OUTPUT, clk_sys, reset_sys, ({byte_valid, frame_error, byte_data}))
endmodule
`default_nettype wire

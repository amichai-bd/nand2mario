`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Host transitions use the existing timebase. They never manufacture dots.
module n2m_uart_core_control (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic start,
    input var logic [7:0] command,
    input var logic [31:0] step_budget,
    input var n2m_input_pkg::input_write_t input_write,
    input var logic gb_tick,
    input var logic paused,
    input var logic core_initialized,
    input var logic instruction_complete,
    input var logic retirement_valid,
    input var logic cpu_stopped,
    output logic pause_request,
    output logic core_reset,
    output n2m_input_pkg::input_write_t accepted_input,
    output logic [31:0] epoch,
    output logic [63:0] dot_count,
    output logic [63:0] retirement_count,
    output logic busy,
    output logic done,
    output logic [7:0] status,
    output logic [63:0] completed_dot
);
    typedef enum logic [3:0] {
        IDLE, HALT_WAIT, RUN_WAIT, RESET_WAIT, RESET_ASSERT, INIT_WAIT,
        INPUT_APPLY, STEP_RUN, STEP_PAUSE, COMPLETE
    } state_t;
    state_t state, state_next;
    logic host_pause, host_pause_next;
    logic [31:0] remaining, remaining_next;
    logic [7:0] status_next;
    n2m_input_pkg::input_write_t pending_input, pending_input_next;
    logic [31:0] epoch_next;
    logic [63:0] dot_next, retirement_next, completed_dot_next;
    logic stop_step;
    assign accepted_input.valid = state == INPUT_APPLY && !gb_tick && !reset_sys && !core_reset;
    assign accepted_input.source_write = pending_input.source_write;
    assign accepted_input.value = pending_input.value;
    assign busy = state != IDLE;
    assign done = state == COMPLETE;
    assign core_reset = state == RESET_ASSERT && !reset_sys;
    assign stop_step = state == STEP_RUN && gb_tick && (instruction_complete || remaining == 1);
    // A new HALT/RESET at the current A edge must stop after that very dot.
    // paused is registered in the timebase, so this creates no tick loop.
    assign pause_request = host_pause || stop_step ||
        (start && (command == n2m_interfaces_pkg::COMMAND_HALT || command == n2m_interfaces_pkg::COMMAND_RESET));
    always_comb begin
        state_next = state;
        host_pause_next = host_pause;
        remaining_next = remaining;
        pending_input_next = pending_input;
        epoch_next = epoch;
        dot_next = dot_count + (gb_tick ? 64'd1 : 64'd0);
        retirement_next = retirement_count + (retirement_valid ? 64'd1 : 64'd0);
        status_next = status;
        completed_dot_next = completed_dot;
        case (state)
            IDLE: if (start) begin
                status_next = n2m_interfaces_pkg::STATUS_OK;
                case (command)
                    n2m_interfaces_pkg::COMMAND_HALT: begin host_pause_next = 1; state_next = HALT_WAIT; end
                    n2m_interfaces_pkg::COMMAND_RUN: begin host_pause_next = 0; state_next = RUN_WAIT; end
                    n2m_interfaces_pkg::COMMAND_RESET: begin host_pause_next = 1; state_next = RESET_WAIT; end
                    n2m_interfaces_pkg::COMMAND_INPUT: begin pending_input_next = input_write; state_next = INPUT_APPLY; end
                    n2m_interfaces_pkg::COMMAND_STEP: begin
                        if (cpu_stopped) begin
                            // An already sleeping oscillator cannot spend a dot
                            // budget. Preserve pause/input and any queued wake.
                            status_next = n2m_interfaces_pkg::STATUS_STEP_LIMIT;
                            completed_dot_next = dot_count;
                            state_next = COMPLETE;
                        end else begin
                            remaining_next = step_budget;
                            host_pause_next = 0;
                            state_next = STEP_RUN;
                        end
                    end
                    default: begin end
                endcase
            end
            HALT_WAIT: if (paused) begin
                completed_dot_next = dot_count;
                state_next = COMPLETE;
            end
            RUN_WAIT: if (!paused) state_next = COMPLETE;
            RESET_WAIT: if (paused) state_next = RESET_ASSERT;
            RESET_ASSERT: begin
                epoch_next = epoch + 1'b1;
                dot_next = 0;
                retirement_next = 0;
                state_next = INIT_WAIT;
            end
            INIT_WAIT: if (core_initialized) begin
                completed_dot_next = 0;
                state_next = COMPLETE;
            end
            INPUT_APPLY: if (!gb_tick) begin
                completed_dot_next = dot_count;
                state_next = COMPLETE;
            end
            STEP_RUN: if (gb_tick) begin
                remaining_next = remaining - 1'b1;
                if (stop_step) begin
                    host_pause_next = 1;
                    status_next = instruction_complete ? n2m_interfaces_pkg::STATUS_OK : n2m_interfaces_pkg::STATUS_STEP_LIMIT;
                    completed_dot_next = dot_next;
                    state_next = STEP_PAUSE;
                end
            end
            // Allow the finishing A capture to publish at B before replying.
            STEP_PAUSE: if (paused) state_next = COMPLETE;
            COMPLETE: state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(host_pause, host_pause_next, clk_sys, reset_sys, 1'b1)
    `DFF_ARST_VAL(remaining, remaining_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(pending_input, pending_input_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(epoch, epoch_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(dot_count, dot_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(retirement_count, retirement_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(status, status_next, clk_sys, reset_sys, n2m_interfaces_pkg::STATUS_OK)
    `DFF_ARST_VAL(completed_dot, completed_dot_next, clk_sys, reset_sys, '0)
    `N2M_ASSERT(UART_CORE_START_IDLE, clk_sys, reset_sys, start |-> !busy)
    `N2M_ASSERT(UART_CORE_RESET_PAUSED, clk_sys, reset_sys, core_reset |-> paused && !gb_tick)
    `N2M_ASSERT(UART_CORE_INIT_FROZEN, clk_sys, reset_sys, state == INIT_WAIT |-> paused && !gb_tick)
    `N2M_ASSERT(UART_STEP_BUDGET, clk_sys, reset_sys,
        start && command == n2m_interfaces_pkg::COMMAND_STEP |-> paused && step_budget != 0 && step_budget <= n2m_interfaces_pkg::WIRE_STEP_MAX_DOTS)
    `N2M_ASSERT(UART_STEP_ASLEEP_COMPLETE, clk_sys, reset_sys,
        start && command == n2m_interfaces_pkg::COMMAND_STEP && cpu_stopped |=>
            done && status == n2m_interfaces_pkg::STATUS_STEP_LIMIT && pause_request && paused && !gb_tick)
    `N2M_ASSERT_STABLE_WHEN(UART_STEP_ASLEEP_TIME, clk_sys, reset_sys,
        start && command == n2m_interfaces_pkg::COMMAND_STEP && cpu_stopped, dot_count)
    `N2M_ASSERT_KNOWN(UART_CORE_CONTROLS, clk_sys, reset_sys,
        ({start, gb_tick, paused, core_initialized, instruction_complete, retirement_valid, cpu_stopped, state}))
endmodule
`default_nettype wire

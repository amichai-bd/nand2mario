`default_nettype none
`include "src/rtl/common/macros.svh"

// Capture CPU effects at T4; publish after the bus owner applies that commit.
module n2m_cpu_retire (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var n2m_cpu_pkg::cpu_retire_capture_t capture,
    input var logic [7:0] ie,
    input var logic [4:0] iflags,
    input var logic [7:0] buttons,
    output logic retirement_valid,
    output n2m_interfaces_pkg::retirement_t retirement
);
    import n2m_interfaces_pkg::*;
    retirement_t capture_t4;
    retirement_t capture_t4_next;
    retirement_t retirement_b_next;
    logic pending_t4;
    logic pending_t4_next;
    logic retirement_valid_next;
    logic [63:0] sequence_number;
    logic [63:0] sequence_next;

    always_comb begin
        capture_t4_next = capture_t4;
        retirement_b_next = retirement;
        pending_t4_next = capture.valid;
        retirement_valid_next = pending_t4;
        sequence_next = sequence_number;
        if (pending_t4) begin
            retirement_b_next = capture_t4;
            retirement_b_next.ie = ie;
            retirement_b_next.iflags = {3'b0, iflags};
            retirement_b_next.buttons = buttons;
        end
        if (capture.valid) begin
            capture_t4_next = '0;
            capture_t4_next.version = TRACE_VERSION;
            capture_t4_next.kind = capture.is_interrupt ? TRACE_INTERRUPT : TRACE_INSTRUCTION;
            capture_t4_next.epoch = capture.epoch;
            capture_t4_next.seq = sequence_number;
            capture_t4_next.dot = capture.dot_after;
            capture_t4_next.pc_before = capture.pc_before;
            capture_t4_next.pc_after = capture.pc_after;
            if (!capture.is_interrupt) begin
                capture_t4_next.opcode_length = {6'b0, capture.fetched_length};
                case (capture.fetched_length)
                    1: capture_t4_next.opcode = {16'b0, capture.fetched_bytes[7:0]};
                    2: capture_t4_next.opcode = {8'b0, capture.fetched_bytes[15:0]};
                    3: capture_t4_next.opcode = capture.fetched_bytes;
                    default: capture_t4_next.opcode = '0;
                endcase
            end
            capture_t4_next.a = capture.registers_after.a;
            capture_t4_next.f = {capture.registers_after.f[7:4], 4'b0};
            capture_t4_next.b = capture.registers_after.b;
            capture_t4_next.c = capture.registers_after.c;
            capture_t4_next.d = capture.registers_after.d;
            capture_t4_next.e = capture.registers_after.e;
            capture_t4_next.h = capture.registers_after.h;
            capture_t4_next.l = capture.registers_after.l;
            capture_t4_next.sp = capture.registers_after.sp;
            capture_t4_next.ime = {7'b0, capture.ime_after};
            capture_t4_next.ime_delay = {7'b0, capture.ime_delay_after};
            capture_t4_next.halted = {7'b0, capture.halted_after};
            capture_t4_next.stopped = {7'b0, capture.stopped_after};
            capture_t4_next.halt_bug = {7'b0, capture.halt_bug_after};
            sequence_next = sequence_number + 64'd1;
        end
        if (core_reset) begin
            capture_t4_next = '0;
            retirement_b_next = '0;
            pending_t4_next = 0;
            retirement_valid_next = 0;
            sequence_next = 0;
        end
    end

    `DFF_ARST_VAL(capture_t4, capture_t4_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(retirement, retirement_b_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(pending_t4, pending_t4_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(retirement_valid, retirement_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(sequence_number, sequence_next, clk_sys, reset_sys, 64'b0)

    `N2M_ASSERT(CPU_RETIRE_SPACING, clk_sys, reset_sys || core_reset,
        !(capture.valid && pending_t4))
    `N2M_ASSERT(CPU_RETIRE_LENGTH, clk_sys, reset_sys || core_reset,
        (capture.valid && !capture.is_interrupt) |-> capture.fetched_length != 0)
    `N2M_ASSERT(CPU_RETIRE_FLAGS, clk_sys, reset_sys || core_reset,
        capture.valid |-> capture.registers_after.f[3:0] == 0)
    `N2M_ASSERT_KNOWN(CPU_RETIRE_KNOWN, clk_sys, reset_sys || core_reset,
        {capture.valid, pending_t4, retirement_valid})
endmodule

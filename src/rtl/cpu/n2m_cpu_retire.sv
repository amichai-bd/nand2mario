`default_nettype none
`include "src/rtl/common/macros.svh"

// Capture CPU effects at T4; publish after the bus owner applies that commit.
module n2m_cpu_retire (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic event_valid,
    input var logic event_interrupt,
    input var n2m_cpu_pkg::cpu_registers_t registers_after,
    input var logic [15:0] pc_before,
    input var logic [15:0] pc_after,
    input var logic [23:0] fetched_bytes,
    input var logic [1:0] fetched_length,
    input var logic ime_after,
    input var logic ime_delay_after,
    input var logic halted_after,
    input var logic stopped_after,
    input var logic halt_bug_after,
    input var logic [31:0] epoch,
    input var logic [63:0] dot_after,
    input var logic [7:0] ie,
    input var logic [4:0] iflags,
    input var logic [7:0] buttons,
    output logic retirement_valid,
    output n2m_interfaces_pkg::retirement_t retirement
);
    import n2m_interfaces_pkg::*;
    retirement_t captured;
    retirement_t captured_next;
    retirement_t retirement_next;
    logic pending;
    logic pending_next;
    logic retirement_valid_next;
    logic [63:0] sequence_number;
    logic [63:0] sequence_next;

    always_comb begin
        captured_next = captured;
        retirement_next = retirement;
        pending_next = event_valid;
        retirement_valid_next = pending;
        sequence_next = sequence_number;
        if (pending) begin
            retirement_next = captured;
            retirement_next.ie = ie;
            retirement_next.iflags = {3'b0, iflags};
            retirement_next.buttons = buttons;
        end
        if (event_valid) begin
            captured_next = '0;
            captured_next.version = TRACE_VERSION;
            captured_next.kind = event_interrupt ? TRACE_INTERRUPT : TRACE_INSTRUCTION;
            captured_next.epoch = epoch;
            captured_next.seq = sequence_number;
            captured_next.dot = dot_after;
            captured_next.pc_before = pc_before;
            captured_next.pc_after = pc_after;
            if (!event_interrupt) begin
                captured_next.opcode_length = {6'b0, fetched_length};
                case (fetched_length)
                    1: captured_next.opcode = {16'b0, fetched_bytes[7:0]};
                    2: captured_next.opcode = {8'b0, fetched_bytes[15:0]};
                    3: captured_next.opcode = fetched_bytes;
                    default: captured_next.opcode = '0;
                endcase
            end
            captured_next.a = registers_after.a;
            captured_next.f = {registers_after.f[7:4], 4'b0};
            captured_next.b = registers_after.b;
            captured_next.c = registers_after.c;
            captured_next.d = registers_after.d;
            captured_next.e = registers_after.e;
            captured_next.h = registers_after.h;
            captured_next.l = registers_after.l;
            captured_next.sp = registers_after.sp;
            captured_next.ime = {7'b0, ime_after};
            captured_next.ime_delay = {7'b0, ime_delay_after};
            captured_next.halted = {7'b0, halted_after};
            captured_next.stopped = {7'b0, stopped_after};
            captured_next.halt_bug = {7'b0, halt_bug_after};
            sequence_next = sequence_number + 64'd1;
        end
        if (core_reset) begin
            captured_next = '0;
            retirement_next = '0;
            pending_next = 0;
            retirement_valid_next = 0;
            sequence_next = 0;
        end
    end

    `DFF_ARST_VAL(captured, captured_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(retirement, retirement_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(pending, pending_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(retirement_valid, retirement_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(sequence_number, sequence_next, clk_sys, reset_sys, 64'b0)

    `N2M_ASSERT(CPU_RETIRE_SPACING, clk_sys, reset_sys || core_reset,
        !(event_valid && pending))
    `N2M_ASSERT(CPU_RETIRE_LENGTH, clk_sys, reset_sys || core_reset,
        (event_valid && !event_interrupt) |-> fetched_length != 0)
    `N2M_ASSERT(CPU_RETIRE_FLAGS, clk_sys, reset_sys || core_reset,
        event_valid |-> registers_after.f[3:0] == 0)
    `N2M_ASSERT_KNOWN(CPU_RETIRE_KNOWN, clk_sys, reset_sys || core_reset,
        {event_valid, pending, retirement_valid})
endmodule
